"""Marshmallow request schemas for every /xing/* route.

Generic fields live in the shared top-level schema_fields.py; this module
adds the XING resolvers (refs.py). Every schema's load() output is the
kwargs dict its endpoint function takes.

ONE param per input (tripadvisor QueryOrLinkField convention, never a
sibling `url`/`id` pair): `job` takes a posting id, a job slug or a job
link; `company` a page slug or a company link; `profile` a page name or a
profile link; `link` a xing.com job search link.
"""
import re

from marshmallow import ValidationError, fields, validate, validates_schema

from schema_fields import (BaseSchema, ChoiceField, CommaListField, COUNTRY_CODES, PageField, PositiveInt, QueryField, RefField,
                           StrippedString)
from xing import refdata as R
from xing import refs

MAX_BATCH = 10
MAX_PAGE = R.SEARCH_MAX_OFFSET // R.SEARCH_LIMIT + 1
_SCRAMBLED_ID_RE = re.compile(r"^[A-Za-z0-9_]{1,24}\.[0-9a-f]{6}$")
_LETTER_RE = re.compile(r"^(?:[a-zäöü]|#)$")


class JobField(RefField):
    resolver = staticmethod(refs.resolve_job)


class CompanyField(RefField):
    resolver = staticmethod(refs.resolve_company)


class ProfileField(RefField):
    resolver = staticmethod(refs.resolve_profile)


class SearchLinkField(RefField):
    resolver = staticmethod(refs.resolve_search_link)


class JobListField(fields.Field):
    """'155730561, https://www.xing.com/jobs/…-156019027' -> posting ids (1..MAX_BATCH)."""

    def __init__(self, **kwargs):
        kwargs.setdefault("required", True)
        super().__init__(**kwargs)

    def _deserialize(self, value, attr, data, **kwargs):
        try:
            return refs.resolve_jobs(value, MAX_BATCH)
        except ValueError as e:
            raise ValidationError(str(e))


class ScrambledIdListField(CommaListField):
    """XING ids as the API reports them ('90100.a8b7b7,25948.0e87ae')."""

    def __init__(self, **kwargs):
        kwargs.setdefault("max_items", 10)
        super().__init__(upper=False, **kwargs)

    def _deserialize(self, value, attr, data, **kwargs):
        items = super()._deserialize(value, attr, data, **kwargs)
        for item in items or []:
            if not _SCRAMBLED_ID_RE.match(item):
                raise ValidationError(f"'{item}' is not a XING id (expected the form 90100.a8b7b7).")
        return items


class ScrambledIdField(StrippedString):
    def __init__(self, **kwargs):
        kwargs.setdefault("required", False)
        kwargs.setdefault("load_default", None)
        super().__init__(**kwargs)

    def _deserialize(self, value, attr, data, **kwargs):
        value = super()._deserialize(value, attr, data, **kwargs)
        if value is not None and not _SCRAMBLED_ID_RE.match(value):
            raise ValidationError(f"'{value}' is not a XING city id (see /xing/autocomplete/locations).")
        return value


def _choices(table):
    return CommaListField(allowed=list(table), upper=False, max_items=len(table))


# ---- jobs ----------------------------------------------------------------------------------------

class _JobFilters(BaseSchema):
    employment_type = _choices(R.EMPLOYMENT_TYPES)
    career_level = _choices(R.CAREER_LEVELS)
    remote = _choices(R.REMOTE_OPTIONS)
    discipline = _choices(R.DISCIPLINES)
    posted_within = ChoiceField(list(R.POSTED_WITHIN))


class JobSearchSchema(_JobFilters):
    keywords = StrippedString(required=False, load_default=None, validate=validate.Length(max=200))
    location = StrippedString(required=False, load_default=None, validate=validate.Length(max=150))
    city = ScrambledIdField()
    radius = fields.Integer(load_default=None, strict=False, validate=validate.Range(min=0, max=500))
    industry = ScrambledIdListField()
    company = ScrambledIdListField()
    salary_min = PositiveInt(max_value=10_000_000)
    salary_max = PositiveInt(max_value=10_000_000)
    sort = ChoiceField(list(R.SORTS), load_default="relevance")
    page = PageField(max_page=MAX_PAGE)

    @validates_schema
    def _needs_a_query(self, data, **kwargs):
        if not any(data.get(k) for k in ("keywords", "location", "city", "industry", "company", "discipline")):
            raise ValidationError("Give keywords, a location / city, or a discipline / industry / company filter.", "keywords")
        if data.get("salary_min") and data.get("salary_max") and data["salary_min"] > data["salary_max"]:
            raise ValidationError("salary_min must not exceed salary_max.", "salary_min")


class JobSchema(BaseSchema):
    job = JobField()


class JobBatchSchema(BaseSchema):
    jobs = JobListField()


class SimilarJobsSchema(BaseSchema):
    job = JobField()
    limit = fields.Integer(load_default=10, strict=False, validate=validate.Range(min=1, max=20))


class SearchLinkSchema(BaseSchema):
    link = SearchLinkField()
    page = fields.Integer(load_default=None, strict=False, validate=validate.Range(min=1, max=MAX_PAGE))


class RelatedSchema(BaseSchema):
    role = QueryField(max_length=100)
    location = StrippedString(required=False, load_default=None, validate=validate.Length(max=100))


class EmptySchema(BaseSchema):
    pass


# ---- companies ---------------------------------------------------------------------------------

class CompanySchema(BaseSchema):
    company = CompanyField()


class CompanyJobsSchema(_JobFilters):
    company = CompanyField()
    keywords = StrippedString(required=False, load_default=None, validate=validate.Length(max=200))
    sort = ChoiceField(list(R.SORTS), load_default="date")
    page = PageField(max_page=MAX_PAGE)


class EmployeesSchema(BaseSchema):
    company = CompanyField()
    limit = fields.Integer(load_default=20, strict=False, validate=validate.Range(min=1, max=R.EMPLOYEES_MAX))


class NewsSchema(BaseSchema):
    company = CompanyField()
    limit = fields.Integer(load_default=20, strict=False, validate=validate.Range(min=1, max=50))
    before = StrippedString(required=False, load_default=None, validate=validate.Regexp(
        r"^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}:\d{2}Z?)?$", error="Must be an ISO datetime (2024-09-11T05:00:01Z)."))


# ---- profiles ------------------------------------------------------------------------------------

class ProfileSchema(BaseSchema):
    profile = ProfileField()


# ---- lookups -------------------------------------------------------------------------------------

class LocationSuggestSchema(BaseSchema):
    query = QueryField(max_length=100)
    language = ChoiceField(["en", "de"], load_default="en")
    countries = CommaListField(allowed=list(COUNTRY_CODES), upper=True, max_items=10)
    limit = fields.Integer(load_default=10, strict=False, validate=validate.Range(min=1, max=20))


class RoleSuggestSchema(BaseSchema):
    query = QueryField(max_length=100)
    limit = fields.Integer(load_default=10, strict=False, validate=validate.Range(min=1, max=20))


class DirectorySchema(BaseSchema):
    letter = StrippedString(required=True)
    kind = ChoiceField(list(R.DIRECTORY_TYPES), load_default="job_role")
    limit = fields.Integer(load_default=100, strict=False, validate=validate.Range(min=1, max=1000))

    @validates_schema
    def _letter(self, data, **kwargs):
        letter = (data.get("letter") or "").lower()
        if not _LETTER_RE.match(letter):
            raise ValidationError("Must be one letter a-z, ä, ö, ü or # (numbers).", "letter")
        data["letter"] = letter
