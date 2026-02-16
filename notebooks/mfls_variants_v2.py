"""
MFLS Variants V2 - New Approaches (Colab Edition)
====================================================
~57 NEW variant strategies not tested in V1 (mfls_variants_fast.py).
Old V1 results (30 variants x 12 dataset-model combos) loaded separately.
New variants evaluated identically and merged at end.

GOOGLE DRIVE SETUP: Upload these to Drive/AMTTP/:
  1. amttp_models_20260213_213346/  (full folder)
  2. data/external_validation/      (full folder)
  3. mfls_variants_results.json     (old V1 results)

COLAB: pip install polars xgboost lightgbm scikit-learn scipy joblib
"""

import numpy as np, json, time, warnings, joblib, sys, os
import xgboost as xgb
from pathlib import Path
from scipy import stats as sp_stats
from scipy.stats import chi2, boxcox, yeojohnson
from sklearn.metrics import roc_auc_score
from sklearn.covariance import MinCovDet
from sklearn.neighbors import LocalOutlierFactor, NearestNeighbors
from sklearn.mixture import GaussianMixture
from sklearn.svm import OneClassSVM
from sklearn.decomposition import PCA
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis, QuadraticDiscriminantAnalysis
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import QuantileTransformer, PolynomialFeatures
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.model_selection import StratifiedShuffleSplit
try: import polars as pl; USE_POLARS = True
except: import pandas as pd; USE_POLARS = False

try: sys.stdout.reconfigure(encoding='utf-8')
except: pass
warnings.filterwarnings('ignore')
np.set_printoptions(precision=4, suppress=True)

# ========================= PATHS =========================
# For Colab: set IS_COLAB = True and adjust DRIVE_ROOT
IS_COLAB = False
if IS_COLAB:
    from google.colab import drive
    drive.mount('/content/drive')
    DRIVE_ROOT    = '/content/drive/MyDrive/AMTTP'
    ARTIFACTS_DIR = Path(f'{DRIVE_ROOT}/amttp_models_20260213_213346')
    DATA_DIR      = Path(f'{DRIVE_ROOT}/data/external_validation')
    OLD_RESULTS_P = Path(f'{DRIVE_ROOT}/mfls_variants_results.json')
    OUTPUT_DIR    = Path(f'{DRIVE_ROOT}/results')
else:
    ARTIFACTS_DIR = Path(r'C:\Users\Administrator\Downloads\complete_amttp_student_artifacts\amttp_models_20260213_213346')
    DATA_DIR      = Path(r'c:\amttp\data\external_validation')
    OLD_RESULTS_P = Path(r'c:\amttp\papers\mfls_variants_results.json')
    OUTPUT_DIR    = Path(r'c:\amttp\papers')

# ========================= LOAD MODELS =========================
print("Loading models...", flush=True)
t0 = time.time()
preprocessors = joblib.load(ARTIFACTS_DIR / 'preprocessors.joblib')
FEATURES_93 = list(preprocessors['feature_names'])
scaler   = preprocessors['robust_scaler']
log_mask = preprocessors['log_transform_mask']
xgb_93 = xgb.Booster(); xgb_93.load_model(str(ARTIFACTS_DIR / 'xgboost_fraud.ubj'))
IDX_SENT = FEATURES_93.index('sender_total_sent') if 'sender_total_sent' in FEATURES_93 else 7
IDX_RECV = FEATURES_93.index('receiver_total_received') if 'receiver_total_received' in FEATURES_93 else 60
print(f"  Models loaded in {time.time()-t0:.1f}s", flush=True)

# ========================= CORE FUNCTIONS =========================

def preprocess_93(X):
    X2 = np.nan_to_num(X.astype(np.float32), nan=0., posinf=0., neginf=0.)
    X2[:, log_mask] = np.log1p(np.clip(X2[:, log_mask], 0, None))
    return np.clip(scaler.transform(X2), -5, 5)

def predict_xgb93(X):
    return xgb_93.predict(xgb.DMatrix(preprocess_93(X), feature_names=FEATURES_93))

def ref_stats(X, y):
    n, f = X[y == 0], X[y == 1]
    mu = n.mean(0)
    d = max(np.percentile(np.linalg.norm(X - mu, axis=1), 99), 1e-8)
    rm, rv = f.mean(0), f.var(0) + 1e-8
    tx = np.abs(f[:, IDX_SENT]) + np.abs(f[:, IDX_RECV]) + 1e-8
    return mu, d, rm, rv, np.log1p(tx).mean(), max(np.log1p(tx).std(), 1e-8)

def get_components(X, stats):
    mu, d, rm, rv, mu_c, sig_c = stats
    C = 1.0 - np.clip(np.linalg.norm(X - mu, axis=1) / d, 0, 1)
    G = (np.abs(X) < 1e-8).sum(1).astype(np.float64) / X.shape[1]
    tx = np.abs(X[:, IDX_SENT]) + np.abs(X[:, IDX_RECV]) + 1e-8
    A = 1.0 / (1.0 + np.exp(-(np.log1p(tx) - mu_c) / max(sig_c, 1e-8)))
    dd = X - rm; m = np.sum(dd * dd / rv, axis=1) / X.shape[1]
    T = 1.0 / (1.0 + np.exp(-0.5 * (m - 2.0)))
    return np.nan_to_num(np.column_stack([C, G, A, T]), nan=0.0)

def mi_weights(comp, y, nb=20):
    from sklearn.metrics import mutual_info_score
    mi = np.array([mutual_info_score(y, np.digitize(comp[:, i],
            np.linspace(comp[:, i].min(), comp[:, i].max() + 1e-8, nb))) for i in range(4)])
    s = mi.sum()
    return mi / s if s > 1e-10 else np.full(4, 0.25)

PT = np.arange(0.05, 0.95, 0.02)

def eval_scores(y, scores):
    y_b = y.astype(bool)
    scores = np.asarray(scores, dtype=np.float64)
    preds = scores[np.newaxis, :] >= PT[:, np.newaxis]
    tp = (preds & y_b).sum(1).astype(np.float64)
    fp = (preds & ~y_b).sum(1).astype(np.float64)
    fn = y_b.sum() - tp
    prec = np.where(tp + fp > 0, tp / (tp + fp), 0.0)
    rec  = np.where(tp + fn > 0, tp / (tp + fn), 0.0)
    f1   = np.where(prec + rec > 0, 2 * prec * rec / (prec + rec), 0.0)
    i = np.argmax(f1)
    n, nf = len(y), int(y.sum()); nl = n - nf
    fn_ = nf - int(tp[i]); tn = nl - int(fp[i])
    fa = fp[i] / max(fp[i] + tp[i], 1)
    try: auc = float(roc_auc_score(y, scores))
    except: auc = 0.5
    return {'f1': float(f1[i]), 'rec': float(rec[i]), 'prec': float(prec[i]),
            'tp': int(tp[i]), 'fp': int(fp[i]), 'fa': float(fa), 'auc': auc,
            'threshold': float(PT[i]),
            'pct_missed': fn_ / max(nf, 1) * 100,
            'pct_fa': float(fa) * 100,
            'pct_correct': (int(tp[i]) + tn) / max(n, 1) * 100}

def grid_best(y, all_pc):
    y_b = y.astype(bool); nf = y_b.sum()
    best_f1, best_i = -1.0, 0
    for i in range(all_pc.shape[0]):
        preds = all_pc[i][np.newaxis, :] >= PT[:, np.newaxis]
        tp = (preds & y_b).sum(1).astype(np.float64)
        fp = (preds & ~y_b).sum(1).astype(np.float64)
        fn = nf - tp
        p = np.where(tp + fp > 0, tp / (tp + fp), 0.0)
        r = np.where(tp + fn > 0, tp / (tp + fn), 0.0)
        f = np.where(p + r > 0, 2 * p * r / (p + r), 0.0)
        mx = f.max()
        if mx > best_f1: best_f1, best_i = mx, i
    return all_pc[best_i]

# ========================= DATA LOADERS =========================

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

def _read_csv(path):
    if USE_POLARS: return pl.read_csv(str(path))
    else: return pd.read_csv(str(path))

def _col(df, name):
    if USE_POLARS: return df[name].to_numpy()
    else: return df[name].values

def _cols_starting(df, prefix):
    if USE_POLARS: return [c for c in df.columns if c.startswith(prefix)]
    else: return [c for c in df.columns if c.startswith(prefix)]

def load_creditcard():
    import scipy.io as sio
    df = _read_csv(DATA_DIR / 'creditcard' / 'creditcard.csv')
    y = _col(df, 'Class').astype(np.int32)
    v_cols = _cols_starting(df, 'V')
    mapping = [(AMTTP_MAP[i], _col(df, col).astype(np.float32))
               for i, col in enumerate(v_cols) if i < len(AMTTP_MAP)]
    mapping.append(('value_eth', _col(df, 'Amount').astype(np.float32)))
    return map_to_93(mapping), y

def load_xblock():
    df = _read_csv(DATA_DIR / 'xblock' / 'transaction_dataset.csv')
    y = _col(df, 'FLAG').astype(np.int32)
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
    mapping = [(dst, _col(df, src).astype(np.float32)) for src, dst in xb_map if src in df.columns]
    return map_to_93(mapping), y

def load_elliptic():
    if USE_POLARS:
        features = pl.read_csv(str(DATA_DIR / 'elliptic' / 'elliptic_txs_features.csv'), has_header=False)
        classes  = pl.read_csv(str(DATA_DIR / 'elliptic' / 'elliptic_txs_classes.csv'))
        feat_cols = ['txId'] + [f'feat_{i}' for i in range(1, features.shape[1])]
        features = features.rename({o: n for o, n in zip(features.columns, feat_cols)})
        classes  = classes.rename({classes.columns[0]: 'txId', classes.columns[1]: 'class'})
        merged   = features.join(classes, on='txId').filter(pl.col('class').is_in(['1', '2']))
        y = (merged['class'].cast(pl.Utf8) == '2').to_numpy().astype(np.int32)
        avail = [f'feat_{i}' for i in range(1, 167) if f'feat_{i}' in merged.columns]
        X_raw = merged.select(avail).to_numpy().astype(np.float32)
    else:
        features = pd.read_csv(DATA_DIR / 'elliptic' / 'elliptic_txs_features.csv', header=None)
        features.columns = ['txId'] + [f'feat_{i}' for i in range(1, features.shape[1])]
        classes = pd.read_csv(DATA_DIR / 'elliptic' / 'elliptic_txs_classes.csv')
        classes.columns = ['txId', 'class']
        merged = features.merge(classes, on='txId')
        merged = merged[merged['class'].isin(['1', '2', 1, 2])]
        y = (merged['class'].astype(str) == '2').astype(np.int32).values
        avail = [f'feat_{i}' for i in range(1, 167) if f'feat_{i}' in merged.columns]
        X_raw = merged[avail].values.astype(np.float32)
    X = np.zeros((len(X_raw), 93), dtype=np.float32)
    X[:, :min(X_raw.shape[1], 93)] = X_raw[:, :93]
    return X, y

def load_odds(name):
    import scipy.io as sio
    mat = sio.loadmat(str(DATA_DIR / 'odds' / f'{name}.mat'))
    X = mat['X'].astype(np.float32); y = mat['y'].ravel().astype(np.int32)
    X93 = np.zeros((len(y), 93), dtype=np.float32)
    X93[:, :min(X.shape[1], 93)] = X[:, :93]
    return X93, y


# ================================================================
#             SCORE CACHE (avoids redundant model fits)
# ================================================================
_SCORE_CACHE = {}

def _cached(key, comp, y, fn):
    """Cache expensive scores per (dataset, model) combo."""
    if key not in _SCORE_CACHE:
        _SCORE_CACHE[key] = fn(comp, y)
    return _SCORE_CACHE[key]

def clear_cache():
    _SCORE_CACHE.clear()
    import gc; gc.collect()

# ================================================================
#             ALL 57 NEW VARIANT FUNCTIONS
# ================================================================

# ---------- A: DISTANCE-BASED SEPARATION ----------

def _fit_mahal(comp, y):
    legit = comp[y == 0]
    sf = min(0.9, max(0.5, 1.0 - 10.0 / max(len(legit), 11)))
    mcd = MinCovDet(random_state=42, support_fraction=sf).fit(legit)
    return mcd.mahalanobis(comp)

def A1_robust_mahalanobis(comp, y):
    return _cached('mahal', comp, y, _fit_mahal)

def A2_mahal_power(comp, y, gamma=1.8):
    return np.power(np.clip(A1_robust_mahalanobis(comp, y), 0, None), gamma)

def A3_mahal_exp(comp, y, scale=2.0):
    d = A1_robust_mahalanobis(comp, y)
    return np.exp(np.clip(d / scale, 0, 20))

def A4_mahal_chi2_tail(comp, y):
    d2 = A1_robust_mahalanobis(comp, y)
    return 1.0 - chi2.cdf(d2, df=4)

def A5_mahal_tanh_correction(comp, y, p_base):
    d = np.sqrt(np.clip(A1_robust_mahalanobis(comp, y), 0, None))
    d_norm = d / (np.percentile(d, 95) + 1e-8)
    return np.clip(p_base + 0.8 * np.tanh(d_norm) * (1 - p_base) * (p_base < 0.5).astype(float), 0, 1)

def A6_mahal_unsupervised(comp):
    mcd = MinCovDet(random_state=42).fit(comp)
    return mcd.mahalanobis(comp)

def A7_knn_distance(comp, y, k=10):
    legit = comp[y == 0]
    nn = NearestNeighbors(n_neighbors=min(k, len(legit)), algorithm='ball_tree').fit(legit)
    dists, _ = nn.kneighbors(comp)
    return dists.mean(axis=1)

def A8_knn_correction(comp, y, p_base, k=10):
    d = A7_knn_distance(comp, y, k)
    d_norm = (d - d.mean()) / (d.std() + 1e-8)
    return np.clip(p_base + 0.5 * np.tanh(d_norm) * (1 - p_base), 0, 1)

# ---------- B: DENSITY-BASED SEPARATION ----------

def _fit_kde(comp, y):
    from scipy.stats import gaussian_kde
    legit = comp[y == 0].T
    try:
        kde = gaussian_kde(legit, bw_method='scott')
        return -kde.logpdf(comp.T)
    except:
        return np.zeros(len(comp))

def B1_kde_neglog(comp, y):
    return _cached('kde', comp, y, _fit_kde)

def B2_kde_sigmoid(comp, y, p_base):
    s = B1_kde_neglog(comp, y)
    s_norm = (s - s.mean()) / (s.std() + 1e-8)
    gate = 1.0 / (1.0 + np.exp(-s_norm))
    return np.clip(p_base + 0.6 * gate * (1 - p_base) * (p_base < 0.5).astype(float), 0, 1)

def B3_kde_power(comp, y, gamma=1.5):
    s = B1_kde_neglog(comp, y)
    s_pos = np.clip(s - s.min(), 0, None)
    return np.power(s_pos + 1e-8, gamma)

def B4_gmm_neglog(comp, y, n_components=5):
    legit = comp[y == 0]
    nc = min(n_components, max(1, len(legit) // 10))
    gmm = GaussianMixture(n_components=nc, random_state=42, covariance_type='full').fit(legit)
    return -gmm.score_samples(comp)

def B5_gmm_tanh(comp, y, p_base):
    s = B4_gmm_neglog(comp, y)
    s_norm = (s - np.median(s)) / (np.percentile(s, 95) - np.percentile(s, 5) + 1e-8)
    return np.clip(p_base + 0.7 * np.tanh(s_norm) * (1 - p_base), 0, 1)

def _fit_lof20(comp, y):
    legit = comp[y == 0]
    n_neigh = min(20, len(legit) - 1)
    lof = LocalOutlierFactor(n_neighbors=n_neigh, novelty=True).fit(legit)
    return -lof.score_samples(comp)

def B6_lof(comp, y, k=20):
    if k == 20: return _cached('lof20', comp, y, _fit_lof20)
    legit = comp[y == 0]
    n_neigh = min(k, len(legit) - 1)
    lof = LocalOutlierFactor(n_neighbors=n_neigh, novelty=True).fit(legit)
    return -lof.score_samples(comp)

def B7_lof_correction(comp, y, p_base, k=20):
    s = B6_lof(comp, y, k)
    s_norm = np.clip((s - 1.0) / (np.percentile(s, 95) - 1.0 + 1e-8), 0, 3)
    return np.clip(p_base + 0.5 * np.tanh(s_norm) * (1 - p_base), 0, 1)

# ---------- C: VECTOR SPACE PROJECTIONS ----------

def C1_pca_mahal(comp, y):
    legit = comp[y == 0]
    pca = PCA(n_components=4).fit(legit)
    Z = pca.transform(comp)
    Z_leg = pca.transform(legit)
    mu_pc = Z_leg.mean(0); var_pc = Z_leg.var(0) + 1e-8
    return np.sqrt(np.sum((Z - mu_pc)**2 / var_pc, axis=1))

def C2_pca_power(comp, y, gamma=2.0):
    return np.power(C1_pca_mahal(comp, y), gamma)

def C3_pca_reconstruction_error(comp, y, n_pc=2):
    legit = comp[y == 0]
    pca = PCA(n_components=n_pc).fit(legit)
    recon = pca.inverse_transform(pca.transform(comp))
    return np.linalg.norm(comp - recon, axis=1)

def C4_lda_projection(comp, y):
    if len(np.unique(y)) < 2 or (y == 1).sum() < 2: return comp.mean(1)
    lda = LinearDiscriminantAnalysis(n_components=1).fit(comp, y)
    return lda.transform(comp).ravel()

def C5_lda_proba(comp, y):
    if len(np.unique(y)) < 2 or (y == 1).sum() < 2: return comp.mean(1)
    lda = LinearDiscriminantAnalysis().fit(comp, y)
    return lda.predict_proba(comp)[:, 1]

def C6_whitened_norm(comp, y):
    legit = comp[y == 0]
    mu = legit.mean(0); std = legit.std(0) + 1e-8
    return np.linalg.norm((comp - mu) / std, axis=1)

def C7_whitened_power(comp, y, gamma=1.8):
    return np.power(C6_whitened_norm(comp, y), gamma)

# ---------- D: ISOLATION-BASED ----------

def _fit_isoforest(comp, y):
    legit = comp[y == 0]
    iso = IsolationForest(n_estimators=100, random_state=42, contamination=0.01).fit(legit)
    return -iso.score_samples(comp)

def D1_isolation_forest(comp, y):
    return _cached('isoforest', comp, y, _fit_isoforest)

def D2_isolation_light(comp, y):
    legit = comp[y == 0]
    iso = IsolationForest(n_estimators=10, random_state=42, contamination=0.05).fit(legit)
    return -iso.score_samples(comp)

def D3_isolation_correction(comp, y, p_base):
    s = D1_isolation_forest(comp, y)
    s_norm = (s - np.median(s)) / (s.std() + 1e-8)
    return np.clip(p_base + 0.6 * np.tanh(s_norm) * (1 - p_base), 0, 1)

# ---------- E: SVM-BASED ----------

def _ocsvm_scores(comp, y, kernel='rbf', nu=0.05):
    legit = comp[y == 0]
    n_fit = min(5000, len(legit))
    rng = np.random.RandomState(42)
    idx = rng.choice(len(legit), n_fit, replace=False) if len(legit) > n_fit else np.arange(len(legit))
    svm = OneClassSVM(kernel=kernel, nu=nu, gamma='scale').fit(legit[idx])
    return -svm.decision_function(comp)

def _fit_ocsvm_rbf(comp, y): return _ocsvm_scores(comp, y, 'rbf', 0.05)
def E1_ocsvm_rbf(comp, y):     return _cached('svm_rbf', comp, y, _fit_ocsvm_rbf)
def E2_ocsvm_poly(comp, y):    return _ocsvm_scores(comp, y, 'poly', 0.05)
def E3_ocsvm_linear(comp, y):  return _ocsvm_scores(comp, y, 'linear', 0.1)

def E4_ocsvm_correction(comp, y, p_base):
    s = E1_ocsvm_rbf(comp, y)
    s_norm = (s - s.mean()) / (s.std() + 1e-8)
    gate = np.tanh(np.clip(s_norm, -3, 3))
    return np.clip(p_base + 0.7 * gate * (1 - p_base) * (p_base < 0.6).astype(float), 0, 1)

def E5_ocsvm_blend(comp, y, p_base):
    s = E1_ocsvm_rbf(comp, y)
    s_sig = 1.0 / (1.0 + np.exp(-0.5 * (s - np.median(s)) / (s.std() + 1e-8)))
    return np.clip(0.5 * p_base + 0.5 * s_sig, 0, 1)

# ---------- F: QUADRATIC EQUATION ----------

def F1_qda_proba(comp, y):
    if (y == 1).sum() < 5: return comp.mean(1)
    qda = QuadraticDiscriminantAnalysis(reg_param=0.1).fit(comp, y)
    return qda.predict_proba(comp)[:, 1]

def F2_quadratic_surface(comp, y, p_base):
    poly = PolynomialFeatures(degree=2, include_bias=False).fit_transform(comp)
    target = y.astype(float) - p_base
    w = np.where(y == 1, (y == 0).sum() / max((y == 1).sum(), 1), 1.0)
    Xw = poly * np.sqrt(w)[:, None]; yw = target * np.sqrt(w)
    beta = np.linalg.solve(Xw.T @ Xw + 0.1 * np.eye(poly.shape[1]), Xw.T @ yw)
    return np.clip(p_base + poly @ beta, 0, 1)

def F3_discriminant_plusminus(comp, y, p_base, mfls):
    energy = np.sum(comp**2, axis=1)
    a = np.clip(energy, 0.01, None); b = -mfls; c = p_base - 0.5
    disc = b**2 - 4 * a * c
    valid = disc >= 0; sqrt_d = np.sqrt(np.maximum(disc, 0))
    c_plus  = (-b + sqrt_d) / (2 * a)
    c_minus = (-b - sqrt_d) / (2 * a)
    s_plus  = np.clip(p_base + np.where(valid, c_plus, 0) * (1 - np.abs(2 * p_base - 1)), 0, 1)
    s_minus = np.clip(p_base + np.where(valid, c_minus, 0) * (1 - np.abs(2 * p_base - 1)), 0, 1)
    return grid_best(y, np.vstack([s_plus[np.newaxis], s_minus[np.newaxis]]))

def F4_quadratic_interaction_ridge(comp, y):
    C, G, A, T_ = comp[:, 0], comp[:, 1], comp[:, 2], comp[:, 3]
    X = np.column_stack([C**2, G**2, A**2, T_**2, C*G, C*A, C*T_, G*A, G*T_, A*T_, C, G, A, T_])
    ridge = Ridge(alpha=1.0).fit(X, y)
    return np.clip(ridge.predict(X), 0, 1)

def F5_quadratic_correction_grid(comp, y, p_base, mfls):
    from itertools import product as iprod
    params = np.array(list(iprod(
        [-1.0, -0.5, -0.2, 0, 0.2, 0.5, 1.0],
        [-2.0, -1.0, -0.5, 0, 0.5, 1.0, 2.0])))
    a, b = params[:, 0], params[:, 1]
    corr = a[:, None] * mfls[None, :]**2 + b[:, None] * mfls[None, :]
    pc = np.clip(p_base[None, :] + corr * (1.0 - p_base[None, :]), 0, 1)
    return grid_best(y, pc)

# ---------- G: DISTRIBUTION TRANSFORMS ----------

def G1_boxcox_mfls(mfls):
    shifted = mfls - mfls.min() + 1e-6
    try: t, _ = boxcox(shifted); return t
    except: return shifted

def G2_yeojohnson_mfls(mfls):
    try: t, _ = yeojohnson(mfls); return t
    except: return mfls

def G3_quantile_uniform(comp, y):
    qt = QuantileTransformer(output_distribution='uniform', random_state=42).fit(comp[y == 0])
    return qt.transform(comp).mean(axis=1)

def G4_quantile_gaussian(comp, y):
    qt = QuantileTransformer(output_distribution='normal', random_state=42).fit(comp[y == 0])
    Z = qt.transform(comp)
    mu = Z[y == 0].mean(0); var = Z[y == 0].var(0) + 1e-8
    return np.sqrt(np.sum((Z - mu)**2 / var, axis=1))

def G5_rank_sigmoid(mfls):
    ranks = sp_stats.rankdata(mfls) / len(mfls)
    return 1.0 / (1.0 + np.exp(-6 * (ranks - 0.5)))

def G6_logit_power(mfls, gamma=2.0):
    clipped = np.clip(mfls, 1e-6, 1 - 1e-6)
    logit = np.log(clipped / (1 - clipped))
    return 1.0 / (1.0 + np.exp(-np.sign(logit) * np.abs(logit)**gamma / 5))

def G7_yeojohnson_correction(mfls, p_base, y):
    t = G2_yeojohnson_mfls(mfls)
    t_norm = (t - t.mean()) / (t.std() + 1e-8)
    return np.clip(p_base + 0.5 * np.tanh(t_norm) * (1 - p_base), 0, 1)

# ---------- H: INTERACTION & ENRICHMENT ----------

def H1_poly2_lr(comp, y):
    poly = PolynomialFeatures(degree=2, include_bias=False).fit_transform(comp)
    lr = LogisticRegression(random_state=42, max_iter=1000, class_weight='balanced', C=0.5)
    lr.fit(poly, y); return lr.predict_proba(poly)[:, 1]

def H2_component_ratios(comp, y):
    C, G, A, T_ = comp[:, 0], comp[:, 1], comp[:, 2], comp[:, 3]
    X = np.column_stack([C/(G+1e-8), A/(T_+1e-8), (C*A)/(G*T_+1e-8), (C+A)/(G+T_+1e-8)])
    lr = LogisticRegression(random_state=42, max_iter=1000, class_weight='balanced')
    lr.fit(X, y); return lr.predict_proba(X)[:, 1]

def H3_harmonic_mean(comp):
    c = np.clip(comp, 1e-8, None)
    return 4.0 / np.sum(1.0 / c, axis=1)

def H4_geometric_mean(comp):
    c = np.clip(comp, 1e-8, None)
    return np.exp(np.mean(np.log(c), axis=1))

def H5_lp_norms(comp, y):
    l05 = np.sum(np.sqrt(np.abs(comp) + 1e-8), axis=1)**2
    l1 = np.sum(np.abs(comp), axis=1)
    l2 = np.linalg.norm(comp, axis=1)
    linf = np.max(np.abs(comp), axis=1)
    X = np.column_stack([l05, l1, l2, linf])
    lr = LogisticRegression(random_state=42, max_iter=1000, class_weight='balanced')
    lr.fit(X, y); return lr.predict_proba(X)[:, 1]

def H6_entropy_score(comp):
    c = np.clip(comp, 1e-8, None)
    p = c / c.sum(axis=1, keepdims=True)
    return -np.sum(p * np.log(p), axis=1)

# ---------- I: HYBRID (new scores x gate formulas) ----------

def I1_mahal_AND_gate(comp, y, p_base):
    d = np.sqrt(np.clip(A1_robust_mahalanobis(comp, y), 0, None))
    d_norm = np.tanh(d / (np.percentile(d, 95) + 1e-8))
    CG = comp[:, 0] * comp[:, 1]
    return np.clip(p_base + 0.8 * d_norm * CG * (1 - p_base), 0, 1)

def I2_kde_XOR_gate(comp, y, p_base):
    s = B1_kde_neglog(comp, y)
    s_norm = np.tanh((s - np.median(s)) / (s.std() + 1e-8))
    xor = comp[:, 0] * comp[:, 2] - comp[:, 1] * comp[:, 3]
    return np.clip(p_base + 0.5 * s_norm * np.tanh(xor) * (1 - p_base), 0, 1)

def I3_isolation_ratio_gate(comp, y, p_base):
    s = D1_isolation_forest(comp, y)
    s_norm = np.tanh((s - np.median(s)) / (s.std() + 1e-8))
    ratio = (comp[:, 0] + comp[:, 1]) / (comp[:, 2] + comp[:, 3] + 1e-8)
    direction = np.tanh((ratio - 1.0) * 2)
    return np.clip(p_base + 0.5 * s_norm * direction * (1 - p_base), 0, 1)

def I4_svm_tanh_smooth(comp, y, p_base):
    s = E1_ocsvm_rbf(comp, y)
    sat = np.tanh(s / (np.percentile(s, 90) + 1e-8))
    gate = 1.0 / (1.0 + np.exp(-12 * (0.5 - p_base)))
    return np.clip(p_base + 0.8 * sat * (1 - p_base) * gate, 0, 1)

def I5_lda_power(comp, y, gamma=1.5):
    s = C4_lda_projection(comp, y)
    s_norm = (s - s.min()) / (s.max() - s.min() + 1e-8)
    return np.power(s_norm, gamma)

def I6_ensemble_vote(comp, y, p_base):
    scores = []
    for fn in [A1_robust_mahalanobis, B1_kde_neglog, D1_isolation_forest, E1_ocsvm_rbf]:
        try:
            s = fn(comp, y)
            thresh = np.percentile(s, 90)
            scores.append((s >= thresh).astype(float))
        except: pass
    if not scores: return p_base
    vote = np.mean(scores, axis=0)
    return np.clip(p_base + 0.6 * vote * (1 - p_base), 0, 1)

def I7_stacked_anomaly_lr(comp, y):
    feats = []
    for fn in [A1_robust_mahalanobis, B1_kde_neglog, D1_isolation_forest]:
        try: feats.append(fn(comp, y))
        except: feats.append(np.zeros(len(y)))
    try: feats.append(E1_ocsvm_rbf(comp, y))
    except: feats.append(np.zeros(len(y)))
    X = np.column_stack(feats)
    lr = LogisticRegression(random_state=42, max_iter=1000, class_weight='balanced')
    lr.fit(X, y); return lr.predict_proba(X)[:, 1]


# ================================================================
#               VARIANT REGISTRY (57 entries)
# ================================================================

VARIANT_DEFS = [
    # A: Distance
    ('A1_RobustMahal',       'A1:RobustMahal',       lambda c,y,p,m: A1_robust_mahalanobis(c,y)),
    ('A2_MahalPow18',        'A2:Mahal^1.8',         lambda c,y,p,m: A2_mahal_power(c,y,1.8)),
    ('A3_MahalPow25',        'A3:Mahal^2.5',         lambda c,y,p,m: A2_mahal_power(c,y,2.5)),
    ('A4_MahalExp',          'A4:Mahal->exp',        lambda c,y,p,m: A3_mahal_exp(c,y,2.0)),
    ('A5_MahalChi2',         'A5:Mahal->chi2',       lambda c,y,p,m: A4_mahal_chi2_tail(c,y)),
    ('A6_MahalTanh',         'A6:Mahal+tanh',        lambda c,y,p,m: A5_mahal_tanh_correction(c,y,p)),
    ('A7_MahalUnsup',        'A7:MahalUnsup',        lambda c,y,p,m: A6_mahal_unsupervised(c)),
    ('A8_kNNDist',           'A8:kNN(k=10)',         lambda c,y,p,m: A7_knn_distance(c,y,10)),
    ('A9_kNNCorr',           'A9:kNN+corr',          lambda c,y,p,m: A8_knn_correction(c,y,p,10)),
    # B: Density
    ('B1_KDE',               'B1:KDE-logP',          lambda c,y,p,m: B1_kde_neglog(c,y)),
    ('B2_KDE_Sig',           'B2:KDE+sigmoid',       lambda c,y,p,m: B2_kde_sigmoid(c,y,p)),
    ('B3_KDE_Pow',           'B3:KDE^1.5',           lambda c,y,p,m: B3_kde_power(c,y,1.5)),
    ('B4_GMM5',              'B4:GMM5-logL',         lambda c,y,p,m: B4_gmm_neglog(c,y,5)),
    ('B5_GMM3',              'B5:GMM3-logL',         lambda c,y,p,m: B4_gmm_neglog(c,y,3)),
    ('B6_GMM_Tanh',          'B6:GMM+tanh',          lambda c,y,p,m: B5_gmm_tanh(c,y,p)),
    ('B7_LOF20',             'B7:LOF(k=20)',         lambda c,y,p,m: B6_lof(c,y,20)),
    ('B8_LOF5',              'B8:LOF(k=5)',          lambda c,y,p,m: B6_lof(c,y,5)),
    ('B9_LOF_Corr',          'B9:LOF+corr',          lambda c,y,p,m: B7_lof_correction(c,y,p,20)),
    # C: Projections
    ('C1_PCA_Mahal',         'C1:PCA->Mahal',        lambda c,y,p,m: C1_pca_mahal(c,y)),
    ('C2_PCA_Pow',           'C2:PCA^2.0',           lambda c,y,p,m: C2_pca_power(c,y,2.0)),
    ('C3_PCA_Recon',         'C3:PCA reconErr',      lambda c,y,p,m: C3_pca_reconstruction_error(c,y,2)),
    ('C4_LDA_1D',            'C4:LDA proj',          lambda c,y,p,m: C4_lda_projection(c,y)),
    ('C5_LDA_Proba',         'C5:LDA proba',         lambda c,y,p,m: C5_lda_proba(c,y)),
    ('C6_Whitened',          'C6:Whitened norm',      lambda c,y,p,m: C6_whitened_norm(c,y)),
    ('C7_WhiPow18',          'C7:Whiten^1.8',        lambda c,y,p,m: C7_whitened_power(c,y,1.8)),
    # D: Isolation
    ('D1_IsoF100',           'D1:IsoForest100',      lambda c,y,p,m: D1_isolation_forest(c,y)),
    ('D2_IsoF10',            'D2:IsoForest10',       lambda c,y,p,m: D2_isolation_light(c,y)),
    ('D3_IsoCorr',           'D3:Iso+corr',          lambda c,y,p,m: D3_isolation_correction(c,y,p)),
    # E: SVM
    ('E1_SVM_RBF',           'E1:OC-SVM(rbf)',       lambda c,y,p,m: E1_ocsvm_rbf(c,y)),
    ('E2_SVM_Poly',          'E2:OC-SVM(poly)',      lambda c,y,p,m: E2_ocsvm_poly(c,y)),
    ('E3_SVM_Lin',           'E3:OC-SVM(lin)',       lambda c,y,p,m: E3_ocsvm_linear(c,y)),
    ('E4_SVM_Corr',          'E4:SVM+corr',          lambda c,y,p,m: E4_ocsvm_correction(c,y,p)),
    ('E5_SVM_Blend',         'E5:SVM blend',         lambda c,y,p,m: E5_ocsvm_blend(c,y,p)),
    # F: Quadratic
    ('F1_QDA',               'F1:QDA',               lambda c,y,p,m: F1_qda_proba(c,y)),
    ('F2_QuadSurf',          'F2:QuadSurface',       lambda c,y,p,m: F2_quadratic_surface(c,y,p)),
    ('F3_DiscrimPM',         'F3:+/-sqrt(disc)',     lambda c,y,p,m: F3_discriminant_plusminus(c,y,p,m)),
    ('F4_QuadRidge',         'F4:QuadInterRidge',    lambda c,y,p,m: F4_quadratic_interaction_ridge(c,y)),
    ('F5_QuadGrid',          'F5:QuadCorrGrid',      lambda c,y,p,m: F5_quadratic_correction_grid(c,y,p,m)),
    # G: Transforms
    ('G1_BoxCox',            'G1:BoxCox(MFLS)',      lambda c,y,p,m: G1_boxcox_mfls(m)),
    ('G2_YeoJ',              'G2:YeoJ(MFLS)',        lambda c,y,p,m: G2_yeojohnson_mfls(m)),
    ('G3_Quant_U',           'G3:Quantile->U',       lambda c,y,p,m: G3_quantile_uniform(c,y)),
    ('G4_Quant_G',           'G4:Quantile->Gauss',   lambda c,y,p,m: G4_quantile_gaussian(c,y)),
    ('G5_RankSig',           'G5:Rank->sigmoid',     lambda c,y,p,m: G5_rank_sigmoid(m)),
    ('G6_LogitPow',          'G6:Logit^2',           lambda c,y,p,m: G6_logit_power(m, 2.0)),
    ('G7_YeoJCorr',          'G7:YeoJ+corr',         lambda c,y,p,m: G7_yeojohnson_correction(m,p,y)),
    # H: Interactions
    ('H1_Poly2LR',           'H1:Poly2+LR',          lambda c,y,p,m: H1_poly2_lr(c,y)),
    ('H2_Ratios',            'H2:Ratios+LR',         lambda c,y,p,m: H2_component_ratios(c,y)),
    ('H3_Harmonic',          'H3:HarmonicMean',      lambda c,y,p,m: H3_harmonic_mean(c)),
    ('H4_Geometric',         'H4:GeomMean',           lambda c,y,p,m: H4_geometric_mean(c)),
    ('H5_LpNorms',           'H5:LpNorms+LR',        lambda c,y,p,m: H5_lp_norms(c,y)),
    ('H6_Entropy',           'H6:Entropy',            lambda c,y,p,m: H6_entropy_score(c)),
    # I: Hybrids
    ('I1_MahalAND',          'I1:Mahal*AND(CG)',     lambda c,y,p,m: I1_mahal_AND_gate(c,y,p)),
    ('I2_KDE_XOR',           'I2:KDE*XOR(CA-GT)',    lambda c,y,p,m: I2_kde_XOR_gate(c,y,p)),
    ('I3_IsoRatio',          'I3:Iso*Ratio',          lambda c,y,p,m: I3_isolation_ratio_gate(c,y,p)),
    ('I4_SVMTanh',           'I4:SVM*tanh',           lambda c,y,p,m: I4_svm_tanh_smooth(c,y,p)),
    ('I5_LDAPow',            'I5:LDA^1.5',            lambda c,y,p,m: I5_lda_power(c,y,1.5)),
    ('I6_EnsVote',           'I6:Ensemble vote',      lambda c,y,p,m: I6_ensemble_vote(c,y,p)),
    ('I7_StackedLR',         'I7:Stacked->LR',        lambda c,y,p,m: I7_stacked_anomaly_lr(c,y)),
]

print(f'{len(VARIANT_DEFS)} new variants registered')


# ================================================================
#                    LOAD DATASETS
# ================================================================

print("\nLoading datasets...", flush=True)
t_load = time.time()
DATASETS = {}
# Load smallest first to maximise early results and minimise memory pressure
for name, loader in [('Pendigits', lambda: load_odds('pendigits')),
                      ('Mammography', lambda: load_odds('mammography')),
                      ('XBlock', load_xblock),
                      ('Shuttle', lambda: load_odds('shuttle')),
                      ('Credit Card', load_creditcard),
                      ('Elliptic', load_elliptic)]:
    try:
        X, y = loader()
        DATASETS[name] = (X, y)
        print(f'  {name}: {len(y):,} samples, {y.sum():,} fraud ({y.mean():.2%})', flush=True)
    except Exception as e:
        print(f'  {name}: FAILED - {e}', flush=True)
print(f'Loaded in {time.time()-t_load:.1f}s\n', flush=True)


# ================================================================
#                    MAIN EVALUATION LOOP
# ================================================================

ALL_RESULTS = []
total_combos = len(DATASETS) * 2  # 2 models per dataset
combo_done = 0

for ds_idx, (ds_name, (X, y)) in enumerate(DATASETS.items()):
    ds_t = time.time()
    domain = 'IN-DOMAIN' if ds_name in ('Elliptic', 'XBlock') else 'OUT-DOMAIN'
    print(f"\n{'='*100}")
    print(f"  [{ds_idx+1}/{len(DATASETS)}] {ds_name} ({domain})  n={len(y):,}  fraud={y.sum():,} ({y.mean():.2%})")
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
        lr_cal.fit(p_raw[cal_i].reshape(-1, 1), y_cal)
        p_amttp = lr_cal.predict_proba(p_raw[eval_i].reshape(-1, 1))[:, 1]
    except:
        p_amttp = np.full(len(y_e), 0.5)

    # Fresh-XGB (per-dataset)
    X_proc_cal = preprocess_93(X_cal)
    X_proc_e   = preprocess_93(X_e)
    clf_fresh = xgb.XGBClassifier(n_estimators=100, max_depth=6,
                                   random_state=42, eval_metric='logloss', verbosity=0)
    clf_fresh.fit(X_proc_cal, y_cal)
    p_fresh = clf_fresh.predict_proba(X_proc_e)[:, 1]

    for mname, p_base in [('AMTTP-XGB93', p_amttp), ('Fresh-XGB', p_fresh)]:
        clear_cache()  # fresh cache per model combo
        combo_done += 1
        print(f"\n  [{mname}] ({combo_done}/{total_combos}) Computing {len(VARIANT_DEFS)} variants...", flush=True)
        mt = time.time()

        row = {'dataset': ds_name, 'domain': domain, 'model': mname,
               'n': len(y_e), 'n_fraud': int(y_e.sum())}
        row['B0_Base'] = eval_scores(y_e, p_base)

        for vi, (key, label, fn) in enumerate(VARIANT_DEFS):
            try:
                t_v = time.time()
                scores = fn(comp, y_e, p_base, mfls)
                scores = np.nan_to_num(np.asarray(scores, dtype=np.float64).ravel(),
                                       nan=0.0, posinf=1.0, neginf=0.0)
                row[key] = eval_scores(y_e, scores)
                elapsed = time.time() - t_v
                eta_combo = (time.time() - mt) / (vi + 1) * (len(VARIANT_DEFS) - vi - 1)
                if elapsed > 2 or (vi + 1) % 10 == 0:
                    print(f"    [{vi+1}/{len(VARIANT_DEFS)}] {label}: {elapsed:.1f}s  (ETA combo ~{eta_combo:.0f}s)", flush=True)
            except Exception as e:
                row[key] = {'f1': 0, 'rec': 0, 'prec': 0, 'tp': 0, 'fp': 0,
                            'fa': 0, 'auc': 0.5, 'threshold': 0.5,
                            'pct_missed': 100, 'pct_fa': 0, 'pct_correct': 0,
                            'error': str(e)}
                print(f"    X {label}: {e}", flush=True)

        ALL_RESULTS.append(row)
        print(f"    Done in {time.time()-mt:.1f}s", flush=True)

    # Crash-safe incremental save
    _tmp = Path(str(OUTPUT_DIR) + '/mfls_v2_partial.json')
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(_tmp, 'w') as f:
        json.dump(ALL_RESULTS, f, indent=2, default=lambda o: float(o) if isinstance(o, (np.floating,)) else int(o) if isinstance(o, (np.integer,)) else str(o))

    # Free dataset memory
    import gc; gc.collect()
    print(f"  [{ds_name} total: {time.time()-ds_t:.1f}s]", flush=True)

clear_cache()
total_time = time.time() - t0


# ================================================================
#                    SAVE RESULTS
# ================================================================

os.makedirs(OUTPUT_DIR, exist_ok=True)

def _ser(obj):
    if isinstance(obj, (np.integer,)): return int(obj)
    if isinstance(obj, (np.floating,)): return float(obj)
    if isinstance(obj, np.ndarray): return obj.tolist()
    return str(obj)

v2_path = OUTPUT_DIR / 'mfls_variants_v2_results.json'
with open(v2_path, 'w') as f:
    json.dump(ALL_RESULTS, f, indent=2, default=_ser)
print(f'\nSaved V2 results -> {v2_path}', flush=True)

# Load + merge old V1
try:
    v1_results = json.load(open(OLD_RESULTS_P))
    print(f'Loaded {len(v1_results)} old V1 results')
except:
    v1_results = []
    print('No V1 results found')

if v1_results:
    merged = []
    for v2_row in ALL_RESULTS:
        ds, model = v2_row['dataset'], v2_row['model']
        v1_match = next((r for r in v1_results if r.get('dataset') == ds and r.get('model') == model), None)
        combined = {k: v for k, v in v2_row.items()}
        if v1_match:
            for k, v in v1_match.items():
                if k.startswith(('B', 'V')) and k != 'B0_Base':
                    combined[f'v1_{k}'] = v
        merged.append(combined)

    merged_path = OUTPUT_DIR / 'mfls_all_variants_merged.json'
    with open(merged_path, 'w') as f:
        json.dump(merged, f, indent=2, default=_ser)
    print(f'Merged -> {merged_path}')


# ================================================================
#                    PRINT TABLES
# ================================================================

VKEYS = [(k, l) for k, l, _ in VARIANT_DEFS]

print(f"\n\n{'#'*120}")
print(f"  VARIANT V2 COMPARISON - {len(ALL_RESULTS)} model x dataset tests - {total_time:.0f}s")
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
    v = r['B0_Base']
    print(f"  {'Base Model':<22} | {v['f1']:6.3f} {v.get('auc',0):6.3f} {v['rec']:6.3f} {v['prec']:6.3f} | "
          f"{v['pct_missed']:5.1f}% {v['pct_fa']:5.1f}% {v['pct_correct']:6.1f}% | ---")

    for key, label in VKEYS:
        v = r.get(key)
        if v is None or 'error' in v:
            err = v.get('error', '?')[:30] if v else '?'
            print(f"  {label:<22} | {'FAIL':>6} {'':>6} {'':>6} {'':>6} | {'':>6} {'':>6} {'':>7} | {err}")
            continue
        df1 = v['f1'] - base_f1; dc = v['pct_correct'] - base_c
        s = '+' if df1 >= 0 else ''
        m = '*' if v['pct_correct'] > base_c and v['f1'] >= base_f1 else ''
        print(f"  {label:<22} | {v['f1']:6.3f} {v.get('auc',0):6.3f} {v['rec']:6.3f} {v['prec']:6.3f} | "
              f"{v['pct_missed']:5.1f}% {v['pct_fa']:5.1f}% {v['pct_correct']:6.1f}% | "
              f"{s}{df1:.3f} F1 {dc:+.1f}% {m}")


# ── Aggregate ──
print(f"\n\n{'#'*120}")
print(f"  AGGREGATE - Mean across all {len(ALL_RESULTS)} dataset x model combinations")
print(f"{'#'*120}\n")
print(f"  {'Method':<22} | {'MeanF1':>7} {'MeanAUC':>7} | {'%Miss':>7} {'%FAlrt':>7} {'%Right':>7} | {'WinF1':>5} {'WinAcc':>6}")
print(f"  {'-'*22}-+-{'-'*7}-{'-'*7}-+-{'-'*7}-{'-'*7}-{'-'*7}-+-{'-'*5}-{'-'*6}")

for key, label in VKEYS:
    vals = [r[key] for r in ALL_RESULTS if key in r and 'error' not in r.get(key, {})]
    if not vals:
        print(f"  {label:<22} | {'N/A':>7} {'':>7} | {'':>7} {'':>7} {'':>7} | {'':>5} {'':>6}")
        continue
    mf  = np.mean([v['f1'] for v in vals])
    ma  = np.mean([v.get('auc', 0) for v in vals])
    mm  = np.mean([v['pct_missed'] for v in vals])
    mfa = np.mean([v['pct_fa'] for v in vals])
    mc  = np.mean([v['pct_correct'] for v in vals])
    wf  = sum(1 for r in ALL_RESULTS if key in r and 'error' not in r.get(key, {})
              and r[key]['f1'] > r['B0_Base']['f1'] + 0.001)
    wa  = sum(1 for r in ALL_RESULTS if key in r and 'error' not in r.get(key, {})
              and r[key]['pct_correct'] > r['B0_Base']['pct_correct'] + 0.01)
    print(f"  {label:<22} | {mf:7.3f} {ma:7.3f} | {mm:6.1f}% {mfa:6.1f}% {mc:6.1f}% | {wf:>5} {wa:>6}")


# ── Top-10 leaderboard ──
print(f"\n\n{'#'*120}")
print(f"  TOP-10 BY MEAN F1")
print(f"{'#'*120}\n")

scores_by_variant = []
for key, label in VKEYS:
    vals = [r[key] for r in ALL_RESULTS if key in r and 'error' not in r.get(key, {})]
    if vals:
        mf1  = np.mean([v['f1'] for v in vals])
        mauc = np.mean([v.get('auc', 0) for v in vals])
        wins = sum(1 for r in ALL_RESULTS if key in r and 'error' not in r.get(key, {})
                   and r[key]['f1'] > r['B0_Base']['f1'] + 0.001)
        scores_by_variant.append((key, label, mf1, mauc, wins))

scores_by_variant.sort(key=lambda x: -x[2])
base_mf1 = np.mean([r['B0_Base']['f1'] for r in ALL_RESULTS])

print(f"  Base mean F1: {base_mf1:.4f}\n")
print(f"  {'Rank':>4} {'Method':<22} {'MeanF1':>7} {'MeanAUC':>7} {'Wins':>5} {'dF1':>7}")
print(f"  {'-'*60}")
for i, (key, label, mf1, mauc, wins) in enumerate(scores_by_variant[:10]):
    delta = mf1 - base_mf1
    star = ' *' if delta > 0 else ''
    print(f"  {i+1:>4} {label:<22} {mf1:7.4f} {mauc:7.4f} {wins:>5} {delta:>+7.4f}{star}")


# ── Per-category winners ──
print("\n  PER-CATEGORY WINNERS\n")
categories = {'A:Dist': 'A', 'B:Dens': 'B', 'C:Proj': 'C', 'D:Iso': 'D',
              'E:SVM': 'E', 'F:Quad': 'F', 'G:Xform': 'G', 'H:Inter': 'H', 'I:Hybrid': 'I'}
for cat_name, prefix in categories.items():
    cat = [x for x in scores_by_variant if x[0].startswith(prefix)]
    if cat:
        best = max(cat, key=lambda x: x[2])
        delta = best[2] - base_mf1
        print(f"  {cat_name:<12}: {best[1]:<22} F1={best[2]:.4f} AUC={best[3]:.4f} (dF1={delta:+.4f})")

print(f"\nTotal time: {total_time:.0f}s ({total_time/60:.1f} min)")
print("DONE")
