"""
resume_parser.py
────────────────
Loads the user's resume from PDF or raw text, extracts structured data,
and exposes a match-scoring function against a job description.
"""

from __future__ import annotations

import os
import re
import json
import math
from pathlib import Path
from typing import Optional


# ── Optional PDF extraction ────────────────────────────────────────────────
def _extract_pdf_text(path: str) -> str:
    try:
        import pdfplumber
        with pdfplumber.open(path) as pdf:
            return "\n".join(page.extract_text() or "" for page in pdf.pages)
    except ImportError:
        pass
    try:
        import PyPDF2
        with open(path, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            return "\n".join(
                page.extract_text() or "" for page in reader.pages
            )
    except ImportError:
        pass
    raise RuntimeError(
        "No PDF library found. Run: pip install pdfplumber  OR  pip install PyPDF2"
    )


def load_resume(config: dict) -> str:
    """Return raw resume text from PDF path or inline raw_text."""
    resume_cfg = config.get("resume", {})
    raw = resume_cfg.get("raw_text", "").strip()
    if raw:
        return raw
    path = resume_cfg.get("path", "resume.pdf")
    if os.path.exists(path):
        return _extract_pdf_text(path)
    raise FileNotFoundError(
        f"Resume not found at '{path}'. "
        "Either place resume.pdf in the project folder or paste text into "
        "config.yaml → resume.raw_text"
    )


# ── Keyword / skill extraction ─────────────────────────────────────────────
_COMMON_SKILLS = [
    "sql", "python", "r", "excel", "tableau", "power bi", "looker",
    "google analytics", "ga4", "mixpanel", "amplitude", "segment",
    "a/b testing", "experimentation", "cohort analysis", "funnel analysis",
    "retention", "segmentation", "email marketing", "crm", "salesforce",
    "hubspot", "marketo", "klaviyo", "braze", "iterable", "sendgrid",
    "dbt", "airflow", "spark", "bigquery", "redshift", "snowflake",
    "data storytelling", "stakeholder management", "product analytics",
    "growth marketing", "lifecycle marketing", "digital marketing",
    "seo", "sem", "paid media", "facebook ads", "google ads",
    "attribution", "ltv", "cac", "conversion rate optimisation",
    "machine learning", "statistics", "regression", "forecasting",
    "javascript", "html", "css", "api", "etl", "data pipeline",
    "agile", "scrum", "jira", "notion", "asana",
]


def extract_skills(text: str) -> list[str]:
    """Return list of recognised skills found in text (case-insensitive)."""
    text_lower = text.lower()
    return [skill for skill in _COMMON_SKILLS if skill in text_lower]


def extract_years_of_experience(text: str) -> int:
    """Rough heuristic: find the highest year count mentioned."""
    matches = re.findall(r"(\d+)\+?\s*years?", text, re.IGNORECASE)
    return max((int(m) for m in matches), default=0)


def parse_resume(resume_text: str) -> dict:
    """Return structured resume snapshot used for matching."""
    skills = extract_skills(resume_text)
    yoe = extract_years_of_experience(resume_text)
    return {
        "raw_text": resume_text,
        "skills": skills,
        "years_of_experience": yoe,
    }


# ── Match scoring ──────────────────────────────────────────────────────────
def score_job(
    job: dict,
    resume: dict,
    config: dict,
) -> dict:
    """
    Score a job dict against a parsed resume.

    Returns a copy of the job dict with added keys:
        match_score   (0-100)
        matched_skills
        missing_skills
        resume_tweaks  (list of suggested bullet-point edits)
    """
    jd = (
        job.get("description", "")
        + " "
        + job.get("title", "")
        + " "
        + job.get("requirements", "")
    ).lower()

    resume_skills = set(resume["skills"])
    jd_skills = set(extract_skills(jd))
    boost_kws = {kw.lower() for kw in config.get("boost_keywords", [])}
    negative_kws = {kw.lower() for kw in config.get("negative_keywords", [])}

    # ── Penalise deal-breakers ────────────────────────────────────────────
    for kw in negative_kws:
        if kw in jd:
            job = {**job, "match_score": 0, "matched_skills": [],
                   "missing_skills": [], "resume_tweaks": [],
                   "disqualifier": kw}
            return job

    # ── Skill overlap ─────────────────────────────────────────────────────
    matched = resume_skills & jd_skills
    missing = jd_skills - resume_skills

    skill_score = (len(matched) / max(len(jd_skills), 1)) * 60  # 60 pts max

    # ── Boost keyword bonus ───────────────────────────────────────────────
    boost_hits = boost_kws & {kw for kw in jd.split() if kw in boost_kws}
    boost_score = min(len(boost_hits) * 2, 20)                  # 20 pts max

    # ── Title proximity bonus ─────────────────────────────────────────────
    title_lower = job.get("title", "").lower()
    title_bonus = 20 if any(
        t.lower() in title_lower for t in [
            "data analyst", "growth analyst", "marketing analyst",
            "product analyst", "lifecycle", "digital marketing"
        ]
    ) else 0

    raw_score = skill_score + boost_score + title_bonus
    final_score = min(round(raw_score), 100)

    # ── Resume tweak suggestions ──────────────────────────────────────────
    tweaks = _suggest_tweaks(missing, jd)

    return {
        **job,
        "match_score": final_score,
        "matched_skills": sorted(matched),
        "missing_skills": sorted(missing),
        "resume_tweaks": tweaks,
    }


def _suggest_tweaks(missing_skills: set[str], jd: str) -> list[str]:
    """Generate specific bullet suggestions the user can add to their resume."""
    suggestions = []
    mapping = {
        "sql": "Add a bullet: 'Wrote complex SQL queries (joins, CTEs, window functions) to extract and analyse data across large datasets.'",
        "python": "Add a bullet: 'Built Python scripts for data cleaning, analysis, and automated reporting using pandas and numpy.'",
        "a/b testing": "Add a bullet: 'Designed and analysed A/B tests to drive conversion rate improvements.'",
        "google analytics": "Add a bullet: 'Tracked and reported on web performance metrics using Google Analytics (GA4).'",
        "tableau": "Add a bullet: 'Built interactive Tableau dashboards consumed by cross-functional stakeholders.'",
        "looker": "Add a bullet: 'Created Looker explores and dashboards to democratise self-serve analytics.'",
        "cohort analysis": "Add a bullet: 'Ran cohort analyses to measure user retention and lifetime value trends.'",
        "email marketing": "Add a bullet: 'Managed email marketing campaigns from segmentation through delivery and performance analysis.'",
        "salesforce": "Add a bullet: 'Used Salesforce CRM to track pipeline and analyse sales funnel conversion.'",
        "hubspot": "Add a bullet: 'Leveraged HubSpot for marketing automation, lead scoring, and campaign tracking.'",
        "dbt": "Add a bullet: 'Used dbt to build and test modular SQL transformation pipelines.'",
    }
    for skill in missing_skills:
        if skill in mapping:
            suggestions.append(mapping[skill])
        else:
            suggestions.append(
                f"Consider adding '{skill}' to your skills section or work bullets if you have relevant experience."
            )
    return suggestions[:5]  # cap at 5 suggestions per job
