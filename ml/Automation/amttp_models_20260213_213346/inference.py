"""
AMTTP V2 Fraud Detection Inference Script
Generated: 20260213_213346
Pipeline: β-VAE → GATv2 → GraphSAGE → PCA → Optuna-LGBM/XGB → Meta-LR
"""
import torch, numpy as np, xgboost as xgb, lightgbm as lgb, joblib, json

def load_models(model_dir):
    preprocessors = joblib.load(f'{model_dir}/preprocessors.joblib')
    pca = joblib.load(f'{model_dir}/pca_embeddings.joblib')
    xgb_model = xgb.XGBClassifier(); xgb_model.load_model(f'{model_dir}/xgboost_fraud.ubj')
    lgb_model = lgb.Booster(model_file=f'{model_dir}/lightgbm_fraud.txt')
    meta_model = joblib.load(f'{model_dir}/meta_ensemble.joblib')
    with open(f'{model_dir}/metadata.json') as f: metadata = json.load(f)
    return {'xgb': xgb_model, 'lgb': lgb_model, 'meta': meta_model,
             'preprocessors': preprocessors, 'pca': pca, 'metadata': metadata}

def preprocess(features, preprocessors):
    X = features.copy().astype(np.float32)
    X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)
    log_mask = preprocessors['log_transform_mask']
    X[:, log_mask] = np.log1p(np.clip(X[:, log_mask], 0, None))
    X = preprocessors['robust_scaler'].transform(X)
    return np.clip(X, -5, 5)

def predict_fraud(raw_features, models, threshold=None):
    if threshold is None: threshold = models['metadata']['optimal_threshold']
    X = preprocess(raw_features, models['preprocessors'])
    xgb_prob = models['xgb'].predict_proba(X)[:, 1]
    lgb_prob = models['lgb'].predict(X)
    # For full pipeline: run VAE + GNN + PCA + meta
    # For XGB-only fallback:
    return {'xgb_prob': xgb_prob, 'lgb_prob': lgb_prob,
             'is_fraud': xgb_prob >= threshold, 'threshold': threshold}
