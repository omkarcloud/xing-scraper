"""/xing/autocomplete/* and /xing/directory — the search box suggestions
(cities with the ids the job search takes, job-role titles) and the
alphabetical job-role / company / city directory with job counts.
"""
from xing import fetch
from xing import parsers as P
from xing import refdata as R


def locations(query, language="en", countries=None, limit=10):
    """City suggestions for a partial name: id (usable as `city` in
    /xing/jobs/search), name, district, region, country. `countries`
    (ISO codes) narrows the ranking to those countries."""
    variables = {"consumer": R.CONSUMER_SUGGEST, "text": query, "language": language, "limit": limit}
    if countries:
        variables["countries"] = [c.upper() for c in countries]
    data = fetch.graphql("GetLocationSuggestions", variables, label=f"location suggestions {query!r}")
    return {"query": query, "countries": [c.upper() for c in countries] if countries else None,
            "suggestions": P.location_suggestions(data)}


def roles(query, limit=10):
    """Job-title suggestions for a partial title."""
    data = fetch.graphql("GetJobRoleSuggestions", {"consumer": R.CONSUMER_SUGGEST, "text": query, "limit": limit},
                         label=f"role suggestions {query!r}")
    return {"query": query, "suggestions": P.role_suggestions(data)}


def directory(letter, kind="job_role", limit=100):
    """The site's A-Z directory: job roles (with live job counts),
    companies or cities starting with a letter, each with its listing link."""
    data = fetch.graphql("MasterDirectoryEntryByLetter", {"letter": letter, "limit": limit, "type": R.DIRECTORY_TYPES[kind]},
                         label=f"directory {kind} {letter!r}")
    return {"letter": letter, "type": kind, "entries": P.directory(data)}
