"""
Check if cross-referenced addresses were already caught or newly discovered
"""
import pandas as pd

# Load all results
combined = pd.read_csv('c:/amttp/processed/combined_all_methods.csv')
consensus = pd.read_csv('c:/amttp/processed/consensus_high_risk.csv')
critical = pd.read_csv('c:/amttp/processed/critical_risk_addresses.csv')
high_risk = pd.read_csv('c:/amttp/processed/high_risk_addresses.csv')

combined_addrs = set(combined['address'].str.lower())
consensus_addrs = set(consensus['address'].str.lower()) if 'address' in consensus.columns else set()
critical_addrs = set(critical['address'].str.lower()) if 'address' in critical.columns else set()
high_risk_addrs = set(high_risk['address'].str.lower()) if 'address' in high_risk.columns else set()

# Previously known = in consensus OR critical OR high_risk
previously_known = consensus_addrs | critical_addrs | high_risk_addrs

# New discoveries
new_discoveries = combined_addrs - previously_known
already_caught = combined_addrs & previously_known

print('=' * 70)
print('DISCOVERY ANALYSIS: Were these addresses caught before?')
print('=' * 70)
print(f'\nTotal combined high-risk addresses: {len(combined_addrs)}')
print(f'Previously in consensus list:       {len(combined_addrs & consensus_addrs)}')
print(f'Previously in critical list:        {len(combined_addrs & critical_addrs)}')
print(f'Previously in high-risk list:       {len(combined_addrs & high_risk_addrs)}')
print()
print(f'ALREADY CAUGHT (in any previous list): {len(already_caught)}')
print(f'🆕 NEW DISCOVERIES (cross-ref revealed):  {len(new_discoveries)}')
print()

if new_discoveries:
    print('=' * 70)
    print('🆕 NEW DISCOVERIES - These were MISSED before!')
    print('=' * 70)
    new_df = combined[combined['address'].str.lower().isin(new_discoveries)].sort_values('combined_total', ascending=False)
    for _, row in new_df.iterrows():
        print(f"  {row['address'][:42]}...")
        print(f"    Total Score: {row['combined_total']}")
        print(f"    Patterns: {row['patterns']}")
        graph_reasons = str(row['reasons'])[:60]
        print(f"    Graph: {graph_reasons}...")
        print()

print('=' * 70)
print('✅ ALREADY CAUGHT - Validation of previous detection')
print('=' * 70)
if already_caught:
    caught_df = combined[combined['address'].str.lower().isin(already_caught)].sort_values('combined_total', ascending=False)
    for _, row in caught_df.iterrows():
        in_consensus = '✓' if row['address'].lower() in consensus_addrs else ' '
        in_critical = '✓' if row['address'].lower() in critical_addrs else ' '
        in_high = '✓' if row['address'].lower() in high_risk_addrs else ' '
        print(f"  {row['address'][:42]}...")
        print(f"    Score: {row['combined_total']} [Consensus:{in_consensus}] [Critical:{in_critical}] [HighRisk:{in_high}]")
        print()

# Summary
print('=' * 70)
print('SUMMARY')
print('=' * 70)
pct_new = (len(new_discoveries) / len(combined_addrs)) * 100 if combined_addrs else 0
pct_caught = (len(already_caught) / len(combined_addrs)) * 100 if combined_addrs else 0
print(f"  {pct_new:.1f}% ({len(new_discoveries)}) are NEW - cross-referencing revealed hidden threats!")
print(f"  {pct_caught:.1f}% ({len(already_caught)}) were already caught - validates our detection methods")
