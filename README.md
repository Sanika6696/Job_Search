# Job Search Automation Agent

An end-to-end automated job search pipeline that:

1. **Scrapes 9+ job boards** for your target roles
2. **Scores each job** against your resume (0–100% match)
3. **Suggests resume tweaks** for missing keywords
4. **Prompts you to apply** — you pick which jobs to pursue
5. **Finds employees** at target companies (recruiters, hiring managers, recently hired)
6. **Drafts personalised outreach** (email + LinkedIn InMail)
7. **Sends only after your approval** — nothing goes out without a green light
8. **Syncs everything to Notion** for tracking

---

## Target Job Titles

| Title | Boards Searched |
|---|---|
| Data Analyst | Indeed, LinkedIn, Glassdoor, BuiltIn, Wellfound, SimplyHired, ZipRecruiter, Remotive, Workable |
| Growth Analyst | ↑ same |
| Marketing Analyst | ↑ same |
| Product Analyst | ↑ same |
| Lifecycle Marketing | ↑ same |
| Digital Marketing Analyst | ↑ same |

---

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Add your resume

Place your resume as `resume.pdf` in this folder, **or** paste the text directly into `config.yaml` under `resume.raw_text`.

### 3. Configure

Edit `config.yaml`:

```yaml
resume:
  path: "resume.pdf"          # ← your resume

outreach:
  your_name: "Sanika Sharma"
  your_linkedin_url: "https://linkedin.com/in/yourprofile"
  your_email: "you@email.com"

search:
  min_match_score: 60         # only show jobs with ≥60% match
```

### 4. Set environment variables (optional)

```bash
cp .env.example .env
# Fill in NOTION_API_KEY and SMTP credentials
```

### 5. Run

```bash
# Full pipeline (search → review → outreach → Notion)
python main.py

# Search & review only (no outreach)
python main.py --search-only

# Load a previous session and re-run outreach
python main.py --outreach-only results/session_20240318_120000.json

# Skip Notion sync
python main.py --no-notion
```

---

## How the Match Score Works

| Component | Max Points |
|---|---|
| Skills overlap (resume vs JD) | 60 |
| Boost keyword hits | 20 |
| Title proximity to target roles | 20 |
| **Total** | **100** |

Jobs with negative keywords (e.g. "10+ years", "Director") are automatically filtered out.

---

## Outreach Flow

```
Find contacts → Draft email + InMail → You review → You approve → Send
```

- **Recruiters**: Get a concise introduction email
- **Hiring Managers**: Get a role-specific pitch
- **Recently Hired Peers**: Get a warm peer-to-peer message
- **LinkedIn InMail**: Opened directly in your browser for you to send

---

## File Structure

```
Job_Search/
├── main.py               # Standalone runner
├── claude_agent.py       # Claude Agent SDK entry point (uses Indeed MCP)
├── config.yaml           # All settings
├── resume_parser.py      # PDF/text resume loading + skill extraction + scoring
├── job_scraper.py        # Multi-board scraper (LinkedIn, Glassdoor, BuiltIn, etc.)
├── employee_finder.py    # Contact finder (LinkedIn people search + Google)
├── outreach_generator.py # Email + InMail draft generation + sending
├── notion_tracker.py     # Notion database sync
├── approval_ui.py        # Interactive terminal UI for review/approval
├── requirements.txt
├── .env.example
└── results/              # Auto-created; stores session JSONs
```

---

## Notion Setup (Optional)

1. Create a Notion integration at [notion.so/my-integrations](https://www.notion.so/my-integrations)
2. Copy the **Internal Integration Token** → set as `NOTION_API_KEY` in `.env`
3. Create a blank Notion page and share it with your integration
4. Copy the page ID from the URL and paste it into the setup call:

```python
from notion_tracker import create_job_database
db_id = create_job_database(parent_page_id="your-page-id")
# Paste db_id into config.yaml → notion.database_id
```

5. Set `notion.enabled: true` in `config.yaml`

---

## Privacy & Safety

- **Nothing sends without your approval.** Every email and InMail is shown for review first.
- Scraping respects `robots.txt` spirit — random delays are built in between requests.
- Your `.env` and `resume.pdf` are git-ignored and never committed.
