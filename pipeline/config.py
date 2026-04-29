"""
Global configuration for the outreach pipeline.
Change values here — all scripts pick them up automatically.
"""

import os

# ── Sending ────────────────────────────────────────────────────────────────────

SENDER_EMAIL = os.environ.get("SENDER_EMAIL", "your@email.com")
NOTIFY_EMAIL = os.environ.get("NOTIFY_EMAIL", "notify@email.com")
DAILY_LIMIT      = int(os.environ.get("DAILY_LIMIT", "20"))
DAILY_PER_TIER   = int(os.environ.get("DAILY_PER_TIER", "4"))
DAILY_INITIAL    = int(os.environ.get("DAILY_INITIAL", "12"))
DAILY_FOLLOWUP   = int(os.environ.get("DAILY_FOLLOWUP", "0"))  # follow-ups disabled

# ── URLs ───────────────────────────────────────────────────────────────────────

TRACKING_BASE = os.environ.get("TRACKING_BASE_URL", "https://your-project.pages.dev")
PORTFOLIO_URL = "https://your-portfolio-url.com/"

# ── AI model ───────────────────────────────────────────────────────────────────

GEMINI_MODEL = "gemini-2.5-flash"

# ── Follow-up cadence (days after previous email) ─────────────────────────────

FOLLOWUP1_DAYS = 3
FOLLOWUP2_DAYS = 7
FOLLOWUP3_DAYS = 14

# ── Signatures ─────────────────────────────────────────────────────────────────
# SIG_FULL  — initial outreach (formal, with title + OID)
# SIG_MID   — follow-up emails (compact, still branded)
# SIG_SLIM  — breakup / last-touch emails (minimal)

SIG_FULL = (
    "Your Name\n"
    "CEO, Your Org | yourorg.com\n"
    "Partnership ID: XXXXXXXX"  # Optional — add any relevant credential or remove this line
)

SIG_MID = "Your Name | Your Org | yourorg.com"

SIG_SLIM = "Your Name | you@yourorg.com | yourorg.com"

# ── Hebrew signatures (custom campaign) ──────────────────────────────────────

SIG_HE_FULL = (
    "שמך\n"
    "הארגון שלך | yourorg.com\n"
    "05X-XXXXXXX | you@yourorg.com"
)

SIG_HE_SLIM = "שמך | הארגון שלך | yourorg.com\n05X-XXXXXXX | you@yourorg.com"

SIG_HE_LAST = "שמך | you@yourorg.com | yourorg.com"

# ── Bounce detection patterns ─────────────────────────────────────────────────

BOUNCE_SENDERS = (
    "mailer-daemon", "postmaster@", "noreply@bounce", "bounce@",
    "delivery@", "mail-noreply@google",
)

BOUNCE_SUBJECTS = (
    "delivery status notification", "undeliverable",
    "mail delivery failed", "delivery failure",
    "returned mail", "failure notice", "mail delivery subsystem",
)
