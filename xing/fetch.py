"""XING transport: plain curl_cffi POSTs to the site's own GraphQL API,
validated 2026-10-19 (no cookies, no login).

Surface: https://www.xing.com/xing-one/api — the API behind xing.com's
React frontend. Every operation this package sends (xing/gql.py) answers
anonymously: job search with filters and aggregations, job details,
similar jobs, company pages (header, about, locations, related companies,
employees, news), public member profiles, directory listings and the
search box suggestions. The HTML pages are never fetched. No WAF, no
challenge, no rate limit seen (25 searches in 19 s, all 200; the frontend
sends the same calls).

Two things the API wants from a logged-out client:
  * a NEW-WORK-LOGGED-OUT-VISITOR-ID header (any UUID) — fields that take
    it (user interactions) are not requested, but the header is sent so a
    future field never fails on it;
  * an egress the site is happy to show jobs to: from an Indian office IP
    about two thirds of the search hits come back as UnauthorizedJob
    {reason: GEO_FENCED}, while DE / AT / CH / US residential exits see
    all of them.

Egress (2026-10-21): every call rides the exit config.xing_proxy() names: in
production the Frankfurt gateway exit (knob XING_EXIT = "gateway:de", 2026-11-11;
a fresh gateway address per request, every job visible through it), with
XING_EXIT = None a sticky residential exit in config.XING_PROXY_COUNTRY, de;
a failed or geo-fenced call is retried on a fresh exit (a geo-fenced or
timed-out gateway call, and a call's last retry, on the residential one). XING never sees the
server's own IP: with no proxy the call fails, unless the config opts in
to direct egress (config.XING_ALLOW_DIRECT — the open-source kit, which
runs from the user's own machine, sets it).

The headful patchright click-through (indeed/fetch.py _browser_page) is
the escalation after that — not built while plain HTTP works.

Failure taxonomy (scraper_errors, mapped to HTTP by route_glue):
  XingUpstreamError  transport failure / 5xx / unexpected body   — retryable
  XingBlocked        403 / 429 / challenge page                   — retryable on a new exit
  XingGeoFenced      the answer hid jobs for our egress           — retryable on a residential exit
  XingQueryError     the API refused our document (schema drift)  — not retried
  XingBadRequest     the API rejected a value (bad scrambled id…) — never retried
  XingNotFound       no such job / company / profile              — never retried

Smoke test:  python xing/fetch.py [keywords]
"""
import json
import fastjson
import os
import sys
import threading
import time
import uuid
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
import egress
from scraper_errors import BadRequest, Blocked, NotFound, UpstreamError
from xing import gql
from xing import refdata as R
from scraper_utils import debug, memo, sessions

IMPERSONATE = "chrome"
TIMEOUT = (10, 60)
HEADERS = {
    "accept": "application/json",
    "content-type": "application/json",
    "origin": R.BASE,
    "referer": R.BASE + "/jobs/search",
}
CHALLENGE_MARKERS = ("just a moment", "challenge-platform", "access denied", "captcha")
QUERY_ERROR_IDS = {"QUERY_ANALYSIS_ERROR", "OPERATION_NAME_MISSING", "ERRONEOUS_VARIABLES"}


class XingUpstreamError(UpstreamError):
    """Transport failure, 5xx or an unexpected body — retryable."""


class XingBlocked(XingUpstreamError, Blocked):
    """403 / 429 / a challenge page — retryable on a fresh exit."""


class XingGeoFenced(XingUpstreamError):
    """The API hid jobs (UnauthorizedJob GEO_FENCED) for our egress — retry on a residential exit."""


class XingQueryError(XingUpstreamError):
    """XING refused our GraphQL document (schema drift) — a retry cannot help."""


class XingBadRequest(BadRequest):
    """XING rejected a value (an id that does not unscramble, an unknown enum) — never retried."""


class XingNotFound(NotFound):
    """No such job / company / profile — never retried."""


def dump_debug(name, text):
    """Write a raw response to $XING_DEBUG_DIR/<name>.txt for post-mortems."""
    debug.dump("XING_DEBUG_DIR", name, text, render=lambda body: json.dumps(body, ensure_ascii=False))


# ---- curl sessions (per thread, keyed by exit) ---------------------------------------------------

_local = threading.local()


def _sessions():
    return sessions.thread_store(_local)


def _session(key, proxy):
    store = _sessions()
    sess = store.get(key)
    if sess is None:
        sess = egress.new_session(proxy, impersonate=IMPERSONATE)     # a proxy URL, None, or the gateway exit ("gateway:de")
        sess.headers.update({**HEADERS, "new-work-logged-out-visitor-id": str(uuid.uuid4())})
        sess.headers["accept-language"] = egress.accept_language(proxy)
        store[key] = sess
        while len(store) > 4:
            _, old = store.popitem(last=False)
            try:
                old.close()
            except Exception:
                pass
    else:
        store.move_to_end(key)
    return sess


def _drop_session(key):
    sessions.drop_keyed(_sessions(), key)


def _proxy(fallback=False):
    """The exit for a session; refuses to go on without one (XING never sees
    the server's own IP) unless the config opts in to direct egress."""
    proxy = config.xing_proxy(fallback=fallback)
    if not proxy and not getattr(config, "XING_ALLOW_DIRECT", False):
        raise XingUpstreamError("no XING proxy configured (XING is never contacted from the server's IP)")
    return proxy


# After a geo-fenced answer on direct egress every call starts on the
# fallback exit until this deadline (config.XING_GEO_FENCE_HOLD_SECONDS):
# the fence is per egress IP, so the next direct attempt would only waste
# a round trip.
_fenced_until = 0.0
_fence_lock = threading.Lock()


def _hold_fallback():
    return time.monotonic() < _fenced_until


def _note_geo_fence():
    global _fenced_until
    with _fence_lock:
        _fenced_until = time.monotonic() + float(config.XING_GEO_FENCE_HOLD_SECONDS)


def _gateway_timed_out(error):
    """the gateway's own 29 s limit (exit_gateway.GatewayError, 504): the API
    was still answering, so only an exit that can wait (TIMEOUT) will do."""
    return type(error).__name__ == "GatewayError" and " 504 " in str(error)


def _attempts(label, send):
    """Run send(session) under the retry policy: XingUpstreamError (incl.
    Blocked / GeoFenced) retries on a fresh exit up to
    config.XING_MAX_ATTEMPTS times; BadRequest / NotFound / QueryError
    surface at once. With the gateway exit as the exit (config.XING_EXIT) a
    retry stays on the gateway, except the LAST one and every retry after a
    geo-fenced answer or a gateway timeout: those ride the residential exit
    (config.xing_proxy(fallback=True)), so a gateway problem degrades to the
    residential path instead of an error. A geo-fenced direct answer puts
    every later call on the fallback exit for
    config.XING_GEO_FENCE_HOLD_SECONDS."""
    attempts = max(1, int(config.XING_MAX_ATTEMPTS))
    last = None
    fenced = None           # the last geo-fenced answer: served when no exit sees more
    residential = False     # the gateway hid jobs or timed out: the rest of this call rides the residential exit
    on_gateway = False      # the previous attempt rode the gateway: a middle retry stays on it (a fresh gateway address)
    for attempt in range(1, attempts + 1):
        proxy = _proxy(fallback=_hold_fallback() or (attempt > 1 and (residential or attempt == attempts or not on_gateway)))
        on_gateway = bool(egress.gateway_country(proxy))
        key = f"{attempt if proxy else 0}:{proxy or 'direct'}"
        sess = _session(key, proxy)
        try:
            return send(sess)
        except (XingBadRequest, XingNotFound, XingQueryError):
            raise
        except XingGeoFenced as e:
            last = e
            if getattr(e, "data", None) is not None:
                fenced = e.data
            if not proxy:
                _note_geo_fence()
            residential = True      # the fence follows the exit's country: another gateway address sees the same
        except XingUpstreamError as e:
            last = e
        except Exception as e:
            last = XingUpstreamError(f"request failed on {label}: {type(e).__name__}: {e}")
            residential = residential or _gateway_timed_out(e)
        _drop_session(key)
        print(f"xing: attempt {attempt}/{attempts} on {label} failed: {last}")
        if attempt < attempts:
            time.sleep(0.5 * attempt)
    if fenced is not None:
        # still fenced on every exit: the rows we could see, hidden ones as
        # {id, is_visible: false, reason} (jobs.py docstring)
        return fenced
    raise last


# ---- GraphQL -------------------------------------------------------------------------------------------

# Field-level errors of the last answer on this thread (tolerated when
# real data came with them) — for the fixture capture / debugging.
_diag = threading.local()


def last_errors():
    return list(getattr(_diag, "errors", None) or [])


def _unscramble_message(errors):
    for e in errors:
        if e.get("id") == "FIELD_SCRAMBLING_ERROR":
            details = e.get("details") or {}
            return f"'{details.get('id')}' is not a valid XING id"
    return None


def _violation(errors):
    for e in errors:
        violations = (e.get("details") or {}).get("violations") or []
        if violations:
            return str(violations[0]).split("(line")[0].strip()[:300]
    return "; ".join(str(e.get("message")) for e in errors)[:300]


def _classify(resp, label):
    status = resp.status_code
    text = resp.text or ""
    head = text[:4000].lower()
    if status in (403, 429, 503) and any(m in head for m in CHALLENGE_MARKERS):
        dump_debug("challenged", text)
        raise XingBlocked(f"challenge (HTTP {status}) on {label}")
    if status in (401, 403, 429):
        raise XingBlocked(f"HTTP {status} on {label}")
    try:
        body = fastjson.loads(text) if text.strip() else None
    except ValueError:
        body = None
    if not isinstance(body, dict):
        dump_debug("non_json", text)
        if status >= 500:
            raise XingUpstreamError(f"HTTP {status} on {label}")
        raise XingUpstreamError(f"non-JSON answer (HTTP {status}) on {label}")
    errors = [e for e in (body.get("errors") or []) if isinstance(e, dict)]
    _diag.errors = errors
    data = body.get("data")
    if data is None:
        ids = {e.get("id") for e in errors}
        if ids & QUERY_ERROR_IDS:
            dump_debug("query_error", text)
            # a bad variable value (an id that fails to unscramble, an enum
            # the API does not know) is the caller's, not schema drift
            if "ERRONEOUS_VARIABLES" in ids:
                raise XingBadRequest(f"XING rejected a value on {label}: {_violation(errors)}")
            raise XingQueryError(f"XING refused the query on {label}: {_violation(errors)}")
        bad = _unscramble_message(errors)
        if bad:
            raise XingBadRequest(bad)
        if status >= 500:
            raise XingUpstreamError(f"HTTP {status} on {label}")
        message = "; ".join(str(e.get("message")) for e in errors)[:300] or f"HTTP {status}"
        raise XingUpstreamError(f"no data on {label}: {message}")
    # a field-level unscramble error with partial data is still the caller's bad id
    bad = _unscramble_message(errors)
    if bad:
        raise XingBadRequest(bad)
    return data


def graphql(op, variables, label=None, check=None):
    """POST one operation -> its `data` dict. `check(data)` may raise
    XingGeoFenced / XingUpstreamError to force a retry on a fresh exit."""
    doc = gql.DOCS[op]
    label = label or op
    payload = json.dumps({"operationName": op, "query": doc, "variables": variables or {}}, ensure_ascii=False)

    def send(sess):
        resp = sess.post(R.GRAPHQL_URL, data=payload.encode("utf-8"), timeout=TIMEOUT)
        data = _classify(resp, label)
        if check is not None:
            try:
                check(data)
            except XingGeoFenced as e:
                e.data = data
                raise
        return data
    return _attempts(label, send)


# ---- memo + fan-out ---------------------------------------------------------------------------------

_memo = OrderedDict()
_memo_lock = threading.Lock()
MEMO_TTL = 24 * 3600
MEMO_MAX = 512


def memoized(key, fn, ttl=MEMO_TTL):
    """In-process memo for lookups that never change (slug -> company id)."""
    return memo.memoized(_memo, _memo_lock, MEMO_MAX, key, fn, ttl)


def run_parallel(fns, workers=None):
    """Run zero-arg callables in parallel; results align with `fns`. Each
    result is ("ok", value) or ("error", exception)."""
    def guard(fn):
        try:
            return ("ok", fn())
        except Exception as e:
            return ("error", e)
    if not fns:
        return []
    workers = workers or int(config.XING_WORKERS)
    with ThreadPoolExecutor(max_workers=max(1, min(workers, len(fns)))) as ex:
        return list(ex.map(guard, fns))


if __name__ == "__main__":
    term = sys.argv[1] if len(sys.argv) > 1 else "python"
    out = graphql("JobSearchByQuery", {"query": {"keywords": term}, "consumer": R.CONSUMER_SEARCH, "limit": 5,
                                       "offset": 0, "returnAggregations": False})
    rows = out["jobSearchByQuery"]["collection"]
    print(out["jobSearchByQuery"]["boundedTotal"], [(r["jobDetail"].get("__typename"), r["jobDetail"].get("title")) for r in rows])
