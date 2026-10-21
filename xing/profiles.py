"""/xing/profiles/details — a member's public profile by page name or
link: header, current occupation, work history, education, languages,
skills and the "similar profiles" rail, from the logged-out profile query
(the same data the public profile page renders).
"""
from xing import fetch
from xing import parsers as P


def details(profile):
    data = fetch.graphql("profileLoProfile", {"id": profile, "idAsString": profile}, label=f"profile {profile}")
    out = P.profile(data)
    if out is None:
        raise fetch.XingNotFound(f"XING has no public profile '{profile}'")
    return out
