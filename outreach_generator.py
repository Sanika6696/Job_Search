"""
outreach_generator.py
─────────────────────
Generates personalised email and LinkedIn InMail drafts for each contact.
All messages are staged for USER APPROVAL before sending.
"""

from __future__ import annotations

import json
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# ── Template bank ──────────────────────────────────────────────────────────

EMAIL_TEMPLATES = {
    "recruiter": """\
Subject: {job_title} Role at {company} — {your_name}

Hi {contact_name},

I came across the {job_title} opening at {company} and I'm genuinely excited \
about it — the work your team is doing in {company_domain} aligns closely with \
my background in {candidate_domain}.

I have {yoe} of experience in {top_skills}, and I'd love to bring that to {company}. \
I've attached my resume for your reference.

Would you be open to a quick 15-minute chat? Happy to work around your schedule.

{signature}
""",

    "hiring_manager": """\
Subject: Interested in the {job_title} Role — {your_name}

Hi {contact_name},

I noticed you're building out the {dept} team at {company} and saw the {job_title} \
opening. I've spent {yoe} working on {top_skills} and have a track record of \
{key_achievement}.

I'm particularly drawn to {company} because of {company_reason}. I'd be thrilled \
to contribute to what your team is building.

Would you be open to a brief conversation? I'd love to learn more about the role.

{signature}
""",

    "peer_recently_hired": """\
Subject: Fellow {job_title_hint} — Would Love to Connect

Hi {contact_name},

I noticed you recently joined {company} in a similar role — congrats! I'm currently \
exploring a move into the {dept} space and came across the {job_title} opening at \
{company}.

I'd love to hear a bit about your experience transitioning in. Would you be open to \
a quick 10-minute chat? No pressure at all — just genuinely curious about the team \
and culture.

{signature}
""",

    "generic_inmail": """\
Hi {contact_name},

I came across the {job_title} role at {company} and was really impressed by the \
team's work in {company_domain}. With my background in {top_skills}, I think I \
could add real value.

I'd love to connect and learn more — would you be open to a quick chat?

Best,
{your_name}
""",
}

LINKEDIN_INMAIL_TEMPLATES = {
    "recruiter": """\
Hi {contact_name}, I came across the {job_title} opening at {company} and I'm very \
interested. I have {yoe} in {top_skills} — happy to share my resume. Would love to \
connect!
""",
    "hiring_manager": """\
Hi {contact_name}, I noticed you lead the {dept} team at {company}. I'm excited \
about the {job_title} role — my background in {top_skills} maps closely to what \
you're building. Can we find 15 minutes to chat?
""",
    "default": """\
Hi {contact_name}, I'm very interested in the {job_title} role at {company}. \
My background in {top_skills} aligns well, and I'd love to learn more about the \
team. Would you be open to a quick connect?
""",
}


# ── Helpers ────────────────────────────────────────────────────────────────

def _detect_contact_type(contact: dict) -> str:
    headline = contact.get("headline", "").lower()
    source = contact.get("source", "")
    if "recruiter" in headline or "talent" in headline:
        return "recruiter"
    if any(kw in headline for kw in ["head of", "director", "vp ", "manager"]):
        return "hiring_manager"
    if source == "recently_hired":
        return "peer_recently_hired"
    return "generic_inmail"


def _company_domain(job: dict) -> str:
    """Guess what the company does from the job description snippet."""
    desc = (job.get("description", "") + " " + job.get("title", "")).lower()
    if "saas" in desc or "software" in desc:
        return "SaaS / software"
    if "e-commerce" in desc or "ecommerce" in desc or "retail" in desc:
        return "e-commerce"
    if "fintech" in desc or "finance" in desc or "banking" in desc:
        return "fintech"
    if "health" in desc or "medical" in desc:
        return "healthtech"
    if "marketing" in desc:
        return "data-driven marketing"
    return "data and analytics"


def _dept_from_title(title: str) -> str:
    title_lower = title.lower()
    if "marketing" in title_lower or "lifecycle" in title_lower or "growth" in title_lower:
        return "Marketing"
    if "product" in title_lower:
        return "Product"
    return "Data & Analytics"


def _top_skills_str(resume: dict) -> str:
    skills = resume.get("skills", [])[:5]
    return ", ".join(s.title() for s in skills) if skills else "data analysis and SQL"


def _yoe_str(resume: dict) -> str:
    yoe = resume.get("years_of_experience", 0)
    if yoe >= 5:
        return f"{yoe}+ years"
    if yoe >= 2:
        return f"{yoe} years"
    return "several years"


# ── Draft generation ───────────────────────────────────────────────────────

def draft_outreach(
    job: dict,
    contact: dict,
    resume: dict,
    config: dict,
) -> dict:
    """
    Generate both an email draft and a LinkedIn InMail draft for approval.
    Returns a dict with keys: email_subject, email_body, inmail_body, contact, job.
    """
    outreach_cfg = config.get("outreach", {})
    your_name = outreach_cfg.get("your_name", "Your Name")
    your_linkedin = outreach_cfg.get("your_linkedin_url", "")
    your_email = outreach_cfg.get("your_email", "")
    signature_template = outreach_cfg.get("email_signature", "{your_name}\n{your_linkedin_url}")
    signature = signature_template.format(
        your_name=your_name, your_linkedin_url=your_linkedin
    )

    contact_type = _detect_contact_type(contact)
    contact_name = contact.get("name", "").split()[0] if contact.get("name") else "there"
    job_title = job.get("title", "this role")
    company = job.get("company", "your company")
    dept = _dept_from_title(job_title)
    top_skills = _top_skills_str(resume)
    yoe = _yoe_str(resume)
    company_domain = _company_domain(job)
    candidate_domain = dept
    key_achievement = "turning complex data into clear business decisions"
    company_reason = f"the innovative work in {company_domain}"

    # Fill email template
    email_tmpl = EMAIL_TEMPLATES.get(contact_type, EMAIL_TEMPLATES["generic_inmail"])
    email_filled = email_tmpl.format(
        job_title=job_title,
        company=company,
        contact_name=contact_name,
        your_name=your_name,
        yoe=yoe,
        top_skills=top_skills,
        dept=dept,
        company_domain=company_domain,
        candidate_domain=candidate_domain,
        key_achievement=key_achievement,
        company_reason=company_reason,
        job_title_hint=job_title,
        signature=signature,
    )

    # Split subject from body
    lines = email_filled.strip().splitlines()
    subject_line = ""
    body_lines = lines
    if lines and lines[0].startswith("Subject:"):
        subject_line = lines[0].replace("Subject:", "").strip()
        body_lines = lines[2:]  # skip blank line after subject
    email_body = "\n".join(body_lines)

    # Fill InMail template
    inmail_tmpl = LINKEDIN_INMAIL_TEMPLATES.get(
        contact_type, LINKEDIN_INMAIL_TEMPLATES["default"]
    )
    inmail_body = inmail_tmpl.format(
        job_title=job_title,
        company=company,
        contact_name=contact_name,
        your_name=your_name,
        yoe=yoe,
        top_skills=top_skills,
        dept=dept,
    ).strip()

    return {
        "contact": contact,
        "job": {"title": job_title, "company": company, "apply_url": job.get("apply_url", "")},
        "email_subject": subject_line,
        "email_body": email_body,
        "inmail_body": inmail_body,
        "status": "pending_approval",  # must be approved before sending
    }


# ── Sending (only after approval) ─────────────────────────────────────────

def send_email(
    draft: dict,
    smtp_host: str,
    smtp_port: int,
    smtp_user: str,
    smtp_pass: str,
    to_email: str,
) -> bool:
    """Send an approved email draft via SMTP. Returns True on success."""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = draft["email_subject"]
    msg["From"] = smtp_user
    msg["To"] = to_email
    msg.attach(MIMEText(draft["email_body"], "plain"))
    try:
        with smtplib.SMTP_SSL(smtp_host, smtp_port) as server:
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_user, [to_email], msg.as_string())
        logger.info(f"Email sent to {to_email}")
        return True
    except Exception as e:
        logger.error(f"Failed to send email to {to_email}: {e}")
        return False


def open_linkedin_inmail(profile_url: str, message: str):
    """
    Opens a pre-filled LinkedIn InMail in the browser.
    (LinkedIn doesn't expose a public API for sending InMail programmatically.)
    """
    import webbrowser
    from urllib.parse import urlencode
    # LinkedIn compose URL trick
    params = {"body": message}
    url = f"{profile_url.rstrip('/')}/?{urlencode(params)}"
    webbrowser.open(url)
    logger.info(f"Opened LinkedIn profile for InMail: {profile_url}")
