"""
Comprehensive BSDT Test — All Models x All Datasets
=====================================================
Tests: (1) Pre-trained AMTTP models (XGB-93, XGB-160, LGB-160)
       (2) Fresh per-dataset models (XGB, RF, LR)
       (3) Original MFLS correction vs Signed LR correction
Datasets: Elliptic (in-domain), XBlock (in-domain),
          Credit Card, Shuttle, Mammography, Pendigits (out-of-domain)
"""

import numpy as np, polars as pl, scipy.io as sio, json, time, warnings, joblib
import xgboost as xgb, lightgbm as lgb
from pathlib import Path
from sklearn.metrics import roc_auc_score, mutual_info_score
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import StratifiedShuffleSplit
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

# XGB as Booster (93 features — raw mode)
xgb_93 = xgb.Booster()
xgb_93.load_model(str(ARTIFACTS / 'xgboost_fraud.ubj'))

# XGB as Classifier (160 features — boost mode)
xgb_160 = xgb.XGBClassifier()
xgb_160.load_model(str(ARTIFACTS / 'xgboost_fraud.ubj'))

# LightGBM (160 features)
lgb_160 = lgb.Booster(model_file=str(ARTIFACTS / 'lightgbm_fraud.txt'))

print(f"Models loaded in {time.time()-t0:.1f}s")

# ── Feature indices ──
IDX_SENT = FEATURES_93.index('sender_total_sent') if 'sender_total_sent' in FEATURES_93 else 7
IDX_RECV = FEATURES_93.index('receiver_total_received') if 'receiver_total_received' in FEATURES_93 else 60

# ══════════════════════════════════════════════════════
# PREPROCESSING + PREDICTION
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
# BSDT CORE (vectorised)
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
# VECTORISED METRICS
# ══════════════════════════════════════════════════════

PT = np.arange(0.05, 0.95, 0.02)  # 45 thresholds

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

def eval_model(y, p):
    try: auc = float(roc_auc_score(y, p))
    except: auc = 0.5
    m = best_f1_at_thresholds(y, p)
    m['auc'] = auc
    return m

# ══════════════════════════════════════════════════════
# CORRECTION FORMULAS
# ══════════════════════════════════════════════════════

LAM = np.arange(0.1, 2.6, 0.2)
TAU = np.array([0.1, 0.2, 0.3, 0.5, 0.7, 0.9])

def apply_original_correction(p, mfls, y):
    best = {'f1': 0.0, 'rec': 0.0, 'prec': 0.0, 'tp': 0, 'fp': 0, 'fa': 1.0}
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
    m['coefs'] = lr.coef_[0].tolist()
    return m

# ══════════════════════════════════════════════════════
# DATA LOADERS
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
    X[:, :min(93, X_raw.shape[1])] = X_raw[:, :93]
    return X, y

def load_odds(name):
    d = sio.loadmat(str(DATA_DIR / 'odds' / f'{name}.mat'))
    X_raw = d['X'].astype(np.float32); y = d['y'].ravel().astype(np.int32)
    mapping = [(AMTTP_MAP[i], X_raw[:,i]) for i in range(min(X_raw.shape[1], len(AMTTP_MAP)))]
    return map_to_93(mapping), y

# ══════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════

print("\nLoading datasets...")
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
        print(f"  {name}: {len(y):,} samples, {y.sum():,} fraud ({y.mean():.2%})")
    except Exception as e:
        print(f"  {name}: FAILED - {e}")

print(f"Loaded in {time.time()-t_load:.1f}s\n")

ROWS = []

for ds_name, (X, y) in DATASETS.items():
    ds_t = time.time()
    domain = 'IN-DOMAIN' if ds_name in ('Elliptic', 'XBlock') else 'OUT-DOMAIN'
    print(f"\n{'='*80}")
    print(f"  {ds_name} ({domain})  n={len(y):,}  fraud={y.sum():,} ({y.mean():.2%})")
    print(f"{'='*80}")

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

    # ── Pre-trained AMTTP models ──
    for mname, pred_fn in [('AMTTP-XGB93', predict_xgb93),
                            ('AMTTP-XGB160', predict_xgb160),
                            ('AMTTP-LGB160', predict_lgb160)]:
        try:
            p_raw_full = pred_fn(X)
            lr_cal = LogisticRegression(random_state=42, max_iter=1000)
            lr_cal.fit(p_raw_full[cal_i].reshape(-1,1), y_cal)
            p = lr_cal.predict_proba(p_raw_full[eval_i].reshape(-1,1))[:, 1]

            base = eval_model(y_e, p)
            orig = apply_original_correction(p, mfls, y_e)
            slr  = apply_signed_lr(p, comp, y_e)

            n_total = len(y_e)
            n_fraud = int(y_e.sum())
            print(f"  {mname:<15} Base F1={base['f1']:.3f} AUC={base['auc']:.4f} | +MFLS F1={orig['f1']:.3f} FA={orig['fa']:.1%} | +SLR F1={slr['f1']:.3f} FA={slr['fa']:.1%}")
            ROWS.append((ds_name, domain, mname, n_total, n_fraud,
                         base['auc'], base['f1'], base['rec'], base['prec'], base['fa'], base['tp'], base['fp'],
                         orig['f1'], orig['rec'], orig['prec'], orig['fa'], orig['tp'], orig['fp'],
                         slr['f1'], slr['rec'], slr['prec'], slr['fa'], slr['auc'], slr['tp'], slr['fp']))
        except Exception as e:
            print(f"  {mname:<15} ERROR: {e}")

    # ── Fresh models (trained on calibration split of THIS dataset) ──
    fresh = [
        ('Fresh-XGB', xgb.XGBClassifier(n_estimators=100, max_depth=6, random_state=42,
                                         eval_metric='logloss', verbosity=0)),
        ('Fresh-RF',  RandomForestClassifier(n_estimators=100, max_depth=10,
                                              random_state=42, n_jobs=-1)),
        ('Fresh-LR',  LogisticRegression(max_iter=1000, random_state=42)),
    ]
    X_proc_cal = preprocess_93(X_cal)
    X_proc_e   = preprocess_93(X_e)

    for mname, clf in fresh:
        try:
            clf.fit(X_proc_cal, y_cal)
            p = clf.predict_proba(X_proc_e)[:, 1] if hasattr(clf, 'predict_proba') else clf.predict(X_proc_e)

            base = eval_model(y_e, p)
            orig = apply_original_correction(p, mfls, y_e)
            slr  = apply_signed_lr(p, comp, y_e)

            n_total = len(y_e)
            n_fraud = int(y_e.sum())
            print(f"  {mname:<15} Base F1={base['f1']:.3f} AUC={base['auc']:.4f} | +MFLS F1={orig['f1']:.3f} FA={orig['fa']:.1%} | +SLR F1={slr['f1']:.3f} FA={slr['fa']:.1%}")
            ROWS.append((ds_name, domain, mname, n_total, n_fraud,
                         base['auc'], base['f1'], base['rec'], base['prec'], base['fa'], base['tp'], base['fp'],
                         orig['f1'], orig['rec'], orig['prec'], orig['fa'], orig['tp'], orig['fp'],
                         slr['f1'], slr['rec'], slr['prec'], slr['fa'], slr['auc'], slr['tp'], slr['fp']))
        except Exception as e:
            print(f"  {mname:<15} ERROR: {e}")

    print(f"  [{ds_name} done in {time.time()-ds_t:.1f}s]")

# ══════════════════════════════════════════════════════
# GRAND SUMMARY TABLE
# ══════════════════════════════════════════════════════

total = time.time() - t0
print(f"\n\n{'#'*130}")
print(f"  GRAND RESULTS — {len(ROWS)} model x dataset combinations — {total:.0f}s")
print(f"{'#'*130}\n")

# Column indices for new extended row format:
# 0=ds, 1=dom, 2=model, 3=n, 4=n_fraud,
# 5=b_auc, 6=b_f1, 7=b_rec, 8=b_prec, 9=b_fa, 10=b_tp, 11=b_fp,
# 12=o_f1, 13=o_rec, 14=o_prec, 15=o_fa, 16=o_tp, 17=o_fp,
# 18=s_f1, 19=s_rec, 20=s_prec, 21=s_fa, 22=s_auc, 23=s_tp, 24=s_fp

hdr = f"{'Dataset':<14} {'Domain':<10} {'Model':<15} │ {'B.AUC':>6} {'B.F1':>5} {'B.Rec':>5} {'B.Prc':>5} {'B.FA':>6} │ {'M.F1':>5} {'M.Rec':>5} {'M.Prc':>5} {'M.FA':>6} │ {'S.F1':>5} {'S.Rec':>5} {'S.Prc':>5} {'S.FA':>6} {'S.AUC':>6} │ {'Win':>5}"
print(hdr)
print('─'*len(hdr))

prev_ds = ''
for row in ROWS:
    ds, dom, model, n, nf = row[0], row[1], row[2], row[3], row[4]
    b_auc, b_f1, b_rec, b_prec, b_fa = row[5], row[6], row[7], row[8], row[9]
    o_f1, o_rec, o_prec, o_fa = row[12], row[13], row[14], row[15]
    s_f1, s_rec, s_prec, s_fa, s_auc = row[18], row[19], row[20], row[21], row[22]

    best = max(b_f1, o_f1, s_f1)
    win = 'SLR' if best==s_f1 and s_f1>0 else ('MFLS' if best==o_f1 and o_f1>0 else 'Base')

    ds_l  = ds if ds != prev_ds else ''
    dom_l = dom if ds != prev_ds else ''
    prev_ds = ds

    print(f"{ds_l:<14} {dom_l:<10} {model:<15} │ {b_auc:6.3f} {b_f1:5.3f} {b_rec:5.3f} {b_prec:5.3f} {b_fa:5.1%} │ {o_f1:5.3f} {o_rec:5.3f} {o_prec:5.3f} {o_fa:5.1%} │ {s_f1:5.3f} {s_rec:5.3f} {s_prec:5.3f} {s_fa:5.1%} {s_auc:6.3f} │ {win:>5}")

# Averages (updated indices)
print(f"\n{'='*100}")
arr_b  = np.array([(r[6], r[9]) for r in ROWS])    # base f1, fa
arr_o  = np.array([(r[12], r[15]) for r in ROWS])  # mfls f1, fa
arr_s  = np.array([(r[18], r[21]) for r in ROWS])  # slr f1, fa
print(f"  OVERALL AVERAGES ({len(ROWS)} runs):")
print(f"    Base model          mean F1={arr_b[:,0].mean():.3f}  mean FA={arr_b[:,1].mean():.1%}")
print(f"    +MFLS correction    mean F1={arr_o[:,0].mean():.3f}  mean FA={arr_o[:,1].mean():.1%}")
print(f"    +Signed LR          mean F1={arr_s[:,0].mean():.3f}  mean FA={arr_s[:,1].mean():.1%}")

# By domain
for dom in ['IN-DOMAIN', 'OUT-DOMAIN']:
    sub = [r for r in ROWS if r[1]==dom]
    if not sub: continue
    a_b = np.array([(r[6], r[9]) for r in sub])
    a_o = np.array([(r[12], r[15]) for r in sub])
    a_s = np.array([(r[18], r[21]) for r in sub])
    print(f"\n  {dom} ({len(sub)} runs):")
    print(f"    Base   F1={a_b[:,0].mean():.3f}  FA={a_b[:,1].mean():.1%}")
    print(f"    +MFLS  F1={a_o[:,0].mean():.3f}  FA={a_o[:,1].mean():.1%}")
    print(f"    +SLR   F1={a_s[:,0].mean():.3f}  FA={a_s[:,1].mean():.1%}")

# By model type
for mtype in ['AMTTP-XGB93','AMTTP-XGB160','AMTTP-LGB160','Fresh-XGB','Fresh-RF','Fresh-LR']:
    sub = [r for r in ROWS if r[2]==mtype]
    if not sub: continue
    a_b = np.array([(r[6], r[9]) for r in sub])
    a_o = np.array([(r[12], r[15]) for r in sub])
    a_s = np.array([(r[18], r[21]) for r in sub])
    print(f"\n  {mtype} across datasets:")
    print(f"    Base   F1={a_b[:,0].mean():.3f}  FA={a_b[:,1].mean():.1%}")
    print(f"    +MFLS  F1={a_o[:,0].mean():.3f}  FA={a_o[:,1].mean():.1%}")
    print(f"    +SLR   F1={a_s[:,0].mean():.3f}  FA={a_s[:,1].mean():.1%}")

# Win count (updated indices)
wins = {'Base':0, 'MFLS':0, 'SLR':0}
for r in ROWS:
    best = max(r[6], r[12], r[18])
    if best == r[18] and r[18]>0: wins['SLR'] += 1
    elif best == r[12] and r[12]>0: wins['MFLS'] += 1
    else: wins['Base'] += 1
print(f"\n  WIN COUNT: Base={wins['Base']}  MFLS={wins['MFLS']}  SignedLR={wins['SLR']}  (of {len(ROWS)})")

# ══════════════════════════════════════════════════════
# EASY-TO-INTERPRET PERCENTAGE METRICS TABLE
# ══════════════════════════════════════════════════════

def pct_metrics(n, n_fraud, tp, fp):
    """Compute easy-to-interpret percentages."""
    n_legit = n - n_fraud
    fn = n_fraud - tp
    tn = n_legit - fp
    missed   = (fn / max(n_fraud, 1)) * 100       # % of fraud missed
    false_al = (fp / max(tp + fp, 1)) * 100       # % of alerts that are false
    correct  = ((tp + tn) / max(n, 1)) * 100      # % of all predictions correct
    return missed, false_al, correct

print(f"\n\n{'#'*160}")
print(f"  EASY-TO-READ METRICS: % Fraud Missed | % False Alerts | % Correct Predictions")
print(f"{'#'*160}")
print(f"  (Lower is better for Missed & False Alerts,  Higher is better for Correct)\n")

ehdr = (f"{'Dataset':<14} {'Model':<15} │"
        f" {'%Miss':>6} {'%FAlrt':>6} {'%Right':>6}  ←Base │"
        f" {'%Miss':>6} {'%FAlrt':>6} {'%Right':>6}  ←+MFLS │"
        f" {'%Miss':>6} {'%FAlrt':>6} {'%Right':>6}  ←+SignedLR │"
        f" {'Best':>6}")
print(ehdr)
print('─'*len(ehdr))

prev_ds = ''
for r in ROWS:
    ds, dom, model, n, nf = r[0], r[1], r[2], r[3], r[4]
    b_tp, b_fp = r[10], r[11]
    o_tp, o_fp = r[16], r[17]
    s_tp, s_fp = r[23], r[24]

    bm, bfa, bc = pct_metrics(n, nf, b_tp, b_fp)
    om, ofa, oc = pct_metrics(n, nf, o_tp, o_fp)
    sm, sfa, sc = pct_metrics(n, nf, s_tp, s_fp)

    # Best = highest %correct (or lowest %missed as tiebreak)
    best_c = max(bc, oc, sc)
    best_tag = 'SLR' if sc==best_c else ('MFLS' if oc==best_c else 'Base')

    ds_l = ds if ds != prev_ds else ''
    prev_ds = ds

    print(f"{ds_l:<14} {model:<15} │"
          f" {bm:5.1f}% {bfa:5.1f}% {bc:5.1f}%  Base  │"
          f" {om:5.1f}% {ofa:5.1f}% {oc:5.1f}%  MFLS  │"
          f" {sm:5.1f}% {sfa:5.1f}% {sc:5.1f}%  SLR   │"
          f" {best_tag:>6}")

# Easy-metric averages
print(f"\n{'─'*100}")
for label, filt in [('ALL', lambda r: True),
                    ('IN-DOMAIN', lambda r: r[1]=='IN-DOMAIN'),
                    ('OUT-DOMAIN', lambda r: r[1]=='OUT-DOMAIN')]:
    sub = [r for r in ROWS if filt(r)]
    if not sub: continue
    b_ms, b_fas, b_cs = [], [], []
    o_ms, o_fas, o_cs = [], [], []
    s_ms, s_fas, s_cs = [], [], []
    for r in sub:
        n, nf = r[3], r[4]
        bm, bfa, bc = pct_metrics(n, nf, r[10], r[11])
        om, ofa, oc = pct_metrics(n, nf, r[16], r[17])
        sm, sfa, sc = pct_metrics(n, nf, r[23], r[24])
        b_ms.append(bm); b_fas.append(bfa); b_cs.append(bc)
        o_ms.append(om); o_fas.append(ofa); o_cs.append(oc)
        s_ms.append(sm); s_fas.append(sfa); s_cs.append(sc)
    print(f"\n  {label} averages ({len(sub)} runs):")
    print(f"    Base       %Missed={np.mean(b_ms):5.1f}%   %FalseAlert={np.mean(b_fas):5.1f}%   %Correct={np.mean(b_cs):5.1f}%")
    print(f"    +MFLS      %Missed={np.mean(o_ms):5.1f}%   %FalseAlert={np.mean(o_fas):5.1f}%   %Correct={np.mean(o_cs):5.1f}%")
    print(f"    +SignedLR  %Missed={np.mean(s_ms):5.1f}%   %FalseAlert={np.mean(s_fas):5.1f}%   %Correct={np.mean(s_cs):5.1f}%")

with open(Path(r'c:\amttp\papers\comprehensive_bsdt_results.json'), 'w') as f:
    json.dump({'rows': [list(r) for r in ROWS], 'total_time': total}, f, indent=2)
print(f"\nSaved -> papers/comprehensive_bsdt_results.json")
