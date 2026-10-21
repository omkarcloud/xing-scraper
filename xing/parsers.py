"""Raw xing-one GraphQL payloads -> clean API objects. Pure functions, no
network; every parser tolerates missing / null / wrong-typed fields and
never raises on a partial payload.

Value helpers (safe access, text, dates, html -> text) are imported from
xing/shared.py (a verbatim copy of the jobstreet/shared.py subset it uses).

Intentionally dropped everywhere: `__typename` (used only to branch),
trackingToken / globalId / surn: urns (tracking and internal ids),
localizationKey / localizationA11y (duplicates of the label), the search's
matchingFacts / nonMatchingFacts (they repeat employment type and salary),
userInteractions / viewer / permissions (login state), image `reference`
names, `isReachRefreshed` / `serviceOfferingGroup` / `contract.type` /
`publicationStatus` / `focusType` (XING-internal product flags), the SEO
page meta (title / description / canonical / qualityIndex), the hashed
suffix of job ids (the numeric posting id is the public one; company,
profile and city ids keep their suffix because the API needs it back).
"""
import re

from xing.shared import amount, as_dict, as_list, g, html_to_text, iso_date, iso_datetime, multiline, text, to_int
from xing import refdata as R

# ---- small shared pieces ---------------------------------------------------------------------------

_POSTING_ID_RE = re.compile(r"^(\d+)")


def posting_id(value):
    """'155730561.9e044b' -> 155730561 (int); None when absent."""
    value = text(value)
    if not value:
        return None
    match = _POSTING_ID_RE.match(value)
    return int(match.group(1)) if match else None


def _lower(value):
    value = text(value)
    return value.lower() if value else None


def _value_label(kind, item):
    """{id: 'FULL_TIME.ef2fe9', localizationValue: 'Full-time'} -> {value, label}.
    `value` is our public filter name when the id is tabled, else the raw id."""
    item = as_dict(item)
    sid = text(item.get("id"))
    label = text(item.get("localizationValue"))
    if not sid and not label:
        return None
    value = R.public_value(kind, sid) if sid else None
    return {"value": value or sid, "label": label}


def _remote_options(values):
    out = []
    for raw in as_list(values):
        raw = text(raw)
        if not raw:
            continue
        public = next((k for k, (sid, _l) in R.REMOTE_OPTIONS.items() if sid.split(".")[0] == raw.split(".")[0]), None)
        value = public or raw.lower()
        if value not in out:
            out.append(value)
    return out


def salary(item):
    """Salary {amount} / SalaryRange {minimum, maximum} / SalaryEstimate
    {minimum, maximum, median} -> {currency, min, max, median, is_estimate}."""
    item = as_dict(item)
    if not item:
        return None
    fixed = amount(item.get("amount"))
    low = amount(item.get("minimum")) if fixed is None else fixed
    high = amount(item.get("maximum")) if fixed is None else fixed
    median = amount(item.get("median"))
    if low is None and high is None and median is None:
        return None
    return {"currency": text(item.get("currency")), "min": low, "max": high, "median": median,
            "is_estimate": median is not None}


def _country(item):
    item = as_dict(item)
    return text(item.get("localizationValue")), text(item.get("countryCode"))


def location(item):
    item = as_dict(item)
    if not item:
        return None
    country, code = _country(item.get("country"))
    out = {"city": text(item.get("city")), "region": text(item.get("region")), "zip_code": text(item.get("zipCode")),
           "street": text(item.get("street")), "country": country, "country_code": code}
    if item.get("cityId") is not None:
        out["city_id"] = to_int(item.get("cityId"))
    return out if any(v for k, v in out.items() if k != "city_id") else None


def kununu(item):
    item = as_dict(item)
    if not item:
        return None
    rating = item.get("ratingAverage")
    out = {"rating": round(float(rating), 2) if isinstance(rating, (int, float)) and not isinstance(rating, bool) else None,
           "recommendation_rate": amount(item.get("recommendationRate")),
           "rating_count": to_int(item.get("ratingCount"))}
    if "companyProfileUrl" in item:
        out["link"] = text(item.get("companyProfileUrl"))
    return out if any(v is not None for v in out.values()) else None


def _logo(logos):
    logos = as_dict(logos)
    return text(logos.get("logo256px") or logos.get("logo128px") or logos.get("logo96px") or logos.get("x1"))


def company_card(info):
    """A job's companyInfo -> {id, name, size, industry, link, logo, kununu}."""
    info = as_dict(info)
    company = as_dict(info.get("company"))
    name = text(info.get("companyNameOverride")) or text(company.get("companyName"))
    if not name and not company:
        return None
    out = {"id": text(company.get("id")), "name": name, "size": text(company.get("companySize")),
           "industry": text(g(company, "industry", "localizationValue")),
           "link": text(g(company, "links", "public")), "logo": _logo(company.get("logos")),
           "kununu": kununu(company.get("kununuData"))}
    if "companySizeRange" in company or "employeesCount" in company or "address" in company:
        size = as_dict(company.get("companySizeRange"))
        out["size_range"] = {"min": to_int(size.get("min")), "max": to_int(size.get("max"))} if size else None
        out["employees_count"] = to_int(company.get("employeesCount"))
        out["address"] = location(company.get("address"))
    return out


def application(item):
    """UrlApplication / EmailApplication / JobXingApplication… -> {type, link, email}."""
    item = as_dict(item)
    if not item:
        return None
    kind = text(item.get("__typename")) or ""
    type_map = {"UrlApplication": "external_link", "EmailApplication": "email", "JobXingApplication": "xing",
                "JobXingCustomApplication": "xing_form", "MessageApplication": "message"}
    out = {"type": type_map.get(kind, _lower(kind.replace("Application", "")) or None),
           "link": text(item.get("applyUrl")), "email": text(item.get("applyEmail"))}
    settings = as_dict(item.get("applyServiceSettings"))
    if settings:
        out["allows_logged_out_applications"] = bool(settings.get("loggedoutApplicationsEnabled"))
    return out


def _text_list(value):
    """The AI summary's bullet fields: XING sends a list of strings (a lone
    string is tolerated) -> list of clean strings, None when empty."""
    if isinstance(value, list):
        out = [line for line in (multiline(v) for v in value) if line]
        return out or None
    line = multiline(value)
    return [line] if line else None


def summary(item):
    content = as_dict(as_dict(item).get("content"))
    out = {"introduction": multiline(content.get("introduction")),
           "responsibilities": _text_list(content.get("keyResponsibilities")),
           "qualifications": _text_list(content.get("qualifications"))}
    return out if any(out.values()) else None


# ---- jobs ---------------------------------------------------------------------------------------------

def hidden_job(item, reason=None):
    item = as_dict(item)
    return {"id": posting_id(item.get("id")), "is_visible": False,
            "reason": _lower(reason or item.get("reason")) or "unauthorized"}


def job_teaser(item):
    """A VisibleJob (search hit, similar job, company job) -> the job card."""
    item = as_dict(item)
    if not item or item.get("__typename") == "UnauthorizedJob":
        return hidden_job(item) if item else None
    jid = posting_id(item.get("id"))
    slug = text(item.get("slug"))
    link = text(item.get("url")) or (f"{R.BASE}/jobs/{slug}" if slug else None)
    locations = [loc for loc in (location(x) for x in as_list(item.get("locations"))) if loc]
    main = location(item.get("location"))
    if main and locations and not main.get("street") and not main.get("region"):
        main = {**locations[0], **{k: v for k, v in main.items() if v is not None}}
    return {
        "id": jid,
        "slug": slug,
        "link": link,
        "title": text(item.get("title")),
        "company": company_card(item.get("companyInfo")),
        "location": main or (locations[0] if locations else None),
        "locations": locations,
        "employment_type": _value_label("employment_type", item.get("employmentType")),
        "career_level": _value_label("career_level", item.get("careerLevel")),
        "discipline": _value_label("discipline", item.get("discipline")),
        "industry": _value_label("industry", item.get("industry")),
        "remote_options": _remote_options(item.get("remoteOptions")),
        "salary": salary(item.get("salary")),
        "summary": summary(item.get("summary")),
        "application": application(item.get("application")),
        "language": text(item.get("language")),
        "job_code": text(item.get("jobCode")),
        "is_paid_listing": bool(item.get("paid")),
        "is_top_job": bool(item.get("topJob")),
        "is_prioritized": bool(item.get("prioritized")),
        "redirects_to_external_site": bool(item.get("redirectsToThirdPartyUrl")),
        "posted_at": iso_datetime(item.get("activatedAt")),
        "refreshed_at": iso_datetime(item.get("refreshedAt")),
        "expires_at": iso_datetime(item.get("activeUntil")),
        "is_visible": True,
    }


def _highlight(item):
    item = as_dict(as_dict(item).get("highlight"))
    if not item:
        return None
    return {"type": _lower(item.get("type")), "label": text(g(item, "localization", "localizationValue"))}


def search_hit(item):
    """One jobSearchByQuery collection row -> job card (+ badge / snippet)."""
    item = as_dict(item)
    job = job_teaser(item.get("jobDetail"))
    if not job:
        return None
    if job.get("is_visible"):
        snippet = text(item.get("descriptionHighlight"))
        job["description_snippet"] = re.sub(r"\*\*", "", snippet) if snippet else None
        job["badge"] = _highlight(item.get("matchingHighlightsV2"))
    return job


def applied_filters(body):
    """searchQuery.body.filterCollection -> {employment_type: [...], …} as the API applied them."""
    out = {}
    for item in as_list(as_dict(body).get("filterCollection")):
        item = as_dict(item)
        if "min" in item or "max" in item:
            out["salary"] = {"min": amount(item.get("min")), "max": amount(item.get("max"))}
            continue
        sid = text(item.get("entityId"))
        for key, kind, label_path in (("employmentType", "employment_type", ("employmentType", "localizationValue")),
                                      ("careerLevel", "career_level", ("careerLevel", "localizationValue")),
                                      ("remoteOption", "remote", ("remoteOption", "localizationValue")),
                                      ("discipline", "discipline", ("discipline", "localizationValue")),
                                      ("industry", "industry", ("industry", "localizationValue")),
                                      ("country", "country", ("country", "localizationValue")),
                                      ("city", "city", ("city", "name")),
                                      ("company", "company", ("company", "companyName"))):
            if key in item:
                value = R.public_value(kind, sid) or sid
                out.setdefault(kind, []).append({"value": value, "label": text(g(item, *label_path))})
                break
    return out


def search_results(payload, page, limit=R.SEARCH_LIMIT):
    """jobSearchByQuery -> {search, pagination, jobs}."""
    data = as_dict(as_dict(payload).get("jobSearchByQuery"))
    body = as_dict(g(data, "searchQuery", "body"))
    bounded = as_dict(data.get("boundedTotal"))
    total = to_int(bounded.get("total"))
    is_exact = text(bounded.get("countType")) == "EXACT" if bounded else None
    jobs = [j for j in (search_hit(x) for x in as_list(data.get("collection"))) if j]
    loc = as_dict(body.get("location"))
    city = as_dict(loc.get("city"))
    total_pages = None
    if total is not None:
        total_pages = min(-(-total // limit), (R.SEARCH_MAX_OFFSET // limit) + 1)
    return {
        "search": {
            "keywords": text(body.get("keywords")),
            "location": {"text": text(loc.get("text")), "radius_km": to_int(loc.get("radius")),
                         "city": {"id": text(city.get("id")), "name": text(city.get("name"))} if city else None} if loc else None,
            "filters": applied_filters(body),
        },
        "pagination": {"page": page, "items_per_page": limit, "total_count": total, "total_pages": total_pages,
                       "is_total_exact": is_exact, "reachable_count": min(total, R.SEARCH_MAX_OFFSET + limit) if total else total},
        "jobs": jobs,
    }


def aggregations(payload):
    """The search's aggregations -> {employment_types: [{value, id, label, count}], …}
    (counts are -1 for a logged-out client and dropped)."""
    data = as_dict(as_dict(as_dict(payload).get("jobSearchByQuery")).get("aggregations"))
    out = {}
    for key, kind, public, label_path in (("employmentTypes", "employment_type", "employment_types", ("employmentType", "localizationValue")),
                                          ("careerLevels", "career_level", "career_levels", ("careerLevel", "localizationValue")),
                                          ("remoteOptions", "remote", "remote_options", ("remoteOption", "localizationValue")),
                                          ("disciplines", "discipline", "disciplines", ("discipline", "localizationValue")),
                                          ("industries", "industry", "industries", ("industry", "localizationValue")),
                                          ("countries", "country", "countries", ("country", "localizationValue")),
                                          ("cities", "city", "cities", ("city", "name"))):
        rows = []
        for item in as_list(data.get(key)):
            item = as_dict(item)
            sid = text(item.get("id"))
            if not sid:
                continue
            row = {"value": R.public_value(kind, sid) or sid, "id": sid, "label": text(g(item, *label_path))}
            count = to_int(item.get("count"))
            if count is not None and count >= 0:
                row["count"] = count
            rows.append(row)
        out[public] = rows
    return out


def _section(title, content):
    content = content if isinstance(content, str) else None
    if not content and not title:
        return None
    return {"title": text(title), "text": html_to_text(content), "html": content or None}


def description(item):
    """HtmlDescription / ExternalUrlDescription / TemplateData -> {text, html, sections, external_link, media}."""
    item = as_dict(item)
    if not item:
        return None
    kind = text(item.get("__typename")) or ""
    out = {"text": None, "html": None, "sections": [], "external_link": None}
    if kind == "HtmlDescription" or "content" in item:
        html = item.get("content") if isinstance(item.get("content"), str) else None
        out["html"], out["text"] = html or None, html_to_text(html)
    elif kind == "ExternalUrlDescription":
        html = item.get("htmlContent") if isinstance(item.get("htmlContent"), str) else None
        out["html"], out["text"] = html or None, html_to_text(html)
        out["external_link"] = text(item.get("url"))
    elif kind == "TemplateData":
        pairs = (("genericDescription", None), ("companyDescription", "company"), ("responsibility", "responsibilities"),
                 ("skills", "skills"), ("weOffer", "offer"), ("contactInfo", "contact"))
        for prefix, key in pairs:
            if key is None:
                section = _section(None, item.get(prefix))
            else:
                section = _section(item.get(prefix + "Title"), item.get(prefix + "Content"))
            if section and (section["text"] or section["title"]):
                section["kind"] = key or "description"
                out["sections"].append(section)
        out["html"] = "\n".join(s["html"] for s in out["sections"] if s["html"]) or None
        out["text"] = "\n\n".join(f"{s['title']}\n{s['text']}" if s["title"] and s["text"] else (s["text"] or s["title"] or "")
                                  for s in out["sections"]).strip() or None
        videos = as_dict(item.get("videoUrls"))
        social = {k: text(v) for k, v in as_dict(item.get("socialUrls")).items()}
        out["media"] = {"header_image": text(item.get("headerImage")), "footer_image": text(item.get("footerImage")),
                        "videos": {"youtube": text(videos.get("youtube")), "vimeo": text(videos.get("vimeo"))},
                        "social_links": {k: v for k, v in social.items() if v} or None}
    return out


def job_details(payload):
    """GetJobDetails -> the full job; None when the job does not exist;
    a hidden_job dict when the API hides it."""
    job = as_dict(payload).get("job")
    if not isinstance(job, dict) or not job:
        return None
    if job.get("__typename") == "UnauthorizedJob":
        return hidden_job(job)
    out = job_teaser(job)
    screening = as_dict(job.get("screenOutCriteria"))
    out.update({
        "description": description(job.get("description")),
        "keywords": [k for k in (text(x) for x in as_list(job.get("keywords"))) if k],
        "screening": {"requires_eu_work_eligibility": screening.get("euWorkEligibility") if isinstance(screening.get("euWorkEligibility"), bool) else None,
                      "requires_german": screening.get("languageSkillsGerman") if isinstance(screening.get("languageSkillsGerman"), bool) else None}
        if screening else None,
    })
    return out


def similar_jobs(payload):
    rows = as_list(g(as_dict(payload), "viewer", "similarJobs", "collection"))
    return [j for j in (job_teaser(as_dict(r).get("job")) for r in rows) if j]


# ---- companies ----------------------------------------------------------------------------------------

def _media_item(node):
    node = as_dict(node)
    media = as_dict(node.get("media"))
    kind = text(media.get("__typename")) or ""
    link = text(media.get("url") or media.get("externalLink") or media.get("videoReferenceV2"))
    if not link and not node.get("description"):
        return None
    return {"id": text(node.get("id")), "type": {"ScaledImage": "image", "EntityVideo": "video",
                                                  "EntityExternalVideo": "external_video"}.get(kind, _lower(kind) or None),
            "description": text(node.get("description")), "link": link,
            "external_link": text(media.get("externalLink")) if kind == "EntityExternalVideo" else None}


def _phone(item):
    item = as_dict(item)
    number = text(item.get("number"))
    if not number:
        return None
    code = to_int(item.get("countryCode"))
    return f"+{code} {number}" if code else number


def company_location(item):
    item = as_dict(item)
    if not item:
        return None
    country, code = _country(item.get("country"))
    coords = as_dict(item.get("coordinates"))
    return {"id": text(item.get("id")), "label": text(item.get("label")), "address": text(item.get("address")),
            "address_suffix": text(item.get("addressSuffix")), "zip_code": text(item.get("postcode")),
            "city": text(item.get("city")), "country": country, "country_code": code,
            "latitude": coords.get("latitude") if isinstance(coords.get("latitude"), (int, float)) else None,
            "longitude": coords.get("longitude") if isinstance(coords.get("longitude"), (int, float)) else None,
            "email": text(item.get("email")), "phone": _phone(item.get("phoneNumber")), "fax": _phone(item.get("faxNumber")),
            "website": text(item.get("websiteURL")), "is_headquarters": bool(item.get("highlighted"))}


def company_page(payload):
    """EntityPage + about + locations -> the company page; None when the
    page does not exist; {"moved_to": slug} when it moved."""
    data = as_dict(payload)
    page = as_dict(data.get("entityPageEX"))
    kind = text(page.get("__typename")) or ""
    if not page or kind == "EntityPageError":
        return None
    if kind == "EntityPageMoved":
        return {"moved_to": text(page.get("slug"))}
    header = as_dict(g(data, "headerModule", "content"))
    company = as_dict(header.get("company"))
    size = as_dict(company.get("companySizeRange"))
    about = as_dict(data.get("pagesAboutUs"))
    media = [m for m in (_media_item(as_dict(e).get("node")) for e in as_list(g(about, "media", "edges"))) if m]
    slug = text(page.get("slug"))
    sections = [s for s in (_lower(as_dict(m).get("type")) for m in as_list(g(page, "modules", "collection"))) if s]
    return {
        "id": text(g(page, "context", "companyId")),
        "page_id": text(page.get("id")),
        "slug": slug,
        "name": text(page.get("title")),
        "link": text(g(page, "links", "self")) or (f"{R.BASE}/pages/{slug}" if slug else None),
        "slogan": text(page.get("slogan")),
        "about": {"headline": text(about.get("headline")), "summary": multiline(about.get("summary"))}
        if about.get("headline") or about.get("summary") else None,
        "industry": _value_label("industry", company.get("industry")),
        "size_range": {"min": to_int(size.get("min")), "max": to_int(size.get("max"))} if size else None,
        "employees_count": to_int(company.get("employeesCount")),
        "followers_count": to_int(g(header, "followers", "total")),
        "logo": text(g(page, "logoImage", 0, "url")),
        "cover_image": text(g(page, "coverImage", 0, "url")),
        "media": media,
        "locations": [loc for loc in (company_location(x) for x in as_list(g(data, "entityPageLocations", "collection"))) if loc],
        "page_sections": sections,
        "is_published": text(page.get("publicationStatus")) == "PUBLISHED" if page.get("publicationStatus") else None,
    }


def company_extra(payload):
    """CompanyExtra (company by id) -> {size, phone, address, links, logo, kununu, related_companies}."""
    company = as_dict(as_dict(payload).get("company"))
    if not company:
        return None
    related = []
    for row in as_list(g(company, "relatedCompanies", "collection")):
        raw = as_dict(as_dict(row).get("company"))
        card = company_card({"company": {k: v for k, v in raw.items() if k != "address"}})
        if card:
            card["address"] = location(raw.get("address"))
            related.append(card)
    size = as_dict(company.get("companySizeRange"))
    return {
        "id": text(company.get("id")),
        "name": text(company.get("companyName")),
        "size": text(company.get("companySize")),
        "size_range": {"min": to_int(size.get("min")), "max": to_int(size.get("max"))} if size else None,
        "employees_count": to_int(company.get("employeesCount")),
        "followers_count": to_int(g(company, "followers", "total")),
        "phone": text(company.get("phone")),
        "industry": _value_label("industry", company.get("industry")),
        "address": location(company.get("address")),
        "link": text(g(company, "links", "public")),
        "logo": _logo(company.get("logos")),
        "kununu": kununu(company.get("kununuData")),
        "related_companies": related,
    }


def merge_company(page, extra):
    """The page (slug-keyed) + the company record (id-keyed) -> one object,
    identity first, then profile, stats, nested lists."""
    page = dict(page or {})
    extra = dict(extra or {})
    out = {
        "id": page.get("id") or extra.get("id"),
        "page_id": page.get("page_id"),
        "slug": page.get("slug"),
        "name": page.get("name") or extra.get("name"),
        "link": page.get("link") or extra.get("link"),
        "slogan": page.get("slogan"),
        "about": page.get("about"),
        "industry": page.get("industry") or extra.get("industry"),
        "size": extra.get("size"),
        "size_range": page.get("size_range") or extra.get("size_range"),
        "employees_count": page.get("employees_count") if page.get("employees_count") is not None else extra.get("employees_count"),
        "followers_count": page.get("followers_count") if page.get("followers_count") is not None else extra.get("followers_count"),
        "phone": extra.get("phone"),
        "address": extra.get("address"),
        "kununu": extra.get("kununu"),
        "logo": page.get("logo") or extra.get("logo"),
        "cover_image": page.get("cover_image"),
        "media": page.get("media") or [],
        "locations": page.get("locations") or [],
        "related_companies": extra.get("related_companies") or [],
        "page_sections": page.get("page_sections") or [],
        "is_published": page.get("is_published"),
    }
    return out


def _occupation(item):
    item = as_dict(item)
    out = {"category": _lower(item.get("category")), "headline": text(item.get("headline")),
           "subline": text(item.get("subline")), "summary": text(item.get("summary")),
           "link": text(g(item, "links", 0, "url"))}
    return out if any(v for k, v in out.items() if k != "category") else None


def _member(item):
    """XingId / profileDetails -> a member card."""
    item = as_dict(item)
    if not item:
        return None
    page_name = text(item.get("pageName"))
    occupations = [o for o in (_occupation(x) for x in as_list(item.get("occupations"))) if o]
    work = next((o for o in occupations if o["category"] == "work_experience"), occupations[0] if occupations else None)
    loc = as_dict(item.get("location"))
    country, code = _country(loc.get("country"))
    return {
        "id": text(item.get("id")),
        "username": page_name,
        "link": f"{R.BASE}/profile/{page_name}" if page_name else None,
        "name": text(item.get("displayName")),
        "first_name": text(item.get("firstName")),
        "last_name": text(item.get("lastName")),
        "academic_title": text(item.get("academicTitle")),
        "gender": _lower(item.get("gender")),
        "headline": (work or {}).get("subline"),
        "company": (work or {}).get("headline"),
        "status": text(g(item, "status", "localizationValue")),
        "location": {"city": text(loc.get("city")), "country": country, "country_code": code} if loc else None,
        "photo": text(g(item, "profileImage", 0, "url")),
        "membership": _lower(g(item, "userFlags", "displayFlag")),
        "occupations": occupations,
    }


def employees(payload):
    """Employees -> {company: {id, name, link}, total_count, employees: [...]}."""
    company = as_dict(as_dict(payload).get("company"))
    if not company:
        return None
    conn = as_dict(company.get("employees"))
    people = []
    hidden = 0
    for edge in as_list(conn.get("edges")):
        member = _member(g(edge, "node", "profileDetails"))
        if member:
            people.append(member)
        else:
            hidden += 1
    return {"company": {"id": text(company.get("id")), "name": text(company.get("companyName")),
                        "link": text(g(company, "links", "public"))},
            "total_count": to_int(conn.get("total")), "hidden_count": hidden, "employees": people}


def _feed_image(obj):
    for key in ("images",):
        url = text(g(obj, key, 0, "url"))
        if url:
            return url
    return text(obj.get("imageUrl")) or text(obj.get("coverImageUrl")) or text(g(obj, "image", "srcWidth1232"))


def news_post(item):
    item = as_dict(item)
    obj = as_dict(item.get("object"))
    kind = text(obj.get("__typename")) or ""
    types = {"EntityPageContentFeedPostingPost": "post", "EntityPageContentFeedCompanyArticlePost": "company_article",
             "EntityPageContentFeedArticlePost": "article", "EntityPageContentFeedArticlesArticlePost": "article"}
    attachment = as_dict(obj.get("attachment"))
    link_preview = None
    link = text(obj.get("permalink") or obj.get("visitUrl"))
    image = _feed_image(obj) or text(g(attachment, "images", 0, "url"))
    video = as_dict(obj.get("video"))
    video_link = text(g(video, "links", "iframeUrl")) or text(g(attachment, "videoV2", "ref"))
    preview = as_dict(attachment.get("link"))
    if preview:
        link_preview = {"link": text(preview.get("url")), "title": text(preview.get("title")),
                        "description": text(preview.get("description")), "image": text(preview.get("cachedImageUrl")),
                        "domain": text(preview.get("sourceDomain"))}
    meta = as_dict(item.get("metadata"))
    return {
        "id": text(item.get("globalId")),
        "type": types.get(kind, _lower(kind) or None),
        "title": text(obj.get("title")),
        "text": multiline(obj.get("comment")),
        "description": multiline(obj.get("description") or obj.get("summary")),
        "link": link,
        "image": image,
        "video": video_link,
        "link_preview": link_preview,
        "provider": text(obj.get("provider")),
        "likes_count": to_int(meta.get("likesCount")),
        "comments_count": to_int(meta.get("commentsCount")),
        "is_pinned": bool(item.get("isPinned")),
        "published_at": iso_datetime(item.get("publishedAt") or obj.get("createdAt")),
    }


def news(payload):
    feed = as_dict(payload).get("entityPageContentFeeds")
    if not isinstance(feed, dict):
        return None
    return [news_post(x) for x in as_list(feed.get("collection")) if isinstance(x, dict)]


# ---- profiles ----------------------------------------------------------------------------------------------

def _duration(label):
    """'**Current** 4 years and 7 months, since Apr 2022' -> '4 years and 7 months'."""
    label = text(label)
    if not label:
        return None
    label = label.replace("**", "")
    label = re.sub(r"^(Current|Aktuell)\s*", "", label)
    return label.split(",")[0].strip() or None


def work_experience(item):
    item = as_dict(item)
    company = as_dict(item.get("company"))
    return {"title": text(item.get("jobTitle")),
            "company": {"name": text(item.get("companyName")), "link": text(g(company, "links", "public")),
                        "logo": text(g(company, "logos", "logo256px"))},
            "start_date": text(item.get("beginDate")) or None, "end_date": text(item.get("endDate")) or None,
            "is_current": bool(item.get("currentCompany")), "duration": _duration(item.get("localizedTimeString")),
            "description": multiline(item.get("companyNotes"))}


def education(item):
    item = as_dict(item)
    return {"school": text(item.get("schoolName")), "subject": text(item.get("subject")), "degree": text(item.get("degree")),
            "start_date": text(item.get("beginDate")) or None, "end_date": text(item.get("endDate")) or None,
            "duration": _duration(item.get("localizedTimeString")), "description": multiline(item.get("schoolNotes")),
            "is_primary": bool(item.get("primarySchool"))}


_LANGUAGE_LEVELS = {1: "basic", 2: "good", 3: "fluent", 4: "native"}


def similar_profile(item):
    item = as_dict(item)
    page_name = text(item.get("pageName"))
    if not page_name and not item.get("id"):
        return None
    first, last = text(item.get("firstName")), text(item.get("lastName"))
    return {"id": text(item.get("id")), "username": page_name,
            "link": f"{R.BASE}/profile/{page_name}" if page_name else None,
            "name": " ".join(p for p in (first, last) if p) or None, "academic_title": text(item.get("academicTitle")),
            "headline": text(item.get("occupationTitle")) if text(item.get("occupationTitle")) != "---" else None,
            "city": text(item.get("businessCity")), "country_code": (text(item.get("businessCountry")) or "").upper() or None,
            "photo": text(item.get("photoUrl")) if item.get("hasPhoto") else None}


def profile(payload):
    """profileLoProfile -> the public profile; None when the profile does not exist."""
    data = as_dict(payload)
    xing_id = as_dict(data.get("xingIdWithError"))
    if not xing_id or xing_id.get("__typename") == "ResponseError":
        return None
    member = _member(xing_id)
    structured = as_dict(data.get("profileStructuredData"))
    meta = as_dict(data.get("profilePageMeta"))
    experience = [work_experience(x) for x in as_list(g(data, "profileWorkExperience", "collection")) if isinstance(x, dict)]
    languages = []
    for item in as_list(g(data, "profileLanguageSkills", "collection")):
        item = as_dict(item)
        level = to_int(item.get("skillLevelId"))
        languages.append({"code": text(item.get("language")), "name": text(item.get("displayLanguage")),
                          "level": _LANGUAGE_LEVELS.get(level), "level_id": level})
    skills = as_dict(data.get("profileSkills"))
    return {
        **{k: member[k] for k in ("id", "username", "link", "name", "first_name", "last_name", "academic_title", "gender")},
        "headline": text(structured.get("jobTitle")) or member["headline"],
        "company": member["company"],
        "status": member["status"],
        "location": member["location"] or ({"city": text(g(structured, "workLocation", "address", "addressLocality")),
                                            "country": None,
                                            "country_code": (text(g(structured, "workLocation", "address", "addressCountry")) or "").upper() or None}
                                           if g(structured, "workLocation", "address") else None),
        "photo": member["photo"],
        "header_image": None if xing_id.get("hasDefaultHeaderImage") else text(g(xing_id, "headerImage", 0, "url")),
        "membership": member["membership"],
        "occupations": member["occupations"],
        "work_experience": experience,
        "education": [education(x) for x in as_list(g(data, "profileEducation", "education")) if isinstance(x, dict)],
        "languages": languages,
        "skills": [s for s in (text(x) for x in as_list(skills.get("skills"))) if s],
        "top_skills": [s for s in (text(x) for x in as_list(skills.get("topSkills"))) if s],
        "similar_profiles": [p for p in (similar_profile(x) for x in as_list(g(data, "similarProfiles", "collection"))) if p],
        "is_indexable": bool(meta.get("indexable")) if "indexable" in meta else None,
        "profile_completeness": round(float(meta["qualityIndex"]), 1) if isinstance(meta.get("qualityIndex"), (int, float)) else None,
    }


# ---- lookups -----------------------------------------------------------------------------------------------

def location_suggestions(payload):
    rows = as_list(g(as_dict(payload), "autocompletionLocationsCity", "collection"))
    out = []
    for item in rows:
        item = as_dict(item)
        name = text(item.get("name"))
        if not name:
            continue
        out.append({"id": text(item.get("cityIdWithScrambling")), "name": name, "district": text(item.get("adminArea3")),
                    "region": text(item.get("adminArea")), "country": text(item.get("formattedCountry"))})
    return out


def role_suggestions(payload):
    rows = as_list(g(as_dict(payload), "autocompletionProfileJobRole", "collection"))
    return [s for s in (text(as_dict(r).get("suggestion")) for r in rows) if s]


def directory(payload):
    rows = as_list(g(as_dict(payload), "masterDirectoryEntryByLetter", "collection"))
    out = []
    for item in rows:
        item = as_dict(item)
        name = text(item.get("displayName"))
        if not name:
            continue
        out.append({"name": name, "link": text(item.get("url")), "jobs_count": to_int(item.get("jobCount"))})
    return out


def _linkbox(entries):
    out = []
    for item in as_list(entries):
        item = as_dict(item)
        name = text(item.get("name"))
        if name:
            out.append({"name": name, "link": text(item.get("url")), "jobs_count": to_int(item.get("jobCount"))})
    return out


def linkboxes(payload):
    """GetJobDetailsLinkboxes -> {popular_locations, related_roles, employment_types, nearby_roles, local_related_roles, local_skills}."""
    data = as_dict(payload)
    boxes = {}
    for root in ("jobRoleLinkboxes", "localJobRoleLinkboxes"):
        for box in as_list(g(data, root, "collection")):
            box = as_dict(box)
            kind = _lower(box.get("kind"))
            if kind:
                boxes[kind] = _linkbox(box.get("entries"))
    return {
        "popular_locations": boxes.get("popular_location", []),
        "related_roles": boxes.get("related_job_roles", []),
        "employment_types": boxes.get("job_role_employment_type", []),
        "other_roles": boxes.get("job_role_randomized", []),
        "nearby_roles": boxes.get("nearby_job_role", []),
        "local_related_roles": boxes.get("local_job_role_related_job_roles", []),
        "local_skills": boxes.get("local_skill", []),
    }
