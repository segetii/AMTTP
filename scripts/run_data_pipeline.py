#!/usr/bin/env python3
"""
AMTTP Data Pipeline Runner
==========================
Chains the fraud detection and data loading scripts in the correct order.

Usage:
    python scripts/run_data_pipeline.py [--skip-ml] [--fraction 0.4]

Options:
    --skip-ml       Skip the ML fraud detection step (use existing processed files)
    --fraction N    Data fraction to load (0.1 to 1.0, default 0.4 = 40%)
    --force-ml      Force re-run ML even if processed files exist
"""

import sys
import os
import subprocess
import argparse
from pathlib import Path
from datetime import datetime

# Paths
SCRIPTS_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPTS_DIR.parent
PROCESSED_DIR = PROJECT_ROOT / "processed"

FRAUD_DETECTION_SCRIPT = SCRIPTS_DIR / "sophisticated_fraud_detection_ultra.py"
DATA_LOADER_SCRIPT = SCRIPTS_DIR / "load_realistic_data.py"

# Required processed files
REQUIRED_FILES = [
    "eth_addresses_labeled.parquet",
    "eth_transactions_full_labeled.parquet",
]


def check_processed_files():
    """Check if required processed files exist."""
    missing = []
    for fname in REQUIRED_FILES:
        fpath = PROCESSED_DIR / fname
        if not fpath.exists():
            missing.append(fname)
    return missing


def run_script(script_path, description, extra_args=None):
    """Run a Python script and return success status."""
    print(f"\n{'='*70}")
    print(f"RUNNING: {description}")
    print(f"Script: {script_path}")
    print(f"{'='*70}\n")
    
    cmd = [sys.executable, str(script_path)]
    if extra_args:
        cmd.extend(extra_args)
    
    try:
        result = subprocess.run(cmd, cwd=str(PROJECT_ROOT))
        return result.returncode == 0
    except Exception as e:
        print(f"ERROR: {e}")
        return False


def update_data_fraction(fraction):
    """Update the DATA_FRACTION in load_realistic_data.py."""
    loader_path = DATA_LOADER_SCRIPT
    
    with open(loader_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Find and replace DATA_FRACTION line
    import re
    new_content = re.sub(
        r'DATA_FRACTION\s*=\s*[\d.]+',
        f'DATA_FRACTION = {fraction}',
        content
    )
    
    if new_content != content:
        with open(loader_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print(f"Updated DATA_FRACTION to {fraction} ({fraction*100:.0f}%)")


def main():
    parser = argparse.ArgumentParser(description="AMTTP Data Pipeline Runner")
    parser.add_argument('--skip-ml', action='store_true', 
                        help='Skip ML fraud detection (use existing files)')
    parser.add_argument('--force-ml', action='store_true',
                        help='Force re-run ML even if files exist')
    parser.add_argument('--fraction', type=float, default=0.4,
                        help='Data fraction to load (0.1-1.0, default 0.4)')
    args = parser.parse_args()
    
    print("="*70)
    print("AMTTP DATA PIPELINE")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*70)
    
    # Validate fraction
    if not 0.1 <= args.fraction <= 1.0:
        print(f"ERROR: --fraction must be between 0.1 and 1.0")
        sys.exit(1)
    
    # Update data fraction in loader script
    update_data_fraction(args.fraction)
    
    # Step 1: Check if we need to run ML
    missing_files = check_processed_files()
    
    if args.skip_ml and missing_files:
        print(f"\nERROR: --skip-ml specified but missing required files:")
        for f in missing_files:
            print(f"  - {f}")
        print("\nRun without --skip-ml to generate these files.")
        sys.exit(1)
    
    run_ml = args.force_ml or (not args.skip_ml and missing_files)
    
    if run_ml:
        print("\n[STEP 1/2] Running fraud detection pipeline...")
        success = run_script(
            FRAUD_DETECTION_SCRIPT,
            "Sophisticated Fraud Detection (Polars + XGBoost)"
        )
        if not success:
            print("\nERROR: Fraud detection failed!")
            sys.exit(1)
    else:
        print("\n[STEP 1/2] Skipping ML - using existing processed files")
        for fname in REQUIRED_FILES:
            fpath = PROCESSED_DIR / fname
            size_mb = fpath.stat().st_size / (1024*1024)
            mtime = datetime.fromtimestamp(fpath.stat().st_mtime)
            print(f"  ✓ {fname} ({size_mb:.1f} MB, {mtime.strftime('%Y-%m-%d %H:%M')})")
    
    # Step 2: Run data loader
    print(f"\n[STEP 2/2] Loading data to services ({args.fraction*100:.0f}% sample)...")
    success = run_script(
        DATA_LOADER_SCRIPT,
        f"Data Loader (Memgraph, MongoDB, Frontend JSON)"
    )
    
    if not success:
        print("\nWARNING: Data loading had some issues (check output above)")
    
    # Summary
    print("\n" + "="*70)
    print("PIPELINE COMPLETE")
    print("="*70)
    print(f"\nData loaded with {args.fraction*100:.0f}% sampling")
    print("\nGenerated files:")
    print("  - Frontend JSON: c:\\amttp\\frontend\\frontend\\src\\data\\")
    print("  - Flutter JSON:  c:\\amttp\\frontend\\amttp_app\\assets\\data\\")
    print("\nTo view the dashboard:")
    print("  1. Start Next.js: cd frontend/frontend && npm run dev -- -p 3006")
    print("  2. Open: http://localhost:3006/war-room/detection-studio")


if __name__ == "__main__":
    main()
