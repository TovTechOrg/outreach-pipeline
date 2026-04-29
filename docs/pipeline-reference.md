# Pipeline Reference

Complete reference for all scripts, data files, and checkpoints.

---

## Data directory (`data/`)

| File | Created by | Description |
|------|-----------|-------------|
| `raw_orgs.csv` | You (input) | Source prospect list |
| `filtered_orgs.csv` | step1 | Scored and tiered prospects |
| `enriched_prospects.csv` | step4 | Full prospect list with email addresses and template hints |
| `emails_checkpoint.json` | step2 | Resume state for email scraping |
| `search_checkpoint.json` | step2b | Resume state for DuckDuckGo email search |
| `personalize_checkpoint.json` | step5 | Resume state for AI personalization |

All long-running scripts save checkpoints so they can be safely interrupted and resumed.

---

## Scripts

### `config.py`
Central configuration. Edit this before running anything else.
- `SENDER_EMAIL`, `NOTIFY_EMAIL` — pulled from env vars, with defaults
- `DAILY_LIMIT`, `DAILY_INITIAL`, `DAILY_FOLLOWUP` — sending limits
- `FOLLOWUP1_DAYS`, `FOLLOWUP2_DAYS`, `FOLLOWUP3_DAYS` — follow-up cadence
- `SIG_FULL`, `SIG_MID`, `SIG_SLIM` — email signatures

---

### `step1_filter.py`
**Input:** `data/raw_orgs.csv`
**Output:** `data/filtered_orgs.csv`

Reads your raw prospect CSV and:
- Removes duplicates by email address
- Scores each org based on relevance signals (keywords in org name, country, project type)
- Assigns a tier: Tier1 (high), Tier2 (medium), Tier3 (general)
- Writes the filtered and scored list

Customize the scoring logic in `step1_filter.py` to match your relevance criteria.

---

### `step2_scrape_parallel.py`
**Input:** `data/filtered_orgs.csv`
**Output:** updates `email` column in CSV

Discovers email addresses from org websites using parallel scraping (15 workers by default). Checkpoint-safe — can be interrupted and resumed.

```bash
python step2_scrape_parallel.py --workers 15
```

---

### `step2b_search_emails.py`
**Input:** `data/filtered_orgs.csv` (orgs with no email after step2)
**Output:** updates `email` column in CSV

Fallback: finds contact emails via DuckDuckGo search for orgs where website scraping failed.

```bash
python step2b_search_emails.py
```

---

### `step4_generate_output.py`
**Input:** `data/filtered_orgs.csv`
**Output:** `data/enriched_prospects.csv`

Generates the final prospect list with all fields needed by the email sending step. Only processes orgs that have an email address.

```bash
python step4_generate_output.py
```

---

### `step5_personalize.py`
**Input:** `data/enriched_prospects.csv`
**Output:** updates personalization columns in CSV + Firebase backup

Uses Gemini Flash to extract org-specific fields that personalize emails:
- **Tier 1:** `specific_achievement` + `their_population` (references real project achievements)
- **Tier 2/3:** `relevant_theme` (thematic alignment)

```bash
# Process Tier 1 (most important, run first)
GEMINI_API_KEY=your_key python step5_personalize.py --tier 1

# Process Tier 2
GEMINI_API_KEY=your_key python step5_personalize.py --tier 2

# Process Tier 3
GEMINI_API_KEY=your_key python step5_personalize.py --tier 3

# Limit number of orgs (useful for testing)
GEMINI_API_KEY=your_key python step5_personalize.py --tier 1 --limit 100
```

Cost: ~$0.002 per org with Gemini Flash. Checkpoint is saved after every org.

> **Important:** Close `enriched_prospects.csv` in Excel before running — file lock will cause a crash.

---

### `step0_import.py`
**Input:** `data/enriched_prospects.csv`
**Output:** writes to Firestore `contacts` collection

One-time bulk import of prospects to Firebase. Idempotent — safe to run multiple times.

```bash
python step0_import.py
```

Only imports orgs that have an email address. Deduplicates by email.

---

### `step6_send_emails.py`
**Input:** Firestore `contacts` collection
**Output:** sends emails, writes events and stats to Firestore

The daily sender. Each run:
1. Checks if already sent today (idempotency)
2. Sends follow-up emails to contacts due for follow-up
3. Sends initial emails to new contacts (up to `DAILY_INITIAL`)
4. Logs every event to Firestore

```bash
# Default campaign (main)
python step6_send_emails.py

# Specific campaign
python step6_send_emails.py --campaign your_campaign

# Dry run (no emails sent, just preview)
python step6_send_emails.py --dry-run
```

---

### `step7_ai_replies.py`
**Input:** Gmail inbox (checks for new replies)
**Output:** Firestore `pending_replies`, sends approval email to `NOTIFY_EMAIL`

Detects inbound replies using Gmail API, uses Gemini to generate a draft response, and emails you an approval link. Clicking "Approve" queues the reply for sending; clicking "Skip" marks it as ignored.

```bash
python step7_ai_replies.py
```

---

### `step_summary.py`
Sends a daily stats email to `NOTIFY_EMAIL` with totals, today's activity, and a link to the dashboard.

---

### `gmail_auth.py`
One-time Gmail OAuth2 setup. Run this locally to generate `pipeline/token.json`.

```bash
python gmail_auth.py
```

---

### `test_system.py`
Health check: runs 23 tests covering Firebase connectivity, Gmail API, email rendering, and config validation.

```bash
python test_system.py
```

---

## Input CSV schema (`data/raw_orgs.csv`)

The minimum required columns:

| Column | Required | Description |
|--------|----------|-------------|
| `org_name` | Yes | Organization name |
| `email` | No | Contact email (discovered by step2 if missing) |
| `website` | No | Website URL (used by step2 for email scraping) |
| `country` | No | Country code (used for tier scoring) |
| `city` | No | City |

Additional columns are passed through unchanged and can be used in step1 scoring logic.

Additional columns in your source CSV are passed through unchanged and can be used in step1 scoring logic.

---

## Enriched prospects schema (`data/enriched_prospects.csv`)

Output of step4, input to step5 and step0. Includes all raw columns plus:

| Column | Added by | Description |
|--------|---------|-------------|
| `tier` | step1 | Tier1 / Tier2 / Tier3 |
| `score` | step1 | Numeric relevance score |
| `template_hint` | step4 | Email template variant hint |
| `specific_achievement` | step5 | AI-extracted org achievement (Tier1) |
| `their_population` | step5 | AI-extracted target population (Tier1) |
| `relevant_theme` | step5 | AI-extracted theme (Tier2/3) |

---

## Checkpoint files

All checkpoints are JSON files in `data/`. To resume a crashed run, just re-run the script — it picks up where it left off.

To restart from scratch, delete the relevant checkpoint file:

```bash
rm data/emails_checkpoint.json     # restart email scraping
rm data/personalize_checkpoint.json  # restart AI personalization
```
