#!/usr/bin/env python3
"""
XGBoost with Node2Vec Embeddings
Combine graph embeddings with transaction features for enhanced fraud detection
"""

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.metrics import roc_auc_score, average_precision_score, classification_report
from sklearn.preprocessing import StandardScaler
import xgboost as xgb
import joblib

def main():
    print("=" * 70)
    print("XGBOOST WITH NODE2VEC EMBEDDINGS - FRAUD DETECTION")
    print("=" * 70)
    
    # Load Node2Vec embeddings
    print("\n[1/5] Loading Node2Vec embeddings...")
    emb_data = np.load('c:/amttp/processed/node2vec_embeddings.npz', allow_pickle=True)
    emb_nodes = emb_data['nodes']
    emb_vectors = emb_data['vectors']
    print(f"   Loaded {len(emb_nodes)} embeddings (dim={emb_vectors.shape[1]})")
    
    # Create embedding DataFrame
    emb_cols = [f'n2v_{i}' for i in range(emb_vectors.shape[1])]
    emb_df = pd.DataFrame(emb_vectors, columns=emb_cols)
    emb_df['address'] = emb_nodes
    emb_df['address'] = emb_df['address'].str.lower()
    
    # Load address features
    print("\n[2/5] Loading address features...")
    addr_df = pd.read_parquet('c:/amttp/processed/eth_addresses_labeled.parquet')
    addr_df['address'] = addr_df['address'].str.lower()
    print(f"   Loaded {len(addr_df)} addresses")
    print(f"   Fraud addresses: {addr_df['fraud'].sum()}")
    
    # Merge embeddings with features
    print("\n[3/5] Merging embeddings with features...")
    merged_df = addr_df.merge(emb_df, on='address', how='inner')
    print(f"   Merged dataset: {len(merged_df)} addresses")
    print(f"   Fraud in merged: {merged_df['fraud'].sum()}")
    
    # Define feature columns
    # Original features (excluding identifiers and targets)
    exclude_cols = ['address', 'fraud', 'risk_level', 'risk_class', 'patterns', 
                    'xgb_raw_score', 'xgb_normalized', 'pattern_boost', 
                    'soph_normalized', 'hybrid_score']
    
    original_features = [c for c in addr_df.columns if c not in exclude_cols]
    embedding_features = emb_cols
    all_features = original_features + embedding_features
    
    print(f"\n   Original features: {len(original_features)}")
    print(f"   Embedding features: {len(embedding_features)}")
    print(f"   Total features: {len(all_features)}")
    
    # Prepare data
    X = merged_df[all_features].fillna(0)
    y = merged_df['fraud']
    
    # Train/test split with stratification
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )
    
    print(f"\n   Train set: {len(X_train)} ({y_train.sum()} fraud)")
    print(f"   Test set: {len(X_test)} ({y_test.sum()} fraud)")
    
    # Scale features
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)
    
    # Train XGBoost with embeddings
    print("\n[4/5] Training XGBoost with embeddings...")
    
    # Calculate scale_pos_weight for imbalanced data
    scale_pos_weight = (y_train == 0).sum() / max((y_train == 1).sum(), 1)
    
    model_with_emb = xgb.XGBClassifier(
        n_estimators=200,
        max_depth=6,
        learning_rate=0.1,
        scale_pos_weight=scale_pos_weight,
        eval_metric='aucpr',
        random_state=42,
        n_jobs=-1
    )
    
    model_with_emb.fit(X_train_scaled, y_train)
    
    # Predictions
    y_pred_proba = model_with_emb.predict_proba(X_test_scaled)[:, 1]
    y_pred = model_with_emb.predict(X_test_scaled)
    
    # Evaluate
    roc_auc = roc_auc_score(y_test, y_pred_proba)
    pr_auc = average_precision_score(y_test, y_pred_proba)
    
    print(f"\n   ROC-AUC: {roc_auc:.4f}")
    print(f"   PR-AUC: {pr_auc:.4f}")
    
    # Train baseline without embeddings for comparison
    print("\n[4b/5] Training baseline XGBoost (without embeddings)...")
    
    X_train_base = X_train[original_features]
    X_test_base = X_test[original_features]
    
    scaler_base = StandardScaler()
    X_train_base_scaled = scaler_base.fit_transform(X_train_base)
    X_test_base_scaled = scaler_base.transform(X_test_base)
    
    model_baseline = xgb.XGBClassifier(
        n_estimators=200,
        max_depth=6,
        learning_rate=0.1,
        scale_pos_weight=scale_pos_weight,
        eval_metric='aucpr',
        random_state=42,
        n_jobs=-1
    )
    
    model_baseline.fit(X_train_base_scaled, y_train)
    y_pred_base = model_baseline.predict_proba(X_test_base_scaled)[:, 1]
    
    roc_auc_base = roc_auc_score(y_test, y_pred_base)
    pr_auc_base = average_precision_score(y_test, y_pred_base)
    
    print(f"   Baseline ROC-AUC: {roc_auc_base:.4f}")
    print(f"   Baseline PR-AUC: {pr_auc_base:.4f}")
    
    # Comparison
    print("\n" + "=" * 70)
    print("COMPARISON: WITH vs WITHOUT NODE2VEC EMBEDDINGS")
    print("=" * 70)
    
    print(f"\n{'Metric':<20} {'Baseline':>15} {'+ Embeddings':>15} {'Change':>15}")
    print("-" * 65)
    print(f"{'ROC-AUC':<20} {roc_auc_base:>15.4f} {roc_auc:>15.4f} {roc_auc - roc_auc_base:>+15.4f}")
    print(f"{'PR-AUC':<20} {pr_auc_base:>15.4f} {pr_auc:>15.4f} {pr_auc - pr_auc_base:>+15.4f}")
    
    # Feature importance for embeddings
    print("\n" + "=" * 70)
    print("TOP FEATURES (Including Embeddings)")
    print("=" * 70)
    
    importances = model_with_emb.feature_importances_
    feat_imp = pd.DataFrame({
        'feature': all_features,
        'importance': importances
    }).sort_values('importance', ascending=False)
    
    print(f"\nTop 15 features:")
    for i, row in feat_imp.head(15).iterrows():
        is_emb = "📊" if row['feature'].startswith('n2v_') else "📈"
        print(f"   {is_emb} {row['feature']:<25} {row['importance']:.4f}")
    
    # Count embedding features in top 20
    top20 = feat_imp.head(20)
    n2v_in_top20 = top20['feature'].str.startswith('n2v_').sum()
    print(f"\n   Node2Vec features in top 20: {n2v_in_top20}")
    
    # Threshold analysis
    print("\n" + "=" * 70)
    print("FRAUD CAPTURE AT DIFFERENT THRESHOLDS")
    print("=" * 70)
    
    for threshold in [0.3, 0.5, 0.7]:
        pred_base = (y_pred_base >= threshold).astype(int)
        pred_emb = (y_pred_proba >= threshold).astype(int)
        
        recall_base = pred_base[y_test == 1].sum() / y_test.sum()
        recall_emb = pred_emb[y_test == 1].sum() / y_test.sum()
        
        prec_base = pred_base[y_test == 1].sum() / max(pred_base.sum(), 1)
        prec_emb = pred_emb[y_test == 1].sum() / max(pred_emb.sum(), 1)
        
        print(f"\nThreshold {threshold}:")
        print(f"   Baseline  - Recall: {recall_base:.1%}, Precision: {prec_base:.1%}")
        print(f"   +Embeddings - Recall: {recall_emb:.1%}, Precision: {prec_emb:.1%}")
    
    # Save models
    print("\n[5/5] Saving models...")
    joblib.dump(model_with_emb, 'c:/amttp/processed/xgb_with_node2vec.pkl')
    joblib.dump(model_baseline, 'c:/amttp/processed/xgb_baseline_comparison.pkl')
    joblib.dump(scaler, 'c:/amttp/processed/scaler_with_embeddings.pkl')
    
    # Save feature list
    with open('c:/amttp/processed/feature_list_with_embeddings.txt', 'w') as f:
        f.write('\n'.join(all_features))
    
    print("   Saved: xgb_with_node2vec.pkl")
    print("   Saved: xgb_baseline_comparison.pkl")
    print("   Saved: feature_list_with_embeddings.txt")
    
    print("\n" + "=" * 70)
    print("✅ COMPLETE")
    print("=" * 70)

if __name__ == '__main__':
    main()
