"""
Step 5: AI Personalization using Gemini API
=============================================
Reads enriched_prospects.csv and adds personalization fields for each org:
  - Tier1: specific_achievement, their_population
  - Tier2: relevant_theme
  - Tier3: relevant_theme (same extraction as Tier2)

These fields are used by step6_send_emails.py to fill in the email templates.

Usage:
  py step5_personalize.py --tier 1         # Tier1 only (~3,400 orgs, ~1 hour)
  py step5_personalize.py --tier 2         # Tier2 only
  py step5_personalize.py --limit 50       # Test run: first 50 orgs
  py step5_personalize.py                  # All orgs

Setup:
  1. Get Gemini API key: https://aistudio.google.com/app/apikey
  2. Set env variable:  set GEMINI_API_KEY=your-key-here
  3. Run this script

Cost estimate: ~$0.002 per org (Gemini Flash is very cheap)
For 3,400 Tier1 orgs: ~$7 total
"""

import pandas as pd
from google import genai
import firebase_admin
from firebase_admin import credentials, firestore
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import GEMINI_MODEL

# ── Paths ──────────────────────────────────────────────────────────────────────
PIPELINE_DIR  = os.path.dirname(os.path.abspath(__file__))
DATA_DIR      = os.path.join(PIPELINE_DIR, "..", "data")
PROSPECTS_CSV = os.path.join(DATA_DIR, "enriched_prospects.csv")
CHECKPOINT    = os.path.join(DATA_DIR, "personalize_checkpoint.json")
SA_PATH       = os.path.join(PIPELINE_DIR, "firebase-service-account.json")

# ── Config ─────────────────────────────────────────────────────────────────────
REQUEST_DELAY   = 1.2    # seconds between API calls (free tier: 60 req/min)
CSV_SAVE_EVERY  = 10     # write CSV every N orgs (checkpoint JSON saved after every org)

# ── Init Gemini ────────────────────────────────────────────────────────────────
api_key = os.environ.get("GEMINI_API_KEY")
if not api_key:
    print("ERROR: GEMINI_API_KEY not set.")
    print("  1. Get key: https://aistudio.google.com/app/apikey")
    print("  2. Run:     set GEMINI_API_KEY=your-key-here")
    sys.exit(1)

client = genai.Client(api_key=api_key)

# ── Init Firebase (optional backup) ────────────────────────────────────────────
db = None
if os.path.exists(SA_PATH):
    try:
        if not firebase_admin._apps:
            firebase_admin.initialize_app(credentials.Certificate(SA_PATH))
        db = firestore.client()
        print("  Firebase backup: enabled")
    except Exception as e:
        print(f"  Firebase backup: disabled ({e})")
else:
    print(f"  Firebase backup: disabled (no {SA_PATH})")


# ── Gemini calls ───────────────────────────────────────────────────────────────

def call_gemini(prompt: str) -> dict:
    """Call Gemini and parse JSON response. Returns {} on failure."""
    try:
        response = client.models.generate_content(model=GEMINI_MODEL, contents=prompt)
        text = response.text.strip()
        m = re.search(r'\{[^{}]*\}', text, re.DOTALL)
        if m:
            return json.loads(m.group())
    except Exception as e:
        print(f"  [Gemini error: {e}]")
    return {}


def personalize_tier1(org_name: str, project_titles: str, project_summaries: str) -> dict:
    prompt = f"""You help write personalized cold emails to European NGOs in an Erasmus+ outreach campaign.

Organization: {org_name}
Project titles: {project_titles[:400]}
Project summary: {project_summaries[:700]}

Extract two short phrases for email personalization:

1. specific_achievement: One specific, concrete thing this org achieved or focused on. Max 18 words.
   Good examples: "three-stage upskilling pathway for adults with health conditions and disabilities"
                  "combining financial literacy with digital skills to unlock remote employment for NEET youth"
                  "organizing adapted water sports activities for 150+ members with disabilities"
   Bad examples: "helping people", "educational programs", "empowering young people" (too generic)
   Rules: Be concrete and specific to THIS org. Use a noun phrase, not a sentence. No filler words.

2. their_population: The specific group this org serves. 3-7 words. Name them precisely — age, condition, situation.
   Good examples: "young adults with learning difficulties", "adults with disabilities seeking employment", "displaced Ukrainian youth at NEET risk"
   Bad examples: "young people with fewer opportunities" (Erasmus+ boilerplate — too vague), "young people for personal growth" (not a population description)
   Rules: NEVER use generic Erasmus+ phrases. Be specific to THIS org's actual beneficiaries.

Respond with valid JSON only (no markdown, no explanation):
{{"specific_achievement": "...", "their_population": "..."}}"""

    return call_gemini(prompt)


def personalize_tier2(org_name: str, project_titles: str, project_summaries: str) -> dict:
    prompt = f"""Extract the main thematic focus of this Erasmus+ VET project in 3-6 words.

Organization: {org_name}
Project titles: {project_titles[:300]}
Project summary: {project_summaries[:400]}

Good examples: "vocational skills for young adults", "digital upskilling for the workforce", "inclusion through vocational education"

Respond with valid JSON only:
{{"relevant_theme": "..."}}"""

    return call_gemini(prompt)


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

    if not os.path.exists(PROSPECTS_CSV):
        print(f"ERROR: {PROSPECTS_CSV} not found.")
        print("Run step4_generate_output.py first.")
        sys.exit(1)

    print(f"Loading: {PROSPECTS_CSV}")
    df = pd.read_csv(PROSPECTS_CSV, low_memory=False)
    df = df.fillna("")

    # Only process orgs that have an email — no point personalizing the rest
    before = len(df)
    df = df[df["email"].astype(str).str.strip().str.len() > 0]
    print(f"  Skipping {before - len(df):,} orgs with no email (kept {len(df):,})")

    # Add columns if missing
    for col in ["specific_achievement", "their_population", "relevant_theme"]:
        if col not in df.columns:
            df[col] = ""

    # Load checkpoint
    checkpoint = {}
    if os.path.exists(CHECKPOINT):
        with open(CHECKPOINT, "r", encoding="utf-8") as f:
            checkpoint = json.load(f)
        # Apply checkpoint to df
        for org, fields in checkpoint.items():
            mask = df["org_name"] == org
            for col, val in fields.items():
                if col in df.columns:
                    df.loc[mask, col] = val
        print(f"  Checkpoint: {len(checkpoint):,} orgs already processed")

    # Build work list: orgs that need personalization and haven't been processed
    def needs_work(row):
        if row["org_name"] in checkpoint:
            return False
        tier = row.get("tier", "")
        if tier == "Tier1":
            return not str(row.get("specific_achievement", "")).strip()
        if tier in ("Tier2", "Tier3"):
            return not str(row.get("relevant_theme", "")).strip()
        return False

    work_mask = df.apply(needs_work, axis=1)
    if tier_filter:
        work_mask = work_mask & (df["tier"] == tier_filter)

    work = df[work_mask].copy()
    # Sort: Tier1 first, then by relevance score
    tier_order = {"Tier1": 0, "Tier2": 1, "Tier3": 2}
    work["_t"] = work["tier"].map(tier_order)
    work = work.sort_values(["_t", "relevance_score"], ascending=[True, False]).drop(columns=["_t"])

    if limit:
        work = work.head(limit)

    t1_count = (work["tier"] == "Tier1").sum()
    t2_count = (work["tier"] == "Tier2").sum()
    t3_count = (work["tier"] == "Tier3").sum()
    print(f"  Orgs to personalize: {len(work):,}  (Tier1: {t1_count}, Tier2: {t2_count}, Tier3: {t3_count})")
    if tier_filter:
        print(f"  Filtered to: {tier_filter}")
    print(f"  Estimated time: ~{len(work) * REQUEST_DELAY / 60:.0f} minutes")
    print(f"  Estimated cost: ~${len(work) * 0.002:.2f}")
    print()

    if len(work) == 0:
        print("Nothing to do — all orgs already personalized.")
        return

    completed = 0
    start_time = time.time()

    for _, row in work.iterrows():
        org_name  = row["org_name"]
        tier      = row["tier"]
        titles    = str(row.get("project_titles", ""))
        summaries = str(row.get("project_summaries", ""))

        if tier == "Tier1":
            fields = personalize_tier1(org_name, titles, summaries)
            df.loc[df["org_name"] == org_name, "specific_achievement"] = fields.get("specific_achievement", "")
            df.loc[df["org_name"] == org_name, "their_population"]     = fields.get("their_population", "")
        elif tier in ("Tier2", "Tier3"):
            fields = personalize_tier2(org_name, titles, summaries)
            df.loc[df["org_name"] == org_name, "relevant_theme"] = fields.get("relevant_theme", "")
        else:
            fields = {}

        checkpoint[org_name] = fields
        completed += 1

        elapsed   = time.time() - start_time
        rate      = completed / elapsed if elapsed > 0 else 0
        remaining = (len(work) - completed) / rate if rate > 0 else 0
        preview   = " | ".join(f"{v[:35]}" for v in fields.values() if v)

        print(f"  [{completed}/{len(work)}] {org_name[:38]:<38}  {preview}  (~{remaining/60:.0f}min)")

        # Save checkpoint JSON after every org
        with open(CHECKPOINT, "w", encoding="utf-8") as f:
            json.dump(checkpoint, f, ensure_ascii=False, indent=2)

        # Save CSV every 10 orgs
        if completed % CSV_SAVE_EVERY == 0:
            df.to_csv(PROSPECTS_CSV, index=False, encoding="utf-8-sig")
            print(f"  [CSV saved: {completed} done]")

        time.sleep(REQUEST_DELAY)

    # Final save
    with open(CHECKPOINT, "w", encoding="utf-8") as f:
        json.dump(checkpoint, f, ensure_ascii=False, indent=2)
    df.to_csv(PROSPECTS_CSV, index=False, encoding="utf-8-sig")

    # Firebase bulk backup
    if db:
        print("  Saving backup to Firebase...")
        batch = db.batch()
        count = 0
        for org, fields in checkpoint.items():
            if not fields:
                continue
            doc_id = re.sub(r'[^\w-]', '_', org)[:100]
            ref = db.collection("personalization_backup").document(doc_id)
            batch.set(ref, {"org_name": org, **fields})
            count += 1
            if count % 500 == 0:   # Firestore batch limit is 500
                batch.commit()
                batch = db.batch()
        if count % 500 != 0:
            batch.commit()
        print(f"  Firebase backup: {count:,} orgs saved")

    elapsed = time.time() - start_time
    print(f"\n{'='*60}")
    print(f"Done in {elapsed/60:.1f} minutes")
    print(f"  Personalized: {completed:,} orgs")
    print(f"  Saved: {PROSPECTS_CSV}")


if __name__ == "__main__":
    main()
