# Gmail API Setup

The pipeline sends emails through the Gmail API using OAuth2. This is a one-time setup.

---

## Step 1: Create a Google Cloud project

1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Create a new project (e.g. `bizdev-outreach`)
3. In the left menu, go to **APIs & Services → Library**
4. Search for **Gmail API** and click **Enable**

---

## Step 2: Create OAuth 2.0 credentials

1. Go to **APIs & Services → Credentials**
2. Click **Create Credentials → OAuth client ID**
3. If prompted, configure the OAuth consent screen first:
   - User Type: **External**
   - App name: anything (e.g. `Outreach Pipeline`)
   - Add your sender email as a test user
   - Scopes: add `https://www.googleapis.com/auth/gmail.send` and `https://www.googleapis.com/auth/gmail.readonly`
4. Back in Credentials → Create OAuth client ID:
   - Application type: **Desktop app**
   - Name: anything
5. Download the JSON file → save it as `pipeline/credentials.json`

---

## Step 3: Run the auth flow

```bash
cd pipeline
python gmail_auth.py
```

This opens a browser window. Log in with your sender Gmail account and grant the requested permissions. On success, `token.json` is created in the `pipeline/` directory.

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

After the OAuth flow, copy the contents of `pipeline/token.json`:

```bash
cat pipeline/token.json
```

Go to your GitHub repo → **Settings → Secrets and variables → Actions → New repository secret**:

- Name: `GMAIL_TOKEN_JSON`
- Value: the full JSON content

The GitHub Actions workflow writes this back to `pipeline/token.json` at runtime.

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
Run `python gmail_auth.py` again to refresh the token, then update the `GMAIL_TOKEN_JSON` secret.

**"Access blocked: app has not completed Google verification"**
While in test mode, only users listed as test users can authorize. Add yourself under OAuth consent screen → Test users.

**"quota exceeded"**
You hit the daily sending limit. Reduce `DAILY_LIMIT` in `config.py` or upgrade to Google Workspace.
