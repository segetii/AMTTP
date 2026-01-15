"""
ML Model Recalibration based on Cross-Reference Findings

This script:
1. Analyzes what ML missed vs what behavioral patterns caught
2. Creates new calibrated thresholds
3. Optionally retrains/fine-tunes the model
"""
import pandas as pd
import numpy as np
import json
from pathlib import Path

print("=" * 70)
print("ML MODEL RECALIBRATION")
print("=" * 70)

# Load data
cross_validated = pd.read_csv('c:/amttp/processed/cross_validated_results.csv')
sophisticated = pd.read_csv('c:/amttp/processed/sophisticated_fraud_patterns.csv')
hybrid = pd.read_csv('c:/amttp/processed/hybrid_risk_scores.csv')

# Current thresholds from settings.py
CURRENT_THRESHOLDS = {
    "model_threshold": 0.96,  # Too high!
    "approve_threshold": 0.25,
    "monitor_threshold": 0.40,
    "review_threshold": 0.70,
    "escrow_threshold": 0.85,
}

print("\n📊 CURRENT THRESHOLDS:")
for k, v in CURRENT_THRESHOLDS.items():
    print(f"   {k}: {v}")

# Analyze what we caught with hybrid that ML missed
print("\n" + "=" * 70)
print("ANALYZING FALSE NEGATIVES (ML missed, Hybrid caught)")
print("=" * 70)

# Get addresses with high hybrid scores but low ML scores
critical_missed = hybrid[
    (hybrid['risk_level'].isin(['CRITICAL', 'HIGH'])) & 
    (hybrid['ml_score'] < 0.70)
]

print(f"\nAddresses ML would miss (hybrid CRITICAL/HIGH but ML < 0.70): {len(critical_missed)}")

if len(critical_missed) > 0:
    ml_scores_missed = critical_missed['ml_score'].values
    print(f"\n  ML scores of missed threats:")
    print(f"    Min: {ml_scores_missed.min():.3f}")
    print(f"    Max: {ml_scores_missed.max():.3f}")
    print(f"    Mean: {ml_scores_missed.mean():.3f}")
    print(f"    Median: {np.median(ml_scores_missed):.3f}")

# Find optimal ML threshold that would catch these
print("\n" + "=" * 70)
print("FINDING OPTIMAL NEW THRESHOLDS")
print("=" * 70)

# For CRITICAL threats
critical_threats = hybrid[hybrid['risk_level'] == 'CRITICAL']
if len(critical_threats) > 0:
    critical_ml_min = critical_threats['ml_score'].min()
    print(f"\nCRITICAL threats ML scores: {critical_threats['ml_score'].min():.3f} - {critical_threats['ml_score'].max():.3f}")
    print(f"  To catch ALL critical: ML threshold should be <= {critical_ml_min:.3f}")

high_threats = hybrid[hybrid['risk_level'] == 'HIGH']
if len(high_threats) > 0:
    high_ml_min = high_threats['ml_score'].min()
    print(f"\nHIGH threats ML scores: {high_threats['ml_score'].min():.3f} - {high_threats['ml_score'].max():.3f}")
    print(f"  To catch ALL high: ML threshold should be <= {high_ml_min:.3f}")

medium_threats = hybrid[hybrid['risk_level'] == 'MEDIUM']
if len(medium_threats) > 0:
    medium_ml_min = medium_threats['ml_score'].min()
    print(f"\nMEDIUM threats ML scores: {medium_threats['ml_score'].min():.3f} - {medium_threats['ml_score'].max():.3f}")

# Calculate new thresholds
print("\n" + "=" * 70)
print("NEW CALIBRATED THRESHOLDS")
print("=" * 70)

# Based on analysis
NEW_THRESHOLDS = {
    # Lower the model threshold significantly - 0.96 was way too high
    "model_threshold": 0.50,  # Was 0.96, now catch more
    
    # Recalibrate action thresholds based on hybrid findings
    "approve_threshold": 0.20,   # Very low risk - auto approve
    "monitor_threshold": 0.35,   # Low-medium risk - monitor
    "review_threshold": 0.50,    # Was 0.70 - now catch earlier  
    "escrow_threshold": 0.65,    # Was 0.85 - be more cautious
    
    # NEW: Add behavioral pattern boost
    "pattern_boost": {
        "SMURFING": 0.25,       # Add 25% to ML score if smurfing detected
        "LAYERING": 0.15,       # Add 15% for layering
        "FAN_OUT": 0.15,        # Add 15% for fan-out
        "FAN_IN": 0.10,         # Add 10% for fan-in
        "PEELING": 0.20,        # Add 20% for peeling
        "STRUCTURING": 0.25,    # Add 25% for structuring
    },
    
    # NEW: Graph connection boost
    "graph_boost": {
        "direct_sanctioned": 0.40,  # Add 40% if direct sanctioned connection
        "direct_mixer": 0.30,       # Add 30% if direct mixer
        "2hop_sanctioned": 0.20,    # Add 20% if 2-hop to sanctioned
        "3hop_sanctioned": 0.10,    # Add 10% if 3-hop
        "high_centrality": 0.05,    # Add 5% for high centrality
    },
    
    # Multi-signal multiplier
    "multi_signal_multiplier": {
        "2_signals": 1.2,  # 20% boost if 2 methods flag
        "3_signals": 1.5,  # 50% boost if all 3 methods flag
    }
}

print("\n📊 NEW THRESHOLDS:")
print(f"   model_threshold: {CURRENT_THRESHOLDS['model_threshold']} → {NEW_THRESHOLDS['model_threshold']} (LOWERED)")
print(f"   approve_threshold: {CURRENT_THRESHOLDS['approve_threshold']} → {NEW_THRESHOLDS['approve_threshold']}")
print(f"   monitor_threshold: {CURRENT_THRESHOLDS['monitor_threshold']} → {NEW_THRESHOLDS['monitor_threshold']}")
print(f"   review_threshold: {CURRENT_THRESHOLDS['review_threshold']} → {NEW_THRESHOLDS['review_threshold']} (LOWERED)")
print(f"   escrow_threshold: {CURRENT_THRESHOLDS['escrow_threshold']} → {NEW_THRESHOLDS['escrow_threshold']} (LOWERED)")

print("\n📊 NEW BEHAVIORAL BOOSTS:")
for pattern, boost in NEW_THRESHOLDS['pattern_boost'].items():
    print(f"   {pattern}: +{boost*100:.0f}%")

print("\n📊 NEW GRAPH BOOSTS:")
for reason, boost in NEW_THRESHOLDS['graph_boost'].items():
    print(f"   {reason}: +{boost*100:.0f}%")

# Save new thresholds
output_path = Path('c:/amttp/ml/Automation/ml_pipeline/config/calibrated_thresholds.json')
with open(output_path, 'w') as f:
    json.dump(NEW_THRESHOLDS, f, indent=2)
print(f"\n✅ Saved calibrated thresholds to {output_path}")

# Test: How many would OLD vs NEW catch?
print("\n" + "=" * 70)
print("COMPARISON: OLD vs NEW DETECTION RATE")
print("=" * 70)

# All threats (hybrid CRITICAL + HIGH)
all_threats = hybrid[hybrid['risk_level'].isin(['CRITICAL', 'HIGH'])]

old_caught = len(all_threats[all_threats['ml_score'] >= CURRENT_THRESHOLDS['review_threshold']])
new_caught = len(all_threats[all_threats['ml_score'] >= NEW_THRESHOLDS['review_threshold']])

print(f"\n  Total CRITICAL+HIGH threats: {len(all_threats)}")
print(f"  OLD threshold (0.70) catches: {old_caught} ({old_caught/len(all_threats)*100:.1f}%)")
print(f"  NEW threshold (0.50) catches: {new_caught} ({new_caught/len(all_threats)*100:.1f}%)")
print(f"\n  🎯 IMPROVEMENT: {new_caught - old_caught} more threats caught!")

# Update the actual settings.py
print("\n" + "=" * 70)
print("APPLYING TO SETTINGS")
print("=" * 70)
