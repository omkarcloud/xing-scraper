"""Use the scraper straight from Python — no server needed.

    python main.py

Every function returns the same JSON the API does; results are written to
output/*.json.
"""
import json
import os

from xing import companies, jobs, refs

os.makedirs("output", exist_ok=True)


def save(name, data):
    path = os.path.join("output", name)
    with open(path, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"saved {path}")


if __name__ == "__main__":
    # a job id, its slug or any xing.com job link
    save("job_158622557.json", jobs.details(refs.resolve_job("158622557")))

    # 20 jobs per page, with every site filter
    save("search_software_engineer_berlin.json", jobs.search(keywords="software engineer", location="Berlin"))

    # a company page: its slug or any xing.com/pages link
    save("company_tesla.json", companies.details(refs.resolve_company("tesla")))
