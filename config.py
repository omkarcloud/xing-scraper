"""Configuration for the Xing Scraper. Everything can be set with an
environment variable; the defaults work out of the box.

    PORT        port the API listens on (default 8000)
    XING_PROXY  proxy URL for every request, e.g. http://user:pass@host:port
                (default: none — direct). XING shows every job to visitors from
                Germany, Austria, Switzerland and the US. From some other
                countries it hides most jobs (the API then returns them as
                {"is_visible": false, "reason": "geo_fenced"}); if you see that,
                set a proxy in one of those countries.

Everything else below is a plain constant with a working default — edit it
here if you need to.
"""
import os

PORT = int(os.environ.get("PORT", "8000"))

# Retry policy for transport errors and blocks (every request).
MAX_RETRIES = 3
RETRY_BACKOFF = 2          # seconds, multiplied by the attempt number

XING_MAX_ATTEMPTS = MAX_RETRIES          # tries per call before giving up
XING_GEO_FENCE_HOLD_SECONDS = 900        # after a geo-fenced answer, start every call on the proxy for this long
XING_WORKERS = 4                         # parallel upstream calls inside one request (jobs/batch, company page)

XING_PROXY = os.environ.get("XING_PROXY") or None


def xing_proxy(fallback=False):
    """The proxy a request uses (None = direct)."""
    return os.environ.get("XING_PROXY") or None
