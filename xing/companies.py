"""/xing/companies/* — a company page by slug / link (header, about,
media, locations, size, industry, kununu rating, related companies), its
open jobs (the job search filtered by company id), the employees the page
shows to a visitor, and its news feed.

XING keys a company two ways: the entity page (slug or page id) and the
company record (a scrambled company id, e.g. 30276.2e5e9c). The page
query returns the company id, which the jobs filter, the employees and
the related-companies queries need; it is memoised per slug.
"""
from xing.shared import text
from xing import fetch
from xing import jobs as J
from xing import parsers as P
from xing import refdata as R


def _page(slug):
    data = fetch.graphql("EntityPage", {"id": slug}, label=f"company page {slug}")
    page = P.company_page(data)
    if page is None:
        raise fetch.XingNotFound(f"XING has no company page '{slug}'")
    if page.get("moved_to"):
        if page["moved_to"] and page["moved_to"] != slug:
            return _page(page["moved_to"])
        raise fetch.XingNotFound(f"XING company page '{slug}' has moved")
    return page


def _ids(slug):
    """slug -> {company_id, page_id, slug} (memoised: they never change)."""
    def lookup():
        page = _page(slug)
        return {"company_id": page.get("id"), "page_id": page.get("page_id"), "slug": page.get("slug") or slug}
    return fetch.memoized(("company_ids", slug), lookup)


def details(company):
    """One company by page slug or link: profile, about text and media,
    industry, size, employee and follower counts, phone, address and
    locations, kununu rating, logo / cover, related companies."""
    page = _page(company)
    extra = None
    if page.get("id"):
        try:
            extra = P.company_extra(fetch.graphql("CompanyExtra", {"id": page["id"]}, label=f"company {page['id']}"))
        except fetch.XingUpstreamError as e:
            print(f"xing: company record for {company} failed: {e}")
    return P.merge_company(page, extra)


def jobs(company, keywords=None, career_level=None, employment_type=None, remote=None, discipline=None,
         posted_within=None, sort="date", page=1):
    """One page (20) of a company's open jobs on XING, with the search filters."""
    ids = _ids(company)
    if not ids.get("company_id"):
        raise fetch.XingNotFound(f"XING page '{company}' is not a company page (no company record)")
    query = J.build_query(keywords=keywords, employment_type=employment_type, career_level=career_level, remote=remote,
                          discipline=discipline, company=[ids["company_id"]])
    out = J._search(query, page, sort, posted_within, consumer=R.CONSUMER_COMPANY_JOBS,
                    label=f"company {company} jobs")
    out["company"] = {"id": ids["company_id"], "slug": ids["slug"], "link": f"{R.BASE}/pages/{ids['slug']}"}
    return out


def employees(company, limit=20):
    """The employees XING shows a visitor on the company page (up to 100;
    the site hides the rest behind a login): name, headline, location,
    photo, profile link. hidden_count = rows the site withheld."""
    ids = _ids(company)
    if not ids.get("company_id"):
        raise fetch.XingNotFound(f"XING page '{company}' is not a company page (no company record)")
    data = fetch.graphql("Employees", {"id": ids["company_id"], "first": min(limit, R.EMPLOYEES_MAX),
                                       "query": {"consumer": R.CONSUMER_EMPLOYEES}}, label=f"company {company} employees")
    out = P.employees(data)
    if out is None:
        raise fetch.XingNotFound(f"XING has no company record for '{company}'")
    out["company"]["slug"] = ids["slug"]
    return out


def news(company, limit=20, before=None):
    """A company page's news feed (posts, shared links, images, videos,
    articles) newest first; `before` (ISO datetime) pages backwards."""
    ids = _ids(company)
    variables = {"id": ids["page_id"], "limit": limit}
    if before:
        variables["until"] = before
    data = fetch.graphql("NewsListItems", variables, label=f"company {company} news")
    posts = P.news(data)
    if posts is None:
        raise fetch.XingNotFound(f"XING page '{company}' has no news feed")
    return {"company": {"page_id": ids["page_id"], "slug": ids["slug"], "link": f"{R.BASE}/pages/{ids['slug']}"},
            "posts": posts, "next_before": posts[-1]["published_at"] if len(posts) >= limit and posts[-1].get("published_at") else None}
