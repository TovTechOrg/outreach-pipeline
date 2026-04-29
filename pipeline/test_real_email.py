"""
Send a realistic production-quality test email to hrazhadas@gmail.com.
Uses exact same build_email + make_gmail_message as step6, with real org data.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from step6_send_emails import (
    init_firebase, make_click_token, build_email, send_email, log_event,
    update_stats, PORTFOLIO_URL, TRACKING_BASE, SENDER_EMAIL
)
from gmail_auth import get_gmail_service

TEST_TO = "hrazhadas@gmail.com"

# Real Tier1 org data — exactly as step6 would process it
contact = {
    "org_name": "Youmore APS",
    "email": TEST_TO,  # override to test address
    "country": "IT",
    "tier": "Tier1",
    "project_name": "Unlocking Rural Youth Potential",
    "specific_achievement": "your work addressing youth unemployment in rural areas through skills training and labor market integration",
    "their_population": "rural youth facing limited job opportunities",
    "relevant_theme": "youth employment and digital skills",
}

db      = init_firebase()
service = get_gmail_service()

# Create tracking token (same as step6 does)
token = make_click_token(db, contact["org_name"], PORTFOLIO_URL)
subject, body = build_email(contact, "initial", token)

print(f"To: {TEST_TO}")
print(f"From: {SENDER_EMAIL}")
print(f"Subject: {subject}")
print(f"---")
print(body)
print(f"---")
print()

msg_id, thread_id = send_email(service, SENDER_EMAIL, TEST_TO, subject, body)
if msg_id:
    log_event(db, contact["org_name"], "test_sent", {"to": TEST_TO})
    update_stats(db, "initial_sent", "Tier1")
    print(f"Sent! Message ID: {msg_id}")
else:
    print("FAILED to send")
    sys.exit(1)
