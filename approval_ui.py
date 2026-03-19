"""
approval_ui.py
──────────────
Interactive terminal UI for reviewing jobs, approving resume tweaks,
and approving / editing outreach messages before they are sent.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Optional


# ── Colour helpers ─────────────────────────────────────────────────────────
def _c(text: str, code: str) -> str:
    if not sys.stdout.isatty():
        return text
    return f"\033[{code}m{text}\033[0m"

def green(t): return _c(t, "32")
def yellow(t): return _c(t, "33")
def red(t): return _c(t, "31")
def bold(t): return _c(t, "1")
def cyan(t): return _c(t, "36")
def magenta(t): return _c(t, "35")
def dim(t): return _c(t, "2")


def _hr(char="─", width=70):
    print(dim(char * width))


def _ask(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    try:
        val = input(f"{prompt}{suffix}: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return default
    return val if val else default


def _confirm(prompt: str, default: bool = True) -> bool:
    suffix = "[Y/n]" if default else "[y/N]"
    answer = _ask(f"{prompt} {suffix}").lower()
    if not answer:
        return default
    return answer.startswith("y")


# ── Job review screen ──────────────────────────────────────────────────────
def review_jobs(jobs: list[dict]) -> list[dict]:
    """
    Show each job to the user and let them decide:
        a — Apply (keep)
        s — Skip
        v — View full description
        q — Quit reviewing
    Returns the list of jobs the user wants to apply to.
    """
    approved = []
    print()
    print(bold("═" * 70))
    print(bold(f"  JOB REVIEW — {len(jobs)} matches found"))
    print(bold("═" * 70))

    for i, job in enumerate(jobs, 1):
        score = job.get("match_score", 0)
        score_color = green if score >= 75 else (yellow if score >= 50 else red)
        title = job.get("title", "Unknown Title")
        company = job.get("company", "Unknown Company")
        location = job.get("location", "")
        source = job.get("source", "")
        salary = job.get("salary", "")
        matched = job.get("matched_skills", [])
        missing = job.get("missing_skills", [])
        tweaks = job.get("resume_tweaks", [])
        apply_url = job.get("apply_url", "")

        print()
        _hr()
        print(f"  {bold(f'[{i}/{len(jobs)}]')}  {bold(title)}  @  {cyan(company)}")
        print(f"  Match Score: {score_color(str(score) + '%')}   |   Source: {dim(source)}   |   Location: {location}")
        if salary:
            print(f"  Salary: {green(salary)}")
        if matched:
            print(f"  {green('✓ Skills matched:')} {', '.join(matched[:8])}")
        if missing:
            print(f"  {yellow('⚠ Skills to add:')} {', '.join(missing[:5])}")

        if tweaks:
            print(f"\n  {bold('Resume Suggestions:')}")
            for t in tweaks[:3]:
                print(f"    • {t}")

        print(f"\n  {dim('Apply URL:')} {apply_url}")
        print()

        while True:
            action = _ask(
                f"  Action? {green('(a)')}pply  {red('(s)')}kip  {yellow('(v)')}iew desc  {dim('(q)')}uit",
                default="a",
            ).lower()
            if action == "q":
                print(yellow("\n  Stopped reviewing. Returning approved jobs so far."))
                return approved
            if action == "v":
                desc = job.get("description", "(No description available)")
                print(f"\n{dim(desc[:2000])}\n")
                continue
            if action == "a":
                approved.append({**job, "user_action": "apply"})
                print(green("  ✓ Added to your apply list."))
                break
            if action == "s":
                print(dim("  Skipped."))
                break

    print()
    print(bold(f"  Review complete. {len(approved)} jobs selected for application."))
    _hr("═")
    return approved


# ── Outreach approval screen ───────────────────────────────────────────────
def review_outreach(drafts: list[dict]) -> list[dict]:
    """
    Show each outreach draft (email + InMail) and let the user:
        a  — Approve as-is
        e  — Edit before approving
        s  — Skip this contact
        q  — Quit outreach review
    Returns approved drafts with status='approved'.
    """
    approved = []
    print()
    print(bold("═" * 70))
    print(bold(f"  OUTREACH REVIEW — {len(drafts)} drafts to review"))
    print(bold("═" * 70))

    for i, draft in enumerate(drafts, 1):
        contact = draft.get("contact", {})
        job_info = draft.get("job", {})
        name = contact.get("name", "Unknown")
        headline = contact.get("headline", "")
        linkedin_url = contact.get("linkedin_url", "")
        source_label = {
            "recruiter": "👔 Recruiter",
            "hiring_manager": "🎯 Hiring Manager",
            "recently_hired": "🆕 Recently Hired",
            "role_post": "📢 Posted About Role",
            "google_search": "🔍 Found via Search",
            "linkedin_search": "💼 LinkedIn Search",
        }.get(contact.get("source", ""), contact.get("source", ""))

        print()
        _hr()
        print(f"  {bold(f'[{i}/{len(drafts)}]')}  {bold(name)}  —  {dim(headline)}")
        print(f"  Type: {cyan(source_label)}   |   Company: {job_info.get('company','')}")
        print(f"  LinkedIn: {dim(linkedin_url)}")
        print()
        print(bold("  ── EMAIL ──"))
        print(f"  Subject: {yellow(draft.get('email_subject',''))}")
        print()
        for line in draft.get("email_body", "").splitlines():
            print(f"  {line}")
        print()
        print(bold("  ── LINKEDIN INMAIL ──"))
        for line in draft.get("inmail_body", "").splitlines():
            print(f"  {line}")
        print()

        while True:
            action = _ask(
                f"  Action? {green('(a)')}pprove  {yellow('(e)')}dit  {red('(s)')}kip  {dim('(q)')}uit",
                default="a",
            ).lower()
            if action == "q":
                print(yellow("\n  Stopped outreach review."))
                return approved
            if action == "s":
                print(dim("  Skipped."))
                break
            if action == "e":
                print(f"\n  {bold('Edit email subject')} (press Enter to keep current):")
                new_subject = _ask("  Subject", default=draft["email_subject"])
                print(f"\n  {bold('Edit email body')} (type END on a new line to finish):")
                lines = []
                while True:
                    try:
                        line = input()
                    except EOFError:
                        break
                    if line.strip().upper() == "END":
                        break
                    lines.append(line)
                new_body = "\n".join(lines) if lines else draft["email_body"]
                draft = {
                    **draft,
                    "email_subject": new_subject,
                    "email_body": new_body,
                }
                print(green("  ✓ Draft updated."))
                continue
            if action == "a":
                approved.append({**draft, "status": "approved"})
                print(green("  ✓ Approved for sending."))
                break

    print()
    print(bold(f"  Outreach review complete. {len(approved)} messages approved."))
    _hr("═")
    return approved


# ── Summary report ─────────────────────────────────────────────────────────
def print_summary(results: dict):
    """Print a final session summary."""
    print()
    print(bold("═" * 70))
    print(bold("  SESSION SUMMARY"))
    print(bold("═" * 70))
    print(f"  Jobs scraped   : {results.get('total_jobs', 0)}")
    print(f"  Jobs matched   : {results.get('matched_jobs', 0)}")
    print(f"  Jobs approved  : {results.get('approved_jobs', 0)}")
    print(f"  Outreach drafted : {results.get('total_drafts', 0)}")
    print(f"  Outreach approved: {results.get('approved_drafts', 0)}")
    if results.get("notion_synced"):
        print(f"  Synced to Notion : {green('Yes')}")
    print()
    saved = results.get("saved_path", "")
    if saved:
        print(f"  {dim('Results saved to:')} {saved}")
    print(bold("═" * 70))
    print()
