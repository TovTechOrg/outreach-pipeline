# Campaigns Guide

The pipeline supports multiple named campaigns running in parallel, each with isolated data in Firestore and a separate tab in the dashboard.

---

## Default campaign

The default campaign is named `main`. All scripts use it unless `--campaign` is passed.

---

## How campaigns work

Each campaign has its own:
- **Firestore collection** for contacts (e.g. `my_campaign` collection)
- **Stats collections** (`my_campaign_stats/global`, `my_campaign_stats_daily/{date}`)
- **Events collection** (`my_campaign_events`)
- **Email copy** (step6 dispatches different templates based on the campaign name)
- **Dashboard tab** (add to `CAMPAIGN_COLLECTIONS` in `cloudflare/functions/api/stats.js`)

---

## Creating a new campaign

### 1. Prepare your contact list

Create a CSV with at minimum: `org_name`, `email`.

```
org_name,email,city,contact_name
"Org A","contact@orga.org","Tel Aviv","Dana"
"Org B","info@orgb.org","Haifa",""
```

Save it somewhere accessible (e.g. `data/my_campaign_contacts.csv`).

### 2. Import contacts to Firestore

The import step reads a CSV and writes to a Firestore collection named after the campaign:

```bash
cd pipeline
python step0_import.py --campaign my_campaign --csv ../data/my_campaign_contacts.csv
```

Each contact document gets:
- `org_name`, `email`, `campaign`
- `status: pending`
- Any extra CSV columns preserved as fields

### 3. Write email templates

Add your campaign's email logic to `step6_send_emails.py`. Find the `get_email_content()` function and add a branch:

```python
elif campaign == 'my_campaign':
    subject = f"Your custom subject for {org_name}"
    body_text = f"""
Hi {contact_name or 'there'},

Your email body here.

{config.SIG_FULL}
"""
    body_html = text_to_html(body_text)
    return subject, body_text, body_html
```

For inspiration, see the templates in `templates/email_tier1.md`, `email_tier2.md`, `email_tier3.md`.

### 4. Configure follow-up sequence

In `step6_send_emails.py`, the follow-up cadence is controlled by `FOLLOWUP1_DAYS`, `FOLLOWUP2_DAYS`, `FOLLOWUP3_DAYS` in `config.py`.

If your campaign needs a different cadence, pass overrides:

```python
# In your campaign's email logic section
FOLLOWUP_DAYS = {'followup1': 5, 'followup2': 10}
```

### 5. Run the campaign

```bash
python step6_send_emails.py --campaign my_campaign
```

Or add it to the GitHub Actions workflow:

```yaml
- name: Step 6 — My campaign
  env:
    SENDER_EMAIL:      ${{ secrets.SENDER_EMAIL }}
    TRACKING_BASE_URL: ${{ secrets.TRACKING_BASE_URL }}
  run: |
    cd pipeline
    python step6_send_emails.py --campaign my_campaign
```

### 6. Add to the dashboard

In `cloudflare/functions/api/stats.js`, add your campaign to `CAMPAIGN_COLLECTIONS`:

```javascript
const CAMPAIGN_COLLECTIONS = {
  main:        { stats: 'stats/global',             daily: 'stats_daily',             events: 'events' },
  my_campaign: { stats: 'my_campaign_stats/global', daily: 'my_campaign_stats_daily', events: 'my_campaign_events' },
}
```

Redeploy the dashboard:

```bash
npx wrangler pages deploy cloudflare --project-name your-project-name --commit-dirty=true
```

Your campaign now appears in the dashboard campaign switcher.

---

## Multi-tier campaigns

The default `main` campaign uses three tiers with different email content and sequence lengths:

| Tier | Emails in sequence | Personalization |
|------|---|---|
| Tier 1 | 4 (initial + 3 follow-ups) | AI-extracted achievement + population |
| Tier 2 | 3 (initial + 2 follow-ups) | AI-extracted theme |
| Tier 3 | 2 (initial + 1 follow-up) | Generic |

For simpler campaigns (e.g. Hebrew outreach to specific organizations), you may only need a single tier with 1–2 emails.

---

## Email personalization with Gemini AI

For large campaigns (100+ orgs), step5 can generate personalized snippets per org using Gemini Flash.

Run it before step0 import:

```bash
GEMINI_API_KEY=your_key python step5_personalize.py --tier 1 --limit 500
```

The AI reads each org's name, website, and project data and fills in:
- `specific_achievement` — e.g. "your VR skills program for young adults in Marseille"
- `their_population` — e.g. "youth with learning disabilities"
- `relevant_theme` — e.g. "digital inclusion"

These fields are referenced in the email templates to make each message feel individually researched.

Cost: ~$0.002 per org with Gemini 2.5 Flash.

---

## Tracking

All outbound emails contain a tracking link wrapped in a unique token. When the recipient clicks a link:

1. Their browser hits `GET /track/c/{token}` on your Cloudflare Worker
2. The Worker logs a `clicked` event to Firestore (fire-and-forget via `waitUntil`)
3. The user is transparently redirected to the real URL

Tracking data appears in the dashboard and in daily summary emails.

---

## AI reply handling

When a contact replies, `step7_ai_replies.py` (runs after step6 in the GitHub Actions workflow):

1. Polls Gmail for new replies
2. Identifies the matching contact in Firestore
3. Calls Gemini to generate a draft reply with context about the org
4. Emails you (at `NOTIFY_EMAIL`) with:
   - The original message
   - The AI-generated draft
   - An **Approve** link and a **Skip** link

Clicking Approve queues the reply; the next step6 run sends it.

You can customize the AI's reply style by editing the system prompt in `step7_ai_replies.py`.
