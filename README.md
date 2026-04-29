# BizDev Outreach Pipeline

A fully automated B2B outreach engine built for Erasmus+ partnership prospecting. Discovers contacts from public databases, personalizes emails with AI, sends daily via Gmail, handles follow-ups, tracks engagement, and presents a live dashboard — all with zero manual work after setup.

**Stack:** Python · Firebase Firestore · Gmail API · Google Gemini AI · Cloudflare Pages · GitHub Actions

---

## Recommended: guided setup with Claude Code

The fastest way to get up and running is with the built-in setup wizard. If you have [Claude Code](https://claude.ai/code) installed:

```bash
# Open this project in Claude Code, then run:
/setup
```

The `/setup` skill walks you through every step interactively — it asks for your details, edits the config files, runs the auth flows, deploys the dashboard, and configures GitHub Actions secrets, one step at a time. No need to read the docs first.

> Don't have Claude Code? Follow the [manual setup instructions](#quick-start) below.

---

## What it does

```
Public database (CSV)
       ↓ step1 — filter & score by relevance (Tier 1 / 2 / 3)
       ↓ step2 — discover websites & scrape email addresses
       ↓ step4 — generate enriched prospect list
       ↓ step5 — AI personalization per org (Gemini Flash)
       ↓ step0 — import to Firebase Firestore
       ↓ step6 — daily send via Gmail API (GitHub Actions, 2×/day)
       ↓ step7 — detect replies → AI drafts → human approval gate
       ↓ Dashboard — live stats on Cloudflare Pages
```

- **Multi-tier campaigns:** Tier 1 (high relevance) → 4 emails, Tier 2 → 3 emails, Tier 3 → 2 emails
- **Follow-up cadence:** Day 3 → Day 7 → Day 14 (breakup)
- **Idempotency:** double-send protection even with backup cron jobs
- **Click & open tracking:** token-based redirects logged to Firestore
- **AI reply handler:** detects inbound replies, generates draft responses, routes for approval
- **Multiple campaigns:** each campaign gets isolated Firestore collections and dashboard tab

---

## Quick start

### 1. Clone and install

```bash
git clone https://github.com/your-org/bizdev-outreach.git
cd bizdev-outreach
pip install -r requirements.txt
```

### 2. Set up external services (one-time)

| Service | Purpose | Guide |
|---------|---------|-------|
| Gmail API | Send emails | [docs/setup-gmail.md](docs/setup-gmail.md) |
| Firebase Firestore | Prospect database & tracking | [docs/setup-firebase.md](docs/setup-firebase.md) |
| Google Gemini | AI personalization | Free key at [aistudio.google.com](https://aistudio.google.com) |
| Cloudflare Pages | Live dashboard | [docs/setup-cloudflare.md](docs/setup-cloudflare.md) |
| GitHub Actions | Daily automation | [docs/setup-github-actions.md](docs/setup-github-actions.md) |

### 3. Configure environment

```bash
cp .env.example .env
# Edit .env with your real values
```

### 4. Prepare your prospect data

Place your source CSV in `data/raw_orgs.csv`. The pipeline expects columns:
`org_name`, `country`, `city`, `website` (optional), `email` (optional), and any enrichment fields you want to filter on.

See [docs/pipeline-reference.md](docs/pipeline-reference.md) for the full data schema.

### 5. Run the pipeline

```bash
cd pipeline

# Step 1: filter and tier your prospects
python step1_filter.py

# Step 2: discover websites and scrape emails (can take 20–40 min)
python step2_scrape_parallel.py --workers 15

# Step 4: generate enriched_prospects.csv
python step4_generate_output.py

# Step 5: AI personalization (needs GEMINI_API_KEY in env)
GEMINI_API_KEY=your_key python step5_personalize.py --tier 1
GEMINI_API_KEY=your_key python step5_personalize.py --tier 2

# Step 0: import to Firebase
python step0_import.py

# Push to GitHub → Actions take over from here
git push
```

### 6. Automate with GitHub Actions

Add the required secrets to your GitHub repo settings (Settings → Secrets → Actions):

| Secret | Value |
|--------|-------|
| `FIREBASE_SERVICE_ACCOUNT` | Full JSON from Firebase console |
| `GMAIL_TOKEN_JSON` | JSON from `pipeline/token.json` after OAuth |
| `SENDER_EMAIL` | Gmail address used for sending |
| `TRACKING_BASE_URL` | Your Cloudflare Pages URL |
| `NOTIFY_EMAIL` | Email to receive reply notifications |
| `GEMINI_API_KEY` | Google AI Studio key |

See [docs/setup-github-actions.md](docs/setup-github-actions.md) for full instructions.

---

## Project structure

```
├── pipeline/                   # Python scripts
│   ├── config.py               # Central configuration (edit this first)
│   ├── step0_import.py         # Import CSV → Firestore
│   ├── step1_filter.py         # Filter & tier prospects
│   ├── step2_scrape_parallel.py # Parallel email scraping
│   ├── step2b_search_emails.py # DuckDuckGo email search fallback
│   ├── step4_generate_output.py # Generate enriched_prospects.csv
│   ├── step5_personalize.py    # Gemini AI personalization
│   ├── step6_send_emails.py    # Daily email sender
│   ├── step7_ai_replies.py     # AI reply handler
│   ├── step_summary.py         # Daily report email
│   ├── gmail_auth.py           # Gmail OAuth2 setup
│   └── test_system.py          # Health check (23 tests)
│
├── cloudflare/                 # Dashboard (Cloudflare Pages)
│   ├── index.html              # SPA dashboard UI
│   ├── _worker.js              # Pages entry point
│   ├── wrangler.toml           # Wrangler config
│   └── functions/
│       ├── api/stats.js        # GET /api/stats
│       ├── api/contacts.js     # GET /api/contacts
│       ├── track/c/[token].js  # Click tracking redirect
│       ├── approve/[token].js  # AI reply approval
│       └── skip/[token].js     # AI reply rejection
│
├── templates/                  # Email copy templates
│   ├── email_tier1.md          # Tier 1 email copy
│   ├── email_tier2.md          # Tier 2 email copy
│   ├── email_tier3.md          # Tier 3 email copy
│   └── discovery_call_script.md
│
├── .github/workflows/
│   └── outreach.yml            # GitHub Actions (runs 2×/day)
│
├── firestore.rules             # Firestore security rules
├── firestore.indexes.json      # Composite indexes
├── firebase.json               # Firebase CLI config
├── requirements.txt            # Python dependencies
└── .env.example                # Environment variable template
```

---

## Configuration

All pipeline settings live in [pipeline/config.py](pipeline/config.py). The most important ones:

| Setting | Default | Description |
|---------|---------|-------------|
| `SENDER_EMAIL` | env var | Gmail address to send from |
| `NOTIFY_EMAIL` | env var | Where to receive reply notifications |
| `DAILY_LIMIT` | 20 | Max emails per day (Gmail free tier safe) |
| `DAILY_INITIAL` | 12 | New initial emails per day |
| `DAILY_FOLLOWUP` | 0 | Follow-up emails per day (0 = disabled) |
| `FOLLOWUP1_DAYS` | 3 | Days before first follow-up |
| `FOLLOWUP2_DAYS` | 7 | Days before second follow-up |
| `FOLLOWUP3_DAYS` | 14 | Days before breakup email |
| `GEMINI_MODEL` | gemini-2.5-flash | Gemini model for personalization |

---

## Campaigns

The system supports multiple named campaigns, each with isolated data and stats. The default campaign is `erasmus` (Erasmus+ organizations). You can add custom campaigns for any audience.

See [docs/campaigns.md](docs/campaigns.md) for full instructions on creating a new campaign.

To run step6 for a specific campaign:

```bash
python step6_send_emails.py --campaign your_campaign_name
```

---

## Dashboard

The live dashboard shows sent/replied/clicked/bounced by tier, daily activity charts, and recent event feed.

Deploy with Wrangler:

```bash
npx wrangler pages deploy cloudflare --project-name your-project-name --commit-dirty=true
```

Protected with HTTP Basic Auth (configure username/password in `cloudflare/index.html`).

See [docs/setup-cloudflare.md](docs/setup-cloudflare.md).

---

## Cost

| Component | Cost |
|-----------|------|
| Gmail API | Free (up to 500 emails/day via free Gmail, 2000/day via Workspace) |
| Firebase Firestore | Free tier covers ~1M reads/day |
| Gemini Flash | ~$0.002 per org for personalization |
| Cloudflare Pages | Free |
| GitHub Actions | Free (2000 min/month on free tier) |

For 10,000 orgs: Gemini personalization ~$20. Everything else free.

---

## Documentation

- [Pipeline Reference](docs/pipeline-reference.md) — all scripts, data schema, checkpoints
- [Gmail Setup](docs/setup-gmail.md) — OAuth2 step by step
- [Firebase Setup](docs/setup-firebase.md) — Firestore project and service account
- [Cloudflare Setup](docs/setup-cloudflare.md) — dashboard deployment
- [GitHub Actions Setup](docs/setup-github-actions.md) — automation secrets and schedule
- [Campaigns Guide](docs/campaigns.md) — creating and running custom campaigns

---

## License

MIT
