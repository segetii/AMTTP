"""
AMTTP FRAUD DETECTION PIPELINE — MASTER ORCHESTRATOR
=====================================================

Runs the full data labeling pipeline end-to-end:

  Step 1:  Pattern detection (Polars ultra) + XGB cross-validation
  Step 2:  Build final labeled dataset (625K addrs, 80 cols)

Optional:
  Step 0:  Data acquisition (Etherscan / BigQuery) — skipped if parquet exists
  Step 3:  30-day relabeling (drift update)
  Step 4:  GAT/GNN dataset creation
  Step 5:  Validation metrics & teacher-student evaluation

Usage:
  python run_pipeline.py                  # Steps 1+2 (default)
  python run_pipeline.py --steps 0,1,2    # Full pipeline from scratch
  python run_pipeline.py --steps 3        # 30-day refresh only
  python run_pipeline.py --steps 1,2,4,5  # Full + downstream

Requirements:
  pip install polars xgboost pandas numpy scipy pyarrow
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

PIPELINE_DIR = Path(__file__).parent
PROJECT_ROOT = PIPELINE_DIR.parent
PYTHON = sys.executable

# ── Step definitions ─────────────────────────────────────────────────────────
STEPS = {
    0: {
        "name": "Data Acquisition",
        "script": "step0_fetch_etherscan.py",
        "description": "Fetch ETH transactions from Etherscan API",
        "skip_if_exists": str(Path(r"C:\Users\Administrator\Downloads\eth_merged_dataset.parquet")),
    },
    1: {
        "name": "Pattern Detection + XGB",
        "script": "step1_pattern_detection.py",
        "description": "Run 7-pattern detection (Polars ultra) + XGB cross-validation",
        "outputs": [
            str(PROJECT_ROOT / "processed" / "sophisticated_fraud_patterns.csv"),
            str(PROJECT_ROOT / "processed" / "sophisticated_xgb_combined.csv"),
            str(PROJECT_ROOT / "processed" / "xgb_high_risk_addresses.csv"),
        ],
    },
    2: {
        "name": "Build Labeled Dataset",
        "script": "step2_build_labeled_dataset.py",
        "description": "Aggregate 625K addrs + merge ultra + graph + XGB + cross-check → final parquet",
        "outputs": [
            str(PROJECT_ROOT / "processed" / "eth_addresses_labeled_v2.parquet"),
        ],
    },
    3: {
        "name": "30-Day Relabel (Drift Update)",
        "script": "step3_relabel_30d.py",
        "description": "Fetch last 30 days from Etherscan, relabel with TeacherAM",
        "outputs": [
            str(PROJECT_ROOT / "processed" / "eth_30d_teacher_labeled.parquet"),
        ],
    },
    4: {
        "name": "GAT/GNN Dataset",
        "script": "step4_create_gat_dataset.py",
        "description": "Build tx-level dataset with edge_index for PyTorch Geometric",
    },
    5: {
        "name": "Validation & Evaluation",
        "script": "step5_validate_metrics.py",
        "description": "Compute ROC-AUC / PR-AUC / F1 against external validation set",
    },
}

DEFAULT_STEPS = [1, 2]


def run_step(step_num: int, dry_run: bool = False) -> bool:
    """Run a single pipeline step. Returns True on success."""
    cfg = STEPS[step_num]
    script = PIPELINE_DIR / cfg["script"]

    print(f"\n{'='*70}")
    print(f"STEP {step_num}: {cfg['name']}")
    print(f"  {cfg['description']}")
    print(f"  Script: {script.name}")
    print(f"{'='*70}")

    if not script.exists():
        print(f"  [SKIP] Script not found: {script}")
        return False

    # Skip if output already exists and skip_if_exists is set
    skip_path = cfg.get("skip_if_exists")
    if skip_path and Path(skip_path).exists():
        print(f"  [SKIP] Input already exists: {skip_path}")
        return True

    if dry_run:
        print(f"  [DRY-RUN] Would run: {PYTHON} {script}")
        return True

    t0 = time.perf_counter()
    result = subprocess.run(
        [PYTHON, str(script)],
        cwd=str(PROJECT_ROOT),
    )
    elapsed = time.perf_counter() - t0

    if result.returncode != 0:
        print(f"\n  [FAIL] Step {step_num} failed (exit code {result.returncode}) after {elapsed:.1f}s")
        return False

    # Verify outputs
    outputs = cfg.get("outputs", [])
    missing = [o for o in outputs if not Path(o).exists()]
    if missing:
        print(f"  [WARN] Missing expected outputs: {missing}")

    print(f"\n  [OK] Step {step_num} completed in {elapsed:.1f}s")
    return True


def main():
    parser = argparse.ArgumentParser(
        description="AMTTP Fraud Detection Pipeline Orchestrator"
    )
    parser.add_argument(
        "--steps", type=str, default=None,
        help="Comma-separated step numbers to run (default: 1,2). E.g. --steps 0,1,2,3,4,5"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print what would run without executing"
    )
    parser.add_argument(
        "--list", action="store_true",
        help="List all available steps"
    )
    args = parser.parse_args()

    if args.list:
        print("AMTTP Pipeline Steps:")
        print("-" * 60)
        for num, cfg in sorted(STEPS.items()):
            script = PIPELINE_DIR / cfg["script"]
            status = "✓" if script.exists() else "✗"
            print(f"  [{status}] Step {num}: {cfg['name']}")
            print(f"        {cfg['description']}")
            print(f"        → {cfg['script']}")
        return

    steps = DEFAULT_STEPS
    if args.steps:
        steps = [int(s.strip()) for s in args.steps.split(",")]

    print("=" * 70)
    print("AMTTP FRAUD DETECTION PIPELINE")
    print(f"Steps to run: {steps}")
    print("=" * 70)

    t_total = time.perf_counter()
    results = {}

    for step_num in steps:
        if step_num not in STEPS:
            print(f"\n[ERROR] Unknown step: {step_num}")
            results[step_num] = False
            continue
        results[step_num] = run_step(step_num, dry_run=args.dry_run)
        if not results[step_num]:
            print(f"\n[ABORT] Step {step_num} failed. Stopping pipeline.")
            break

    elapsed = time.perf_counter() - t_total
    print(f"\n{'='*70}")
    print("PIPELINE SUMMARY")
    print(f"{'='*70}")
    for s, ok in results.items():
        status = "OK" if ok else "FAIL"
        print(f"  Step {s} ({STEPS[s]['name']:30s}): {status}")
    print(f"\nTotal time: {elapsed:.1f}s")
    print(f"{'='*70}")


if __name__ == "__main__":
    main()
