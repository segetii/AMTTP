"""
Test recalibrated ML settings - Check for false positives
"""
import pandas as pd
import numpy as np

print("=" * 70)
print("TESTING RECALIBRATED SETTINGS - FALSE POSITIVE ANALYSIS")
print("=" * 70)

# Load all data
cross_validated = pd.read_csv('c:/amttp/processed/cross_validated_results.csv')
hybrid = pd.read_csv('c:/amttp/processed/hybrid_risk_scores.csv')
sophisticated = pd.read_csv('c:/amttp/processed/sophisticated_fraud_patterns.csv')

# NEW calibrated thresholds
NEW_THRESHOLDS = {
    "threshold": 0.50,
    "approve": 0.20,
    "monitor": 0.35,
    "review": 0.50,
    "escrow": 0.65,
}

# OLD thresholds for comparison
OLD_THRESHOLDS = {
    "threshold": 0.96,
    "approve": 0.25,
    "monitor": 0.40,
    "review": 0.70,
    "escrow": 0.85,
}

print(f"\nTotal addresses in dataset: {len(cross_validated)}")

# Classify with OLD thresholds
old_review = cross_validated[cross_validated['ml_max_score'] >= OLD_THRESHOLDS['review']]
old_escrow = cross_validated[cross_validated['ml_max_score'] >= OLD_THRESHOLDS['escrow']]

# Classify with NEW thresholds
new_review = cross_validated[cross_validated['ml_max_score'] >= NEW_THRESHOLDS['review']]
new_escrow = cross_validated[cross_validated['ml_max_score'] >= NEW_THRESHOLDS['escrow']]

print("\n" + "=" * 70)
print("DETECTION COMPARISON: OLD vs NEW")
print("=" * 70)

print(f"\n  REVIEW threshold (manual review required):")
print(f"    OLD (≥0.70): {len(old_review)} addresses flagged")
print(f"    NEW (≥0.50): {len(new_review)} addresses flagged")
print(f"    Difference:  +{len(new_review) - len(old_review)} more flagged")

print(f"\n  ESCROW threshold (hold funds):")
print(f"    OLD (≥0.85): {len(old_escrow)} addresses flagged")
print(f"    NEW (≥0.65): {len(new_escrow)} addresses flagged")
print(f"    Difference:  +{len(new_escrow) - len(old_escrow)} more flagged")

# Check: How many of the NEW flags have supporting evidence?
print("\n" + "=" * 70)
print("FALSE POSITIVE ANALYSIS")
print("=" * 70)

# Get addresses flagged by NEW but not OLD
new_only = new_review[~new_review['address'].isin(old_review['address'])]
print(f"\n  Newly flagged addresses (NEW caught, OLD missed): {len(new_only)}")

# Check if they have graph evidence or pattern evidence
new_only_with_evidence = 0
new_only_false_positives = []

pattern_addrs = set(sophisticated['address'].str.lower())

for _, row in new_only.iterrows():
    addr = row['address'].lower()
    has_graph = row['risk_score'] > 0
    has_pattern = addr in pattern_addrs
    has_validation = row['validation_status'] in ['BOTH_HIGH', 'ML_ONLY']
    
    if has_graph or has_pattern:
        new_only_with_evidence += 1
    else:
        # Potential false positive - flagged only by ML with no other evidence
        new_only_false_positives.append({
            'address': row['address'],
            'ml_score': row['ml_max_score'],
            'graph_score': row['risk_score'],
            'validation': row['validation_status']
        })

print(f"  With supporting evidence (graph or patterns): {new_only_with_evidence}")
print(f"  Potential false positives (ML only, no evidence): {len(new_only_false_positives)}")

if new_only_false_positives:
    fp_rate = len(new_only_false_positives) / len(new_only) * 100 if len(new_only) > 0 else 0
    print(f"\n  ⚠️  False Positive Rate: {fp_rate:.1f}%")
    
    print("\n  Potential false positives (showing top 10):")
    for fp in new_only_false_positives[:10]:
        print(f"    {fp['address'][:42]}...")
        print(f"      ML: {fp['ml_score']:.3f} | Graph: {fp['graph_score']} | Status: {fp['validation']}")

# Calculate optimal threshold to minimize FPs while catching threats
print("\n" + "=" * 70)
print("FINDING OPTIMAL THRESHOLD")
print("=" * 70)

# Get true threats (have both high hybrid score AND evidence)
true_threats = hybrid[
    (hybrid['risk_level'].isin(['CRITICAL', 'HIGH'])) & 
    (hybrid['signal_count'] >= 2)  # At least 2 signals = likely real threat
]
true_threat_addrs = set(true_threats['address'].str.lower())

# Test different thresholds
thresholds_to_test = [0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70]

print("\n  Threshold | Flagged | True Threats Caught | False Positives | FP Rate")
print("  " + "-" * 70)

best_threshold = 0.50
best_f1 = 0

for thresh in thresholds_to_test:
    flagged = cross_validated[cross_validated['ml_max_score'] >= thresh]
    flagged_addrs = set(flagged['address'].str.lower())
    
    # True positives = flagged AND is true threat
    tp = len(flagged_addrs & true_threat_addrs)
    # False positives = flagged but NOT true threat and no other evidence
    fp_candidates = flagged[~flagged['address'].str.lower().isin(true_threat_addrs)]
    fp = len(fp_candidates[fp_candidates['risk_score'] == 0])  # No graph evidence
    
    # Recall = caught / total threats
    recall = tp / len(true_threat_addrs) * 100 if true_threat_addrs else 0
    # Precision = true positives / flagged
    precision = tp / len(flagged) * 100 if len(flagged) > 0 else 0
    # FP rate
    fp_rate = fp / len(flagged) * 100 if len(flagged) > 0 else 0
    
    # F1 score
    f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0
    
    marker = " ← CURRENT" if thresh == 0.50 else ""
    if thresh == 0.70:
        marker = " ← OLD"
    
    print(f"    {thresh:.2f}   |  {len(flagged):5}  |        {tp:2}          |       {fp:4}      |  {fp_rate:5.1f}%{marker}")
    
    if f1 > best_f1:
        best_f1 = f1
        best_threshold = thresh

print(f"\n  📊 OPTIMAL THRESHOLD: {best_threshold} (best F1 score)")

# Final recommendation
print("\n" + "=" * 70)
print("RECOMMENDATION")
print("=" * 70)

# Count by category with new thresholds
categories = {
    'approve': cross_validated[cross_validated['ml_max_score'] < NEW_THRESHOLDS['approve']],
    'monitor': cross_validated[(cross_validated['ml_max_score'] >= NEW_THRESHOLDS['approve']) & 
                               (cross_validated['ml_max_score'] < NEW_THRESHOLDS['monitor'])],
    'review': cross_validated[(cross_validated['ml_max_score'] >= NEW_THRESHOLDS['monitor']) & 
                              (cross_validated['ml_max_score'] < NEW_THRESHOLDS['review'])],
    'flag': cross_validated[(cross_validated['ml_max_score'] >= NEW_THRESHOLDS['review']) & 
                            (cross_validated['ml_max_score'] < NEW_THRESHOLDS['escrow'])],
    'escrow': cross_validated[cross_validated['ml_max_score'] >= NEW_THRESHOLDS['escrow']],
}

print(f"\n  Distribution with NEW thresholds:")
print(f"    ✅ APPROVE (< 0.20):  {len(categories['approve']):,} addresses")
print(f"    👁️ MONITOR (0.20-0.35): {len(categories['monitor']):,} addresses")  
print(f"    🔍 REVIEW (0.35-0.50):  {len(categories['review']):,} addresses")
print(f"    🚨 FLAG (0.50-0.65):    {len(categories['flag']):,} addresses")
print(f"    🛑 ESCROW (≥ 0.65):     {len(categories['escrow']):,} addresses")

# Check if thresholds are too aggressive
total_flagged = len(categories['flag']) + len(categories['escrow'])
flag_rate = total_flagged / len(cross_validated) * 100

print(f"\n  Total flagged (FLAG + ESCROW): {total_flagged} ({flag_rate:.2f}%)")

if flag_rate > 5:
    print(f"\n  ⚠️  WARNING: Flag rate is {flag_rate:.2f}% - might be too aggressive!")
    print(f"      Consider raising review threshold to 0.55 or 0.60")
elif flag_rate < 0.5:
    print(f"\n  ⚠️  WARNING: Flag rate is only {flag_rate:.2f}% - might miss threats!")
else:
    print(f"\n  ✅ Flag rate of {flag_rate:.2f}% is reasonable (1-5% is typical)")
