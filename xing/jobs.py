"""/xing/jobs/* — job search with the site's own filters (20 a page, 1,000
deep), a job by id / slug / link, a batch of jobs, similar jobs, the filter
catalog, a saved search by link and the SEO "related searches" boxes.

The search is jobSearchByQuery: keywords, a location text with a radius
(or a city id from /xing/autocomplete/locations), and `filter` ids —
employment type, career level, remote option, discipline (tabled in
refdata.py), industry (ids as /xing/jobs/details reports them), company
(ids as reported on jobs) and a salary band. `sincePeriod` is the posting
age, `sort` relevance or date. The site answers at most 20 rows a call
and nothing past offset 980; the result count is exact up to 1,000 and
"at least 1,000" beyond.

A logged-out answer can hide rows as UnauthorizedJob{GEO_FENCED} when the
egress is one the site fences (fetch.py); the transport retries those on
a residential exit, and whatever stays hidden is returned as
{id, is_visible: false, reason}.
"""
from xing.shared import text
from xing import fetch
from xing import parsers as P
from xing import refdata as R

PER_PAGE = R.SEARCH_LIMIT
MAX_PAGE = R.SEARCH_MAX_OFFSET // PER_PAGE + 1
SIMILAR_MAX = 20


def _geo_fenced(data):
    """Raise XingGeoFenced when the answer hid rows for our egress — the
    transport then retries on a residential exit. A row hidden for another
    reason (expired, private) is returned as is."""
    rows = (data.get("jobSearchByQuery") or {}).get("collection") or []
    reasons = {(r.get("jobDetail") or {}).get("reason") for r in rows
               if (r.get("jobDetail") or {}).get("__typename") == "UnauthorizedJob"}
    if "GEO_FENCED" in reasons:
        raise fetch.XingGeoFenced("the search hid geo-fenced jobs for this egress")


def build_query(keywords=None, location=None, radius=None, city=None, employment_type=None, career_level=None,
                remote=None, discipline=None, industry=None, company=None, salary_min=None, salary_max=None):
    """The JobSearchQueryInput for the public params."""
    query = {}
    if keywords:
        query["keywords"] = keywords
    loc = {}
    if city:
        loc["cityId"] = city
    elif location:
        loc["text"] = location
    if loc and radius is not None:
        loc["radius"] = radius
    if loc:
        query["location"] = loc
    filters = {}
    for key, table, values in (("employmentType", R.EMPLOYMENT_TYPES, employment_type),
                               ("careerLevel", R.CAREER_LEVELS, career_level),
                               ("remoteOption", R.REMOTE_OPTIONS, remote),
                               ("discipline", R.DISCIPLINES, discipline)):
        ids = R.ids_for(table, values)
        if ids:
            filters[key] = {"id": ids}
    if industry:
        filters["industry"] = {"id": list(industry)}
    if company:
        filters["company"] = {"id": list(company)}
    if salary_min is not None or salary_max is not None:
        filters["salary"] = {"min": salary_min or 0, "max": salary_max or 1_000_000}
    if filters:
        query["filter"] = filters
    return query


def _search(query, page, sort, posted_within, consumer=R.CONSUMER_SEARCH, label="job search"):
    variables = {"query": query, "consumer": consumer, "limit": PER_PAGE, "offset": (page - 1) * PER_PAGE,
                 "sort": R.SORTS.get(sort or "relevance", "relevance"), "returnAggregations": False}
    if posted_within:
        variables["sincePeriod"] = R.POSTED_WITHIN[posted_within]
    data = fetch.graphql("JobSearchByQuery", variables, label=label, check=_geo_fenced)
    out = P.search_results(data, page, PER_PAGE)
    out["search"]["sort"] = sort or "relevance"
    out["search"]["posted_within"] = posted_within
    return out


def search(keywords=None, location=None, radius=None, city=None, employment_type=None, career_level=None, remote=None,
           discipline=None, industry=None, company=None, salary_min=None, salary_max=None, posted_within=None,
           sort="relevance", page=1):
    """One page (20 jobs) of a job search with the site's filters."""
    query = build_query(keywords, location, radius, city, employment_type, career_level, remote, discipline, industry,
                        company, salary_min, salary_max)
    out = _search(query, page, sort, posted_within, label=f"job search {keywords!r} in {location or city!r}")
    out["search"]["requested"] = {k: v for k, v in {
        "keywords": keywords, "location": location, "radius_km": radius, "city": city, "employment_type": employment_type,
        "career_level": career_level, "remote": remote, "discipline": discipline, "industry": industry, "company": company,
        "salary_min": salary_min, "salary_max": salary_max}.items() if v not in (None, [], "")}
    return out


def by_link(link, page=None):
    """The jobs of any xing.com/jobs/search link (a saved search with the
    site's own filters), page by page."""
    params = dict(link)
    if page is not None:
        params["page"] = page
    return search(**params)


def _geo_check_job(data):
    job = data.get("job") or {}
    if job.get("__typename") == "UnauthorizedJob" and job.get("reason") == "GEO_FENCED":
        raise fetch.XingGeoFenced("job hidden for this egress")


def _details(job_id):
    data = fetch.graphql("GetJobDetails", {"slug": str(job_id)}, label=f"job {job_id}", check=_geo_check_job)
    out = P.job_details(data)
    if out is None:
        raise fetch.XingNotFound(f"XING has no job {job_id} (expired or removed)")
    return out


def details(job):
    """One job by id, slug or link: full description (text, HTML, the
    template sections of designed ads), salary (stated or XING's estimate),
    career level, discipline, industry, remote options, company card with
    kununu rating, apply link / email, screening criteria, dates."""
    return _details(job)


def batch(jobs):
    """Up to 10 jobs in parallel; expired ids are listed in not_found,
    other failures in errors."""
    results = fetch.run_parallel([lambda j=j: _details(j) for j in jobs])
    found, not_found, errors = [], [], []
    for job_id, (status, value) in zip(jobs, results):
        if status == "ok":
            found.append(value)
        elif isinstance(value, fetch.XingNotFound):
            not_found.append(int(job_id))
        else:
            errors.append({"id": int(job_id), "error": str(value)})
    if not found and errors and not not_found:
        raise fetch.XingUpstreamError("; ".join(e["error"] for e in errors))
    return {"jobs": found, "not_found": not_found, "errors": errors}


def _scrambled_id(job_id):
    """The posting's scrambled id ('155730561.9e044b'), which the
    similar-jobs API needs; read once from the job itself and memoised."""
    def lookup():
        data = fetch.graphql("GetJobDetails", {"slug": str(job_id)}, label=f"job {job_id}")
        raw = text((data.get("job") or {}).get("id"))
        if not raw:
            raise fetch.XingNotFound(f"XING has no job {job_id} (expired or removed)")
        return raw
    return fetch.memoized(("scrambled", str(job_id)), lookup)


def similar(job, limit=10):
    """Jobs XING recommends next to a job (its "similar jobs" rail)."""
    scrambled = _scrambled_id(job)

    def check(data):
        rows = ((data.get("viewer") or {}).get("similarJobs") or {}).get("collection") or []
        if any(((r.get("job") or {}).get("reason")) == "GEO_FENCED" for r in rows):
            raise fetch.XingGeoFenced("similar jobs hidden for this egress")
    data = fetch.graphql("GetSimilarJobs", {"jobId": scrambled, "limit": min(limit, SIMILAR_MAX),
                                            "consumer": R.CONSUMER_SIMILAR}, label=f"similar to job {job}", check=check)
    return {"job_id": int(job), "jobs": P.similar_jobs(data)[:limit]}


def filters():
    """The filter values /xing/jobs/search accepts (employment types,
    career levels, remote options, disciplines, posting age, sort) with
    XING's own ids and labels. Static — the ids are stable per entity."""
    def table(rows):
        return [{"value": public, "id": sid, "label": label} for public, (sid, label) in rows.items()]
    return {
        "employment_type": table(R.EMPLOYMENT_TYPES),
        "career_level": table(R.CAREER_LEVELS),
        "remote": table(R.REMOTE_OPTIONS),
        "discipline": table(R.DISCIPLINES),
        "posted_within": [{"value": k, "label": {"day": "Past 24 hours", "week": "Last week", "month": "Last month"}[k]}
                          for k in R.POSTED_WITHIN],
        "sort": [{"value": k} for k in R.SORTS],
        "industry": "ids as /xing/jobs/details reports in job.industry.value (e.g. 90100.a8b7b7); comma-separated",
        "company": "company ids as reported in job.company.id (e.g. 25948.0e87ae); comma-separated",
        "city": "a city id from /xing/autocomplete/locations (e.g. 2867714.724c7f); replaces `location`",
        "salary": "salary_min / salary_max in EUR per year",
        "pagination": {"items_per_page": PER_PAGE, "max_page": MAX_PAGE},
    }


def related(role, location=None):
    """XING's SEO link boxes for a job role (and a city): popular cities
    with job counts, related roles, employment-type pages, nearby roles,
    local skills."""
    data = fetch.graphql("GetJobDetailsLinkboxes", {"jobRole": role, "location": location},
                         label=f"related searches for {role!r}")
    out = P.linkboxes(data)
    return {"role": role, "location": location, **out}
