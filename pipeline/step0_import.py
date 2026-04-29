"""
Step 0: One-Time CSV Import to Firebase
========================================
Run this ONCE when you have a new batch of prospects to load.
After this, the daily pipeline reads exclusively from Firebase.

Usage:
  py step0_import.py                        # import from default CSV path
  py step0_import.py --file path/to/file.csv
  py step0_import.py --dry-run              # preview counts, nothing written
  py step0_import.py --stats               # show current Firebase contact counts

The CSV must have these columns:
  org_name, email, country, tier,
  project_titles, specific_achievement, their_population, relevant_theme
"""

import os
import re
import sys
from datetime import datetime, timezone

import pandas as pd
import firebase_admin
from firebase_admin import credentials, firestore

PIPELINE_DIR  = os.path.dirname(os.path.abspath(__file__))
DATA_DIR      = os.path.join(PIPELINE_DIR, "..", "data")
DEFAULT_CSV   = os.path.join(DATA_DIR, "enriched_prospects.csv")
SA_PATH       = os.path.join(PIPELINE_DIR, "firebase-service-account.json")


def init_firebase():
    if not firebase_admin._apps:
        cred = credentials.Certificate(SA_PATH)
        firebase_admin.initialize_app(cred)
    return firestore.client()


def safe_id(s: str) -> str:
    return re.sub(r"[^\w-]", "_", s)[:100]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def show_stats(db):
    """Print current contact counts by status and tier."""
    docs   = db.collection("contacts").get()
    total  = len(docs)

    by_status = {}
    by_tier   = {}
    for doc in docs:
        d = doc.to_dict()
        s = d.get("status", "unknown")
        t = d.get("tier", "unknown")
        by_status[s] = by_status.get(s, 0) + 1
        by_tier[t]   = by_tier.get(t, 0) + 1

    print(f"\nFirebase contacts — total: {total:,}")
    print("\nBy status:")
    for s, n in sorted(by_status.items()):
        print(f"  {s:<25} {n:>6,}")
    print("\nBy tier:")
    for t, n in sorted(by_tier.items()):
        print(f"  {t:<25} {n:>6,}")
    print()


def import_csv(db, csv_path: str, dry_run: bool):
    if not os.path.exists(csv_path):
        print(f"ERROR: file not found: {csv_path}")
        sys.exit(1)

    df = pd.read_csv(csv_path, low_memory=False).fillna("")
    df = df[df["email"].astype(str).str.strip() != ""]
    total = len(df)
    print(f"CSV rows with email: {total:,}")

    # Pre-fetch existing doc IDs (1 read per doc, but uses a single stream)
    print("  Fetching existing contacts...")
    existing_ids = {doc.id for doc in db.collection("contacts").select([]).get()}
    print(f"  Found {len(existing_ids):,} existing contacts in Firebase")

    imported  = 0
    skipped   = 0
    batch     = db.batch()
    batch_n   = 0

    for _, row in df.iterrows():
        doc_id = safe_id(str(row["org_name"]))

        if doc_id in existing_ids:
            skipped += 1
            continue

        ref = db.collection("contacts").document(doc_id)
        data = {
            "org_name":             str(row["org_name"]),
            "email":                str(row["email"]).split(" | ")[0].strip(),
            "country":              str(row.get("country", "")),
            "tier":                 str(row.get("tier", "Tier3")),
            "project_name":         str(row.get("project_titles", "")).split(" | ")[0][:120],
            "specific_achievement": str(row.get("specific_achievement", "")),
            "their_population":     str(row.get("their_population", "")),
            "relevant_theme":       str(row.get("relevant_theme", "")),
            "status":               "pending",
            "replied":              False,
            "click_count":          0,
            "initial_sent_at":      None,
            "initial_thread_id":    None,
            "followup1_sent_at":    None,
            "followup1_thread_id":  None,
            "followup2_sent_at":    None,
            "followup2_thread_id":  None,
            "followup3_sent_at":    None,
            "replied_at":           None,
            "created_at":           now_iso(),
        }

        if dry_run:
            imported += 1
            continue

        batch.set(ref, data)
        imported += 1
        batch_n  += 1

        # Firestore batch limit is 500 — flush every 400
        if batch_n >= 400:
            batch.commit()
            batch   = db.batch()
            batch_n = 0
            print(f"  ... {imported + skipped} / {total} processed")

    if not dry_run and batch_n > 0:
        batch.commit()

    print(f"\nDone.")
    print(f"  Imported : {imported:,}")
    print(f"  Skipped  : {skipped:,} (already in Firebase)")

    # Update global stats
    if not dry_run and imported > 0:
        db.collection("stats").document("global").set(
            {"total_contacts": firestore.Increment(imported)}, merge=True
        )


def main():
    args     = sys.argv[1:]
    dry_run  = "--dry-run" in args
    stats_only = "--stats" in args

    csv_path = DEFAULT_CSV
    if "--file" in args:
        csv_path = args[args.index("--file") + 1]

    if dry_run:
        print("=== DRY RUN — nothing will be written ===\n")

    db = init_firebase()

    if stats_only:
        show_stats(db)
        return

    print(f"Importing from: {csv_path}")
    import_csv(db, csv_path, dry_run)

    if not dry_run:
        print()
        show_stats(db)


if __name__ == "__main__":
    main()
