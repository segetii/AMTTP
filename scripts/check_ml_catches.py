"""
Check if the ML model caught any of the new discoveries
"""
import pandas as pd

# Load new discoveries (24 addresses we found via cross-referencing)
combined = pd.read_csv('c:/amttp/processed/combined_all_methods.csv')
consensus = pd.read_csv('c:/amttp/processed/consensus_high_risk.csv')
critical = pd.read_csv('c:/amttp/processed/critical_risk_addresses.csv')
high_risk = pd.read_csv('c:/amttp/processed/high_risk_addresses.csv')

# Load ML results  
cross_validated = pd.read_csv('c:/amttp/processed/cross_validated_results.csv')
scored_tx = pd.read_csv('c:/amttp/processed/scored_transactions.csv')

print("=" * 70)
print("ML MODEL ANALYSIS")
print("=" * 70)

print("\nCross-validated results columns:", cross_validated.columns.tolist())
print("Scored transactions columns:", scored_tx.columns.tolist()[:10], "...")

# Find new discoveries
combined_addrs = set(combined['address'].str.lower())
consensus_addrs = set(consensus['address'].str.lower()) if 'address' in consensus.columns else set()
critical_addrs = set(critical['address'].str.lower()) if 'address' in critical.columns else set()
high_risk_addrs = set(high_risk['address'].str.lower()) if 'address' in high_risk.columns else set()
previously_known = consensus_addrs | critical_addrs | high_risk_addrs
new_discoveries = combined_addrs - previously_known

print(f"\nNew discoveries to check: {len(new_discoveries)}")

# Check cross_validated for ML predictions
print("\n" + "=" * 70)
print("CROSS-VALIDATED RESULTS (ML + Graph)")
print("=" * 70)

# Look for address columns
addr_cols = [c for c in cross_validated.columns if 'addr' in c.lower() or 'from' in c.lower() or 'to' in c.lower()]
print(f"Address columns found: {addr_cols}")

if 'from_address' in cross_validated.columns:
    cv_addrs = set(cross_validated['from_address'].str.lower())
    ml_caught = new_discoveries & cv_addrs
    print(f"\nML cross-validated caught: {len(ml_caught)} of {len(new_discoveries)} new discoveries")
    
    if ml_caught:
        print("\n🤖 ML DID CATCH THESE:")
        for addr in list(ml_caught)[:10]:
            row = cross_validated[cross_validated['from_address'].str.lower() == addr].iloc[0]
            ml_score = row.get('ml_risk_score', row.get('risk_score', 'N/A'))
            ml_pred = row.get('ml_prediction', row.get('prediction', 'N/A'))
            print(f"  {addr[:42]}...")
            print(f"    ML Score: {ml_score}, Prediction: {ml_pred}")

# Check scored_transactions 
print("\n" + "=" * 70)
print("SCORED TRANSACTIONS (Pure ML)")
print("=" * 70)

if 'from_address' in scored_tx.columns:
    scored_addrs = set(scored_tx['from_address'].str.lower())
    ml_in_scored = new_discoveries & scored_addrs
    print(f"\nNew discoveries in scored_transactions: {len(ml_in_scored)}")
    
    # Check if they were marked as high risk by ML
    if 'ml_risk_score' in scored_tx.columns or 'risk_score' in scored_tx.columns:
        score_col = 'ml_risk_score' if 'ml_risk_score' in scored_tx.columns else 'risk_score'
        
        ml_high_risk = []
        for addr in new_discoveries:
            matches = scored_tx[scored_tx['from_address'].str.lower() == addr]
            if len(matches) > 0:
                max_score = matches[score_col].max()
                if max_score > 0.5:  # Threshold for "high risk"
                    ml_high_risk.append((addr, max_score))
        
        print(f"\nML flagged as high-risk (score > 0.5): {len(ml_high_risk)}")
        
        if ml_high_risk:
            print("\n🤖 ML CAUGHT (score > 0.5):")
            for addr, score in sorted(ml_high_risk, key=lambda x: -x[1])[:10]:
                combined_row = combined[combined['address'].str.lower() == addr]
                if len(combined_row) > 0:
                    patterns = combined_row.iloc[0]['patterns']
                else:
                    patterns = 'N/A'
                print(f"  {addr[:42]}... ML: {score:.3f} | Patterns: {patterns}")

# Load high_risk_transactions for ML predictions
print("\n" + "=" * 70)
print("HIGH RISK TRANSACTIONS (ML Flagged)")
print("=" * 70)

high_risk_tx = pd.read_csv('c:/amttp/processed/high_risk_transactions.csv')
print(f"Columns: {high_risk_tx.columns.tolist()[:8]}...")
print(f"Total high-risk transactions: {len(high_risk_tx)}")

if 'from_address' in high_risk_tx.columns:
    hr_addrs = set(high_risk_tx['from_address'].str.lower())
    ml_hr_caught = new_discoveries & hr_addrs
    print(f"\n🤖 ML HIGH-RISK CAUGHT: {len(ml_hr_caught)} of {len(new_discoveries)} new discoveries")
    
    if ml_hr_caught:
        print("\nThese were in ML's high-risk list:")
        for addr in list(ml_hr_caught)[:10]:
            combined_row = combined[combined['address'].str.lower() == addr]
            if len(combined_row) > 0:
                score = combined_row.iloc[0]['combined_total']
                patterns = combined_row.iloc[0]['patterns']
            else:
                score = 'N/A'
                patterns = 'N/A'
            print(f"  {addr[:42]}... Combined: {score} | {patterns}")

# Final Summary
print("\n" + "=" * 70)
print("FINAL VERDICT: DID ML CATCH THE NEW DISCOVERIES?")
print("=" * 70)

if 'from_address' in high_risk_tx.columns:
    ml_hr_caught = new_discoveries & set(high_risk_tx['from_address'].str.lower())
    ml_missed = new_discoveries - set(high_risk_tx['from_address'].str.lower())
    
    pct_caught = (len(ml_hr_caught) / len(new_discoveries)) * 100 if new_discoveries else 0
    
    print(f"\n  ✅ ML caught:  {len(ml_hr_caught)} ({pct_caught:.1f}%)")
    print(f"  ❌ ML missed:  {len(ml_missed)} ({100-pct_caught:.1f}%)")
    
    if ml_missed:
        print("\n  🚨 ML COMPLETELY MISSED THESE:")
        for addr in list(ml_missed)[:5]:
            combined_row = combined[combined['address'].str.lower() == addr]
            if len(combined_row) > 0:
                score = combined_row.iloc[0]['combined_total']
                patterns = combined_row.iloc[0]['patterns']
                print(f"    {addr[:42]}...")
                print(f"      Score: {score} | Patterns: {patterns}")
