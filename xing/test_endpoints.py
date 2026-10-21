"""Live endpoint smoke tests: one call per /xing/* route against a running
service, with example values proven to return data (2026-10-19). The
listing tooling reads each route's FIRST call from this file's AST as its
working example, so the values stay literals.

Skipped unless XING_BASE points at a running service:

    SCRAPERS_PORT=6093 ONLY_SCRAPER=xing python run.py
    XING_BASE=http://127.0.0.1:6093 python -m pytest xing/test_endpoints.py -q
"""
import os

import pytest

BASE = os.environ.get("XING_BASE", "").rstrip("/")

pytestmark = pytest.mark.skipif(not BASE, reason="set XING_BASE to run live endpoint tests")


def call(path, **params):
    from curl_cffi import requests
    resp = requests.get(BASE + path, params=params, timeout=300)
    assert resp.status_code == 200, f"{path} {params} -> {resp.status_code} {resp.text[:300]}"
    body = resp.json()
    assert body, f"{path} returned an empty body"
    return body


def status(path, **params):
    from curl_cffi import requests
    return requests.get(BASE + path, params=params, timeout=300).status_code


def test_job_search():
    body = call("/xing/jobs/search", keywords="java", location="Berlin", radius=50)
    assert body["count"] >= 20 and len(body["jobs"]) == 20 and body["per_page"] == 20 and body["total_pages"] >= 2 and body["next"]
    job = next(j for j in body["jobs"] if j["is_visible"])
    assert job["id"] and job["title"] and job["link"].startswith("https://www.xing.com/jobs/") and job["company"]["name"]
    assert sum(1 for j in body["jobs"] if j["is_visible"]) >= 15
    page2 = call("/xing/jobs/search", keywords="java", location="Berlin", radius=50, page=2)
    assert page2["current_page"] == 2 and page2["jobs"][0]["id"] not in {j["id"] for j in body["jobs"]}
    body = call("/xing/jobs/search", keywords="software", location="München", employment_type="full_time", career_level="professional",
                remote="remote,hybrid", salary_min=60000, posted_within="month", sort="date")
    assert body["jobs"] and {r["value"] for r in body["search"]["filters"]["remote"]} == {"remote", "hybrid"}
    body = call("/xing/jobs/search", keywords="python", city="2867714.724c7f", discipline="it_software")
    assert body["jobs"] and body["search"]["location"]["city"]["name"]
    assert status("/xing/jobs/search") == 400
    assert status("/xing/jobs/search", keywords="java", employment_type="fulltime") == 400


def test_job_details():
    body = call("/xing/jobs/details", job="155730561")
    assert body["id"] == 155730561 and body["title"] and body["description"]["text"] and body["company"]["link"]
    assert body["salary"]["currency"] == "EUR" and body["application"]["link"]
    by_link = call("/xing/jobs/details", job="https://www.xing.com/jobs/berlin-java-full-stack-entwickler-all-genders-155730561")
    assert by_link["id"] == 155730561
    assert status("/xing/jobs/details", job="999999999") == 404
    assert status("/xing/jobs/details", job="https://www.linkedin.com/jobs/view/1") == 400


def test_job_batch():
    body = call("/xing/jobs/batch", jobs="155730561,156019027,999999999")
    assert {j["id"] for j in body["jobs"]} == {155730561, 156019027} and body["not_found"] == [999999999] and body["errors"] == []


def test_similar_jobs():
    body = call("/xing/jobs/similar", job="155730561", limit=5)
    assert body["job_id"] == 155730561 and 1 <= len(body["jobs"]) <= 5 and body["jobs"][0]["title"]


def test_job_filters():
    body = call("/xing/jobs/filters")
    assert {f["value"] for f in body["employment_type"]} >= {"full_time", "part_time"} and body["discipline"][0]["id"]
    assert body["pagination"]["max_page"] == 50


def test_jobs_by_link():
    body = call("/xing/jobs/by-link", link="https://www.xing.com/jobs/search?keywords=java&location=Berlin&remoteOption=FULL_REMOTE.050e26")
    assert body["jobs"] and body["search"]["filters"]["remote"][0]["value"] == "remote" and body["next"]
    assert status("/xing/jobs/by-link", link="https://www.xing.com/jobs/berlin-java-155730561") == 400


def test_related_searches():
    body = call("/xing/jobs/related", role="softwareentwickler", location="berlin")
    assert body["popular_locations"][0]["jobs_count"] > 0 and body["related_roles"]


def test_company_details():
    body = call("/xing/companies/details", company="sap")
    assert body["id"] and body["slug"] == "sap" and body["name"] == "SAP" and body["followers_count"] > 1000
    assert body["about"]["summary"] and body["locations"][0]["city"] == "Walldorf" and body["related_companies"]
    assert call("/xing/companies/details", company="https://www.xing.com/pages/accenture")["slug"] == "accenture"
    assert status("/xing/companies/details", company="no-such-company-xyz-123") == 404


def test_company_jobs():
    body = call("/xing/companies/jobs", company="accenture", keywords="consultant")
    assert body["count"] >= 20 and body["jobs"] and body["company"]["slug"] == "accenture" and body["next"]
    assert all(j["company"]["link"] == "https://www.xing.com/pages/accenture" for j in body["jobs"] if j["is_visible"])


def test_company_employees():
    body = call("/xing/companies/employees", company="accenture", limit=10)
    assert body["total_count"] > 1000 and len(body["employees"]) + body["hidden_count"] == 10
    assert body["employees"][0]["username"] and body["employees"][0]["headline"]


def test_company_news():
    body = call("/xing/companies/news", company="sap", limit=5)
    assert len(body["posts"]) == 5 and body["posts"][0]["text"] and body["posts"][0]["published_at"] and body["next_before"]
    older = call("/xing/companies/news", company="sap", limit=5, before=body["next_before"])
    assert older["posts"] and older["posts"][0]["published_at"] < body["posts"][-1]["published_at"]


def test_profile_details():
    body = call("/xing/profiles/details", profile="Harish_Govindarajalu2")
    assert body["name"] == "Harish Govindarajalu" and body["work_experience"] and body["education"] and body["skills"]
    assert call("/xing/profiles/details", profile="https://www.xing.com/profile/Harish_Govindarajalu2")["username"] == "Harish_Govindarajalu2"
    assert status("/xing/profiles/details", profile="No_Such_Person_XyZ999") == 404


def test_autocomplete():
    body = call("/xing/autocomplete/locations", query="Mün", countries="DE", limit=5)
    assert body["suggestions"][0]["name"] == "München" and body["suggestions"][0]["id"]
    body = call("/xing/autocomplete/roles", query="soft", limit=5)
    assert "Softwareentwickler" in body["suggestions"]


def test_directory():
    body = call("/xing/directory", letter="a", kind="job_role", limit=5)
    assert len(body["entries"]) == 5 and body["entries"][0]["jobs_count"] >= 0
    body = call("/xing/directory", letter="b", kind="company", limit=5)
    assert body["entries"][0]["link"].startswith("https://www.xing.com/jobs/c-")
    assert status("/xing/directory", letter="ab") == 400
