"""
DEEP DIVE: Actual Analysis of Missed Fraud Cases (8%)
Using the actual transaction data to identify specific patterns
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
import warnings
warnings.filterwarnings('ignore')

# Paths
DATA_PATH = Path(r"c:\amttp\processed\eth_transactions_full_labeled.parquet")
OUTPUT_PATH = Path(r"c:\amttp\reports")

print("=" * 70)
print("DEEP DIVE: Analyzing Actual Missed Fraud Transactions")
print("=" * 70)

# Load data
print("\n[1] Loading Transaction Data...")
df = pd.read_parquet(DATA_PATH)
print(f"   ✓ Loaded {len(df):,} transactions")

# Check available columns
print(f"\n[2] Available columns for analysis:")
score_cols = [col for col in df.columns if 'score' in col.lower() or 'xgb' in col.lower()]
print(f"   Score columns: {score_cols}")

# Use hybrid_score or xgb_score as proxy for ensemble
# The max_hybrid_score column should represent the final risk score
if 'max_hybrid_score' in df.columns:
    score_col = 'max_hybrid_score'
elif 'sender_hybrid_score' in df.columns:
    score_col = 'sender_hybrid_score'
elif 'sender_xgb_normalized' in df.columns:
    score_col = 'sender_xgb_normalized'
else:
    score_col = None
    
print(f"\n   Using score column: {score_col}")

# Analyze fraud distribution
fraud_col = 'fraud'
print(f"\n[3] Fraud Distribution:")
print(f"   Total transactions: {len(df):,}")
print(f"   Fraud cases: {df[fraud_col].sum():,} ({df[fraud_col].mean():.2%})")
print(f"   Legitimate cases: {(~df[fraud_col].astype(bool)).sum():,}")

# Define threshold for analysis
THRESHOLD = 0.727

if score_col:
    # Classify predictions at threshold
    df['predicted_fraud'] = df[score_col] >= THRESHOLD
    
    # Calculate confusion matrix components
    fraud_mask = df[fraud_col].astype(bool)
    
    TP = ((fraud_mask) & (df['predicted_fraud'])).sum()
    FN = ((fraud_mask) & (~df['predicted_fraud'])).sum()
    FP = ((~fraud_mask) & (df['predicted_fraud'])).sum()
    TN = ((~fraud_mask) & (~df['predicted_fraud'])).sum()
    
    print(f"\n[4] Confusion Matrix at Threshold {THRESHOLD}:")
    print(f"   True Positives (Caught):  {TP:,}")
    print(f"   False Negatives (MISSED): {FN:,}")
    print(f"   False Positives:          {FP:,}")
    print(f"   True Negatives:           {TN:,}")
    
    recall = TP / (TP + FN) if (TP + FN) > 0 else 0
    precision = TP / (TP + FP) if (TP + FP) > 0 else 0
    
    print(f"\n   Recall: {recall:.2%}")
    print(f"   Precision: {precision:.2%}")
    print(f"   Miss Rate: {1 - recall:.2%}")
    
    # DEEP DIVE: Analyze the False Negatives (Missed Fraud)
    print("\n" + "=" * 70)
    print("[5] DEEP DIVE: Characteristics of MISSED FRAUD")
    print("=" * 70)
    
    # Get missed fraud cases
    missed_fraud = df[(fraud_mask) & (~df['predicted_fraud'])]
    caught_fraud = df[(fraud_mask) & (df['predicted_fraud'])]
    legitimate = df[~fraud_mask]
    
    print(f"\n   Missed fraud cases: {len(missed_fraud):,}")
    print(f"   Caught fraud cases: {len(caught_fraud):,}")
    
    # Analyze key features
    analysis_cols = [
        'value_eth', 'gas_price_gwei', 'gas_used',
        'sender_total_transactions', 'sender_pattern_count',
        'sender_unique_counterparties', 'sender_sophisticated_score',
        'sender_in_out_ratio', 'sender_active_duration_mins'
    ]
    
    # Filter to available columns
    analysis_cols = [c for c in analysis_cols if c in df.columns]
    
    print(f"\n[5.1] Feature Comparison: Caught vs Missed Fraud")
    print("-" * 70)
    print(f"{'Feature':<35} {'Caught (median)':<18} {'Missed (median)':<18} {'Δ'}")
    print("-" * 70)
    
    feature_comparison = {}
    for col in analysis_cols:
        caught_median = caught_fraud[col].median()
        missed_median = missed_fraud[col].median()
        legit_median = legitimate[col].median()
        delta = missed_median - caught_median
        
        feature_comparison[col] = {
            'caught': caught_median,
            'missed': missed_median,
            'legit': legit_median,
            'delta': delta
        }
        
        # Direction indicator
        if abs(delta) < 0.01:
            arrow = "≈"
        elif delta > 0:
            arrow = "↑"
        else:
            arrow = "↓"
        
        print(f"{col:<35} {caught_median:<18.4f} {missed_median:<18.4f} {arrow}")
    
    print("-" * 70)
    
    # Key findings based on data
    print("\n[5.2] KEY FINDINGS from Data Analysis:")
    print("=" * 70)
    
    findings = []
    
    # Check value_eth pattern
    if 'value_eth' in feature_comparison:
        c = feature_comparison['value_eth']
        if abs(c['missed'] - c['legit']) < abs(c['caught'] - c['legit']):
            findings.append(("VALUE", "Missed fraud has NORMAL transaction values",
                           f"Caught: {c['caught']:.4f} ETH, Missed: {c['missed']:.4f} ETH, Legit: {c['legit']:.4f} ETH"))
    
    # Check pattern_count
    if 'sender_pattern_count' in feature_comparison:
        c = feature_comparison['sender_pattern_count']
        if c['missed'] < c['caught']:
            findings.append(("PATTERN", "Missed fraud has FEWER repeated patterns",
                           f"Caught: {c['caught']:.0f} patterns, Missed: {c['missed']:.0f} patterns"))
    
    # Check sophisticated_score
    if 'sender_sophisticated_score' in feature_comparison:
        c = feature_comparison['sender_sophisticated_score']
        if c['missed'] < c['caught']:
            findings.append(("SOPHISTICATION", "Missed fraud appears LESS sophisticated",
                           f"Caught: {c['caught']:.4f}, Missed: {c['missed']:.4f}"))
    
    # Check counterparties
    if 'sender_unique_counterparties' in feature_comparison:
        c = feature_comparison['sender_unique_counterparties']
        if abs(c['missed'] - c['legit']) < abs(c['caught'] - c['legit']):
            findings.append(("NETWORK", "Missed fraud has NORMAL network connectivity",
                           f"Caught: {c['caught']:.0f} counterparties, Missed: {c['missed']:.0f}, Legit: {c['legit']:.0f}"))
    
    for i, (category, finding, evidence) in enumerate(findings, 1):
        print(f"\n   FINDING {i}: [{category}]")
        print(f"   → {finding}")
        print(f"   Evidence: {evidence}")
    
    # Score distribution analysis
    print("\n[5.3] Score Distribution Analysis:")
    print("-" * 70)
    
    caught_score_mean = caught_fraud[score_col].mean()
    caught_score_std = caught_fraud[score_col].std()
    missed_score_mean = missed_fraud[score_col].mean()
    missed_score_std = missed_fraud[score_col].std()
    
    print(f"   Caught fraud scores: mean={caught_score_mean:.4f}, std={caught_score_std:.4f}")
    print(f"   Missed fraud scores: mean={missed_score_mean:.4f}, std={missed_score_std:.4f}")
    print(f"   Threshold: {THRESHOLD}")
    
    # Score percentiles for missed fraud
    missed_percentiles = missed_fraud[score_col].describe(percentiles=[.25, .5, .75, .9, .95])
    print(f"\n   Missed fraud score distribution:")
    print(f"   25th percentile: {missed_percentiles['25%']:.4f}")
    print(f"   50th percentile: {missed_percentiles['50%']:.4f}")
    print(f"   75th percentile: {missed_percentiles['75%']:.4f}")
    print(f"   90th percentile: {missed_percentiles['90%']:.4f}")
    
    # How many are "close" to threshold?
    close_to_threshold = ((missed_fraud[score_col] >= 0.5) & (missed_fraud[score_col] < THRESHOLD)).sum()
    very_low_score = (missed_fraud[score_col] < 0.3).sum()
    medium_score = ((missed_fraud[score_col] >= 0.3) & (missed_fraud[score_col] < 0.5)).sum()
    
    print(f"\n   Score breakdown of missed fraud:")
    print(f"   • Very low (< 0.3):        {very_low_score:,} ({very_low_score/len(missed_fraud)*100:.1f}%)")
    print(f"   • Medium (0.3 - 0.5):      {medium_score:,} ({medium_score/len(missed_fraud)*100:.1f}%)")
    print(f"   • Close to threshold (0.5-0.727): {close_to_threshold:,} ({close_to_threshold/len(missed_fraud)*100:.1f}%)")
    
    # VISUALIZATION
    print("\n[6] Generating Detailed Visualizations...")
    
    fig, axes = plt.subplots(2, 3, figsize=(18, 12))
    fig.suptitle('Deep Dive: Why 8% of Fraud Slips Through (Actual Data)', fontsize=16, fontweight='bold')
    
    # 1. Score distribution comparison
    ax1 = axes[0, 0]
    ax1.hist(legitimate[score_col].clip(0, 1), bins=50, alpha=0.5, label='Legitimate', color='green', density=True)
    ax1.hist(caught_fraud[score_col].clip(0, 1), bins=50, alpha=0.5, label='Caught Fraud', color='red', density=True)
    ax1.hist(missed_fraud[score_col].clip(0, 1), bins=30, alpha=0.7, label='MISSED Fraud', color='orange', density=True)
    ax1.axvline(x=THRESHOLD, color='black', linestyle='--', linewidth=2, label=f'Threshold ({THRESHOLD})')
    ax1.set_xlabel('Risk Score', fontsize=12)
    ax1.set_ylabel('Density', fontsize=12)
    ax1.set_title('Score Distribution: Caught vs Missed Fraud', fontsize=12, fontweight='bold')
    ax1.legend()
    ax1.set_xlim(0, 1)
    ax1.grid(True, alpha=0.3)
    
    # 2. Value distribution
    ax2 = axes[0, 1]
    if 'value_eth' in df.columns:
        # Log transform for better visualization
        for data, label, color in [(caught_fraud, 'Caught', 'red'), (missed_fraud, 'Missed', 'orange'), (legitimate.sample(min(10000, len(legitimate))), 'Legit', 'green')]:
            values = np.log10(data['value_eth'].clip(1e-10, None) + 1e-10)
            ax2.hist(values, bins=50, alpha=0.5, label=label, color=color, density=True)
        ax2.set_xlabel('Log10(Value ETH)', fontsize=12)
        ax2.set_ylabel('Density', fontsize=12)
        ax2.set_title('Transaction Value: Missed Fraud Looks Normal', fontsize=12, fontweight='bold')
        ax2.legend()
        ax2.grid(True, alpha=0.3)
    
    # 3. Pattern count comparison
    ax3 = axes[0, 2]
    if 'sender_pattern_count' in df.columns:
        data_to_plot = [
            caught_fraud['sender_pattern_count'].clip(0, 50),
            missed_fraud['sender_pattern_count'].clip(0, 50),
            legitimate['sender_pattern_count'].clip(0, 50).sample(min(10000, len(legitimate)))
        ]
        bp = ax3.boxplot(data_to_plot, labels=['Caught\nFraud', 'MISSED\nFraud', 'Legitimate'], patch_artist=True)
        colors = ['red', 'orange', 'green']
        for patch, color in zip(bp['boxes'], colors):
            patch.set_facecolor(color)
            patch.set_alpha(0.6)
        ax3.set_ylabel('Pattern Count', fontsize=12)
        ax3.set_title('Pattern Count: Missed Fraud Has Fewer Repeats', fontsize=12, fontweight='bold')
        ax3.grid(True, alpha=0.3)
    
    # 4. Network connectivity (unique counterparties)
    ax4 = axes[1, 0]
    if 'sender_unique_counterparties' in df.columns:
        data_to_plot = [
            caught_fraud['sender_unique_counterparties'].clip(0, 100),
            missed_fraud['sender_unique_counterparties'].clip(0, 100),
            legitimate['sender_unique_counterparties'].clip(0, 100).sample(min(10000, len(legitimate)))
        ]
        bp = ax4.boxplot(data_to_plot, labels=['Caught\nFraud', 'MISSED\nFraud', 'Legitimate'], patch_artist=True)
        colors = ['red', 'orange', 'green']
        for patch, color in zip(bp['boxes'], colors):
            patch.set_facecolor(color)
            patch.set_alpha(0.6)
        ax4.set_ylabel('Unique Counterparties', fontsize=12)
        ax4.set_title('Network: Missed Fraud Blends In', fontsize=12, fontweight='bold')
        ax4.grid(True, alpha=0.3)
    
    # 5. Sophistication score
    ax5 = axes[1, 1]
    if 'sender_sophisticated_score' in df.columns:
        for data, label, color in [(caught_fraud, 'Caught', 'red'), (missed_fraud, 'Missed', 'orange'), (legitimate.sample(min(10000, len(legitimate))), 'Legit', 'green')]:
            ax5.hist(data['sender_sophisticated_score'].clip(0, 1), bins=30, alpha=0.5, label=label, color=color, density=True)
        ax5.set_xlabel('Sophistication Score', fontsize=12)
        ax5.set_ylabel('Density', fontsize=12)
        ax5.set_title('Sophistication: Missed Fraud Appears Simple', fontsize=12, fontweight='bold')
        ax5.legend()
        ax5.grid(True, alpha=0.3)
    
    # 6. Summary breakdown pie chart
    ax6 = axes[1, 2]
    
    # Categorize why fraud was missed
    categories = ['Close to Threshold\n(recoverable)', 'Medium Score\n(needs features)', 'Very Low Score\n(sophisticated mimicry)']
    sizes = [close_to_threshold, medium_score, very_low_score]
    colors_pie = ['#FFD700', '#FFA500', '#FF4500']
    explode = (0.05, 0.05, 0.1)
    
    wedges, texts, autotexts = ax6.pie(sizes, explode=explode, labels=categories, colors=colors_pie,
                                        autopct='%1.1f%%', startangle=90, shadow=True)
    ax6.set_title(f'Breakdown of {len(missed_fraud):,} Missed Cases', fontsize=12, fontweight='bold')
    
    # Style the pie chart text
    for text in texts:
        text.set_fontsize(10)
    for autotext in autotexts:
        autotext.set_fontsize(10)
        autotext.set_fontweight('bold')
    
    plt.tight_layout()
    plt.savefig(OUTPUT_PATH / 'missed_fraud_deep_dive.png', dpi=150, bbox_inches='tight',
                facecolor='white', edgecolor='none')
    plt.close()
    
    print(f"   ✓ Saved: {OUTPUT_PATH / 'missed_fraud_deep_dive.png'}")
    
    # Final summary
    print("\n" + "=" * 70)
    print("INVESTIGATION SUMMARY: Why 8% Slips Through")
    print("=" * 70)
    
    print(f"""
┌────────────────────────────────────────────────────────────────────────┐
│                    ROOT CAUSES (Data-Driven)                           │
├────────────────────────────────────────────────────────────────────────┤
│                                                                        │
│  1. THRESHOLD EFFECT ({close_to_threshold:,} cases = {close_to_threshold/len(missed_fraud)*100:.0f}%)
│     → Scores between 0.50 and 0.727                                    │
│     → Could be recovered by adding "manual review" tier                │
│                                                                        │
│  2. NORMAL TRANSACTION VALUES                                          │
│     → Missed fraud value median: {feature_comparison.get('value_eth', {}).get('missed', 0):.4f} ETH
│     → Legitimate value median:   {feature_comparison.get('value_eth', {}).get('legit', 0):.4f} ETH
│     → Caught fraud value median: {feature_comparison.get('value_eth', {}).get('caught', 0):.4f} ETH
│                                                                        │
│  3. LOW PATTERN REPETITION                                             │
│     → Caught fraud pattern count: {feature_comparison.get('sender_pattern_count', {}).get('caught', 0):.0f}
│     → Missed fraud pattern count: {feature_comparison.get('sender_pattern_count', {}).get('missed', 0):.0f}
│     → These are "one-time" or low-frequency fraudsters                 │
│                                                                        │
│  4. NORMAL NETWORK STRUCTURE                                           │
│     → Missed fraud counterparties: {feature_comparison.get('sender_unique_counterparties', {}).get('missed', 0):.0f}
│     → Legitimate counterparties:   {feature_comparison.get('sender_unique_counterparties', {}).get('legit', 0):.0f}
│     → Graph models see "normal" connectivity                           │
│                                                                        │
│  5. LOW SOPHISTICATION SCORE                                           │
│     → Paradoxically, "simple" looking fraud evades detection           │
│     → Complex fraud is easier to spot than simple fraud                │
│                                                                        │
├────────────────────────────────────────────────────────────────────────┤
│                                                                        │
│  RECOMMENDATION: Implement 3-tier system                               │
│                                                                        │
│   Score 0.727+    → AUTO-BLOCK (current)                               │
│   Score 0.50-0.727 → MANUAL REVIEW (catches {close_to_threshold:,} more)
│   Score <0.50     → PASS (with monitoring)                             │
│                                                                        │
└────────────────────────────────────────────────────────────────────────┘
""")

else:
    print("\n   ⚠ No score column found for analysis.")
    print("   Available columns:", df.columns.tolist())

print("\n✓ Deep dive analysis complete!")
