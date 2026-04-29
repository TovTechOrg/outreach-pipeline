# Gmail API Setup

The pipeline sends emails through the Gmail API using OAuth2. This is a one-time setup.

---

## Step 1: Create a Google Cloud project and enable the Gmail API

**Using the CLI (recommended):**

Install the [Google Cloud CLI](https://cloud.google.com/sdk/docs/install) if you haven't, then:

```bash
# Authenticate
gcloud auth login

# Create a new project
gcloud projects create bizdev-outreach --name="BizDev Outreach"

# Set it as the active project
gcloud config set project bizdev-outreach

# Enable the Gmail API
gcloud services enable gmail.googleapis.com
```

**Alternative — browser:**
Go to [console.cloud.google.com](https://console.cloud.google.com), create a new project, then go to **APIs & Services → Library** → search "Gmail API" → **Enable**.

---

## Step 2: Create OAuth 2.0 credentials

This step requires the browser — there is no CLI for creating OAuth Desktop credentials.

1. Go to [console.cloud.google.com](https://console.cloud.google.com) → **APIs & Services → OAuth consent screen**:
   - User Type: **External**
   - App name: anything (e.g. `Outreach Pipeline`)
   - Add your sender email as a **test user**
   - Scopes: add `https://www.googleapis.com/auth/gmail.send` and `https://www.googleapis.com/auth/gmail.readonly`
   - Save and continue through all screens
2. Go to **APIs & Services → Credentials → Create Credentials → OAuth client ID**:
   - Application type: **Desktop app**
   - Download the JSON file
3. Save the downloaded file as `pipeline/credentials.json`

---

## Step 3: Run the auth flow

```bash
cd pipeline
python gmail_auth.py
```

This opens a browser window. Log in with your sender Gmail account and click **Allow**. On success, `pipeline/token.json` is created.

> **Note:** `token.json` contains your OAuth refresh token. Keep it secret and never commit it.

---

## Step 4: Verify

```bash
cd pipeline
python test_send.py
```

This sends a test email to `NOTIFY_EMAIL`. Check your inbox.

---

## Step 5: Add to GitHub Actions secrets

**Using the CLI (recommended):**

Install the [GitHub CLI](https://cli.github.com) if you haven't, then from the project root:

```bash
gh secret set GMAIL_TOKEN_JSON < pipeline/token.json
```

**Alternative — browser:**
Go to your GitHub repo → **Settings → Secrets and variables → Actions → New repository secret**, name it `GMAIL_TOKEN_JSON`, and paste the contents of `pipeline/token.json`.

---

## Gmail sending limits

| Account type | Daily limit |
|---|---|
| Free Gmail | ~500 emails/day |
| Google Workspace | ~2,000 emails/day |

The pipeline defaults to 20 emails/day (`DAILY_LIMIT` in `config.py`), well within free tier limits.

---

## Troubleshooting

**"Token has been expired or revoked"**
Run `python gmail_auth.py` again, then update the secret: `gh secret set GMAIL_TOKEN_JSON < pipeline/token.json`

**"Access blocked: app has not completed Google verification"**
While in test mode, only users listed as test users can authorize. Add yourself under OAuth consent screen → Test users.

**"quota exceeded"**
You hit the daily sending limit. Reduce `DAILY_LIMIT` in `config.py` or upgrade to Google Workspace.
