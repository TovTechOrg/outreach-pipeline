"""
One-time fix: update personalization fields in Firebase from enriched_prospects.csv.
Fast version: fetches all pending contacts in one query, then batch-updates.
"""

import os, re
import pandas as pd
import firebase_admin
from firebase_admin import credentials, firestore

PIPELINE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR     = os.path.join(PIPELINE_DIR, "..", "data")
CSV_PATH     = os.path.join(DATA_DIR, "enriched_prospects.csv")
SA_PATH      = os.path.join(PIPELINE_DIR, "firebase-service-account.json")


def safe_id(s: str) -> str:
    return re.sub(r"[^\w-]", "_", s)[:100]


def main():
    if not firebase_admin._apps:
        firebase_admin.initialize_app(credentials.Certificate(SA_PATH))
    db = firestore.client()

    # 1. Load CSV
    df = pd.read_csv(CSV_PATH, low_memory=False).fillna("")
    df = df[df["email"].astype(str).str.strip() != ""]
    print(f"CSV rows with email: {len(df):,}")

    # 2. Fetch all pending contacts from Firebase in ONE query
    print("Fetching pending contacts from Firebase...")
    pending_ids = {doc.id for doc in db.collection("contacts").where("status", "==", "pending").select([]).get()}
    print(f"Found {len(pending_ids):,} pending contacts")

    # 3. Batch-update personalization fields
    updated = skipped_no_data = skipped_not_pending = 0
    batch   = db.batch()
    batch_n = 0

    for _, row in df.iterrows():
        doc_id = safe_id(str(row["org_name"]))
        tier   = str(row.get("tier", ""))

        if doc_id not in pending_ids:
            skipped_not_pending += 1
            continue

        if tier == "Tier1":
            sa  = str(row.get("specific_achievement", "")).strip()
            pop = str(row.get("their_population", "")).strip()
            if not (sa and pop):
                skipped_no_data += 1
                continue
            fields = {"specific_achievement": sa, "their_population": pop}
        else:
            theme = str(row.get("relevant_theme", "")).strip()
            if not theme:
                skipped_no_data += 1
                continue
            fields = {"relevant_theme": theme}

        batch.update(db.collection("contacts").document(doc_id), fields)
        updated += 1
        batch_n += 1

        if batch_n >= 400:
            batch.commit()
            batch   = db.batch()
            batch_n = 0
            print(f"  ... {updated} updated so far")

    if batch_n > 0:
        batch.commit()

    print(f"\nDone.")
    print(f"  Updated            : {updated:,}")
    print(f"  Skipped (no data)  : {skipped_no_data:,}")
    print(f"  Skipped (not pend) : {skipped_not_pending:,}")


if __name__ == "__main__":
    main()
