#!/usr/bin/env python3
"""
AMTTP V2 Model — Cross-Validation Against External Datasets
============================================================
Validates the V2 production model (β-VAE → GATv2 → GraphSAGE → PCA → Optuna-LGBM/XGB → Meta-LR)
against independently-labeled fraud datasets.

Also evaluates Meta-Learner 3 (LR + Q-Learning Dueling DQN) against the baseline
LogisticRegressionCV meta-ensemble (Meta-Learner 1).

Model: amttp_student_artifacts/amttp_models_20260213_213346
Architecture: 93 raw features → 160 boost features (incl. 64 VAE latents + anomaly scores)

External datasets:
  1. Elliptic Bitcoin (46K labeled tx, law enforcement ground truth)
  2. XBlock Ethereum Phishing (9.8K addresses, confirmed phishing)
  3. Forta Network (live security bot detections)
  4. OFAC SDN (U.S. Treasury sanctioned addresses)
  5. Chainabuse (community-reported scams)
"""

# %% [markdown]
# # Cross-Validation: AMTTP V2 Model vs External Datasets
#
# **Model**: V2 Pipeline (β-VAE → GATv2 → GraphSAGE → PCA → Optuna-LGBM/XGB → Meta-LR)
# **Features**: 93 raw (sender/receiver/tx/graph/mixer/sanctioned) → 160 boost (+ 64 VAE latents + anomaly scores)
# **Training**: 625K samples, 25% fraud rate, Optuna 50-trial HPO

# %% Cell 1: Setup & Load Models
import subprocess, sys, os
import numpy as np
import pandas as pd
import json
import time
import warnings
import requests
from pathlib import Path
from datetime import datetime

warnings.filterwarnings('ignore')

IN_COLAB = 'google.colab' in sys.modules

# ── Model & Data Paths ──
MODELS_DIR = Path(r'C:\Users\Administrator\Downloads\amttp_student_artifacts\amttp_models_20260213_213346')
DATA_DIR = Path(r'c:\amttp\data\external_validation')
DATA_DIR.mkdir(parents=True, exist_ok=True)

print(f'Models dir: {MODELS_DIR}')
print(f'Data dir:   {DATA_DIR}')

# ── Load V2 Models ──
import xgboost as xgb
import lightgbm as lgb
import joblib
from sklearn.metrics import (
    roc_auc_score, average_precision_score, f1_score,
    precision_score, recall_score, classification_report,
    confusion_matrix, precision_recall_curve
)

# XGBoost
xgb_model = xgb.XGBClassifier()
xgb_model.load_model(str(MODELS_DIR / 'xgboost_fraud.ubj'))
print(f'✅ XGBoost loaded')

# LightGBM
lgb_model = lgb.Booster(model_file=str(MODELS_DIR / 'lightgbm_fraud.txt'))
print(f'✅ LightGBM loaded ({lgb_model.num_trees()} trees)')

# Meta-Ensemble (LogisticRegressionCV)
meta_model = joblib.load(str(MODELS_DIR / 'meta_ensemble.joblib'))
print(f'✅ Meta-Ensemble loaded')
if hasattr(meta_model, 'coef_'):
    print(f'   Coef: {meta_model.coef_[0].tolist()}')

# Preprocessors (RobustScaler + log transform mask)
preprocessors = joblib.load(str(MODELS_DIR / 'preprocessors.joblib'))
print(f'✅ Preprocessors loaded (keys: {list(preprocessors.keys()) if isinstance(preprocessors, dict) else type(preprocessors).__name__})')

# Metadata & feature config
with open(MODELS_DIR / 'metadata.json') as f:
    metadata = json.load(f)
with open(MODELS_DIR / 'feature_config.json') as f:
    feature_config = json.load(f)

RAW_FEATURES = feature_config['raw_features']       # 93 features
BOOST_FEATURES = feature_config['boost_features']    # 160 features
META_FEATURES = feature_config['meta_features']      # 8 meta features
OPTIMAL_THRESHOLD = metadata['optimal_threshold']     # 0.6428
THRESHOLDS = metadata['thresholds']

print(f'\n📋 Feature Schema:')
print(f'   Raw features:   {len(RAW_FEATURES)}')
print(f'   Boost features: {len(BOOST_FEATURES)} (raw + {len(BOOST_FEATURES)-len(RAW_FEATURES)} VAE/anomaly)')
print(f'   Meta features:  {len(META_FEATURES)}')
print(f'   Optimal threshold: {OPTIMAL_THRESHOLD:.4f}')
print(f'   Thresholds: {THRESHOLDS}')

# ── Load ML3: LR + Q-Learning Neural Network Meta-Learner ──
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch_geometric.nn import GATv2Conv, SAGEConv
from sklearn.neighbors import NearestNeighbors

# ── Model Definitions (matching training notebook) ──

class BetaVAE(nn.Module):
    """β-VAE for unsupervised anomaly scoring. in_dim=93, latent_dim=64."""
    def __init__(self, in_dim, latent_dim=64, hidden=256, beta=4.0):
        super().__init__()
        self.beta = beta
        self.latent_dim = latent_dim
        self.enc = nn.Sequential(
            nn.Linear(in_dim, hidden), nn.LayerNorm(hidden), nn.GELU(), nn.Dropout(0.1),
            nn.Linear(hidden, hidden // 2), nn.LayerNorm(hidden // 2), nn.GELU()
        )
        self.mu = nn.Linear(hidden // 2, latent_dim)
        self.logvar = nn.Linear(hidden // 2, latent_dim)
        self.dec = nn.Sequential(
            nn.Linear(latent_dim, hidden // 2), nn.LayerNorm(hidden // 2), nn.GELU(), nn.Dropout(0.1),
            nn.Linear(hidden // 2, hidden), nn.LayerNorm(hidden), nn.GELU(),
            nn.Linear(hidden, in_dim)
        )
    def encode(self, x):
        h = self.enc(x)
        return self.mu(h), self.logvar(h)
    def reparameterize(self, mu, logvar):
        std = torch.exp(0.5 * logvar)
        return mu + torch.randn_like(std) * std
    def forward(self, x):
        mu, logvar = self.encode(x)
        z = self.reparameterize(mu, logvar)
        recon = self.dec(z)
        return recon, mu, logvar, z


class GATModel(nn.Module):
    """GATv2 graph classifier. in_dim=160 (boost features)."""
    def __init__(self, in_dim, hidden=64, heads=4, dropout=0.3):
        super().__init__()
        self.conv1 = GATv2Conv(in_dim, hidden, heads=heads, dropout=dropout, concat=True)
        self.bn1 = nn.BatchNorm1d(hidden * heads)
        self.conv2 = GATv2Conv(hidden * heads, hidden, heads=1, concat=False, dropout=dropout)
        self.bn2 = nn.BatchNorm1d(hidden)
        self.skip = nn.Linear(in_dim, hidden)
        self.lin = nn.Linear(hidden, 1)
        self.dropout = dropout

    def encode(self, x, edge_index):
        x_skip = self.skip(x)
        x = self.conv1(x, edge_index)
        x = self.bn1(x).relu()
        x = F.dropout(x, p=self.dropout, training=self.training)
        x = self.conv2(x, edge_index)
        x = self.bn2(x).relu()
        return x + x_skip

    def forward(self, x, edge_index):
        return self.lin(self.encode(x, edge_index)).squeeze(-1)


class GraphSAGEModel(nn.Module):
    """GraphSAGE classifier. in_dim=160 (boost features)."""
    def __init__(self, in_dim, hidden=128, num_layers=3, dropout=0.3):
        super().__init__()
        self.convs = nn.ModuleList()
        self.bns = nn.ModuleList()
        self.convs.append(SAGEConv(in_dim, hidden))
        self.bns.append(nn.BatchNorm1d(hidden))
        for _ in range(num_layers - 2):
            self.convs.append(SAGEConv(hidden, hidden))
            self.bns.append(nn.BatchNorm1d(hidden))
        self.convs.append(SAGEConv(hidden, hidden))
        self.bns.append(nn.BatchNorm1d(hidden))
        self.lin = nn.Linear(hidden, 1)
        self.dropout = dropout

    def encode(self, x, edge_index):
        for i, conv in enumerate(self.convs):
            x = conv(x, edge_index)
            x = self.bns[i](x).relu()
            x = F.dropout(x, p=self.dropout, training=self.training)
        return x

    def forward(self, x, edge_index):
        return self.lin(self.encode(x, edge_index)).squeeze(-1)

class LR_QLearning_MetaLearner(nn.Module):
    """
    Meta-Learner 3: Dueling-DQN architecture with 3 fused pathways.
    
    Path A (LR):     Linear(n_meta_features → 1) → sigmoid
    Path B (Q-Net):  Dueling DQN (value + advantage) → softmax-weighted base probs
    Path C (Fusion): Concatenation of all signals → MLP → sigmoid
    
    Final output: gate[0]*lr_out + gate[1]*q_out + gate[2]*fusion_out
    where gate is a learned 3-element softmax parameter.
    """
    def __init__(self, n_meta_features, n_base_models=8, hidden_dim=64,
                 q_hidden=32, dropout=0.3):
        super().__init__()
        self.n_base_models = n_base_models
        self.lr_head = nn.Linear(n_meta_features, 1)
        self.value_stream = nn.Sequential(
            nn.Linear(n_base_models, q_hidden), nn.LayerNorm(q_hidden), nn.GELU(),
            nn.Linear(q_hidden, 1))
        self.advantage_stream = nn.Sequential(
            nn.Linear(n_base_models, q_hidden), nn.LayerNorm(q_hidden), nn.GELU(),
            nn.Dropout(dropout * 0.5),
            nn.Linear(q_hidden, q_hidden), nn.GELU(),
            nn.Linear(q_hidden, n_base_models))
        fusion_input_dim = n_meta_features + n_base_models + 2
        self.fusion = nn.Sequential(
            nn.Linear(fusion_input_dim, hidden_dim), nn.LayerNorm(hidden_dim), nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_dim, hidden_dim // 2), nn.LayerNorm(hidden_dim // 2), nn.GELU(),
            nn.Dropout(dropout * 0.5),
            nn.Linear(hidden_dim // 2, 1))
        self.gate = nn.Parameter(torch.tensor([0.33, 0.33, 0.34]))
        self.temperature = nn.Parameter(torch.tensor(1.0))

    def forward(self, x, base_probs):
        lr_out = torch.sigmoid(self.lr_head(x))
        v = self.value_stream(base_probs)
        a = self.advantage_stream(base_probs)
        q_values = v + a - a.mean(dim=1, keepdim=True)
        q_weights = torch.softmax(q_values / self.temperature.clamp(min=0.1), dim=1)
        q_out = (q_weights * base_probs).sum(dim=1, keepdim=True)
        fusion_input = torch.cat([x, q_weights, lr_out, q_out], dim=1)
        fusion_out = torch.sigmoid(self.fusion(fusion_input))
        gate = torch.softmax(self.gate, dim=0)
        final = gate[0] * lr_out + gate[1] * q_out + gate[2] * fusion_out
        return final.squeeze(1), {
            'lr_out': lr_out.squeeze(1), 'q_out': q_out.squeeze(1),
            'fusion_out': fusion_out.squeeze(1), 'q_weights': q_weights,
            'gate': gate, 'q_values': q_values}

# Load the trained ML3 model
ML3_PATH = MODELS_DIR / 'meta3_lr_qlearning_nn.pt'
ml3_model = None
if ML3_PATH.exists():
    checkpoint = torch.load(str(ML3_PATH), map_location='cpu', weights_only=False)
    ml3_config = checkpoint['config']
    ml3_model = LR_QLearning_MetaLearner(
        n_meta_features=ml3_config['n_meta_features'],
        n_base_models=ml3_config['n_base_models'],
        hidden_dim=ml3_config['hidden_dim'],
        q_hidden=ml3_config['q_hidden'],
        dropout=ml3_config['dropout'],
    )
    ml3_model.load_state_dict(checkpoint['model_state_dict'])
    ml3_model.eval()
    gate = torch.softmax(ml3_model.gate.data, dim=0)
    n_params = sum(p.numel() for p in ml3_model.parameters())
    print(f'✅ ML3 (LR+Q-Learning NN) loaded ({n_params:,} params)')
    print(f'   Config: {ml3_config}')
    print(f'   Gate weights: LR={gate[0]:.3f}  Q-Net={gate[1]:.3f}  Fusion={gate[2]:.3f}')
else:
    print(f'⚠️  ML3 not found at {ML3_PATH}')

# ── Load β-VAE (anomaly scoring: recon_err, kl_div, mahalanobis) ──
vae_model = None
VAE_PATH = MODELS_DIR / 'beta_vae.pt'
if VAE_PATH.exists():
    vae_ckpt = torch.load(str(VAE_PATH), map_location='cpu', weights_only=False)
    vae_cfg = vae_ckpt['config']
    vae_model = BetaVAE(
        in_dim=vae_cfg['in_dim'], latent_dim=vae_cfg['latent_dim'],
        hidden=vae_cfg['hidden'], beta=vae_cfg['beta']
    )
    # Handle torch.compile prefix in state dict keys
    sd = vae_ckpt['model_state_dict']
    sd_clean = {k.replace('_orig_mod.', ''): v for k, v in sd.items()}
    vae_model.load_state_dict(sd_clean)
    vae_model.eval()
    n_vae = sum(p.numel() for p in vae_model.parameters())
    print(f'✅ β-VAE loaded ({n_vae:,} params, latent={vae_cfg["latent_dim"]}, β={vae_cfg["beta"]})')
else:
    print(f'⚠️  β-VAE not found at {VAE_PATH}')

# ── Load GATv2 (graph attention network) ──
gat_model = None
GAT_PATH = MODELS_DIR / 'gatv2.pt'
if GAT_PATH.exists():
    gat_ckpt = torch.load(str(GAT_PATH), map_location='cpu', weights_only=False)
    gat_cfg = gat_ckpt['config']
    gat_model = GATModel(
        in_dim=gat_cfg['in_dim'], hidden=gat_cfg['hidden'],
        heads=gat_cfg['heads'], dropout=gat_cfg['dropout']
    )
    gat_model.load_state_dict(gat_ckpt['model_state_dict'])
    gat_model.eval()
    n_gat = sum(p.numel() for p in gat_model.parameters())
    print(f'✅ GATv2 loaded ({n_gat:,} params, hidden={gat_cfg["hidden"]}, heads={gat_cfg["heads"]})')
else:
    print(f'⚠️  GATv2 not found at {GAT_PATH}')

# ── Load GraphSAGE ──
sage_model = None
SAGE_PATH = MODELS_DIR / 'graphsage.pt'
if SAGE_PATH.exists():
    sage_ckpt = torch.load(str(SAGE_PATH), map_location='cpu', weights_only=False)
    sage_cfg = sage_ckpt['config']
    sage_model = GraphSAGEModel(
        in_dim=sage_cfg['in_dim'], hidden=sage_cfg['hidden'],
        num_layers=sage_cfg['num_layers'], dropout=sage_cfg['dropout']
    )
    sage_model.load_state_dict(sage_ckpt['model_state_dict'])
    sage_model.eval()
    n_sage = sum(p.numel() for p in sage_model.parameters())
    print(f'✅ GraphSAGE loaded ({n_sage:,} params, hidden={sage_cfg["hidden"]}, layers={sage_cfg["num_layers"]})')
else:
    print(f'⚠️  GraphSAGE not found at {SAGE_PATH}')

# ── Load TEACHER Model (Hope_machine XGB — trained on 99.7% BitcoinHeist + 0.3% ETH Kaggle) ──
TEACHER_MODEL_PATH = Path(r'c:\amttp\ml\Automation\ml_pipeline\models\trained\xgb.json')
teacher_xgb = xgb.Booster()
teacher_xgb.load_model(str(TEACHER_MODEL_PATH))
TEACHER_FEATURES = teacher_xgb.feature_names  # 171 features (56 core + 115 missingness)
TEACHER_CORE = [f for f in TEACHER_FEATURES if not f.endswith('_was_missing') and not f.endswith('_not_applicable')]
print(f'\n✅ Teacher XGB loaded (Hope_machine)')
print(f'   Features: {teacher_xgb.num_features()} ({len(TEACHER_CORE)} core + {len(TEACHER_FEATURES)-len(TEACHER_CORE)} missingness)')
print(f'   Training: 99.7% BitcoinHeist + 0.3% Ethereum Kaggle (~2.9M rows)')

# %% Cell 2: Prediction & Evaluation Utilities

def preprocess_raw(X_raw: np.ndarray) -> np.ndarray:
    """
    Apply the EXACT same preprocessing as training:
      1. Impute NaN/Inf → 0
      2. Log1p transform on 76 skewed features
      3. RobustScaler (fitted on training data)
      4. Clip to [-5, 5]
    Input: [n, 93] raw features in RAW_FEATURES order
    Output: [n, 93] preprocessed features
    """
    X = X_raw.copy().astype(np.float64)  # Use float64 for scaler compatibility
    X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)
    
    # Step 1: Impute (replace remaining NaN)
    imputer = preprocessors.get('imputer', None)
    if imputer is not None:
        X = imputer.transform(X)
    
    # Step 2: Log1p transform on skewed features
    log_mask = preprocessors.get('log_transform_mask', None)
    if log_mask is not None:
        log_mask = np.array(log_mask)
        X[:, log_mask] = np.log1p(np.clip(X[:, log_mask], 0, None))
    
    # Step 3: RobustScaler
    scaler = preprocessors.get('robust_scaler', None)
    if scaler is not None:
        X = scaler.transform(X)
    
    # Step 4: Clip
    clip_range = preprocessors.get('clip_range', 5)
    X = np.clip(X, -clip_range, clip_range)
    
    return X.astype(np.float32)


def build_knn_graph(X: np.ndarray, k: int = 10) -> torch.LongTensor:
    """
    Build a KNN graph from feature matrix.
    Returns edge_index [2, num_edges] for PyG.
    """
    n = X.shape[0]
    k_actual = min(k, n - 1)
    if k_actual < 1:
        # Single node: self-loop
        return torch.tensor([[0], [0]], dtype=torch.long)
    
    nn_model = NearestNeighbors(n_neighbors=k_actual + 1, algorithm='auto', metric='euclidean')
    nn_model.fit(X)
    distances, indices = nn_model.kneighbors(X)
    
    # Build edge list (skip self-loops from kNN, add directed edges)
    src, dst = [], []
    for i in range(n):
        for j in range(1, k_actual + 1):  # skip index 0 (self)
            src.append(i)
            dst.append(indices[i, j])
    
    edge_index = torch.tensor([src, dst], dtype=torch.long)
    return edge_index


def generate_full_features(X_raw_93: np.ndarray) -> dict:
    """
    Generate the COMPLETE V2 feature set from raw 93 features.
    
    Full pipeline (matching training):
      1. Preprocess: impute → log1p → RobustScale → clip (93 features)
      2. β-VAE: encode → decode → recon_err, kl_div, mahalanobis + 64 latent dims
      3. Assemble 160 boost features: 93 raw + 64 latent + 3 anomaly scores
      4. Build KNN graph from boost features (proxy for transaction graph)
      5. GATv2: forward → gat_prob, MC dropout → gat_uncertainty
      6. GraphSAGE: forward → sage_prob
      7. XGB + LGB on 160 boost features → xgb_prob, lgb_prob
      8. 8 meta features: [recon_err, kl_div, mahalanobis, gat_prob, gat_uncertainty, sage_prob, xgb_prob, lgb_prob]
    
    Returns dict with all intermediate results.
    """
    X = np.nan_to_num(X_raw_93.astype(np.float32), nan=0.0, posinf=0.0, neginf=0.0)
    n = X.shape[0]
    
    # Step 1: Preprocess raw features
    X_preprocessed = preprocess_raw(X)
    
    # Step 2: β-VAE forward pass
    recon_err_np = np.zeros(n, dtype=np.float32)
    kl_div_np = np.zeros(n, dtype=np.float32)
    mahal_np = np.zeros(n, dtype=np.float32)
    z_latent_np = np.zeros((n, 64), dtype=np.float32)
    
    if vae_model is not None:
        with torch.no_grad():
            X_t = torch.FloatTensor(X_preprocessed)
            recon, mu, logvar, z = vae_model(X_t)
            
            # Reconstruction error (per-sample MSE)
            recon_err = ((recon - X_t) ** 2).mean(dim=1)
            
            # KL divergence per sample
            kl_per_sample = -0.5 * (1 + logvar - mu.pow(2) - logvar.exp()).sum(dim=1)
            
            # Mahalanobis in latent space (using dataset's own distribution as reference)
            mu_mean = mu.mean(dim=0)
            mu_centered = mu - mu_mean
            cov = (mu_centered.t() @ mu_centered) / max(n - 1, 1)
            cov += torch.eye(mu.shape[1]) * 1e-4  # regularize
            try:
                cov_inv = torch.linalg.inv(cov)
                diff = mu - mu_mean
                mahal = torch.sqrt((diff @ cov_inv * diff).sum(dim=1).clamp(min=0))
            except Exception:
                mahal = torch.zeros(n)
            
            recon_err_np = recon_err.numpy()
            kl_div_np = kl_per_sample.numpy()
            mahal_np = mahal.numpy()
            z_latent_np = z.numpy()
        
        print(f'    β-VAE: recon_err={recon_err_np.mean():.4f}±{recon_err_np.std():.4f}, '
              f'kl={kl_div_np.mean():.4f}, mahal={mahal_np.mean():.4f}')
    
    # Step 3: Assemble 160 boost features = 93 raw + 64 latent + 3 anomaly
    n_raw = len(RAW_FEATURES)      # 93
    n_boost = len(BOOST_FEATURES)  # 160
    X_boost = np.zeros((n, n_boost), dtype=np.float32)
    X_boost[:, :n_raw] = X_preprocessed                         # 93 preprocessed raw
    X_boost[:, n_raw:n_raw + 64] = z_latent_np                  # 64 VAE latent dims
    X_boost[:, n_raw + 64] = recon_err_np                       # recon_err
    X_boost[:, n_raw + 65] = kl_div_np                          # kl_div
    X_boost[:, n_raw + 66] = mahal_np                           # mahalanobis
    
    # Step 4-6: GNN predictions (require graph)
    gat_prob_np = np.full(n, 0.5, dtype=np.float32)
    gat_unc_np = np.full(n, 0.1, dtype=np.float32)
    sage_prob_np = np.full(n, 0.5, dtype=np.float32)
    
    if (gat_model is not None or sage_model is not None) and n >= 3:
        # Build KNN graph from boost features
        k = min(10, n - 1)
        edge_index = build_knn_graph(X_boost, k=k)
        X_boost_t = torch.FloatTensor(X_boost)
        
        if gat_model is not None:
            with torch.no_grad():
                gat_model.eval()
                gat_logits = gat_model(X_boost_t, edge_index)
                gat_prob_np = torch.sigmoid(gat_logits).numpy()
            
            # MC Dropout for uncertainty
            gat_model.train()  # enable dropout
            mc_preds = []
            with torch.no_grad():
                for _ in range(20):
                    logits = gat_model(X_boost_t, edge_index)
                    mc_preds.append(torch.sigmoid(logits))
            mc_preds = torch.stack(mc_preds)
            gat_prob_np = mc_preds.mean(dim=0).numpy()
            gat_unc_np = mc_preds.std(dim=0).numpy()
            gat_model.eval()
            
            print(f'    GATv2:  prob={gat_prob_np.mean():.4f}±{gat_prob_np.std():.4f}, '
                  f'unc={gat_unc_np.mean():.4f}')
        
        if sage_model is not None:
            with torch.no_grad():
                sage_model.eval()
                sage_logits = sage_model(X_boost_t, edge_index)
                sage_prob_np = torch.sigmoid(sage_logits).numpy()
            
            print(f'    SAGE:   prob={sage_prob_np.mean():.4f}±{sage_prob_np.std():.4f}')
    
    # Step 7: XGB + LGB on full 160 boost features
    preds = predict_xgb_lgb(X_boost)
    
    # Step 8: Assemble 8 meta features
    # Order: [recon_err, kl_div, mahalanobis, gat_prob, gat_uncertainty, sage_prob, xgb_oof, lgb_oof]
    meta = np.column_stack([
        recon_err_np,
        kl_div_np,
        mahal_np,
        gat_prob_np,
        gat_unc_np,
        sage_prob_np,
        preds['xgb_prob'],
        preds['lgb_prob'],
    ])
    
    return {
        'X_preprocessed': X_preprocessed,
        'X_boost': X_boost,
        'z_latent': z_latent_np,
        'recon_err': recon_err_np,
        'kl_div': kl_div_np,
        'mahalanobis': mahal_np,
        'gat_prob': gat_prob_np,
        'gat_uncertainty': gat_unc_np,
        'sage_prob': sage_prob_np,
        'xgb_prob': preds['xgb_prob'],
        'lgb_prob': preds['lgb_prob'],
        'meta_features': meta,
    }


def predict_xgb_lgb(X_boost: np.ndarray) -> dict:
    """
    Run XGB + LGB on PREPROCESSED boost features (160-dim).
    Returns dict with xgb_prob and lgb_prob arrays.
    """
    X = np.nan_to_num(X_boost.astype(np.float32), nan=0.0, posinf=0.0, neginf=0.0)
    
    # XGBoost
    try:
        xgb_prob = xgb_model.predict_proba(X)[:, 1]
    except Exception:
        dmat = xgb.DMatrix(X)
        xgb_prob = xgb_model.predict(dmat)
    
    # LightGBM
    lgb_prob = lgb_model.predict(X)
    if lgb_prob.max() > 1.0 or lgb_prob.min() < 0.0:
        from scipy.special import expit
        lgb_prob = expit(lgb_prob)
    
    return {'xgb_prob': xgb_prob, 'lgb_prob': lgb_prob}


def predict_fraud_v2(X_raw_93: np.ndarray, use_meta: bool = False,
                     use_full_pipeline: bool = False) -> np.ndarray:
    """
    Run V2 model on raw 93-feature input with FULL preprocessing.
    
    Pipeline:
      1. Impute + log1p + RobustScale + clip (93 raw features)
      2. If use_full_pipeline: run β-VAE → GNN → full 160 boost features
         Else: pad to 160 (zeros for missing VAE latents + anomaly)
      3. XGB + LGB predict
      4. Optionally: meta-ensemble with real or zero meta features
    """
    if use_full_pipeline and vae_model is not None:
        feats = generate_full_features(X_raw_93)
        if use_meta and meta_model is not None:
            try:
                fraud_prob = meta_model.predict_proba(feats['meta_features'])[:, 1]
            except Exception:
                fraud_prob = feats['xgb_prob']
        else:
            fraud_prob = feats['xgb_prob']
        return fraud_prob
    
    # Fallback: original zero-padded approach
    X = np.nan_to_num(X_raw_93.astype(np.float32), nan=0.0, posinf=0.0, neginf=0.0)
    X_preprocessed = preprocess_raw(X)
    n = X_preprocessed.shape[0]
    n_raw = len(RAW_FEATURES)
    n_boost = len(BOOST_FEATURES)
    X_boost = np.zeros((n, n_boost), dtype=np.float32)
    X_boost[:, :n_raw] = X_preprocessed
    
    preds = predict_xgb_lgb(X_boost)
    
    if use_meta and meta_model is not None:
        meta_input = np.zeros((n, len(META_FEATURES)), dtype=np.float32)
        meta_input[:, -2] = preds['xgb_prob']
        meta_input[:, -1] = preds['lgb_prob']
        try:
            fraud_prob = meta_model.predict_proba(meta_input)[:, 1]
        except Exception:
            fraud_prob = preds['xgb_prob']
    else:
        fraud_prob = preds['xgb_prob']
    
    return fraud_prob


def recalibrate_platt(y_cal: np.ndarray, prob_cal: np.ndarray, prob_all: np.ndarray) -> np.ndarray:
    """
    Platt scaling recalibration.
    Fits LogisticRegression on (prob_cal → y_cal) then transforms prob_all.
    Use a held-out calibration split to avoid information leakage.
    """
    from sklearn.linear_model import LogisticRegression
    lr = LogisticRegression(C=1.0, max_iter=1000, random_state=42)
    lr.fit(prob_cal.reshape(-1, 1), y_cal)
    recal = lr.predict_proba(prob_all.reshape(-1, 1))[:, 1]
    print(f'    Platt recalibration: coef={lr.coef_[0][0]:.4f}, intercept={lr.intercept_[0]:.4f}')
    return recal


def predict_fraud_v2_ml3(X_raw_93: np.ndarray, use_full_pipeline: bool = True) -> np.ndarray:
    """
    Run V2 model through the RL Neural Network Meta-Learner (ML3).
    
    Full pipeline:
      1. Preprocess raw features (impute → log1p → scale → clip)
      2. β-VAE → recon_err, kl_div, mahalanobis + 64 latent dims
      3. Assemble 160 boost features
      4. Build KNN graph → GATv2 → gat_prob, gat_uncertainty
      5. GraphSAGE → sage_prob
      6. XGB + LGB → xgb_prob, lgb_prob
      7. All 8 meta features → LR+Q-Learning Neural Network
    
    Returns:
        fraud_prob: [n_samples] probability array
    """
    if ml3_model is None:
        raise ValueError("ML3 model not loaded")
    
    if use_full_pipeline and vae_model is not None:
        feats = generate_full_features(X_raw_93)
        meta_input = feats['meta_features']
    else:
        # Fallback: zero-padded meta features
        X = np.nan_to_num(X_raw_93.astype(np.float32), nan=0.0, posinf=0.0, neginf=0.0)
        X_preprocessed = preprocess_raw(X)
        n = X_preprocessed.shape[0]
        X_boost = np.zeros((n, len(BOOST_FEATURES)), dtype=np.float32)
        X_boost[:, :len(RAW_FEATURES)] = X_preprocessed
        preds = predict_xgb_lgb(X_boost)
        meta_input = np.zeros((n, len(META_FEATURES)), dtype=np.float32)
        meta_input[:, -2] = preds['xgb_prob']
        meta_input[:, -1] = preds['lgb_prob']
    
    with torch.no_grad():
        x_t = torch.FloatTensor(meta_input)
        base_probs_t = torch.FloatTensor(meta_input)
        fraud_prob, details = ml3_model(x_t, base_probs_t)
        fraud_prob = fraud_prob.numpy()
    
    return np.clip(fraud_prob, 0, 1)


def predict_teacher(feature_df: pd.DataFrame) -> np.ndarray:
    """
    Run the TEACHER XGBoost (Hope_machine) on a DataFrame.
    
    The teacher expects 171 features (56 core + 115 missingness flags).
    We build the full feature matrix: fill core features from the DataFrame,
    and generate _was_missing / _not_applicable flags automatically.
    
    Args:
        feature_df: DataFrame with columns matching teacher core feature names
    Returns:
        fraud_prob: [n_samples] probability array
    """
    n = len(feature_df)
    X = np.zeros((n, len(TEACHER_FEATURES)), dtype=np.float32)
    
    # Fill core features
    mapped_count = 0
    for i, fname in enumerate(TEACHER_FEATURES):
        if fname in feature_df.columns:
            vals = pd.to_numeric(feature_df[fname], errors='coerce').fillna(0).values
            X[:, i] = vals.astype(np.float32)
            if (vals != 0).any():
                mapped_count += 1
        elif fname.endswith('_was_missing'):
            # Set was_missing=1 for features we don't have
            core_name = fname.replace('_was_missing', '')
            if core_name not in feature_df.columns:
                X[:, i] = 1.0
        elif fname.endswith('_not_applicable'):
            core_name = fname.replace('_not_applicable', '')
            if core_name not in feature_df.columns:
                X[:, i] = 1.0
    
    print(f'    Teacher features mapped: {mapped_count}/{len(TEACHER_CORE)} core features')
    
    dmat = xgb.DMatrix(X, feature_names=TEACHER_FEATURES)
    prob = teacher_xgb.predict(dmat)
    return prob


def build_v2_feature_matrix(df: pd.DataFrame) -> np.ndarray:
    """
    Build the 93-feature raw matrix from a DataFrame.
    Maps available columns to RAW_FEATURES order, fills missing with 0.
    """
    X = np.zeros((len(df), len(RAW_FEATURES)), dtype=np.float32)
    for i, feat in enumerate(RAW_FEATURES):
        if feat in df.columns:
            X[:, i] = pd.to_numeric(df[feat], errors='coerce').fillna(0).values
    return np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)


def evaluate_and_report(name: str, y_true: np.ndarray, y_prob: np.ndarray,
                        threshold: float = None, also_try_xgb_threshold: bool = True) -> dict:
    """Full evaluation report for one external dataset."""
    if threshold is None:
        threshold = OPTIMAL_THRESHOLD

    y_pred = (y_prob >= threshold).astype(int)

    n_pos = int(y_true.sum())
    n_neg = int((y_true == 0).sum())
    
    if n_pos == 0 or n_neg == 0:
        print(f'\n⚠️  {name}: Only one class present (pos={n_pos}, neg={n_neg})')
        print(f'   Mean predicted prob: {y_prob.mean():.4f} (min={y_prob.min():.4f}, max={y_prob.max():.4f})')
        print(f'   Predicted positive rate: {y_pred.mean():.2%}')
        return {'name': name, 'n_samples': len(y_true), 'n_pos': n_pos,
                'n_neg': n_neg, 'error': 'single_class',
                'mean_prob': round(float(y_prob.mean()), 4)}

    roc = roc_auc_score(y_true, y_prob)
    pr = average_precision_score(y_true, y_prob)
    f1 = f1_score(y_true, y_pred, zero_division=0)
    prec = precision_score(y_true, y_pred, zero_division=0)
    rec = recall_score(y_true, y_pred, zero_division=0)

    # Find dataset-optimal threshold
    prec_curve, rec_curve, thresholds_curve = precision_recall_curve(y_true, y_prob)
    f1s = 2 * prec_curve * rec_curve / (prec_curve + rec_curve + 1e-10)
    best_idx = np.argmax(f1s)
    best_thresh = thresholds_curve[min(best_idx, len(thresholds_curve)-1)]
    best_f1 = f1s[best_idx]

    # Also evaluate at XGB-specific threshold
    xgb_thresh = THRESHOLDS.get('xgb_p85', OPTIMAL_THRESHOLD)
    y_pred_xgb = (y_prob >= xgb_thresh).astype(int)
    f1_xgb = f1_score(y_true, y_pred_xgb, zero_division=0)

    print(f'\n{"="*70}')
    print(f'  📊 {name}')
    print(f'{"="*70}')
    print(f'  Samples: {len(y_true):,}  (pos={n_pos:,}, neg={n_neg:,}, rate={n_pos/len(y_true):.2%})')
    print(f'  ── Production threshold ({threshold:.4f}) ──')
    print(f'    ROC-AUC:    {roc:.4f}')
    print(f'    PR-AUC:     {pr:.4f}')
    print(f'    F1:         {f1:.4f}')
    print(f'    Precision:  {prec:.4f}')
    print(f'    Recall:     {rec:.4f}')
    print(f'  ── Dataset-optimal threshold ({best_thresh:.4f}) ──')
    print(f'    Best F1:    {best_f1:.4f}')
    if also_try_xgb_threshold:
        print(f'  ── XGB P85 threshold ({xgb_thresh:.6f}) ──')
        print(f'    F1:         {f1_xgb:.4f}')
    cm = confusion_matrix(y_true, y_pred)
    tp, fn, fp, tn = cm[1,1], cm[1,0], cm[0,1], cm[0,0]

    print(f'\n  Confusion Matrix (production threshold):')
    print(f'    TN={tn:,}  FP={fp:,}')
    print(f'    FN={fn:,}  TP={tp:,}')

    # === FRAUD CAUGHT vs FRAUD PRESENT ===
    print(f'\n  FRAUD DETECTION SCORECARD:')
    print(f'    Fraud present: {n_pos:,}    Normal present: {n_neg:,}')
    print(f'    {"─"*60}')
    detection_rows = []
    for thr_label, thr in [
        ('Production', threshold),
        ('Optimal F1', float(best_thresh)),
        ('0.50', 0.5),
        ('0.30', 0.3),
        ('0.10', 0.1),
    ]:
        yp = (y_prob >= thr).astype(int)
        caught = int((yp & y_true.astype(int)).sum())
        false_alarms = int((yp & (1 - y_true.astype(int))).sum())
        det_rate = caught / n_pos if n_pos else 0
        fa_rate = false_alarms / n_neg if n_neg else 0
        detection_rows.append((thr_label, thr, caught, n_pos, false_alarms, n_neg))
        print(f'    @{thr_label:>12} ({thr:.4f}):  Caught {caught:>6,} / {n_pos:,} fraud ({det_rate:>6.1%})  |  False alarms {false_alarms:>6,} / {n_neg:,} ({fa_rate:>6.1%})')

    # Best threshold for catching the most fraud
    prod_caught = int(((y_prob >= threshold).astype(int) & y_true.astype(int)).sum())
    opt_caught = int(((y_prob >= best_thresh).astype(int) & y_true.astype(int)).sum())

    # Probability distribution
    print(f'\n  Probability distribution:')
    print(f'    Fraud cases:  mean={y_prob[y_true==1].mean():.4f}  median={np.median(y_prob[y_true==1]):.4f}  std={y_prob[y_true==1].std():.4f}')
    print(f'    Normal cases: mean={y_prob[y_true==0].mean():.4f}  median={np.median(y_prob[y_true==0]):.4f}  std={y_prob[y_true==0].std():.4f}')

    prod_fa = int(((y_prob >= threshold).astype(int) & (1 - y_true.astype(int))).sum())
    opt_fa = int(((y_prob >= best_thresh).astype(int) & (1 - y_true.astype(int))).sum())

    return {
        'name': name, 'n_samples': len(y_true), 'n_pos': n_pos, 'n_neg': n_neg,
        'roc_auc': round(roc, 4), 'pr_auc': round(pr, 4),
        'f1_production': round(f1, 4), 'precision': round(prec, 4),
        'recall': round(rec, 4), 'f1_optimal': round(float(best_f1), 4),
        'optimal_threshold': round(float(best_thresh), 4),
        'production_threshold': round(float(threshold), 4),
        'mean_prob_fraud': round(float(y_prob[y_true==1].mean()), 4),
        'mean_prob_normal': round(float(y_prob[y_true==0].mean()), 4),
        'caught_production': prod_caught,
        'caught_optimal': opt_caught,
        'fa_production': prod_fa,
        'fa_optimal': opt_fa,
    }


ALL_RESULTS = []
print('✅ All utilities ready')

# %% [markdown]
# ---
# ## Dataset 1: Elliptic Bitcoin Transaction Dataset
# **Source**: Law enforcement + exchange compliance  
# **Size**: 203K tx (4,545 illicit, 42,019 licit)  
# **Why**: Gold-standard independent labels. Tests cross-chain generalisation.

# %% Cell 3: Download Elliptic Dataset
elliptic_dir = DATA_DIR / 'elliptic'
elliptic_dir.mkdir(parents=True, exist_ok=True)

features_file = elliptic_dir / 'elliptic_txs_features.csv'
classes_file = elliptic_dir / 'elliptic_txs_classes.csv'

if not features_file.exists():
    print('📥 Downloading Elliptic dataset via kagglehub...')
    try:
        import kagglehub
        path = kagglehub.dataset_download('ellipticco/elliptic-data-set')
        print(f'   Downloaded to: {path}')
        import shutil
        dl_path = Path(path)
        for f in dl_path.rglob('*.csv'):
            dest = elliptic_dir / f.name
            if not dest.exists():
                shutil.copy2(f, dest)
                print(f'   Copied: {f.name}')
    except Exception as e:
        print(f'❌ Download failed: {e}')
        print(f'   Manual: https://www.kaggle.com/datasets/ellipticco/elliptic-data-set')
        print(f'   Extract to: {elliptic_dir}')
else:
    print(f'✅ Elliptic dataset already present')

for f in [features_file, classes_file]:
    if f.exists():
        print(f'   ✓ {f.name} ({f.stat().st_size / 1e6:.1f} MB)')
    else:
        print(f'   ✗ {f.name} — MISSING')

# %% Cell 4: Evaluate on Elliptic
print('\n📊 Evaluating V2 model on Elliptic Bitcoin Dataset...')
t0 = time.time()

if features_file.exists() and classes_file.exists():
    # Load Elliptic (167 cols: txId + 166 anonymised features)
    df_feat = pd.read_csv(features_file, header=None)
    df_feat.columns = ['txId'] + [f'feat_{i}' for i in range(1, 167)]
    
    df_class = pd.read_csv(classes_file)
    df_class.columns = ['txId', 'class']
    
    df_ell = df_feat.merge(df_class, on='txId')
    df_labeled = df_ell[df_ell['class'].isin(['1', '2', 1, 2])].copy()
    df_labeled['fraud'] = (df_labeled['class'].astype(str) == '1').astype(int)
    
    print(f'  Total: {len(df_ell):,}  |  Labeled: {len(df_labeled):,}')
    print(f'  Illicit: {df_labeled["fraud"].sum():,}  |  Licit: {(df_labeled["fraud"]==0).sum():,}  |  Rate: {df_labeled["fraud"].mean():.2%}')
    
    # ── Feature Mapping (V2 has 93 raw features — much richer than V1's 21) ──
    # Elliptic features are anonymised, but Weber et al. (2019) describes:
    #   feat_1 = time step
    #   feat_2-94 = local features (amounts, fees, in/out degree, etc.)
    #   feat_95-166 = 1-hop aggregated neighborhood features
    # 
    # V2 raw features include sender+receiver aggregates + graph metrics + mixer flags
    # We map Elliptic's local features to tx-level, and 1-hop to sender/receiver aggregates
    
    mapped = pd.DataFrame()
    
    # TX-level features (from Elliptic local features)
    mapped['value_eth'] = df_labeled['feat_2'].abs()
    mapped['gas_price_gwei'] = df_labeled['feat_3'].abs()
    mapped['gas_used'] = df_labeled['feat_4'].abs()
    mapped['gas_limit'] = df_labeled['feat_5'].abs()
    mapped['transaction_type'] = 0.0  # Bitcoin has no tx types
    mapped['nonce'] = df_labeled['feat_6'].abs()
    mapped['transaction_index'] = df_labeled['feat_7'].abs()
    
    # Sender aggregate features (from Elliptic 1-hop features)
    sender_feat_map = {
        'sender_sent_count': 'feat_8',
        'sender_total_sent': 'feat_9',
        'sender_avg_sent': 'feat_10',
        'sender_max_sent': 'feat_11',
        'sender_min_sent': 'feat_12',
        'sender_std_sent': 'feat_13',
        'sender_total_gas_sent': 'feat_14',
        'sender_avg_gas_used': 'feat_15',
        'sender_avg_gas_price': 'feat_16',
        'sender_unique_receivers': 'feat_17',
        'sender_received_count': 'feat_18',
        'sender_total_received': 'feat_19',
        'sender_avg_received': 'feat_20',
        'sender_max_received': 'feat_21',
        'sender_min_received': 'feat_22',
        'sender_std_received': 'feat_23',
        'sender_unique_senders': 'feat_24',
        'sender_total_transactions': 'feat_25',
        'sender_balance': 'feat_26',
        'sender_in_out_ratio': 'feat_27',
        'sender_unique_counterparties': 'feat_28',
        'sender_avg_value': 'feat_29',
        'sender_neighbors': 'feat_30',
        'sender_count': 'feat_31',
        'sender_income': 'feat_32',
        'sender_active_duration_mins': 'feat_33',
        'sender_in_degree': 'feat_34',
        'sender_out_degree': 'feat_35',
        'sender_degree': 'feat_36',
        'sender_degree_centrality': 'feat_37',
        'sender_betweenness_proxy': 'feat_38',
    }
    
    for our_feat, ell_feat in sender_feat_map.items():
        if ell_feat in df_labeled.columns:
            mapped[our_feat] = df_labeled[ell_feat].abs()
    
    # Receiver aggregate features (from deeper Elliptic features)
    receiver_offset = 50  # Elliptic receiver-side features start around feat_50+
    receiver_feat_map = {
        'receiver_sent_count': f'feat_{receiver_offset}',
        'receiver_total_sent': f'feat_{receiver_offset+1}',
        'receiver_avg_sent': f'feat_{receiver_offset+2}',
        'receiver_max_sent': f'feat_{receiver_offset+3}',
        'receiver_min_sent': f'feat_{receiver_offset+4}',
        'receiver_std_sent': f'feat_{receiver_offset+5}',
        'receiver_total_gas_sent': f'feat_{receiver_offset+6}',
        'receiver_avg_gas_used': f'feat_{receiver_offset+7}',
        'receiver_avg_gas_price': f'feat_{receiver_offset+8}',
        'receiver_unique_receivers': f'feat_{receiver_offset+9}',
        'receiver_received_count': f'feat_{receiver_offset+10}',
        'receiver_total_received': f'feat_{receiver_offset+11}',
        'receiver_avg_received': f'feat_{receiver_offset+12}',
        'receiver_max_received': f'feat_{receiver_offset+13}',
        'receiver_min_received': f'feat_{receiver_offset+14}',
        'receiver_std_received': f'feat_{receiver_offset+15}',
        'receiver_unique_senders': f'feat_{receiver_offset+16}',
        'receiver_total_transactions': f'feat_{receiver_offset+17}',
        'receiver_balance': f'feat_{receiver_offset+18}',
        'receiver_in_out_ratio': f'feat_{receiver_offset+19}',
        'receiver_unique_counterparties': f'feat_{receiver_offset+20}',
        'receiver_avg_value': f'feat_{receiver_offset+21}',
        'receiver_neighbors': f'feat_{receiver_offset+22}',
        'receiver_count': f'feat_{receiver_offset+23}',
        'receiver_income': f'feat_{receiver_offset+24}',
        'receiver_active_duration_mins': f'feat_{receiver_offset+25}',
        'receiver_in_degree': f'feat_{receiver_offset+26}',
        'receiver_out_degree': f'feat_{receiver_offset+27}',
        'receiver_degree': f'feat_{receiver_offset+28}',
        'receiver_degree_centrality': f'feat_{receiver_offset+29}',
        'receiver_betweenness_proxy': f'feat_{receiver_offset+30}',
    }
    
    for our_feat, ell_feat in receiver_feat_map.items():
        if ell_feat in df_labeled.columns:
            mapped[our_feat] = df_labeled[ell_feat].abs()
    
    # Mixer/sanctioned/exchange flags — not available in Elliptic (set to 0)
    # These 18 features (sender_sent_to_mixer, etc.) will be 0
    
    X_ell = build_v2_feature_matrix(mapped)
    y_ell = df_labeled['fraud'].values.astype(int)
    
    # Count actually mapped features
    mapped_count = sum(1 for i, f in enumerate(RAW_FEATURES) if (X_ell[:, i] != 0).any())
    print(f'  Features mapped: {mapped_count}/{len(RAW_FEATURES)} raw features')
    
    # ── Strategy A: XGB direct (with full preprocessing) ──
    print('\n  ── Strategy A: XGB Direct (preprocessed, zero-padded) ──')
    prob_ell_raw = predict_fraud_v2(X_ell, use_meta=False, use_full_pipeline=False)
    result_ell_raw = evaluate_and_report('Elliptic (XGB zero-padded)', y_ell, prob_ell_raw)
    ALL_RESULTS.append(result_ell_raw)
    
    # ── Strategy A2: XGB with FULL pipeline (VAE+GNN features) ──
    print('\n  ── Strategy A2: Full Pipeline (β-VAE → GNN → XGB) ──')
    feats_ell = generate_full_features(X_ell)
    prob_ell_full = feats_ell['xgb_prob']
    result_ell_full = evaluate_and_report('Elliptic (Full Pipeline XGB)', y_ell, prob_ell_full)
    ALL_RESULTS.append(result_ell_full)
    
    # ── Strategy B: XGB + Platt Recalibration ──
    # Use 20% as calibration set, evaluate on remaining 80%
    from sklearn.model_selection import StratifiedShuffleSplit
    print('\n  ── Strategy B: Full Pipeline + Platt Recalibration ──')
    sss = StratifiedShuffleSplit(n_splits=1, test_size=0.8, random_state=42)
    cal_idx, eval_idx = next(sss.split(X_ell, y_ell))
    
    prob_ell_recal = recalibrate_platt(
        y_ell[cal_idx], prob_ell_full[cal_idx],
        prob_ell_full[eval_idx]
    )
    recal_threshold = 0.5  # Standard threshold after Platt scaling
    result_ell_recal = evaluate_and_report(
        'Elliptic (Full+Platt)', y_ell[eval_idx], prob_ell_recal,
        threshold=recal_threshold
    )
    ALL_RESULTS.append(result_ell_recal)
    
    # ── Strategy C: Meta-ensemble (LR) with full features + Platt ──
    print('\n  ── Strategy C: Meta-LR (full features) + Platt ──')
    try:
        prob_ell_meta = meta_model.predict_proba(feats_ell['meta_features'])[:, 1]
    except Exception:
        prob_ell_meta = prob_ell_full
    prob_ell_meta_recal = recalibrate_platt(
        y_ell[cal_idx], prob_ell_meta[cal_idx],
        prob_ell_meta[eval_idx]
    )
    result_ell_meta = evaluate_and_report(
        'Elliptic (Meta-LR+full+Platt)', y_ell[eval_idx], prob_ell_meta_recal,
        threshold=recal_threshold
    )
    ALL_RESULTS.append(result_ell_meta)
    
    # ── Strategy E: ML3 (RL Neural Network Meta-Learner) with full features + Platt ──
    if ml3_model is not None:
        print('\n  ── Strategy E: ML3 (LR+Q-Learning NN, full features) + Platt ──')
        prob_ell_ml3 = predict_fraud_v2_ml3(X_ell, use_full_pipeline=True)
        prob_ell_ml3_recal = recalibrate_platt(
            y_ell[cal_idx], prob_ell_ml3[cal_idx],
            prob_ell_ml3[eval_idx]
        )
        result_ell_ml3 = evaluate_and_report(
            'Elliptic (ML3-RL+full+Platt)', y_ell[eval_idx], prob_ell_ml3_recal,
            threshold=recal_threshold
        )
        ALL_RESULTS.append(result_ell_ml3)
        
        # Also evaluate ML3 raw (no Platt) for comparison
        print('\n  ── Strategy E2: ML3 (full features) Raw ──')
        result_ell_ml3_raw = evaluate_and_report(
            'Elliptic (ML3-RL+full raw)', y_ell, prob_ell_ml3
        )
        ALL_RESULTS.append(result_ell_ml3_raw)
    
    # ── Strategy D: Concept Alignment Test ──
    from sklearn.model_selection import cross_val_predict
    from sklearn.linear_model import LogisticRegression
    
    feat_cols = [c for c in df_labeled.columns if c.startswith('feat_')]
    X_ell_native = df_labeled[feat_cols].values.astype(np.float32)
    X_ell_native = np.nan_to_num(X_ell_native, nan=0.0)
    
    print('\n  ── Strategy D: Concept Alignment Test ──')
    print('  Does our V2 fraud score add value to Elliptic native features?')
    
    lr_base = LogisticRegression(max_iter=1000, C=0.1, random_state=42)
    base_preds = cross_val_predict(lr_base, X_ell_native, y_ell, cv=5, method='predict_proba')[:, 1]
    base_roc = roc_auc_score(y_ell, base_preds)
    base_ap = average_precision_score(y_ell, base_preds)
    
    X_augmented = np.column_stack([X_ell_native, prob_ell_raw.reshape(-1, 1)])
    lr_aug = LogisticRegression(max_iter=1000, C=0.1, random_state=42)
    aug_preds = cross_val_predict(lr_aug, X_augmented, y_ell, cv=5, method='predict_proba')[:, 1]
    aug_roc = roc_auc_score(y_ell, aug_preds)
    aug_ap = average_precision_score(y_ell, aug_preds)
    
    print(f'  Elliptic features only:     ROC-AUC={base_roc:.4f}  PR-AUC={base_ap:.4f}')
    print(f'  Elliptic + V2 score:        ROC-AUC={aug_roc:.4f}  PR-AUC={aug_ap:.4f}')
    delta = aug_roc - base_roc
    if delta > 0.005:
        print(f'  ✅ V2 score adds +{delta:.4f} ROC-AUC — complementary fraud signal')
    elif delta > -0.005:
        print(f'  ➡️  V2 score is neutral ({delta:+.4f}) — possibly redundant')
    else:
        print(f'  ⚠️  V2 score reduces performance ({delta:+.4f}) — domain mismatch')
    
    # Overlap analysis (using recalibrated scores)
    our_high_risk = prob_ell_raw >= OPTIMAL_THRESHOLD
    overlap_rate = y_ell[our_high_risk].mean() if our_high_risk.sum() > 0 else 0
    print(f'\n  ── Overlap Analysis ──')
    print(f'  V2 flags {our_high_risk.sum():,} / {len(y_ell):,} as high-risk ({our_high_risk.mean():.2%})')
    print(f'  Of those, {overlap_rate:.2%} are truly illicit per Elliptic labels')
    print(f'  Baseline fraud rate: {y_ell.mean():.2%}')
    lift = overlap_rate / max(y_ell.mean(), 1e-6)
    print(f'  Lift: {lift:.1f}x over baseline')
    
    # ── Strategy E: TEACHER MODEL (Hope_machine XGB) — Direct Bitcoin Evaluation ──
    print('\n  ── Strategy E: Teacher XGB (Hope_machine — Bitcoin-trained) ──')
    print('  The teacher was trained on 99.7% BitcoinHeist + 0.3% ETH Kaggle.')
    print('  Evaluating teacher directly on Elliptic (Bitcoin) — this shows the')
    print('  CEILING that the student could inherit through distillation.')
    
    # Map Elliptic to teacher schema — teacher uses address-aggregate features
    # Elliptic's 166 anonymised features don't directly name-match teacher's features,
    # so we map using the same approximate positional mapping (Weber et al. 2019):
    #   feat_2-94 = local features, feat_95-166 = 1-hop aggregated
    teacher_ell_df = pd.DataFrame()
    teacher_ell_map = {
        'total_ether_sent': 'feat_9',       # ~ total value sent
        'total_ether_received': 'feat_19',   # ~ total value received
        'sent_tnx': 'feat_31',              # ~ sender count
        'received_tnx': 'feat_18',          # ~ receive count
        'avg_val_sent': 'feat_10',           # ~ avg sent value
        'avg_val_received': 'feat_20',       # ~ avg received value
        'max_val_sent': 'feat_11',
        'max_value_received': 'feat_21',
        'min_val_sent': 'feat_12',
        'min_value_received': 'feat_22',
        'unique_sent_to_addresses': 'feat_17',
        'unique_received_from_addresses': 'feat_24',
        'total_ether_balance': 'feat_26',
        'neighbors': 'feat_30',
        'income': 'feat_32',
        'time_diff_between_first_and_last_(mins)': 'feat_33',
        'avg_min_between_sent_tnx': 'feat_34',
        'avg_min_between_received_tnx': 'feat_35',
        'count': 'feat_36',
        'total_transactions_(including_tnx_to_create_contract': 'feat_25',
        'total_ether_sent_contracts': 'feat_14',
        'number_of_created_contracts': 'feat_41',
        'looped': 'feat_2',
        'weight': 'feat_3',
        'length': 'feat_4',
    }
    for teacher_feat, ell_feat in teacher_ell_map.items():
        if ell_feat in df_labeled.columns:
            teacher_ell_df[teacher_feat] = df_labeled[ell_feat].abs()
    
    prob_teacher_ell = predict_teacher(teacher_ell_df)
    result_teacher_ell = evaluate_and_report(
        'Elliptic (TEACHER XGB — Bitcoin-trained)', y_ell, prob_teacher_ell,
        threshold=0.5  # Teacher may have different optimal threshold
    )
    ALL_RESULTS.append(result_teacher_ell)
    
    # Teacher + Platt
    print('\n  ── Teacher + Platt Recalibration ──')
    prob_teacher_recal = recalibrate_platt(
        y_ell[cal_idx], prob_teacher_ell[cal_idx],
        prob_teacher_ell[eval_idx]
    )
    result_teacher_recal = evaluate_and_report(
        'Elliptic (Teacher+Platt)', y_ell[eval_idx], prob_teacher_recal,
        threshold=0.5
    )
    ALL_RESULTS.append(result_teacher_recal)
    
    print(f'\n  ⏱️  Elliptic evaluation completed in {time.time()-t0:.1f}s')
else:
    print('⚠️  Elliptic dataset not found. Run download cell first.')


# %% [markdown]
# ---
# ## Dataset 2: XBlock Ethereum Phishing Addresses
# **Source**: Zhejiang University  
# **Size**: ~9.8K addresses (confirmed phishing vs normal)
# **Why**: Ethereum-native, independently labeled

# %% Cell 5: Evaluate on XBlock Phishing
print('\n📊 Evaluating V2 model on XBlock Ethereum Phishing Dataset...')
t0 = time.time()

xblock_dir = DATA_DIR / 'xblock'
xblock_dir.mkdir(parents=True, exist_ok=True)
xblock_file = xblock_dir / 'transaction_dataset.csv'

if not xblock_file.exists():
    print('📥 Downloading XBlock dataset...')
    try:
        import kagglehub
        kpath = kagglehub.dataset_download('vagifa/ethereum-frauddetection-dataset')
        print(f'   Downloaded to: {kpath}')
        import shutil
        for f in Path(kpath).rglob('*.csv'):
            dest = xblock_dir / f.name
            shutil.copy2(f, dest)
            print(f'   Copied: {f.name}')
            if 'transaction' in f.name.lower():
                xblock_file = dest
    except Exception as e:
        print(f'   ⚠️  Download failed: {e}')
        print(f'   Manual: https://www.kaggle.com/datasets/vagifa/ethereum-frauddetection-dataset')

if xblock_file.exists():
    df_xb = pd.read_csv(xblock_file)
    print(f'  Loaded {len(df_xb):,} records')
    print(f'  Columns: {list(df_xb.columns)}')
    
    # Identify label column
    label_col = None
    for candidate in ['FLAG', 'flag', 'label', 'Label', 'class', 'Class', 'is_phishing', 'FLAG ']:
        if candidate in df_xb.columns:
            label_col = candidate
            break
    
    if label_col is None:
        print(f'  ⚠️  Could not find label column')
    else:
        y_xb = df_xb[label_col].astype(int).values
        print(f'  Label: "{label_col}" | Phishing: {y_xb.sum():,}  Normal: {(y_xb==0).sum():,}')
        
        # Map XBlock address features to V2 schema
        # XBlock has address aggregates similar to our sender_* features
        xb_map = {
            # Sender-side features
            'Sent tnx': 'sender_sent_count',
            'total Ether sent': 'sender_total_sent',
            'avg val sent': 'sender_avg_sent',
            'max val sent': 'sender_max_sent',
            'min val sent': 'sender_min_sent',
            'Avg min between sent tnx': 'sender_active_duration_mins',
            'Unique Sent To Addresses': 'sender_unique_receivers',
            'total ether balance': 'sender_balance',
            'ERC20 total Ether sent': 'sender_total_gas_sent',  # Proxy
            
            # Receiver-side features
            'Received Tnx': 'receiver_received_count',
            'total ether received': 'receiver_total_received',  
            'avg val received': 'receiver_avg_received',
            'max val received': 'receiver_max_received',
            'min val received': 'receiver_min_received',
            'Avg min between received tnx': 'receiver_active_duration_mins',
            'Unique Received From Addresses': 'receiver_unique_senders',
            
            # Cross-map to also populate sender_total_received
            'total ether received ': 'sender_total_received',
        }
        
        mapped_xb = pd.DataFrame()
        for src_col, dst_col in xb_map.items():
            for actual_col in df_xb.columns:
                if actual_col.strip() == src_col.strip():
                    mapped_xb[dst_col] = pd.to_numeric(df_xb[actual_col], errors='coerce').fillna(0)
                    break
        
        # Derive additional features
        if 'sender_total_sent' in mapped_xb.columns and 'sender_sent_count' in mapped_xb.columns:
            mapped_xb['value_eth'] = mapped_xb['sender_total_sent'] / mapped_xb['sender_sent_count'].replace(0, 1)
            mapped_xb['sender_total_transactions'] = mapped_xb['sender_sent_count']
        
        if 'sender_sent_count' in mapped_xb.columns and 'receiver_received_count' in mapped_xb.columns:
            mapped_xb['sender_in_out_ratio'] = mapped_xb['receiver_received_count'] / mapped_xb['sender_sent_count'].replace(0, 1)
            mapped_xb['sender_degree'] = mapped_xb['sender_sent_count'] + mapped_xb['receiver_received_count']
            mapped_xb['sender_in_degree'] = mapped_xb['receiver_received_count']
            mapped_xb['sender_out_degree'] = mapped_xb['sender_sent_count']
        
        if 'sender_unique_receivers' in mapped_xb.columns and 'receiver_unique_senders' in mapped_xb.columns:
            mapped_xb['sender_unique_counterparties'] = (
                mapped_xb.get('sender_unique_receivers', 0) + mapped_xb.get('receiver_unique_senders', 0)
            )
            mapped_xb['sender_neighbors'] = mapped_xb['sender_unique_counterparties']
        
        X_xb = build_v2_feature_matrix(mapped_xb)
        mapped_count = sum(1 for i, f in enumerate(RAW_FEATURES) if (X_xb[:, i] != 0).any())
        print(f'  Features mapped: {mapped_count}/{len(RAW_FEATURES)} raw features')
        print(f'  ⚠️  NOTE: XBlock is ADDRESS-level data. Our model is TRANSACTION-level.')
        print(f'  Mapping address aggregates → sender/receiver features for best-effort eval.')
        
        # Predict (XGB with zero-padded preprocessing for baseline)
        prob_xb_raw = predict_fraud_v2(X_xb, use_meta=False, use_full_pipeline=False)
        result_xb_raw = evaluate_and_report('XBlock (XGB zero-padded)', y_xb, prob_xb_raw)
        ALL_RESULTS.append(result_xb_raw)
        
        # Full pipeline XGB
        print('\n  ── XBlock Full Pipeline (β-VAE → GNN → XGB) ──')
        feats_xb = generate_full_features(X_xb)
        prob_xb_full = feats_xb['xgb_prob']
        result_xb_full = evaluate_and_report('XBlock (Full Pipeline XGB)', y_xb, prob_xb_full)
        ALL_RESULTS.append(result_xb_full)
        
        # Full pipeline + Platt recalibration
        from sklearn.model_selection import StratifiedShuffleSplit
        print('\n  ── XBlock Full Pipeline + Platt ──')
        sss_xb = StratifiedShuffleSplit(n_splits=1, test_size=0.8, random_state=42)
        cal_xb, eval_xb = next(sss_xb.split(X_xb, y_xb))
        
        prob_xb_recal = recalibrate_platt(
            y_xb[cal_xb], prob_xb_full[cal_xb],
            prob_xb_full[eval_xb]
        )
        result_xb_recal = evaluate_and_report(
            'XBlock (Full+Platt)', y_xb[eval_xb], prob_xb_recal,
            threshold=0.5
        )
        ALL_RESULTS.append(result_xb_recal)
        
        # Meta-LR (full features) + Platt
        print('\n  ── XBlock Meta-LR (full features) + Platt ──')
        try:
            prob_xb_meta = meta_model.predict_proba(feats_xb['meta_features'])[:, 1]
        except Exception:
            prob_xb_meta = prob_xb_full
        prob_xb_meta_recal = recalibrate_platt(
            y_xb[cal_xb], prob_xb_meta[cal_xb],
            prob_xb_meta[eval_xb]
        )
        result_xb_meta = evaluate_and_report(
            'XBlock (Meta-LR+full+Platt)', y_xb[eval_xb], prob_xb_meta_recal,
            threshold=0.5
        )
        ALL_RESULTS.append(result_xb_meta)
        
        # ── ML3 (RL Neural Network) with full features on XBlock ──
        if ml3_model is not None:
            print('\n  ── ML3 (LR+Q-Learning NN, full features) + Platt on XBlock ──')
            prob_xb_ml3 = predict_fraud_v2_ml3(X_xb, use_full_pipeline=True)
            prob_xb_ml3_recal = recalibrate_platt(
                y_xb[cal_xb], prob_xb_ml3[cal_xb],
                prob_xb_ml3[eval_xb]
            )
            result_xb_ml3 = evaluate_and_report(
                'XBlock (ML3-RL+full+Platt)', y_xb[eval_xb], prob_xb_ml3_recal,
                threshold=0.5
            )
            ALL_RESULTS.append(result_xb_ml3)
        
        # ── TEACHER MODEL on XBlock ──
        # Teacher was trained on address-level features from the SAME Kaggle ETH dataset!
        # XBlock columns name-match teacher features directly.
        print('\n  ── Teacher XGB on XBlock (SAME source distribution!) ──')
        print('  The teacher trained on Kaggle ETH Phishing = XBlock source.')
        print('  This measures in-distribution recall, NOT generalization.')
        
        # Build teacher feature DataFrame — direct column name mapping
        teacher_xb_col_map = {
            'avg_min_between_sent_tnx': 'Avg min between sent tnx',
            'avg_min_between_received_tnx': 'Avg min between received tnx',
            'avg_val_received': 'avg val received',
            'avg_val_sent': 'avg val sent',
            'avg_value_sent_to_contract': 'avg value sent to contract',
            'max_val_sent': 'max val sent',
            'max_val_sent_to_contract': 'max val sent to contract',
            'max_value_received': 'max value received ',
            'min_val_sent': 'min val sent',
            'min_value_received': 'min value received',
            'min_value_sent_to_contract': 'min value sent to contract',
            'neighbors': 'Unique Sent To Addresses',  # proxy
            'number_of_created_contracts': 'Number of Created Contracts',
            'received_tnx': 'Received Tnx',
            'sent_tnx': 'Sent tnx',
            'time_diff_between_first_and_last_(mins)': 'Time Diff between first and last (Mins)',
            'total_erc20_tnxs': ' Total ERC20 tnxs',
            'total_ether_balance': 'total ether balance',
            'total_ether_received': 'total ether received',
            'total_ether_sent': 'total Ether sent',
            'total_ether_sent_contracts': 'total ether sent contracts',
            'total_transactions_(including_tnx_to_create_contract': 'total transactions (including tnx to create contract',
            'unique_received_from_addresses': 'Unique Received From Addresses',
            'unique_sent_to_addresses': 'Unique Sent To Addresses',
            'erc20_total_ether_received': ' ERC20 total Ether received',
            'erc20_total_ether_sent': ' ERC20 total ether sent',
            'erc20_total_ether_sent_contract': ' ERC20 total Ether sent contract',
            'erc20_uniq_sent_addr': ' ERC20 uniq sent addr',
            'erc20_uniq_rec_addr': ' ERC20 uniq rec addr',
            'erc20_uniq_sent_addr.1': ' ERC20 uniq sent addr.1',
            'erc20_uniq_rec_contract_addr': ' ERC20 uniq rec contract addr',
            'erc20_avg_time_between_sent_tnx': ' ERC20 avg time between sent tnx',
            'erc20_avg_time_between_rec_tnx': ' ERC20 avg time between rec tnx',
            'erc20_avg_time_between_rec_2_tnx': ' ERC20 avg time between rec 2 tnx',
            'erc20_avg_time_between_contract_tnx': ' ERC20 avg time between contract tnx',
            'erc20_min_val_rec': ' ERC20 min val rec',
            'erc20_max_val_rec': ' ERC20 max val rec',
            'erc20_avg_val_rec': ' ERC20 avg val rec',
            'erc20_min_val_sent': ' ERC20 min val sent',
            'erc20_max_val_sent': ' ERC20 max val sent',
            'erc20_avg_val_sent': ' ERC20 avg val sent',
            'erc20_min_val_sent_contract': ' ERC20 min val sent contract',
            'erc20_max_val_sent_contract': ' ERC20 max val sent contract',
            'erc20_avg_val_sent_contract': ' ERC20 avg val sent contract',
            'erc20_uniq_sent_token_name': ' ERC20 uniq sent token name',
            'erc20_uniq_rec_token_name': ' ERC20 uniq rec token name',
        }
        
        teacher_xb_df = pd.DataFrame()
        for teacher_feat, xb_col in teacher_xb_col_map.items():
            # Try exact match and stripped match
            for actual_col in df_xb.columns:
                if actual_col.strip() == xb_col.strip():
                    teacher_xb_df[teacher_feat] = pd.to_numeric(df_xb[actual_col], errors='coerce').fillna(0)
                    break
        
        prob_teacher_xb = predict_teacher(teacher_xb_df)
        result_teacher_xb = evaluate_and_report(
            'XBlock (TEACHER — in-distribution)', y_xb, prob_teacher_xb,
            threshold=0.5
        )
        ALL_RESULTS.append(result_teacher_xb)
        
        # Teacher + Platt on XBlock
        print('\n  ── Teacher + Platt on XBlock ──')
        prob_teacher_xb_recal = recalibrate_platt(
            y_xb[cal_xb], prob_teacher_xb[cal_xb],
            prob_teacher_xb[eval_xb]
        )
        result_teacher_xb_recal = evaluate_and_report(
            'XBlock (Teacher+Platt)', y_xb[eval_xb], prob_teacher_xb_recal,
            threshold=0.5
        )
        ALL_RESULTS.append(result_teacher_xb_recal)
        
        print(f'\n  ⏱️  XBlock evaluation completed in {time.time()-t0:.1f}s')
else:
    print('⚠️  XBlock dataset not found.')


# %% [markdown]
# ---
# ## Dataset 3: Forta Network — Live Security Bot Labels

# %% Cell 6: Forta Network (CSV-based, Etherscan-fetched features)
print('\n📊 Forta Network — Ground-Truth Labeled Addresses...')
t0 = time.time()

# Load pre-evaluated Forta results from evaluate_forta_addresses.py
FORTA_DIR = Path(r'c:\amttp\data\external_validation\forta')
FORTA_RESULTS = FORTA_DIR / 'forta_evaluation_results.json'
FORTA_CACHE = FORTA_DIR / 'forta_etherscan_txs.parquet'

if FORTA_RESULTS.exists():
    with open(FORTA_RESULTS) as f:
        forta_eval = json.load(f)
    
    print(f'  Source: Forta Network labelled-datasets (GitHub)')
    print(f'  7,891 unique addresses: Etherscan banned + phishing + malicious SCs')
    print(f'  Evaluated: {forta_eval["n_malicious"]} malicious + {forta_eval["n_normal"]} normal (exchanges)')
    
    for model_key in ['student_xgb', 'student_lgb', 'teacher']:
        r = forta_eval.get(model_key, {})
        if r:
            print(f'\n  {r["name"]:40s}  ROC-AUC={r["roc_auc"]:.4f}  PR-AUC={r["pr_auc"]:.4f}  Best-F1={r["best_f1"]:.4f}')
    
    # Load cached data for detection rate analysis
    if FORTA_CACHE.exists():
        df_forta_cache = pd.read_parquet(FORTA_CACHE)
        v2_feats = [json.loads(row['v2_features']) for _, row in df_forta_cache.iterrows()]
        
        # Build feature matrix and predict
        n_f = len(v2_feats)
        X_f = np.zeros((n_f, len(RAW_FEATURES)), dtype=np.float32)
        for i, fd in enumerate(v2_feats):
            for j, fname in enumerate(RAW_FEATURES):
                X_f[i, j] = float(fd.get(fname, 0))
        
        prob_f = predict_fraud_v2(X_f, use_meta=False)
        
        print(f'\n  Detection rates (all-malicious, {n_f} addresses):')
        print(f'  {"─"*60}')
        for thr_name, thr in [('0.50', 0.5), ('V2 optimal', OPTIMAL_THRESHOLD), ('0.30', 0.3), ('0.10', 0.1), ('0.05', 0.05)]:
            caught = int((prob_f >= thr).sum())
            missed = n_f - caught
            det = caught / n_f
            print(f'    @{thr_name:>12} ({thr:.4f}):  Caught {caught:>4} / {n_f} ({det:>6.1%})  |  Missed {missed:>4}')
        
        print(f'\n  Mean fraud probability: {prob_f.mean():.4f}')
        print(f'  Median fraud probability: {np.median(prob_f):.4f}')
        
        # ML3 on Forta
        if ml3_model is not None:
            prob_f_ml3 = predict_fraud_v2_ml3(X_f, use_full_pipeline=True)
            print(f'\n  ML3 (LR+Q-Learning NN) on Forta ({n_f} addresses):')
            print(f'  Mean fraud probability (ML3): {prob_f_ml3.mean():.4f}')
            print(f'  Median fraud probability (ML3): {np.median(prob_f_ml3):.4f}')
            for thr_name, thr in [('0.50', 0.5), ('V2 optimal', OPTIMAL_THRESHOLD), ('0.30', 0.3), ('0.10', 0.1)]:
                caught = int((prob_f_ml3 >= thr).sum())
                det = caught / n_f
                print(f'    @{thr_name:>12} ({thr:.4f}):  Caught {caught:>4} / {n_f} ({det:>6.1%})')
    
    # Interpretation
    print(f'\n  ── INTERPRETATION ──')
    print(f'  ROC-AUC < 0.5 = model assigns HIGHER scores to normal addresses (exchanges)')
    print(f'  This reveals a semantic mismatch:')
    print(f'    • Model detects behavioral fraud patterns (high volume, gas anomalies)')
    print(f'    • Forta labels are intelligence-based (known exploits, reported scams)')
    print(f'    • Many scam wallets have "normal-looking" on-chain patterns')
    print(f'    • Exchange hot wallets have extreme behavioral features → higher anomaly score')
    print(f'  24/93 features missing (mixer/sanction/exchange flags + all receiver-side)')
    print(f'  Severe distribution shift: training gas_price=1.1 vs Forta=42.4 gwei')
    
    ALL_RESULTS.append({
        'name': 'Forta (268 malicious + 21 normal)',
        'n_samples': forta_eval['n_malicious'] + forta_eval['n_normal'],
        'roc_auc': forta_eval['student_xgb']['roc_auc'],
        'pr_auc': forta_eval['student_xgb']['pr_auc'],
        'best_f1': forta_eval['student_xgb']['best_f1'],
        'note': 'Semantic mismatch: behavioral vs. intelligence-based labels',
    })
    ALL_RESULTS.append({
        'name': 'Forta (TEACHER)',
        'n_samples': forta_eval['n_malicious'] + forta_eval['n_normal'],
        'roc_auc': forta_eval['teacher']['roc_auc'],
        'pr_auc': forta_eval['teacher']['pr_auc'],
        'best_f1': forta_eval['teacher']['best_f1'],
        'note': 'Teacher also fails → not a distillation issue',
    })
else:
    print('  ⚠️  Run evaluate_forta_addresses.py first.')
    print('  Script fetches Etherscan TX data for 7,891 Forta-labeled addresses.')
    ALL_RESULTS.append({'name': 'Forta Network', 'n_samples': 0, 'note': 'Not evaluated yet'})

print(f'  ⏱️  {time.time()-t0:.1f}s')


# %% [markdown]
# ---
# ## Dataset 4: OFAC SDN — U.S. Treasury Sanctioned Addresses

# %% Cell 7: OFAC SDN
print('\n📊 Checking OFAC SDN Sanctioned Addresses...')
t0 = time.time()

OFAC_SANCTIONED = [
    # Tornado Cash
    '0xd90e2f925da726b50c4ed8d0fb90ad053324f31b',
    '0xd96f2b1c14db8458374d9aca76e26c3d18364307',
    '0x4736dcf1b7a3d580672cce6e7c65cd5cc9cfbf68',
    '0xdd4c48c0b24039969fc16d1cdf626eab821d3384',
    '0xd4b88df4d29f5cedd6857912842cff3b20c8cfa3',
    '0x910cb14c8ae0a3a15a26dcc6d66c39458b878e79',
    '0xa160cdab225685da1d56aa342ad8841c3b53f291',
    '0xfd8610d20aa15b7b2e3be39b396a1bc3516c7144',
    '0xf60dd140cff0706bae9cd734ac3683696c17a0b3',
    '0x22aaa7720ddd5388a3c0a3333430953c68f1849b',
    '0xba214c1c1928a32bffe790263e38b4af9bfcd659',
    '0xb1c8094b234dce6e03f10a5b673c1d8c69739a00',
    '0x527653ea119f3e6a1f5bd18fbf4714081d7b31ce',
    '0x58e8dcc13be9780fc42e8723d8ead4cf46943df2',
    '0xd691f27f38b395864ea86cfc7253969b409c362d',
    '0xaeaac358560e11f52454d997aaff2c5731b6f8a6',
    '0x1356c899d8c9467c7f71c195612f8a395abf2f0a',
    '0xa7e5d5a720f06526557c513402f2e6b5fa20b008',
    '0x12d66f87a04a9e220743712ce6d9bb1b5616b8fc',
    '0x47ce0c6ed5b0ce3d3a51fdb1c52dc66a7c3c2936',
    '0x23773e65ed146a459791799d01336db287f25334',
    '0xd21be7248e0197ee08e0c20d4a398dad3e6e232c',
    '0x610b717796ad172b316836ac95a2ffad065ceab4',
    '0x178169b423a011fff22b9e3f3abea13414ddd0f1',
    '0xbb93e510bbcd0b7beb5a853875f9ec60275cf498',
    # Lazarus Group
    '0x098b716b8aaf21512996dc57eb0615e2383e2f96',
    '0xa0e1c89ef1a489c9c7de96311ed5ce5d32c20e4b',
    '0x3cffd56b47b7b41c56258d9c7731abadc360e460',
    '0x53b6936513e738f44fb50d2b9476730c0ab3bfc1',
    # Blender.io
    '0x8589427373d6d84e98730d7795d8f6f8731fda16',
    '0x722122df12d4e14e13ac3b6895a86e84145b6967',
    '0xca0840578f57fe216fab5aab07c7379c83067836',
]

# Try live OFAC SDN list
import re
try:
    print('  Fetching latest OFAC SDN list...')
    r = requests.get('https://www.treasury.gov/ofac/downloads/sdn.csv', timeout=30)
    if r.status_code == 200:
        additional = set(addr.lower() for addr in re.findall(r'0x[a-fA-F0-9]{40}', r.text))
        existing = set(a.lower() for a in OFAC_SANCTIONED)
        new_addrs = additional - existing
        OFAC_SANCTIONED.extend(list(new_addrs))
        if new_addrs:
            print(f'  +{len(new_addrs)} from live SDN list')
except Exception as e:
    print(f'  SDN download failed: {e}')

print(f'  Total sanctioned addresses: {len(OFAC_SANCTIONED)}')

try:
    df_our = pd.read_parquet(r'c:\amttp\processed\eth_transactions_full_labeled.parquet')
    ofac_set = set(a.lower() for a in OFAC_SANCTIONED)
    our_addresses = set(df_our['from_address'].str.lower().unique())
    overlap = ofac_set & our_addresses
    
    print(f'  OFAC: {len(ofac_set)} | Our data: {len(our_addresses):,} | Overlap: {len(overlap)}')
    
    if len(overlap) > 0:
        df_ofac = df_our[df_our['from_address'].str.lower().isin(overlap)].copy()
        X_ofac = build_v2_feature_matrix(df_ofac)
        prob_ofac = predict_fraud_v2(X_ofac, use_meta=False)
        
        detected = (prob_ofac >= OPTIMAL_THRESHOLD).sum()
        print(f'\n  Sanctioned tx: {len(df_ofac):,}')
        print(f'  Detected: {detected:,} / {len(prob_ofac):,} ({detected/len(prob_ofac):.2%})')
        print(f'  Mean fraud prob: {prob_ofac.mean():.4f}')
        print(f'  Our labels: {df_ofac["fraud"].mean():.2%} fraud')
        
        ALL_RESULTS.append({
            'name': 'OFAC SDN', 'n_samples': len(df_ofac),
            'detection_rate': round(detected / len(prob_ofac), 4),
            'mean_prob': round(float(prob_ofac.mean()), 4),
        })
    else:
        print('  No overlap with our 30-day dataset')
        ALL_RESULTS.append({'name': 'OFAC SDN', 'n_samples': 0, 'note': 'No overlap'})
except FileNotFoundError:
    print('  ⚠️  Training dataset not found.')

print(f'  ⏱️  {time.time()-t0:.1f}s')


# %% [markdown]
# ---
# ## Dataset 5: Chainabuse Community Reports

# %% Cell 8: Chainabuse
print('\n📊 Checking Chainabuse community reports...')
t0 = time.time()

CHAINABUSE_API = 'https://www.chainabuse.com/api/graphql-proxy'
CHAINABUSE_KNOWN = [
    '0x7bd9902e5d04e4e0a628edcb8cdec6dbc5a9f115',
    '0x4b6aab87c338fa4e66bd7e42c27ca43d440bc829',
    '0xd882cfc20f52f2599d84b8e8d58c7fb62cfe344b',
]

chainabuse_addrs = set(a.lower() for a in CHAINABUSE_KNOWN)
try:
    query = {'query': '{ getReports(input: { chain: "ethereum", limit: 100 }) { reports { address category } } }'}
    r = requests.post(CHAINABUSE_API, json=query, timeout=15, headers={'Content-Type': 'application/json'})
    if r.status_code == 200:
        reports = r.json().get('data', {}).get('getReports', {}).get('reports', [])
        for report in reports:
            addr = report.get('address', '')
            if addr.startswith('0x') and len(addr) == 42:
                chainabuse_addrs.add(addr.lower())
        print(f'  Chainabuse API: {len(chainabuse_addrs)} addresses')
    else:
        print(f'  API returned {r.status_code}')
except Exception as e:
    print(f'  API error: {e}')

print(f'  Total Chainabuse addresses: {len(chainabuse_addrs)}')

if chainabuse_addrs:
    try:
        df_our = pd.read_parquet(r'c:\amttp\processed\eth_transactions_full_labeled.parquet')
        overlap = chainabuse_addrs & set(df_our['from_address'].str.lower().unique())
        print(f'  Overlap: {len(overlap)}')
        
        if len(overlap) > 0:
            df_ca = df_our[df_our['from_address'].str.lower().isin(overlap)].copy()
            X_ca = build_v2_feature_matrix(df_ca)
            prob_ca = predict_fraud_v2(X_ca, use_meta=False)
            
            detected = (prob_ca >= OPTIMAL_THRESHOLD).sum()
            print(f'  Transactions: {len(df_ca):,} | Detected: {detected:,} ({detected/len(df_ca):.2%})')
            ALL_RESULTS.append({
                'name': 'Chainabuse', 'n_samples': len(df_ca),
                'detection_rate': round(detected / len(df_ca), 4),
                'mean_prob': round(float(prob_ca.mean()), 4),
            })
        else:
            ALL_RESULTS.append({'name': 'Chainabuse', 'n_samples': 0, 'note': 'No overlap'})
    except FileNotFoundError:
        print('  ⚠️  Training dataset not found.')

print(f'  ⏱️  {time.time()-t0:.1f}s')


# %% [markdown]
# ---
# ## Summary Report

# %% Cell 9: Final Summary
print('\n' + '=' * 90)
print('           CROSS-VALIDATION SUMMARY — AMTTP V2 MODEL')
print('           β-VAE → GATv2 → GraphSAGE → PCA → Optuna-LGBM/XGB → Meta-LR')
print('           + TEACHER (Hope_machine XGB — 99.7% BitcoinHeist + 0.3% ETH)')
print('=' * 90)

print(f'\nDate: {datetime.now().isoformat()}')
print(f'Student: V2 Pipeline (amttp_models_20260213_213346)')
print(f'  Raw features: {len(RAW_FEATURES)} | Boost: {len(BOOST_FEATURES)} | Meta: {len(META_FEATURES)}')
print(f'  Threshold: {OPTIMAL_THRESHOLD:.4f}')
print(f'  Training: 625K ETH samples (pseudo-labeled by teacher hybrid pipeline)')
print(f'Teacher: Hope_machine XGB (xgb.json)')
print(f'  Features: {len(TEACHER_FEATURES)} ({len(TEACHER_CORE)} core + {len(TEACHER_FEATURES)-len(TEACHER_CORE)} missingness)')
print(f'  Training: ~2.9M samples (99.7% BitcoinHeist + 0.3% Kaggle ETH)')
print(f'\nKnowledge Path: Bitcoin → Teacher → pseudo-labels → Student')
print(f'  Teacher AUC: 0.6448 | Student AUC: 0.9999 (on teacher-labeled data)')

# ── Table 1: Detection metrics at PRODUCTION threshold ──
print(f'\n  TABLE 1: DETECTION AT PRODUCTION THRESHOLD')
print(f'  (The threshold the model actually uses in production)')
print(f'  {"─"*140}')
print(f'  {"Dataset":<42} {"Fraud":>6} {"Caught":>7} {"Missed":>7} {"Recall":>8} {"Normal":>7} {"FalseAlm":>8} {"FP Rate":>8} {"ROC-AUC":>10} {"Threshold":>10}')
print(f'  {"─"*140}')

t1_fraud = t1_caught = t1_missed = 0
for r in ALL_RESULTS:
    name = r.get('name', '?')
    n_pos = r.get('n_pos', None)
    n_neg = r.get('n_neg', None)
    roc = r.get('roc_auc', '')
    caught_p = r.get('caught_production', None)
    fa_p = r.get('fa_production', None)
    thr_p = r.get('production_threshold', '')
    note = r.get('note', r.get('error', ''))
    
    roc_str = f'{roc:.4f}' if isinstance(roc, float) else str(roc)
    thr_str = f'{thr_p:.4f}' if isinstance(thr_p, float) else str(thr_p)
    
    if isinstance(n_pos, int) and isinstance(caught_p, int):
        missed_p = n_pos - caught_p
        recall_p = caught_p / n_pos if n_pos > 0 else 0
        fp_rate = fa_p / n_neg if isinstance(fa_p, int) and n_neg and n_neg > 0 else 0
        print(f'  {name:<42} {n_pos:>6,} {caught_p:>7,} {missed_p:>7,} {recall_p:>7.1%} {n_neg:>7,} {fa_p:>8,} {fp_rate:>7.1%} {roc_str:>10} {thr_str:>10}')
        t1_fraud += n_pos; t1_caught += caught_p; t1_missed += missed_p
    else:
        n_str = f'{n_pos}' if n_pos is not None else '-'
        print(f'  {name:<42} {n_str:>6} {"-":>7} {"-":>7} {"-":>8} {"-":>7} {"-":>8} {"-":>8} {roc_str:>10} {thr_str:>10}  {note}')

print(f'  {"─"*140}')
t1_recall = t1_caught / t1_fraud if t1_fraud > 0 else 0
print(f'  {"TOTAL":.<42} {t1_fraud:>6,} {t1_caught:>7,} {t1_missed:>7,} {t1_recall:>7.1%}')
print()

# ── Table 2: Detection at OPTIMAL F1 threshold ──
print(f'\n  TABLE 2: DETECTION AT OPTIMAL F1 THRESHOLD')
print(f'  (Best trade-off between catching fraud and avoiding false alarms)')
print(f'  {"─"*140}')
print(f'  {"Dataset":<42} {"Fraud":>6} {"Caught":>7} {"Missed":>7} {"Recall":>8} {"Normal":>7} {"FalseAlm":>8} {"FP Rate":>8} {"Best F1":>10} {"Threshold":>10}')
print(f'  {"─"*140}')

t2_fraud = t2_caught = t2_missed = 0
for r in ALL_RESULTS:
    name = r.get('name', '?')
    n_pos = r.get('n_pos', None)
    n_neg = r.get('n_neg', None)
    best_f1 = r.get('f1_optimal', '')
    caught_o = r.get('caught_optimal', None)
    fa_o = r.get('fa_optimal', None)
    thr_o = r.get('optimal_threshold', '')
    note = r.get('note', r.get('error', ''))
    
    f1_str = f'{best_f1:.4f}' if isinstance(best_f1, float) else str(best_f1)
    thr_str = f'{thr_o:.4f}' if isinstance(thr_o, float) else str(thr_o)
    
    if isinstance(n_pos, int) and isinstance(caught_o, int):
        missed_o = n_pos - caught_o
        recall_o = caught_o / n_pos if n_pos > 0 else 0
        fp_rate = fa_o / n_neg if isinstance(fa_o, int) and n_neg and n_neg > 0 else 0
        print(f'  {name:<42} {n_pos:>6,} {caught_o:>7,} {missed_o:>7,} {recall_o:>7.1%} {n_neg:>7,} {fa_o:>8,} {fp_rate:>7.1%} {f1_str:>10} {thr_str:>10}')
        t2_fraud += n_pos; t2_caught += caught_o; t2_missed += missed_o
    else:
        n_str = f'{n_pos}' if n_pos is not None else '-'
        print(f'  {name:<42} {n_str:>6} {"-":>7} {"-":>7} {"-":>8} {"-":>7} {"-":>8} {"-":>8} {f1_str:>10} {thr_str:>10}  {note}')

print(f'  {"─"*140}')
t2_recall = t2_caught / t2_fraud if t2_fraud > 0 else 0
print(f'  {"TOTAL":.<42} {t2_fraud:>6,} {t2_caught:>7,} {t2_missed:>7,} {t2_recall:>7.1%}')
print()

print(f'\n{"="*100}')
print('INTERPRETATION')
print(f'{"="*100}')
print('''
  KNOWLEDGE DISTILLATION ANALYSIS:
    Teacher was trained on 99.7% Bitcoin (BitcoinHeist ransomware).
    Student never saw Bitcoin data directly — it trained on Ethereum data
    pseudo-labeled by the teacher hybrid pipeline (0.4*XGB + 0.3*rules + 0.3*graph).
    
    Comparing Teacher vs Student on Elliptic (Bitcoin) shows how much
    Bitcoin fraud knowledge transferred through distillation.
    
    For XBlock (ETH Kaggle Phishing): Teacher trained on the SAME source
    distribution (0.3% of its data). This is quasi in-distribution for the teacher.

  ELLIPTIC (Bitcoin, 46K labeled transactions):
    ROC-AUC > 0.55 = better than random (meaningful cross-chain signal)
    ROC-AUC > 0.65 = meaningful cross-domain fraud signal
    ROC-AUC > 0.75 = strong generalisation / knowledge transfer
    Note: Anonymised features require approximate positional mapping

  XBLOCK (Ethereum, 9.8K addresses):
    ⚠️ ADDRESS-level data scored by a TRANSACTION-level model
    Student mapping: 22/93 features | Teacher mapping: 40+/56 features
    ROC-AUC < 0.5 on student = inverse ranking (address ≠ transaction semantics)
    Teacher should outperform since it was trained on address-level data

  FORTA (7,891 labeled malicious addresses — Etherscan TX-fetched):
    ROC-AUC < 0.5 for both student AND teacher.
    This is NOT a model failure — it reveals a SEMANTIC MISMATCH:
    
    1. Our model detects behavioural fraud patterns (high volume, gas anomalies,
       rapid in-out flow, counterparty patterns)
    2. Forta labels are intelligence-based (known exploits, reported scams,
       Etherscan-flagged addresses)
    3. Many scammer wallets have "normal-looking" on-chain behaviour patterns
    4. Exchange hot wallets (our negatives) have extreme features → higher 
       anomaly scores than actual scammers
    
    Additional handicaps:
    - 24/93 features missing (mixer/sanctioned/exchange flags + receiver-side)
    - Severe temporal distribution shift (training gas=1.1 vs Forta=42.4 gwei)
    - Training addresses had 2,833 avg sent txs vs Forta's 40
    
    Key insight: The teacher also fails (ROC-AUC=0.21) → this is NOT a 
    distillation artefact. Both models learn statistical patterns from their
    training window, not generalised "fraud address classification".

  OFAC / Chainabuse:
    Detection rate matters (all-positive class)
    Limited by overlap with our 30-day training window
''')

# Save results
results_file = DATA_DIR / 'cross_validation_v2_results.json'
with open(results_file, 'w') as f:
    json.dump({
        'date': datetime.now().isoformat(),
        'model': 'V2-pipeline-20260213',
        'model_dir': str(MODELS_DIR),
        'threshold': OPTIMAL_THRESHOLD,
        'n_raw_features': len(RAW_FEATURES),
        'n_boost_features': len(BOOST_FEATURES),
        'training_performance': metadata['performance'],
        'results': ALL_RESULTS,
    }, f, indent=2, default=str)
print(f'\n📁 Results saved to: {results_file}')
