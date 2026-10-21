"""Cache TTL per /xing/* endpoint (cache.py, keyed on the validated params —
marshmallow fills the defaults, so an omitted param and its default share a
row).

Result lists churn hourly (new postings, expiries, refreshes); a single job
changes rarely once posted; company pages move daily at most; profiles
change rarely; suggestions and directories are stable."""
from datetime import timedelta

SEARCH_CACHE = timedelta(hours=1)
JOB_CACHE = timedelta(hours=6)
SIMILAR_CACHE = timedelta(hours=6)
RELATED_CACHE = timedelta(days=3)
COMPANY_CACHE = timedelta(days=1)
COMPANY_JOBS_CACHE = timedelta(hours=1)
EMPLOYEES_CACHE = timedelta(days=1)
NEWS_CACHE = timedelta(hours=12)
PROFILE_CACHE = timedelta(days=1)
AUTOCOMPLETE_CACHE = timedelta(days=7)
DIRECTORY_CACHE = timedelta(days=1)
