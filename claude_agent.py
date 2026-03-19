#!/usr/bin/env python3
"""
claude_agent.py
───────────────
This is the Claude Agent SDK entry point.
It wires together the MCP tools (Indeed job search, resume fetch, company data)
with the local pipeline (scraper, scorer, employee finder, outreach generator).

Run this when working inside the Claude Code / Agent environment where
MCP tools are available.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

import yaml

# Local modules
from resume_parser import parse_resume, score_job, load_resume
from job_scraper import scrape_all_boards, deduplicate
from employee_finder import find_contacts_for_job
from outreach_generator import draft_outreach, open_linkedin_inmail, send_email
from notion_tracker import sync_jobs_to_notion, update_job_status, update_outreach_status
from approval_ui import review_jobs, review_outreach, print_summary

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

RESULTS_DIR = Path("results")
RESULTS_DIR.mkdir(exist_ok=True)


def load_config(path: str = "config.yaml") -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def parse_indeed_mcp_result(raw: str | dict) -> list[dict]:
    """
    Convert the Indeed MCP tool output into our standard job dict list.
    The MCP tool returns markdown — we parse it into structured dicts.
    """
    if isinstance(raw, dict):
        raw = json.dumps(raw)

    jobs = []
    # Indeed MCP returns formatted markdown; parse job blocks
    import re
    # Pattern: each job block has title, company, location, url
    blocks = re.split(r"\n---+\n|\n\*\*\d+\.\*\*", str(raw))
    for block in blocks:
        if not block.strip():
            continue
        title_m = re.search(r"\*\*(.+?)\*\*", block)
        company_m = re.search(r"Company:\s*(.+)", block)
        location_m = re.search(r"Location:\s*(.+)", block)
        salary_m = re.search(r"Salary:\s*(.+)", block)
        url_m = re.search(r"https?://[^\s\)]+", block)
        job_id_m = re.search(r"job[_ ]?id[:\s]+([a-zA-Z0-9_-]+)", block, re.IGNORECASE)

        title = title_m.group(1).strip() if title_m else ""
        company = company_m.group(1).strip() if company_m else ""
        location = location_m.group(1).strip() if location_m else ""
        salary = salary_m.group(1).strip() if salary_m else ""
        apply_url = url_m.group(0).strip() if url_m else ""
        job_id = job_id_m.group(1).strip() if job_id_m else ""

        if title and company:
            jobs.append({
                "id": job_id or f"indeed_{abs(hash(title+company))}",
                "source": "Indeed",
                "title": title,
                "company": company,
                "location": location,
                "apply_url": apply_url,
                "description": block,
                "salary": salary,
                "posted": "",
            })
    return jobs


def run_agent_pipeline(
    indeed_results_by_query: dict[str, list[dict]],
    resume_text: str,
    config: dict,
) -> dict:
    """
    Main pipeline called by the Claude agent after MCP tool results arrive.

    Parameters
    ----------
    indeed_results_by_query : dict mapping "title|location" → list of job dicts
                              (already parsed from Indeed MCP output)
    resume_text             : raw resume text from get_resume MCP or config
    config                  : loaded config.yaml dict
    """
    import argparse
    args = argparse.Namespace(search_only=False, no_notion=False, outreach_only=None)

    resume = parse_resume(resume_text)
    search_cfg = config.get("search", {})
    min_score = search_cfg.get("min_match_score", 60)

    # Collect all raw jobs
    all_raw_jobs: list[dict] = []
    job_titles = config.get("job_titles", [])
    locations = search_cfg.get("locations", ["remote"])

    for title in job_titles:
        for location in locations:
            key = f"{title}|{location}"
            indeed_jobs = indeed_results_by_query.get(key, [])
            logger.info(f"Aggregating jobs for: {title} @ {location} — {len(indeed_jobs)} from Indeed")
            scraped = scrape_all_boards(title, location, config, indeed_jobs)
            all_raw_jobs.extend(scraped)

    all_raw_jobs = deduplicate(all_raw_jobs)
    logger.info(f"Total unique jobs: {len(all_raw_jobs)}")

    # Score
    scored = [score_job(j, resume, config) for j in all_raw_jobs]
    matched = sorted(
        [j for j in scored if j.get("match_score", 0) >= min_score and "disqualifier" not in j],
        key=lambda j: -j["match_score"],
    )
    logger.info(f"Jobs above {min_score}% match: {len(matched)}")

    # User reviews jobs
    approved_jobs = review_jobs(matched)
    if not approved_jobs:
        return {"approved_jobs": 0, "approved_drafts": 0}

    # Notion sync
    notion_map = {}
    if not args.no_notion:
        notion_map = sync_jobs_to_notion(approved_jobs, config)
        for job in approved_jobs:
            pid = notion_map.get(job.get("id", ""))
            if pid:
                update_job_status(pid, "Applying")

    # Find contacts + draft outreach
    all_drafts = []
    for job in approved_jobs:
        contacts = find_contacts_for_job(job)
        for contact in contacts:
            all_drafts.append(draft_outreach(job, contact, resume, config))

    # User reviews outreach
    approved_drafts = review_outreach(all_drafts)

    # Send approved outreach
    smtp_cfg = {
        "host": os.environ.get("SMTP_HOST", "smtp.gmail.com"),
        "port": int(os.environ.get("SMTP_PORT", "465")),
        "user": os.environ.get("SMTP_USER", config.get("outreach", {}).get("your_email", "")),
        "pass_": os.environ.get("SMTP_PASS", ""),
    }

    for draft in approved_drafts:
        contact = draft.get("contact", {})
        to_email = contact.get("email", "")
        linkedin_url = contact.get("linkedin_url", "")
        job_info = draft.get("job", {})

        if to_email and smtp_cfg["user"] and smtp_cfg["pass_"]:
            send_email(draft, smtp_cfg["host"], smtp_cfg["port"],
                       smtp_cfg["user"], smtp_cfg["pass_"], to_email)

        if linkedin_url:
            open_linkedin_inmail(linkedin_url, draft.get("inmail_body", ""))

        job_id = next(
            (j.get("id") for j in approved_jobs
             if j.get("title") == job_info.get("title")
             and j.get("company") == job_info.get("company")), ""
        )
        pid = notion_map.get(job_id)
        if pid:
            update_outreach_status(pid, "Sent")

    summary = {
        "total_jobs": len(all_raw_jobs),
        "matched_jobs": len(matched),
        "approved_jobs": len(approved_jobs),
        "total_drafts": len(all_drafts),
        "approved_drafts": len(approved_drafts),
        "notion_synced": bool(notion_map),
    }
    print_summary(summary)
    return summary


# ── Standalone demo (no MCP) ───────────────────────────────────────────────
if __name__ == "__main__":
    config = load_config("config.yaml")
    try:
        resume_text = load_resume(config)
    except FileNotFoundError as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    # No Indeed MCP results in standalone mode
    run_agent_pipeline({}, resume_text, config)
