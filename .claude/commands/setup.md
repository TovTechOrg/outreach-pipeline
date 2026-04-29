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

First, check which CLIs are available:

```bash
gcloud version 2>/dev/null && echo "gcloud: ok" || echo "gcloud: not installed"
```

**If gcloud is available**, run the setup automatically:

```bash
gcloud auth login
gcloud projects create bizdev-outreach --name="BizDev Outreach"
gcloud config set project bizdev-outreach
gcloud services enable gmail.googleapis.com
```

Tell the user:
> ✓ Google Cloud project created and Gmail API enabled via CLI.

**If gcloud is NOT available**, tell the user:

> **Manual step needed (browser, ~3 min):**
>
> 1. Go to **https://console.cloud.google.com** → create a new project (e.g. "bizdev-outreach")
> 2. **APIs & Services → Library** → search "Gmail API" → **Enable**
>
> Tell me when done.

---

Next, regardless of which path was taken, the OAuth credentials must be created in the browser (no CLI alternative exists for this):

Tell the user:

> **One browser step needed to create OAuth credentials:**
>
> 1. Go to **https://console.cloud.google.com** → **APIs & Services → OAuth consent screen**
>    - User Type: **External** → App name: anything → add your email as a **test user** → Scopes: `gmail.send` + `gmail.readonly` → save
> 2. **Credentials → Create Credentials → OAuth client ID**
>    - Application type: **Desktop app** → download the JSON file
> 3. Save the file as `pipeline/credentials.json` in this project
>
> Tell me when `pipeline/credentials.json` is in place.

Wait for confirmation. Then run the OAuth flow:

```bash
cd pipeline && python gmail_auth.py
```

Tell the user:
> A browser window just opened. Sign in with your sender email and click **Allow**. Come back here when you see "Authentication successful".

After they confirm, verify and test:

```bash
ls pipeline/token.json && cd pipeline && python test_send.py
```

If it succeeds:
> ✓ Gmail API connected. `token.json` saved.

Move to Step 3. If it fails, diagnose before continuing.

---

## Step 3 — Firebase setup

Check which CLIs are available:

```bash
firebase --version 2>/dev/null && echo "firebase: ok" || echo "firebase: not installed"
gcloud version 2>/dev/null && echo "gcloud: ok" || echo "gcloud: not installed"
```

**If firebase CLI is available**, run:

```bash
# Install if needed
npm install -g firebase-tools

firebase login
firebase projects:create bizdev-outreach --display-name "BizDev Outreach"
firebase use bizdev-outreach
firebase firestore:databases:create --location=europe-west1
firebase deploy --only firestore:rules,firestore:indexes
```

Tell the user to choose a region if asked. After deploy succeeds, continue to the service account step.

**If firebase CLI is NOT available**, tell the user:

> **Manual steps needed (browser, ~5 min):**
>
> 1. Go to **https://console.firebase.google.com** → **Add project** → disable Google Analytics
> 2. **Build → Firestore Database → Create database** → production mode → pick a region
>
> Tell me when Firestore is created.

Wait for confirmation. Then regardless of path, deploy rules and indexes:

```bash
npm install -g firebase-tools
firebase login
firebase use --add  # select the project just created
firebase deploy --only firestore:rules,firestore:indexes
```

---

**Service account:** check if gcloud is available:

```bash
gcloud version 2>/dev/null && echo "gcloud: ok" || echo "gcloud: not installed"
```

**If gcloud is available**, download the key automatically:

```bash
PROJECT_ID=bizdev-outreach
SA_EMAIL=$(gcloud iam service-accounts list \
  --project=$PROJECT_ID \
  --filter="displayName~firebase-adminsdk" \
  --format="value(email)")
echo "Found service account: $SA_EMAIL"
gcloud iam service-accounts keys create pipeline/firebase-service-account.json \
  --iam-account=$SA_EMAIL --project=$PROJECT_ID
```

Tell the user:
> ✓ Service account key downloaded automatically.

**If gcloud is NOT available**, tell the user:

> **Manual step needed (browser, ~1 min):**
>
> 1. Go to **https://console.firebase.google.com** → **Project settings** (gear icon) → **Service accounts**
> 2. Click **Generate new private key** → download the JSON
> 3. Save it as `pipeline/firebase-service-account.json` in this project
>
> Tell me when the file is in place.

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
> This requires the browser (no CLI for key creation):
> 1. Go to **https://aistudio.google.com**
> 2. Click **Get API key → Create API key** → copy it
>
> Tell me your Gemini API key.

Wait for the key. Write it to `.env`:

```bash
echo "GEMINI_API_KEY=<key>" >> .env
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

Check if Wrangler is available:

```bash
npx wrangler --version 2>/dev/null && echo "wrangler: ok" || npm install -g wrangler
```

Authenticate (opens browser once for OAuth):

```bash
npx wrangler login
```

If the user is in a headless environment and can't use browser login, tell them:

> **Alternative — create an API token:**
> Go to **https://dash.cloudflare.com/profile/api-tokens** → **Create Token** → **"Edit Cloudflare Workers"** template → copy token.
> Then run: `export CLOUDFLARE_API_TOKEN=<token>`

Deploy:

```bash
npx wrangler pages project create <dashboard-subdomain>
npx wrangler pages deploy cloudflare --project-name <dashboard-subdomain> --commit-dirty=true
```

Add Firebase credentials as a Pages secret:

```bash
cat pipeline/firebase-service-account.json | \
  npx wrangler pages secret put FIREBASE_SERVICE_ACCOUNT \
  --project-name <dashboard-subdomain>
```

Update `.env`:

```bash
echo "TRACKING_BASE_URL=https://<dashboard-subdomain>.pages.dev" >> .env
```

Tell the user the URL and ask them to confirm it loads. Then:
> ✓ Dashboard live at `https://<dashboard-subdomain>.pages.dev`

Move to Step 6.

---

## Step 6 — GitHub Actions

Check if GitHub CLI is available:

```bash
gh --version 2>/dev/null && echo "gh: ok" || echo "gh: not installed"
```

Push the repo:

```bash
git remote add origin <github-repo-url>
git add .
git commit -m "Initial setup"
git push -u origin main
```

**If gh CLI is available**, set all secrets in one block:

```bash
gh secret set FIREBASE_SERVICE_ACCOUNT < pipeline/firebase-service-account.json
gh secret set GMAIL_TOKEN_JSON < pipeline/token.json
gh secret set SENDER_EMAIL --body "<sender email>"
gh secret set TRACKING_BASE_URL --body "https://<dashboard-subdomain>.pages.dev"
gh secret set NOTIFY_EMAIL --body "<notification email>"
```

Tell the user:
> ✓ All 5 GitHub Actions secrets set via CLI.

**If gh CLI is NOT available**, tell the user:

> **Manual steps needed (browser):**
> Go to your GitHub repo → **Settings → Secrets and variables → Actions → New repository secret** and add:
>
> | Secret | Value |
> |--------|-------|
> | `FIREBASE_SERVICE_ACCOUNT` | contents of `pipeline/firebase-service-account.json` |
> | `GMAIL_TOKEN_JSON` | contents of `pipeline/token.json` |
> | `SENDER_EMAIL` | `<sender email>` |
> | `TRACKING_BASE_URL` | `https://<dashboard-subdomain>.pages.dev` |
> | `NOTIFY_EMAIL` | `<notification email>` |
>
> Tell me when all 5 are added.

Then trigger a dry run:

**If gh CLI is available:**

```bash
gh workflow run outreach.yml --field mode=dry-run
gh run watch
```

**If not:**
> In your GitHub repo → **Actions** tab → **"TovPlay Outreach Pipeline"** → **Run workflow** → mode: `dry-run` → **Run workflow**. Tell me when it shows a green checkmark.

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
| Cloudflare deploy error | Check Wrangler is logged in (`npx wrangler whoami`); re-run `npx wrangler login` |
| GitHub Actions fail | Run `gh secret list` to verify all secrets exist; check Actions log for details |
| Gemini quota error | Reduce `--limit` in step5 or switch to a paid plan |
| `gh` not installed | Install from https://cli.github.com — saves significant time for secret management |
| `firebase` not installed | Run `npm install -g firebase-tools` |
| `gcloud` not installed | Install from https://cloud.google.com/sdk/docs/install |

Full docs: [docs/setup-gmail.md](../../docs/setup-gmail.md) · [docs/setup-firebase.md](../../docs/setup-firebase.md) · [docs/setup-cloudflare.md](../../docs/setup-cloudflare.md) · [docs/setup-github-actions.md](../../docs/setup-github-actions.md)
