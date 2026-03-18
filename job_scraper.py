"""
job_scraper.py
──────────────
Scrapes jobs from multiple boards (Indeed via MCP + web scraping for others).
Returns a unified list of job dicts.
"""

from __future__ import annotations

import time
import json
import random
import logging
import hashlib
import requests
from typing import Optional
from bs4 import BeautifulSoup
from urllib.parse import urlencode, quote_plus

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


def _job_id(title: str, company: str, url: str) -> str:
    return hashlib.md5(f"{title}{company}{url}".encode()).hexdigest()[:12]


def _sleep():
    time.sleep(random.uniform(1.5, 3.5))


# ── LinkedIn scraper ───────────────────────────────────────────────────────
def scrape_linkedin(query: str, location: str, limit: int = 15) -> list[dict]:
    """Scrape LinkedIn public job listings (no login required)."""
    jobs = []
    params = {
        "keywords": query,
        "location": location,
        "f_TP": "1,2",          # past month
        "f_JT": "F",            # full-time
        "start": 0,
    }
    url = f"https://www.linkedin.com/jobs/search/?{urlencode(params)}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(resp.text, "html.parser")
        cards = soup.select("div.base-card")[:limit]
        for card in cards:
            title_el = card.select_one("h3.base-search-card__title")
            company_el = card.select_one("h4.base-search-card__subtitle")
            location_el = card.select_one("span.job-search-card__location")
            link_el = card.select_one("a.base-card__full-link")
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            company = company_el.get_text(strip=True) if company_el else ""
            loc = location_el.get_text(strip=True) if location_el else location
            apply_url = link_el["href"].split("?")[0] if link_el else url
            jobs.append({
                "id": _job_id(title, company, apply_url),
                "source": "LinkedIn",
                "title": title,
                "company": company,
                "location": loc,
                "apply_url": apply_url,
                "description": "",
                "salary": "",
                "posted": "",
            })
        _sleep()
    except Exception as e:
        logger.warning(f"LinkedIn scrape failed: {e}")
    return jobs


# ── Glassdoor scraper ──────────────────────────────────────────────────────
def scrape_glassdoor(query: str, location: str, limit: int = 15) -> list[dict]:
    """Scrape Glassdoor job listings."""
    jobs = []
    encoded_q = quote_plus(query)
    encoded_l = quote_plus(location)
    url = (
        f"https://www.glassdoor.com/Job/jobs.htm"
        f"?sc.keyword={encoded_q}&locT=C&locId=1147401&jobType=fulltime"
    )
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(resp.text, "html.parser")
        cards = soup.select("li.react-job-listing")[:limit]
        for card in cards:
            title_el = card.select_one("a.jobLink span")
            company_el = card.select_one("div.job-search-key-l93PBi")
            loc_el = card.select_one("span.loc")
            link_el = card.select_one("a.jobLink")
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            company = company_el.get_text(strip=True) if company_el else ""
            loc = loc_el.get_text(strip=True) if loc_el else location
            href = link_el["href"] if link_el else ""
            apply_url = f"https://www.glassdoor.com{href}" if href.startswith("/") else href
            jobs.append({
                "id": _job_id(title, company, apply_url),
                "source": "Glassdoor",
                "title": title,
                "company": company,
                "location": loc,
                "apply_url": apply_url,
                "description": "",
                "salary": "",
                "posted": "",
            })
        _sleep()
    except Exception as e:
        logger.warning(f"Glassdoor scrape failed: {e}")
    return jobs


# ── Built In scraper ───────────────────────────────────────────────────────
def scrape_builtin(query: str, limit: int = 15) -> list[dict]:
    """Scrape Built In (builtin.com) — popular for tech/startup roles."""
    jobs = []
    encoded_q = quote_plus(query)
    url = f"https://builtin.com/jobs/remote?search={encoded_q}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(resp.text, "html.parser")
        cards = soup.select("article.job-card")[:limit]
        for card in cards:
            title_el = card.select_one("h2 a")
            company_el = card.select_one("span.company-title")
            loc_el = card.select_one("span.job-info__location")
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            company = company_el.get_text(strip=True) if company_el else ""
            loc = loc_el.get_text(strip=True) if loc_el else "Remote"
            apply_url = "https://builtin.com" + title_el["href"]
            jobs.append({
                "id": _job_id(title, company, apply_url),
                "source": "BuiltIn",
                "title": title,
                "company": company,
                "location": loc,
                "apply_url": apply_url,
                "description": "",
                "salary": "",
                "posted": "",
            })
        _sleep()
    except Exception as e:
        logger.warning(f"BuiltIn scrape failed: {e}")
    return jobs


# ── Wellfound (AngelList) scraper ──────────────────────────────────────────
def scrape_wellfound(query: str, limit: int = 15) -> list[dict]:
    """Scrape Wellfound (startup-focused board)."""
    jobs = []
    encoded_q = quote_plus(query)
    url = f"https://wellfound.com/jobs?q={encoded_q}&remote=true"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(resp.text, "html.parser")
        cards = soup.select("div[data-test='StartupResult']")[:limit]
        for card in cards:
            title_el = card.select_one("a[data-test='job-link']")
            company_el = card.select_one("span[data-test='startup-result-name']")
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            company = company_el.get_text(strip=True) if company_el else ""
            href = title_el.get("href", "")
            apply_url = f"https://wellfound.com{href}" if href.startswith("/") else href
            jobs.append({
                "id": _job_id(title, company, apply_url),
                "source": "Wellfound",
                "title": title,
                "company": company,
                "location": "Remote",
                "apply_url": apply_url,
                "description": "",
                "salary": "",
                "posted": "",
            })
        _sleep()
    except Exception as e:
        logger.warning(f"Wellfound scrape failed: {e}")
    return jobs


# ── SimplyHired scraper ────────────────────────────────────────────────────
def scrape_simplyhired(query: str, location: str, limit: int = 15) -> list[dict]:
    jobs = []
    params = {"q": query, "l": location}
    url = f"https://www.simplyhired.com/search?{urlencode(params)}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(resp.text, "html.parser")
        cards = soup.select("article.SerpJob")[:limit]
        for card in cards:
            title_el = card.select_one("h3.jobposting-title a")
            company_el = card.select_one("span[data-testid='companyName']")
            loc_el = card.select_one("span[data-testid='searchSerpJobLocation']")
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            company = company_el.get_text(strip=True) if company_el else ""
            loc = loc_el.get_text(strip=True) if loc_el else location
            href = title_el.get("href", "")
            apply_url = f"https://www.simplyhired.com{href}" if href.startswith("/") else href
            jobs.append({
                "id": _job_id(title, company, apply_url),
                "source": "SimplyHired",
                "title": title,
                "company": company,
                "location": loc,
                "apply_url": apply_url,
                "description": "",
                "salary": "",
                "posted": "",
            })
        _sleep()
    except Exception as e:
        logger.warning(f"SimplyHired scrape failed: {e}")
    return jobs


# ── ZipRecruiter scraper ───────────────────────────────────────────────────
def scrape_ziprecruiter(query: str, location: str, limit: int = 15) -> list[dict]:
    jobs = []
    params = {"search": query, "location": location}
    url = f"https://www.ziprecruiter.com/jobs-search?{urlencode(params)}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(resp.text, "html.parser")
        cards = soup.select("article.job_result")[:limit]
        for card in cards:
            title_el = card.select_one("h2.title a")
            company_el = card.select_one("a.company_name")
            loc_el = card.select_one("ul.location_list li")
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            company = company_el.get_text(strip=True) if company_el else ""
            loc = loc_el.get_text(strip=True) if loc_el else location
            apply_url = title_el.get("href", url)
            jobs.append({
                "id": _job_id(title, company, apply_url),
                "source": "ZipRecruiter",
                "title": title,
                "company": company,
                "location": loc,
                "apply_url": apply_url,
                "description": "",
                "salary": "",
                "posted": "",
            })
        _sleep()
    except Exception as e:
        logger.warning(f"ZipRecruiter scrape failed: {e}")
    return jobs


# ── Niche boards ───────────────────────────────────────────────────────────
def scrape_remotive(query: str, limit: int = 10) -> list[dict]:
    """Remotive.io — remote-only tech/marketing jobs."""
    jobs = []
    try:
        resp = requests.get(
            f"https://remotive.com/api/remote-jobs?search={quote_plus(query)}&limit={limit}",
            timeout=15,
        )
        data = resp.json().get("jobs", [])
        for j in data[:limit]:
            jobs.append({
                "id": _job_id(j.get("title",""), j.get("company_name",""), j.get("url","")),
                "source": "Remotive",
                "title": j.get("title", ""),
                "company": j.get("company_name", ""),
                "location": j.get("candidate_required_location", "Remote"),
                "apply_url": j.get("url", ""),
                "description": j.get("description", ""),
                "salary": j.get("salary", ""),
                "posted": j.get("publication_date", ""),
            })
    except Exception as e:
        logger.warning(f"Remotive scrape failed: {e}")
    return jobs


def scrape_workable_api(query: str, limit: int = 10) -> list[dict]:
    """Query Workable job board (public listings)."""
    jobs = []
    try:
        resp = requests.get(
            f"https://www.workable.com/api/jobs?query={quote_plus(query)}&limit={limit}",
            headers=HEADERS,
            timeout=15,
        )
        items = resp.json().get("results", [])
        for j in items[:limit]:
            jobs.append({
                "id": _job_id(j.get("title",""), j.get("company",""), j.get("url","")),
                "source": "Workable",
                "title": j.get("title", ""),
                "company": j.get("company", ""),
                "location": j.get("location", {}).get("city", "Remote"),
                "apply_url": j.get("url", ""),
                "description": j.get("description", ""),
                "salary": "",
                "posted": j.get("created_at", ""),
            })
    except Exception as e:
        logger.warning(f"Workable scrape failed: {e}")
    return jobs


# ── Deduplication ──────────────────────────────────────────────────────────
def deduplicate(jobs: list[dict]) -> list[dict]:
    seen = set()
    unique = []
    for job in jobs:
        key = f"{job['title'].lower().strip()}|{job['company'].lower().strip()}"
        if key not in seen:
            seen.add(key)
            unique.append(job)
    return unique


# ── Master scrape function ─────────────────────────────────────────────────
def scrape_all_boards(
    query: str,
    location: str,
    config: dict,
    indeed_results: Optional[list[dict]] = None,
) -> list[dict]:
    """
    Scrape all enabled job boards for a single query+location combo.
    `indeed_results` — pass pre-fetched Indeed results from the MCP tool.
    """
    boards = config.get("job_boards", {})
    limit = config.get("search", {}).get("results_per_title", 15)
    all_jobs: list[dict] = []

    if indeed_results:
        all_jobs.extend(indeed_results)

    if boards.get("linkedin", True):
        logger.info(f"  Scraping LinkedIn: {query} @ {location}")
        all_jobs.extend(scrape_linkedin(query, location, limit))

    if boards.get("glassdoor", True):
        logger.info(f"  Scraping Glassdoor: {query} @ {location}")
        all_jobs.extend(scrape_glassdoor(query, location, limit))

    if boards.get("builtin", True):
        logger.info(f"  Scraping BuiltIn: {query}")
        all_jobs.extend(scrape_builtin(query, limit))

    if boards.get("wellfound", True):
        logger.info(f"  Scraping Wellfound: {query}")
        all_jobs.extend(scrape_wellfound(query, limit))

    if boards.get("simplyhired", True):
        logger.info(f"  Scraping SimplyHired: {query} @ {location}")
        all_jobs.extend(scrape_simplyhired(query, location, limit))

    if boards.get("ziprecruiter", True):
        logger.info(f"  Scraping ZipRecruiter: {query} @ {location}")
        all_jobs.extend(scrape_ziprecruiter(query, location, limit))

    # Niche boards (always on)
    logger.info(f"  Scraping Remotive: {query}")
    all_jobs.extend(scrape_remotive(query, limit))
    logger.info(f"  Scraping Workable: {query}")
    all_jobs.extend(scrape_workable_api(query, limit))

    return deduplicate(all_jobs)
