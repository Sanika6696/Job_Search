"""
employee_finder.py
──────────────────
Finds relevant people at target companies to reach out to:
  - People who posted about the role on LinkedIn
  - People working in the relevant department
  - Recently hired people in similar roles

Uses web scraping + LinkedIn public search (no login required for basic search).
"""

from __future__ import annotations

import re
import time
import random
import logging
import requests
from urllib.parse import urlencode, quote_plus
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

# Roles worth contacting at the target company
TARGET_ROLES = [
    "recruiter",
    "talent acquisition",
    "hiring manager",
    "head of data",
    "head of analytics",
    "head of marketing",
    "vp data",
    "vp marketing",
    "director of analytics",
    "director of marketing",
    "data team",
    "growth team",
    "marketing team",
]


def _sleep():
    time.sleep(random.uniform(2.0, 4.0))


# ── LinkedIn people search (public) ───────────────────────────────────────
def search_linkedin_people(company: str, role_hint: str = "") -> list[dict]:
    """
    Search LinkedIn's public people directory for employees at `company`.
    Returns a list of profile dicts.
    """
    people = []
    query = f"{company} {role_hint}".strip()
    params = {
        "keywords": query,
        "origin": "SWITCH_SEARCH_VERTICAL",
    }
    url = f"https://www.linkedin.com/search/results/people/?{urlencode(params)}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(resp.text, "html.parser")
        cards = soup.select("li.reusable-search__result-container")[:10]
        for card in cards:
            name_el = card.select_one("span.entity-result__title-text a")
            headline_el = card.select_one("div.entity-result__primary-subtitle")
            location_el = card.select_one("div.entity-result__secondary-subtitle")
            link_el = card.select_one("a.app-aware-link")
            if not name_el:
                continue
            name = name_el.get_text(strip=True)
            headline = headline_el.get_text(strip=True) if headline_el else ""
            location = location_el.get_text(strip=True) if location_el else ""
            profile_url = link_el["href"].split("?")[0] if link_el else ""
            # Filter to people who seem relevant
            headline_lower = headline.lower()
            if company.lower() in headline_lower or any(
                r in headline_lower for r in TARGET_ROLES
            ):
                people.append({
                    "name": name,
                    "headline": headline,
                    "location": location,
                    "linkedin_url": profile_url,
                    "source": "linkedin_search",
                    "company": company,
                })
        _sleep()
    except Exception as e:
        logger.warning(f"LinkedIn people search failed for {company}: {e}")
    return people


# ── Google search for LinkedIn profiles ───────────────────────────────────
def google_linkedin_profiles(company: str, role_hint: str = "") -> list[dict]:
    """
    Use Google to find LinkedIn profiles at a company.
    More reliable than direct LinkedIn search since it doesn't require login.
    """
    people = []
    query = f'site:linkedin.com/in "{company}" "{role_hint}"'
    params = {"q": query, "num": 10}
    url = f"https://www.google.com/search?{urlencode(params)}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(resp.text, "html.parser")
        results = soup.select("div.g")[:10]
        for result in results:
            title_el = result.select_one("h3")
            link_el = result.select_one("a")
            snippet_el = result.select_one("div.VwiC3b")
            if not title_el or not link_el:
                continue
            href = link_el.get("href", "")
            if "linkedin.com/in/" not in href:
                continue
            title = title_el.get_text(strip=True)
            snippet = snippet_el.get_text(strip=True) if snippet_el else ""
            # Parse name from title (usually "Name - Role at Company | LinkedIn")
            name = title.split(" - ")[0].strip() if " - " in title else title
            headline = title.split(" - ")[1].strip() if " - " in title else ""
            people.append({
                "name": name,
                "headline": headline,
                "snippet": snippet,
                "linkedin_url": href,
                "source": "google_search",
                "company": company,
            })
        _sleep()
    except Exception as e:
        logger.warning(f"Google profile search failed for {company}: {e}")
    return people


# ── Find recently hired employees ──────────────────────────────────────────
def find_recently_hired(company: str, role_hint: str = "") -> list[dict]:
    """
    Search for recently hired employees at a company via LinkedIn and Google.
    Looks for 'started new position' or '#opentowork' signals.
    """
    people = []
    query = f'site:linkedin.com/in "{company}" "started new position" "{role_hint}"'
    params = {"q": query, "num": 5}
    url = f"https://www.google.com/search?{urlencode(params)}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(resp.text, "html.parser")
        results = soup.select("div.g")[:5]
        for result in results:
            title_el = result.select_one("h3")
            link_el = result.select_one("a")
            if not title_el or not link_el:
                continue
            href = link_el.get("href", "")
            if "linkedin.com/in/" not in href:
                continue
            title = title_el.get_text(strip=True)
            name = title.split(" - ")[0].strip()
            headline = title.split(" - ")[1].strip() if " - " in title else ""
            people.append({
                "name": name,
                "headline": headline,
                "linkedin_url": href,
                "source": "recently_hired",
                "company": company,
            })
        _sleep()
    except Exception as e:
        logger.warning(f"Recently hired search failed for {company}: {e}")
    return people


# ── Find posts about the role ──────────────────────────────────────────────
def find_role_posts(company: str, job_title: str) -> list[dict]:
    """
    Search for LinkedIn posts where someone at the company announced hiring
    or shared the job opening.
    """
    people = []
    query = f'site:linkedin.com "{company}" "{job_title}" "hiring" OR "we are looking" OR "join our team"'
    params = {"q": query, "num": 5}
    url = f"https://www.google.com/search?{urlencode(params)}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(resp.text, "html.parser")
        results = soup.select("div.g")[:5]
        for result in results:
            title_el = result.select_one("h3")
            link_el = result.select_one("a")
            snippet_el = result.select_one("div.VwiC3b")
            if not title_el or not link_el:
                continue
            href = link_el.get("href", "")
            if "linkedin.com" not in href:
                continue
            title = title_el.get_text(strip=True)
            snippet = snippet_el.get_text(strip=True) if snippet_el else ""
            people.append({
                "name": title,
                "headline": "",
                "snippet": snippet,
                "linkedin_url": href,
                "source": "role_post",
                "company": company,
            })
        _sleep()
    except Exception as e:
        logger.warning(f"Role post search failed for {company}: {e}")
    return people


# ── Master finder ──────────────────────────────────────────────────────────
def find_contacts_for_job(job: dict) -> list[dict]:
    """
    Given a job dict, return a ranked list of people to reach out to.
    Priority: recruiter > hiring manager > department head > recently hired > post author
    """
    company = job.get("company", "")
    title = job.get("title", "")
    if not company:
        return []

    contacts = []

    # 1. Recruiters / talent acquisition
    contacts.extend(google_linkedin_profiles(company, "recruiter"))
    contacts.extend(google_linkedin_profiles(company, "talent acquisition"))

    # 2. Department heads
    if any(kw in title.lower() for kw in ["data", "analytics", "analyst"]):
        contacts.extend(google_linkedin_profiles(company, "head of data analytics"))
        contacts.extend(google_linkedin_profiles(company, "director of analytics"))
    if any(kw in title.lower() for kw in ["marketing", "growth", "lifecycle"]):
        contacts.extend(google_linkedin_profiles(company, "head of marketing"))
        contacts.extend(google_linkedin_profiles(company, "vp marketing"))

    # 3. People who posted about this role
    contacts.extend(find_role_posts(company, title))

    # 4. Recently hired in similar roles
    contacts.extend(find_recently_hired(company, title))

    # Deduplicate by LinkedIn URL
    seen_urls = set()
    unique_contacts = []
    for c in contacts:
        url = c.get("linkedin_url", "")
        if url and url not in seen_urls:
            seen_urls.add(url)
            unique_contacts.append(c)

    return unique_contacts[:8]  # Cap at 8 contacts per company
