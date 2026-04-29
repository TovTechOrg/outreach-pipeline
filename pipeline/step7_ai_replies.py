"""
Step 7: AI Reply Handler — Gemini + Gmail + Email Approval
==========================================================
Runs twice daily via GitHub Actions.

For each new inbound reply:
  1. Extracts the reply text from the Gmail thread
  2. Sends it to Gemini with org context + background doc
  3. Saves the AI draft to Firebase (pending_replies collection)
  4. Sends an approval email to NOTIFY_EMAIL with:
       - The reply text received
       - The AI-generated draft
       - [Approve] and [Skip] links

For each previously-approved draft:
  5. Sends the reply via Gmail in the original thread
  6. Updates Firebase: pending_reply status → "sent", contact status → "ai_replied"

Usage:
  py step7_ai_replies.py                 # normal run
  py step7_ai_replies.py --dry-run       # preview only, nothing sent
  py step7_ai_replies.py --send-only     # only send approved drafts (skip new reply check)

Env vars required:
  SENDER_EMAIL      — Gmail account to send from
  GEMINI_API_KEY    — Google AI Studio API key
  NOTIFY_EMAIL      — where to send approval emails (e.g. your-notify@email.com)
  TRACKING_BASE_URL — base URL of Cloudflare dashboard (for approve/skip links)
"""

import base64
import email as email_lib
import email.mime.multipart
import email.mime.text
import json
import os
import re
import sys
import time
import uuid
from datetime import datetime, timezone

import google.generativeai as genai

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from step6_send_emails import (
    init_firebase, safe_id, now_iso, make_gmail_message,
    send_email, log_event, update_stats,
)
from gmail_auth import get_gmail_service
from config import (
    SENDER_EMAIL, TRACKING_BASE, NOTIFY_EMAIL, GEMINI_MODEL,
    BOUNCE_SENDERS, BOUNCE_SUBJECTS,
)

# ── Config ─────────────────────────────────────────────────────────────────────
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

CONTEXT_DOC_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "docs", "gemini_reply_context.md"
)


# ── Gemini ─────────────────────────────────────────────────────────────────────

def load_context_doc() -> str:
    try:
        with open(CONTEXT_DOC_PATH, encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return ""


def generate_ai_reply(contact: dict, our_email: str, their_reply: str,
                      db=None) -> str:
    """Call Gemini to generate a reply draft. Returns the draft text."""
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY not set")

    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel(GEMINI_MODEL)

    context = load_context_doc()

    prompt = f"""
{context}

---

## Current Conversation

**Organisation**: {contact.get("org_name", "Unknown")}
**Country**: {contact.get("country", "")}
**Tier**: {contact.get("tier", "")}
**Project**: {contact.get("project_name", "")}
**Their population**: {contact.get("their_population", "")}
**Relevant theme**: {contact.get("relevant_theme", "")}

**Our last email to them**:
{our_email}

**Their reply**:
{their_reply}

---

Write a reply email body only (no subject line, no "From:", no metadata).
Follow the tone rules strictly. 3-6 sentences max. One clear next step.
End with the signature block as defined above.
"""

    response = model.generate_content(prompt)

    # Track token usage in Firebase
    if db and hasattr(response, "usage_metadata"):
        usage = response.usage_metadata
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        from google.cloud.firestore_v1 import Increment
        db.collection("stats_daily").document(today).set({
            "gemini_input_tokens":  Increment(usage.prompt_token_count or 0),
            "gemini_output_tokens": Increment(usage.candidates_token_count or 0),
            "gemini_calls":         Increment(1),
        }, merge=True)
        db.collection("stats").document("global").set({
            "gemini_input_tokens":  Increment(usage.prompt_token_count or 0),
            "gemini_output_tokens": Increment(usage.candidates_token_count or 0),
            "gemini_calls":         Increment(1),
        }, merge=True)

    return response.text.strip()


# ── Gmail helpers ──────────────────────────────────────────────────────────────

def decode_body(part) -> str:
    """Decode a Gmail message part body to plain text."""
    data = part.get("body", {}).get("data", "")
    if not data:
        return ""
    try:
        return base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")
    except Exception:
        return ""


def extract_plain_text(payload) -> str:
    """Recursively extract plain text from a Gmail message payload."""
    mime_type = payload.get("mimeType", "")

    if mime_type == "text/plain":
        return decode_body(payload)

    if mime_type.startswith("multipart/"):
        for part in payload.get("parts", []):
            text = extract_plain_text(part)
            if text:
                return text

    return ""


def get_thread_messages(service, thread_id: str) -> list:
    """Return all messages in a thread."""
    try:
        thread = service.users().threads().get(
            userId="me", id=thread_id, format="full"
        ).execute()
        return thread.get("messages", [])
    except Exception as e:
        print(f"    Error fetching thread {thread_id}: {e}")
        return []


def get_sender(message) -> str:
    headers = {h["name"].lower(): h["value"] for h in message.get("payload", {}).get("headers", [])}
    return headers.get("from", "")


def get_subject(message) -> str:
    headers = {h["name"].lower(): h["value"] for h in message.get("payload", {}).get("headers", [])}
    return headers.get("subject", "")


def is_our_message(message, sender_email: str) -> bool:
    if "SENT" in message.get("labelIds", []):
        return True
    return sender_email.lower() in get_sender(message).lower()


# BOUNCE_SENDERS and BOUNCE_SUBJECTS imported from config


def _header(message, name: str) -> str:
    for h in message.get("payload", {}).get("headers", []):
        if h["name"].lower() == name.lower():
            return h["value"].lower()
    return ""


def is_bounce(message) -> bool:
    return (any(b in _header(message, "from")    for b in BOUNCE_SENDERS) or
            any(b in _header(message, "subject") for b in BOUNCE_SUBJECTS))


def find_inbound_reply(messages: list, sender_email: str) -> tuple[str, str] | None:
    """
    Find the first inbound (not from us, not a bounce) message.
    Returns (their_reply_text, our_last_email_text) or None.
    """
    our_last = ""
    for msg in messages:
        if is_our_message(msg, sender_email):
            text = extract_plain_text(msg.get("payload", {}))
            if text:
                our_last = text
        elif is_bounce(msg):
            continue  # skip bounce notifications
        else:
            text = extract_plain_text(msg.get("payload", {}))
            if text:
                return text.strip(), our_last.strip()
    return None


# ── Firebase helpers ───────────────────────────────────────────────────────────

def already_processed(db, contact_id: str) -> bool:
    """Check if we already created a pending_reply for this contact."""
    docs = db.collection("pending_replies") \
              .where("contact_id", "==", contact_id) \
              .where("status", "in", ["pending", "approved", "sent"]) \
              .limit(1).get()
    return len(docs) > 0


def create_pending_reply(db, contact: dict, contact_id: str,
                         their_reply: str, ai_draft: str,
                         thread_id: str) -> str:
    approval_token = uuid.uuid4().hex
    db.collection("pending_replies").document(approval_token).set({
        "contact_id":       contact_id,
        "org_name":         contact.get("org_name"),
        "contact_email":    contact.get("email"),
        "thread_id":        thread_id,
        "their_reply":      their_reply,
        "ai_draft":         ai_draft,
        "status":           "pending",
        "approval_token":   approval_token,
        "created_at":       now_iso(),
    })
    return approval_token


def get_approved_replies(db) -> list:
    docs = db.collection("pending_replies") \
              .where("status", "==", "approved") \
              .get()
    return [(doc.id, doc.to_dict()) for doc in docs]


# ── Approval email ─────────────────────────────────────────────────────────────

def send_approval_email(service, pending_id: str, contact: dict,
                        their_reply: str, ai_draft: str):
    approve_url = f"{TRACKING_BASE}/approve/{pending_id}"
    skip_url    = f"{TRACKING_BASE}/skip/{pending_id}"

    org  = contact.get("org_name", "Unknown")
    addr = contact.get("email", "")

    subject = f"[Outreach AI] Reply from {org} — approve draft?"

    body = f"""New reply received from {org} ({addr}).

━━━━━━━━ THEIR REPLY ━━━━━━━━
{their_reply}

━━━━━━━━ AI DRAFT (Gemini) ━━━━━━━━
{ai_draft}

━━━━━━━━ ACTIONS ━━━━━━━━
Approve & send: {approve_url}

Skip (do nothing): {skip_url}

━━━━━━━━━━━━━━━━━━━━━━━━
"""

    send_email(service, SENDER_EMAIL, NOTIFY_EMAIL, subject, body)
    print(f"  Approval email sent to {NOTIFY_EMAIL} for: {org}")


# ── Core logic ─────────────────────────────────────────────────────────────────

def check_new_replies(db, service, dry_run: bool):
    """Find new inbound replies, generate AI drafts, send approval emails."""

    # All contacts that are in an active stage and not yet replied
    active = db.collection("contacts") \
               .where("replied", "==", False) \
               .where("status", "in", [
                   "initial_sent", "followup1_sent",
                   "followup2_sent", "followup3_sent",
               ]).get()

    new_found = 0

    for doc in active:
        contact    = doc.to_dict()
        contact_id = doc.id
        org        = contact.get("org_name", contact_id)

        thread_id = (
            contact.get("followup3_sent_at") and contact.get("followup2_thread_id") or
            contact.get("followup2_thread_id") or
            contact.get("followup1_thread_id") or
            contact.get("initial_thread_id")
        )
        if not thread_id:
            continue

        # Skip if already in pending_replies
        if already_processed(db, contact_id):
            continue

        # Cheap metadata check first — only download full thread if there's a reply
        try:
            meta = service.users().threads().get(
                userId="me", id=thread_id, format="metadata",
                metadataHeaders=["From"],
            ).execute()
            if len(meta.get("messages", [])) <= 1:
                continue  # no reply yet — skip expensive full fetch
        except Exception:
            continue

        messages = get_thread_messages(service, thread_id)
        if len(messages) <= 1:
            continue  # no reply yet

        result = find_inbound_reply(messages, SENDER_EMAIL)
        if not result:
            continue

        their_reply, our_last_email = result
        new_found += 1

        print(f"  New reply: {org[:50]}")
        print(f"    From: {contact.get('email')}")
        print(f"    Preview: {their_reply[:100]}...")

        if dry_run:
            print(f"    [DRY RUN] Would generate AI draft and send approval email")
            continue

        # Generate AI reply
        try:
            ai_draft = generate_ai_reply(contact, our_last_email, their_reply, db)
        except Exception as e:
            print(f"    Gemini error: {e}")
            continue

        # Save to Firebase
        approval_token = create_pending_reply(
            db, contact, contact_id, their_reply, ai_draft, thread_id
        )

        # Send approval email
        send_approval_email(service, approval_token, contact, their_reply, ai_draft)

        # Mark contact as replied so step6 stops sending followups
        doc.reference.update({
            "replied":    True,
            "replied_at": now_iso(),
            "status":     "replied",
        })
        log_event(db, org, "replied_detected", {"thread_id": thread_id})
        update_stats(db, "replied", contact.get("tier"))

        time.sleep(1)

    print(f"  Found {new_found} new replies")
    return new_found


def send_approved_replies(db, service, dry_run: bool):
    """Send all drafts that have been approved via the Cloudflare Worker link."""
    approved = get_approved_replies(db)

    if not approved:
        print("  No approved drafts to send")
        return 0

    sent = 0
    for pending_id, pending in approved:
        org        = pending.get("org_name", "?")
        to         = pending.get("contact_email", "")
        thread_id  = pending.get("thread_id")
        ai_draft   = pending.get("ai_draft", "")
        contact_id = pending.get("contact_id")

        print(f"  Sending approved reply to: {org[:50]}")

        if dry_run:
            print(f"    [DRY RUN] Would send to {to}")
            print(f"    Draft: {ai_draft[:100]}...")
            continue

        # Rebuild subject from thread (use "Re: <original subject>" pattern)
        messages = get_thread_messages(service, thread_id)
        original_subject = get_subject(messages[0]) if messages else "Re: your message"
        if not original_subject.startswith("Re:"):
            original_subject = f"Re: {original_subject}"

        msg_id, _ = send_email(
            service, SENDER_EMAIL, to,
            original_subject, ai_draft,
            thread_id=thread_id,
        )

        if msg_id:
            # Mark pending reply as sent
            db.collection("pending_replies").document(pending_id).update({
                "status":  "sent",
                "sent_at": now_iso(),
            })
            # Update contact
            if contact_id:
                db.collection("contacts").document(contact_id).update({
                    "status": "ai_replied",
                })
            log_event(db, org, "ai_reply_sent", {"to": to})
            sent += 1
            time.sleep(2)
        else:
            print(f"    FAILED to send to {to}")

    return sent


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    args      = sys.argv[1:]
    dry_run   = "--dry-run"   in args
    send_only = "--send-only" in args

    if dry_run:
        print("=== DRY RUN — nothing will be sent ===\n")

    db      = init_firebase()
    service = get_gmail_service()

    print(f"Notify email : {NOTIFY_EMAIL}")
    print(f"Sender       : {SENDER_EMAIL}")
    print(f"Gemini model : {GEMINI_MODEL}\n")

    if not send_only:
        print("─── Checking for new replies ───")
        check_new_replies(db, service, dry_run)
        print()

    print("─── Sending approved drafts ───")
    sent = send_approved_replies(db, service, dry_run)
    print(f"  Sent: {sent}\n")


if __name__ == "__main__":
    main()
