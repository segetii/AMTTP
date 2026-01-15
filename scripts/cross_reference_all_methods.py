"""
Cross-Reference: Sophisticated Fraud Patterns + Graph Analysis
Finds addresses that exhibit BOTH behavioral patterns AND connections to sanctioned/mixer addresses.
"""
import pandas as pd

print("="*70)
print("CROSS-REFERENCING: Sophisticated Patterns + Graph Analysis")
print("="*70)

# Load sophisticated patterns (smurfing, layering, etc.)
soph = pd.read_csv(r'c:\amttp\processed\sophisticated_fraud_patterns.csv')
print(f"Sophisticated patterns: {len(soph)} addresses")

# Load graph analysis (sanctioned connections)
graph = pd.read_csv(r'c:\amttp\processed\scored_transactions_expanded.csv')
print(f"Graph analysis: {len(graph)} addresses")

# Load consensus high-risk
try:
    consensus = pd.read_csv(r'c:\amttp\processed\consensus_high_risk.csv')
    print(f"Consensus high-risk: {len(consensus)} addresses")
except:
    consensus = pd.DataFrame()

# Normalize addresses
soph['address_lower'] = soph['address'].str.lower()
graph['address_lower'] = graph['address'].str.lower()

# Merge sophisticated patterns with graph analysis
merged = soph.merge(
    graph[['address_lower', 'risk_score', 'reasons']], 
    on='address_lower', 
    how='left'
)
merged['risk_score'] = merged['risk_score'].fillna(0)
merged['reasons'] = merged['reasons'].fillna('')

# Calculate combined score
merged['combined_total'] = merged['sophisticated_score'] + merged['risk_score']

# Sort by combined score
merged = merged.sort_values('combined_total', ascending=False)

print()
print("="*70)
print("ADDRESSES WITH BOTH SOPHISTICATED PATTERNS AND GRAPH CONNECTIONS")
print("="*70)

# Find addresses with BOTH sophisticated patterns AND graph connections
both = merged[(merged['sophisticated_score'] > 0) & (merged['risk_score'] > 0)].copy()
print(f"\n🚨 Found {len(both)} addresses with BOTH types of risk!")

if len(both) > 0:
    print()
    print("🔴 TOP 15 MOST DANGEROUS ADDRESSES:")
    print("-"*70)
    
    for idx, (i, row) in enumerate(both.head(15).iterrows()):
        addr = row['address']
        soph_score = row['sophisticated_score']
        patterns = row['patterns']
        graph_score = row['risk_score']
        graph_reasons = row['reasons'][:60] if row['reasons'] else 'N/A'
        total = row['combined_total']
        
        print(f"\n  #{idx+1} {addr}")
        print(f"      Sophisticated: {soph_score:.0f} pts")
        print(f"        Patterns: {patterns}")
        print(f"      Graph:         {graph_score:.0f} pts")
        print(f"        Reasons: {graph_reasons}")
        print(f"      ─────────────────────────")
        print(f"      TOTAL SCORE:   {total:.0f}")

# Risk categorization
print()
print("="*70)
print("RISK CATEGORIZATION")
print("="*70)

critical = both[both['combined_total'] >= 300]
high = both[(both['combined_total'] >= 150) & (both['combined_total'] < 300)]
medium = both[(both['combined_total'] >= 50) & (both['combined_total'] < 150)]

print(f"\n🔴 CRITICAL (score >= 300): {len(critical)} addresses")
print(f"🟠 HIGH (150-299):          {len(high)} addresses")
print(f"🟡 MEDIUM (50-149):         {len(medium)} addresses")

# Pattern + Graph correlation analysis
print()
print("="*70)
print("PATTERN CORRELATION WITH SANCTIONED CONNECTIONS")
print("="*70)

# Which sophisticated patterns correlate most with graph connections?
pattern_correlations = []
for pattern in ['SMURFING', 'FAN_OUT', 'FAN_IN', 'PEELING', 'LAYERING', 'STRUCTURING']:
    pattern_addresses = soph[soph['patterns'].str.contains(pattern, na=False)]
    with_graph = pattern_addresses.merge(
        graph[graph['risk_score'] > 0][['address_lower']], 
        on='address_lower'
    )
    correlation_rate = len(with_graph) / len(pattern_addresses) * 100 if len(pattern_addresses) > 0 else 0
    pattern_correlations.append({
        'pattern': pattern,
        'total_addresses': len(pattern_addresses),
        'with_graph_connection': len(with_graph),
        'correlation_rate': correlation_rate
    })

corr_df = pd.DataFrame(pattern_correlations)
corr_df = corr_df.sort_values('correlation_rate', ascending=False)

print("\nWhich patterns correlate most with sanctioned/mixer connections?")
print("-"*60)
for _, row in corr_df.iterrows():
    bar = '█' * int(row['correlation_rate'] / 5)
    print(f"  {row['pattern']:12} {bar} {row['correlation_rate']:.1f}% ({row['with_graph_connection']}/{row['total_addresses']})")

# Save results
both.to_csv(r'c:\amttp\processed\combined_all_methods.csv', index=False)
print(f"\n✅ Saved {len(both)} combined high-risk addresses to combined_all_methods.csv")

# Summary
print()
print("="*70)
print("FINAL SUMMARY")
print("="*70)
print(f"\n📊 Detection Method Breakdown:")
print(f"   Sophisticated patterns only: {len(merged[merged['risk_score'] == 0])}")
print(f"   Graph connections only:      {len(graph) - len(both)}")
print(f"   BOTH methods (highest risk): {len(both)}")

print(f"\n🎯 Action Required:")
print(f"   {len(critical)} addresses need IMMEDIATE investigation (critical)")
print(f"   {len(high)} addresses need priority review (high)")
print(f"   {len(medium)} addresses should be monitored (medium)")
