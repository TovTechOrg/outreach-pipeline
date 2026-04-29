# /setup

Interactive setup wizard for the BizDev Outreach Pipeline. Guides you through every external service, credential, and config — one step at a time.

---

## What this skill does

Walks you through the complete one-time setup:
1. Collect your project details (org name, sender email, etc.)
2. Gmail API — OAuth2 credentials and token
3. Firebase — project creation and service account
4. Google Gemini — API key for AI personalization
5. Cloudflare Pages — dashboard deployment
6. GitHub Actions — secrets for daily automation
7. First pipeline run — verify everything works

---

## Step 0 — Gather info

Start by asking the user (all at once, in a numbered list):

> Before we begin, I need a few details:
>
> 1. **Your name** — used in email signatures
> 2. **Your email address** — the Gmail account you'll send from
> 3. **Your notification email** — where to receive daily summaries and reply alerts (can be the same)
> 4. **Your organization name** — shown in signatures (e.g. "Acme Org")
> 5. **Your website** — shown in signatures (e.g. "acme.org")
> 6. **Your portfolio/product URL** — the link inserted in outreach emails (e.g. "https://portfolio.acme.org")
> 7. **GitHub repo URL** — where this project will be hosted (e.g. "https://github.com/you/bizdev-outreach")
> 8. **Preferred dashboard subdomain** — becomes `https://<name>.pages.dev` (e.g. "bizdev-acme")
>
> Answer all 8 in one message (numbered list is fine).

Wait for the user to answer. Save all answers as variables for later steps. Then proceed to Step 1.

---

## Step 1 — Update config.py

Once you have the user's details, edit `pipeline/config.py`:

- `SENDER_EMAIL` default → user's sender email
- `NOTIFY_EMAIL` default → user's notification email
- `SIG_FULL`, `SIG_MID`, `SIG_SLIM` → replace `Your Name`, `Your Org`, `yourorg.com`, `you@yourorg.com` with real values
- `PORTFOLIO_URL` → user's portfolio/product URL

Also edit `cloudflare/wrangler.toml`:
```toml
name = "<user's preferred dashboard subdomain>"
```

Tell the user:
> ✓ `pipeline/config.py` and `wrangler.toml` updated with your details.

Then move to Step 2.

---

## Step 2 — Gmail API setup

Tell the user:

> **Step 2 of 6 — Gmail API**
>
> You need to create a Google Cloud project and enable the Gmail API so the pipeline can send emails on your behalf. This takes about 5 minutes.
>
> **Do these steps in your browser:**
>
> 1. Go to **https://console.cloud.google.com** → create a new project (e.g. "bizdev-outreach")
> 2. **APIs & Services → Library** → search "Gmail API" → **Enable**
> 3. **APIs & Services → OAuth consent screen**:
>    - User Type: **External**
>    - App name: anything (e.g. "Outreach Pipeline")
>    - Add your sender email as a **test user**
>    - Scopes: add `gmail.send` and `gmail.readonly`
>    - Save and continue
> 4. **Credentials → Create Credentials → OAuth client ID**
>    - Application type: **Desktop app**
>    - Download the JSON file
> 5. Save the file as `pipeline/credentials.json` in this project
>
> Tell me when `pipeline/credentials.json` is in place.

Wait for confirmation. Then run the OAuth flow:

```bash
cd pipeline && python gmail_auth.py
```

Tell the user:
> A browser window just opened. Sign in with your sender email and click **Allow**. Come back here when you see "Authentication successful".

After they confirm, verify:

```bash
ls pipeline/token.json
```

Then test:

```bash
cd pipeline && python test_send.py
```

If it succeeds:
> ✓ Gmail API connected. `token.json` saved.

Move to Step 3. If it fails, diagnose before continuing.

---

## Step 3 — Firebase setup

Tell the user:

> **Step 3 of 6 — Firebase Firestore**
>
> Firebase stores all prospects, sent emails, and tracking events. Free tier is more than enough.
>
> **Do these steps in your browser:**
>
> 1. Go to **https://console.firebase.google.com** → **Add project**
>    - Disable Google Analytics
> 2. **Build → Firestore Database → Create database**
>    - Mode: **production**
>    - Region: pick one close to you (e.g. `europe-west1`, `us-central`)
> 3. **Project settings** (gear icon) → **Service accounts** → **Generate new private key** → download JSON
> 4. Save the file as `pipeline/firebase-service-account.json` in this project
>
> Tell me when `pipeline/firebase-service-account.json` is in place.

Wait for confirmation. Then deploy rules and indexes:

```bash
npm install -g firebase-tools
firebase login
firebase use --add
firebase deploy --only firestore:rules,firestore:indexes
```

For `firebase use --add`, tell the user to select the project they just created.

Verify the connection:

```bash
cd pipeline && python test_system.py 2>&1 | grep -i firebase
```

If it passes:
> ✓ Firebase connected. Rules and indexes deployed.

Move to Step 4.

---

## Step 4 — Gemini API key

Tell the user:

> **Step 4 of 6 — Google Gemini AI**
>
> Gemini personalizes each email with org-specific context. Free tier is sufficient for testing.
>
> 1. Go to **https://aistudio.google.com**
> 2. Click **Get API key → Create API key** → copy it
>
> Tell me your Gemini API key.

Wait for the key. Add it to `.env`:

```
GEMINI_API_KEY=<key>
```

Test it:

```bash
cd pipeline && GEMINI_API_KEY=<key> python -c "
from google import genai
client = genai.Client(api_key='<key>')
r = client.models.generate_content(model='gemini-2.5-flash', contents='Say hello in one word')
print('Connected:', r.text)
"
```

If it works:
> ✓ Gemini API connected. Key saved to `.env`.

Move to Step 5.

---

## Step 5 — Cloudflare Pages dashboard

Tell the user:

> **Step 5 of 6 — Cloudflare Dashboard**
>
> The live dashboard shows emails sent, replies, clicks, and daily stats. Runs free on Cloudflare Pages.
>
> **Do these steps in your browser:**
>
> 1. Go to **https://dash.cloudflare.com/profile/api-tokens**
> 2. **Create Token** → use **"Edit Cloudflare Workers"** template → copy the token
> 3. Go to **https://dash.cloudflare.com** → copy your **Account ID** from the right sidebar
>
> Tell me: `Token: <token>  Account: <account-id>`

Wait for credentials. Authenticate and deploy:

```bash
CLOUDFLARE_API_TOKEN=<token> npx wrangler whoami
CLOUDFLARE_API_TOKEN=<token> npx wrangler pages project create <dashboard-subdomain>
CLOUDFLARE_API_TOKEN=<token> npx wrangler pages deploy cloudflare \
  --project-name <dashboard-subdomain> --commit-dirty=true
```

Add the Firebase service account as a Pages secret:

```bash
cat pipeline/firebase-service-account.json | \
  CLOUDFLARE_API_TOKEN=<token> npx wrangler pages secret put FIREBASE_SERVICE_ACCOUNT \
  --project-name <dashboard-subdomain>
```

Update `.env`:
```
TRACKING_BASE_URL=https://<dashboard-subdomain>.pages.dev
```

Tell the user the URL and ask them to confirm it loads. Then:
> ✓ Dashboard live at `https://<dashboard-subdomain>.pages.dev`

Move to Step 6.

---

## Step 6 — GitHub Actions

Tell the user:

> **Step 6 of 6 — GitHub Actions (daily automation)**
>
> GitHub Actions runs the pipeline automatically twice per day — no server needed.
>
> First, push the repo:

```bash
git remote add origin <github-repo-url>
git add .
git commit -m "Initial setup"
git push -u origin main
```

> Then go to your repo on GitHub → **Settings → Secrets and variables → Actions** and add these 5 secrets:

Walk through each one:

**`FIREBASE_SERVICE_ACCOUNT`** — run `cat pipeline/firebase-service-account.json` and paste the output.

**`GMAIL_TOKEN_JSON`** — run `cat pipeline/token.json` and paste the output.

**`SENDER_EMAIL`** — the sender email from Step 0.

**`TRACKING_BASE_URL`** — `https://<dashboard-subdomain>.pages.dev`

**`NOTIFY_EMAIL`** — the notification email from Step 0.

After user confirms all 5 secrets are added, trigger a dry run:

> In your GitHub repo → **Actions** tab → **"TovPlay Outreach Pipeline"** → **Run workflow** → mode: `dry-run` → **Run workflow**

Ask them to confirm the green checkmark. If it fails, check the logs.

> ✓ GitHub Actions configured. Pipeline runs automatically on weekdays at 07:23 UTC and 11:47 UTC.

---

## Step 7 — First pipeline run

Tell the user:

> **Setup complete! Here's how to run the full pipeline for the first time:**

```bash
cd pipeline

# 1. Filter your prospects (edit step1_filter.py first to match your data)
python step1_filter.py

# 2. Scrape email addresses (20–40 min for large lists)
python step2_scrape_parallel.py --workers 15

# 3. Generate enriched prospect list
python step4_generate_output.py

# 4. AI personalization — start with a small batch to test
GEMINI_API_KEY=<key> python step5_personalize.py --tier 1 --limit 50

# 5. Import to Firebase
python step0_import.py

# 6. Preview emails before sending
python step6_send_emails.py --dry-run
```

> Review the dry-run output. When you're happy with the emails, push to GitHub — the Actions workflow takes it from there.

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Gmail auth fails | Re-run `python gmail_auth.py`; check test users in OAuth consent screen |
| Firebase connection error | Verify `firebase-service-account.json` is valid JSON; check Firestore is enabled |
| Cloudflare deploy error | Check token has "Edit Cloudflare Workers" permission; verify account ID |
| GitHub Actions fail | Check all 5 secrets are set; read the Actions log for the specific error |
| Gemini quota error | Switch to a paid plan or reduce `--limit` in step5 |

Full docs: [docs/setup-gmail.md](../../docs/setup-gmail.md) · [docs/setup-firebase.md](../../docs/setup-firebase.md) · [docs/setup-cloudflare.md](../../docs/setup-cloudflare.md) · [docs/setup-github-actions.md](../../docs/setup-github-actions.md)
