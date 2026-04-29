# GitHub Actions Setup

GitHub Actions runs the pipeline automatically twice per day. No server needed.

---

## Prerequisites

Install the [GitHub CLI](https://cli.github.com) — it lets you set secrets and trigger runs without touching the browser:

```bash
# Install (macOS/Linux)
brew install gh        # macOS
sudo apt install gh    # Ubuntu/Debian

# Authenticate
gh auth login
```

---

## How it works

The workflow at `.github/workflows/outreach.yml` triggers:
- **07:23 UTC** — primary run (weekdays)
- **11:47 UTC** — backup run (idempotency check prevents double-sending)
- **Manual trigger** — on demand with a `mode` selector

Each run: checks out the repo → installs dependencies → writes credentials from secrets → sends emails → sends daily summary → cleans up credentials.

---

## Step 1: Push your repo to GitHub

```bash
git init
git remote add origin https://github.com/your-org/your-repo.git
git add .
git commit -m "Initial commit"
git push -u origin main
```

---

## Step 2: Add secrets

**Using the CLI (recommended):**

```bash
# Firebase service account (from setup-firebase.md)
gh secret set FIREBASE_SERVICE_ACCOUNT < pipeline/firebase-service-account.json

# Gmail OAuth token (from setup-gmail.md)
gh secret set GMAIL_TOKEN_JSON < pipeline/token.json

# Simple string secrets
gh secret set SENDER_EMAIL --body "you@yourdomain.com"
gh secret set TRACKING_BASE_URL --body "https://your-project.pages.dev"
gh secret set NOTIFY_EMAIL --body "notify@youremail.com"

# Optional — only needed for step7 (AI reply handler)
gh secret set GEMINI_API_KEY --body "your_gemini_api_key"
```

**Alternative — browser:**
Go to your GitHub repo → **Settings → Secrets and variables → Actions → New repository secret** and add each secret manually.

---

## Step 3: Verify with a dry run

**Using the CLI (recommended):**

```bash
gh workflow run outreach.yml --field mode=dry-run
```

Then watch the run:

```bash
gh run watch
```

**Alternative — browser:**
Go to **Actions** tab → select **"TovPlay Outreach Pipeline"** → **Run workflow** → mode: `dry-run` → **Run workflow**.

---

## Customizing the schedule

Edit `.github/workflows/outreach.yml`:

```yaml
on:
  schedule:
    - cron: '23 7 * * 1-5'   # weekdays 07:23 UTC
    - cron: '47 11 * * 1-5'  # backup run
```

Cron syntax: `minute hour day-of-month month day-of-week`. GitHub Actions runs on UTC.

---

## Manual trigger options

```bash
gh workflow run outreach.yml --field mode=both        # step6 + step7 (default)
gh workflow run outreach.yml --field mode=step6-only  # emails only
gh workflow run outreach.yml --field mode=step7-only  # AI reply handler only
gh workflow run outreach.yml --field mode=dry-run     # preview without sending
```

---

## Adding a new campaign to the workflow

Add a new step in `outreach.yml`:

```yaml
- name: Step 6 — My campaign
  if: ${{ github.event.inputs.mode != 'step7-only' && github.event.inputs.mode != 'dry-run' }}
  env:
    SENDER_EMAIL:      ${{ secrets.SENDER_EMAIL }}
    TRACKING_BASE_URL: ${{ secrets.TRACKING_BASE_URL }}
  run: |
    cd pipeline
    python step6_send_emails.py --campaign my_campaign_name
```

---

## Secret rotation

When your Gmail token expires, refresh it and update the secret in one command:

```bash
cd pipeline && python gmail_auth.py
gh secret set GMAIL_TOKEN_JSON < pipeline/token.json
```

---

## Troubleshooting

**Workflow not running on schedule**
GitHub skips runs if the repo has no activity for 60 days. Wake it up:
```bash
gh workflow run outreach.yml --field mode=dry-run
```

**"firebase-service-account.json not found"**
The secret is missing or malformed. Check with `gh secret list` and re-set if needed.

**"invalid_grant" in Gmail logs**
OAuth token expired. Refresh it:
```bash
cd pipeline && python gmail_auth.py && gh secret set GMAIL_TOKEN_JSON < pipeline/token.json
```
