"""
Master runner — executes all pipeline steps in sequence.
Run: py run_pipeline.py [--step 1|2|3]

Steps:
  1 — Filter + deduplicate + score orgs from Erasmus+ CSV  (~5 sec)
  2 — Parallel email scraping from websites in CSV         (~20-40 min)
  3 — Generate final enriched_prospects.csv               (~5 sec)

Examples:
  py run_pipeline.py                        # run all steps
  py run_pipeline.py --step 1               # re-run filter only
  py run_pipeline.py --step 2               # scrape emails (resume-safe)
  py run_pipeline.py --step 2 --tier 1      # scrape Tier1 orgs first
  py run_pipeline.py --step 2 --workers 20  # more parallel workers
  py run_pipeline.py --step 3               # generate output CSV
"""

import sys
import os
import time
import importlib

sys.path.insert(0, os.path.dirname(__file__))


def run_step(n: int, extra_args: list[str] = None):
    print(f"\n{'='*60}")
    print(f"  STEP {n}")
    print(f"{'='*60}\n")
    start = time.time()

    if extra_args:
        # Pass extra args via sys.argv for steps that parse them
        orig_argv = sys.argv[:]
        sys.argv = [sys.argv[0]] + extra_args

    if n == 1:
        import step1_filter as m
        importlib.reload(m)
    elif n == 2:
        import step2_scrape_parallel as m
        importlib.reload(m)
    elif n == 3:
        import step4_generate_output as m
        importlib.reload(m)
    else:
        print(f"Unknown step: {n}")
        return

    m.main()

    if extra_args:
        sys.argv = orig_argv

    elapsed = time.time() - start
    print(f"\n  Step {n} complete in {elapsed:.1f}s")


def main():
    args = sys.argv[1:]

    if "--step" in args:
        idx = args.index("--step")
        step = int(args[idx + 1])
        # Pass remaining args (--workers, --tier) to the step
        extra = args[idx + 2:]
        run_step(step, extra)
    else:
        print("TovPlay Outreach Pipeline")
        print("=" * 60)
        print("Step 1: filter + score orgs      (~5 seconds)")
        print("Step 2: parallel email scraping  (~20-40 minutes, resume-safe)")
        print("Step 3: generate output CSV      (~5 seconds)")
        print()
        print("Interrupt step 2 with Ctrl+C anytime — progress is saved.")
        print()

        for step in [1, 2, 3]:
            run_step(step)

        print(f"\n{'='*60}")
        print("  PIPELINE COMPLETE")
        print(f"{'='*60}")
        print("Output: data/enriched_prospects.csv")
        print("Open in Excel, filter by 'tier' column to start outreach.")


if __name__ == "__main__":
    main()
