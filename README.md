# 💼 Xing Scraper

Xing Scraper is a **free and open-source** scraper that gets you **unlimited** detailed Xing data for free.

## ✨ What Can I Get?

- 🔍 **Search 550K+ live jobs** — keywords, city & radius, salary band, career level, remote and job field
- 📄 **Full job details** — description, salary range, career level, remote options, company card & apply link
- 🏢 **Company pages** — Tesla, BMW Group & co: about, size, followers, locations, open jobs, employees & news
- 👤 **Public member profiles** — headline, work history, education, languages & skills

## 💼 Example: A Full Xing Job

```json
{
  "id": 158622557,
  "title": "Product Integrity Engineer - Incident Response",
  "link": "https://www.xing.com/jobs/berlin-product-integrity-engineer-incident-response-158622557",
  "company": {
    "id": "131040.ce063d",
    "name": "Tesla Germany GmbH",
    "size": "10,001 or more employees",
    "industry": "Automotive, motorcycles and bicycles",
    "link": "https://www.xing.com/pages/tesla"
  },
  "location": { "city": "Berlin", "street": "Friedrichshagener Str. 29-36", "zip_code": "12555", "country": "Germany" },
  "employment_type": { "value": "full_time", "label": "Full-time" },
  "career_level": { "value": "professional", "label": "Professional/Experienced" },
  "remote_options": ["on_site"],
  "salary": { "currency": "EUR", "min": 57000, "max": 78000, "median": 68500, "is_estimate": true },
  "application": { "type": "external_link", "link": "https://www.tesla.com/careers/search/job/286485?source=BA&utm_source=xing.com" },
  "posted_at": "2026-10-17T08:19:44Z",
  "expires_at": "2027-10-17T08:25:01Z",
  "description": {
    "text": "What to Expect\n\nEMEA Vehicle Engineering is looking for an experienced Engineer, to join our team in the role of Engineer - Incident Response..."
  },
  "keywords": ["engineering", "legal", "analysis", "vehicle", "design"]
}
```

*Trimmed for readability.*

## 🚀 Unlimited Free Xing Data — Get It in 60 Seconds

1️⃣ Clone and install:
```bash
git clone https://github.com/omkarcloud/xing-scraper
cd xing-scraper
python -m pip install -r requirements.txt
```

2️⃣ Start the API:
```bash
python run.py
```

3️⃣ Get your first data:
```bash
curl "http://localhost:8000/jobs/details?job=158622557"
```

```json
{
  "id": 158622557,
  "title": "Product Integrity Engineer - Incident Response",
  "link": "https://www.xing.com/jobs/berlin-product-integrity-engineer-incident-response-158622557",
  "company": {
    "id": "131040.ce063d",
    "name": "Tesla Germany GmbH",
    "industry": "Automotive, motorcycles and bicycles",
    "link": "https://www.xing.com/pages/tesla"
  },
  "location": { "city": "Berlin", "zip_code": "12555", "country": "Germany", "country_code": "DE" },
  "employment_type": { "value": "full_time", "label": "Full-time" },
  "career_level": { "value": "professional", "label": "Professional/Experienced" },
  "salary": { "currency": "EUR", "min": 57000, "max": 78000, "median": 68500, "is_estimate": true },
  "posted_at": "2026-10-17T08:19:44Z",
  "expires_at": "2027-10-17T08:25:01Z"
}
```

All 15 endpoints are now live at `http://localhost:8000`.

XING shows every job to visitors in Germany, Austria, Switzerland and the US. From some other countries it hides part of them (they come back as `"is_visible": false`). If you see that, set `XING_PROXY=http://user:pass@host:port` to a proxy in one of those countries before `python run.py`.

## 📚 Endpoints

15 endpoints cover everything you need.

| Endpoint | Path | Returns |
|---|---|---|
| Job Details | `/jobs/details` | Full description, salary, career level, remote options & apply link |
| Autocomplete Job Titles | `/autocomplete/roles` | Job-title suggestions straight from XING's search box |
| Autocomplete Locations | `/autocomplete/locations` | City suggestions with IDs for precise job searches |
| Search Jobs | `/jobs/search` | 20 jobs per page; salary, career level, remote & field filters |
| Job Filters | `/jobs/filters` | Every filter value Search Jobs accepts, with XING's IDs |
| Jobs by Search Link | `/jobs/by-link` | The jobs behind any xing.com job search URL |
| Batch Job Details | `/jobs/batch` | Up to 10 full job ads in one call |
| Similar Jobs | `/jobs/similar` | The jobs XING recommends next to any job |
| Company Details | `/companies/details` | About, size, followers, address, locations & related companies |
| Company Jobs | `/companies/jobs` | Every open job at one employer, filterable, 20 per page |
| Company Employees | `/companies/employees` | Up to 100 employees with headline, photo & profile link |
| Company News | `/companies/news` | Posts, articles, likes & comments, newest first |
| Profile Details | `/profiles/details` | Work history, education, languages & skills of any public member |
| Related Job Searches | `/jobs/related` | Top cities with job counts, related titles & local skills |
| Directory | `/directory` | A-Z job titles with live job counts, companies & cities |

## 🔍 Exploring Parameters

The same API is published on RapidAPI, and its playground is the easiest place to try parameters and see raw responses. Once a request looks right, run it locally for **unlimited free** data.

1. [Subscribe to the free plan](https://rapidapi.com/OmkarCloud/api/best-xing-scraper-free-1000-calls/pricing) — 1,000 calls/month, no credit card.
2. [Try the endpoints in the playground](https://rapidapi.com/OmkarCloud/api/best-xing-scraper-free-1000-calls/playground) — every param is pre-filled, so you see real data in one click.
3. Copy the generated code and replace `https://best-xing-scraper-free-1000-calls.p.rapidapi.com` with `http://localhost:8000`. It will now run against your local API.

```python
import requests

# generated by the playground, host swapped for the local API
response = requests.get(
    "http://localhost:8000/jobs/search",
    params={"keywords": "software engineer", "location": "Berlin", "remote": "hybrid,remote", "salary_min": 60000},
)
print(response.json())
```

## 💬 Have Questions? We Have Answers.

You're a developer — we know how hard completing a project can be. So we offer full support: just message us and we'll reply ✅ with a solution within 1 working day.

[![Message Us on WhatsApp about Xing Scraper](https://raw.githubusercontent.com/omkarcloud/assets/master/images/whatsapp-us.png)](https://api.whatsapp.com/send?phone=918178804274&text=I%20need%20help%20using%20the%20Xing%20Scraper%20API.)

[![Ask Us by Email about Xing Scraper](https://raw.githubusercontent.com/omkarcloud/assets/master/images/ask-on-email.png)](mailto:happy.to.help@omkar.cloud?subject=Help%20with%20Xing%20Scraper%20API&body=I%20need%20help%20using%20the%20Xing%20Scraper%20API.)

## ⚡ Popular Scrapers by Omkar Cloud

- [**Google Maps Scraper (3,100+ GitHub Stars)**](https://github.com/omkarcloud/google-maps-scraper) — type "dentists in New York", get every business as a ready-to-call lead list: phones, emails, websites & reviews. Up to 100K free leads/month.
- [**Stepstone Scraper**](https://github.com/omkarcloud/stepstone-scraper) — Stepstone jobs, salaries & employer ratings from 8 boards
- [**Glassdoor Scraper**](https://github.com/omkarcloud/glassdoor-scraper) — Glassdoor jobs, company ratings, salaries & reviews
- [**Upwork Scraper**](https://github.com/omkarcloud/upwork-scraper) — Upwork jobs, clients, freelancers & agencies
- [**G2 Scraper**](https://www.omkar.cloud/tools/g2-scraper) — G2 product details, ratings & AI-found contacts
- [**Website Email Contact Scraper**](https://www.omkar.cloud/tools/website-email-contact-scraper) — emails, phones & socials from any website

## ⭐ Love It? [Star It ⭐!](https://github.com/omkarcloud/xing-scraper)

Star the repo ⭐ and become my star hero!

It's just 1 click, but it means the world to me.

[![Star us on GitHub](https://raw.githubusercontent.com/omkarcloud/google-maps-scraper/master/screenshots/star-us.png)](https://github.com/omkarcloud/xing-scraper)
