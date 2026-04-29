"""
Daily Usage Summary — sends a report email after each pipeline run.
====================================================================
Called at the end of the GitHub Actions workflow.

Reports:
  - Emails sent today (initial / followup1 / followup2 / followup3)
  - Replies found + AI drafts sent for approval
  - Gemini token usage + estimated cost
  - Firebase operations estimate
  - Cumulative totals

Usage:
  py step_summary.py
"""

import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from step6_send_emails import (
    init_firebase, make_gmail_message,
)
from gmail_auth import get_gmail_service
from googleapiclient.errors import HttpError
from config import SENDER_EMAIL, TRACKING_BASE, NOTIFY_EMAIL

# Gemini 2.0 Flash pricing (USD per 1M tokens)
GEMINI_INPUT_PRICE  = 0.075
GEMINI_OUTPUT_PRICE = 0.30


def today_str():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def build_bar(value, limit, width=20):
    """Simple ASCII bar: ████░░░░ 142 / 50,000"""
    pct  = min(value / limit, 1.0) if limit else 0
    fill = int(pct * width)
    bar  = "█" * fill + "░" * (width - fill)
    return f"{bar}  {value:,} / {limit:,}  ({pct*100:.1f}%)"


def send_summary(service, db):
    today   = today_str()
    daily   = (db.collection("stats_daily").document(today).get().to_dict() or {})
    totals  = (db.collection("stats").document("global").get().to_dict() or {})

    # ── Today's email activity ─────────────────────────────────────────────────
    initial_sent   = daily.get("initial_sent",   0)
    followup1_sent = daily.get("followup1_sent",  0)
    followup2_sent = daily.get("followup2_sent",  0)
    followup3_sent = daily.get("followup3_sent",  0)
    replied_today  = daily.get("replied",         0)
    bounced_today  = daily.get("bounced",         0)
    sent_today     = initial_sent + followup1_sent + followup2_sent + followup3_sent

    # ── Gemini usage ───────────────────────────────────────────────────────────
    g_in   = daily.get("gemini_input_tokens",  0)
    g_out  = daily.get("gemini_output_tokens", 0)
    g_calls = daily.get("gemini_calls",        0)
    g_cost = (g_in / 1_000_000 * GEMINI_INPUT_PRICE) + \
             (g_out / 1_000_000 * GEMINI_OUTPUT_PRICE)

    # ── Cumulative totals ──────────────────────────────────────────────────────
    total_sent    = totals.get("sent",    0)
    total_replied = totals.get("replied", 0)
    total_clicked = totals.get("clicked", 0)
    total_bounced = totals.get("bounced", 0)
    reply_rate    = f"{total_replied/total_sent*100:.1f}%" if total_sent else "—"
    click_rate    = f"{total_clicked/total_sent*100:.1f}%" if total_sent else "—"
    bounce_rate   = f"{total_bounced/total_sent*100:.1f}%" if total_sent else "—"

    # ── Firebase free tier estimate ────────────────────────────────────────────
    est_reads  = daily.get("_est_reads",  sent_today * 3 + 50)
    est_writes = daily.get("_est_writes", sent_today * 2 + 10)

    subject = f"[Outreach] Daily report — {today}"

    body = f"""Daily pipeline run complete — {today}

━━━━━━━━ TODAY'S ACTIVITY ━━━━━━━━
  Initial emails  : {initial_sent}
  Followup 1      : {followup1_sent}
  Followup 2      : {followup2_sent}
  Followup 3      : {followup3_sent}
  ─────────────────────────────────
  Total today     : {sent_today}
  New replies     : {replied_today}
  Bounces         : {bounced_today}

━━━━━━━━ GEMINI USAGE TODAY ━━━━━━━━
  API calls       : {g_calls}
  Input tokens    : {g_in:,}
  Output tokens   : {g_out:,}
  Est. cost       : ${g_cost:.4f}  (free tier: 1,000,000 tokens/day)

━━━━━━━━ FIREBASE ESTIMATE ━━━━━━━━
  Reads today     : {build_bar(est_reads,  50_000)}
  Writes today    : {build_bar(est_writes, 20_000)}

━━━━━━━━ CUMULATIVE TOTALS ━━━━━━━━
  Sent            : {total_sent:,}
  Replied         : {total_replied:,}  ({reply_rate})
  Clicked         : {total_clicked:,}  ({click_rate})
  Bounced         : {total_bounced:,}  ({bounce_rate})

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Dashboard: {TRACKING_BASE}
"""

    payload = make_gmail_message(SENDER_EMAIL, NOTIFY_EMAIL, subject, body)
    try:
        service.users().messages().send(userId="me", body=payload).execute()
        print(f"Summary email sent to {NOTIFY_EMAIL}")
    except HttpError as e:
        print(f"Failed to send summary: {e}")


def main():
    db      = init_firebase()
    service = get_gmail_service()
    send_summary(service, db)


if __name__ == "__main__":
    main()
