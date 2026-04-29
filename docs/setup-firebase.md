# Firebase / Firestore Setup

Firestore is the database that stores all prospects, tracking events, and campaign stats.

---

## Step 1: Create a Firebase project

1. Go to [console.firebase.google.com](https://console.firebase.google.com)
2. Click **Add project**
3. Give it a name (e.g. `bizdev-outreach`)
4. Disable Google Analytics (not needed)
5. Click **Create project**

---

## Step 2: Enable Firestore

1. In the Firebase console, go to **Build → Firestore Database**
2. Click **Create database**
3. Choose **Start in production mode** (we'll apply rules next)
4. Pick a region close to you (e.g. `europe-west1` for Europe)

---

## Step 3: Deploy security rules and indexes

Install the Firebase CLI if you haven't:

```bash
npm install -g firebase-tools
firebase login
```

From the project root:

```bash
firebase use --add  # select your project
firebase deploy --only firestore:rules,firestore:indexes
```

This applies `firestore.rules` (restricts writes to authenticated service accounts) and `firestore.indexes.json` (composite indexes for efficient queries).

---

## Step 4: Create a service account

The pipeline needs a service account key to write to Firestore from Python and from GitHub Actions.

1. Go to [console.firebase.google.com](https://console.firebase.google.com) → **Project settings** (gear icon)
2. Click the **Service accounts** tab
3. Click **Generate new private key**
4. Download the JSON file → save as `pipeline/firebase-service-account.json`

> **Keep this file secret.** It grants write access to your entire Firestore database.

---

## Step 5: Add to GitHub Actions secrets

Copy the full contents of the service account JSON:

```bash
cat pipeline/firebase-service-account.json
```

Go to GitHub → **Settings → Secrets → Actions → New repository secret**:

- Name: `FIREBASE_SERVICE_ACCOUNT`
- Value: the full JSON content

---

## Step 6: Verify locally

```bash
cd pipeline
python test_system.py
```

Look for "Firebase connection" in the output — it should show a green check.

---

## Firestore data model

```
contacts/                       ← main prospect database
  {contact_id}
    org_name, email, tier
    status: pending | initial_sent | followup1_sent | ... | replied | bounced
    last_contacted (timestamp)
    initial_sent_at, followup1_sent_at, ...
    specific_achievement, their_population, relevant_theme  ← AI fields
    campaign (string, default "erasmus")

events/                         ← event log
  {event_id}
    contact_id, org_name, event_type
    created_at (timestamp)
    meta (object, varies by event type)

stats/global                    ← cumulative totals (1 document)
  total, sent, replied, clicked, bounced
  initial_sent, followup1_sent, followup2_sent
  by_tier: { Tier1: {...}, Tier2: {...}, Tier3: {...} }

stats_daily/{YYYY-MM-DD}        ← daily breakdown
  initial_sent, followup1_sent, replied, clicked, bounced

tracking_tokens/                ← click tracking
  {token}
    target_url, contact_id, event_type
    created_at, clicked_at (nullable)

pending_replies/                ← AI reply drafts awaiting approval
  {token}
    contact_id, org_name, original_message
    draft_reply, approve_url, skip_url
    status: pending | approved | skipped
```

Custom campaigns use prefixed collections:
- `{campaign}_stats/global`
- `{campaign}_stats_daily/{date}`
- `{campaign}_events/`

---

## Cost

Firestore free tier (Spark plan) provides:
- 50,000 document reads/day
- 20,000 document writes/day
- 1 GB storage

A typical day running 20 emails generates ~100–200 reads and writes. The free tier covers most use cases. Upgrade to the Blaze (pay-as-you-go) plan only if you exceed these limits.
