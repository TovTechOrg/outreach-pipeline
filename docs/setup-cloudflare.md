# Cloudflare Pages Dashboard Setup

The live dashboard is a single-page app deployed to Cloudflare Pages with serverless Workers functions that query Firestore in real time.

---

## Prerequisites

- A Cloudflare account (free tier is sufficient)
- Node.js installed locally
- Firebase service account JSON (from [setup-firebase.md](setup-firebase.md))

---

## Step 1: Authenticate with Wrangler

Install Wrangler:

```bash
npm install -g wrangler
```

**Using the CLI (recommended):**

```bash
wrangler login
```

This opens a browser once for OAuth — after that all Wrangler commands run without browser interaction.

**Alternative — API token (for headless/CI environments):**
Go to [dash.cloudflare.com/profile/api-tokens](https://dash.cloudflare.com/profile/api-tokens) → **Create Token** → use the **"Edit Cloudflare Workers"** template. Then set the token as an environment variable:

```bash
export CLOUDFLARE_API_TOKEN=your_token_here
```

---

## Step 2: Create the Pages project

```bash
npx wrangler pages project create your-project-name
```

Replace `your-project-name` with whatever you want (e.g. `bizdev-outreach`). This becomes your dashboard URL: `https://your-project-name.pages.dev`.

---

## Step 3: Configure the Wrangler file

Edit `cloudflare/wrangler.toml`:

```toml
name = "your-project-name"
compatibility_date = "2024-09-23"
```

---

## Step 4: Add Firebase credentials as a secret

```bash
cat pipeline/firebase-service-account.json | \
  npx wrangler pages secret put FIREBASE_SERVICE_ACCOUNT \
  --project-name your-project-name
```

---

## Step 5: Configure dashboard auth

The dashboard is protected with HTTP Basic Auth. Edit `cloudflare/index.html` and update the credentials near the top:

```javascript
const DASHBOARD_USER = 'admin';
const DASHBOARD_PASS = 'your-secure-password';
```

---

## Step 6: Deploy

```bash
npx wrangler pages deploy cloudflare --project-name your-project-name --commit-dirty=true
```

Your dashboard will be live at `https://your-project-name.pages.dev`.

---

## Step 7: Update pipeline config

Set `TRACKING_BASE_URL` in `.env`:

```
TRACKING_BASE_URL=https://your-project-name.pages.dev
```

---

## Dashboard features

- **Campaign switcher** — toggle between multiple campaigns
- **Totals** — sent, replied, clicked, bounced (with by-tier breakdown)
- **Daily chart** — 30-day rolling activity timeline
- **Recent events** — live feed of latest activity (replied, clicked, bounced)

---

## Endpoints

| Endpoint | Function |
|----------|---------|
| `GET /api/stats?campaign=main` | Campaign statistics |
| `GET /api/contacts?campaign=main` | Paginated contact list |
| `GET /track/c/:token` | Click tracking redirect |
| `GET /approve/:token` | Approve AI reply draft |
| `GET /skip/:token` | Skip AI reply draft |

---

## Custom domain (optional)

Add a custom domain via CLI:

```bash
npx wrangler pages domain add your-domain.com --project-name your-project-name
```

Then update `TRACKING_BASE_URL` accordingly.

**Alternative — browser:**
Cloudflare dashboard → **Workers & Pages → your-project → Custom domains** → add domain.

---

## Redeploying after changes

```bash
npx wrangler pages deploy cloudflare --project-name your-project-name --commit-dirty=true
```
