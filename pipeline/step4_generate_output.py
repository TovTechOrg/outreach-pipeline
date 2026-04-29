"""
Step 4: Generate final enriched_prospects.csv ready for outreach.
Input:  data/filtered_orgs.csv
Output: data/enriched_prospects.csv
"""

import pandas as pd
import os

FILTERED_CSV = os.path.join(os.path.dirname(__file__), "..", "data", "filtered_orgs.csv")
OUTPUT_CSV   = os.path.join(os.path.dirname(__file__), "..", "data", "enriched_prospects.csv")

# Email template hints embedded in the output
# Customize these hints to match your campaign — they appear in enriched_prospects.csv
# as a guide when writing email copy in step6_send_emails.py
TEMPLATE_HINTS = {
    "Tier1": (
        "Subject: [Your high-relevance subject line] | "
        "Open: Reference the specific project or achievement | "
        "Hook: [Your core value proposition for highest-fit prospects] | "
        "CTA: 15-min call to explore fit | "
        "Angle: [Your strongest partnership angle for this tier]"
    ),
    "Tier2": (
        "Subject: [Your medium-relevance subject line] | "
        "Open: Content gift or relevant resource | "
        "Hook: [Your value proposition for medium-fit prospects] | "
        "CTA: Would this fit your work? Happy to share more | "
        "Angle: [Your partnership angle for this tier]"
    ),
    "Tier3": (
        "Subject: [Your general subject line] | "
        "Open: Short intro + free resource | "
        "Hook: [Brief one-line value proposition] | "
        "CTA: Hope this sparks an idea. Happy to chat if useful | "
        "Angle: no-pressure content sharing"
    ),
}

FINAL_COLUMNS = [
    "org_name",
    "org_type",
    "country",
    "address",
    "website",
    "email",
    "tier",
    "relevance_score",
    "project_count",
    "project_titles",
    "project_summaries",
    "outreach_strategy",
    "email_template_hints",
    "status",           # empty = prospect, to be filled during outreach
    "contacted_date",
    "response",
    "notes",
]


def main():
    print(f"Loading: {FILTERED_CSV}")
    df = pd.read_csv(FILTERED_CSV, low_memory=False)
    print(f"  Total orgs: {len(df):,}")

    # Add template hints
    df["email_template_hints"] = df["tier"].map(TEMPLATE_HINTS)

    # Add pipeline status columns (empty, for tracking outreach)
    for col in ["status", "contacted_date", "response"]:
        if col not in df.columns:
            df[col] = ""

    # Select and reorder final columns (only those that exist)
    existing_cols = [c for c in FINAL_COLUMNS if c in df.columns]
    df_out = df[existing_cols].copy()

    # Sort: Tier1 first, then by score
    tier_order = {"Tier1": 0, "Tier2": 1, "Tier3": 2}
    df_out["_t"] = df_out["tier"].map(tier_order)
    df_out = df_out.sort_values(["_t", "relevance_score"], ascending=[True, False])
    df_out = df_out.drop(columns=["_t"])

    # Save
    os.makedirs(os.path.dirname(OUTPUT_CSV), exist_ok=True)
    df_out.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")

    # Stats
    has_email = (df_out["email"].notna() & (df_out["email"] != "")).sum()
    has_website = (df_out["website"].notna() & (df_out["website"] != "")).sum()
    tier_counts = df_out["tier"].value_counts()

    print(f"\nOutput saved: {OUTPUT_CSV}")
    print(f"  Total prospects:     {len(df_out):,}")
    print(f"  Tier1 (hot):         {tier_counts.get('Tier1', 0):,}")
    print(f"  Tier2 (warm):        {tier_counts.get('Tier2', 0):,}")
    print(f"  Tier3 (general):     {tier_counts.get('Tier3', 0):,}")
    print(f"  Have website:        {has_website:,}")
    print(f"  Have email:          {has_email:,}")
    print(f"\nReady for outreach. Start with Tier1 contacts.")


if __name__ == "__main__":
    main()
