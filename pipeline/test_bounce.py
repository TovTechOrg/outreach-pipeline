"""
Bounce Detection Test
=====================
Sends a test email to a non-existent address, waits for the bounce,
then runs the bounce detection logic and reports results.

Usage:
  py test_bounce.py
"""

import sys
import time
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from step6_send_emails import (
    init_firebase, send_email, make_click_token,
    get_thread_metadata, is_bounce, _msg_headers,
    SENDER_EMAIL, PORTFOLIO_URL,
)
from gmail_auth import get_gmail_service

# A clearly invalid address — no MX records on example.com, will hard-bounce
TEST_BOUNCE_EMAIL = "nobody-xyz-test-invalid@example.com"

WAIT_SECONDS = 90   # bounce usually arrives within 30-90 seconds


def main():
    db      = init_firebase()
    service = get_gmail_service()

    print(f"Sending test email to: {TEST_BOUNCE_EMAIL}")
    print(f"(From: {SENDER_EMAIL})\n")

    msg_id, thread_id = send_email(
        service, SENDER_EMAIL, TEST_BOUNCE_EMAIL,
        subject="Test — bounce detection",
        body="This is an automated bounce detection test. Please ignore.",
    )

    if not msg_id:
        print("ERROR: failed to send email")
        sys.exit(1)

    print(f"Sent. Thread ID: {thread_id}")
    print(f"Waiting {WAIT_SECONDS}s for bounce to arrive...\n")

    for i in range(WAIT_SECONDS, 0, -10):
        print(f"  {i}s remaining...", end="\r")
        time.sleep(10)

    print("\n\nChecking thread for bounce...")

    messages = get_thread_metadata(service, thread_id)
    print(f"  Messages in thread: {len(messages)}")

    if len(messages) <= 1:
        print("\n  No reply yet — bounce may take longer.")
        print("  Try running: py test_bounce.py --check-only <thread_id>")
        print(f"  Thread ID: {thread_id}")
        sys.exit(0)

    for i, msg in enumerate(messages):
        h       = _msg_headers(msg)
        sender  = h.get("from", "(unknown)")
        subject = h.get("subject", "(no subject)")
        bounce  = is_bounce(msg)
        marker  = "✓ BOUNCE DETECTED" if bounce else "  (not a bounce)"
        print(f"\n  Message {i+1}:")
        print(f"    From   : {sender}")
        print(f"    Subject: {subject}")
        print(f"    Result : {marker}")

    inbound = [m for m in messages if "SENT" not in m.get("labelIds", [])]

    if inbound and is_bounce(inbound[0]):
        print("\nPASS — bounce correctly detected")
    elif not inbound:
        print("\nINFO — no inbound message yet (try again in a few minutes)")
    else:
        print("\nFAIL — inbound message not recognized as bounce")
        print("  Check BOUNCE_SENDERS / BOUNCE_SUBJECTS in step6_send_emails.py")


if __name__ == "__main__":
    main()
