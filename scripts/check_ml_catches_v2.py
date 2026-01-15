"""
Check if the ML model caught any of the new discoveries - FIXED
"""
import pandas as pd

# Load all data
combined = pd.read_csv('c:/amttp/processed/combined_all_methods.csv')
consensus = pd.read_csv('c:/amttp/processed/consensus_high_risk.csv')
critical = pd.read_csv('c:/amttp/processed/critical_risk_addresses.csv')
high_risk = pd.read_csv('c:/amttp/processed/high_risk_addresses.csv')
cross_validated = pd.read_csv('c:/amttp/processed/cross_validated_results.csv')
high_risk_tx = pd.read_csv('c:/amttp/processed/high_risk_transactions.csv')

# Find the 24 NEW discoveries
combined_addrs = set(combined['address'].str.lower())
consensus_addrs = set(consensus['address'].str.lower())
critical_addrs = set(critical['address'].str.lower())
high_risk_addrs = set(high_risk['address'].str.lower())
previously_known = consensus_addrs | critical_addrs | high_risk_addrs
new_discoveries = combined_addrs - previously_known

print("=" * 70)
print("DID YOUR ML MODEL CATCH THE 24 NEW DISCOVERIES?")
print("=" * 70)

# Check cross_validated (has ML scores)
cv_addrs = set(cross_validated['address'].str.lower())
cv_caught = new_discoveries & cv_addrs

print(f"\n📊 NEW DISCOVERIES: {len(new_discoveries)}")
print(f"📊 Cross-validated dataset has: {len(cv_addrs)} addresses")

# Analyze each new discovery
print("\n" + "=" * 70)
print("DETAILED ANALYSIS")
print("=" * 70)

ml_caught = []
ml_missed = []

for addr in new_discoveries:
    # Check if in cross-validated
    cv_match = cross_validated[cross_validated['address'].str.lower() == addr]
    hr_match = high_risk_tx[high_risk_tx['address'].str.lower() == addr]
    
    combined_row = combined[combined['address'].str.lower() == addr].iloc[0]
    combined_score = combined_row['combined_total']
    patterns = combined_row['patterns']
    
    if len(cv_match) > 0:
        ml_max = cv_match.iloc[0]['ml_max_score']
        ml_avg = cv_match.iloc[0]['ml_avg_score']
        validation = cv_match.iloc[0]['validation_status']
        ml_caught.append({
            'address': addr,
            'combined_score': combined_score,
            'patterns': patterns,
            'ml_max': ml_max,
            'ml_avg': ml_avg,
            'validation': validation
        })
    elif len(hr_match) > 0:
        ml_caught.append({
            'address': addr,
            'combined_score': combined_score,
            'patterns': patterns,
            'ml_max': 'N/A (graph)',
            'ml_avg': 'N/A',
            'validation': 'high_risk_tx'
        })
    else:
        ml_missed.append({
            'address': addr,
            'combined_score': combined_score,
            'patterns': patterns
        })

# Sort by combined score
ml_caught = sorted(ml_caught, key=lambda x: -x['combined_score'])
ml_missed = sorted(ml_missed, key=lambda x: -x['combined_score'])

print(f"\n✅ ML CAUGHT: {len(ml_caught)} addresses")
print("-" * 70)
for item in ml_caught[:10]:
    print(f"  {item['address'][:42]}...")
    print(f"    Combined: {item['combined_score']:.1f} | ML Max: {item['ml_max']} | Status: {item['validation']}")
    print(f"    Patterns: {item['patterns']}")
    print()

print(f"\n❌ ML COMPLETELY MISSED: {len(ml_missed)} addresses")
print("-" * 70)
for item in ml_missed[:10]:
    print(f"  {item['address'][:42]}...")
    print(f"    Combined: {item['combined_score']:.1f}")
    print(f"    Patterns: {item['patterns']}")
    print()

# Final verdict
print("=" * 70)
print("FINAL VERDICT")
print("=" * 70)
pct_caught = (len(ml_caught) / len(new_discoveries)) * 100 if new_discoveries else 0
print(f"""
  Total new discoveries:    {len(new_discoveries)}
  ML caught:                {len(ml_caught)} ({pct_caught:.1f}%)
  ML missed:                {len(ml_missed)} ({100-pct_caught:.1f}%)
""")

if len(ml_missed) > 0:
    print("  ⚠️  The behavioral pattern analysis (smurfing, layering, etc.)")
    print("      caught threats that ML behavioral scoring MISSED!")
    print("      This proves the value of multi-layered detection.")
else:
    print("  ✅ ML caught everything! Excellent model performance.")
