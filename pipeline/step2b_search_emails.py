"""
Step 2b: Find emails for orgs that still have no email after website scraping.
Uses DuckDuckGo search (via `ddgs` package) to find emails in search snippets
and discover websites for orgs that have none.

Targets two groups:
  A) Has website but scraper found no email  → search "{org_name}" site email contact
  B) No website at all                        → search "{org_name}" {country} contact email

Then for any newly discovered website URL, does a quick scrape of that page too.

Input:  data/filtered_orgs.csv
Output: updates 'email' and 'website' columns in-place

Usage:
  py step2b_search_emails.py                  # all orgs missing email
  py step2b_search_emails.py --tier 1         # Tier1 only (~1,968 orgs, ~2 hours)
  py step2b_search_emails.py --tier 2
  py step2b_search_emails.py --limit 100      # stop after N orgs (for testing)

Notes:
  - Run sequentially (no parallel) to avoid DDG rate limits.
  - Run with --tier 1 first to get high-value contacts fast.
  - Checkpoint saved every 50 orgs — safe to Ctrl+C and resume.
  - Requires: pip install ddgs
"""

import pandas as pd
import requests
from bs4 import BeautifulSoup
import json
import os
import re
import sys
import time
import random
from urllib.parse import urlparse

from ddgs import DDGS

# ── Paths ──────────────────────────────────────────────────────────────────────
FILTERED_CSV = os.path.join(os.path.dirname(__file__), "..", "data", "filtered_orgs.csv")
CHECKPOINT   = os.path.join(os.path.dirname(__file__), "..", "data", "search_checkpoint.json")

# ── Config ─────────────────────────────────────────────────────────────────────
CHECKPOINT_EVERY = 50
SEARCH_DELAY     = 1.5   # seconds between DDG searches
MAX_RESULTS      = 5     # search results to inspect per org

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

EMAIL_RE = re.compile(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}')

JUNK_PATTERNS = re.compile(
    r'(@example\.|@sentry\.|@placeholder|@2x\.|\.png@|\.jpg@|\.gif@|'
    r'wix\.|wordpress\.|schema\.org|w3\.org|w3c\.org|noreply|no-reply|'
    r'@duckduck|@google\.|yourdomain|somerights|privacy)',
    re.IGNORECASE
)

PREFERRED_PREFIXES = [
    "coordinator", "director", "manager", "info",
    "contact", "office", "admin", "project", "education",
]

CONTACT_PATHS = ["/contact", "/contact-us", "/contacts", "/kontakt",
                 "/contacto", "/contatti", "/contact.html", "/en/contact", "/about"]

SKIP_DOMAINS = {"facebook.com", "linkedin.com", "twitter.com", "instagram.com",
                "youtube.com", "wikipedia.org", "europa.eu", "ec.europa.eu",
                "google.com", "bing.com", "duckduckgo.com"}


# ── Helpers ────────────────────────────────────────────────────────────────────

def is_junk(email: str) -> bool:
    if JUNK_PATTERNS.search(email):
        return True
    if any(ext in email.lower() for ext in [".png", ".jpg", ".gif", ".svg", ".ico", ".webp"]):
        return True
    local, domain = email.split("@", 1)
    if len(local) < 2 or "." not in domain:
        return True
    return False


def score_email(email: str) -> int:
    prefix = email.split("@")[0].lower()
    for i, kw in enumerate(PREFERRED_PREFIXES):
        if kw in prefix:
            return len(PREFERRED_PREFIXES) - i
    return 0


def extract_emails(text: str) -> list[str]:
    found = set()
    for m in EMAIL_RE.findall(text):
        m = m.lower()
        if not is_junk(m):
            found.add(m)
    return sorted(found, key=lambda e: (-score_email(e), e))


def scrape_website(url: str) -> list[str]:
    """Scrape a website homepage + /contact page for emails."""
    base = url.rstrip("/")
    pages = [base] + [base + p for p in CONTACT_PATHS[:4]]
    for page_url in pages:
        try:
            time.sleep(0.4)
            r = requests.get(page_url, headers=HEADERS, timeout=8, allow_redirects=True)
            if r.status_code < 400:
                soup = BeautifulSoup(r.text, "html.parser")
                emails = set()
                for a in soup.find_all("a", href=True):
                    if a["href"].lower().startswith("mailto:"):
                        e = a["href"][7:].split("?")[0].strip().lower()
                        if "@" in e and not is_junk(e):
                            emails.add(e)
                for m in EMAIL_RE.findall(soup.get_text(" ")):
                    m = m.lower()
                    if not is_junk(m):
                        emails.add(m)
                if emails:
                    return sorted(emails, key=lambda e: (-score_email(e), e))[:3]
        except Exception:
            pass
    return []


def ddg_search(query: str) -> list[dict]:
    """Run a DDG search, return list of result dicts with title/body/href."""
    try:
        time.sleep(SEARCH_DELAY + random.uniform(0, 0.8))
        with DDGS() as d:
            return list(d.text(query, max_results=MAX_RESULTS))
    except Exception as e:
        if "429" in str(e) or "rate" in str(e).lower():
            print("  [rate-limited — sleeping 30s]")
            time.sleep(30)
            try:
                with DDGS() as d:
                    return list(d.text(query, max_results=MAX_RESULTS))
            except Exception:
                pass
        return []


def process_org(org_name: str, country: str, website: str | None) -> dict:
    """
    Search DDG for an org's email.
    Returns dict: email, website, method
    """
    result = {"email": "", "website": website or "", "method": "none"}
    country = country if isinstance(country, str) else ""
    website_clean = website if (website and website not in ("", "nan")) else None

    # Build query
    org_clean = re.sub(r'[^\w\s\-]', ' ', org_name).strip()
    if website_clean:
        query = f'"{org_clean}" email contact'
    else:
        query = f'"{org_clean}" {country} contact email'

    results = ddg_search(query)
    if not results:
        return result

    # Collect all text from snippets
    all_text = " ".join(r.get("body", "") + " " + r.get("title", "") for r in results)
    emails = extract_emails(all_text)

    if emails:
        result["email"] = " | ".join(emails[:3])
        result["method"] = "snippet"
        return result

    # No email in snippets — find a website to scrape
    if not website_clean:
        for r in results:
            href = r.get("href", "")
            if not href:
                continue
            parsed = urlparse(href)
            if any(s in parsed.netloc for s in SKIP_DOMAINS):
                continue
            # Try scraping this discovered site
            emails = scrape_website(href)
            if emails:
                result["email"] = " | ".join(emails[:3])
                result["website"] = href
                result["method"] = "discovered_site"
                return result
            else:
                # Save discovered website even without email
                result["website"] = href
                result["method"] = "discovered_site_no_email"
                break  # only try the first non-junk URL
    else:
        # Has website but DDG snippets had no email — try harder on the website itself
        emails = scrape_website(website_clean)
        if emails:
            result["email"] = " | ".join(emails[:3])
            result["method"] = "site_scrape"

    return result


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    args        = sys.argv[1:]
    tier_filter = None
    limit       = None

    if "--tier" in args:
        idx = args.index("--tier")
        tier_filter = f"Tier{args[idx + 1]}"
    if "--limit" in args:
        idx = args.index("--limit")
        limit = int(args[idx + 1])

    print(f"Loading: {FILTERED_CSV}")
    df = pd.read_csv(FILTERED_CSV, low_memory=False, dtype={"email": str, "website": str})
    df["email"]   = df["email"].fillna("").astype(str).str.strip()
    df["website"] = df["website"].fillna("").astype(str).str.strip()
    df["notes"]   = df["notes"].fillna("").astype(str)
    print(f"  Total orgs: {len(df):,}")

    # ── Load checkpoint ───────────────────────────────────────────────────────
    checkpoint = {}
    if os.path.exists(CHECKPOINT):
        with open(CHECKPOINT, "r", encoding="utf-8") as f:
            checkpoint = json.load(f)
        print(f"  Checkpoint: {len(checkpoint):,} orgs already searched")
        for org_name, data in checkpoint.items():
            mask = df["org_name"] == org_name
            if mask.any():
                if data.get("email"):
                    df.loc[mask, "email"] = data["email"]
                if data.get("website"):
                    df.loc[mask, "website"] = data["website"]

    # ── Build work list ───────────────────────────────────────────────────────
    needs_email  = df["email"] == ""
    not_searched = ~df["org_name"].isin(checkpoint.keys())
    work_mask    = needs_email & not_searched

    if tier_filter:
        work_mask = work_mask & (df["tier"] == tier_filter)

    work = df[work_mask].copy()
    tier_order = {"Tier1": 0, "Tier2": 1, "Tier3": 2}
    work["_t"] = work["tier"].map(tier_order)
    work = work.sort_values(["_t", "relevance_score"], ascending=[True, False]).drop(columns=["_t"])

    if limit:
        work = work.head(limit)

    has_site = (work["website"] != "") & (work["website"] != "nan")
    print(f"  Orgs to search: {len(work):,}")
    if tier_filter:
        print(f"  Filtered to: {tier_filter}")
    print(f"    Has website (DDG search + re-scrape): {has_site.sum():,}")
    print(f"    No website (search by name):          {(~has_site).sum():,}")
    print()

    if len(work) == 0:
        print("  Nothing to do.")
        return

    # ── Sequential search (DDG rate-limit friendly) ───────────────────────────
    completed = 0
    found     = 0
    start_time = time.time()

    for _, row in work.iterrows():
        org_name = row["org_name"]
        country  = str(row.get("country", ""))
        website  = str(row.get("website", "")).strip()
        if website in ("", "nan"):
            website = None

        res = process_org(org_name, country, website)

        mask = df["org_name"] == org_name
        df.loc[mask, "email"]   = res["email"]
        df.loc[mask, "website"] = res["website"]
        checkpoint[org_name] = {"email": res["email"], "website": res["website"]}

        completed += 1
        if res["email"]:
            found += 1

        elapsed   = time.time() - start_time
        rate      = completed / elapsed if elapsed > 0 else 0
        remaining = (len(work) - completed) / rate if rate > 0 else 0

        method_tag = {
            "snippet":               "DDG",
            "site_scrape":           "re-scraped",
            "discovered_site":       "new-site",
            "discovered_site_no_email": "new-site(no email)",
            "none":                  "—",
        }.get(res["method"], res["method"])

        status = f"✓ {res['email'][:45]}  [{method_tag}]" if res["email"] else f"— [{method_tag}]"
        print(
            f"  [{completed}/{len(work)}] {org_name[:40]:<40} {status}  "
            f"({rate:.2f}/s, ~{remaining/60:.0f}min left)"
        )

        if completed % CHECKPOINT_EVERY == 0:
            with open(CHECKPOINT, "w", encoding="utf-8") as f:
                json.dump(checkpoint, f, ensure_ascii=False, indent=2)
            df.to_csv(FILTERED_CSV, index=False, encoding="utf-8-sig")
            hit_rate = found / completed * 100
            print(f"  [Checkpoint saved: {completed} done, {found} emails, {hit_rate:.0f}% hit rate]")

    # ── Final save ────────────────────────────────────────────────────────────
    with open(CHECKPOINT, "w", encoding="utf-8") as f:
        json.dump(checkpoint, f, ensure_ascii=False, indent=2)
    df.to_csv(FILTERED_CSV, index=False, encoding="utf-8-sig")

    elapsed = time.time() - start_time
    total_with_email = (df["email"].notna() & (df["email"].astype(str) != "")).sum()

    print(f"\n{'='*60}")
    print(f"Done in {elapsed/60:.1f} minutes")
    print(f"  Searched: {completed:,}  |  Found email: {found:,}  |  Hit rate: {found/max(completed,1)*100:.0f}%")
    print(f"  Total orgs with email: {total_with_email:,} / {len(df):,}")
    print(f"  Saved: {FILTERED_CSV}")


if __name__ == "__main__":
    main()
