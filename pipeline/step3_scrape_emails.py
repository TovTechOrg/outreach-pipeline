"""
Step 3: Scrape email addresses from organization websites.
Input:  data/filtered_orgs.csv  (with 'website' column populated)
Output: updates 'email' column, saves data/emails_checkpoint.json + data/filtered_orgs.csv
"""

import pandas as pd
import requests
from bs4 import BeautifulSoup
import json
import os
import re
import time
from urllib.parse import urljoin, urlparse

FILTERED_CSV = os.path.join(os.path.dirname(__file__), "..", "data", "filtered_orgs.csv")
CHECKPOINT   = os.path.join(os.path.dirname(__file__), "..", "data", "emails_checkpoint.json")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

TIMEOUT = 10
SLEEP_BETWEEN = 2.0
CHECKPOINT_EVERY = 50

EMAIL_RE = re.compile(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}')

# Email fragments that indicate a good/relevant contact
PREFERRED_PREFIXES = [
    "erasmus", "coordinator", "director", "manager", "info",
    "contact", "office", "admin", "project", "education",
]

# Junk email patterns to exclude
JUNK_PATTERNS = [
    r"@example\.", r"@sentry\.", r"@placeholder", r"@2x\.",
    r"\.png@", r"\.jpg@", r"\.gif@", r"wix\.", r"wordpress\.",
    r"schema\.org", r"w3\.org",
]

# Contact-like subpages to try (multi-language)
CONTACT_PAGES = [
    "/contact", "/contact-us", "/contacts", "/kontakt",
    "/contacto", "/contatti", "/contact.html", "/about",
    "/about-us", "/impressum", "/en/contact",
]


def is_junk_email(email: str) -> bool:
    email_lower = email.lower()
    for pattern in JUNK_PATTERNS:
        if re.search(pattern, email_lower):
            return True
    # Skip if looks like a file path or image reference
    if any(ext in email_lower for ext in [".png", ".jpg", ".gif", ".svg", ".ico"]):
        return True
    return False


def score_email(email: str) -> int:
    """Higher score = better candidate for outreach."""
    prefix = email.split("@")[0].lower()
    for i, kw in enumerate(PREFERRED_PREFIXES):
        if kw in prefix:
            return len(PREFERRED_PREFIXES) - i
    return 0


def extract_emails_from_html(html: str) -> list[str]:
    """Extract and clean email addresses from HTML text."""
    soup = BeautifulSoup(html, "html.parser")

    emails = set()

    # mailto: links (highest confidence)
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.startswith("mailto:"):
            email = href[7:].split("?")[0].strip()
            if email and "@" in email:
                emails.add(email.lower())

    # Regex across all text
    text = soup.get_text(" ")
    for match in EMAIL_RE.findall(text):
        emails.add(match.lower())

    # Filter junk
    emails = [e for e in emails if not is_junk_email(e)]

    # Sort: preferred prefixes first, then alphabetically
    emails = sorted(emails, key=lambda e: (-score_email(e), e))

    return emails[:3]  # return top 3


def fetch_page(url: str) -> str | None:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
        if resp.status_code < 400:
            return resp.text
    except Exception:
        pass
    return None


def scrape_emails(base_url: str) -> list[str]:
    """Try homepage + contact pages and return best emails found."""
    all_emails: list[str] = []

    # Homepage
    html = fetch_page(base_url)
    if html:
        all_emails.extend(extract_emails_from_html(html))

    if all_emails:
        return all_emails[:3]  # found on homepage, stop here

    # Try contact sub-pages
    base = base_url.rstrip("/")
    for page in CONTACT_PAGES:
        url = base + page
        html = fetch_page(url)
        if html:
            emails = extract_emails_from_html(html)
            if emails:
                all_emails.extend(emails)
                break  # found emails, stop trying pages
        time.sleep(0.5)

    # Deduplicate while preserving order/score
    seen = set()
    result = []
    for e in all_emails:
        if e not in seen:
            seen.add(e)
            result.append(e)

    return result[:3]


def main():
    print(f"Loading: {FILTERED_CSV}")
    df = pd.read_csv(FILTERED_CSV, low_memory=False)
    print(f"  Total orgs: {len(df):,}")

    # Load checkpoint
    checkpoint = {}
    if os.path.exists(CHECKPOINT):
        with open(CHECKPOINT, "r", encoding="utf-8") as f:
            checkpoint = json.load(f)
        print(f"  Checkpoint loaded: {len(checkpoint):,} orgs already processed")

    # Apply checkpoint data
    for org_name, data in checkpoint.items():
        mask = df["org_name"] == org_name
        if mask.any():
            df.loc[mask, "email"] = data.get("email", "")

    # Only process orgs that have a website but no email yet
    needs_email = df[
        df["website"].notna() &
        (df["website"] != "") &
        (df["email"].isna() | (df["email"] == ""))
    ]["org_name"].tolist()

    print(f"  Orgs with website, no email yet: {len(needs_email):,}")

    processed = 0
    found = 0

    for org_name in needs_email:
        row = df[df["org_name"] == org_name].iloc[0]
        website = str(row["website"]).strip()

        if not website.startswith("http"):
            website = "https://" + website

        print(f"  [{processed+1}/{len(needs_email)}] {org_name[:50]}...", end=" ", flush=True)

        emails = scrape_emails(website)
        email_str = " | ".join(emails)

        df.loc[df["org_name"] == org_name, "email"] = email_str
        checkpoint[org_name] = {"email": email_str}

        if emails:
            print(f"→ {email_str[:70]}")
            found += 1
        else:
            print("→ no email found")

        processed += 1

        if processed % CHECKPOINT_EVERY == 0:
            with open(CHECKPOINT, "w", encoding="utf-8") as f:
                json.dump(checkpoint, f, ensure_ascii=False, indent=2)
            df.to_csv(FILTERED_CSV, index=False, encoding="utf-8-sig")
            print(f"  [Checkpoint saved: {processed} processed, {found} with email]")

        time.sleep(SLEEP_BETWEEN)

    # Final save
    with open(CHECKPOINT, "w", encoding="utf-8") as f:
        json.dump(checkpoint, f, ensure_ascii=False, indent=2)
    df.to_csv(FILTERED_CSV, index=False, encoding="utf-8-sig")

    print(f"\nDone. Found emails for {found:,} / {len(needs_email):,} orgs.")
    total_with_email = (df["email"].notna() & (df["email"] != "")).sum()
    print(f"Total orgs with email: {total_with_email:,} / {len(df):,}")


if __name__ == "__main__":
    main()
