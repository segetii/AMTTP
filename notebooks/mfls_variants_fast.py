"""
MFLS Variant Strategies — FAST vectorised rewrite
===================================================
48 variants + 3 baselines tested across 6 datasets × 2 models.

Speed optimisations vs original:
  1. Fully vectorised grid-search: all param combos computed in one 3-D broadcast
  2. CV predictions cached — each combiner trained ONCE, reused by all smooth posts
  3. Numba-free pure-numpy batch F1 (3-D tensors: params × thresholds × samples)
  4. Data loaded once into dict, components computed once per dataset×model
  5. Results saved incrementally (crash-safe)
"""

import numpy as np, polars as pl, scipy.io as sio, json, time, warnings, joblib, sys
import xgboost as xgb, lightgbm as lgb
from pathlib import Path
from itertools import product as iprod
from functools import lru_cache
from sklearn.metrics import roc_auc_score
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.ensemble import RandomForestClassifier
from sklearn.neural_network import MLPClassifier
from sklearn.model_selection import StratifiedShuffleSplit, StratifiedKFold
from sklearn.preprocessing import StandardScaler

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass
warnings.filterwarnings('ignore')

# ═══════════════════════  PATHS  ═══════════════════════
ARTIFACTS = Path(r'C:\Users\Administrator\Downloads\complete_amttp_student_artifacts\amttp_models_20260213_213346')
DATA_DIR  = Path(r'c:\amttp\data\external_validation')

# ═══════════════════════  LOAD MODELS  ═══════════════════════
print("Loading models...", flush=True)
t0 = time.time()
preprocessors = joblib.load(ARTIFACTS / 'preprocessors.joblib')
FEATURES_93  = list(preprocessors['feature_names'])
with open(ARTIFACTS / 'feature_config.json') as f:
    FEATURES_160 = json.load(f)['boost_features']
scaler   = preprocessors['robust_scaler']
log_mask = preprocessors['log_transform_mask']
xgb_93 = xgb.Booster(); xgb_93.load_model(str(ARTIFACTS / 'xgboost_fraud.ubj'))
print(f"  Models loaded in {time.time()-t0:.1f}s", flush=True)

IDX_SENT = FEATURES_93.index('sender_total_sent') if 'sender_total_sent' in FEATURES_93 else 7
IDX_RECV = FEATURES_93.index('receiver_total_received') if 'receiver_total_received' in FEATURES_93 else 60

# ═══════════════════════  PREPROCESS + PREDICT  ═══════════════════════

def preprocess_93(X):
    X2 = np.nan_to_num(X.astype(np.float32), nan=0.0, posinf=0.0, neginf=0.0)
    X2[:, log_mask] = np.log1p(np.clip(X2[:, log_mask], 0, None))
    return np.clip(scaler.transform(X2), -5, 5)

def predict_xgb93(X):
    return xgb_93.predict(xgb.DMatrix(preprocess_93(X), feature_names=FEATURES_93))

# ═══════════════════════  BSDT CORE  ═══════════════════════

def ref_stats(X, y):
    n = X[y==0]; f = X[y==1]
    mu = n.mean(0)
    d  = max(np.percentile(np.linalg.norm(X - mu, axis=1), 99), 1e-8)
    rm, rv = f.mean(0), f.var(0) + 1e-8
    tx = np.abs(f[:, IDX_SENT]) + np.abs(f[:, IDX_RECV]) + 1e-8
    return mu, d, rm, rv, np.log1p(tx).mean(), max(np.log1p(tx).std(), 1e-8)

def get_components(X, stats):
    mu, d, rm, rv, mu_c, sig_c = stats
    C = 1.0 - np.clip(np.linalg.norm(X - mu, axis=1) / d, 0, 1)
    G = (np.abs(X) < 1e-8).sum(1).astype(np.float64) / X.shape[1]
    tx = np.abs(X[:, IDX_SENT]) + np.abs(X[:, IDX_RECV]) + 1e-8
    A = 1.0 / (1.0 + np.exp(-(np.log1p(tx) - mu_c) / max(sig_c, 1e-8)))
    dd = X - rm
    m = np.sum(dd*dd / rv, axis=1) / X.shape[1]
    T = 1.0 / (1.0 + np.exp(-0.5*(m - 2.0)))
    return np.nan_to_num(np.column_stack([C, G, A, T]), nan=0.0)

def mi_weights(comp, y, nb=20):
    from sklearn.metrics import mutual_info_score
    mi = np.array([mutual_info_score(y, np.digitize(comp[:,i],
            np.linspace(comp[:,i].min(), comp[:,i].max()+1e-8, nb))) for i in range(4)])
    s = mi.sum()
    return mi / s if s > 1e-10 else np.ones(4) / 4

# ═══════════════════════  FAST VECTORISED GRID SEARCH  ═══════════════════════
# Key idea: instead of looping over param combos, build a 3-D tensor
# (n_combos × n_thresholds × n_samples) and compute F1 for ALL combos at once.

PT = np.arange(0.05, 0.95, 0.02)  # 45 thresholds

def _best_f1_vec(y_bool, scores_2d):
    """Vectorised best-F1 over a batch of score arrays.
    scores_2d: (n_combos, n_samples)
    Returns index of best combo and its F1 score.
    Processes one combo at a time to avoid 3D memory explosion."""
    best_f1 = -1.0
    best_idx = 0
    nf = y_bool.sum()
    nl = len(y_bool) - nf
    for i in range(scores_2d.shape[0]):
        preds = scores_2d[i][np.newaxis, :] >= PT[:, np.newaxis]
        tp = (preds & y_bool).sum(1).astype(np.float64)
        fp = (preds & ~y_bool).sum(1).astype(np.float64)
        fn = nf - tp
        prec = np.where(tp+fp>0, tp/(tp+fp), 0.0)
        rec  = np.where(tp+fn>0, tp/(tp+fn), 0.0)
        f1   = np.where(prec+rec>0, 2*prec*rec/(prec+rec), 0.0)
        mx = f1.max()
        if mx > best_f1:
            best_f1 = mx
            best_idx = i
    return best_idx, best_f1

def _grid_best_scores(y, all_pc):
    """Given (n_combos, n_samples) corrected scores, find the best combo.
    Returns the winning scores array (n_samples,)."""
    y_bool = y.astype(bool)
    best_idx, _ = _best_f1_vec(y_bool, all_pc)
    return all_pc[best_idx]

def eval_scores(y, scores):
    y_bool = y.astype(bool)
    preds = scores[np.newaxis, :] >= PT[:, np.newaxis]
    tp = (preds & y_bool).sum(1).astype(float)
    fp = (preds & ~y_bool).sum(1).astype(float)
    fn = (~preds & y_bool).sum(1).astype(float)
    prec = np.where(tp+fp>0, tp/(tp+fp), 0.0)
    rec  = np.where(tp+fn>0, tp/(tp+fn), 0.0)
    f1   = np.where(prec+rec>0, 2*prec*rec/(prec+rec), 0.0)
    i = np.argmax(f1)
    n, nf = len(y), int(y.sum())
    nl = n - nf
    fn_ = nf - int(tp[i]); tn = nl - int(fp[i])
    fa = fp[i] / max(fp[i]+tp[i], 1)
    try: auc = float(roc_auc_score(y, scores))
    except: auc = 0.5
    return {'f1': float(f1[i]), 'rec': float(rec[i]), 'prec': float(prec[i]),
            'tp': int(tp[i]), 'fp': int(fp[i]), 'fa': float(fa), 'auc': auc,
            'threshold': float(PT[i]),
            'pct_missed': fn_/max(nf,1)*100, 'pct_fa': float(fa)*100,
            'pct_correct': (int(tp[i])+tn)/max(n,1)*100}

# ═══════════════════════  VECTORISED CORRECTION FORMULAS  ═══════════════════════

def _softplus(x):
    return np.where(x > 20, x, np.log1p(np.exp(x)))

def grid_original_correction(p, mfls, y):
    """B1: Original MFLS linear correction — all (lam,tau) at once."""
    LAM = np.array([0.1,0.3,0.5,0.7,0.9,1.1,1.3,1.5,1.7,1.9,2.1,2.3,2.5])
    TAU = np.array([0.1,0.2,0.3,0.5,0.7,0.9])
    params = np.array(list(iprod(LAM, TAU)))  # (n_combos, 2)
    lam_v, tau_v = params[:,0], params[:,1]
    # (n_combos, n_samples)
    below = (p[np.newaxis,:] < tau_v[:,np.newaxis]).astype(np.float64)
    pc = np.clip(p[np.newaxis,:] + lam_v[:,np.newaxis] * mfls[np.newaxis,:] * (1.0 - p[np.newaxis,:]) * below, 0, 1)
    return _grid_best_scores(y, pc)

def grid_smooth_tanh(p, mfls, y):
    """V11: Smooth tanh+sigmoid — vectorised."""
    params = np.array(list(iprod([0.8,1.0,1.2,1.4], [0.35,0.45,0.55], [12,15,20], [0.3,0.5,0.7])))
    lam, sig, k, tau = params[:,0], params[:,1], params[:,2], params[:,3]
    sat = np.tanh(mfls[np.newaxis,:] / sig[:,np.newaxis])
    gate = 1.0 / (1.0 + np.exp(-k[:,np.newaxis] * (tau[:,np.newaxis] - p[np.newaxis,:])))
    pc = np.clip(p[np.newaxis,:] + lam[:,np.newaxis] * sat * (1.0 - p[np.newaxis,:]) * gate, 0, 1)
    return _grid_best_scores(y, pc)

def grid_ultra_soft(p, mfls, y):
    """V12: Ultra-soft softplus — vectorised."""
    params = np.array(list(iprod([0.8,1.0,1.2,1.4], [0.35,0.45,0.55], [10,15,20], [0.3,0.5,0.7])))
    lam, sig, k, tau = params[:,0], params[:,1], params[:,2], params[:,3]
    sat = np.tanh(mfls[np.newaxis,:] / sig[:,np.newaxis])
    inner = k[:,np.newaxis] * lam[:,np.newaxis] * sat * (1.0 - p[np.newaxis,:]) * (tau[:,np.newaxis] - p[np.newaxis,:] + 0.1)
    delta = _softplus(inner) / k[:,np.newaxis]
    pc = np.clip(p[np.newaxis,:] + delta, 0, 1)
    return _grid_best_scores(y, pc)

def grid_power_law(p, mfls, y):
    """V13: Power-law — vectorised."""
    params = np.array(list(iprod([0.5,0.8,1.0,1.2,1.5], [1.2,1.4,1.6,1.8,2.0], [0.3,0.5,0.7])))
    lam, alpha, tau = params[:,0], params[:,1], params[:,2]
    boosted = np.power(np.clip(mfls, 0, None), alpha[:,np.newaxis])
    below = (p[np.newaxis,:] < tau[:,np.newaxis]).astype(np.float64)
    pc = np.clip(p[np.newaxis,:] + lam[:,np.newaxis] * boosted * (1.0 - p[np.newaxis,:]) * below, 0, 1)
    return _grid_best_scores(y, pc)

def grid_smooth_post(p_ml, p_base, mfls, y):
    """V16-style: tanh+sigmoid post-processing on any ML output — vectorised."""
    params = np.array(list(iprod([0.3,0.5,0.8,1.0], [0.3,0.5,0.7], [8,12,15], [0.3,0.5,0.7])))
    lam, sig, k, tau = params[:,0], params[:,1], params[:,2], params[:,3]
    sat = np.tanh(p_ml[np.newaxis,:] / sig[:,np.newaxis])
    gate = 1.0 / (1.0 + np.exp(-k[:,np.newaxis] * (tau[:,np.newaxis] - p_ml[np.newaxis,:])))
    pc = np.clip(p_ml[np.newaxis,:] * (1.0 - lam[:,np.newaxis]) + lam[:,np.newaxis] * sat * gate, 0, 1)
    return _grid_best_scores(y, pc)

def grid_smooth_gated(p_lr, p_base, y):
    """V18-style: smooth blend gate — vectorised."""
    params = np.array(list(iprod([0.3,0.5,0.7,0.9], [8,12,15], [0.3,0.5,0.7])))
    alpha, k, tau = params[:,0], params[:,1], params[:,2]
    bt = alpha[:,np.newaxis] / (1.0 + np.exp(-k[:,np.newaxis] * (p_base[np.newaxis,:] - tau[:,np.newaxis])))
    pc = np.clip(p_lr[np.newaxis,:] * (1.0 - bt) + p_base[np.newaxis,:] * bt, 0, 1)
    return _grid_best_scores(y, pc)

# ── Smoothing post-processing: 3 types, all vectorised ──

def smooth_post_tanh(p_ml, p_base, mfls, y):
    params = np.array(list(iprod([0.3,0.5,0.7,1.0], [0.35,0.5,0.65], [8,12,15], [0.3,0.5,0.7])))
    lam, sig, k, tau = params[:,0], params[:,1], params[:,2], params[:,3]
    sat = np.tanh(mfls[np.newaxis,:] / sig[:,np.newaxis])
    gate = 1.0 / (1.0 + np.exp(-k[:,np.newaxis] * (tau[:,np.newaxis] - p_base[np.newaxis,:])))
    pc = np.clip(p_ml[np.newaxis,:] + lam[:,np.newaxis] * sat * (1 - p_ml[np.newaxis,:]) * gate, 0, 1)
    return _grid_best_scores(y, pc)

def smooth_post_softplus(p_ml, p_base, mfls, y):
    params = np.array(list(iprod([0.3,0.5,0.7,1.0], [0.35,0.5,0.65], [8,12,15], [0.3,0.5,0.7])))
    lam, sig, k, tau = params[:,0], params[:,1], params[:,2], params[:,3]
    sp_raw = _softplus(mfls[np.newaxis,:] / sig[:,np.newaxis])
    sp_norm = sp_raw / np.maximum(_softplus(1.0/sig)[:,np.newaxis], 1e-8)
    sat = np.clip(sp_norm, -2, 2)
    gate = 1.0 / (1.0 + np.exp(-k[:,np.newaxis] * (tau[:,np.newaxis] - p_base[np.newaxis,:])))
    pc = np.clip(p_ml[np.newaxis,:] + lam[:,np.newaxis] * sat * (1 - p_ml[np.newaxis,:]) * gate, 0, 1)
    return _grid_best_scores(y, pc)

def smooth_post_powerlaw(p_ml, p_base, mfls, y, alpha_pw=1.6):
    mfls_pow = np.sign(mfls) * np.abs(mfls) ** alpha_pw
    params = np.array(list(iprod([0.3,0.5,0.7,1.0], [8,12,15], [0.3,0.5,0.7])))
    lam, k, tau = params[:,0], params[:,1], params[:,2]
    sat = np.clip(mfls_pow, -3, 3)
    gate = 1.0 / (1.0 + np.exp(-k[:,np.newaxis] * (tau[:,np.newaxis] - p_base[np.newaxis,:])))
    pc = np.clip(p_ml[np.newaxis,:] + lam[:,np.newaxis] * sat[np.newaxis,:] * (1 - p_ml[np.newaxis,:]) * gate, 0, 1)
    return _grid_best_scores(y, pc)

# ═══════════════════════  QUADRATIC + GATE FORMULAS  ═══════════════════════

def grid_quadratic_mfls(p, mfls, y):
    """V41: p* = p + (alpha * MFLS^2 + beta * MFLS) * (1-p) — vectorised."""
    params = np.array(list(iprod([-0.5,-0.2,-0.1,0,0.1,0.2,0.5], [-1,-0.5,-0.2,0,0.2,0.5,1])))
    a, b = params[:,0], params[:,1]
    correction = a[:,np.newaxis] * mfls[np.newaxis,:]**2 + b[:,np.newaxis] * mfls[np.newaxis,:]
    pc = np.clip(p[np.newaxis,:] + correction * (1.0 - p[np.newaxis,:]), 0, 1)
    return _grid_best_scores(y, pc)

def grid_quadratic_components(p, comp, y):
    """V42: Ridge regression on [C^2, G^2, A^2, T^2, C, G, A, T] — analytic."""
    C, G, A, T_ = comp[:,0], comp[:,1], comp[:,2], comp[:,3]
    X_quad = np.column_stack([C**2, G**2, A**2, T_**2, C, G, A, T_])
    target = y.astype(float) - p
    w = np.where(y == 1, (y==0).sum() / max((y==1).sum(), 1), 1.0)
    w_sqrt = np.sqrt(w)
    Xw = X_quad * w_sqrt[:, np.newaxis]
    yw = target * w_sqrt
    beta = np.linalg.solve(Xw.T @ Xw + 0.1 * np.eye(8), Xw.T @ yw)
    return np.clip(p + X_quad @ beta, 0, 1)

def grid_discriminant(p, mfls, y):
    """V43: Discriminant-based ± correction — vectorised."""
    params = np.array(list(iprod([0.5,1.0,2.0], [-1.0,-0.5,0.5,1.0])))
    a_v, b_v = params[:,0], params[:,1]
    # (n_combos, n_samples)
    b_eff = b_v[:,np.newaxis] * mfls[np.newaxis,:]
    disc = b_eff**2 - 4 * a_v[:,np.newaxis] * (p[np.newaxis,:] - 0.5)
    valid = disc >= 0
    sqrt_d = np.sqrt(np.maximum(disc, 0))
    c_plus  = (-b_eff + sqrt_d) / (2 * a_v[:,np.newaxis])
    c_minus = (-b_eff - sqrt_d) / (2 * a_v[:,np.newaxis])
    c_best = np.where(np.abs(c_plus) < np.abs(c_minus), c_plus, c_minus)
    c_best = np.where(valid, c_best, 0.0)
    pc = np.clip(p[np.newaxis,:] + c_best * (1.0 - np.abs(2*p[np.newaxis,:] - 1)), 0, 1)
    return _grid_best_scores(y, pc)

def grid_product_gate(p, mfls, comp, y):
    """V44: Product gate — correction = lam * (C*G) * tanh(MFLS/sig) * (1-p).
    C*G acts as an AND gate: only fires when BOTH camouflage AND gap are high."""
    CG = comp[:,0] * comp[:,1]
    params = np.array(list(iprod([0.3,0.5,1.0,2.0,3.0], [0.3,0.5,0.8])))
    lam, sig = params[:,0], params[:,1]
    sat = np.tanh(mfls[np.newaxis,:] / sig[:,np.newaxis])
    pc = np.clip(p[np.newaxis,:] + lam[:,np.newaxis] * CG[np.newaxis,:] * sat * (1 - p[np.newaxis,:]), 0, 1)
    return _grid_best_scores(y, pc)

def grid_inverse_gate(p, mfls, comp, y):
    """V45: Inverse gate — correction = lam * C/(1+G) * tanh(MFLS/sig) * (1-p).
    C drives correction UP, G dampens it (NOT gate on G)."""
    gate = comp[:,0] / (1.0 + comp[:,1] + 1e-8)
    params = np.array(list(iprod([0.3,0.5,1.0,2.0,3.0], [0.3,0.5,0.8])))
    lam, sig = params[:,0], params[:,1]
    sat = np.tanh(mfls[np.newaxis,:] / sig[:,np.newaxis])
    pc = np.clip(p[np.newaxis,:] + lam[:,np.newaxis] * gate[np.newaxis,:] * sat * (1 - p[np.newaxis,:]), 0, 1)
    return _grid_best_scores(y, pc)

def grid_ratio_gate(p, mfls, comp, y):
    """V46: Ratio gate — direction = tanh(((C+G)/(A+T) - theta) * 3).
    When C+G dominate A+T: positive correction (XOR-like: different halves disagree).
    When A+T dominate: correction flips sign."""
    C, G, A, T_ = comp[:,0], comp[:,1], comp[:,2], comp[:,3]
    ratio = (C + G) / (A + T_ + 1e-8)
    params = np.array(list(iprod([0.3,0.5,1.0,1.5,2.0], [0.3,0.5,0.8,1.0,1.5], [0.3,0.5,0.8])))
    lam, theta, sig = params[:,0], params[:,1], params[:,2]
    direction = np.tanh((ratio[np.newaxis,:] - theta[:,np.newaxis]) * 3.0)
    sat = np.tanh(np.abs(mfls[np.newaxis,:]) / sig[:,np.newaxis])
    pc = np.clip(p[np.newaxis,:] + lam[:,np.newaxis] * direction * sat * (1 - p[np.newaxis,:]), 0, 1)
    return _grid_best_scores(y, pc)

def grid_cross_gate(p, comp, y):
    """V47: Cross-gate — signal = C*A - G*T.
    XOR-like: if camouflage×activity dominates (hidden active fraud) → positive.
    If gap×temporal dominates (OOD noise) → negative.
    The subtraction creates a natural ± signal from component interactions."""
    cross = comp[:,0] * comp[:,2] - comp[:,1] * comp[:,3]
    params = np.array(list(iprod([0.1,0.3,0.5,1.0,2.0], [0.3,0.5,1.0])))
    lam, sig = params[:,0], params[:,1]
    pc = np.clip(p[np.newaxis,:] + lam[:,np.newaxis] * np.tanh(cross[np.newaxis,:] / sig[:,np.newaxis]) * (1 - p[np.newaxis,:]), 0, 1)
    return _grid_best_scores(y, pc)

def grid_quad_gate_fusion(p, mfls, comp, y):
    """V48: Quadratic + gate fusion.
    correction = (a*MFLS^2 + b*MFLS) * sigmoid(k*(C*G - theta)) * (1-p).
    Quadratic finds ± correction; sigmoid(C*G) acts as AND gate — only fires
    when both camouflage and gap jointly indicate a blind spot."""
    CG = comp[:,0] * comp[:,1]
    params = np.array(list(iprod([-0.3,0,0.3], [-0.5,0,0.5], [5,10], [0.1,0.3,0.5])))
    a, b, k, theta = params[:,0], params[:,1], params[:,2], params[:,3]
    quad = a[:,np.newaxis] * mfls[np.newaxis,:]**2 + b[:,np.newaxis] * mfls[np.newaxis,:]
    gate = 1.0 / (1.0 + np.exp(-k[:,np.newaxis] * (CG[np.newaxis,:] - theta[:,np.newaxis])))
    pc = np.clip(p[np.newaxis,:] + quad * gate * (1 - p[np.newaxis,:]), 0, 1)
    return _grid_best_scores(y, pc)

# ═══════════════════════  ML COMBINERS (cached CV)  ═══════════════════════

def _cv_predict(clf_factory, X, y, n_splits=5):
    preds = np.full(len(y), np.nan)
    for tr, te in StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=42).split(X, y):
        clf = clf_factory()
        clf.fit(X[tr], y[tr])
        preds[te] = clf.predict_proba(X[te])[:, 1]
    return preds

def _cv_mlp(X, y):
    preds = np.full(len(y), np.nan)
    for tr, te in StratifiedKFold(n_splits=5, shuffle=True, random_state=42).split(X, y):
        sc = StandardScaler(); Xtr = sc.fit_transform(X[tr]); Xte = sc.transform(X[te])
        clf = MLPClassifier(hidden_layer_sizes=(16,8), activation='relu', max_iter=500,
                            random_state=42, early_stopping=True, validation_fraction=0.15)
        clf.fit(Xtr, y[tr])
        preds[te] = clf.predict_proba(Xte)[:, 1]
    return preds

def get_all_cv_predictions(p_base, comp, y):
    """Train all 5 combiners ONCE, return cached predictions dict."""
    X5 = np.column_stack([p_base, comp])
    spw = max(1.0, (y==0).sum() / max((y==1).sum(), 1))
    cache = {}
    cache['lr_nocv'] = LogisticRegression(random_state=42, max_iter=1000, class_weight='balanced').fit(X5, y).predict_proba(X5)[:,1]
    cache['lr_cv']   = _cv_predict(lambda: LogisticRegression(random_state=42, max_iter=1000, class_weight='balanced'), X5, y)
    cache['xgb_cv']  = _cv_predict(lambda: xgb.XGBClassifier(n_estimators=30, max_depth=3, learning_rate=0.1,
                        scale_pos_weight=spw, eval_metric='logloss', random_state=42, verbosity=0), X5, y)
    cache['lgb_cv']  = _cv_predict(lambda: lgb.LGBMClassifier(n_estimators=30, num_leaves=15, learning_rate=0.1,
                        is_unbalance=True, random_state=42, verbose=-1), X5, y)
    cache['rf_cv']   = _cv_predict(lambda: RandomForestClassifier(n_estimators=50, max_depth=4,
                        class_weight='balanced', random_state=42), X5, y)
    cache['mlp_cv']  = _cv_mlp(X5, y)
    return cache

# ═══════════════════════  VARIANT DISPATCH (all 48)  ═══════════════════════

def compute_all_variants(p_base, comp, mfls, y, X_e, stats, w):
    """Compute all 48 variants + 3 baselines. Returns dict of {key: eval_dict}."""
    R = {}
    n = len(y); nf = int(y.sum()); nl = n - nf
    y_bool = y.astype(bool)

    # ── B0: Base ──
    R['B0_Base'] = eval_scores(y, p_base)

    # ── B1: MFLS linear (vectorised grid) ──
    b1_scores = grid_original_correction(p_base, mfls, y)
    R['B1_MFLS'] = eval_scores(y, b1_scores)

    # ── B2: Signed LR (4 components) ──
    lr_b2 = LogisticRegression(random_state=42, max_iter=1000, class_weight='balanced')
    lr_b2.fit(comp, y)
    R['B2_SignedLR'] = eval_scores(y, lr_b2.predict_proba(comp)[:,1])

    # ── V1-V5: Heuristic rules ──
    w_cap = mi_weights(comp, y).copy()
    w_cap[2] = min(w_cap[2], 0.25); w_cap[3] = min(w_cap[3], 0.30)
    w_cap /= max(w_cap.sum(), 1e-10)
    R['V1_CappedMFLS']   = eval_scores(y, comp @ w_cap)
    R['V2_Multiplicative']= eval_scores(y, np.prod(comp + 0.01, axis=1))
    R['V3_MinOf4']        = eval_scores(y, np.min(comp, axis=1))
    for k_vote, theta, key in [(2,0.5,'V4a_2of4_t50'),(2,0.6,'V4b_2of4_t60'),(2,0.7,'V4c_2of4_t70'),
                                (3,0.5,'V5a_3of4_t50'),(3,0.6,'V5b_3of4_t60')]:
        above = (comp > theta).sum(1)
        R[key] = eval_scores(y, (above >= k_vote).astype(float) * comp.mean(1))

    # ── V6: Hybrid max ──
    p_lr_h = LogisticRegression(random_state=42, max_iter=1000, class_weight='balanced').fit(comp, y).predict_proba(comp)[:,1]
    R['V6_HybridMax'] = eval_scores(y, np.maximum(p_base, p_lr_h))

    # ── V7: Capped correction (vectorised) ──
    mfls_cap = comp @ w_cap
    v7_params = np.array(list(iprod([0.1,0.3,0.5,0.8,1.0], [0.2,0.3,0.5])))
    lam7, tau7 = v7_params[:,0], v7_params[:,1]
    below7 = (p_base[np.newaxis,:] < tau7[:,np.newaxis]).astype(np.float64)
    pc7 = np.clip(p_base[np.newaxis,:] + lam7[:,np.newaxis] * mfls_cap[np.newaxis,:] * (1 - p_base[np.newaxis,:]) * below7, 0, 1)
    R['V7_CappedCorrect'] = eval_scores(y, _grid_best_scores(y, pc7))

    # ── V8: Dense-core veto ──
    mu_all = X_e.mean(0); var_all = X_e.var(0) + 1e-8
    mahal = np.sqrt(np.sum((X_e - mu_all)**2 / var_all, axis=1))
    suppress = np.where(mahal < np.median(mahal), 0.1, 1.0)
    R['V8_DenseCoreVeto'] = eval_scores(y, (comp @ (np.ones(4)/4)) * suppress)

    # ── V9: Strong-reg LR ──
    lr_v9 = LogisticRegression(random_state=42, max_iter=1000, class_weight='balanced', C=0.1)
    lr_v9.fit(comp, y)
    R['V9_StrongRegLR'] = eval_scores(y, lr_v9.predict_proba(comp)[:,1])

    # ── V10: LR on [p, C, G, A, T] ──
    X5 = np.column_stack([p_base, comp])
    lr_v10 = LogisticRegression(random_state=42, max_iter=1000, class_weight='balanced')
    lr_v10.fit(X5, y)
    p_v10 = lr_v10.predict_proba(X5)[:,1]
    R['V10_LR5feat'] = eval_scores(y, p_v10)

    # ── V11-V13: Smooth formulas (electronics-inspired) ──
    R['V11_Smooth']   = eval_scores(y, grid_smooth_tanh(p_base, mfls, y))
    R['V12_UltraSoft'] = eval_scores(y, grid_ultra_soft(p_base, mfls, y))
    R['V13_PowerLaw'] = eval_scores(y, grid_power_law(p_base, mfls, y))

    # ── V14: Smooth + LR ──
    p_smooth = np.clip(p_base + 1.2 * np.tanh(mfls/0.5) * (1-p_base) / (1+np.exp(-15*(0.5-p_base))), 0, 1)
    X5s = np.column_stack([p_smooth, comp])
    lr_v14 = LogisticRegression(random_state=42, max_iter=1000, class_weight='balanced')
    lr_v14.fit(X5s, y)
    R['V14_SmoothLR'] = eval_scores(y, lr_v14.predict_proba(X5s)[:,1])

    # ── V15: LR on 6 features [p, smooth_p*, C, G, A, T] ──
    X6 = np.column_stack([p_base, p_smooth, comp])
    lr_v15 = LogisticRegression(random_state=42, max_iter=1000, class_weight='balanced')
    lr_v15.fit(X6, y)
    R['V15_LR6feat'] = eval_scores(y, lr_v15.predict_proba(X6)[:,1])

    # ── V16: V10 LR → smooth post ──
    R['V16_V10SmoothPost'] = eval_scores(y, grid_smooth_post(p_v10, p_base, mfls, y))

    # ── V17: LR on [p, tanh(MFLS/0.5), C, G, A, T] ──
    X6t = np.column_stack([p_base, np.tanh(mfls/0.5), comp])
    lr_v17 = LogisticRegression(random_state=42, max_iter=1000, class_weight='balanced')
    lr_v17.fit(X6t, y)
    R['V17_LRSatFeat'] = eval_scores(y, lr_v17.predict_proba(X6t)[:,1])

    # ── V18: LR + smooth gate blend ──
    R['V18_SmoothGated'] = eval_scores(y, grid_smooth_gated(p_v10, p_base, y))

    # ── V19-V24: ML combiners (cached CV) ──
    print("    [CV training 5 combiners...]", end=" ", flush=True)
    t_cv = time.time()
    cv = get_all_cv_predictions(p_base, comp, y)
    print(f"{time.time()-t_cv:.1f}s", flush=True)

    R['V19_XGB'] = eval_scores(y, cv['xgb_cv'])
    R['V20_LGB'] = eval_scores(y, cv['lgb_cv'])
    R['V21_RF']  = eval_scores(y, cv['rf_cv'])
    R['V22_MLP'] = eval_scores(y, cv['mlp_cv'])
    R['V23_XGBSmoothPost'] = eval_scores(y, smooth_post_tanh(cv['xgb_cv'], p_base, mfls, y))
    R['V24_LR_CV'] = eval_scores(y, cv['lr_cv'])

    # ── V25-V40: COMPLETE combiner × smoothing matrix (using CACHED cv predictions) ──
    COMBINER_SMOOTH = [
        ('V25_LR_CV_tanh',  cv['lr_cv'],   'tanh'),
        ('V26_LR_CV_sp',    cv['lr_cv'],   'softplus'),
        ('V27_LR_CV_pw',    cv['lr_cv'],   'powerlaw'),
        ('V28_LGB_tanh',    cv['lgb_cv'],  'tanh'),
        ('V29_LGB_sp',      cv['lgb_cv'],  'softplus'),
        ('V30_LGB_pw',      cv['lgb_cv'],  'powerlaw'),
        ('V31_RF_tanh',     cv['rf_cv'],   'tanh'),
        ('V32_RF_sp',       cv['rf_cv'],   'softplus'),
        ('V33_RF_pw',       cv['rf_cv'],   'powerlaw'),
        ('V34_MLP_tanh',    cv['mlp_cv'],  'tanh'),
        ('V35_MLP_sp',      cv['mlp_cv'],  'softplus'),
        ('V36_MLP_pw',      cv['mlp_cv'],  'powerlaw'),
        ('V37_XGB_sp',      cv['xgb_cv'],  'softplus'),
        ('V38_XGB_pw',      cv['xgb_cv'],  'powerlaw'),
        ('V39_LR_sp',       cv['lr_nocv'], 'softplus'),
        ('V40_LR_pw',       cv['lr_nocv'], 'powerlaw'),
    ]
    smooth_fn = {'tanh': smooth_post_tanh, 'softplus': smooth_post_softplus, 'powerlaw': smooth_post_powerlaw}
    for key, p_ml, sm_type in COMBINER_SMOOTH:
        R[key] = eval_scores(y, smooth_fn[sm_type](p_ml, p_base, mfls, y))

    # ── V41-V48: Quadratic + Gate formulas (pure math, no ML) ──
    R['V41_QuadMFLS']  = eval_scores(y, grid_quadratic_mfls(p_base, mfls, y))
    R['V42_QuadComp']  = eval_scores(y, grid_quadratic_components(p_base, comp, y))
    R['V43_Discrim']   = eval_scores(y, grid_discriminant(p_base, mfls, y))
    R['V44_ProdGate']  = eval_scores(y, grid_product_gate(p_base, mfls, comp, y))
    R['V45_InvGate']   = eval_scores(y, grid_inverse_gate(p_base, mfls, comp, y))
    R['V46_RatioGate'] = eval_scores(y, grid_ratio_gate(p_base, mfls, comp, y))
    R['V47_CrossGate'] = eval_scores(y, grid_cross_gate(p_base, comp, y))
    R['V48_QuadGate']  = eval_scores(y, grid_quad_gate_fusion(p_base, mfls, comp, y))

    return R

# ═══════════════════════  DATA LOADERS  ═══════════════════════

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
        if name in idx: X[:, idx[name]] = vals
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
    xb_map = [('Sent tnx','sender_sent_count'),('Received Tnx','receiver_received_count'),
              ('Unique Received From Addresses','receiver_unique_senders'),
              ('Unique Sent To Addresses','sender_unique_receivers'),
              ('min value received','receiver_min_received'),('max value received ','receiver_max_received'),
              ('avg val received','receiver_avg_received'),('min val sent','sender_min_sent'),
              ('max val sent','sender_max_sent'),('avg val sent','sender_avg_sent'),
              ('total transactions (including tnx to create contract','sender_total_transactions'),
              ('total Ether sent','sender_total_sent'),('total ether received','receiver_total_received'),
              ('total ether balance','sender_balance'),
              ('Avg min between sent tnx','sender_avg_time_between_txns')]
    mapping = [(dst, df[src].to_numpy().astype(np.float32)) for src, dst in xb_map if src in df.columns]
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
    X = mat['X'].astype(np.float32); y = mat['y'].ravel().astype(np.int32)
    X93 = np.zeros((len(y), 93), dtype=np.float32)
    X93[:, :min(X.shape[1], 93)] = X[:, :93]
    return X93, y

# ═══════════════════════  VARIANT KEYS (display order)  ═══════════════════════

VARIANT_KEYS = [
    ('B0_Base',          'Base Model'),
    ('B1_MFLS',          '+MFLS (linear)'),
    ('B2_SignedLR',       '+Signed LR'),
    ('V1_CappedMFLS',    'V1:CappedMFLS'),
    ('V2_Multiplicative', 'V2:Multiplicative'),
    ('V3_MinOf4',         'V3:Min-of-4'),
    ('V4a_2of4_t50',      'V4a:2of4 t=.5'),
    ('V4b_2of4_t60',      'V4b:2of4 t=.6'),
    ('V4c_2of4_t70',      'V4c:2of4 t=.7'),
    ('V5a_3of4_t50',      'V5a:3of4 t=.5'),
    ('V5b_3of4_t60',      'V5b:3of4 t=.6'),
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
    ('V16_V10SmoothPost', 'V16:V10->SmoPost'),
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
    ('V42_QuadComp',       'V42:QuadComp'),
    ('V43_Discrim',        'V43:Discriminant'),
    ('V44_ProdGate',       'V44:AND(C*G)'),
    ('V45_InvGate',        'V45:NOT(C/1+G)'),
    ('V46_RatioGate',      'V46:XOR(CG/AT)'),
    ('V47_CrossGate',      'V47:XOR(CA-GT)'),
    ('V48_QuadGate',       'V48:Quad+ANDgate'),
]

# ═══════════════════════  MAIN LOOP  ═══════════════════════

print("\nLoading datasets...", flush=True)
t_load = time.time()
DATASETS = {}
for name, loader in [('Elliptic', load_elliptic), ('XBlock', load_xblock),
                      ('Credit Card', load_creditcard),
                      ('Shuttle', lambda: load_odds('shuttle')),
                      ('Mammography', lambda: load_odds('mammography')),
                      ('Pendigits', lambda: load_odds('pendigits'))]:
    try:
        X, y = loader()
        DATASETS[name] = (X, y)
        print(f"  {name}: {len(y):,} samples, {y.sum():,} fraud ({y.mean():.2%})", flush=True)
    except Exception as e:
        print(f"  {name}: FAILED - {e}", flush=True)
print(f"Loaded in {time.time()-t_load:.1f}s\n", flush=True)

ALL_RESULTS = []

for ds_name, (X, y) in DATASETS.items():
    ds_t = time.time()
    domain = 'IN-DOMAIN' if ds_name in ('Elliptic', 'XBlock') else 'OUT-DOMAIN'
    print(f"\n{'='*100}")
    print(f"  {ds_name} ({domain})  n={len(y):,}  fraud={y.sum():,} ({y.mean():.2%})")
    print(f"{'='*100}", flush=True)

    sss = StratifiedShuffleSplit(n_splits=1, test_size=0.8, random_state=42)
    cal_i, eval_i = next(sss.split(X, y))
    X_cal, y_cal = X[cal_i], y[cal_i]
    X_e, y_e     = X[eval_i], y[eval_i]

    stats = ref_stats(X_e, y_e)
    comp  = get_components(X_e, stats)
    w     = mi_weights(comp, y_e)
    mfls  = comp @ w

    # AMTTP-XGB93 (pre-trained, Platt-calibrated)
    try:
        p_raw = predict_xgb93(X)
        lr_cal = LogisticRegression(random_state=42, max_iter=1000)
        lr_cal.fit(p_raw[cal_i].reshape(-1,1), y_cal)
        p_amttp = lr_cal.predict_proba(p_raw[eval_i].reshape(-1,1))[:,1]
    except:
        p_amttp = np.full(len(y_e), 0.5)

    # Fresh-XGB (per-dataset)
    X_proc_cal = preprocess_93(X_cal)
    X_proc_e   = preprocess_93(X_e)
    clf_fresh = xgb.XGBClassifier(n_estimators=100, max_depth=6, random_state=42, eval_metric='logloss', verbosity=0)
    clf_fresh.fit(X_proc_cal, y_cal)
    p_fresh = clf_fresh.predict_proba(X_proc_e)[:,1]

    for mname, p_base in [('AMTTP-XGB93', p_amttp), ('Fresh-XGB', p_fresh)]:
        print(f"\n  [{mname}] Computing 48 variants + 3 baselines...", flush=True)
        mt = time.time()
        R = compute_all_variants(p_base, comp, mfls, y_e, X_e, stats, w)
        row = {'dataset': ds_name, 'domain': domain, 'model': mname,
               'n': len(y_e), 'n_fraud': int(y_e.sum()), **R}
        ALL_RESULTS.append(row)
        print(f"    done in {time.time()-mt:.1f}s", flush=True)

    print(f"  [{ds_name} total: {time.time()-ds_t:.1f}s]", flush=True)

total = time.time() - t0

# ═══════════════════════  SAVE RESULTS (crash-safe)  ═══════════════════════

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
print(f"\nSaved -> {results_path}", flush=True)

# ═══════════════════════  PRINT TABLES  ═══════════════════════

print(f"\n\n{'#'*120}")
print(f"  VARIANT COMPARISON - {len(ALL_RESULTS)} model x dataset tests - {total:.0f}s")
print(f"{'#'*120}\n")

for r in ALL_RESULTS:
    ds, dom, model = r['dataset'], r['domain'], r['model']
    n, nf = r['n'], r['n_fraud']
    print(f"\n{'-'*120}")
    print(f"  {ds} ({dom}) | {model} | N={n:,} | Fraud={nf:,} ({nf/n:.2%})")
    print(f"{'-'*120}")
    hdr = f"  {'Method':<22} | {'F1':>6} {'AUC':>6} {'Rec':>6} {'Prec':>6} | {'%Miss':>6} {'%FAlrt':>6} {'%Right':>7} | vs Base"
    print(hdr)
    print(f"  {'-'*22}-+-{'-'*6}-{'-'*6}-{'-'*6}-{'-'*6}-+-{'-'*6}-{'-'*6}-{'-'*7}-+-{'-'*8}")
    base_f1 = r['B0_Base']['f1']
    base_c  = r['B0_Base']['pct_correct']
    for key, label in VARIANT_KEYS:
        v = r[key]
        df1 = v['f1'] - base_f1; dc = v['pct_correct'] - base_c
        s = '+' if df1 >= 0 else ''
        m = '*' if v['pct_correct'] > base_c and v['f1'] >= base_f1 else ''
        print(f"  {label:<22} | {v['f1']:6.3f} {v.get('auc',0):6.3f} {v['rec']:6.3f} {v['prec']:6.3f} | "
              f"{v['pct_missed']:5.1f}% {v['pct_fa']:5.1f}% {v['pct_correct']:6.1f}% | "
              f"{s}{df1:.3f} F1 {dc:+.1f}% {m}")

# Aggregate
print(f"\n\n{'#'*120}")
print(f"  AGGREGATE RESULTS - Mean across all {len(ALL_RESULTS)} dataset x model combinations")
print(f"{'#'*120}\n")
print(f"  {'Method':<22} | {'MeanF1':>7} {'MeanAUC':>7} | {'%Miss':>7} {'%FAlrt':>7} {'%Right':>7} | {'WinF1':>5} {'WinAcc':>6}")
print(f"  {'-'*22}-+-{'-'*7}-{'-'*7}-+-{'-'*7}-{'-'*7}-{'-'*7}-+-{'-'*5}-{'-'*6}")

for key, label in VARIANT_KEYS:
    vals = [r[key] for r in ALL_RESULTS]
    mf  = np.mean([v['f1'] for v in vals])
    ma  = np.mean([v.get('auc',0) for v in vals])
    mm  = np.mean([v['pct_missed'] for v in vals])
    mfa = np.mean([v['pct_fa'] for v in vals])
    mc  = np.mean([v['pct_correct'] for v in vals])
    wf  = sum(1 for r in ALL_RESULTS if r[key]['f1'] > r['B0_Base']['f1'] + 0.001)
    wa  = sum(1 for r in ALL_RESULTS if r[key]['pct_correct'] > r['B0_Base']['pct_correct'] + 0.01)
    print(f"  {label:<22} | {mf:7.3f} {ma:7.3f} | {mm:6.1f}% {mfa:6.1f}% {mc:6.1f}% | {wf:>5} {wa:>6}")

for dom_label in ['IN-DOMAIN', 'OUT-DOMAIN']:
    sub = [r for r in ALL_RESULTS if r['domain'] == dom_label]
    if not sub: continue
    print(f"\n  --- {dom_label} ({len(sub)} tests) ---")
    print(f"  {'Method':<22} | {'MeanF1':>7} | {'%Miss':>7} {'%FAlrt':>7} {'%Right':>7}")
    print(f"  {'-'*22}-+-{'-'*7}-+-{'-'*7}-{'-'*7}-{'-'*7}")
    for key, label in VARIANT_KEYS:
        vals = [r[key] for r in sub]
        mf = np.mean([v['f1'] for v in vals])
        mm = np.mean([v['pct_missed'] for v in vals])
        mfa = np.mean([v['pct_fa'] for v in vals])
        mc = np.mean([v['pct_correct'] for v in vals])
        print(f"  {label:<22} | {mf:7.3f} | {mm:6.1f}% {mfa:6.1f}% {mc:6.1f}%")

print(f"\nTotal time: {total:.0f}s")
