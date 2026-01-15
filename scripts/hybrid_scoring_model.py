"""
Hybrid Scoring Model: Combines ML + Behavioral Patterns + Graph Analysis
This creates a unified risk score that leverages all detection methods.

Integrated with sophisticated_fraud_detection_ultra.py (Polars-based) for pattern detection.
"""
import pandas as pd
import numpy as np
import subprocess
import sys
import os

print("=" * 70)
print("HYBRID SCORING MODEL - ML + Behavioral + Graph")
print("=" * 70)

# =============================================================================
# STEP 1: Run Sophisticated Fraud Detection (Ultra - Polars)
# =============================================================================
print("\n[STEP 1] Running Sophisticated Fraud Detection...")

# The ULTRA script is the latest and fastest (Polars-based)
ULTRA_SCRIPT = r"c:\amttp\scripts\sophisticated_fraud_detection_ultra.py"
SOPHISTICATED_OUTPUT = r"c:\amttp\processed\sophisticated_fraud_patterns.csv"
XGB_COMBINED_OUTPUT = r"c:\amttp\processed\sophisticated_xgb_combined.csv"

# Check for ultra script
if os.path.exists(ULTRA_SCRIPT):
    detection_script = ULTRA_SCRIPT
    print(f"   Using: sophisticated_fraud_detection_ultra.py (Polars engine - LATEST)")
else:
    detection_script = None
    print(f"   ⚠ Ultra detection script not found!")

# Run the detection if script exists and results are stale (> 1 hour old)
run_detection = False
if detection_script:
    # Check the XGB combined output (the final output from ultra script)
    check_file = XGB_COMBINED_OUTPUT if os.path.exists(XGB_COMBINED_OUTPUT) else SOPHISTICATED_OUTPUT
    
    if os.path.exists(check_file):
        import time
        file_age = time.time() - os.path.getmtime(check_file)
        if file_age > 3600:  # Older than 1 hour
            run_detection = True
            print(f"   Results are {file_age/60:.0f} min old, re-running detection...")
        else:
            print(f"   Using cached results ({file_age/60:.0f} min old)")
    else:
        run_detection = True
        print(f"   No cached results, running detection...")

if run_detection and detection_script:
    print(f"\n   Executing: {detection_script}")
    print("   " + "-" * 60)
    result = subprocess.run(
        [sys.executable, detection_script],
        capture_output=False,
        text=True
    )
    print("   " + "-" * 60)
    if result.returncode != 0:
        print(f"   ⚠ Detection script returned code {result.returncode}")

# =============================================================================
# STEP 2: Load Data from Ultra Detection
# =============================================================================
print("\n[STEP 2] Loading data sources...")

# Priority: XGB combined (from ultra script) > sophisticated patterns > cross-validated
# The ultra script produces sophisticated_xgb_combined.csv which has everything

# Load XGB combined results (PRIMARY - from ultra detection)
if os.path.exists(XGB_COMBINED_OUTPUT):
    xgb_combined = pd.read_csv(XGB_COMBINED_OUTPUT)
    print(f"   ✅ XGB Combined (from ultra): {len(xgb_combined):,} addresses")
else:
    xgb_combined = None
    print("   ⚠ No XGB combined results from ultra detection")

# Load sophisticated patterns as fallback
if os.path.exists(SOPHISTICATED_OUTPUT):
    sophisticated = pd.read_csv(SOPHISTICATED_OUTPUT)
    print(f"   Sophisticated patterns: {len(sophisticated):,} addresses")
else:
    sophisticated = pd.DataFrame(columns=['address', 'sophisticated_score', 'patterns', 'pattern_count'])
    print("   ⚠ No sophisticated patterns found")

# Load cross-validated results if available (optional enrichment)
CV_PATH = r"c:\amttp\processed\cross_validated_results.csv"
if os.path.exists(CV_PATH):
    cross_validated = pd.read_csv(CV_PATH, low_memory=False)
    print(f"   Cross-validated (ML+Graph): {len(cross_validated):,} addresses")
else:
    cross_validated = None

# =============================================================================
# STEP 3: Build Hybrid Scores (from Ultra Detection results)
# =============================================================================
print("\n[STEP 3] Computing hybrid scores...")

# Use XGB combined results from ultra detection (already has hybrid scoring)
if xgb_combined is not None and 'hybrid_score' in xgb_combined.columns:
    print("   ✅ Using pre-computed hybrid scores from ultra detection")
    hybrid_df = xgb_combined.copy()
    
    # Ensure required columns exist
    if 'risk_level' not in hybrid_df.columns:
        hybrid_df['risk_level'] = hybrid_df['hybrid_score'].apply(
            lambda x: 'CRITICAL' if x >= 80 else 'HIGH' if x >= 60 else 'MEDIUM' if x >= 40 else 'LOW' if x >= 20 else 'MINIMAL'
        )
else:
    # Build hybrid scores from sophisticated patterns + cross-validated
    print("   Building hybrid scores from available data...")
    
    # Start with sophisticated patterns as base
    hybrid_df = sophisticated.copy()
    hybrid_df['address'] = hybrid_df['address'].str.lower()
    
    # Add ML scores if available
    if cross_validated is not None:
        cross_validated['address'] = cross_validated['address'].str.lower()
        hybrid_df = hybrid_df.merge(
            cross_validated[['address', 'ml_max_score', 'ml_avg_score', 'risk_score']],
            on='address',
            how='left'
        )
        hybrid_df['ml_max_score'] = hybrid_df['ml_max_score'].fillna(0)
        hybrid_df['ml_avg_score'] = hybrid_df['ml_avg_score'].fillna(0)
        hybrid_df['risk_score'] = hybrid_df['risk_score'].fillna(0)
    else:
        hybrid_df['ml_max_score'] = 0
        hybrid_df['ml_avg_score'] = 0
        hybrid_df['risk_score'] = 0
    
    # Normalize scores to 0-100
    max_pattern = hybrid_df['sophisticated_score'].max()
    hybrid_df['pattern_normalized'] = (hybrid_df['sophisticated_score'] / max_pattern) * 100 if max_pattern > 0 else 0
    hybrid_df['ml_normalized'] = hybrid_df['ml_max_score'] * 100  # Already 0-1
    hybrid_df['graph_normalized'] = (hybrid_df['risk_score'] / 305) * 100  # Assuming max ~305
    
    # Pattern boost based on type
    PATTERN_BOOST = {
        "SMURFING": 25, "LAYERING": 15, "FAN_OUT": 15, "FAN_IN": 15,
        "STRUCTURING": 20, "VELOCITY": 15, "PEELING": 20
    }
    
    def calc_boost(patterns_str):
        if pd.isna(patterns_str) or not patterns_str:
            return 0
        boost = sum(PATTERN_BOOST.get(p.strip(), 0) for p in str(patterns_str).split(','))
        return min(boost, 100)
    
    hybrid_df['pattern_boost'] = hybrid_df['patterns'].apply(calc_boost)
    
    # Compute hybrid score
    # 40% Pattern + 30% ML + 20% Graph + 10% Boost
    hybrid_df['hybrid_score'] = (
        hybrid_df['pattern_normalized'] * 0.40 +
        hybrid_df['ml_normalized'] * 0.30 +
        hybrid_df['graph_normalized'] * 0.20 +
        hybrid_df['pattern_boost'] * 0.10
    )
    
    # Multi-signal bonus
    def count_signals(row):
        signals = 0
        if row.get('ml_max_score', 0) >= 0.3: signals += 1
        if row.get('risk_score', 0) >= 50: signals += 1
        if row.get('pattern_count', 0) >= 3: signals += 1
        return signals
    
    hybrid_df['signal_count'] = hybrid_df.apply(count_signals, axis=1)
    
    # Boost for multi-signal
    hybrid_df.loc[hybrid_df['signal_count'] == 2, 'hybrid_score'] *= 1.2
    hybrid_df.loc[hybrid_df['signal_count'] >= 3, 'hybrid_score'] *= 1.5
    hybrid_df['hybrid_score'] = hybrid_df['hybrid_score'].clip(0, 100)
    
    # Risk classification
    hybrid_df['risk_level'] = hybrid_df['hybrid_score'].apply(
        lambda x: 'CRITICAL' if x >= 80 else 'HIGH' if x >= 60 else 'MEDIUM' if x >= 40 else 'LOW' if x >= 20 else 'MINIMAL'
    )

# Sort by hybrid score
hybrid_df = hybrid_df.sort_values('hybrid_score', ascending=False)

# =============================================================================
# STEP 4: Display Results
# =============================================================================
print("\n" + "=" * 70)
print("RISK DISTRIBUTION (HYBRID SCORES)")
print("=" * 70)

risk_counts = hybrid_df['risk_level'].value_counts()
total = len(hybrid_df)

for level in ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'MINIMAL']:
    count = risk_counts.get(level, 0)
    pct = count / total * 100
    emoji = {'CRITICAL': '�', 'HIGH': '�', 'MEDIUM': '🟡', 'LOW': '🟢', 'MINIMAL': '⚪'}.get(level, '')
    print(f"  {emoji} {level:10}: {count:>6,} ({pct:>5.2f}%)")

# Show top threats
print("\n" + "=" * 70)
print("TOP 20 HIGHEST-RISK ADDRESSES")
print("=" * 70)

display_cols = ['address', 'hybrid_score', 'pattern_count', 'patterns', 'risk_level']
if 'xgb_normalized' in hybrid_df.columns:
    display_cols.insert(2, 'xgb_normalized')

for i, (_, row) in enumerate(hybrid_df.head(20).iterrows(), 1):
    print(f"\n  #{i} {row['address']}")
    score_str = f"      Hybrid: {row['hybrid_score']:.1f}"
    if 'xgb_normalized' in row:
        score_str += f" | XGB: {row['xgb_normalized']:.1f}"
    score_str += f" | Patterns: {row.get('pattern_count', 0)}"
    print(score_str)
    if pd.notna(row.get('patterns')) and row.get('patterns'):
        print(f"      Types: {row['patterns']}")

# =============================================================================
# STEP 5: Save Results
# =============================================================================
print("\n" + "=" * 70)
print("SAVING RESULTS")
print("=" * 70)

output_file = r'c:\amttp\processed\hybrid_risk_scores.csv'
hybrid_df.to_csv(output_file, index=False)
print(f"  ✅ Saved {len(hybrid_df):,} hybrid scores to {output_file}")

# Save high-risk subset
high_risk = hybrid_df[hybrid_df['risk_level'].isin(['CRITICAL', 'HIGH'])]
if len(high_risk) > 0:
    high_risk_file = r'c:\amttp\processed\hybrid_high_risk.csv'
    high_risk.to_csv(high_risk_file, index=False)
    print(f"  ✅ Saved {len(high_risk):,} high-risk addresses to {high_risk_file}")

# Summary statistics
print("\n" + "=" * 70)
print("SUMMARY STATISTICS")
print("=" * 70)
print(f"  Total flagged addresses: {len(hybrid_df):,}")
print(f"  Hybrid score range: {hybrid_df['hybrid_score'].min():.1f} - {hybrid_df['hybrid_score'].max():.1f}")
print(f"  Mean hybrid score: {hybrid_df['hybrid_score'].mean():.1f}")
print(f"  Median hybrid score: {hybrid_df['hybrid_score'].median():.1f}")

if 'pattern_count' in hybrid_df.columns:
    multi = hybrid_df[hybrid_df['pattern_count'] >= 3]
    print(f"  Multi-pattern addresses (≥3): {len(multi):,}")

print("\n" + "=" * 70)
print("HYBRID SCORING COMPLETE")
print("=" * 70)
