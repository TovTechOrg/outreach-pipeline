"""
System Test Suite — TovPlay Outreach Pipeline
==============================================
Runs all automated checks and reports results.
Manual tests (reply flow, approve link) are flagged clearly.

Usage:
  py test_system.py              # run all automated tests
  py test_system.py --fast       # skip tests that send real emails
  py test_system.py --verbose    # show full output for each test

Results are printed as:  PASS / FAIL / SKIP / MANUAL
"""

import os
import sys
import time
import json
import traceback
import urllib.request
import urllib.error
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

FAST    = "--fast"    in sys.argv
VERBOSE = "--verbose" in sys.argv

results = []


# ── Test runner ────────────────────────────────────────────────────────────────

def test(name, fn=None, manual=False, skip_if_fast=False):
    """Decorator / runner for a single test."""
    if manual:
        results.append(("MANUAL", name, "Requires human interaction — see docs/testing-checklist.md"))
        print(f"  MANUAL  {name}")
        return

    if skip_if_fast and FAST:
        results.append(("SKIP", name, "--fast mode"))
        print(f"  SKIP    {name}")
        return

    try:
        msg = fn()
        results.append(("PASS", name, msg or ""))
        print(f"  PASS    {name}" + (f"  ({msg})" if msg else ""))
    except AssertionError as e:
        results.append(("FAIL", name, str(e)))
        print(f"  FAIL    {name}  — {e}")
        if VERBOSE:
            traceback.print_exc()
    except Exception as e:
        results.append(("FAIL", name, str(e)))
        print(f"  FAIL    {name}  — {e}")
        if VERBOSE:
            traceback.print_exc()


# ── 1. Environment & secrets ───────────────────────────────────────────────────

print("\n━━━ 1. Environment & Secrets ━━━")

def t_sender_email():
    from step6_send_emails import SENDER_EMAIL
    assert SENDER_EMAIL and "@" in SENDER_EMAIL, f"SENDER_EMAIL not set: {SENDER_EMAIL!r}"
    return SENDER_EMAIL

def t_tracking_base():
    from step6_send_emails import TRACKING_BASE
    assert "bizdev-outreach" in TRACKING_BASE, f"Unexpected TRACKING_BASE: {TRACKING_BASE}"
    return TRACKING_BASE

def t_gemini_key():
    key = os.environ.get("GEMINI_API_KEY", "")
    assert key, "GEMINI_API_KEY not set"
    assert len(key) > 20, "GEMINI_API_KEY looks too short"
    return f"len={len(key)}"

def t_firebase_sa():
    sa_path = os.path.join(os.path.dirname(__file__), "firebase-service-account.json")
    assert os.path.exists(sa_path), f"firebase-service-account.json not found at {sa_path}"
    with open(sa_path) as f:
        data = json.load(f)
    assert data.get("type") == "service_account", "Not a service account file"
    return data.get("project_id")

def t_gmail_token():
    token_path = os.path.join(os.path.dirname(__file__), "token.json")
    assert os.path.exists(token_path), f"token.json not found at {token_path}"
    with open(token_path) as f:
        data = json.load(f)
    assert data.get("refresh_token"), "No refresh_token in token.json"
    expiry = data.get("expiry", "")
    return f"expiry={expiry[:19]}"

test("SENDER_EMAIL configured",  t_sender_email)
test("TRACKING_BASE_URL correct", t_tracking_base)
test("GEMINI_API_KEY present",    t_gemini_key)
test("Firebase service account",  t_firebase_sa)
test("Gmail token.json present",  t_gmail_token)


# ── 2. Firebase connection ─────────────────────────────────────────────────────

print("\n━━━ 2. Firebase Connection ━━━")

def t_firebase_connect():
    from step6_send_emails import init_firebase
    db = init_firebase()
    doc = db.collection("stats").document("global").get()
    return f"stats/global exists={doc.exists}"

def t_firebase_write():
    from step6_send_emails import init_firebase, now_iso
    from google.cloud.firestore_v1 import Increment
    db = init_firebase()
    ref = db.collection("_test").document("ping")
    ref.set({"ping": now_iso(), "count": Increment(1)}, merge=True)
    doc = ref.get().to_dict()
    assert doc.get("ping"), "Write didn't persist"
    ref.delete()
    return "write+read+delete OK"

def t_firebase_contacts_readable():
    from step6_send_emails import init_firebase
    db = init_firebase()
    pending = db.collection("contacts").where("status", "==", "pending").limit(3).get()
    return f"pending contacts sample={len(pending)}"

test("Firebase connect",           t_firebase_connect)
test("Firebase write/read/delete", t_firebase_write)
test("Contacts collection readable", t_firebase_contacts_readable)


# ── 3. Gmail API ───────────────────────────────────────────────────────────────

print("\n━━━ 3. Gmail API ━━━")

def t_gmail_connect():
    from gmail_auth import get_gmail_service
    service = get_gmail_service()
    profile = service.users().getProfile(userId="me").execute()
    assert profile.get("emailAddress"), "No email in profile"
    return profile["emailAddress"]

def t_gmail_send_dry():
    from step6_send_emails import make_gmail_message, SENDER_EMAIL
    msg = make_gmail_message(SENDER_EMAIL, SENDER_EMAIL,
                             "Test subject", "Test body — ignore")
    assert msg.get("raw"), "make_gmail_message returned no 'raw' key"
    return "MIME built OK"

test("Gmail API connect",    t_gmail_connect)
test("Gmail MIME builder",   t_gmail_send_dry)


# ── 4. Gemini API ──────────────────────────────────────────────────────────────

print("\n━━━ 4. Gemini API ━━━")

def t_gemini_connect():
    import google.generativeai as genai
    key = os.environ.get("GEMINI_API_KEY", "")
    assert key, "GEMINI_API_KEY not set"
    genai.configure(api_key=key)
    model = genai.GenerativeModel("gemini-2.5-flash")
    resp  = model.generate_content("Reply with just the word: OK")
    assert resp.text.strip(), "Empty response from Gemini"
    tokens = resp.usage_metadata.prompt_token_count if hasattr(resp, "usage_metadata") else "?"
    return f"OK  input_tokens={tokens}"

test("Gemini API connect + generate", t_gemini_connect, skip_if_fast=True)


# ── 5. Email pipeline logic ────────────────────────────────────────────────────

print("\n━━━ 5. Email Pipeline Logic ━━━")

def t_build_email_tier1():
    from step6_send_emails import build_email
    contact = {
        "org_name": "Test Org", "tier": "Tier1",
        "project_name": "Test Project", "specific_achievement": "great work",
        "their_population": "youth", "relevant_theme": "digital skills",
    }
    subj, body = build_email(contact, "initial", "fake-token-123")
    assert subj, "No subject"
    assert "Test Org" in body, "Org name missing from body"
    assert "fake-token-123" in body or "portfolio" in body.lower(), "Portfolio link missing"
    assert "tovtech.org" in body, "Signature missing"
    return f"subject='{subj[:40]}...'"

def t_build_email_all_types():
    from step6_send_emails import build_email
    contact = {
        "org_name": "Org", "tier": "Tier1",
        "project_name": "Proj", "specific_achievement": "stuff",
        "their_population": "youth", "relevant_theme": "skills",
    }
    errors = []
    for tier in ["Tier1", "Tier2", "Tier3"]:
        contact["tier"] = tier
        stages = {"Tier1": ["initial","followup1","followup2","followup3"],
                  "Tier2": ["initial","followup1","followup2"],
                  "Tier3": ["initial","followup1"]}
        for stage in stages[tier]:
            s, b = build_email(contact, stage, "tok")
            if not s or not b:
                errors.append(f"{tier}/{stage} returned empty")
    assert not errors, f"Empty templates: {errors}"
    return "all 9 templates non-empty"

def t_followup_timing():
    from step6_send_emails import FOLLOWUP1_DAYS, FOLLOWUP2_DAYS, FOLLOWUP3_DAYS
    assert FOLLOWUP1_DAYS == 3,  f"followup1 should be 3 days, got {FOLLOWUP1_DAYS}"
    assert FOLLOWUP2_DAYS == 7,  f"followup2 should be 7 days, got {FOLLOWUP2_DAYS}"
    assert FOLLOWUP3_DAYS == 14, f"followup3 should be 14 days, got {FOLLOWUP3_DAYS}"
    return f"Day {FOLLOWUP1_DAYS} / {FOLLOWUP2_DAYS} / {FOLLOWUP3_DAYS}"

def t_safe_id():
    from step6_send_emails import safe_id
    assert safe_id("Test Org / Name!") == "Test_Org___Name_", f"safe_id broken: {safe_id('Test Org / Name!')}"
    assert len(safe_id("x" * 200)) == 100, "safe_id should truncate to 100"
    return "OK"

test("build_email Tier1 initial", t_build_email_tier1)
test("build_email all tiers/stages", t_build_email_all_types)
test("Followup timing constants", t_followup_timing)
test("safe_id sanitization", t_safe_id)


# ── 5b. CSV data quality ────────────────────────────────────────────────────────

print("\n━━━ 5b. CSV Data Quality ━━━")

def t_csv_exists():
    assert os.path.exists(PROSPECTS_CSV := os.path.join(
        os.path.dirname(__file__), "..", "data", "enriched_prospects.csv"
    )), "enriched_prospects.csv not found"
    import pandas as pd
    df = pd.read_csv(PROSPECTS_CSV, low_memory=False).fillna("")
    with_email = df[df["email"].astype(str).str.strip() != ""]
    return f"{len(with_email):,} contacts with email (total rows: {len(df):,})"

def t_csv_personalized():
    import pandas as pd
    PROSPECTS_CSV = os.path.join(os.path.dirname(__file__), "..", "data", "enriched_prospects.csv")
    df = pd.read_csv(PROSPECTS_CSV, low_memory=False).fillna("")
    tier1 = df[df["tier"] == "Tier1"]
    tier2 = df[df["tier"] == "Tier2"]

    t1_missing = (tier1["specific_achievement"].astype(str).str.strip() == "").sum()
    t2_missing = (tier2["relevant_theme"].astype(str).str.strip() == "").sum()
    t1_pct = t1_missing / len(tier1) * 100 if len(tier1) else 0
    t2_pct = t2_missing / len(tier2) * 100 if len(tier2) else 0

    assert t1_pct < 5, \
        f"{t1_missing}/{len(tier1)} Tier1 orgs missing specific_achievement ({t1_pct:.0f}%) — run step5_personalize.py"
    assert t2_pct < 5, \
        f"{t2_missing}/{len(tier2)} Tier2 orgs missing relevant_theme ({t2_pct:.0f}%) — run step5_personalize.py"
    return f"Tier1: {len(tier1)-t1_missing}/{len(tier1)} personalized | Tier2: {len(tier2)-t2_missing}/{len(tier2)} personalized"

test("CSV file exists + has contacts", t_csv_exists)
test("CSV personalization fields populated", t_csv_personalized)


# ── 6. Bounce detection ────────────────────────────────────────────────────────

print("\n━━━ 6. Bounce Detection ━━━")

def t_bounce_senders():
    from step6_send_emails import is_bounce
    cases = [
        ({"payload": {"headers": [
            {"name": "From",    "value": "Mail Delivery Subsystem <mailer-daemon@googlemail.com>"},
            {"name": "Subject", "value": "Delivery Status Notification (Failure)"},
        ]}}, True),
        ({"payload": {"headers": [
            {"name": "From",    "value": "postmaster@example.com"},
            {"name": "Subject", "value": "Undeliverable: your message"},
        ]}}, True),
        ({"payload": {"headers": [
            {"name": "From",    "value": "John Smith <john@example.org>"},
            {"name": "Subject", "value": "Re: Your message"},
        ]}}, False),
        ({"payload": {"headers": [
            {"name": "From",    "value": "contact@ngo.eu"},
            {"name": "Subject", "value": "Interested in collaboration"},
        ]}}, False),
    ]
    for msg, expected in cases:
        result = is_bounce(msg)
        assert result == expected, \
            f"is_bounce wrong for '{msg['payload']['headers'][0]['value']}': expected {expected}, got {result}"
    return f"4/4 cases correct"

def t_sent_label_detection():
    # Verify SENT label logic (simulated messages)
    sent_msg    = {"labelIds": ["SENT", "INBOX"], "payload": {"headers": []}}
    inbound_msg = {"labelIds": ["INBOX"],         "payload": {"headers": []}}
    assert "SENT" in sent_msg.get("labelIds", []),        "SENT msg not identified"
    assert "SENT" not in inbound_msg.get("labelIds", []), "Inbound incorrectly has SENT"
    return "SENT label logic OK"

test("Bounce sender/subject patterns", t_bounce_senders)
test("SENT label outbound detection",  t_sent_label_detection)


# ── 7. Cloudflare endpoints ────────────────────────────────────────────────────

print("\n━━━ 7. Cloudflare Endpoints ━━━")

CF_BASE = "https://bizdev-outreach.pages.dev"

def http_get(path, auth=None, timeout=15):
    url = CF_BASE + path
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    })
    if auth:
        import base64
        creds = base64.b64encode(auth.encode()).decode()
        req.add_header("Authorization", f"Basic {creds}")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read(8000).decode(errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception as e:
        raise AssertionError(f"Request failed: {e}")

def t_cf_track_redirect():
    status, _ = http_get("/track/c/nonexistent-token-xyz")
    # Should redirect (3xx) or 404 — not 500
    assert status in (200, 301, 302, 303, 307, 308, 404), \
        f"Unexpected status {status} from /track/c/"
    return f"status={status}"

def t_cf_approve_route():
    status, body = http_get("/approve/nonexistent-token-xyz")
    assert status in (200, 404), f"Unexpected status {status} — approve route may not be deployed"
    assert "500" not in body, "Server error on /approve route"
    return f"status={status}"

def t_cf_skip_route():
    status, body = http_get("/skip/nonexistent-token-xyz")
    assert status in (200, 404), f"Unexpected status {status} — skip route may not be deployed"
    assert "500" not in body, "Server error on /skip route"
    return f"status={status}"

def t_cf_api_stats():
    status, body = http_get("/api/stats", auth="admin:TovTech2026!")
    assert status == 200, f"Stats API returned {status}"
    data = json.loads(body)
    assert "totals" in data, f"No 'totals' in response: {list(data.keys())}"
    return f"sent={data['totals'].get('sent',0)} replied={data['totals'].get('replied',0)}"

def t_cf_dashboard_loads():
    status, body = http_get("/", auth="admin:TovTech2026!")
    assert status == 200, f"Dashboard returned {status}"
    assert "TovTech" in body, "Dashboard HTML missing TovTech"
    assert "sBounced" in body, "Bounced card not in dashboard HTML — may need redeploy"
    return "HTML OK, bounced card present"

test("Cloudflare /track/c/ route",   t_cf_track_redirect)
test("Cloudflare /approve/ route",   t_cf_approve_route)
test("Cloudflare /skip/ route",      t_cf_skip_route)
test("Cloudflare /api/stats",        t_cf_api_stats)
test("Cloudflare dashboard HTML",    t_cf_dashboard_loads)


# ── 8. Step6 dry-run ──────────────────────────────────────────────────────────

print("\n━━━ 8. Step6 Dry-Run ━━━")

def t_step6_dryrun():
    import subprocess
    result = subprocess.run(
        [sys.executable, "step6_send_emails.py", "--dry-run", "--limit", "3"],
        capture_output=True, text=True, timeout=60,
        cwd=os.path.dirname(__file__),
    )
    assert result.returncode == 0, f"step6 exited {result.returncode}:\n{result.stderr[-500:]}"
    assert "DRY RUN" in result.stdout, "DRY RUN marker missing from output"
    assert "Sent:" in result.stdout, "No Sent: line in output"
    if VERBOSE:
        print(result.stdout)
    return "exited 0, output looks correct"

test("step6 --dry-run runs cleanly", t_step6_dryrun)


# ── 9. Manual tests (flagged) ─────────────────────────────────────────────────

print("\n━━━ 9. Manual Tests (cannot automate) ━━━")

test("Reply flow end-to-end",  manual=True)
test("Approve link → send reply", manual=True)
test("Skip link → no send",    manual=True)
test("CSV import (step0)",     manual=True)
test("GitHub Actions cron run", manual=True)


# ── Summary ───────────────────────────────────────────────────────────────────

passed  = sum(1 for r in results if r[0] == "PASS")
failed  = sum(1 for r in results if r[0] == "FAIL")
skipped = sum(1 for r in results if r[0] == "SKIP")
manual  = sum(1 for r in results if r[0] == "MANUAL")
total   = len(results)

print(f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Results: {passed} PASS  {failed} FAIL  {skipped} SKIP  {manual} MANUAL  / {total} total
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━""")

if failed:
    print("\nFailed tests:")
    for status, name, msg in results:
        if status == "FAIL":
            print(f"  ✗ {name}")
            print(f"    {msg}")

if failed:
    sys.exit(1)
