"""XING input parsing: ONE param per input that auto-detects its forms
(tripadvisor QueryOrLinkField convention, never a sibling `url`/`id` pair).
Every resolver returns plain JSON values so validated params stay usable as
a response-cache key, and raises ValueError with a user-facing message.

  job       155730561 | 155730561.9e044b | berlin-java-full-stack-entwickler-155730561
            | https://www.xing.com/jobs/berlin-java-full-stack-entwickler-155730561
                                                      -> "155730561" (the posting id)
  company   sap | https://www.xing.com/pages/sap | https://www.xing.com/pages/sap/jobs
            | https://www.xing.com/jobs/c-sap                       -> "sap" (the page slug)
  profile   Harish_Govindarajalu2 | https://www.xing.com/profile/Harish_Govindarajalu2
                                                      -> "Harish_Govindarajalu2" (the page name)
  link      https://www.xing.com/jobs/search?keywords=java&location=Berlin&employmentType=FULL_TIME.ef2fe9
                                                      -> the /xing/jobs/search params it encodes
"""
import re
from urllib.parse import parse_qs, unquote, urlparse

from xing import refdata as R

HOSTS = {"www.xing.com", "xing.com", "m.xing.com", "login.xing.com"}
_POSTING_ID_RE = re.compile(r"^\d{5,12}$")
_SCRAMBLED_RE = re.compile(r"^(\d{5,12})\.[0-9a-f]{6}$")
_SLUG_ID_RE = re.compile(r"-(\d{5,12})$")
_JOB_PATH_RE = re.compile(r"^/jobs/(?:[a-z0-9\-]*-)?(\d{5,12})/?$", re.I)
_PAGE_PATH_RE = re.compile(r"^/pages/([^/?#]+)", re.I)
_JOBS_COMPANY_PATH_RE = re.compile(r"^/jobs/c-([^/?#]+)", re.I)
_PROFILE_PATH_RE = re.compile(r"^/profile/([^/?#]+)", re.I)
_SLUG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\-]{0,120}$")
_PAGE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\-]{0,120}$")

JOB_HINT = ("Must be a XING job id (155730561), a job slug (berlin-java-entwickler-155730561) "
            "or a job link (https://www.xing.com/jobs/…-155730561).")
COMPANY_HINT = ("Must be a XING company page slug (sap) or a company link "
                "(https://www.xing.com/pages/sap, https://www.xing.com/jobs/c-sap).")
PROFILE_HINT = ("Must be a XING profile name (Harish_Govindarajalu2) or a profile link "
                "(https://www.xing.com/profile/Harish_Govindarajalu2).")
LINK_HINT = "Must be a XING job search link (https://www.xing.com/jobs/search?keywords=…&location=…)."


def _parse_url(value):
    """-> (path, query dict) when value is a xing.com URL; None when it is
    not URL-like; ValueError for another site."""
    raw = (value or "").strip()
    low = raw.lower()
    if low.startswith("//"):
        raw = "https:" + raw
    elif not low.startswith(("http://", "https://")):
        head = low.split("/", 1)[0]
        if head not in HOSTS:
            return None
        raw = "https://" + raw
    parsed = urlparse(raw)
    host = (parsed.hostname or "").lower()
    if host not in HOSTS:
        raise ValueError(f"'{host}' is not xing.com.")
    path = unquote(parsed.path)
    query = parse_qs(parsed.query)
    if host == "login.xing.com":            # login wall redirect: the real page is in dest_url
        dest = (query.get("dest_url") or [None])[0]
        if dest:
            return _parse_url(dest)
    return path, query


# ---- jobs -----------------------------------------------------------------------------------

def resolve_job(value):
    raw = (value or "").strip()
    if _POSTING_ID_RE.match(raw):
        return raw
    match = _SCRAMBLED_RE.match(raw)
    if match:
        return match.group(1)
    try:
        url = _parse_url(raw)
    except ValueError as e:
        raise ValueError(f"{e} {JOB_HINT}")
    if url:
        path = url[0].rstrip("/")
        match = _JOB_PATH_RE.match(path)
        if match:
            return match.group(1)
        raise ValueError(f"'{raw}' is not a job link. {JOB_HINT}")
    match = _SLUG_ID_RE.search(raw)
    if match and _SLUG_RE.match(raw):
        return match.group(1)
    raise ValueError(f"'{raw}' has no job id. {JOB_HINT}")


def resolve_jobs(value, max_items=10):
    out = []
    for item in str(value or "").split(","):
        item = item.strip()
        if not item:
            continue
        try:
            job = resolve_job(item)
        except ValueError as e:
            raise ValueError(f"'{item}': {e}")
        if job not in out:
            out.append(job)
    if not out:
        raise ValueError("Must list at least one job id or link (comma-separated).")
    if len(out) > max_items:
        raise ValueError(f"At most {max_items} jobs.")
    return out


# ---- companies -------------------------------------------------------------------------------

def resolve_company(value):
    raw = (value or "").strip()
    if not raw:
        raise ValueError(COMPANY_HINT)
    try:
        url = _parse_url(raw)
    except ValueError as e:
        raise ValueError(f"{e} {COMPANY_HINT}")
    if url:
        path = url[0]
        match = _PAGE_PATH_RE.match(path) or _JOBS_COMPANY_PATH_RE.match(path)
        if match and _SLUG_RE.match(match.group(1)):
            return match.group(1).lower()
        raise ValueError(f"'{raw}' is not a company page link. {COMPANY_HINT}")
    if "/" in raw or " " in raw or not _SLUG_RE.match(raw):
        raise ValueError(f"'{raw}' is not a company page slug. {COMPANY_HINT}")
    return raw.lower()


# ---- profiles -------------------------------------------------------------------------------

def resolve_profile(value):
    raw = (value or "").strip()
    if not raw:
        raise ValueError(PROFILE_HINT)
    try:
        url = _parse_url(raw)
    except ValueError as e:
        raise ValueError(f"{e} {PROFILE_HINT}")
    if url:
        match = _PROFILE_PATH_RE.match(url[0])
        if match and _PAGE_NAME_RE.match(match.group(1)):
            return match.group(1)
        raise ValueError(f"'{raw}' is not a profile link. {PROFILE_HINT}")
    if not _PAGE_NAME_RE.match(raw):
        raise ValueError(f"'{raw}' is not a profile name. {PROFILE_HINT}")
    return raw


# ---- search links ------------------------------------------------------------------------------

# the site's URL params -> (our param, the public-value table)
_ID_TABLES = {
    "employmentType": ("employment_type", R.EMPLOYMENT_TYPES), "type": ("employment_type", R.EMPLOYMENT_TYPES),
    "careerLevel": ("career_level", R.CAREER_LEVELS), "level": ("career_level", R.CAREER_LEVELS),
    "remoteOption": ("remote", R.REMOTE_OPTIONS), "remote": ("remote", R.REMOTE_OPTIONS),
    "discipline": ("discipline", R.DISCIPLINES),
}
_SINCE = {v.lower(): k for k, v in R.POSTED_WITHIN.items()}


def _first(query, *names):
    for name in names:
        for value in query.get(name, []):
            value = value.strip()
            if value:
                return value
    return None


def _ids(query, name):
    out = []
    for value in query.get(name, []):
        out += [v.strip() for v in value.split(",") if v.strip()]
    return out


def resolve_search_link(value):
    """A xing.com/jobs/search link -> the /xing/jobs/search params it encodes
    (keywords, location, radius, city, filters, sort, posted_within, page)."""
    raw = (value or "").strip()
    try:
        url = _parse_url(raw)
    except ValueError as e:
        raise ValueError(f"{e} {LINK_HINT}")
    if not url:
        raise ValueError(LINK_HINT)
    path, query = url
    if not path.rstrip("/").startswith("/jobs/search"):
        if _JOB_PATH_RE.match(path.rstrip("/")):
            raise ValueError("That is a single job's link — use /xing/jobs/details for it.")
        raise ValueError(f"'{path}' is not a job search page. {LINK_HINT}")
    out = {"keywords": _first(query, "keywords", "q"), "location": _first(query, "location"),
           "city": _first(query, "cityId"), "radius": None, "page": 1, "sort": "relevance", "posted_within": None,
           "employment_type": [], "career_level": [], "remote": [], "discipline": [],
           "industry": _ids(query, "industry"), "company": _ids(query, "company"), "salary_min": None, "salary_max": None}
    radius = _first(query, "radius")
    if radius and radius.isdigit():
        out["radius"] = int(radius)
    page = _first(query, "page")
    if page and page.isdigit():
        out["page"] = max(1, int(page))
    sort = (_first(query, "sort") or "").lower()
    if sort in R.SORTS:
        out["sort"] = sort
    since = (_first(query, "sincePeriod") or "").lower()
    if since in _SINCE:
        out["posted_within"] = _SINCE[since]
    for site_name, (ours, table) in _ID_TABLES.items():
        for sid in _ids(query, site_name):
            public = R.public_value(ours, sid) or (sid.lower() if sid.lower() in table else None)
            if public and public not in out[ours]:
                out[ours].append(public)
    salary = _first(query, "salary")
    if salary:
        parts = [p for p in re.split(r"[-–]", salary) if p.strip().isdigit()]
        if parts:
            out["salary_min"] = int(parts[0])
            if len(parts) > 1:
                out["salary_max"] = int(parts[1])
    return {k: v for k, v in out.items() if v not in (None, [], "")} | {"page": out["page"], "sort": out["sort"]}
