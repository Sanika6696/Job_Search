"""
notion_tracker.py
─────────────────
Syncs job applications and outreach status to a Notion database.
Requires NOTION_API_KEY env var and a database ID in config.yaml.
"""

from __future__ import annotations

import os
import logging
import requests

logger = logging.getLogger(__name__)

NOTION_API_BASE = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"


def _headers() -> dict:
    token = os.environ.get("NOTION_API_KEY", "")
    if not token:
        raise EnvironmentError(
            "NOTION_API_KEY env var is not set. "
            "Add it to your .env file: NOTION_API_KEY=secret_..."
        )
    return {
        "Authorization": f"Bearer {token}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


def create_job_database(parent_page_id: str, title: str = "Job Applications") -> str:
    """Create a Notion database to track applications. Returns database_id."""
    payload = {
        "parent": {"type": "page_id", "page_id": parent_page_id},
        "title": [{"type": "text", "text": {"content": title}}],
        "properties": {
            "Job Title": {"title": {}},
            "Company": {"rich_text": {}},
            "Source": {"select": {"options": [
                {"name": "Indeed", "color": "blue"},
                {"name": "LinkedIn", "color": "purple"},
                {"name": "Glassdoor", "color": "green"},
                {"name": "BuiltIn", "color": "orange"},
                {"name": "Wellfound", "color": "pink"},
                {"name": "Remotive", "color": "yellow"},
                {"name": "SimplyHired", "color": "gray"},
                {"name": "ZipRecruiter", "color": "red"},
                {"name": "Workable", "color": "brown"},
            ]}},
            "Match Score": {"number": {"format": "percent"}},
            "Status": {"select": {"options": [
                {"name": "To Review", "color": "gray"},
                {"name": "Applying", "color": "blue"},
                {"name": "Applied", "color": "green"},
                {"name": "Outreach Sent", "color": "purple"},
                {"name": "Interview", "color": "yellow"},
                {"name": "Offer", "color": "pink"},
                {"name": "Rejected", "color": "red"},
                {"name": "Skipped", "color": "brown"},
            ]}},
            "Apply URL": {"url": {}},
            "Location": {"rich_text": {}},
            "Salary": {"rich_text": {}},
            "Notes": {"rich_text": {}},
            "Date Added": {"date": {}},
            "Outreach Status": {"select": {"options": [
                {"name": "None", "color": "gray"},
                {"name": "Draft Ready", "color": "blue"},
                {"name": "Approved", "color": "green"},
                {"name": "Sent", "color": "purple"},
            ]}},
        },
    }
    resp = requests.post(
        f"{NOTION_API_BASE}/databases",
        headers=_headers(),
        json=payload,
    )
    resp.raise_for_status()
    return resp.json()["id"]


def add_job_to_notion(database_id: str, job: dict) -> str:
    """Add a single job to the Notion database. Returns page_id."""
    from datetime import date
    score = job.get("match_score", 0)
    payload = {
        "parent": {"database_id": database_id},
        "properties": {
            "Job Title": {
                "title": [{"text": {"content": job.get("title", "")}}]
            },
            "Company": {
                "rich_text": [{"text": {"content": job.get("company", "")}}]
            },
            "Source": {
                "select": {"name": job.get("source", "Other")}
            },
            "Match Score": {
                "number": score / 100
            },
            "Status": {
                "select": {"name": "To Review"}
            },
            "Apply URL": {
                "url": job.get("apply_url") or None
            },
            "Location": {
                "rich_text": [{"text": {"content": job.get("location", "")}}]
            },
            "Salary": {
                "rich_text": [{"text": {"content": job.get("salary", "")}}]
            },
            "Date Added": {
                "date": {"start": date.today().isoformat()}
            },
            "Outreach Status": {
                "select": {"name": "None"}
            },
        },
    }
    resp = requests.post(
        f"{NOTION_API_BASE}/pages",
        headers=_headers(),
        json=payload,
    )
    resp.raise_for_status()
    return resp.json()["id"]


def update_job_status(page_id: str, status: str, notes: str = "") -> None:
    """Update the status of a job application page."""
    payload: dict = {
        "properties": {
            "Status": {"select": {"name": status}},
        }
    }
    if notes:
        payload["properties"]["Notes"] = {
            "rich_text": [{"text": {"content": notes}}]
        }
    resp = requests.patch(
        f"{NOTION_API_BASE}/pages/{page_id}",
        headers=_headers(),
        json=payload,
    )
    resp.raise_for_status()


def update_outreach_status(page_id: str, outreach_status: str) -> None:
    payload = {
        "properties": {
            "Outreach Status": {"select": {"name": outreach_status}},
        }
    }
    resp = requests.patch(
        f"{NOTION_API_BASE}/pages/{page_id}",
        headers=_headers(),
        json=payload,
    )
    resp.raise_for_status()


def sync_jobs_to_notion(jobs: list[dict], config: dict) -> dict[str, str]:
    """
    Sync a list of scored jobs to Notion.
    Returns mapping of job_id → notion_page_id.
    """
    notion_cfg = config.get("notion", {})
    if not notion_cfg.get("enabled", False):
        logger.info("Notion sync is disabled. Set notion.enabled: true in config.yaml")
        return {}

    database_id = notion_cfg.get("database_id", "")
    if not database_id:
        logger.warning("Notion database_id not set in config.yaml")
        return {}

    mapping = {}
    for job in jobs:
        try:
            page_id = add_job_to_notion(database_id, job)
            mapping[job.get("id", "")] = page_id
            logger.info(f"  Added to Notion: {job.get('title')} @ {job.get('company')}")
        except Exception as e:
            logger.warning(f"  Notion sync failed for {job.get('title')}: {e}")

    return mapping
