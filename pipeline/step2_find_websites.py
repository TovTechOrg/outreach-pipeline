"""
Step 2: Find organization websites via DuckDuckGo HTML search.
Input:  data/filtered_orgs.csv
Output: updates 'website' column, saves data/websites_checkpoint.json + data/filtered_orgs.csv
"""

import pandas as pd
import requests
from bs4 import BeautifulSoup
import json
import os
import time
import re
from urllib.parse import urlparse, quote_plus

FILTERED_CSV  = os.path.join(os.path.dirname(__file__), "..", "data", "filtered_orgs.csv")
CHECKPOINT    = os.path.join(os.path.dirname(__file__), "..", "data", "websites_checkpoint.json")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

# Domains to skip in search results
SKIP_DOMAINS = {
    # Add source-database domains here so they're skipped in search results
    # e.g. "yourdatabase.ec.europa.eu",
    "ec.europa.eu",
    "facebook.com",
    "linkedin.com",
    "twitter.com",
    "youtube.com",
    "wikipedia.org",
    "instagram.com",
    "google.com",
}

MAX_SEARCH_RESULTS = 5   # check up to N results per org
SLEEP_BETWEEN = 2.0       # seconds between DuckDuckGo requests
TIMEOUT = 10              # HTTP timeout in seconds
CHECKPOINT_EVERY = 50     # save checkpoint every N orgs


def ddg_search(query: str) -> list[str]:
    """Search DuckDuckGo HTML and return list of result URLs."""
    url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        resp.raise_for_status()
    except Exception as e:
        print(f"    DDG search error: {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    urls = []
    for a in soup.select("a.result__url"):
        href = a.get("href", "").strip()
        if href and href.startswith("http"):
            urls.append(href)
    # Also try result__a links
    if not urls:
        for a in soup.select("a.result__a"):
            href = a.get("href", "").strip()
            if href and href.startswith("http"):
                urls.append(href)
    return urls[:MAX_SEARCH_RESULTS]


def is_skip_domain(url: str) -> bool:
    try:
        domain = urlparse(url).netloc.lower().lstrip("www.")
        return any(skip in domain for skip in SKIP_DOMAINS)
    except Exception:
        return True


def validate_url(url: str, org_name: str) -> bool:
    """Quick check: does the page load and contain a fragment of the org name?"""
    # Use first significant word of org name (>3 chars)
    words = [w for w in re.split(r'\W+', org_name) if len(w) > 3]
    if not words:
        return True  # can't validate, assume ok

    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
        if resp.status_code >= 400:
            return False
        text = resp.text.lower()
        # At least 1 significant word from org name appears on page
        return any(w.lower() in text for w in words[:3])
    except Exception:
        return False


def find_website(org_name: str, country: str) -> str:
    """Return best website URL for the org, or empty string."""
    query = f'"{org_name}" {country}'
    urls = ddg_search(query)

    for url in urls:
        if is_skip_domain(url):
            continue
        # Light validation: just check the URL loads
        try:
            resp = requests.head(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
            if resp.status_code < 400:
                return url
        except Exception:
            continue

    # Fallback: broader search without quotes
    if not urls:
        query2 = f"{org_name} {country} official site"
        urls2 = ddg_search(query2)
        for url in urls2:
            if is_skip_domain(url):
                continue
            try:
                resp = requests.head(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
                if resp.status_code < 400:
                    return url
            except Exception:
                continue

    return ""


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

    # Apply checkpoint data back to df
    for org_name, data in checkpoint.items():
        mask = df["org_name"] == org_name
        if mask.any():
            df.loc[mask, "website"] = data.get("website", "")

    # Count how many still need websites
    need_website = df[df["website"].isna() | (df["website"] == "")]["org_name"].tolist()
    print(f"  Need website lookup: {len(need_website):,}")

    processed = 0
    found = 0

    for org_name in need_website:
        row = df[df["org_name"] == org_name].iloc[0]
        country = str(row.get("country", ""))

        print(f"  [{processed+1}/{len(need_website)}] {org_name[:60]}...", end=" ", flush=True)

        website = find_website(org_name, country)
        df.loc[df["org_name"] == org_name, "website"] = website

        if website:
            print(f"→ {website[:60]}")
            found += 1
        else:
            print("→ not found")

        checkpoint[org_name] = {"website": website}
        processed += 1

        # Save checkpoint periodically
        if processed % CHECKPOINT_EVERY == 0:
            with open(CHECKPOINT, "w", encoding="utf-8") as f:
                json.dump(checkpoint, f, ensure_ascii=False, indent=2)
            df.to_csv(FILTERED_CSV, index=False, encoding="utf-8-sig")
            print(f"  [Checkpoint saved at {processed} orgs, {found} found so far]")

        time.sleep(SLEEP_BETWEEN)

    # Final save
    with open(CHECKPOINT, "w", encoding="utf-8") as f:
        json.dump(checkpoint, f, ensure_ascii=False, indent=2)
    df.to_csv(FILTERED_CSV, index=False, encoding="utf-8-sig")

    print(f"\nDone. Found websites for {found:,} / {len(need_website):,} orgs.")
    print(f"Total with website: {df['website'].notna().sum():,} / {len(df):,}")


if __name__ == "__main__":
    main()
