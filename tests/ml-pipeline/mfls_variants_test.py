"""
MFLS Variant Strategies Test
==============================
Tests whether alternative MFLS combination rules improve accuracy
over the current approaches (Base, MFLS linear, Signed LR).

Variants tested:
  V1. Capped-weight MFLS  (w_A ≤ 0.25, w_T ≤ 0.30)
  V2. Multiplicative       ∏(S_i + ε)
  V3. Min-of-4             min(C, G, A, T)
  V4. 2-of-4 voting        flag if ≥2 components > θ
  V5. 3-of-4 voting        flag if ≥3 components > θ
  V6. Hybrid: Base + Signed LR max-ensemble
  V7. Hybrid: Base score + MFLS correction with capped weights
  V8. Dense-core veto      ignore if Mahalanobis to centroid < median

For each dataset, we compare all variants against:
  - Base model (best of 6 models per dataset)
  - +MFLS (original linear correction)
  - +Signed LR (direction-aware LR on 4 components)
"""

import numpy as np, polars as pl, scipy.io as sio, json, time, warnings, joblib, sys
import xgboost as xgb, lightgbm as lgb
from pathlib import Path

# Fix Windows encoding
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass
from sklearn.metrics import roc_auc_score, mutual_info_score
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.neural_network import MLPClassifier
from sklearn.model_selection import StratifiedShuffleSplit, StratifiedKFold
from sklearn.preprocessing import StandardScaler
warnings.filterwarnings('ignore')

# ── Paths ──
ARTIFACTS = Path(r'C:\Users\Administrator\Downloads\complete_amttp_student_artifacts\amttp_models_20260213_213346')
DATA_DIR  = Path(r'c:\amttp\data\external_validation')

# ── Load pre-trained models ──
print("Loading pre-trained AMTTP models...")
t0 = time.time()
preprocessors = joblib.load(ARTIFACTS / 'preprocessors.joblib')
FEATURES_93  = list(preprocessors['feature_names'])
with open(ARTIFACTS / 'feature_config.json') as f:
    feat_cfg = json.load(f)
FEATURES_160 = feat_cfg['boost_features']
scaler   = preprocessors['robust_scaler']
log_mask = preprocessors['log_transform_mask']

xgb_93 = xgb.Booster()
xgb_93.load_model(str(ARTIFACTS / 'xgboost_fraud.ubj'))
xgb_160 = xgb.XGBClassifier()
xgb_160.load_model(str(ARTIFACTS / 'xgboost_fraud.ubj'))
lgb_160 = lgb.Booster(model_file=str(ARTIFACTS / 'lightgbm_fraud.txt'))
print(f"Models loaded in {time.time()-t0:.1f}s")

IDX_SENT = FEATURES_93.index('sender_total_sent') if 'sender_total_sent' in FEATURES_93 else 7
IDX_RECV = FEATURES_93.index('receiver_total_received') if 'receiver_total_received' in FEATURES_93 else 60

# ══════════════════════════════════════════════════════
# PREPROCESSING + PREDICTION  (same as comprehensive test)
# ══════════════════════════════════════════════════════

def preprocess_93(X):
    X2 = X.copy().astype(np.float32)
    X2 = np.nan_to_num(X2, nan=0.0, posinf=0.0, neginf=0.0)
    X2[:, log_mask] = np.log1p(np.clip(X2[:, log_mask], 0, None))
    X2 = scaler.transform(X2)
    return np.clip(X2, -5, 5)

def predict_xgb93(X):
    Xp = preprocess_93(X)
    return xgb_93.predict(xgb.DMatrix(Xp, feature_names=FEATURES_93))

def predict_xgb160(X):
    Xp = preprocess_93(X)
    X160 = np.zeros((Xp.shape[0], 160), dtype=np.float32)
    X160[:, :93] = Xp
    return xgb_160.predict_proba(X160)[:, 1]

def predict_lgb160(X):
    Xp = preprocess_93(X)
    X160 = np.zeros((Xp.shape[0], 160), dtype=np.float32)
    X160[:, :93] = Xp
    return lgb_160.predict(X160)

# ══════════════════════════════════════════════════════
# BSDT CORE
# ══════════════════════════════════════════════════════

def camouflage(X, mu, dmax):
    return 1.0 - np.clip(np.linalg.norm(X - mu, axis=1) / dmax, 0, 1)

def feature_gap(X):
    return (np.abs(X) < 1e-8).sum(axis=1).astype(np.float64) / X.shape[1]

def activity_anomaly(X, mu_c, sig_c):
    tx = np.abs(X[:, IDX_SENT]) + np.abs(X[:, IDX_RECV]) + 1e-8
    z = (np.log1p(tx) - mu_c) / max(sig_c, 1e-8)
    return 1.0 / (1.0 + np.exp(-z))

def temporal_novelty(X, rm, rv):
    d = X - rm
    m = np.sum(d*d / rv, axis=1) / X.shape[1]
    return 1.0 / (1.0 + np.exp(-0.5*(m - 2.0)))

def ref_stats(X, y):
    n = X[y==0]; f = X[y==1]
    mu = n.mean(0)
    d  = max(np.percentile(np.linalg.norm(X - mu, axis=1), 99), 1e-8)
    rm = f.mean(0); rv = f.var(0) + 1e-8
    tx = np.abs(f[:, IDX_SENT]) + np.abs(f[:, IDX_RECV]) + 1e-8
    return mu, d, rm, rv, np.log1p(tx).mean(), max(np.log1p(tx).std(), 1e-8)

def get_components(X, stats):
    c = np.column_stack([
        camouflage(X, stats[0], stats[1]),
        feature_gap(X),
        activity_anomaly(X, stats[4], stats[5]),
        temporal_novelty(X, stats[2], stats[3])
    ])
    return np.nan_to_num(c, nan=0.0)

def mi_weights(comp, y, nb=20):
    mi = np.zeros(4)
    for i in range(4):
        bins = np.digitize(comp[:,i], np.linspace(comp[:,i].min(), comp[:,i].max()+1e-8, nb))
        mi[i] = mutual_info_score(y, bins)
    s = mi.sum()
    return mi / s if s > 1e-10 else np.ones(4) / 4

# ══════════════════════════════════════════════════════
# METRICS
# ══════════════════════════════════════════════════════

PT = np.arange(0.05, 0.95, 0.02)

def best_f1_at_thresholds(y_true, scores, thresholds=PT):
    y = y_true.astype(bool)
    preds = scores[np.newaxis, :] >= thresholds[:, np.newaxis]
    tp = (preds & y).sum(1).astype(float)
    fp = (preds & ~y).sum(1).astype(float)
    fn = (~preds & y).sum(1).astype(float)
    prec = np.where(tp+fp>0, tp/(tp+fp), 0.0)
    rec  = np.where(tp+fn>0, tp/(tp+fn), 0.0)
    f1   = np.where(prec+rec>0, 2*prec*rec/(prec+rec), 0.0)
    i = np.argmax(f1)
    fa = fp[i] / max(fp[i]+tp[i], 1)
    return {'f1': float(f1[i]), 'rec': float(rec[i]), 'prec': float(prec[i]),
            'tp': int(tp[i]), 'fp': int(fp[i]), 'fa': float(fa),
            'auc': 0.0, 'threshold': float(thresholds[i])}

def eval_scores(y, scores):
    """Evaluate scores → best F1 + AUC + pct metrics."""
    try: auc = float(roc_auc_score(y, scores))
    except: auc = 0.5
    m = best_f1_at_thresholds(y, scores)
    m['auc'] = auc
    n = len(y)
    nf = int(y.sum())
    nl = n - nf
    fn = nf - m['tp']
    tn = nl - m['fp']
    m['pct_missed']  = (fn / max(nf,1)) * 100
    m['pct_fa']      = m['fa'] * 100
    m['pct_correct'] = ((m['tp'] + tn) / max(n,1)) * 100
    return m

# ══════════════════════════════════════════════════════
# CORRECTION METHODS (original + signed LR for reference)
# ══════════════════════════════════════════════════════

LAM = np.arange(0.1, 2.6, 0.2)
TAU = np.array([0.1, 0.2, 0.3, 0.5, 0.7, 0.9])

def apply_original_correction(p, mfls, y):
    best = {'f1': 0.0}
    y_arr = y.astype(bool)
    for lam in LAM:
        for tau in TAU:
            below = (p < tau).astype(np.float64)
            pc = np.clip(p + lam * mfls * (1.0 - p) * below, 0, 1)
            preds = pc[np.newaxis, :] >= PT[:, np.newaxis]
            tp = (preds & y_arr).sum(1).astype(float)
            fp = (preds & ~y_arr).sum(1).astype(float)
            fn = (~preds & y_arr).sum(1).astype(float)
            prec = np.where(tp+fp>0, tp/(tp+fp), 0.0)
            rec  = np.where(tp+fn>0, tp/(tp+fn), 0.0)
            f1   = np.where(prec+rec>0, 2*prec*rec/(prec+rec), 0.0)
            i = np.argmax(f1)
            if f1[i] > best['f1']:
                fa_v = fp[i] / max(fp[i]+tp[i], 1)
                best = {'f1': float(f1[i]), 'rec': float(rec[i]), 'prec': float(prec[i]),
                        'tp': int(tp[i]), 'fp': int(fp[i]), 'fa': float(fa_v)}
    return best

def apply_signed_lr(p, comp, y):
    lr = LogisticRegression(random_state=42, max_iter=1000, class_weight='balanced')
    lr.fit(comp, y)
    p_lr = lr.predict_proba(comp)[:, 1]
    m = best_f1_at_thresholds(y, p_lr)
    try: m['auc'] = float(roc_auc_score(y, p_lr))
    except: m['auc'] = 0.5
    return m

# ══════════════════════════════════════════════════════
# NEW VARIANT STRATEGIES
# ══════════════════════════════════════════════════════

def variant_capped_mfls(comp, y):
    """V1: MI weights with caps: w_A ≤ 0.25, w_T ≤ 0.30."""
    w = mi_weights(comp, y)
    w[2] = min(w[2], 0.25)  # A
    w[3] = min(w[3], 0.30)  # T
    s = w.sum()
    w = w / s if s > 1e-10 else np.ones(4) / 4
    return comp @ w

def variant_multiplicative(comp):
    """V2: Product-based ∏(S_i + ε)."""
    eps = 0.01
    return np.prod(comp + eps, axis=1)

def variant_min_of_4(comp):
    """V3: min(C, G, A, T) — only flags when ALL components signal."""
    return np.min(comp, axis=1)

def variant_k_of_4_voting(comp, k, theta):
    """V4/V5: Flag if ≥ k components exceed theta."""
    above = (comp > theta).sum(axis=1)
    return (above >= k).astype(float) * np.mean(comp, axis=1)

def variant_hybrid_max(p_base, p_lr):
    """V6: max(base, signed_lr) — take higher fraud score."""
    return np.maximum(p_base, p_lr)

def variant_capped_correction(p, comp, y):
    """V7: MFLS correction with capped weights (less aggressive)."""
    mfls_capped = variant_capped_mfls(comp, y)
    best = {'f1': 0.0}
    y_arr = y.astype(bool)
    for lam in [0.1, 0.3, 0.5, 0.8, 1.0]:
        for tau in [0.2, 0.3, 0.5]:
            below = (p < tau).astype(np.float64)
            pc = np.clip(p + lam * mfls_capped * (1.0 - p) * below, 0, 1)
            preds = pc[np.newaxis, :] >= PT[:, np.newaxis]
            tp = (preds & y_arr).sum(1).astype(float)
            fp = (preds & ~y_arr).sum(1).astype(float)
            fn = (~preds & y_arr).sum(1).astype(float)
            prec = np.where(tp+fp>0, tp/(tp+fp), 0.0)
            rec  = np.where(tp+fn>0, tp/(tp+fn), 0.0)
            f1   = np.where(prec+rec>0, 2*prec*rec/(prec+rec), 0.0)
            i = np.argmax(f1)
            if f1[i] > best['f1']:
                fa_v = fp[i] / max(fp[i]+tp[i], 1)
                best = {'f1': float(f1[i]), 'rec': float(rec[i]), 'prec': float(prec[i]),
                        'tp': int(tp[i]), 'fp': int(fp[i]), 'fa': float(fa_v)}
    return best

def variant_dense_core_veto(comp, X, stats):
    """V8: Suppress scores for samples in the dense core of data."""
    mu_all = X.mean(axis=0)
    var_all = X.var(axis=0) + 1e-8
    mahal = np.sqrt(np.sum((X - mu_all)**2 / var_all, axis=1))
    median_mahal = np.median(mahal)
    # Suppress: if in dense core (mahal < median), scale score down
    w = mi_weights(comp, np.zeros(len(comp)))  # unsupervised — equal weights
    w = np.ones(4) / 4
    mfls = comp @ w
    suppress = np.where(mahal < median_mahal, 0.1, 1.0)
    return mfls * suppress

def variant_signed_lr_l2(comp, y, C_val=0.1):
    """V9: Signed LR with stronger regularisation (C=0.1)."""
    lr = LogisticRegression(random_state=42, max_iter=1000, class_weight='balanced', C=C_val)
    lr.fit(comp, y)
    return lr.predict_proba(comp)[:, 1]

def variant_signed_lr_plus_base(p_base, comp, y):
    """V10: LR on [base_score, C, G, A, T] — 5 features."""
    X5 = np.column_stack([p_base, comp])
    lr = LogisticRegression(random_state=42, max_iter=1000, class_weight='balanced')
    lr.fit(X5, y)
    return lr.predict_proba(X5)[:, 1]


# ── SMOOTH CORRECTION VARIANTS (electronics-inspired) ──

def _softplus(x):
    """Numerically stable softplus: log(1 + exp(x))."""
    return np.where(x > 20, x, np.log1p(np.exp(x)))

def _best_smooth_p(p, mfls):
    """Compute best smooth-corrected score across a param grid.
    Returns the smooth p* for a fixed param set (no label peeking).
    Uses σ=0.5, k=15, τ=0.5, λ=1.2 as sensible defaults."""
    sat = np.tanh(mfls / 0.5)
    gate = 1.0 / (1.0 + np.exp(-15.0 * (0.5 - p)))
    return np.clip(p + 1.2 * sat * (1.0 - p) * gate, 0, 1)

def _best_smooth_p_tuned(p, mfls, y):
    """Compute best smooth-corrected score with grid-tuned params."""
    best_f1 = -1.0
    best_pc = None
    y_arr = y.astype(bool)
    for lam in [0.8, 1.0, 1.2, 1.4]:
        for sigma in [0.35, 0.45, 0.55]:
            sat = np.tanh(mfls / sigma)
            for k_val in [12, 15, 20]:
                for tau in [0.3, 0.5, 0.7]:
                    gate = 1.0 / (1.0 + np.exp(-k_val * (tau - p)))
                    pc = np.clip(p + lam * sat * (1.0 - p) * gate, 0, 1)
                    preds = pc[np.newaxis, :] >= PT[:, np.newaxis]
                    tp = (preds & y_arr).sum(1).astype(float)
                    fp = (preds & ~y_arr).sum(1).astype(float)
                    fn = (~preds & y_arr).sum(1).astype(float)
                    prec_a = np.where(tp+fp>0, tp/(tp+fp), 0.0)
                    rec_a  = np.where(tp+fn>0, tp/(tp+fn), 0.0)
                    f1_a   = np.where(prec_a+rec_a>0, 2*prec_a*rec_a/(prec_a+rec_a), 0.0)
                    mx = f1_a.max()
                    if mx > best_f1:
                        best_f1 = mx
                        best_pc = pc.copy()
    return best_pc if best_pc is not None else p.copy()

def variant_smooth_correction(p, mfls, y):
    """V11: Smooth correction — tanh saturation + sigmoid gate.
    p*(x) = p(x) + λ · tanh(MFLS/σ) · (1-p) · sigmoid(k·(τ - p))
    The tanh acts as a soft-clipping diode (saturates the MFLS boost).
    The sigmoid acts as a transistor gate (smooth on/off around τ).
    (1-p) keeps the correction proportional to remaining uncertainty.
    """
    best_f1 = -1.0
    best_pc = None
    y_arr = y.astype(bool)
    for lam in [0.8, 1.0, 1.2, 1.4]:
        for sigma in [0.35, 0.45, 0.55]:
            sat = np.tanh(mfls / sigma)  # soft diode — caps at ~1
            for k_val in [12, 15, 20]:
                for tau in [0.3, 0.5, 0.7]:
                    gate = 1.0 / (1.0 + np.exp(-k_val * (tau - p)))  # smooth transistor
                    pc = np.clip(p + lam * sat * (1.0 - p) * gate, 0, 1)
                    # Quick F1 scan
                    preds = pc[np.newaxis, :] >= PT[:, np.newaxis]
                    tp = (preds & y_arr).sum(1).astype(float)
                    fp = (preds & ~y_arr).sum(1).astype(float)
                    fn = (~preds & y_arr).sum(1).astype(float)
                    prec_a = np.where(tp+fp>0, tp/(tp+fp), 0.0)
                    rec_a  = np.where(tp+fn>0, tp/(tp+fn), 0.0)
                    f1_a   = np.where(prec_a+rec_a>0, 2*prec_a*rec_a/(prec_a+rec_a), 0.0)
                    mx = f1_a.max()
                    if mx > best_f1:
                        best_f1 = mx
                        best_pc = pc.copy()
    return eval_scores(y, best_pc) if best_pc is not None else eval_scores(y, p)

def variant_ultra_soft(p, mfls, y):
    """V12: Ultra-soft correction — softplus wrapper (no sharp edges at all).
    δ = (1/k) · softplus(k · λ · tanh(MFLS/σ) · (1-p) · (τ - p + 0.1))
    p* = p + δ
    """
    best_f1 = -1.0
    best_pc = None
    y_arr = y.astype(bool)
    for lam in [0.8, 1.0, 1.2, 1.4]:
        for sigma in [0.35, 0.45, 0.55]:
            sat = np.tanh(mfls / sigma)
            for k_val in [10, 15, 20]:
                for tau in [0.3, 0.5, 0.7]:
                    inner = k_val * lam * sat * (1.0 - p) * (tau - p + 0.1)
                    delta = _softplus(inner) / k_val
                    pc = np.clip(p + delta, 0, 1)
                    preds = pc[np.newaxis, :] >= PT[:, np.newaxis]
                    tp = (preds & y_arr).sum(1).astype(float)
                    fp = (preds & ~y_arr).sum(1).astype(float)
                    fn = (~preds & y_arr).sum(1).astype(float)
                    prec_a = np.where(tp+fp>0, tp/(tp+fp), 0.0)
                    rec_a  = np.where(tp+fn>0, tp/(tp+fn), 0.0)
                    f1_a   = np.where(prec_a+rec_a>0, 2*prec_a*rec_a/(prec_a+rec_a), 0.0)
                    mx = f1_a.max()
                    if mx > best_f1:
                        best_f1 = mx
                        best_pc = pc.copy()
    return eval_scores(y, best_pc) if best_pc is not None else eval_scores(y, p)

def variant_power_law(p, mfls, y):
    """V13: Power-law softening — MFLS^α compresses high values.
    p* = p + λ · MFLS^α · (1-p) · 1[p < τ]
    Raising MFLS to α > 1 penalises moderate scores, keeping only strong signals.
    """
    best_f1 = -1.0
    best_pc = None
    y_arr = y.astype(bool)
    for lam in [0.5, 0.8, 1.0, 1.2, 1.5]:
        for alpha in [1.2, 1.4, 1.6, 1.8, 2.0]:
            boosted = np.power(np.clip(mfls, 0, None), alpha)
            for tau in [0.3, 0.5, 0.7]:
                below = (p < tau).astype(np.float64)
                pc = np.clip(p + lam * boosted * (1.0 - p) * below, 0, 1)
                preds = pc[np.newaxis, :] >= PT[:, np.newaxis]
                tp = (preds & y_arr).sum(1).astype(float)
                fp = (preds & ~y_arr).sum(1).astype(float)
                fn = (~preds & y_arr).sum(1).astype(float)
                prec_a = np.where(tp+fp>0, tp/(tp+fp), 0.0)
                rec_a  = np.where(tp+fn>0, tp/(tp+fn), 0.0)
                f1_a   = np.where(prec_a+rec_a>0, 2*prec_a*rec_a/(prec_a+rec_a), 0.0)
                mx = f1_a.max()
                if mx > best_f1:
                    best_f1 = mx
                    best_pc = pc.copy()
    return eval_scores(y, best_pc) if best_pc is not None else eval_scores(y, p)

def variant_smooth_plus_base(p, mfls, comp, y):
    """V14: Best smooth correction + V10-style LR on [smooth_p*, C, G, A, T].
    First applies the smooth correction, then feeds the corrected p* into
    a 5-feature LR alongside the raw BSDT components.
    """
    # Apply smooth correction with reasonable defaults
    best_f1 = -1.0
    best_pc = None
    y_arr = y.astype(bool)
    for lam in [1.0, 1.2]:
        for sigma in [0.45, 0.55]:
            sat = np.tanh(mfls / sigma)
            for k_val in [12, 15]:
                for tau in [0.3, 0.5]:
                    gate = 1.0 / (1.0 + np.exp(-k_val * (tau - p)))
                    pc = np.clip(p + lam * sat * (1.0 - p) * gate, 0, 1)
                    preds = pc[np.newaxis, :] >= PT[:, np.newaxis]
                    tp = (preds & y_arr).sum(1).astype(float)
                    fp = (preds & ~y_arr).sum(1).astype(float)
                    fn = (~preds & y_arr).sum(1).astype(float)
                    prec_a = np.where(tp+fp>0, tp/(tp+fp), 0.0)
                    rec_a  = np.where(tp+fn>0, tp/(tp+fn), 0.0)
                    f1_a   = np.where(prec_a+rec_a>0, 2*prec_a*rec_a/(prec_a+rec_a), 0.0)
                    mx = f1_a.max()
                    if mx > best_f1:
                        best_f1 = mx
                        best_pc = pc.copy()
    if best_pc is None:
        best_pc = p.copy()
    # Now feed smooth-corrected p* + components into LR
    X5 = np.column_stack([best_pc, comp])
    lr = LogisticRegression(random_state=42, max_iter=1000, class_weight='balanced')
    lr.fit(X5, y)
    return lr.predict_proba(X5)[:, 1]


def variant_v10_smooth_features(p, mfls, comp, y):
    """V15: LR on [p_raw, smooth_p*, C, G, A, T] — 6 features.
    Gives the LR access to both the raw base score AND the smooth-corrected
    score, so it can learn the optimal blend of raw vs smoothed prediction
    alongside the BSDT components."""
    p_smooth = _best_smooth_p(p, mfls)  # deterministic defaults, no label leak
    X6 = np.column_stack([p, p_smooth, comp])
    lr = LogisticRegression(random_state=42, max_iter=1000, class_weight='balanced')
    lr.fit(X6, y)
    return lr.predict_proba(X6)[:, 1]

def variant_v10_smooth_post(p, comp, y, mfls):
    """V16: V10 LR output → smooth post-processing.
    Train LR on [p, C, G, A, T] (same as V10), then apply tanh+sigmoid
    smoothing to the LR output to suppress borderline false positives."""
    X5 = np.column_stack([p, comp])
    lr = LogisticRegression(random_state=42, max_iter=1000, class_weight='balanced')
    lr.fit(X5, y)
    p_lr = lr.predict_proba(X5)[:, 1]
    # Post-smooth: apply tanh saturation + sigmoid gate to LR output
    best_f1 = -1.0
    best_pc = None
    y_arr = y.astype(bool)
    for lam in [0.3, 0.5, 0.8, 1.0]:
        for sigma in [0.3, 0.5, 0.7]:
            sat = np.tanh(p_lr / sigma)
            for k_val in [8, 12, 15]:
                for tau in [0.3, 0.5, 0.7]:
                    gate = 1.0 / (1.0 + np.exp(-k_val * (tau - p_lr)))
                    # Blend: keep some of LR output, add smooth-gated portion
                    pc = np.clip(p_lr * (1.0 - lam) + lam * sat * gate, 0, 1)
                    preds = pc[np.newaxis, :] >= PT[:, np.newaxis]
                    tp = (preds & y_arr).sum(1).astype(float)
                    fp = (preds & ~y_arr).sum(1).astype(float)
                    fn = (~preds & y_arr).sum(1).astype(float)
                    prec_a = np.where(tp+fp>0, tp/(tp+fp), 0.0)
                    rec_a  = np.where(tp+fn>0, tp/(tp+fn), 0.0)
                    f1_a   = np.where(prec_a+rec_a>0, 2*prec_a*rec_a/(prec_a+rec_a), 0.0)
                    mx = f1_a.max()
                    if mx > best_f1:
                        best_f1 = mx
                        best_pc = pc.copy()
    return best_pc if best_pc is not None else p_lr

def variant_v10_sat_features(p, mfls, comp, y):
    """V17: LR on [p, tanh(MFLS/σ), C, G, A, T] — 6 features.
    Instead of raw MFLS, the LR gets the tanh-saturated MFLS signal
    as an explicit 'soft diode' feature. This lets the LR see both
    the raw base score and a bounded smooth MFLS signal."""
    sat = np.tanh(mfls / 0.5)  # soft-clipped MFLS
    X6 = np.column_stack([p, sat, comp])
    lr = LogisticRegression(random_state=42, max_iter=1000, class_weight='balanced')
    lr.fit(X6, y)
    return lr.predict_proba(X6)[:, 1]

def variant_v10_smooth_gated(p, mfls, comp, y):
    """V18: LR on [p, C, G, A, T] with smooth-gated output.
    V10's LR output is multiplied by a smooth gate based on the base p,
    suppressing corrections for already-confident predictions.
    p_final = p_lr * [1 - α·sigmoid(k·(p - τ))] + p·α·sigmoid(k·(p - τ))
    This smoothly blends: trust LR when base is uncertain, trust base when confident."""
    X5 = np.column_stack([p, comp])
    lr = LogisticRegression(random_state=42, max_iter=1000, class_weight='balanced')
    lr.fit(X5, y)
    p_lr = lr.predict_proba(X5)[:, 1]
    best_f1 = -1.0
    best_pc = None
    y_arr = y.astype(bool)
    for alpha in [0.3, 0.5, 0.7, 0.9]:
        for k_val in [8, 12, 15]:
            for tau in [0.3, 0.5, 0.7]:
                # When p > τ: trust base more. When p < τ: trust LR more.
                base_trust = alpha / (1.0 + np.exp(-k_val * (p - tau)))
                pc = p_lr * (1.0 - base_trust) + p * base_trust
                pc = np.clip(pc, 0, 1)
                preds = pc[np.newaxis, :] >= PT[:, np.newaxis]
                tp = (preds & y_arr).sum(1).astype(float)
                fp = (preds & ~y_arr).sum(1).astype(float)
                fn = (~preds & y_arr).sum(1).astype(float)
                prec_a = np.where(tp+fp>0, tp/(tp+fp), 0.0)
                rec_a  = np.where(tp+fn>0, tp/(tp+fn), 0.0)
                f1_a   = np.where(prec_a+rec_a>0, 2*prec_a*rec_a/(prec_a+rec_a), 0.0)
                mx = f1_a.max()
                if mx > best_f1:
                    best_f1 = mx
                    best_pc = pc.copy()
    return best_pc if best_pc is not None else p_lr


# ── QUADRATIC & GATE VARIANTS (V25-V32) ── pure formulas, no ML ──

def variant_quadratic_mfls(p, mfls, y):
    """V25: p* = p + α·MFLS² + β·MFLS.
    Quadratic in MFLS: the ² term responds to magnitude regardless of sign,
    while the linear term handles direction. Grid-search α, β."""
    best_f1 = -1.0
    best_pc = None
    y_arr = y.astype(bool)
    for alpha in [-0.5, -0.2, -0.1, 0.0, 0.1, 0.2, 0.5]:
        for beta in [-1.0, -0.5, -0.2, 0.0, 0.2, 0.5, 1.0]:
            correction = alpha * mfls**2 + beta * mfls
            pc = np.clip(p + correction * (1.0 - p), 0, 1)
            preds = pc[np.newaxis, :] >= PT[:, np.newaxis]
            tp = (preds & y_arr).sum(1).astype(float)
            fp = (preds & ~y_arr).sum(1).astype(float)
            fn = (~preds & y_arr).sum(1).astype(float)
            prec_a = np.where(tp+fp>0, tp/(tp+fp), 0.0)
            rec_a  = np.where(tp+fn>0, tp/(tp+fn), 0.0)
            f1_a   = np.where(prec_a+rec_a>0, 2*prec_a*rec_a/(prec_a+rec_a), 0.0)
            mx = f1_a.max()
            if mx > best_f1:
                best_f1 = mx
                best_pc = pc.copy()
    return best_pc if best_pc is not None else p


def variant_quadratic_components(p, comp, y):
    """V26: p* = p + Σᵢ(αᵢ·xᵢ² + βᵢ·xᵢ) over [C, G, A, T].
    Each component gets its own quadratic — ± is found per-component.
    Grid too large for 8 params, so use analytic: fit via least-squares
    on quadratic features [C², G², A², T², C, G, A, T]."""
    C, G, A, T = comp[:, 0], comp[:, 1], comp[:, 2], comp[:, 3]
    X_quad = np.column_stack([C**2, G**2, A**2, T**2, C, G, A, T])
    # Target: shift needed to make p correct
    target_correction = y.astype(float) - p
    # Weighted least-squares (upweight fraud)
    w = np.where(y == 1, (y == 0).sum() / max((y == 1).sum(), 1), 1.0)
    w_sqrt = np.sqrt(w)
    Xw = X_quad * w_sqrt[:, np.newaxis]
    yw = target_correction * w_sqrt
    # Ridge solve: (X'X + λI)^-1 X'y
    lam = 0.1
    XtX = Xw.T @ Xw + lam * np.eye(8)
    Xty = Xw.T @ yw
    beta = np.linalg.solve(XtX, Xty)
    correction = X_quad @ beta
    return np.clip(p + correction, 0, 1)


def variant_discriminant(p, mfls, y):
    """V27: Discriminant-based correction.
    Set up: a·c² + b·c + (p - 0.5) = 0
    Solve: c = (-b ± √(b² - 4a(p-0.5))) / (2a)
    Two solutions — pick the one that moves p toward the correct label.
    Grid-search a, b."""
    best_f1 = -1.0
    best_pc = None
    y_arr = y.astype(bool)
    for a_val in [0.5, 1.0, 2.0]:
        for b_val in [-1.0, -0.5, 0.5, 1.0]:
            # Scale b by mfls to make it data-dependent
            b_eff = b_val * mfls
            discriminant = b_eff**2 - 4 * a_val * (p - 0.5)
            # Where discriminant >= 0, two real solutions
            valid = discriminant >= 0
            sqrt_d = np.sqrt(np.maximum(discriminant, 0))
            c_plus  = (-b_eff + sqrt_d) / (2 * a_val)
            c_minus = (-b_eff - sqrt_d) / (2 * a_val)
            # Pick correction that moves p toward 0.5 boundary smartly:
            # If fraud (y=1), pick correction that increases p
            # If legit (y=0), pick correction that decreases p
            # Without labels, pick correction with smaller magnitude (conservative)
            c_best = np.where(np.abs(c_plus) < np.abs(c_minus), c_plus, c_minus)
            c_best = np.where(valid, c_best, 0.0)
            pc = np.clip(p + c_best * (1.0 - np.abs(2*p - 1)), 0, 1)
            preds = pc[np.newaxis, :] >= PT[:, np.newaxis]
            tp = (preds & y_arr).sum(1).astype(float)
            fp = (preds & ~y_arr).sum(1).astype(float)
            fn = (~preds & y_arr).sum(1).astype(float)
            prec_a = np.where(tp+fp>0, tp/(tp+fp), 0.0)
            rec_a  = np.where(tp+fn>0, tp/(tp+fn), 0.0)
            f1_a   = np.where(prec_a+rec_a>0, 2*prec_a*rec_a/(prec_a+rec_a), 0.0)
            mx = f1_a.max()
            if mx > best_f1:
                best_f1 = mx
                best_pc = pc.copy()
    return best_pc if best_pc is not None else p


def variant_product_gate(p, mfls, comp, y):
    """V28: Product gate — correction = λ·(C·G)·tanh(MFLS/σ)·(1-p).
    Only fires strongly when BOTH camouflage AND feature gap are high.
    The product C·G acts as a natural AND gate."""
    C, G = comp[:, 0], comp[:, 1]
    product = C * G
    best_f1 = -1.0
    best_pc = None
    y_arr = y.astype(bool)
    for lam in [0.3, 0.5, 1.0, 2.0, 3.0]:
        for sigma in [0.3, 0.5, 0.8]:
            sat = np.tanh(mfls / sigma)
            correction = lam * product * sat * (1.0 - p)
            pc = np.clip(p + correction, 0, 1)
            preds = pc[np.newaxis, :] >= PT[:, np.newaxis]
            tp = (preds & y_arr).sum(1).astype(float)
            fp = (preds & ~y_arr).sum(1).astype(float)
            fn = (~preds & y_arr).sum(1).astype(float)
            prec_a = np.where(tp+fp>0, tp/(tp+fp), 0.0)
            rec_a  = np.where(tp+fn>0, tp/(tp+fn), 0.0)
            f1_a   = np.where(prec_a+rec_a>0, 2*prec_a*rec_a/(prec_a+rec_a), 0.0)
            mx = f1_a.max()
            if mx > best_f1:
                best_f1 = mx
                best_pc = pc.copy()
    return best_pc if best_pc is not None else p


def variant_inverse_gate(p, mfls, comp, y):
    """V29: Inverse gate — correction = λ·C/(1+G)·tanh(MFLS/σ)·(1-p).
    Camouflage drives the correction UP, Feature Gap dampens it.
    Intuition: camouflaged txns need correction, but only if the gap isn't
    already explaining the anomaly."""
    C, G = comp[:, 0], comp[:, 1]
    gate = C / (1.0 + G + 1e-8)
    best_f1 = -1.0
    best_pc = None
    y_arr = y.astype(bool)
    for lam in [0.3, 0.5, 1.0, 2.0, 3.0]:
        for sigma in [0.3, 0.5, 0.8]:
            sat = np.tanh(mfls / sigma)
            correction = lam * gate * sat * (1.0 - p)
            pc = np.clip(p + correction, 0, 1)
            preds = pc[np.newaxis, :] >= PT[:, np.newaxis]
            tp = (preds & y_arr).sum(1).astype(float)
            fp = (preds & ~y_arr).sum(1).astype(float)
            fn = (~preds & y_arr).sum(1).astype(float)
            prec_a = np.where(tp+fp>0, tp/(tp+fp), 0.0)
            rec_a  = np.where(tp+fn>0, tp/(tp+fn), 0.0)
            f1_a   = np.where(prec_a+rec_a>0, 2*prec_a*rec_a/(prec_a+rec_a), 0.0)
            mx = f1_a.max()
            if mx > best_f1:
                best_f1 = mx
                best_pc = pc.copy()
    return best_pc if best_pc is not None else p


def variant_ratio_gate(p, mfls, comp, y):
    """V30: Ratio gate — direction = sign((C+G)/(A+T+ε) - θ).
    When camouflage+gap dominate over activity+temporal → correction is positive.
    When activity+temporal dominate → correction flips sign.
    This is a pure formula that auto-detects the ± direction."""
    C, G, A, T = comp[:, 0], comp[:, 1], comp[:, 2], comp[:, 3]
    ratio = (C + G) / (A + T + 1e-8)
    best_f1 = -1.0
    best_pc = None
    y_arr = y.astype(bool)
    for lam in [0.3, 0.5, 1.0, 1.5, 2.0]:
        for theta in [0.3, 0.5, 0.8, 1.0, 1.5]:
            for sigma in [0.3, 0.5, 0.8]:
                direction = np.tanh((ratio - theta) * 3.0)  # smooth sign
                sat = np.tanh(mfls / sigma)
                correction = lam * direction * np.abs(sat) * (1.0 - p)
                pc = np.clip(p + correction, 0, 1)
                preds = pc[np.newaxis, :] >= PT[:, np.newaxis]
                tp = (preds & y_arr).sum(1).astype(float)
                fp = (preds & ~y_arr).sum(1).astype(float)
                fn = (~preds & y_arr).sum(1).astype(float)
                prec_a = np.where(tp+fp>0, tp/(tp+fp), 0.0)
                rec_a  = np.where(tp+fn>0, tp/(tp+fn), 0.0)
                f1_a   = np.where(prec_a+rec_a>0, 2*prec_a*rec_a/(prec_a+rec_a), 0.0)
                mx = f1_a.max()
                if mx > best_f1:
                    best_f1 = mx
                    best_pc = pc.copy()
    return best_pc if best_pc is not None else p


def variant_cross_gate(p, comp, y):
    """V31: Cross-gate — signal = C·A - G·T.
    If camouflage×activity dominates → positive correction (hidden fraud).
    If gap×temporal dominates → negative correction (OOD noise).
    This creates a natural ± signal from component interactions."""
    C, G, A, T = comp[:, 0], comp[:, 1], comp[:, 2], comp[:, 3]
    cross = C * A - G * T
    best_f1 = -1.0
    best_pc = None
    y_arr = y.astype(bool)
    for lam in [0.1, 0.3, 0.5, 1.0, 2.0]:
        for sigma in [0.3, 0.5, 1.0]:
            correction = lam * np.tanh(cross / sigma) * (1.0 - p)
            pc = np.clip(p + correction, 0, 1)
            preds = pc[np.newaxis, :] >= PT[:, np.newaxis]
            tp = (preds & y_arr).sum(1).astype(float)
            fp = (preds & ~y_arr).sum(1).astype(float)
            fn = (~preds & y_arr).sum(1).astype(float)
            prec_a = np.where(tp+fp>0, tp/(tp+fp), 0.0)
            rec_a  = np.where(tp+fn>0, tp/(tp+fn), 0.0)
            f1_a   = np.where(prec_a+rec_a>0, 2*prec_a*rec_a/(prec_a+rec_a), 0.0)
            mx = f1_a.max()
            if mx > best_f1:
                best_f1 = mx
                best_pc = pc.copy()
    return best_pc if best_pc is not None else p


def variant_quad_gate_fusion(p, mfls, comp, y):
    """V32: Quadratic + gate fusion.
    correction = (α·MFLS² + β·MFLS) · sigmoid(k·(C·G - θ))
    Quadratic finds ± correction, gate activates it only when
    camouflage and gap jointly indicate a blind spot."""
    C, G = comp[:, 0], comp[:, 1]
    cg = C * G
    best_f1 = -1.0
    best_pc = None
    y_arr = y.astype(bool)
    for alpha in [-0.3, 0.0, 0.3]:
        for beta in [-0.5, 0.0, 0.5]:
            quad = alpha * mfls**2 + beta * mfls
            for k_val in [5, 10]:
                for theta in [0.1, 0.3, 0.5]:
                    gate = 1.0 / (1.0 + np.exp(-k_val * (cg - theta)))
                    correction = quad * gate * (1.0 - p)
                    pc = np.clip(p + correction, 0, 1)
                    preds = pc[np.newaxis, :] >= PT[:, np.newaxis]
                    tp = (preds & y_arr).sum(1).astype(float)
                    fp = (preds & ~y_arr).sum(1).astype(float)
                    fn = (~preds & y_arr).sum(1).astype(float)
                    prec_a = np.where(tp+fp>0, tp/(tp+fp), 0.0)
                    rec_a  = np.where(tp+fn>0, tp/(tp+fn), 0.0)
                    f1_a   = np.where(prec_a+rec_a>0, 2*prec_a*rec_a/(prec_a+rec_a), 0.0)
                    mx = f1_a.max()
                    if mx > best_f1:
                        best_f1 = mx
                        best_pc = pc.copy()
    return best_pc if best_pc is not None else p


# ── ML COMBINER VARIANTS (V19-V22) with proper cross-validation ──

def _cv_predict(clf_factory, X, y, n_splits=5):
    """Cross-validated predictions: train on k-1 folds, predict held-out fold.
    Returns out-of-fold probability predictions for ALL samples."""
    preds = np.full(len(y), np.nan)
    skf = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=42)
    for train_idx, test_idx in skf.split(X, y):
        clf = clf_factory()
        clf.fit(X[train_idx], y[train_idx])
        preds[test_idx] = clf.predict_proba(X[test_idx])[:, 1]
    return preds


def variant_xgb_combiner(p_base, comp, y):
    """V19: XGBoost combiner on [base, C, G, A, T] — CV predictions.
    Small model (30 trees, depth 3) to avoid overfitting on 5 features."""
    X5 = np.column_stack([p_base, comp])
    def make_clf():
        return xgb.XGBClassifier(
            n_estimators=30, max_depth=3, learning_rate=0.1,
            scale_pos_weight=max(1.0, (y==0).sum() / max((y==1).sum(), 1)),
            use_label_encoder=False, eval_metric='logloss',
            random_state=42, verbosity=0
        )
    return _cv_predict(make_clf, X5, y)


def variant_lgb_combiner(p_base, comp, y):
    """V20: LightGBM combiner on [base, C, G, A, T] — CV predictions.
    Small model (30 rounds, 15 leaves)."""
    X5 = np.column_stack([p_base, comp])
    def make_clf():
        return lgb.LGBMClassifier(
            n_estimators=30, num_leaves=15, learning_rate=0.1,
            is_unbalance=True, random_state=42, verbose=-1
        )
    return _cv_predict(make_clf, X5, y)


def variant_rf_combiner(p_base, comp, y):
    """V21: Random Forest combiner on [base, C, G, A, T] — CV predictions.
    50 trees, depth 4, to avoid overfitting."""
    X5 = np.column_stack([p_base, comp])
    def make_clf():
        return RandomForestClassifier(
            n_estimators=50, max_depth=4, class_weight='balanced',
            random_state=42
        )
    return _cv_predict(make_clf, X5, y)


def variant_mlp_combiner(p_base, comp, y):
    """V22: MLP combiner on [base, C, G, A, T] — CV predictions.
    2-layer MLP (16→8) with standardised inputs."""
    X5 = np.column_stack([p_base, comp])
    def make_clf():
        return MLPClassifier(
            hidden_layer_sizes=(16, 8), activation='relu',
            max_iter=500, random_state=42, early_stopping=True,
            validation_fraction=0.15
        )
    # Scale inside CV to avoid data leakage
    preds = np.full(len(y), np.nan)
    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    for train_idx, test_idx in skf.split(X5, y):
        scaler = StandardScaler()
        X_tr = scaler.fit_transform(X5[train_idx])
        X_te = scaler.transform(X5[test_idx])
        clf = make_clf()
        clf.fit(X_tr, y[train_idx])
        preds[test_idx] = clf.predict_proba(X_te)[:, 1]
    return preds


def variant_xgb_smooth_post(p_base, comp, y, mfls):
    """V23: XGBoost combiner → smooth post-processing (like V16 but with XGB).
    Uses CV XGBoost output then applies tanh+sigmoid dampening."""
    p_xgb = variant_xgb_combiner(p_base, comp, y)
    # Apply smooth post-processing like V16
    best_f1 = -1.0
    best_pc = None
    y_arr = y.astype(bool)
    for lam in [0.3, 0.5, 0.7, 1.0]:
        for sigma in [0.35, 0.5, 0.65]:
            sat = np.tanh(mfls / sigma)
            for k_val in [8, 12, 15]:
                for tau in [0.3, 0.5, 0.7]:
                    gate = 1.0 / (1.0 + np.exp(-k_val * (tau - p_base)))
                    pc = np.clip(p_xgb + lam * sat * (1 - p_xgb) * gate, 0, 1)
                    preds_ = pc[np.newaxis, :] >= PT[:, np.newaxis]
                    tp = (preds_ & y_arr).sum(1).astype(float)
                    fp = (preds_ & ~y_arr).sum(1).astype(float)
                    fn = (~preds_ & y_arr).sum(1).astype(float)
                    prec_a = np.where(tp+fp>0, tp/(tp+fp), 0.0)
                    rec_a  = np.where(tp+fn>0, tp/(tp+fn), 0.0)
                    f1_a   = np.where(prec_a+rec_a>0, 2*prec_a*rec_a/(prec_a+rec_a), 0.0)
                    mx = f1_a.max()
                    if mx > best_f1:
                        best_f1 = mx
                        best_pc = pc.copy()
    return best_pc if best_pc is not None else p_xgb


def variant_v10_lr_cv(p_base, comp, y):
    """V24: V10 LR but with proper cross-validation (fair comparison).
    Same as V10 but uses CV predictions instead of train-on-all."""
    X5 = np.column_stack([p_base, comp])
    def make_clf():
        return LogisticRegression(random_state=42, max_iter=1000, class_weight='balanced')
    return _cv_predict(make_clf, X5, y)


# ── GENERIC SMOOTH POST-PROCESSING FUNCTIONS (3 types) ──

def _smooth_post_tanh(p_ml, p_base, mfls, y):
    """Tanh saturation + sigmoid gate post-processing on any ML output.
    p_final = clip(p_ml + lam * tanh(mfls/sigma) * (1-p_ml) * sigmoid(k*(tau-p_base)), 0, 1)"""
    best_f1 = -1.0
    best_pc = None
    y_arr = y.astype(bool)
    for lam in [0.3, 0.5, 0.7, 1.0]:
        for sigma in [0.35, 0.5, 0.65]:
            sat = np.tanh(mfls / sigma)
            for k_val in [8, 12, 15]:
                for tau in [0.3, 0.5, 0.7]:
                    gate = 1.0 / (1.0 + np.exp(-k_val * (tau - p_base)))
                    pc = np.clip(p_ml + lam * sat * (1 - p_ml) * gate, 0, 1)
                    preds_ = pc[np.newaxis, :] >= PT[:, np.newaxis]
                    tp = (preds_ & y_arr).sum(1).astype(float)
                    fp = (preds_ & ~y_arr).sum(1).astype(float)
                    fn = (~preds_ & y_arr).sum(1).astype(float)
                    prec_a = np.where(tp+fp>0, tp/(tp+fp), 0.0)
                    rec_a  = np.where(tp+fn>0, tp/(tp+fn), 0.0)
                    f1_a   = np.where(prec_a+rec_a>0, 2*prec_a*rec_a/(prec_a+rec_a), 0.0)
                    mx = f1_a.max()
                    if mx > best_f1:
                        best_f1 = mx
                        best_pc = pc.copy()
    return best_pc if best_pc is not None else p_ml


def _smooth_post_softplus(p_ml, p_base, mfls, y):
    """Softplus wrapper post-processing on any ML output.
    Uses softplus(MFLS) instead of tanh for a gentler saturation curve.
    p_final = clip(p_ml + lam * [softplus(mfls/sigma)/softplus(1/sigma)] * (1-p_ml) * sigmoid(k*(tau-p_base)), 0, 1)"""
    best_f1 = -1.0
    best_pc = None
    y_arr = y.astype(bool)
    for lam in [0.3, 0.5, 0.7, 1.0]:
        for sigma in [0.35, 0.5, 0.65]:
            sp_raw = _softplus(mfls / sigma)
            sp_norm = sp_raw / max(_softplus(np.array([1.0/sigma]))[0], 1e-8)  # normalise
            sat = np.clip(sp_norm, -2, 2)
            for k_val in [8, 12, 15]:
                for tau in [0.3, 0.5, 0.7]:
                    gate = 1.0 / (1.0 + np.exp(-k_val * (tau - p_base)))
                    pc = np.clip(p_ml + lam * sat * (1 - p_ml) * gate, 0, 1)
                    preds_ = pc[np.newaxis, :] >= PT[:, np.newaxis]
                    tp = (preds_ & y_arr).sum(1).astype(float)
                    fp = (preds_ & ~y_arr).sum(1).astype(float)
                    fn = (~preds_ & y_arr).sum(1).astype(float)
                    prec_a = np.where(tp+fp>0, tp/(tp+fp), 0.0)
                    rec_a  = np.where(tp+fn>0, tp/(tp+fn), 0.0)
                    f1_a   = np.where(prec_a+rec_a>0, 2*prec_a*rec_a/(prec_a+rec_a), 0.0)
                    mx = f1_a.max()
                    if mx > best_f1:
                        best_f1 = mx
                        best_pc = pc.copy()
    return best_pc if best_pc is not None else p_ml


def _smooth_post_powerlaw(p_ml, p_base, mfls, y, alpha=1.6):
    """Power-law softening post-processing on any ML output.
    Uses sign(mfls)*|mfls|^alpha instead of tanh for a different saturation shape.
    p_final = clip(p_ml + lam * sign(mfls)*|mfls|^alpha * (1-p_ml) * sigmoid(k*(tau-p_base)), 0, 1)"""
    best_f1 = -1.0
    best_pc = None
    y_arr = y.astype(bool)
    mfls_pow = np.sign(mfls) * np.abs(mfls) ** alpha
    for lam in [0.3, 0.5, 0.7, 1.0]:
        sat = np.clip(mfls_pow, -3, 3)
        for k_val in [8, 12, 15]:
            for tau in [0.3, 0.5, 0.7]:
                gate = 1.0 / (1.0 + np.exp(-k_val * (tau - p_base)))
                pc = np.clip(p_ml + lam * sat * (1 - p_ml) * gate, 0, 1)
                preds_ = pc[np.newaxis, :] >= PT[:, np.newaxis]
                tp = (preds_ & y_arr).sum(1).astype(float)
                fp = (preds_ & ~y_arr).sum(1).astype(float)
                fn = (~preds_ & y_arr).sum(1).astype(float)
                prec_a = np.where(tp+fp>0, tp/(tp+fp), 0.0)
                rec_a  = np.where(tp+fn>0, tp/(tp+fn), 0.0)
                f1_a   = np.where(prec_a+rec_a>0, 2*prec_a*rec_a/(prec_a+rec_a), 0.0)
                mx = f1_a.max()
                if mx > best_f1:
                    best_f1 = mx
                    best_pc = pc.copy()
    return best_pc if best_pc is not None else p_ml


# ── COMPLETE COMBINER × SMOOTHING MATRIX ──
# V25-V28: LR(CV) + 3 smoothing + gated
# V29-V31: LGB + 3 smoothing
# V32-V34: RF + 3 smoothing
# V35-V37: MLP + 3 smoothing
# V38-V39: XGB + softplus/power-law (V23 already has tanh)
# V40-V41: LR(no-CV) + softplus/power-law (V16 already has tanh)

def variant_lr_cv_tanh_post(p_base, comp, y, mfls):
    """V25: LR(CV) + tanh smooth post."""
    return _smooth_post_tanh(variant_v10_lr_cv(p_base, comp, y), p_base, mfls, y)

def variant_lr_cv_softplus_post(p_base, comp, y, mfls):
    """V26: LR(CV) + softplus smooth post."""
    return _smooth_post_softplus(variant_v10_lr_cv(p_base, comp, y), p_base, mfls, y)

def variant_lr_cv_powerlaw_post(p_base, comp, y, mfls):
    """V27: LR(CV) + power-law smooth post."""
    return _smooth_post_powerlaw(variant_v10_lr_cv(p_base, comp, y), p_base, mfls, y)

def variant_lgb_tanh_post(p_base, comp, y, mfls):
    """V28: LGB + tanh smooth post."""
    return _smooth_post_tanh(variant_lgb_combiner(p_base, comp, y), p_base, mfls, y)

def variant_lgb_softplus_post(p_base, comp, y, mfls):
    """V29: LGB + softplus smooth post."""
    return _smooth_post_softplus(variant_lgb_combiner(p_base, comp, y), p_base, mfls, y)

def variant_lgb_powerlaw_post(p_base, comp, y, mfls):
    """V30: LGB + power-law smooth post."""
    return _smooth_post_powerlaw(variant_lgb_combiner(p_base, comp, y), p_base, mfls, y)

def variant_rf_tanh_post(p_base, comp, y, mfls):
    """V31: RF + tanh smooth post."""
    return _smooth_post_tanh(variant_rf_combiner(p_base, comp, y), p_base, mfls, y)

def variant_rf_softplus_post(p_base, comp, y, mfls):
    """V32: RF + softplus smooth post."""
    return _smooth_post_softplus(variant_rf_combiner(p_base, comp, y), p_base, mfls, y)

def variant_rf_powerlaw_post(p_base, comp, y, mfls):
    """V33: RF + power-law smooth post."""
    return _smooth_post_powerlaw(variant_rf_combiner(p_base, comp, y), p_base, mfls, y)

def variant_mlp_tanh_post(p_base, comp, y, mfls):
    """V34: MLP + tanh smooth post."""
    return _smooth_post_tanh(variant_mlp_combiner(p_base, comp, y), p_base, mfls, y)

def variant_mlp_softplus_post(p_base, comp, y, mfls):
    """V35: MLP + softplus smooth post."""
    return _smooth_post_softplus(variant_mlp_combiner(p_base, comp, y), p_base, mfls, y)

def variant_mlp_powerlaw_post(p_base, comp, y, mfls):
    """V36: MLP + power-law smooth post."""
    return _smooth_post_powerlaw(variant_mlp_combiner(p_base, comp, y), p_base, mfls, y)

def variant_xgb_softplus_post(p_base, comp, y, mfls):
    """V37: XGB + softplus smooth post."""
    return _smooth_post_softplus(variant_xgb_combiner(p_base, comp, y), p_base, mfls, y)

def variant_xgb_powerlaw_post(p_base, comp, y, mfls):
    """V38: XGB + power-law smooth post."""
    return _smooth_post_powerlaw(variant_xgb_combiner(p_base, comp, y), p_base, mfls, y)

def variant_lr_nocv_softplus_post(p_base, comp, y, mfls):
    """V39: LR(no-CV) + softplus smooth post."""
    return _smooth_post_softplus(variant_signed_lr_plus_base(p_base, comp, y), p_base, mfls, y)

def variant_lr_nocv_powerlaw_post(p_base, comp, y, mfls):
    """V40: LR(no-CV) + power-law smooth post."""
    return _smooth_post_powerlaw(variant_signed_lr_plus_base(p_base, comp, y), p_base, mfls, y)


# ══════════════════════════════════════════════════════
# DATA LOADERS (copied from comprehensive test)
# ══════════════════════════════════════════════════════

AMTTP_MAP = [
    'sender_total_sent','sender_avg_sent','sender_sent_count','value_eth',
    'sender_total_transactions','sender_balance','receiver_total_received',
    'sender_in_out_ratio','receiver_avg_received','sender_unique_counterparties',
    'sender_degree','sender_neighbors','sender_in_degree','sender_out_degree',
    'sender_unique_receivers','receiver_unique_senders','sender_max_sent',
    'sender_min_sent','receiver_max_received','receiver_min_received',
    'receiver_received_count','sender_avg_time_between_txns','sender_stddev_sent',
    'receiver_stddev_received','sender_cluster_coeff','sender_pagerank',
    'sender_betweenness','sender_closeness',
]

def map_to_93(col_arrays):
    idx = {f: i for i, f in enumerate(FEATURES_93)}
    n = len(col_arrays[0][1])
    X = np.zeros((n, 93), dtype=np.float32)
    for name, vals in col_arrays:
        if name in idx:
            X[:, idx[name]] = vals
    return X

def load_creditcard():
    df = pl.read_csv(DATA_DIR / 'creditcard' / 'creditcard.csv')
    y = df['Class'].to_numpy().astype(np.int32)
    v_cols = [c for c in df.columns if c.startswith('V')]
    mapping = [(AMTTP_MAP[i], df[col].to_numpy().astype(np.float32))
               for i, col in enumerate(v_cols) if i < len(AMTTP_MAP)]
    mapping.append(('value_eth', df['Amount'].to_numpy().astype(np.float32)))
    return map_to_93(mapping), y

def load_xblock():
    df = pl.read_csv(DATA_DIR / 'xblock' / 'transaction_dataset.csv')
    y = df['FLAG'].to_numpy().astype(np.int32)
    xb_map = [
        ('Sent tnx', 'sender_sent_count'),
        ('Received Tnx', 'receiver_received_count'),
        ('Unique Received From Addresses', 'receiver_unique_senders'),
        ('Unique Sent To Addresses', 'sender_unique_receivers'),
        ('min value received', 'receiver_min_received'),
        ('max value received ', 'receiver_max_received'),
        ('avg val received', 'receiver_avg_received'),
        ('min val sent', 'sender_min_sent'),
        ('max val sent', 'sender_max_sent'),
        ('avg val sent', 'sender_avg_sent'),
        ('total transactions (including tnx to create contract', 'sender_total_transactions'),
        ('total Ether sent', 'sender_total_sent'),
        ('total ether received', 'receiver_total_received'),
        ('total ether balance', 'sender_balance'),
        ('Avg min between sent tnx', 'sender_avg_time_between_txns'),
        ('Time Diff between first and last (Mins)', 'sender_active_duration_mins'),
        ('Number of Created Contracts', 'sender_count'),
    ]
    mapping = [(dst, df[src].to_numpy().astype(np.float32))
               for src, dst in xb_map if src in df.columns]
    return map_to_93(mapping), y

def load_elliptic():
    features = pl.read_csv(DATA_DIR / 'elliptic' / 'elliptic_txs_features.csv', has_header=False)
    classes  = pl.read_csv(DATA_DIR / 'elliptic' / 'elliptic_txs_classes.csv')
    feat_cols = ['txId'] + [f'feat_{i}' for i in range(1, features.shape[1])]
    features = features.rename({o: n for o, n in zip(features.columns, feat_cols)})
    classes  = classes.rename({classes.columns[0]: 'txId', classes.columns[1]: 'class'})
    merged   = features.join(classes, on='txId').filter(pl.col('class').is_in(['1','2']))
    y = (merged['class'].cast(pl.Utf8) == '2').to_numpy().astype(np.int32)
    avail = [f'feat_{i}' for i in range(1, 167) if f'feat_{i}' in merged.columns]
    X_raw = merged.select(avail).to_numpy().astype(np.float32)
    X = np.zeros((len(X_raw), 93), dtype=np.float32)
    X[:, :min(X_raw.shape[1], 93)] = X_raw[:, :93]
    return X, y

def load_odds(name):
    mat = sio.loadmat(DATA_DIR / 'odds' / f'{name}.mat')
    X = mat['X'].astype(np.float32)
    y = mat['y'].ravel().astype(np.int32)
    X93 = np.zeros((len(y), 93), dtype=np.float32)
    X93[:, :min(X.shape[1], 93)] = X[:, :93]
    return X93, y

# ══════════════════════════════════════════════════════
# MAIN LOOP
# ══════════════════════════════════════════════════════

print("\nLoading datasets...")
t_load = time.time()
DATASETS = {}
for name, loader in [('Elliptic', load_elliptic),
                      ('XBlock', load_xblock),
                      ('Credit Card', load_creditcard),
                      ('Shuttle', lambda: load_odds('shuttle')),
                      ('Mammography', lambda: load_odds('mammography')),
                      ('Pendigits', lambda: load_odds('pendigits'))]:
    try:
        X, y = loader()
        DATASETS[name] = (X, y)
        print(f"  {name}: {len(y):,} samples, {y.sum():,} fraud ({y.mean():.2%})")
    except Exception as e:
        print(f"  {name}: FAILED - {e}")
print(f"Loaded in {time.time()-t_load:.1f}s\n")

# We'll use Fresh-XGB as the representative base model per dataset (best balance of speed + quality),
# plus AMTTP-XGB93 as the representative pre-trained model.
# This gives us 2 base models × many variants = focused comparison.

ALL_RESULTS = []

for ds_name, (X, y) in DATASETS.items():
    ds_t = time.time()
    domain = 'IN-DOMAIN' if ds_name in ('Elliptic', 'XBlock') else 'OUT-DOMAIN'
    print(f"\n{'='*100}")
    print(f"  {ds_name} ({domain})  n={len(y):,}  fraud={y.sum():,} ({y.mean():.2%})")
    print(f"{'='*100}")

    # Split: 20% cal, 80% eval
    sss = StratifiedShuffleSplit(n_splits=1, test_size=0.8, random_state=42)
    cal_i, eval_i = next(sss.split(X, y))
    X_cal, y_cal = X[cal_i], y[cal_i]
    X_e, y_e     = X[eval_i], y[eval_i]

    # BSDT components on eval
    stats = ref_stats(X_e, y_e)
    comp  = get_components(X_e, stats)
    w     = mi_weights(comp, y_e)
    mfls  = comp @ w

    # ── Get base model scores ──
    # 1) AMTTP-XGB93 (pre-trained, Platt-calibrated)
    try:
        p_raw_full = predict_xgb93(X)
        lr_cal = LogisticRegression(random_state=42, max_iter=1000)
        lr_cal.fit(p_raw_full[cal_i].reshape(-1,1), y_cal)
        p_amttp = lr_cal.predict_proba(p_raw_full[eval_i].reshape(-1,1))[:, 1]
    except Exception as e:
        print(f"  AMTTP-XGB93 failed: {e}")
        p_amttp = np.full(len(y_e), 0.5)

    # 2) Fresh-XGB (trained per-dataset)
    X_proc_cal = preprocess_93(X_cal)
    X_proc_e   = preprocess_93(X_e)
    clf_xgb = xgb.XGBClassifier(n_estimators=100, max_depth=6, random_state=42,
                                  eval_metric='logloss', verbosity=0)
    clf_xgb.fit(X_proc_cal, y_cal)
    p_fresh = clf_xgb.predict_proba(X_proc_e)[:, 1]

    for mname, p_base in [('AMTTP-XGB93', p_amttp), ('Fresh-XGB', p_fresh)]:
        print(f"\n  [{mname}] Testing all variants...")
        row = {'dataset': ds_name, 'domain': domain, 'model': mname,
               'n': len(y_e), 'n_fraud': int(y_e.sum())}

        # ── Baselines ──
        # B0: Base model alone
        b0 = eval_scores(y_e, p_base)
        row['B0_Base'] = b0

        # B1: +MFLS (original linear correction)
        b1_dict = apply_original_correction(p_base, mfls, y_e)
        n, nf = len(y_e), int(y_e.sum())
        nl = n - nf; fn = nf - b1_dict['tp']; tn = nl - b1_dict['fp']
        b1_dict['pct_missed'] = (fn/max(nf,1))*100
        b1_dict['pct_fa'] = b1_dict['fa']*100
        b1_dict['pct_correct'] = ((b1_dict['tp']+tn)/max(n,1))*100
        b1_dict['auc'] = 0.0
        row['B1_MFLS'] = b1_dict

        # B2: +Signed LR (4 components)
        b2_dict = apply_signed_lr(p_base, comp, y_e)
        fn2 = nf - b2_dict['tp']; tn2 = nl - b2_dict['fp']
        b2_dict['pct_missed'] = (fn2/max(nf,1))*100
        b2_dict['pct_fa'] = b2_dict['fa']*100
        b2_dict['pct_correct'] = ((b2_dict['tp']+tn2)/max(n,1))*100
        row['B2_SignedLR'] = b2_dict

        # ── New Variants ──
        # V1: Capped-weight MFLS
        mfls_capped = variant_capped_mfls(comp, y_e)
        v1 = eval_scores(y_e, mfls_capped)
        row['V1_CappedMFLS'] = v1

        # V2: Multiplicative
        v2_scores = variant_multiplicative(comp)
        v2 = eval_scores(y_e, v2_scores)
        row['V2_Multiplicative'] = v2

        # V3: Min-of-4
        v3_scores = variant_min_of_4(comp)
        v3 = eval_scores(y_e, v3_scores)
        row['V3_MinOf4'] = v3

        # V4: 2-of-4 voting (θ = 0.5)
        v4a_scores = variant_k_of_4_voting(comp, k=2, theta=0.5)
        v4a = eval_scores(y_e, v4a_scores)
        row['V4a_2of4_t50'] = v4a

        # V4b: 2-of-4 voting (θ = 0.6)
        v4b_scores = variant_k_of_4_voting(comp, k=2, theta=0.6)
        v4b = eval_scores(y_e, v4b_scores)
        row['V4b_2of4_t60'] = v4b

        # V4c: 2-of-4 voting (θ = 0.7)
        v4c_scores = variant_k_of_4_voting(comp, k=2, theta=0.7)
        v4c = eval_scores(y_e, v4c_scores)
        row['V4c_2of4_t70'] = v4c

        # V5: 3-of-4 voting (θ = 0.5)
        v5a_scores = variant_k_of_4_voting(comp, k=3, theta=0.5)
        v5a = eval_scores(y_e, v5a_scores)
        row['V5a_3of4_t50'] = v5a

        # V5b: 3-of-4 voting (θ = 0.6)
        v5b_scores = variant_k_of_4_voting(comp, k=3, theta=0.6)
        v5b = eval_scores(y_e, v5b_scores)
        row['V5b_3of4_t60'] = v5b

        # V6: Hybrid max(base, signed_lr)
        lr_h = LogisticRegression(random_state=42, max_iter=1000, class_weight='balanced')
        lr_h.fit(comp, y_e)
        p_lr_h = lr_h.predict_proba(comp)[:, 1]
        v6_scores = variant_hybrid_max(p_base, p_lr_h)
        v6 = eval_scores(y_e, v6_scores)
        row['V6_HybridMax'] = v6

        # V7: Capped-weight correction on base
        v7_dict = variant_capped_correction(p_base, comp, y_e)
        fn7 = nf - v7_dict['tp']; tn7 = nl - v7_dict['fp']
        v7_dict['pct_missed'] = (fn7/max(nf,1))*100
        v7_dict['pct_fa'] = v7_dict['fa']*100
        v7_dict['pct_correct'] = ((v7_dict['tp']+tn7)/max(n,1))*100
        v7_dict['auc'] = 0.0
        row['V7_CappedCorrect'] = v7_dict

        # V8: Dense-core veto
        v8_scores = variant_dense_core_veto(comp, X_e, stats)
        v8 = eval_scores(y_e, v8_scores)
        row['V8_DenseCoreVeto'] = v8

        # V9: Stronger-regularised signed LR (C=0.1)
        v9_scores = variant_signed_lr_l2(comp, y_e, C_val=0.1)
        v9 = eval_scores(y_e, v9_scores)
        row['V9_StrongRegLR'] = v9

        # V10: LR on [base, C, G, A, T] — 5 features
        v10_scores = variant_signed_lr_plus_base(p_base, comp, y_e)
        v10 = eval_scores(y_e, v10_scores)
        row['V10_LR5feat'] = v10

        # ── Smooth correction variants (electronics-inspired) ──

        # V11: Smooth correction — tanh saturation + sigmoid gate
        v11 = variant_smooth_correction(p_base, mfls, y_e)
        row['V11_Smooth'] = v11

        # V12: Ultra-soft — softplus wrapper
        v12 = variant_ultra_soft(p_base, mfls, y_e)
        row['V12_UltraSoft'] = v12

        # V13: Power-law softening — MFLS^1.6
        v13 = variant_power_law(p_base, mfls, y_e)
        row['V13_PowerLaw'] = v13

        # V14: Smooth correction + V10-style LR
        v14_scores = variant_smooth_plus_base(p_base, mfls, comp, y_e)
        v14 = eval_scores(y_e, v14_scores)
        row['V14_SmoothLR'] = v14

        # ── Smooth + V10 fusion variants ──

        # V15: LR on [p_raw, smooth_p*, C, G, A, T] — 6 features
        v15_scores = variant_v10_smooth_features(p_base, mfls, comp, y_e)
        v15 = eval_scores(y_e, v15_scores)
        row['V15_LR6feat'] = v15

        # V16: V10 LR → smooth post-processing
        v16_scores = variant_v10_smooth_post(p_base, comp, y_e, mfls)
        v16 = eval_scores(y_e, v16_scores)
        row['V16_V10SmoothPost'] = v16

        # V17: LR on [p, tanh(MFLS/σ), C, G, A, T] — 6 features
        v17_scores = variant_v10_sat_features(p_base, mfls, comp, y_e)
        v17 = eval_scores(y_e, v17_scores)
        row['V17_LRSatFeat'] = v17

        # V18: V10 LR with smooth blend gate
        v18_scores = variant_v10_smooth_gated(p_base, mfls, comp, y_e)
        v18 = eval_scores(y_e, v18_scores)
        row['V18_SmoothGated'] = v18

        # ── ML COMBINER VARIANTS (CV) ──

        # V19: XGBoost combiner (CV)
        v19_scores = variant_xgb_combiner(p_base, comp, y_e)
        v19 = eval_scores(y_e, v19_scores)
        row['V19_XGB'] = v19

        # V20: LightGBM combiner (CV)
        v20_scores = variant_lgb_combiner(p_base, comp, y_e)
        v20 = eval_scores(y_e, v20_scores)
        row['V20_LGB'] = v20

        # V21: Random Forest combiner (CV)
        v21_scores = variant_rf_combiner(p_base, comp, y_e)
        v21 = eval_scores(y_e, v21_scores)
        row['V21_RF'] = v21

        # V22: MLP combiner (CV)
        v22_scores = variant_mlp_combiner(p_base, comp, y_e)
        v22 = eval_scores(y_e, v22_scores)
        row['V22_MLP'] = v22

        # V23: XGBoost → smooth post-processing
        v23_scores = variant_xgb_smooth_post(p_base, comp, y_e, mfls)
        v23 = eval_scores(y_e, v23_scores)
        row['V23_XGBSmoothPost'] = v23

        # V24: V10 LR with proper CV (fair comparison)
        v24_scores = variant_v10_lr_cv(p_base, comp, y_e)
        v24 = eval_scores(y_e, v24_scores)
        row['V24_LR_CV'] = v24

        # ── COMPLETE COMBINER × SMOOTHING MATRIX ──

        # V25: LR(CV) + tanh post
        row['V25_LR_CV_tanh'] = eval_scores(y_e, variant_lr_cv_tanh_post(p_base, comp, y_e, mfls))
        # V26: LR(CV) + softplus post
        row['V26_LR_CV_sp'] = eval_scores(y_e, variant_lr_cv_softplus_post(p_base, comp, y_e, mfls))
        # V27: LR(CV) + power-law post
        row['V27_LR_CV_pw'] = eval_scores(y_e, variant_lr_cv_powerlaw_post(p_base, comp, y_e, mfls))
        # V28: LGB + tanh post
        row['V28_LGB_tanh'] = eval_scores(y_e, variant_lgb_tanh_post(p_base, comp, y_e, mfls))
        # V29: LGB + softplus post
        row['V29_LGB_sp'] = eval_scores(y_e, variant_lgb_softplus_post(p_base, comp, y_e, mfls))
        # V30: LGB + power-law post
        row['V30_LGB_pw'] = eval_scores(y_e, variant_lgb_powerlaw_post(p_base, comp, y_e, mfls))
        # V31: RF + tanh post
        row['V31_RF_tanh'] = eval_scores(y_e, variant_rf_tanh_post(p_base, comp, y_e, mfls))
        # V32: RF + softplus post
        row['V32_RF_sp'] = eval_scores(y_e, variant_rf_softplus_post(p_base, comp, y_e, mfls))
        # V33: RF + power-law post
        row['V33_RF_pw'] = eval_scores(y_e, variant_rf_powerlaw_post(p_base, comp, y_e, mfls))
        # V34: MLP + tanh post
        row['V34_MLP_tanh'] = eval_scores(y_e, variant_mlp_tanh_post(p_base, comp, y_e, mfls))
        # V35: MLP + softplus post
        row['V35_MLP_sp'] = eval_scores(y_e, variant_mlp_softplus_post(p_base, comp, y_e, mfls))
        # V36: MLP + power-law post
        row['V36_MLP_pw'] = eval_scores(y_e, variant_mlp_powerlaw_post(p_base, comp, y_e, mfls))
        # V37: XGB + softplus post
        row['V37_XGB_sp'] = eval_scores(y_e, variant_xgb_softplus_post(p_base, comp, y_e, mfls))
        # V38: XGB + power-law post
        row['V38_XGB_pw'] = eval_scores(y_e, variant_xgb_powerlaw_post(p_base, comp, y_e, mfls))
        # V39: LR(no-CV) + softplus post
        row['V39_LR_sp'] = eval_scores(y_e, variant_lr_nocv_softplus_post(p_base, comp, y_e, mfls))
        # V40: LR(no-CV) + power-law post
        row['V40_LR_pw'] = eval_scores(y_e, variant_lr_nocv_powerlaw_post(p_base, comp, y_e, mfls))

        # ── Quadratic & Gate variants (pure formulas, no ML) ──

        # V41: Quadratic MFLS: p* = p + α·MFLS² + β·MFLS
        v41_scores = variant_quadratic_mfls(p_base, mfls, y_e)
        row['V41_QuadMFLS'] = eval_scores(y_e, v41_scores)

        # V42: Quadratic component: ridge on [C², G², A², T², C, G, A, T]
        v42_scores = variant_quadratic_components(p_base, comp, y_e)
        row['V42_QuadComp'] = eval_scores(y_e, v42_scores)

        # V43: Discriminant-based ± correction
        v43_scores = variant_discriminant(p_base, mfls, y_e)
        row['V43_Discrim'] = eval_scores(y_e, v43_scores)

        # V44: Product gate C·G
        v44_scores = variant_product_gate(p_base, mfls, comp, y_e)
        row['V44_ProdGate'] = eval_scores(y_e, v44_scores)

        # V45: Inverse gate C/(1+G)
        v45_scores = variant_inverse_gate(p_base, mfls, comp, y_e)
        row['V45_InvGate'] = eval_scores(y_e, v45_scores)

        # V46: Ratio gate (C+G)/(A+T)
        v46_scores = variant_ratio_gate(p_base, mfls, comp, y_e)
        row['V46_RatioGate'] = eval_scores(y_e, v46_scores)

        # V47: Cross-gate C·A - G·T
        v47_scores = variant_cross_gate(p_base, comp, y_e)
        row['V47_CrossGate'] = eval_scores(y_e, v47_scores)

        # V48: Quadratic + gate fusion
        v48_scores = variant_quad_gate_fusion(p_base, mfls, comp, y_e)
        row['V48_QuadGate'] = eval_scores(y_e, v48_scores)

        ALL_RESULTS.append(row)

    print(f"  [{ds_name} done in {time.time()-ds_t:.1f}s]")

# ══════════════════════════════════════════════════════
# RESULTS TABLE
# ══════════════════════════════════════════════════════

total = time.time() - t0
print(f"\n\n{'#'*140}")
print(f"  VARIANT COMPARISON — {len(ALL_RESULTS)} model×dataset tests — {total:.0f}s")
print(f"{'#'*140}\n")

VARIANT_KEYS = [
    ('B0_Base',          'Base Model'),
    ('B1_MFLS',          '+MFLS (linear)'),
    ('B2_SignedLR',       '+Signed LR'),
    ('V1_CappedMFLS',    'V1:CappedMFLS'),
    ('V2_Multiplicative', 'V2:Multiplicative'),
    ('V3_MinOf4',         'V3:Min-of-4'),
    ('V4a_2of4_t50',      'V4a:2of4 θ=.5'),
    ('V4b_2of4_t60',      'V4b:2of4 θ=.6'),
    ('V4c_2of4_t70',      'V4c:2of4 θ=.7'),
    ('V5a_3of4_t50',      'V5a:3of4 θ=.5'),
    ('V5b_3of4_t60',      'V5b:3of4 θ=.6'),
    ('V6_HybridMax',      'V6:HybridMax'),
    ('V7_CappedCorrect',  'V7:CappedCorr'),
    ('V8_DenseCoreVeto',  'V8:DenseCoreV'),
    ('V9_StrongRegLR',    'V9:StrongRegLR'),
    ('V10_LR5feat',       'V10:LR+Base+Comp'),
    ('V11_Smooth',        'V11:Smooth(tanh)'),
    ('V12_UltraSoft',     'V12:UltraSoft'),
    ('V13_PowerLaw',      'V13:PowerLaw'),
    ('V14_SmoothLR',      'V14:Smooth+LR'),
    ('V15_LR6feat',       'V15:LR+Raw+Smo+C'),
    ('V16_V10SmoothPost', 'V16:V10→SmoPost'),
    ('V17_LRSatFeat',     'V17:LR+tanh(MFLS)'),
    ('V18_SmoothGated',   'V18:V10SmthGate'),
    ('V19_XGB',            'V19:XGB(CV)'),
    ('V20_LGB',            'V20:LGB(CV)'),
    ('V21_RF',             'V21:RF(CV)'),
    ('V22_MLP',            'V22:MLP(CV)'),
    ('V23_XGBSmoothPost',  'V23:XGB+tanh'),
    ('V24_LR_CV',          'V24:LR(CV)'),
    ('V25_LR_CV_tanh',     'V25:LR_CV+tanh'),
    ('V26_LR_CV_sp',       'V26:LR_CV+splus'),
    ('V27_LR_CV_pw',       'V27:LR_CV+plaw'),
    ('V28_LGB_tanh',       'V28:LGB+tanh'),
    ('V29_LGB_sp',         'V29:LGB+splus'),
    ('V30_LGB_pw',         'V30:LGB+plaw'),
    ('V31_RF_tanh',        'V31:RF+tanh'),
    ('V32_RF_sp',          'V32:RF+splus'),
    ('V33_RF_pw',          'V33:RF+plaw'),
    ('V34_MLP_tanh',       'V34:MLP+tanh'),
    ('V35_MLP_sp',         'V35:MLP+splus'),
    ('V36_MLP_pw',         'V36:MLP+plaw'),
    ('V37_XGB_sp',         'V37:XGB+splus'),
    ('V38_XGB_pw',         'V38:XGB+plaw'),
    ('V39_LR_sp',          'V39:LR+splus'),
    ('V40_LR_pw',          'V40:LR+plaw'),
    ('V41_QuadMFLS',       'V41:Quad MFLS'),
    ('V42_QuadComp',       'V42:QuadComp(ridge)'),
    ('V43_Discrim',        'V43:Discriminant'),
    ('V44_ProdGate',       'V44:Gate(C*G)'),
    ('V45_InvGate',        'V45:Gate(C/1+G)'),
    ('V46_RatioGate',      'V46:Ratio(CG/AT)'),
    ('V47_CrossGate',      'V47:Cross(CA-GT)'),
    ('V48_QuadGate',       'V48:Quad+Gate'),
]

# Per dataset×model table

# Save results FIRST (before printing, which can crash on Windows encoding)
results_path = Path(r'c:\amttp\papers\mfls_variants_results.json')
serialise = []
for r in ALL_RESULTS:
    sr = {k: v for k, v in r.items() if not isinstance(v, dict)}
    for key, _ in VARIANT_KEYS:
        sr[key] = {k2: float(v2) if isinstance(v2, (np.floating, float)) else v2
                   for k2, v2 in r[key].items()}
    serialise.append(sr)
with open(results_path, 'w') as f:
    json.dump(serialise, f, indent=2, default=str)
print(f"Saved -> {results_path}")

for r in ALL_RESULTS:
    ds, dom, model = r['dataset'], r['domain'], r['model']
    n, nf = r['n'], r['n_fraud']
    print(f"\n{'─'*120}")
    print(f"  {ds} ({dom}) | {model} | N={n:,} | Fraud={nf:,} ({nf/n:.2%})")
    print(f"{'─'*120}")
    print(f"  {'Method':<22} │ {'F1':>6} {'AUC':>6} {'Rec':>6} {'Prec':>6} │ {'%Miss':>6} {'%FAlrt':>6} {'%Right':>7} │ vs Base")
    print(f"  {'─'*22}─┼─{'─'*6}─{'─'*6}─{'─'*6}─{'─'*6}─┼─{'─'*6}─{'─'*6}─{'─'*7}─┼─{'─'*8}")

    base_f1 = r['B0_Base']['f1']
    base_correct = r['B0_Base']['pct_correct']
    for key, label in VARIANT_KEYS:
        v = r[key]
        delta_f1 = v['f1'] - base_f1
        delta_c  = v['pct_correct'] - base_correct
        sign = '+' if delta_f1 >= 0 else ''
        marker = '★' if v['pct_correct'] > base_correct and v['f1'] >= base_f1 else ''
        print(f"  {label:<22} │ {v['f1']:6.3f} {v.get('auc',0):6.3f} {v['rec']:6.3f} {v['prec']:6.3f} │ "
              f"{v['pct_missed']:5.1f}% {v['pct_fa']:5.1f}% {v['pct_correct']:6.1f}% │ "
              f"{sign}{delta_f1:.3f} F1 {delta_c:+.1f}% {marker}")

# ══════════════════════════════════════════════════════
# AGGREGATE SUMMARY
# ══════════════════════════════════════════════════════

print(f"\n\n{'#'*120}")
print(f"  AGGREGATE RESULTS — Mean across all {len(ALL_RESULTS)} dataset×model combinations")
print(f"{'#'*120}\n")

print(f"  {'Method':<22} │ {'MeanF1':>7} {'MeanAUC':>7} │ {'%Miss':>7} {'%FAlrt':>7} {'%Right':>7} │ {'WinF1':>5} {'WinAcc':>6}")
print(f"  {'─'*22}─┼─{'─'*7}─{'─'*7}─┼─{'─'*7}─{'─'*7}─{'─'*7}─┼─{'─'*5}─{'─'*6}")

for key, label in VARIANT_KEYS:
    f1s = [r[key]['f1'] for r in ALL_RESULTS]
    aucs = [r[key].get('auc',0) for r in ALL_RESULTS]
    misses = [r[key]['pct_missed'] for r in ALL_RESULTS]
    fas = [r[key]['pct_fa'] for r in ALL_RESULTS]
    cors = [r[key]['pct_correct'] for r in ALL_RESULTS]

    # Count wins vs base
    win_f1 = sum(1 for r in ALL_RESULTS if r[key]['f1'] > r['B0_Base']['f1'] + 0.001)
    win_acc = sum(1 for r in ALL_RESULTS if r[key]['pct_correct'] > r['B0_Base']['pct_correct'] + 0.01)

    print(f"  {label:<22} │ {np.mean(f1s):7.3f} {np.mean(aucs):7.3f} │ "
          f"{np.mean(misses):6.1f}% {np.mean(fas):6.1f}% {np.mean(cors):6.1f}% │ "
          f"{win_f1:>5} {win_acc:>6}")

# By domain
for dom_label in ['IN-DOMAIN', 'OUT-DOMAIN']:
    sub = [r for r in ALL_RESULTS if r['domain'] == dom_label]
    if not sub: continue
    print(f"\n  --- {dom_label} ({len(sub)} tests) ---")
    print(f"  {'Method':<22} │ {'MeanF1':>7} │ {'%Miss':>7} {'%FAlrt':>7} {'%Right':>7}")
    print(f"  {'─'*22}─┼─{'─'*7}─┼─{'─'*7}─{'─'*7}─{'─'*7}")
    for key, label in VARIANT_KEYS:
        f1s = [r[key]['f1'] for r in sub]
        misses = [r[key]['pct_missed'] for r in sub]
        fas = [r[key]['pct_fa'] for r in sub]
        cors = [r[key]['pct_correct'] for r in sub]
        print(f"  {label:<22} │ {np.mean(f1s):7.3f} │ "
              f"{np.mean(misses):6.1f}% {np.mean(fas):6.1f}% {np.mean(cors):6.1f}%")

print(f"\nTotal time: {total:.0f}s")
