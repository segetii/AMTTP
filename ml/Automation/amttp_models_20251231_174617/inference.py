
"""
AMTTP Fraud Detection Inference Script
Generated: 20251231_174617

Includes full preprocessing pipeline for production inference.
"""
import torch
import numpy as np
import xgboost as xgb
import lightgbm as lgb
import joblib
import json


def load_models(model_dir):
    """Load all models and preprocessors for inference."""
    # Load configs
    with open(f'{model_dir}/metadata.json') as f:
        metadata = json.load(f)
    with open(f'{model_dir}/feature_config.json') as f:
        feature_config = json.load(f)

    # Preprocessors (CRITICAL for production)
    preprocessors = joblib.load(f'{model_dir}/preprocessors.joblib')

    # XGBoost
    xgb_model = xgb.XGBClassifier()
    xgb_model.load_model(f'{model_dir}/xgboost_fraud.ubj')

    # LightGBM
    lgb_model = lgb.Booster(model_file=f'{model_dir}/lightgbm_fraud.txt')

    # Meta-ensemble
    meta_model = joblib.load(f'{model_dir}/meta_ensemble.joblib')

    return {
        'xgb': xgb_model,
        'lgb': lgb_model,
        'meta': meta_model,
        'preprocessors': preprocessors,
        'metadata': metadata,
        'feature_config': feature_config
    }


def preprocess_features(features, preprocessors):
    """
    Apply the same preprocessing used during training.

    Args:
        features: numpy array of shape (n_samples, n_features) - RAW features
        preprocessors: dict containing scalers and transforms

    Returns:
        Preprocessed features ready for model inference
    """
    X = features.copy().astype(np.float32)

    # 1. Handle missing values
    X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)

    # 2. Apply log transform to skewed features
    log_mask = preprocessors['log_transform_mask']
    X[:, log_mask] = np.log1p(np.clip(X[:, log_mask], 0, None))

    # 3. Apply RobustScaler (outlier-resistant)
    X = preprocessors['robust_scaler'].transform(X)

    # 4. Clip extreme outliers (consistent with training)
    clip_range = preprocessors.get('clip_range', 5)
    X = np.clip(X, -clip_range, clip_range)

    return X


def predict_fraud(raw_features, models, threshold=None):
    """
    Full inference pipeline with preprocessing.

    Args:
        raw_features: numpy array of shape (n_samples, n_features) - RAW unprocessed features
        models: dict returned by load_models()
        threshold: classification threshold (default: use optimal from training)

    Returns:
        dict with fraud_prob, risk_levels, is_fraud, xgb_prob, lgb_prob
    """
    if threshold is None:
        threshold = models['metadata']['optimal_threshold']

    # Preprocess
    features = preprocess_features(raw_features, models['preprocessors'])

    # Predict with individual models
    xgb_prob = models['xgb'].predict_proba(features)[:, 1]
    lgb_prob = models['lgb'].predict(features)

    # Placeholders for graph/unsupervised features not computed in this simplified script
    n_samples = len(features)
    zeros = np.zeros(n_samples)
    
    # Meta-ensemble (full version includes VAE, GATv2, and GraphSAGE)
    # Meta-model expects: [recon, edge, gat, unc, sage, xgb, lgb]
    meta_features = np.column_stack([
        zeros, # recon
        zeros, # edge
        zeros, # gat
        zeros, # unc
        zeros, # sage
        xgb_prob,
        lgb_prob
    ])
    
    # WARNING: This meta-prediction is an approximation as it lacks the graph embeddings.
    fraud_prob = models['meta'].predict_proba(meta_features)[:, 1]

    # Risk levels
    risk_levels = np.where(fraud_prob >= 0.85, 'CRITICAL',
                  np.where(fraud_prob >= 0.65, 'HIGH',
                  np.where(fraud_prob >= 0.45, 'MEDIUM',
                  np.where(fraud_prob >= 0.25, 'LOW', 'MINIMAL'))))

    return {
        'fraud_prob': fraud_prob,
        'risk_levels': risk_levels,
        'is_fraud': fraud_prob >= threshold,
        'threshold': threshold,
        'xgb_prob': xgb_prob,
        'lgb_prob': lgb_prob
    }


if __name__ == '__main__':
    MODEL_DIR = '/content/amttp_models_20251231_174617'
    models = load_models(MODEL_DIR)

    print(f"✅ Models loaded successfully!")
    print(f"   Performance: ROC-AUC={models['metadata']['performance']['meta_roc_auc']:.4f}")
    print(f"   Optimal threshold: {models['metadata']['optimal_threshold']:.4f}")
    print(f"   Features expected: {len(models['feature_config']['tabular_features'])})")

    # Example usage:
    # raw_data = np.random.randn(10, len(models['feature_config']['tabular_features']))
    # results = predict_fraud(raw_data, models)
    # print(f"Fraud probabilities: {results['fraud_prob']}")
    # print(f"Risk levels: {results['risk_levels']}")
