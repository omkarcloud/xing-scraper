"""Parser tests on saved xing-one answers (xing/fixtures/*.json, captured
2026-10-19 from this Mac through the package's own transport — each file
holds {operationName, variables, data, errors}) and on the input
resolvers and schemas. No network.

    /usr/local/bin/python3.12 -m pytest xing/test_parsers.py -q
"""
import json
import os

import pytest

from schema_fields import load_query
from xing import parsers as P
from xing import refs, schemas
from xing.jobs import build_query

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def data(name):
    with open(os.path.join(FIXTURES, name + ".json"), encoding="utf-8") as f:
        return json.load(f)["data"]


# ---- jobs --------------------------------------------------------------------------------------------

def test_search_results():
    out = P.search_results(data("JobSearchByQuery"), page=1)
    assert out["search"]["keywords"] == "java" and out["search"]["location"]["text"] == "Berlin"
    assert out["search"]["location"]["radius_km"] == 50
    pagination = out["pagination"]
    assert pagination["items_per_page"] == 20 and pagination["total_count"] >= 20 and pagination["total_pages"] >= 2
    assert pagination["is_total_exact"] is True
    assert len(out["jobs"]) == 20
    job = next(j for j in out["jobs"] if j["is_visible"])
    assert isinstance(job["id"], int) and job["slug"] and job["link"].startswith("https://www.xing.com/jobs/")
    assert job["title"] and job["company"]["name"] and job["location"]["city"] == "Berlin"
    assert job["employment_type"]["value"] in ("full_time", "part_time", "self_employed", "student", "seasonal", "temporary", "volunteer")
    assert job["salary"] is None or set(job["salary"]) == {"currency", "min", "max", "median", "is_estimate"}
    assert job["posted_at"] and job["expires_at"] and job["posted_at"].endswith("Z")
    assert "badge" in job and "description_snippet" in job
    assert "__typename" not in json.dumps(out) and "trackingToken" not in json.dumps(out)


def test_summary_bullets_are_lists():
    # XING sends keyResponsibilities / qualifications as lists; they must stay
    # JSON arrays of clean strings, never a stringified Python list
    jobs = [j for name in ("JobSearchByQuery", "JobSearchByQuery_1", "JobSearchByQuery_2")
            for j in P.search_results(data(name), page=1)["jobs"]]
    summaries = [j["summary"] for j in jobs if j.get("summary")]
    assert summaries
    for s in summaries:
        for key in ("responsibilities", "qualifications"):
            assert s[key] is None or (isinstance(s[key], list) and all(isinstance(x, str) and x for x in s[key]))
            assert not (s[key] and s[key][0].startswith("['"))
    assert P.summary({"content": {"keyResponsibilities": ["a", " ", None]}}) == {
        "introduction": None, "responsibilities": ["a"], "qualifications": None}


def test_search_filters_echo():
    out = P.search_results(data("JobSearchByQuery_1"), page=2)
    filters = out["search"]["filters"]
    assert filters["employment_type"] == [{"value": "full_time", "label": "Full-time"}]
    assert filters["career_level"][0]["value"] == "professional"
    assert {r["value"] for r in filters["remote"]} == {"remote", "hybrid"}
    assert filters["salary"]["min"] == 60000
    assert out["pagination"]["page"] == 2


def test_search_by_city_id():
    out = P.search_results(data("JobSearchByQuery_2"), page=1)
    assert out["search"]["location"]["city"] == {"id": "2867714.724c7f", "name": "Munich"}
    assert out["search"]["filters"]["discipline"][0]["value"] == "it_software"


def test_hidden_job():
    payload = {"jobSearchByQuery": {"collection": [{"position": 0, "jobDetail": {"__typename": "UnauthorizedJob", "id": "1234567.abcdef", "reason": "GEO_FENCED"}}]}}
    out = P.search_results(payload, page=1)
    assert out["jobs"] == [{"id": 1234567, "is_visible": False, "reason": "geo_fenced"}]
    assert out["pagination"]["total_count"] is None


def test_job_details():
    job = P.job_details(data("GetJobDetails"))
    assert job["id"] == 155730561 and job["is_visible"] is True
    assert job["title"].startswith("Java Full Stack")
    assert job["company"]["name"] and job["company"]["link"] == "https://www.xing.com/pages/accenture"
    assert job["company"]["size_range"]["min"] == 10001 and job["company"]["address"]["city"]
    assert job["career_level"] == {"value": "professional", "label": "Professional/Experienced"}
    assert job["discipline"]["value"] == "it_software" and job["industry"]["label"] == "Consulting"
    assert job["remote_options"] == ["hybrid"]
    assert job["salary"]["is_estimate"] is True and job["salary"]["median"] == 68000
    assert job["application"]["type"] == "external_link" and job["application"]["link"].startswith("https://")
    assert job["description"]["text"].startswith("Du bist Softwareentwickler") and job["description"]["html"].startswith("<DIV>")
    assert "softwareentwickler" in job["keywords"]
    assert job["language"] == "de" and job["expires_at"] == "2026-12-25T00:55:19Z"


def test_job_details_missing_and_hidden():
    assert P.job_details({"job": None}) is None
    assert P.job_details({}) is None
    hidden = P.job_details({"job": {"__typename": "UnauthorizedJob", "id": "157876789.13a671", "reason": "GEO_FENCED"}})
    assert hidden == {"id": 157876789, "is_visible": False, "reason": "geo_fenced"}


def test_description_template():
    out = P.description({"__typename": "TemplateData", "genericDescription": "<p>Intro</p>", "responsibilityTitle": "Tasks",
                         "responsibilityContent": "<ul><li>Code</li><li>Test</li></ul>", "skillsTitle": None, "skillsContent": None,
                         "headerImage": "https://x/y.png", "videoUrls": {"youtube": None, "vimeo": None}, "socialUrls": {"website": "https://acme.de", "kununu": None}})
    assert [s["kind"] for s in out["sections"]] == ["description", "responsibilities"]
    assert out["sections"][1]["text"] == "- Code\n- Test"
    assert out["text"] == "Intro\n\nTasks\n- Code\n- Test"
    assert out["media"]["header_image"] == "https://x/y.png" and out["media"]["social_links"] == {"website": "https://acme.de"}
    assert P.description(None) is None


def test_similar_jobs():
    jobs = P.similar_jobs(data("GetSimilarJobs"))
    assert 1 <= len(jobs) <= 5 and all(j["id"] and j["title"] for j in jobs if j["is_visible"])


def test_salary_shapes():
    assert P.salary({"currency": "EUR", "amount": 50000}) == {"currency": "EUR", "min": 50000, "max": 50000, "median": None, "is_estimate": False}
    assert P.salary({"currency": "EUR", "minimum": 40000, "maximum": 60000}) == {"currency": "EUR", "min": 40000, "max": 60000, "median": None, "is_estimate": False}
    assert P.salary({"currency": "EUR", "minimum": 40000, "maximum": 60000, "median": 50000})["is_estimate"] is True
    assert P.salary({}) is None and P.salary({"currency": "EUR"}) is None


def test_linkboxes():
    out = P.linkboxes(data("GetJobDetailsLinkboxes"))
    assert out["popular_locations"][0]["jobs_count"] > 0 and out["popular_locations"][0]["link"].startswith("https://www.xing.com/jobs/")
    assert out["related_roles"] and out["nearby_roles"]


# ---- companies ------------------------------------------------------------------------------------------

def test_company_page_and_merge():
    page = P.company_page(data("EntityPage"))
    assert page["id"] == "30276.2e5e9c" and page["page_id"] == "210.d5ee28" and page["slug"] == "sap" and page["name"] == "SAP"
    assert page["link"] == "https://www.xing.com/pages/sap" and page["followers_count"] > 1000
    assert page["about"]["summary"].startswith("SAP ist") and page["industry"]["label"] == "Software"
    assert page["locations"][0]["city"] == "Walldorf" and page["locations"][0]["phone"].startswith("+49")
    assert page["locations"][0]["latitude"] and page["locations"][0]["is_headquarters"] is True
    assert "news" in page["page_sections"] and page["is_published"] is True
    extra = P.company_extra(data("CompanyExtra"))
    assert extra["size"].startswith("10,001") and extra["address"]["city"] == "Walldorf" and extra["related_companies"]
    merged = P.merge_company(page, extra)
    assert list(merged)[:5] == ["id", "page_id", "slug", "name", "link"]
    assert merged["size"] == extra["size"] and merged["related_companies"][0]["name"] and merged["locations"]
    assert "size_range" not in merged["related_companies"][0] and merged["related_companies"][0]["address"]["city"]


def test_company_page_missing():
    assert P.company_page(data("EntityPage_4")) is None
    assert P.company_page({"entityPageEX": {"__typename": "EntityPageMoved", "slug": "new-slug"}}) == {"moved_to": "new-slug"}
    assert P.company_page({}) is None


def test_employees():
    out = P.employees(data("Employees"))
    assert out["company"]["name"] == "Accenture" and out["total_count"] > 1000
    assert len(out["employees"]) + out["hidden_count"] == 10
    person = out["employees"][0]
    assert person["username"] and person["link"] == f"https://www.xing.com/profile/{person['username']}"
    assert person["headline"] and person["company"] and person["membership"] in ("basic", "premium", "moderator", None)
    assert person["gender"] in ("female", "male", None)
    assert P.employees({"company": None}) is None


def test_news():
    posts = P.news(data("NewsListItems"))
    assert len(posts) == 5 and posts[0]["type"] == "post" and posts[0]["text"] and posts[0]["published_at"].endswith("Z")
    assert posts[0]["likes_count"] >= 0 and posts[0]["image"].startswith("https://")
    assert P.news({"entityPageContentFeeds": None}) is None


def test_news_post_link_share():
    post = P.news_post({"globalId": "g1", "publishedAt": "2026-01-02T03:04:05Z", "metadata": {"likesCount": 1},
                        "object": {"__typename": "EntityPageContentFeedPostingPost", "comment": "Look", "attachment": {
                            "__typename": "PostingsLinkAttachment", "link": {"url": "https://a.de/x", "title": "T", "description": "D", "cachedImageUrl": "https://i", "sourceDomain": "a.de"}}}})
    assert post["link_preview"] == {"link": "https://a.de/x", "title": "T", "description": "D", "image": "https://i", "domain": "a.de"}
    assert post["type"] == "post" and post["likes_count"] == 1 and post["comments_count"] is None


# ---- profiles ------------------------------------------------------------------------------------------

def test_profile():
    out = P.profile(data("profileLoProfile"))
    assert out["username"] == "Harish_Govindarajalu2" and out["name"] == "Harish Govindarajalu" and out["gender"] == "male"
    assert out["headline"] == "Strategic Insights Manager" and out["company"] == "Prodapt Solutions"
    assert out["location"] == {"city": "Chennai", "country": "India", "country_code": "IN"}
    assert out["work_experience"][0]["is_current"] is True and out["work_experience"][0]["start_date"] == "2022-04"
    assert out["work_experience"][0]["duration"].endswith("months") and out["work_experience"][1]["end_date"]
    assert out["education"][0]["school"] == "Audencia" and out["education"][0]["degree"] == "Masters"
    assert {l["code"]: l["level"] for l in out["languages"]}["en"] == "native"
    assert "Business Analysis" in out["skills"] and len(out["similar_profiles"]) == 20
    assert out["similar_profiles"][0]["link"].startswith("https://www.xing.com/profile/")
    assert out["profile_completeness"] > 0 and out["is_indexable"] is True


def test_profile_missing():
    assert P.profile(data("profileLoProfile_1")) is None
    assert P.profile({}) is None


# ---- lookups ---------------------------------------------------------------------------------------------

def test_suggestions_and_directory():
    cities = P.location_suggestions(data("GetLocationSuggestions"))
    assert any(c["name"] == "München" and c["id"] == "2867714.724c7f" and c["country"] == "Germany" for c in cities)
    assert P.role_suggestions(data("GetJobRoleSuggestions")) == ["Software Developer", "Software Architect", "Software-Entwickler", "Softwarearchitekt", "Softwareentwickler"]
    roles = P.directory(data("MasterDirectoryEntryByLetter"))
    assert roles[0]["name"] and roles[0]["link"].startswith("https://www.xing.com/jobs/t-") and roles[0]["jobs_count"] >= 0
    companies = P.directory(data("MasterDirectoryEntryByLetter_1"))
    assert companies[0]["link"].startswith("https://www.xing.com/jobs/c-") and companies[0]["jobs_count"] is None


# ---- resolvers / schemas --------------------------------------------------------------------------------------

def test_resolve_job():
    for value in ("155730561", "155730561.9e044b", "berlin-java-full-stack-entwickler-155730561",
                  "https://www.xing.com/jobs/berlin-java-full-stack-entwickler-155730561", "xing.com/jobs/155730561",
                  "https://login.xing.com/?dest_url=https%3A%2F%2Fwww.xing.com%2Fjobs%2Fberlin-java-155730561"):
        assert refs.resolve_job(value) == "155730561", value
    for bad in ("", "abc", "https://www.linkedin.com/jobs/view/1", "https://www.xing.com/pages/sap", "1234"):
        with pytest.raises(ValueError):
            refs.resolve_job(bad)
    assert refs.resolve_jobs("155730561, https://www.xing.com/jobs/x-156019027,155730561") == ["155730561", "156019027"]
    with pytest.raises(ValueError):
        refs.resolve_jobs(",".join(str(100000000 + i) for i in range(11)))


def test_resolve_company_and_profile():
    for value in ("sap", "SAP", "https://www.xing.com/pages/sap", "https://www.xing.com/pages/sap/jobs", "https://www.xing.com/jobs/c-sap"):
        assert refs.resolve_company(value) == "sap", value
    for bad in ("", "sap gmbh", "https://www.xing.com/profile/Someone", "https://linkedin.com/company/sap"):
        with pytest.raises(ValueError):
            refs.resolve_company(bad)
    for value in ("Harish_Govindarajalu2", "https://www.xing.com/profile/Harish_Govindarajalu2", "https://www.xing.com/profile/Harish_Govindarajalu2/cv"):
        assert refs.resolve_profile(value) == "Harish_Govindarajalu2", value
    with pytest.raises(ValueError):
        refs.resolve_profile("https://www.xing.com/pages/sap")


def test_resolve_search_link():
    out = refs.resolve_search_link("https://www.xing.com/jobs/search?keywords=java&location=Berlin&employmentType=FULL_TIME.ef2fe9,PART_TIME.58889d"
                                   "&careerLevel=3.2ebf16&remoteOption=FULL_REMOTE.050e26&sincePeriod=last_week&sort=date&page=2&salary=50000-90000&radius=50")
    assert out == {"keywords": "java", "location": "Berlin", "radius": 50, "page": 2, "sort": "date", "posted_within": "week",
                   "employment_type": ["full_time", "part_time"], "career_level": ["professional"], "remote": ["remote"],
                   "salary_min": 50000, "salary_max": 90000}
    with pytest.raises(ValueError):
        refs.resolve_search_link("https://www.xing.com/jobs/berlin-java-155730561")
    with pytest.raises(ValueError):
        refs.resolve_search_link("java")


def test_build_query():
    query = build_query(keywords="java", location="Berlin", radius=30, employment_type=["full_time"], remote=["remote", "hybrid"],
                        industry=["90100.a8b7b7"], salary_min=60000)
    assert query == {"keywords": "java", "location": {"text": "Berlin", "radius": 30},
                     "filter": {"employmentType": {"id": ["FULL_TIME.ef2fe9"]}, "remoteOption": {"id": ["FULL_REMOTE.050e26", "PARTLY_REMOTE.ca71ca"]},
                                "industry": {"id": ["90100.a8b7b7"]}, "salary": {"min": 60000, "max": 1000000}}}
    assert build_query(city="2867714.724c7f", location="ignored")["location"] == {"cityId": "2867714.724c7f"}


def test_schemas():
    ok, err = load_query(schemas.JobSearchSchema, {"keywords": "java", "employment_type": "full_time,part_time", "page": "3", "remote": "Remote"})
    assert err is None and ok["employment_type"] == ["full_time", "part_time"] and ok["page"] == 3 and ok["remote"] == ["remote"]
    assert load_query(schemas.JobSearchSchema, {})[1]
    assert load_query(schemas.JobSearchSchema, {"keywords": "java", "employment_type": "fulltime"})[1]
    assert load_query(schemas.JobSearchSchema, {"keywords": "java", "page": "51"})[1]
    assert load_query(schemas.JobSearchSchema, {"keywords": "java", "industry": "software"})[1]
    assert load_query(schemas.JobSearchSchema, {"keywords": "java", "salary_min": "90000", "salary_max": "50000"})[1]
    ok, err = load_query(schemas.JobSchema, {"job": "https://www.xing.com/jobs/berlin-java-155730561"})
    assert ok == {"job": "155730561"}
    assert load_query(schemas.JobSchema, {"job": "155730561", "url": "x"})[1]       # unknown param -> 400
    ok, err = load_query(schemas.DirectorySchema, {"letter": "Ä", "kind": "location"})
    assert ok == {"letter": "ä", "kind": "location", "limit": 100}
    assert load_query(schemas.DirectorySchema, {"letter": "ab"})[1]
    ok, err = load_query(schemas.LocationSuggestSchema, {"query": "Mün", "countries": "de,AT"})
    assert ok["countries"] == ["DE", "AT"]
    assert load_query(schemas.NewsSchema, {"company": "sap", "before": "yesterday"})[1]


# ---- egress ---------------------------------------------------------------------------------------

def test_never_direct_without_opt_in(monkeypatch):
    # XING is never contacted from the server's own IP: no proxy -> the call fails
    import config
    from xing import fetch
    monkeypatch.setattr(config, "xing_proxy", lambda fallback=False: None)
    monkeypatch.delattr(config, "XING_ALLOW_DIRECT", raising=False)
    with pytest.raises(fetch.XingUpstreamError):
        fetch._proxy()
    monkeypatch.setattr(config, "XING_ALLOW_DIRECT", True, raising=False)   # the open-source kit
    assert fetch._proxy() is None
    monkeypatch.setattr(config, "xing_proxy", lambda fallback=False: "http://u:p@exit:1")
    assert fetch._proxy() == "http://u:p@exit:1"
