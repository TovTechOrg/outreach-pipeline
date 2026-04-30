"""
Step 6: Daily Email Sender — Gmail API + Firebase
==================================================
Runs once per day. Handles the full outreach lifecycle:
  1. Imports new prospects from enriched_prospects.csv into Firebase
  2. Checks Gmail threads for replies → marks replied contacts
  3. Sends followup3 (Day 14) — breakup email
  4. Sends followup2 (Day 7) to non-responders
  5. Sends followup1 (Day 3) to non-responders
  6. Sends new initial emails (up to DAILY_LIMIT)

All tracking data lives in Firebase Firestore (replaces SQLite).
The dashboard at Cloudflare Pages reads the same Firebase project.

Usage:
  py step6_send_emails.py                              # normal daily run (main campaign)
  py step6_send_emails.py --dry-run                    # preview only, no emails sent
  py step6_send_emails.py --tier 1                     # only Tier1 contacts today
  py step6_send_emails.py --limit 10                   # cap at 10 emails this run
  py step6_send_emails.py --check-replies              # only check replies, no sending
  py step6_send_emails.py --campaign my_campaign       # run a custom named campaign

Setup:
  1. py gmail_auth.py                                   (one-time)
  2. Place Firebase service account at: pipeline/firebase-service-account.json
  3. set SENDER_EMAIL=your@email.com
  4. py step6_send_emails.py
"""

import base64
import email.mime.multipart
import email.mime.text
import json
import os
import re
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone

import pandas as pd
import firebase_admin
from firebase_admin import credentials, firestore
from google.api_core.exceptions import AlreadyExists, NotFound
from google.cloud.firestore_v1 import ArrayUnion, Increment, SERVER_TIMESTAMP
from googleapiclient.errors import HttpError

# ── Paths ──────────────────────────────────────────────────────────────────────
PIPELINE_DIR  = os.path.dirname(os.path.abspath(__file__))
DATA_DIR      = os.path.join(PIPELINE_DIR, "..", "data")
PROSPECTS_CSV = os.path.join(DATA_DIR, "enriched_prospects.csv")
SA_PATH       = os.path.join(PIPELINE_DIR, "firebase-service-account.json")

# ── Config (all shared settings live in config.py) ─────────────────────────────
from config import (
    SENDER_EMAIL, DAILY_LIMIT, DAILY_PER_TIER, DAILY_INITIAL, DAILY_FOLLOWUP,
    TRACKING_BASE, PORTFOLIO_URL,
    FOLLOWUP1_DAYS, FOLLOWUP2_DAYS, FOLLOWUP3_DAYS,
    BOUNCE_SENDERS, BOUNCE_SUBJECTS,
    SIG_FULL, SIG_MID, SIG_SLIM,
)


# ── Firebase init ──────────────────────────────────────────────────────────────

def init_firebase():
    if not firebase_admin._apps:
        cred = credentials.Certificate(SA_PATH)
        firebase_admin.initialize_app(cred)
    return firestore.client()


def _gh_output(key: str, value: str):
    """Write key=value to GitHub Actions output file (no-op when running locally)."""
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a") as f:
            f.write(f"{key}={value}\n")


def safe_id(s: str) -> str:
    """Convert org name to a valid Firestore document ID."""
    return re.sub(r"[^\w-]", "_", s)[:100]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def today_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


# ── Email templates ────────────────────────────────────────────────────────────
# These are PLACEHOLDER templates. Customize the subject and body copy below
# to match your organization, product, and target audience.
# See templates/email_tier1.md, templates/email_tier2.md, templates/email_tier3.md
# for full guidance on writing effective email copy.

_TRAILING_PREPS = {
    # English
    "for", "in", "on", "of", "to", "with", "by", "and", "or", "the", "a", "an",
    # French
    "de", "du", "des", "le", "la", "les", "et", "au", "aux", "en", "pour", "sur",
    # Spanish / Portuguese
    "para", "por", "del", "las", "los", "el", "da", "dos", "das", "na", "no",
    # Italian
    "di", "il", "dei", "delle", "della", "dello", "nel", "nella",
    # German
    "und", "der", "die", "das", "den", "dem", "im", "vom", "zum", "zur", "fur",
}

def _truncate(text: str, max_len: int) -> str:
    """Truncate text at a word boundary, strip trailing prepositions and punctuation."""
    if len(text) <= max_len:
        return text
    cut = text[:max_len].rsplit(" ", 1)[0]
    cut = cut.rstrip(" ,;:-–—'\"")
    # Strip orphaned opening quote if closing quote was truncated
    if cut.startswith('"') and '"' not in cut[1:]:
        cut = cut[1:].lstrip()
    # Strip trailing prepositions/conjunctions left by truncation
    words = cut.split()
    while words and words[-1].lower() in _TRAILING_PREPS:
        words.pop()
    return " ".join(words)


def _display_name(org: str) -> str:
    """Title-case ALL CAPS org names; shorten long names at first separator."""
    if org == org.upper() and len(org) > 5:
        # Title-case but keep short abbreviations uppercase
        _LOWERCASE_WORDS = {
            "de", "del", "des", "du", "da", "das", "do", "dos",
            "di", "el", "la", "le", "les", "et", "en", "y",
            "of", "the", "and", "or", "in", "on", "at", "to",
            "von", "und", "der", "die",
        }
        words = []
        for i, w in enumerate(org.split()):
            wl = w.lower()
            if wl in _LOWERCASE_WORDS and i > 0:
                words.append(wl)
            elif len(w) <= 3 and w.isalpha():
                words.append(w)  # keep short abbreviations as-is
            else:
                words.append(w.title())
        org = " ".join(words)
    # Shorten at first separator (' - ', ' – ', ' / ') if name is long
    for sep in (" - ", " – ", " / "):
        if sep in org and len(org) > 40:
            org = org.split(sep)[0].strip()
            break
    return org


def build_email(contact: dict, email_type: str, click_token: str) -> tuple[str, str]:
    """Returns (subject, body).

    CUSTOMIZE THIS FUNCTION with your own email copy.
    See templates/email_tier1.md, email_tier2.md, email_tier3.md for guidance.

    Available contact fields:
      - contact["org_name"]            — organization name
      - contact["tier"]                — Tier1 / Tier2 / Tier3
      - contact["project_name"]        — their project name (if available)
      - contact["specific_achievement"] — AI-extracted achievement (Tier1)
      - contact["their_population"]    — AI-extracted target group (Tier1)
      - contact["relevant_theme"]      — AI-extracted theme (Tier2/3)

    The click_token is used to build a tracked link to PORTFOLIO_URL.
    Return (None, None) for email types that don't apply to a given tier.
    """
    org       = _display_name(contact["org_name"])
    org_short = _truncate(org, 30)
    proj      = _truncate(contact.get("project_name") or "your project", 40)
    achieve   = contact.get("specific_achievement") or "your impactful work"
    pop       = contact.get("their_population") or "your participants"
    theme     = _truncate(contact.get("relevant_theme") or "vocational skills", 35)
    tier      = contact.get("tier", "Tier3")
    link_html = PORTFOLIO_URL

    # ── Tier 1 — highest relevance, full 4-email sequence ─────────────────────
    # Customize: these contacts have the strongest match to your target audience.
    # Use specific_achievement and their_population for personalization.
    if tier == "Tier1":
        if email_type == "initial":
            return (
                f"[Your subject line for {org_short}]",
                f"""Hi,

[Your Tier 1 initial email body here. See templates/email_tier1.md for guidance.]

I noticed {org}'s work on {proj} — specifically {achieve}. That's impressive.

[Introduce yourself and your organization. Explain the value you offer.]

[Include a link to your portfolio/product: {link_html}]

[Explain why this is relevant to {pop}.]

[Clear call to action — e.g. "Would it be useful if I sent you our Session 1 materials?"]

{SIG_FULL}"""
            )
        elif email_type == "followup1":
            return (
                f"Re: [Your subject] + {org_short}",
                f"""Hi,

[Your Tier 1 follow-up 1 body here. See templates/email_tier1.md for guidance.]

[Add more context about your methodology or approach.]

[Reinforce the value for {pop}.]

[Gentle call to action — e.g. "Worth a quick call?"]

{SIG_MID}"""
            )
        elif email_type == "followup2":
            return (
                f"Re: [Your subject] + {org_short}",
                f"""Hi,

[Your Tier 1 follow-up 2 body here. See templates/email_tier1.md for guidance.]

[Add a new angle or hook, e.g. partnership opportunity, shared goal around {theme}.]

[{org}'s work on {proj} is relevant here.]

[Offer something concrete, e.g. a one-page concept note.]

{SIG_SLIM}"""
            )
        else:  # followup3
            return (
                f"Last note — [Your Org] + {org}",
                f"""Hi,

[Your Tier 1 breakup email here. See templates/email_tier1.md for guidance.]

[Keep it short. Wish them well. Leave the door open.]

[If {pop} or [your offer] is ever on your radar, I'm here.]

{SIG_SLIM}"""
            )

    # ── Tier 2 — medium relevance, 3-email sequence ────────────────────────────
    # Customize: content-gift approach. Lead with value.
    elif tier == "Tier2":
        if email_type == "initial":
            return (
                f"[Your subject line for {org_short}]",
                f"""Hi,

[Your Tier 2 initial email body here. See templates/email_tier2.md for guidance.]

[Briefly introduce yourself and your organization.]

[Lead with a gift or free resource relevant to {proj} and {theme}.]

[Link: {link_html}]

[Soft call to action — "Interested? Just reply and I'll send it over."]

{SIG_FULL}"""
            )
        elif email_type == "followup1":
            return (
                f"Re: [Your subject] for {org}",
                f"""Hi,

[Your Tier 2 follow-up 1 body here. See templates/email_tier2.md for guidance.]

[Short reminder. Restate the offer.]

[Easy yes/no call to action.]

{SIG_SLIM}"""
            )
        elif email_type == "followup2":
            return (
                f"Re: [Your subject] for {org}",
                f"""Hi,

[Your Tier 2 breakup email here. See templates/email_tier2.md for guidance.]

[Last follow-up. Keep it gracious. No pressure.]

{SIG_SLIM}"""
            )
        else:  # followup3 — not used for Tier2
            return None, None

    # ── Tier 3 — general audience, 2-email sequence ────────────────────────────
    # Customize: simple, low-pressure content-gift approach.
    elif tier == "Tier3":
        if email_type == "initial":
            return (
                f"[Your subject line for {org_short}]",
                f"""Hi,

[Your Tier 3 initial email body here. See templates/email_tier3.md for guidance.]

[Brief intro. Lead with your free offer or resource.]

[Link: {link_html}]

[Simple call to action — "If it fits what {org} does, just reply."]

{SIG_FULL}"""
            )
        elif email_type == "followup1":
            return (
                "Re: [Your subject] — thought of your work",
                f"""Hi,

[Your Tier 3 follow-up body here. See templates/email_tier3.md for guidance.]

[One-line reminder. No pressure.]

{SIG_SLIM}"""
            )
        else:  # followup2/3 — not used for Tier3
            return None, None

    # ── Custom campaigns ────────────────────────────────────────────────────────
    # Add additional elif branches here for custom campaigns.
    # Example:
    #
    # elif tier == "my_campaign":
    #     name = contact.get("contact_name") or ""
    #     if email_type == "initial":
    #         return (
    #             f"[Custom subject for {org_short}]",
    #             f"""Hi {name},
    #
    # [Custom email body for your campaign.]
    #
    # {SIG_FULL}"""
    #         )
    #     elif email_type == "followup1":
    #         ...
    #     else:
    #         return None, None

    return None, None


# ── Firebase helpers ───────────────────────────────────────────────────────────

def import_prospects(db):
    """Import new contacts from CSV into Firebase (skip already-imported orgs)."""
    if not os.path.exists(PROSPECTS_CSV):
        print(f"  CSV not found — skipping import (contacts already in Firebase).")
        return

    df = pd.read_csv(PROSPECTS_CSV, low_memory=False).fillna("")
    df = df[df["email"].astype(str).str.strip() != ""]

    # Extract primary email (first one) and filter obvious placeholders
    BAD_EMAIL_DOMAINS = {"mysite.com", "example.com", "test.com", "email.com"}
    EMAIL_RE = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')
    def primary_email(raw):
        e = str(raw).split(" | ")[0].strip().lower()
        # Strip common prefixes/suffixes from messy data
        for prefix in ("email :", "email:", "mailto:", "mailti:", "..."):
            if e.startswith(prefix):
                e = e[len(prefix):].strip()
        e = e.rstrip(",;. ")
        domain = e.split("@")[-1] if "@" in e else ""
        if domain in BAD_EMAIL_DOMAINS:
            return ""
        if not EMAIL_RE.match(e):
            return ""
        return e

    df["_primary_email"] = df["email"].apply(primary_email)
    df = df[df["_primary_email"] != ""]

    # Deduplicate by email: keep highest-tier org per email address
    tier_order = {"Tier1": 0, "Tier2": 1, "Tier3": 2}
    df["_tier_rank"] = df["tier"].map(tier_order).fillna(3)
    df = df.sort_values("_tier_rank").drop_duplicates(subset="_primary_email", keep="first")
    df = df.drop(columns=["_tier_rank"])

    imported = 0
    skipped_email_dupes = 0
    seen_emails: set = set()

    # Also collect emails already in Firebase to prevent cross-batch dupes
    existing = db.collection("contacts").stream()
    for doc in existing:
        e = (doc.to_dict() or {}).get("email", "").lower().strip()
        if e:
            seen_emails.add(e)

    batch    = db.batch()
    batch_n  = 0

    for _, row in df.iterrows():
        email_addr = row["_primary_email"]
        if email_addr in seen_emails:
            skipped_email_dupes += 1
            continue
        seen_emails.add(email_addr)

        doc_id = safe_id(str(row["org_name"]))
        ref    = db.collection("contacts").document(doc_id)

        data = {
            "org_name":             str(row["org_name"]),
            "email":                email_addr,
            "country":              str(row.get("country", "")),
            "tier":                 str(row.get("tier", "Tier3")),
            "project_name":         str(row.get("project_titles", "")).split(" | ")[0][:120],
            "specific_achievement": str(row.get("specific_achievement", "")),
            "their_population":     str(row.get("their_population", "")),
            "relevant_theme":       str(row.get("relevant_theme", "")),
            "status":               "pending",
            "replied":              False,
            "click_count":          0,
            "initial_sent_at":      None,
            "initial_thread_id":    None,
            "followup1_sent_at":    None,
            "followup1_thread_id":  None,
            "followup2_sent_at":    None,
            "followup2_thread_id":  None,
            "followup3_sent_at":    None,
            "replied_at":           None,
            "created_at":           now_iso(),
        }

        try:
            ref.create(data)
            imported += 1
            batch_n  += 1
        except AlreadyExists:
            pass  # already imported — skip

        if batch_n >= 400:
            batch.commit()
            batch   = db.batch()
            batch_n = 0

    if imported:
        print(f"  Imported {imported:,} new contacts into Firebase")
    if skipped_email_dupes:
        print(f"  Skipped {skipped_email_dupes:,} orgs with duplicate email addresses")


def make_click_token(db, org_name: str, target_url: str) -> str:
    token = uuid.uuid4().hex
    db.collection("tracking_tokens").document(token).set({
        "org_name":   org_name,
        "token_type": "click",
        "target_url": target_url,
        "used_count": 0,
        "created_at": now_iso(),
    })
    return token


def log_event(db, org_name: str, event_type: str, data: dict = None, campaign: str = "main"):
    events_col = f"{campaign}_events" if campaign != "main" else "events"
    db.collection(events_col).add({
        "org_name":   org_name,
        "event_type": event_type,
        "event_data": json.dumps(data or {}),
        "created_at": now_iso(),
    })


def update_stats(db, event_type: str, tier: str, campaign: str = "main"):
    """Increment counters in stats/global and stats_daily/{today}."""
    today = today_str()

    if campaign and campaign != "main":
        stats_col = f"{campaign}_stats"
        daily_col = f"{campaign}_stats_daily"
    else:
        stats_col = "stats"
        daily_col = "stats_daily"

    global_ref = db.collection(stats_col).document("global")
    daily_ref  = db.collection(daily_col).document(today)

    # Global: increment event type + sent + tier counter
    global_updates = { event_type: Increment(1) }
    if event_type in ("initial_sent", "followup1_sent", "followup2_sent"):
        global_updates["sent"] = Increment(1)

    global_ref.set(global_updates, merge=True)
    daily_ref.set({ event_type: Increment(1) }, merge=True)

    # Tier breakdown (nested map)
    if tier:
        global_ref.set({
            "by_tier": { tier: { event_type: Increment(1) } }
        }, merge=True)
        if event_type in ("initial_sent", "followup1_sent", "followup2_sent"):
            global_ref.set({
                "by_tier": { tier: { "sent": Increment(1) } }
            }, merge=True)


# ── Gmail helpers ──────────────────────────────────────────────────────────────

def make_gmail_message(sender, to, subject, body, rtl=False):
    # body may contain HTML anchor tags — send as multipart/alternative
    # so plain-text clients see the raw text and HTML clients see the link
    msg = email.mime.multipart.MIMEMultipart("alternative")
    msg["to"]      = to
    msg["from"]    = sender
    msg["subject"] = subject

    plain = body

    # HTML: body already has anchor tags — just convert newlines to <br>
    dir_attr = ' dir="rtl"' if rtl else ''
    text_align = "right" if rtl else "left"
    html = (
        f'<html><body{dir_attr} style="font-family:Arial,sans-serif;font-size:14px;'
        f'line-height:1.7;color:#222;max-width:600px;text-align:{text_align};">'
        + body.replace("\n", "<br>\n") +
        "</body></html>"
    )

    msg.attach(email.mime.text.MIMEText(plain, "plain", "utf-8"))
    msg.attach(email.mime.text.MIMEText(html,  "html",  "utf-8"))
    return {"raw": base64.urlsafe_b64encode(msg.as_bytes()).decode()}


def send_email(service, sender, to, subject, body, thread_id=None, rtl=False):
    payload = make_gmail_message(sender, to, subject, body, rtl=rtl)
    if thread_id:
        payload["threadId"] = thread_id
    try:
        result = service.users().messages().send(userId="me", body=payload).execute()
        return result["id"], result["threadId"]
    except HttpError as e:
        print(f"    Gmail error: {e}")
        return None, None


# BOUNCE_SENDERS and BOUNCE_SUBJECTS imported from config


def _msg_headers(message) -> dict:
    return {h["name"].lower(): h["value"].lower()
            for h in message.get("payload", {}).get("headers", [])}


def is_bounce(message) -> bool:
    h = _msg_headers(message)
    sender  = h.get("from", "")
    subject = h.get("subject", "")
    return (any(b in sender  for b in BOUNCE_SENDERS) or
            any(b in subject for b in BOUNCE_SUBJECTS))


def get_thread_metadata(service, thread_id: str) -> list:
    """Fetch thread messages with headers only (efficient — no body download)."""
    try:
        thread = service.users().threads().get(
            userId="me", id=thread_id, format="metadata",
            metadataHeaders=["From", "Subject"],
        ).execute()
        return thread.get("messages", [])
    except Exception:
        return []


# ── Core logic ─────────────────────────────────────────────────────────────────

def _collection_for_campaign(campaign: str) -> str:
    """Return the Firestore collection name for a given campaign."""
    if campaign and campaign != "main":
        return campaign  # custom campaigns use a collection named after the campaign
    return "contacts"


def check_replies(db, service, dry_run: bool = False, campaign: str = None):
    col = _collection_for_campaign(campaign) if campaign else "contacts"
    collections = [col] if campaign else ["contacts"]

    active = []
    for c in collections:
        active += db.collection(c) \
                    .where("replied", "==", False) \
                    .where("status", "in", ["initial_sent", "followup1_sent",
                                            "followup2_sent", "followup3_sent"]) \
                    .get()

    replied = 0
    bounced = 0

    for doc in active:
        contact   = doc.to_dict()
        thread_id = (contact.get("followup2_thread_id")
                     or contact.get("followup1_thread_id")
                     or contact.get("initial_thread_id"))
        if not thread_id:
            continue

        messages = get_thread_metadata(service, thread_id)
        if len(messages) <= 1:
            continue

        # Find first non-outbound message (SENT label is reliable regardless of From address)
        inbound = next(
            (m for m in messages if "SENT" not in m.get("labelIds", [])),
            None
        )
        if not inbound:
            continue

        _camp = campaign or "main"
        if is_bounce(inbound):
            print(f"  ✗ Bounce: {contact['org_name']}")
            bounced += 1
            if not dry_run:
                doc.reference.update({
                    "status":     "bounced",
                    "replied":    True,   # stops all followups
                    "bounced_at": now_iso(),
                })
                log_event(db, contact["org_name"], "bounced", {"email": contact["email"]}, campaign=_camp)
                update_stats(db, "bounced", contact.get("tier"), campaign=_camp)
        else:
            print(f"  ↩ Reply: {contact['org_name']}")
            replied += 1
            if not dry_run:
                doc.reference.update({
                    "status":     "replied",
                    "replied":    True,
                    "replied_at": now_iso(),
                })
                log_event(db, contact["org_name"], "replied", {"email": contact["email"]}, campaign=_camp)
                update_stats(db, "replied", contact.get("tier"), campaign=_camp)

    print(f"  Checked {len(active):,} active → {replied} replies, {bounced} bounces")
    return replied, bounced


def send_followups(db, service, followup_type: str, days: int,
                   tier_filter, dry_run: bool, max_send: int = 999,
                   campaign: str = "main") -> int:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    col = _collection_for_campaign(campaign)

    if followup_type == "followup1":
        query = db.collection(col) \
                  .where("status", "==", "initial_sent") \
                  .where("initial_sent_at", "<=", cutoff) \
                  .where("replied", "==", False)
        thread_field = "initial_thread_id"
        save_thread  = "followup1_thread_id"
        sent_field   = "followup1_sent_at"
        next_status  = "followup1_sent"
    elif followup_type == "followup2":
        query = db.collection(col) \
                  .where("status", "==", "followup1_sent") \
                  .where("followup1_sent_at", "<=", cutoff) \
                  .where("replied", "==", False)
        thread_field = "followup1_thread_id"
        save_thread  = "followup2_thread_id"
        sent_field   = "followup2_sent_at"
        next_status  = "followup2_sent"
    else:  # followup3
        query = db.collection(col) \
                  .where("status", "==", "followup2_sent") \
                  .where("followup2_sent_at", "<=", cutoff) \
                  .where("replied", "==", False)
        thread_field = "followup2_thread_id"
        save_thread  = None
        sent_field   = "followup3_sent_at"
        next_status  = "followup3_sent"

    docs = query.get()
    if tier_filter:
        docs = [d for d in docs if d.to_dict().get("tier") == tier_filter]

    sent = 0
    for doc in docs:
        if sent >= max_send:
            break
        contact   = doc.to_dict()
        token     = make_click_token(db, contact["org_name"], PORTFOLIO_URL)
        subject, body = build_email(contact, followup_type, token)
        if subject is None:
            # This tier doesn't have this followup stage — mark as done
            if not dry_run:
                doc.reference.update({"status": next_status, sent_field: now_iso()})
            continue
        thread_id = contact.get(thread_field)

        print(f"  → [{followup_type}] {contact['org_name'][:45]}")

        if not dry_run:
            msg_id, t_id = send_email(
                service, SENDER_EMAIL, contact["email"],
                subject, body, thread_id=thread_id
            )
            if msg_id:
                update = {
                    "status":    next_status,
                    sent_field:  now_iso(),
                }
                if save_thread:
                    update[save_thread] = t_id
                doc.reference.update(update)
                log_event(db, contact["org_name"], followup_type,
                          {"to": contact["email"], "subject": subject}, campaign=campaign)
                update_stats(db, followup_type, contact.get("tier"), campaign=campaign)
                sent += 1
                time.sleep(2)
        else:
            sent += 1

    return sent


def send_initial_emails(db, service, quota: int, tier_filter, dry_run: bool,
                        campaign: str = "main") -> int:
    if quota <= 0:
        return 0

    tiers = [tier_filter] if tier_filter else ["Tier1", "Tier2", "Tier3"]
    per_tier = DAILY_PER_TIER if not tier_filter else quota

    sent = 0
    col = _collection_for_campaign(campaign)

    for tier in tiers:
        tier_quota = per_tier

        docs = db.collection(col) \
                 .where("status", "==", "pending") \
                 .where("tier", "==", tier) \
                 .limit(500) \
                 .get()

        tier_sent = 0
        for doc in docs:
            if tier_sent >= tier_quota:
                break
            contact = doc.to_dict()

            # Only send to contacts with personalization data (skip if not yet personalized)
            if tier == "Tier1" and not (contact.get("specific_achievement") and contact.get("their_population")):
                continue
            if tier in ("Tier2", "Tier3") and not contact.get("relevant_theme"):
                continue

            token   = make_click_token(db, contact["org_name"], PORTFOLIO_URL)
            subject, body = build_email(contact, "initial", token)

            if subject is None:
                continue  # no template for this tier

            print(f"  -> [initial/{tier}] {contact['org_name'][:45]}")

            if not dry_run:
                msg_id, thread_id = send_email(
                    service, SENDER_EMAIL, contact["email"], subject, body
                )
                if msg_id:
                    doc.reference.update({
                        "status":           "initial_sent",
                        "initial_sent_at":  now_iso(),
                        "initial_thread_id": thread_id,
                    })
                    log_event(db, contact["org_name"], "initial_sent",
                              {"to": contact["email"], "subject": subject}, campaign=campaign)
                    update_stats(db, "initial_sent", contact.get("tier"), campaign=campaign)
                    tier_sent += 1
                    time.sleep(2)
            else:
                tier_sent += 1

        if tier_sent:
            print(f"  {tier}: {tier_sent} sent")
        sent += tier_sent

    return sent


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    args        = sys.argv[1:]
    dry_run     = "--dry-run"       in args
    check_only  = "--check-replies" in args
    campaign_arg = "main"
    if "--campaign" in args:
        campaign_arg = args[args.index("--campaign") + 1]
    tier_filter = None
    limit       = DAILY_LIMIT

    if "--tier" in args:
        raw_tier = args[args.index("--tier") + 1]
        tier_filter = f"Tier{raw_tier}" if not raw_tier.startswith("Tier") else raw_tier
    if "--limit" in args:
        limit = int(args[args.index("--limit") + 1])

    if dry_run:
        print("=== DRY RUN — no emails will be sent ===\n")

    # Init Firebase
    db = init_firebase()

    # ── Idempotency check: skip if already sent today ──────────────────────────
    if not dry_run and not check_only:
        today = today_str()
        if campaign_arg != "main":
            daily_col = f"{campaign_arg}_stats_daily"
        else:
            daily_col = "stats_daily"
        daily_doc = db.collection(daily_col).document(today).get().to_dict() or {}
        already_sent = daily_doc.get("initial_sent", 0)
        if already_sent > 0:
            print(f"Already sent {already_sent} initial emails today — skipping to prevent duplicates.")
            _gh_output("had_activity", "false")
            return

    # Import prospects from CSV
    print(f"─── Importing prospects (campaign: {campaign_arg}) ───")
    import_prospects(db)
    print()

    # ── Early exit: skip Gmail entirely if there is nothing to do ──────────────
    active_col = _collection_for_campaign(campaign_arg)
    if not dry_run and not check_only:
        ACTIVE_STATUSES = ["initial_sent", "followup1_sent", "followup2_sent", "followup3_sent"]
        has_pending = bool(
            db.collection(active_col).where("status", "==", "pending").limit(1).get()
        )
        has_active = bool(
            db.collection(active_col)
              .where("replied", "==", False)
              .where("status", "in", ACTIVE_STATUSES)
              .limit(1).get()
        )
        if not has_pending and not has_active:
            print("Nothing to do — no pending or active contacts.")
            _gh_output("had_activity", "false")
            return

    # Init Gmail
    sys.path.insert(0, PIPELINE_DIR)
    from gmail_auth import get_gmail_service
    print("Connecting to Gmail...")
    service = get_gmail_service()
    print(f"  Sender: {SENDER_EMAIL}")
    print(f"  Daily limit: {limit} | Tracking: {TRACKING_BASE}\n")

    # 1. Check replies + bounces
    print("─── Checking replies ───")
    _campaign = campaign_arg if campaign_arg != "main" else None
    replied_count, bounced_count = check_replies(db, service, dry_run, campaign=_campaign)
    print()


    if check_only:
        print("Done (check-replies only).")
        _gh_output("had_activity", "true" if (replied_count > 0 or bounced_count > 0) else "false")
        return

    sent_today = 0

    # 2. Initial emails FIRST (up to DAILY_INITIAL per day)
    initial_quota = min(DAILY_INITIAL, DAILY_LIMIT)
    print(f"─── Initial emails (quota: {initial_quota}) ───")
    n = send_initial_emails(db, service, initial_quota, tier_filter, dry_run, campaign=campaign_arg)
    sent_today += n
    print(f"  Sent: {n}\n")

    # 3. Followup 1 (max DAILY_FOLLOWUP/day, never exceed DAILY_LIMIT total)
    followup_quota = min(DAILY_FOLLOWUP, DAILY_LIMIT - sent_today)
    print(f"─── Followup 1 (Day {FOLLOWUP1_DAYS}, quota: {followup_quota}) ───")
    if followup_quota > 0:
        n = send_followups(db, service, "followup1", FOLLOWUP1_DAYS,
                           tier_filter, dry_run, max_send=followup_quota,
                           campaign=campaign_arg)
        sent_today += n
    else:
        print("  Skipped — daily limit reached")
        n = 0
    print(f"  Sent: {n}\n")

    # 4. Followup 2 (max DAILY_FOLLOWUP/day, never exceed DAILY_LIMIT total)
    followup_quota = min(DAILY_FOLLOWUP, DAILY_LIMIT - sent_today)
    print(f"─── Followup 2 (Day {FOLLOWUP2_DAYS}, quota: {followup_quota}) ───")
    if followup_quota > 0:
        n = send_followups(db, service, "followup2", FOLLOWUP2_DAYS,
                           tier_filter, dry_run, max_send=followup_quota,
                           campaign=campaign_arg)
        sent_today += n
    else:
        print("  Skipped — daily limit reached")
        n = 0
    print(f"  Sent: {n}\n")

    # 5. Followup 3 — breakup (max DAILY_FOLLOWUP/day, never exceed DAILY_LIMIT total)
    followup_quota = min(DAILY_FOLLOWUP, DAILY_LIMIT - sent_today)
    print(f"─── Followup 3 — breakup (Day {FOLLOWUP3_DAYS}, quota: {followup_quota}) ───")
    if followup_quota > 0:
        n = send_followups(db, service, "followup3", FOLLOWUP3_DAYS,
                           tier_filter, dry_run, max_send=followup_quota,
                           campaign=campaign_arg)
        sent_today += n
    else:
        print("  Skipped — daily limit reached")
        n = 0
    print(f"  Sent: {n}\n")

    # Summary from Firebase
    stats_col = f"{campaign_arg}_stats" if campaign_arg != "main" else "stats"
    global_stats = db.collection(stats_col).document("global").get().to_dict() or {}
    print("=" * 50)
    print(f"Sent today: {sent_today}")
    print(f"Totals → Sent: {global_stats.get('sent', 0):,} | "
          f"Replied: {global_stats.get('replied', 0):,} | "
          f"Clicked: {global_stats.get('clicked', 0):,}")
    print(f"Dashboard: {TRACKING_BASE}")

    # Report activity to GitHub Actions so downstream steps can skip if idle
    had_activity = sent_today > 0 or replied_count > 0 or bounced_count > 0
    _gh_output("had_activity", "true" if had_activity else "false")
    _gh_output("sent_count", str(sent_today))


if __name__ == "__main__":
    main()
