"""
Test: send one tracked email → verify Firebase logged it → verify dashboard shows it.
Run: py test_send.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import uuid
from step6_send_emails import (
    init_firebase, make_click_token, send_email, log_event, update_stats,
    PORTFOLIO_URL, TRACKING_BASE, SENDER_EMAIL
)
from gmail_auth import get_gmail_service

TEST_TO   = "hrazhadas@gmail.com"
TEST_ORG  = "_TEST_ORG_"

db      = init_firebase()
service = get_gmail_service()

# Create click token
token = make_click_token(db, TEST_ORG, PORTFOLIO_URL)
link      = f"{TRACKING_BASE}/track/c/{token}"
link_html = f'<a href="{link}">click here to test tracking →</a>'

subject = "[TEST] TovPlay dashboard + click tracking verification"
body = f"""Hi,

This is a test email to verify the full TovPlay outreach pipeline.

To test click counting: {link_html}

Then check the dashboard: https://bizdev-outreach.pages.dev
Login: admin / TovTech2026!

You should see:
- "Sent" counter increased by 1
- After clicking the link above: "Clicked" counter increased by 1

Raz | TovTech"""

print(f"Sending test email to {TEST_TO}...")
msg_id, thread_id = send_email(service, SENDER_EMAIL, TEST_TO, subject, body)

if msg_id:
    log_event(db, TEST_ORG, "initial_sent", {"to": TEST_TO, "subject": subject, "thread_id": thread_id})
    update_stats(db, "initial_sent", "Tier1")
    print(f"  Message ID  : {msg_id}")
    print(f"  Thread ID   : {thread_id}")
    print(f"  Click token : {token}")
    print(f"  Click link  : {link}")
    print()
    print("Now:")
    print("  1. Open hrazhadas@gmail.com and click the link in the email")
    print("  2. Check dashboard: https://bizdev-outreach.pages.dev")
    print("     Login: admin / TovTech2026!")
    print("     Sent should = old+1, Clicked should = old+1 after clicking")
else:
    print("ERROR: failed to send email")
    sys.exit(1)
