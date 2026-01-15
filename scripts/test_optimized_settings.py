"""
Test OPTIMIZED ML settings - Require multi-signal for flagging
"""
import pandas as pd
import numpy as np

print("=" * 70)
print("TESTING OPTIMIZED SETTINGS (Multi-Signal Required)")
print("=" * 70)

# Load all data
cross_validated = pd.read_csv('c:/amttp/processed/cross_validated_results.csv')
hybrid = pd.read_csv('c:/amttp/processed/hybrid_risk_scores.csv')
sophisticated = pd.read_csv('c:/amttp/processed/sophisticated_fraud_patterns.csv')

# OPTIMIZED thresholds
OPTIMIZED = {
    "threshold": 0.55,
    "approve": 0.20,
    "monitor": 0.40,
    "review": 0.55,
    "escrow": 0.75,
    "require_multi_signal": True
}

print(f"\nTotal addresses: {len(cross_validated)}")
print(f"\n📊 OPTIMIZED THRESHOLDS:")
for k, v in OPTIMIZED.items():
    print(f"   {k}: {v}")

# Get pattern addresses
pattern_addrs = set(sophisticated['address'].str.lower())

# Apply multi-signal logic
print("\n" + "=" * 70)
print("MULTI-SIGNAL DETECTION RESULTS")
print("=" * 70)

flagged_addresses = []
false_positives = []
true_threats = []

for _, row in cross_validated.iterrows():
    addr = row['address'].lower()
    ml_score = row['ml_max_score']
    graph_score = row['risk_score']
    
    # Check signals
    ml_signal = ml_score >= OPTIMIZED['review']  # ML thinks it's risky
    graph_signal = graph_score > 0  # Has graph evidence
    pattern_signal = addr in pattern_addrs  # Has behavioral pattern
    
    signal_count = sum([ml_signal, graph_signal, pattern_signal])
    
    # Determine action
    if ml_score < OPTIMIZED['approve']:
        action = 'APPROVE'
    elif ml_score < OPTIMIZED['monitor']:
        action = 'MONITOR'
    elif ml_score < OPTIMIZED['review']:
        action = 'REVIEW'
    elif OPTIMIZED['require_multi_signal'] and signal_count < 2:
        # ML flags it but no corroborating evidence - don't flag, just review
        action = 'REVIEW'  # Downgrade from FLAG to REVIEW
    elif ml_score >= OPTIMIZED['escrow'] and signal_count >= 2:
        action = 'ESCROW'
    else:
        action = 'FLAG'
    
    if action in ['FLAG', 'ESCROW']:
        flagged_addresses.append({
            'address': row['address'],
            'ml_score': ml_score,
            'graph_score': graph_score,
            'has_pattern': pattern_signal,
            'signal_count': signal_count,
            'action': action
        })
        
        # Check if likely true threat
        if signal_count >= 2:
            true_threats.append(row['address'])
        else:
            false_positives.append(row['address'])

print(f"\n  Total flagged (FLAG + ESCROW): {len(flagged_addresses)}")
print(f"  With 2+ signals (likely true threats): {len(true_threats)}")
print(f"  With 1 signal (potential false positives): {len(false_positives)}")

fp_rate = len(false_positives) / len(flagged_addresses) * 100 if flagged_addresses else 0
print(f"\n  📊 FALSE POSITIVE RATE: {fp_rate:.1f}%")

# Show flagged addresses
if flagged_addresses:
    print("\n" + "=" * 70)
    print("FLAGGED ADDRESSES (sorted by signal count)")
    print("=" * 70)
    
    flagged_df = pd.DataFrame(flagged_addresses)
    flagged_df = flagged_df.sort_values(['signal_count', 'ml_score'], ascending=[False, False])
    
    for _, row in flagged_df.iterrows():
        signals = "🎯" * row['signal_count']
        pattern_mark = "📊" if row['has_pattern'] else ""
        graph_mark = "🔗" if row['graph_score'] > 0 else ""
        print(f"  {row['address'][:42]}...")
        print(f"    ML: {row['ml_score']:.3f} | Graph: {row['graph_score']} | Action: {row['action']} {signals} {graph_mark}{pattern_mark}")

# Compare with OLD settings
print("\n" + "=" * 70)
print("COMPARISON: OLD vs OPTIMIZED")
print("=" * 70)

# OLD settings would flag everyone with ML >= 0.70
old_flagged = cross_validated[cross_validated['ml_max_score'] >= 0.70]
old_with_evidence = old_flagged[
    (old_flagged['risk_score'] > 0) | 
    (old_flagged['address'].str.lower().isin(pattern_addrs))
]

print(f"\n  OLD SETTINGS (threshold 0.70, no multi-signal):")
print(f"    Flagged: {len(old_flagged)}")
print(f"    With evidence: {len(old_with_evidence)}")
print(f"    False positive rate: {(len(old_flagged) - len(old_with_evidence)) / len(old_flagged) * 100:.1f}%" if len(old_flagged) > 0 else "    N/A")

print(f"\n  OPTIMIZED SETTINGS (threshold 0.55, multi-signal required):")
print(f"    Flagged: {len(flagged_addresses)}")
print(f"    With evidence: {len(true_threats)}")
print(f"    False positive rate: {fp_rate:.1f}%")

# Get true threats caught
hybrid_critical = hybrid[hybrid['risk_level'].isin(['CRITICAL', 'HIGH'])]
hybrid_critical_addrs = set(hybrid_critical['address'].str.lower())

old_caught_critical = len(set(old_flagged['address'].str.lower()) & hybrid_critical_addrs)
new_caught_critical = len(set([f['address'].lower() for f in flagged_addresses]) & hybrid_critical_addrs)

print(f"\n  CRITICAL/HIGH threats caught:")
print(f"    OLD: {old_caught_critical} / {len(hybrid_critical_addrs)}")
print(f"    OPTIMIZED: {new_caught_critical} / {len(hybrid_critical_addrs)}")

print("\n" + "=" * 70)
print("FINAL VERDICT")
print("=" * 70)

if fp_rate < 20:
    print(f"\n  ✅ EXCELLENT! False positive rate of {fp_rate:.1f}% is acceptable")
elif fp_rate < 40:
    print(f"\n  ⚠️ ACCEPTABLE: False positive rate of {fp_rate:.1f}% is manageable")
else:
    print(f"\n  ❌ TOO HIGH: False positive rate of {fp_rate:.1f}% needs adjustment")

print(f"""
  Summary:
    - Total addresses reviewed: {len(cross_validated):,}
    - Flagged for action: {len(flagged_addresses)} ({len(flagged_addresses)/len(cross_validated)*100:.2f}%)
    - Critical threats caught: {new_caught_critical}/{len(hybrid_critical_addrs)}
    - False positive rate: {fp_rate:.1f}%
    - Multi-signal requirement: ENABLED
""")
