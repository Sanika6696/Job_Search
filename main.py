#!/usr/bin/env python3
"""
main.py — Job Search Automation Agent
──────────────────────────────────────
Orchestrates the full pipeline:

  1. Load resume → parse skills & experience
  2. Search jobs across all boards (Indeed via MCP + web scraping)
  3. Score each job against your resume
  4. Show jobs for review — you decide which to apply for
  5. Find employees at target companies to reach out to
  6. Draft personalised email + LinkedIn InMail for each contact
  7. Show outreach for approval — nothing sends without your OK
  8. Send approved messages and sync everything to Notion

Usage:
    python main.py                    # full run
    python main.py --search-only      # stop after job review
    python main.py --outreach-only    # load existing results, just do outreach
    python main.py --no-notion        # skip Notion sync
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

import yaml

from resume_parser import load_resume, parse_resume
from job_scraper import scrape_all_boards
from resume_parser import score_job
from employee_finder import find_contacts_for_job
from outreach_generator import draft_outreach, send_email, open_linkedin_inmail
from notion_tracker import sync_jobs_to_notion, update_job_status, update_outreach_status
from approval_ui import review_jobs, review_outreach, print_summary

# ── Logging ────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

RESULTS_DIR = Path("results")
RESULTS_DIR.mkdir(exist_ok=True)


# ── Config loader ──────────────────────────────────────────────────────────
def load_config(path: str = "config.yaml") -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


# ── Indeed search via MCP (called from CLI wrapper) ────────────────────────
def search_indeed_stub(query: str, location: str, config: dict) -> list[dict]:
    """
    Placeholder: in the Claude agent context the MCP tool handles Indeed search.
    When running standalone, returns empty list and logs a notice.
    """
    logger.info(
        "  [Indeed] MCP tool not available in standalone mode. "
        "Run via the Claude agent for Indeed results."
    )
    return []


# ── Core pipeline ──────────────────────────────────────────────────────────
def run_pipeline(config: dict, args: argparse.Namespace) -> dict:
    results = {
        "total_jobs": 0,
        "matched_jobs": 0,
        "approved_jobs": 0,
        "total_drafts": 0,
        "approved_drafts": 0,
        "notion_synced": False,
        "saved_path": "",
    }

    # ── 1. Load & parse resume ─────────────────────────────────────────────
    logger.info("Loading resume...")
    try:
        resume_text = load_resume(config)
    except FileNotFoundError as e:
        logger.error(str(e))
        sys.exit(1)
    resume = parse_resume(resume_text)
    logger.info(
        f"  Skills detected: {', '.join(resume['skills'][:10])}"
        + (f"  (+{len(resume['skills'])-10} more)" if len(resume['skills']) > 10 else "")
    )
    logger.info(f"  Years of experience: {resume['years_of_experience']}")

    # ── 2. Scrape jobs ─────────────────────────────────────────────────────
    search_cfg = config.get("search", {})
    job_titles = config.get("job_titles", [])
    locations = search_cfg.get("locations", ["remote"])
    min_score = search_cfg.get("min_match_score", 60)

    all_raw_jobs: list[dict] = []

    for title in job_titles:
        for location in locations:
            logger.info(f"Searching: '{title}' in '{location}'")
            indeed_jobs = search_indeed_stub(title, location, config)
            jobs = scrape_all_boards(title, location, config, indeed_jobs)
            all_raw_jobs.extend(jobs)
            logger.info(f"  → {len(jobs)} jobs found")

    results["total_jobs"] = len(all_raw_jobs)
    logger.info(f"Total raw jobs collected: {len(all_raw_jobs)}")

    # ── 3. Score & filter jobs ─────────────────────────────────────────────
    logger.info(f"Scoring jobs (min match score: {min_score}%)...")
    scored_jobs = [score_job(job, resume, config) for job in all_raw_jobs]
    matched_jobs = [
        j for j in scored_jobs
        if j.get("match_score", 0) >= min_score
        and "disqualifier" not in j
    ]
    matched_jobs.sort(key=lambda j: j.get("match_score", 0), reverse=True)
    results["matched_jobs"] = len(matched_jobs)
    logger.info(f"  {len(matched_jobs)} jobs meet the {min_score}% threshold")

    # ── 4. Save raw results ────────────────────────────────────────────────
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    raw_path = RESULTS_DIR / f"jobs_{timestamp}.json"
    raw_path.write_text(json.dumps(matched_jobs, indent=2))
    logger.info(f"  Results saved: {raw_path}")

    # ── 5. User reviews jobs ───────────────────────────────────────────────
    if not matched_jobs:
        logger.warning("No jobs matched your criteria. Try lowering min_match_score in config.yaml.")
        return results

    approved_jobs = review_jobs(matched_jobs)
    results["approved_jobs"] = len(approved_jobs)

    if not approved_jobs:
        logger.info("No jobs approved. Exiting.")
        return results

    if args.search_only:
        logger.info("--search-only flag set. Stopping before outreach.")
        return results

    # ── 6. Sync approved jobs to Notion ───────────────────────────────────
    notion_map: dict[str, str] = {}
    if not args.no_notion:
        logger.info("Syncing to Notion...")
        notion_map = sync_jobs_to_notion(approved_jobs, config)
        if notion_map:
            results["notion_synced"] = True
            logger.info(f"  Synced {len(notion_map)} jobs to Notion")
            # Mark as "Applying"
            for job in approved_jobs:
                page_id = notion_map.get(job.get("id", ""))
                if page_id:
                    update_job_status(page_id, "Applying")

    # ── 7. Find contacts & draft outreach ─────────────────────────────────
    logger.info("Finding contacts at target companies...")
    all_drafts: list[dict] = []

    for job in approved_jobs:
        company = job.get("company", "")
        logger.info(f"  Finding contacts @ {company}...")
        contacts = find_contacts_for_job(job)
        logger.info(f"    {len(contacts)} contacts found")
        for contact in contacts:
            draft = draft_outreach(job, contact, resume, config)
            all_drafts.append(draft)

    results["total_drafts"] = len(all_drafts)
    logger.info(f"Total outreach drafts: {len(all_drafts)}")

    # ── 8. User approves outreach ──────────────────────────────────────────
    if not all_drafts:
        logger.info("No contacts found for outreach.")
        print_summary(results)
        return results

    approved_drafts = review_outreach(all_drafts)
    results["approved_drafts"] = len(approved_drafts)

    # ── 9. Send approved outreach ──────────────────────────────────────────
    smtp_cfg = {
        "host": os.environ.get("SMTP_HOST", "smtp.gmail.com"),
        "port": int(os.environ.get("SMTP_PORT", "465")),
        "user": os.environ.get("SMTP_USER", config.get("outreach", {}).get("your_email", "")),
        "pass": os.environ.get("SMTP_PASS", ""),
    }

    for draft in approved_drafts:
        contact = draft.get("contact", {})
        linkedin_url = contact.get("linkedin_url", "")
        job_info = draft.get("job", {})

        logger.info(
            f"  Sending outreach to {contact.get('name','')} "
            f"@ {job_info.get('company','')}"
        )

        # Send email if we have an address
        to_email = contact.get("email", "")
        if to_email and smtp_cfg["user"] and smtp_cfg["pass"]:
            sent = send_email(
                draft,
                smtp_host=smtp_cfg["host"],
                smtp_port=smtp_cfg["port"],
                smtp_user=smtp_cfg["user"],
                smtp_pass=smtp_cfg["pass"],
                to_email=to_email,
            )
            if sent:
                logger.info(f"    Email sent to {to_email}")

        # Open LinkedIn InMail in browser
        if linkedin_url:
            open_linkedin_inmail(linkedin_url, draft.get("inmail_body", ""))

        # Update Notion outreach status
        job = draft.get("job", {})
        job_id = next(
            (j.get("id", "") for j in approved_jobs if j.get("title") == job.get("title")
             and j.get("company") == job.get("company")),
            "",
        )
        page_id = notion_map.get(job_id)
        if page_id:
            update_outreach_status(page_id, "Sent")

    # ── 10. Save full session ──────────────────────────────────────────────
    session_path = RESULTS_DIR / f"session_{timestamp}.json"
    session_data = {
        "timestamp": timestamp,
        "approved_jobs": approved_jobs,
        "approved_drafts": approved_drafts,
        "results": results,
    }
    session_path.write_text(json.dumps(session_data, indent=2))
    results["saved_path"] = str(session_path)
    logger.info(f"Session saved: {session_path}")

    print_summary(results)
    return results


# ── Entry point ────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Job Search Automation Agent")
    parser.add_argument("--config", default="config.yaml", help="Path to config file")
    parser.add_argument("--search-only", action="store_true",
                        help="Stop after job review (no outreach)")
    parser.add_argument("--outreach-only", type=str, metavar="SESSION_JSON",
                        help="Load a previous session JSON and only do outreach")
    parser.add_argument("--no-notion", action="store_true",
                        help="Skip Notion sync")
    args = parser.parse_args()

    config = load_config(args.config)

    if args.outreach_only:
        _run_outreach_only(args.outreach_only, config, args)
        return

    run_pipeline(config, args)


def _run_outreach_only(session_path: str, config: dict, args: argparse.Namespace):
    """Re-run outreach phase from a saved session JSON."""
    data = json.loads(Path(session_path).read_text())
    approved_jobs = data.get("approved_jobs", [])
    resume_text = load_resume(config)
    resume = parse_resume(resume_text)

    all_drafts = []
    for job in approved_jobs:
        contacts = find_contacts_for_job(job)
        for contact in contacts:
            all_drafts.append(draft_outreach(job, contact, resume, config))

    approved_drafts = review_outreach(all_drafts)
    logger.info(f"{len(approved_drafts)} outreach messages approved and sent.")


if __name__ == "__main__":
    main()
