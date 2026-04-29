# Cloudflare Pages Dashboard Setup

The live dashboard is a single-page app deployed to Cloudflare Pages with serverless Workers functions that query Firestore in real time.

---

## Prerequisites

- A Cloudflare account (free tier is sufficient)
- Node.js installed locally (for Wrangler CLI)
- Firebase service account JSON (from [setup-firebase.md](setup-firebase.md))

---

## Step 1: Install Wrangler

```bash
npm install -g wrangler
wrangler login
```

This opens a browser to authenticate with Cloudflare.

---

## Step 2: Create the Pages project

```bash
npx wrangler pages project create your-project-name
```

Replace `your-project-name` with whatever you want (e.g. `bizdev-outreach`). This becomes part of your dashboard URL: `https://your-project-name.pages.dev`.

---

## Step 3: Configure the Wrangler file

Edit `cloudflare/wrangler.toml`:

```toml
name = "your-project-name"
compatibility_date = "2024-09-23"
```

---

## Step 4: Add Firebase credentials as a secret

The Workers functions need Firebase credentials to query Firestore. Add them as a Pages secret:

```bash
# From the project root
cat pipeline/firebase-service-account.json | npx wrangler pages secret put FIREBASE_SERVICE_ACCOUNT --project-name your-project-name
```

Or via the Cloudflare dashboard:
1. Go to **Workers & Pages → your-project-name → Settings → Environment variables**
2. Add a secret named `FIREBASE_SERVICE_ACCOUNT` with the full JSON value

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

Set `TRACKING_BASE_URL` to your dashboard URL in `.env`:

```
TRACKING_BASE_URL=https://your-project-name.pages.dev
```

And update `PORTFOLIO_URL` in `pipeline/config.py` if you have a portfolio page to link to.

---

## Dashboard features

- **Campaign switcher** — toggle between multiple campaigns
- **Totals** — sent, replied, clicked, bounced (with by-tier breakdown)
- **Daily chart** — 30-day rolling activity timeline
- **Recent events** — live feed of latest activity (replied, clicked, bounced)

---

## Endpoints

All endpoints are serverless Workers functions in `cloudflare/functions/`:

| Endpoint | Function |
|----------|---------|
| `GET /api/stats?campaign=erasmus` | Campaign statistics |
| `GET /api/contacts?campaign=erasmus` | Paginated contact list |
| `GET /track/c/:token` | Click tracking redirect |
| `GET /approve/:token` | Approve AI reply draft |
| `GET /skip/:token` | Skip AI reply draft |

---

## Custom domain (optional)

1. In Cloudflare dashboard → **Workers & Pages → your-project → Custom domains**
2. Add your domain and follow the CNAME instructions
3. Update `TRACKING_BASE_URL` accordingly

---

## Redeploying after changes

Any time you change `cloudflare/index.html` or the Workers functions:

```bash
npx wrangler pages deploy cloudflare --project-name your-project-name --commit-dirty=true
```
