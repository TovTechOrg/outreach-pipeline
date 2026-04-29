"""
Step 1: Filter, deduplicate, and score Erasmus+ organizations.
Input:  CSV file from Erasmus+ project database
Output: data/filtered_orgs.csv
"""

import pandas as pd
import re
import os
import sys

# ── Config ────────────────────────────────────────────────────────────────────

CSV_PATH = os.path.join(os.path.dirname(__file__), "..",
    "ErasmusPlus_KA1_2025_LearningMobilityOfIndividuals_Projects_Overview_2026-03-03.csv")
OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "filtered_orgs.csv")

# Org types to include
TARGET_ORG_TYPES = [
    "Non-governmental organisation/association/social enterprise",
    "School/Institute/Educational centre – Vocational Training (secondary level)",
    "School/Institute/Educational centre – Vocational Training (tertiary level)",
    "School/Institute/Educational centre – Adult education",
    "Foundation",
    "Local Public body",
    "Regional Public body",
]

# Scoring keywords (checked against project titles + summaries, case-insensitive)
KEYWORDS = {
    "disability": 3,
    "disabilities": 3,
    "disabled": 3,
    "handicap": 3,
    "special needs": 3,
    "impairment": 2,
    "autism": 2,
    "employment": 2,
    "employability": 2,
    "job": 2,
    "work": 1,
    "vocational": 2,
    "vet ": 2,
    "youth": 2,
    "young": 1,
    "adult learning": 2,
    "digital": 1,
    "artificial intelligence": 2,
    " ai ": 1,
    "technology": 1,
    "innovation": 1,
    "inclusion": 2,
    "inclusive": 2,
    "social enterprise": 1,
}

def score_text(text: str) -> int:
    if not isinstance(text, str):
        return 0
    text_lower = text.lower()
    total = 0
    for kw, pts in KEYWORDS.items():
        if kw in text_lower:
            total += pts
    return total

def tier_from_score(score: int) -> str:
    if score >= 5:
        return "Tier1"
    elif score >= 2:
        return "Tier2"
    return "Tier3"

def outreach_strategy(tier: str) -> str:
    strategies = {
        "Tier1": "Strategy 1+4: Expert advice request + Erasmus+ future partner angle",
        "Tier2": "Strategy 3+2: Content gift email + pilot partnership offer",
        "Tier3": "Strategy 3: Content gift email (simple, no deep personalization needed)",
    }
    return strategies.get(tier, "")

def main():
    print(f"Loading CSV: {CSV_PATH}")
    df = pd.read_csv(CSV_PATH, low_memory=False)
    print(f"  Total rows: {len(df):,}")

    # ── Filter by org type ────────────────────────────────────────────────────
    mask = df["Coordinating organisation type"].isin(TARGET_ORG_TYPES)
    df_filtered = df[mask].copy()
    print(f"  After org-type filter: {len(df_filtered):,} rows")

    # ── Score each row ────────────────────────────────────────────────────────
    combined_text = (
        df_filtered["Project Title"].fillna("") + " " +
        df_filtered["Project Summary"].fillna("")
    )
    df_filtered["_score"] = combined_text.apply(score_text)

    # ── Pull website — prefer Coordinator's website (14,200 values), fallback Project Website
    def clean_url(s):
        if not isinstance(s, str):
            return pd.NA
        s = s.strip()
        if not s:
            return pd.NA
        if not s.startswith("http"):
            s = "https://" + s
        return s

    coord_web = df_filtered["Coordinator's website"].apply(clean_url)
    proj_web  = df_filtered["Project Website"].apply(clean_url)
    df_filtered["_website_from_csv"] = coord_web.fillna(proj_web)

    # ── Deduplicate by org name – aggregate all projects ─────────────────────
    def join_unique(series):
        vals = series.dropna().astype(str).unique()
        return " | ".join(v for v in vals if v.strip() and v.strip() != "nan")

    def first_valid(series):
        """Return first non-null, non-empty value."""
        for v in series:
            if pd.notna(v) and str(v).strip() and str(v).strip() != "nan":
                return str(v).strip()
        return pd.NA

    agg = df_filtered.groupby("Coordinating organisation name").agg(
        org_type=("Coordinating organisation type", "first"),
        address=("Coordinator's address", "first"),
        region=("Coordinator's region", "first"),
        country=("Coordinator's country", "first"),
        project_count=("Project Identifier", "count"),
        project_ids=("Project Identifier", join_unique),
        project_titles=("Project Title", join_unique),
        project_summaries=("Project Summary", join_unique),
        relevance_score=("_score", "max"),         # highest score from any project
        website_from_csv=("_website_from_csv", first_valid),
    ).reset_index()

    agg.rename(columns={"Coordinating organisation name": "org_name"}, inplace=True)

    # ── Add tier + outreach strategy ──────────────────────────────────────────
    agg["tier"] = agg["relevance_score"].apply(tier_from_score)
    agg["outreach_strategy"] = agg["tier"].apply(outreach_strategy)

    # ── Columns for website-scraping steps ────────────────────────────────────
    agg["website"] = agg["website_from_csv"]
    agg["email"] = ""
    agg["notes"] = ""

    # ── Sort: Tier1 first, then by score descending ───────────────────────────
    tier_order = {"Tier1": 0, "Tier2": 1, "Tier3": 2}
    agg["_tier_order"] = agg["tier"].map(tier_order)
    agg = agg.sort_values(["_tier_order", "relevance_score"], ascending=[True, False])
    agg = agg.drop(columns=["_tier_order", "website_from_csv"])

    # ── Save ──────────────────────────────────────────────────────────────────
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    agg.to_csv(OUTPUT_PATH, index=False, encoding="utf-8-sig")

    # ── Summary ───────────────────────────────────────────────────────────────
    tier_counts = agg["tier"].value_counts()
    print(f"\nOutput: {OUTPUT_PATH}")
    print(f"  Unique orgs: {len(agg):,}")
    print(f"  Tier1 (high-relevance): {tier_counts.get('Tier1', 0):,}")
    print(f"  Tier2 (medium):         {tier_counts.get('Tier2', 0):,}")
    print(f"  Tier3 (general):        {tier_counts.get('Tier3', 0):,}")
    print(f"  Already have website:   {agg['website'].notna().sum():,}")
    print("\nTop 5 Tier1 orgs:")
    top = agg[agg["tier"] == "Tier1"].head(5)
    for _, row in top.iterrows():
        print(f"  [{row['country']}] {row['org_name']} (score={row['relevance_score']}, projects={row['project_count']})")

if __name__ == "__main__":
    main()
