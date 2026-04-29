# Firebase / Firestore Setup

Firestore is the database that stores all prospects, tracking events, and campaign stats.

---

## Step 1: Create a Firebase project

**Using the CLI (recommended):**

Install [Firebase CLI](https://firebase.google.com/docs/cli) if you haven't:

```bash
npm install -g firebase-tools
firebase login
```

Then create the project:

```bash
firebase projects:create bizdev-outreach --display-name "BizDev Outreach"
```

**Alternative — browser:**
Go to [console.firebase.google.com](https://console.firebase.google.com) → **Add project**, give it a name, disable Google Analytics, and click **Create project**.

---

## Step 2: Enable Firestore

**Using the CLI (recommended):**

```bash
# Link your local project to Firebase
firebase use bizdev-outreach

# Create the Firestore database
# Replace europe-west1 with a region close to you
# Other options: us-central, asia-east1
firebase firestore:databases:create --location=europe-west1
```

**Alternative — browser:**
In the Firebase console → **Build → Firestore Database → Create database** → production mode → pick a region.

---

## Step 3: Deploy security rules and indexes

```bash
firebase deploy --only firestore:rules,firestore:indexes
```

This applies `firestore.rules` (restricts writes to authenticated service accounts) and `firestore.indexes.json` (composite indexes for efficient queries).

---

## Step 4: Create a service account key

The pipeline needs a service account key to write to Firestore from Python and from GitHub Actions.

**Using the CLI (recommended):**

```bash
PROJECT_ID=bizdev-outreach

# Find the Firebase Admin service account (created automatically with the project)
SA_EMAIL=$(gcloud iam service-accounts list \
  --project=$PROJECT_ID \
  --filter="displayName:firebase-adminsdk" \
  --format="value(email)")

echo "Service account: $SA_EMAIL"

# Download the key
gcloud iam service-accounts keys create pipeline/firebase-service-account.json \
  --iam-account=$SA_EMAIL \
  --project=$PROJECT_ID
```

**Alternative — browser:**
Go to [console.firebase.google.com](https://console.firebase.google.com) → **Project settings** (gear icon) → **Service accounts** tab → **Generate new private key** → download the JSON and save it as `pipeline/firebase-service-account.json`.

> **Keep this file secret.** It grants write access to your entire Firestore database.

---

## Step 5: Add to GitHub Actions secrets

**Using the CLI (recommended):**

```bash
gh secret set FIREBASE_SERVICE_ACCOUNT < pipeline/firebase-service-account.json
```

**Alternative — browser:**
Go to GitHub → **Settings → Secrets → Actions → New repository secret**, name it `FIREBASE_SERVICE_ACCOUNT`, and paste the file contents.

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
    campaign (string, default "main")

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
