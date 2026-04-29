"""
Step 2 (fast): Parallel email scraping from websites already in filtered_orgs.csv.
Uses ThreadPoolExecutor to scrape many orgs simultaneously.

Input:  data/filtered_orgs.csv  (with 'website' column from step1)
Output: updates 'email' column, saves checkpoint + filtered_orgs.csv

Usage:
  py step2_scrape_parallel.py              # default: 15 workers
  py step2_scrape_parallel.py --workers 20 # more aggressive
  py step2_scrape_parallel.py --tier 1     # only Tier1 orgs first
"""

import pandas as pd
import requests
from bs4 import BeautifulSoup
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin

FILTERED_CSV = os.path.join(os.path.dirname(__file__), "..", "data", "filtered_orgs.csv")
CHECKPOINT   = os.path.join(os.path.dirname(__file__), "..", "data", "emails_checkpoint.json")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

TIMEOUT          = 8       # seconds per request
CHECKPOINT_EVERY = 100     # save progress every N completions
DEFAULT_WORKERS  = 15      # concurrent threads

EMAIL_RE = re.compile(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}')

PREFERRED_PREFIXES = [
    "erasmus", "coordinator", "director", "manager", "info",
    "contact", "office", "admin", "project", "education", "hr",
]

JUNK_PATTERNS = re.compile(
    r'(@example\.|@sentry\.|@placeholder|@2x\.|\.png@|\.jpg@|\.gif@|'
    r'wix\.|wordpress\.|schema\.org|w3\.org|w3c\.org|\.ico@|noreply|no-reply)',
    re.IGNORECASE
)

CONTACT_PATHS = [
    "/contact", "/contact-us", "/contacts", "/kontakt",
    "/contacto", "/contatti", "/contact.html", "/en/contact",
    "/about", "/about-us", "/impressum",
]


def is_junk(email: str) -> bool:
    if JUNK_PATTERNS.search(email):
        return True
    if any(ext in email.lower() for ext in [".png", ".jpg", ".gif", ".svg", ".ico", ".webp"]):
        return True
    return False


def score_email(email: str) -> int:
    prefix = email.split("@")[0].lower()
    for i, kw in enumerate(PREFERRED_PREFIXES):
        if kw in prefix:
            return len(PREFERRED_PREFIXES) - i
    return 0


def extract_emails(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    emails = set()

    # mailto: links (highest confidence)
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.lower().startswith("mailto:"):
            email = href[7:].split("?")[0].strip().lower()
            if "@" in email and not is_junk(email):
                emails.add(email)

    # Regex on page text
    for match in EMAIL_RE.findall(soup.get_text(" ")):
        m = match.lower()
        if not is_junk(m):
            emails.add(m)

    return sorted(emails, key=lambda e: (-score_email(e), e))


def fetch(url: str) -> str | None:
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT,
                         allow_redirects=True)
        if r.status_code < 400:
            return r.text
    except Exception:
        pass
    return None


def scrape_org(org_name: str, website: str) -> list[str]:
    """Scrape emails for one org. Returns list of up to 3 emails."""
    base = website.rstrip("/")

    # Try homepage first
    html = fetch(base)
    if html:
        emails = extract_emails(html)
        if emails:
            return emails[:3]

    # Try contact-like sub-pages
    for path in CONTACT_PATHS:
        html = fetch(base + path)
        if html:
            emails = extract_emails(html)
            if emails:
                return emails[:3]

    return []


def main():
    # ── Parse args ────────────────────────────────────────────────────────────
    args = sys.argv[1:]
    workers = DEFAULT_WORKERS
    tier_filter = None

    if "--workers" in args:
        idx = args.index("--workers")
        workers = int(args[idx + 1])
    if "--tier" in args:
        idx = args.index("--tier")
        tier_filter = f"Tier{args[idx + 1]}"

    print(f"Loading: {FILTERED_CSV}")
    df = pd.read_csv(FILTERED_CSV, low_memory=False, dtype={"email": str, "website": str})
    df["email"] = df["email"].fillna("").astype(str)
    print(f"  Total orgs: {len(df):,}")

    # ── Load checkpoint ───────────────────────────────────────────────────────
    checkpoint = {}
    if os.path.exists(CHECKPOINT):
        with open(CHECKPOINT, "r", encoding="utf-8") as f:
            checkpoint = json.load(f)
        print(f"  Checkpoint: {len(checkpoint):,} orgs already done")

    # Apply checkpoint to df
    for org_name, data in checkpoint.items():
        mask = df["org_name"] == org_name
        if mask.any():
            df.loc[mask, "email"] = data.get("email", "")

    # ── Build work list ───────────────────────────────────────────────────────
    mask_has_site  = df["website"].notna() & (df["website"].astype(str).str.strip() != "")
    mask_needs_email = df["email"].isna() | (df["email"].astype(str).str.strip() == "")
    mask_not_done  = ~df["org_name"].isin(checkpoint.keys())

    work_mask = mask_has_site & (mask_needs_email | mask_not_done)
    if tier_filter:
        work_mask = work_mask & (df["tier"] == tier_filter)

    work = df[work_mask][["org_name", "website"]].dropna(subset=["website"])
    print(f"  Orgs to scrape: {len(work):,}  (workers={workers})")
    if tier_filter:
        print(f"  Filtered to: {tier_filter}")

    if len(work) == 0:
        print("  Nothing to do — all orgs already have emails or no website.")
        return

    # ── Parallel scrape ───────────────────────────────────────────────────────
    completed = 0
    found     = 0
    start_time = time.time()

    def worker(row):
        org_name = row["org_name"]
        website  = str(row["website"]).strip()
        if not website.startswith("http"):
            website = "https://" + website
        emails = scrape_org(org_name, website)
        return org_name, emails

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(worker, row): row["org_name"]
            for _, row in work.iterrows()
        }

        for future in as_completed(futures):
            org_name, emails = future.result()
            email_str = " | ".join(emails)

            df.loc[df["org_name"] == org_name, "email"] = email_str
            checkpoint[org_name] = {"email": email_str}

            completed += 1
            if emails:
                found += 1

            # Progress line
            elapsed = time.time() - start_time
            rate = completed / elapsed if elapsed > 0 else 0
            remaining = (len(work) - completed) / rate if rate > 0 else 0
            status = f"✓ {email_str[:50]}" if emails else "—"
            print(
                f"  [{completed}/{len(work)}] {org_name[:40]:<40} {status}  "
                f"({rate:.1f}/s, ~{remaining/60:.0f}min left)"
            )

            # Checkpoint save
            if completed % CHECKPOINT_EVERY == 0:
                with open(CHECKPOINT, "w", encoding="utf-8") as f:
                    json.dump(checkpoint, f, ensure_ascii=False, indent=2)
                df.to_csv(FILTERED_CSV, index=False, encoding="utf-8-sig")
                print(f"  [Saved checkpoint: {completed} done, {found} with email]")

    # ── Final save ────────────────────────────────────────────────────────────
    with open(CHECKPOINT, "w", encoding="utf-8") as f:
        json.dump(checkpoint, f, ensure_ascii=False, indent=2)
    df.to_csv(FILTERED_CSV, index=False, encoding="utf-8-sig")

    elapsed = time.time() - start_time
    total_with_email = (df["email"].notna() & (df["email"].astype(str) != "")).sum()

    print(f"\n{'='*60}")
    print(f"Done in {elapsed/60:.1f} minutes")
    print(f"  Scraped: {completed:,}  |  Found email: {found:,}  |  Hit rate: {found/completed*100:.0f}%")
    print(f"  Total orgs with email: {total_with_email:,} / {len(df):,}")
    print(f"  Saved: {FILTERED_CSV}")


if __name__ == "__main__":
    main()
