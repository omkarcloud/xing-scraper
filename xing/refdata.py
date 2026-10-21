"""XING reference tables: the filter ids the job search accepts (captured
2026-10-19 from the search page's aggregations and the SEO catalog in the
search bundle), their public names, the sort / posted-within / directory
enums and the `consumer` strings the site's own frontend sends.

Every id on XING is "scrambled": a numeric part plus a 6-hex-digit suffix
(FULL_TIME.ef2fe9, 3.2ebf16, 1011.6cf3f7). The suffixes are stable per
entity (the frontend ships them in its bundles), so they are tabled here;
the search's aggregations echo them with each answer, so a drift shows up
in /xing/jobs/filters first.
"""

HOST = "www.xing.com"
BASE = f"https://{HOST}"
GRAPHQL_URL = f"{BASE}/xing-one/api"

# the frontend's `consumer` tag per surface (free-form strings the API logs)
CONSUMER_SEARCH = "loggedout.web.jobs.conv_search_results.center"
CONSUMER_COMPANY_JOBS = "web.entity_pages.jobs_subpage"
CONSUMER_SIMILAR = "loggedout.web.jobs.job_details"
CONSUMER_EMPLOYEES = "loggedout.web.publisher.employees"
CONSUMER_SUGGEST = "loggedout.web.jobs.search"

# ---- job search filters: public value -> (scrambled id, site label) ----------------------------

EMPLOYMENT_TYPES = {
    "full_time": ("FULL_TIME.ef2fe9", "Full-time"),
    "part_time": ("PART_TIME.58889d", "Part-time"),
    "self_employed": ("CONTRACTOR.0ed397", "Self-employed"),
    "student": ("INTERN.dc571c", "Student"),
    "seasonal": ("SEASONAL.e4ab1d", "Seasonal"),
    "temporary": ("TEMPORARY.8ff6ad", "Temp"),
    "volunteer": ("VOLUNTARY.c61099", "Volunteer"),
}

CAREER_LEVELS = {
    "student": ("1.795d28", "Student/Intern"),
    "entry": ("2.24d1f6", "Entry Level"),
    "professional": ("3.2ebf16", "Professional/Experienced"),
    "manager": ("4.83b992", "Manager/Supervisor"),
    "executive": ("5.6b837d", "Executive (VP, SVP, etc.)"),
    "senior_executive": ("6.37d32d", "Senior Executive (CEO, CFO, President)"),
}

REMOTE_OPTIONS = {
    "remote": ("FULL_REMOTE.050e26", "Full Remote"),
    "hybrid": ("PARTLY_REMOTE.ca71ca", "Hybrid"),
    "on_site": ("NON_REMOTE.3ca273", "On-site"),
}

DISCIPLINES = {
    "analysis_statistics": ("1001.0a04a4", "Analysis and statistics"),
    "administration": ("1002.0ed5c6", "Administration"),
    "consulting": ("1003.6eca43", "Consulting"),
    "customer_service": ("1004.2c7416", "Customer service"),
    "purchasing_logistics": ("1005.6628c4", "Purchasing, materials management & logistics"),
    "finance_accounting": ("1006.375e88", "Finance, accounting & controlling"),
    "teaching_research": ("1007.b61d22", "Teaching, R&D"),
    "health_medical_social": ("1008.61ee6f", "Health, medical and social"),
    "design_architecture": ("1009.76bd22", "Graphic design and architecture"),
    "engineering": ("1010.b48650", "Engineering and technical"),
    "it_software": ("1011.6cf3f7", "IT and software development"),
    "management": ("1012.6ce534", "Management and corporate development"),
    "marketing_advertising": ("1013.2ed6ec", "Marketing and advertising"),
    "hr": ("1014.6261b0", "HR"),
    "pr_journalism": ("1015.d1d430", "PR and journalism"),
    "production_manufacturing": ("1016.455c16", "Production and manufacturing"),
    "product_management": ("1017.551846", "Product management"),
    "project_management": ("1018.1c154d", "Project management"),
    "process_planning_qa": ("1019.8e3e37", "Process planning & QA"),
    "legal": ("1020.26befa", "Legal"),
    "sales": ("1021.500257", "Sales and commerce"),
    "other": ("1022.ed6b40", "Other"),
}

POSTED_WITHIN = {"day": "LAST_24_HOURS", "week": "LAST_WEEK", "month": "LAST_MONTH"}
SORTS = {"relevance": "relevance", "date": "date"}
DIRECTORY_TYPES = {"job_role": "JOB_ROLE", "company": "COMPANY", "location": "LOCATION"}

# reverse maps: scrambled id -> public value (for echoing applied filters)
_REVERSE = {}
for _name, _table in (("employment_type", EMPLOYMENT_TYPES), ("career_level", CAREER_LEVELS),
                      ("remote", REMOTE_OPTIONS), ("discipline", DISCIPLINES)):
    _REVERSE[_name] = {sid: public for public, (sid, _label) in _table.items()}


def public_value(kind, scrambled_id):
    """'FULL_TIME.ef2fe9' -> 'full_time' (None when unknown)."""
    return _REVERSE.get(kind, {}).get(scrambled_id)


def ids_for(table, values):
    """['full_time', 'part_time'] -> their scrambled ids."""
    return [table[v][0] for v in values or [] if v in table]


SEARCH_LIMIT = 20          # the API answers 0 rows above 20
SEARCH_MAX_OFFSET = 980    # offset 1000+ answers 0 rows: 50 pages of 20
EMPLOYEES_MAX = 100        # `after` cursors are ignored anonymously; `first` goes to 100
