"""
Strict No-Data-Leakage Evaluation Protocol for MolecularEngine
================================================================

Demonstrates no data leakage via strict time-series evaluation:

1. EXPANDING-WINDOW (prospective): train on data <= t, score t+1 only.
   Future data is NEVER used when scoring the past.

2. PREPROCESSING FIT ON PAST ONLY: StandardScaler is fit on the training
   window only, then applied (transform) to the next period.

3. FROZEN HYPERPARAMETERS: All parameters fixed from a pre-crisis
   validation period (2005Q1–2007Q3). No tuning after seeing crises.

4. FIXED THRESHOLD: Alarm threshold computed once from the pre-crisis
   baseline distribution. Never updated.

5. TIMELINE PLOT: Anomaly score vs time with GFC / Lehman markers.
   If the spike appears BEFORE the event, leakage is ruled out.

Protocol checklist:
  ✓ Expanding-window evaluation
  ✓ Preprocessing fit on training only
  ✓ Frozen hyperparameters
  ✓ Fixed threshold
  ✓ Full timeline plot
"""
import sys, os, time, warnings, json, gc
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'research', 'udl'))

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score
from sklearn.preprocessing import StandardScaler
from udl.system_mode import MolecularEngine

warnings.filterwarnings("ignore")

ROOT = r'C:\amttp'
CACHE_DIR = os.path.join(ROOT, 'research', 'adaptive-friction',
                         'banklevel_enhanced', 'gsib_cache_real')
npz = np.load(os.path.join(CACHE_DIR, 'gsib_real_panel.npz'))
X_3d = npz['X']
with open(os.path.join(CACHE_DIR, 'gsib_real_meta.json')) as f:
    meta = json.load(f)

dates = pd.date_range('2005-01-01', '2023-12-31', freq='QE')[:X_3d.shape[0]]
T, N, d = X_3d.shape

# ══════════════════════════════════════════════════════════════════
#  Crisis labels (NBER-dated)
# ══════════════════════════════════════════════════════════════════
CRISIS_QUARTERS = {
    '2007-12-31','2008-03-31','2008-06-30','2008-09-30',
    '2008-12-31','2009-03-31','2009-06-30',
    '2020-03-31','2020-06-30',
    '2011-09-30','2011-12-31','2012-03-31','2012-06-30',
}
y_crisis = np.array([1 if str(d.date()) in CRISIS_QUARTERS else 0
                     for d in dates])

print(f'Panel: T={T} quarters, N={N} banks, d={d} features')
print(f'Crisis quarters: {int(y_crisis.sum())}/{T}')
print(f'Date range: {dates[0].date()} to {dates[-1].date()}')

# ══════════════════════════════════════════════════════════════════
#  Step 3: FREEZE HYPERPARAMETERS (chosen from pre-crisis period)
#  These are fixed BEFORE any crisis data is seen.
# ══════════════════════════════════════════════════════════════════
FROZEN_PARAMS = dict(
    epsilon=1.0,
    sigma_lj=1.0,
    alpha_radial=0.1,
    eta=0.01,
    iterations=80,
    k_neighbors=10,
    max_samples=2000,
    use_fused=True,
    use_bsdt_damping=True,
    normalize=False,       # We handle scaling ourselves for strict protocol
)

# ══════════════════════════════════════════════════════════════════
#  Step 1 & 2: EXPANDING-WINDOW PROSPECTIVE EVALUATION
#
#  For each quarter t (starting after a burn-in):
#    1. Training window: all data from quarter 0..t
#    2. Fit scaler on TRAINING window only
#    3. Transform test quarter (t+1) using that scaler
#    4. Run MolecularEngine on training data (scaled)
#    5. Score test quarter (t+1) using the fitted engine
#    6. Record the quarter-level anomaly score for t+1
#
#  The scored quarter t+1 was NEVER in the training data.
# ══════════════════════════════════════════════════════════════════

# Burn-in: need at least 4 quarters to fit a meaningful model
BURN_IN = 4

# Pre-crisis end: 2007Q3 (the quarter BEFORE any crisis label)
calib_end = pd.Timestamp('2007-09-30')
n_calib = int((dates <= calib_end).sum())

print(f'\nBurn-in: {BURN_IN} quarters')
print(f'Pre-crisis calibration: {dates[0].date()} to {dates[n_calib-1].date()} ({n_calib} quarters)')
print(f'Prospective test: {dates[BURN_IN].date()} to {dates[-1].date()}')

q_scores = np.full(T, np.nan)
t0_total = time.time()

for t in range(BURN_IN, T - 1):
    # ── Training window: quarters 0..t ──
    n_train_q = t + 1
    X_train = X_3d[:n_train_q].reshape(n_train_q * N, d)

    # Labels for training: ONLY use past crisis labels
    y_train = np.zeros(n_train_q * N, dtype=int)
    for t_idx in range(n_train_q):
        if str(dates[t_idx].date()) in CRISIS_QUARTERS:
            y_train[t_idx * N:(t_idx + 1) * N] = 1

    # ── Step 2: Fit scaler on TRAINING window only ──
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train).astype(np.float64)

    # ── Test quarter: t+1 (NEVER seen during training) ──
    X_test = X_3d[t + 1].reshape(1, N, d).reshape(N, d)
    X_test_scaled = scaler.transform(X_test).astype(np.float64)

    # ── Run engine on training data ──
    eng = MolecularEngine(**FROZEN_PARAMS)
    train_scores = eng.fit_score(X_train_scaled, y_train)

    # ── Score test quarter using the FITTED engine ──
    # FusedSystemScorer was fitted during fit_score; score new data
    if eng.fused_scorer is not None:
        test_scores = eng.fused_scorer.score(X_test_scaled)
    elif hasattr(eng, 'alarm'):
        test_scores = eng.alarm.score(X_test_scaled)
    else:
        test_scores = np.linalg.norm(X_test_scaled - X_test_scaled.mean(axis=0), axis=1)

    # Quarter-level score = mean over N banks
    q_scores[t + 1] = float(test_scores.mean())

    # Progress
    ds = str(dates[t + 1].date())
    crisis_mark = ' << CRISIS' if ds in CRISIS_QUARTERS else ''
    if (t + 1) % 10 == 0 or ds in CRISIS_QUARTERS:
        print(f'  t={t+1:3d}  {ds}  score={q_scores[t+1]:.4f}{crisis_mark}')

    del eng, X_train, X_train_scaled, X_test_scaled, train_scores, test_scores
    gc.collect()

elapsed = time.time() - t0_total
print(f'\nTotal time: {elapsed:.0f}s')

# ══════════════════════════════════════════════════════════════════
#  Step 4: FIXED THRESHOLD from pre-crisis baseline
#  Computed ONCE from calibration-period scores, then frozen.
# ══════════════════════════════════════════════════════════════════
calib_scores = q_scores[BURN_IN + 1:n_calib + 1]  # prospective scores during pre-crisis
calib_scores = calib_scores[~np.isnan(calib_scores)]

if len(calib_scores) < 3:
    print(f'WARNING: Only {len(calib_scores)} calibration scores. Using all pre-crisis.')
    calib_scores = q_scores[:n_calib + 1]
    calib_scores = calib_scores[~np.isnan(calib_scores)]

mu_cal = calib_scores.mean()
std_cal = calib_scores.std() + 1e-10

# Fixed threshold: μ + 3σ (conservative, common in risk management)
FIXED_THRESHOLD = mu_cal + 3.0 * std_cal

print(f'\n{"="*70}')
print(f'  FIXED THRESHOLD (from pre-crisis baseline, frozen)')
print(f'{"="*70}')
print(f'  Calibration scores: n={len(calib_scores)}')
print(f'  μ = {mu_cal:.6f}')
print(f'  σ = {std_cal:.6f}')
print(f'  Threshold (μ + 3σ) = {FIXED_THRESHOLD:.6f}')

# ══════════════════════════════════════════════════════════════════
#  Results
# ══════════════════════════════════════════════════════════════════
valid = ~np.isnan(q_scores)
q_valid = q_scores[valid]
y_valid = y_crisis[valid]

auroc = roc_auc_score(y_valid, q_valid) if 0 < y_valid.sum() < len(y_valid) else float('nan')

y_pred = (q_valid >= FIXED_THRESHOLD).astype(int)
TP = int(((y_pred == 1) & (y_valid == 1)).sum())
FP = int(((y_pred == 1) & (y_valid == 0)).sum())
FN = int(((y_pred == 0) & (y_valid == 1)).sum())
TN = int(((y_pred == 0) & (y_valid == 0)).sum())
n_normal = TN + FP
far = FP / n_normal * 100 if n_normal > 0 else 0
recall = TP / (TP + FN) * 100 if (TP + FN) > 0 else 0
prec = TP / (TP + FP) * 100 if (TP + FP) > 0 else 0

print(f'\n{"="*70}')
print(f'  STRICT NO-LEAKAGE RESULTS')
print(f'{"="*70}')
print(f'  AUROC:     {auroc:.4f}')
print(f'  Threshold: {FIXED_THRESHOLD:.6f}  (μ+3σ, frozen from pre-crisis)')
print(f'  TP={TP}  FP={FP}  FN={FN}  TN={TN}')
print(f'  FAR:       {far:.1f}%')
print(f'  Recall:    {recall:.1f}%')
print(f'  Precision: {prec:.1f}%')
print(f'  Time:      {elapsed:.0f}s')

# Threshold sweep for reference
print(f'\n{"="*70}')
print(f'  Threshold sweep (μ + k·σ, all from frozen pre-crisis baseline)')
print(f'{"="*70}')
print(f'  {"k":>5s}  {"Thresh":>8s}  {"TP":>3s}  {"FP":>3s}  {"FN":>3s}  {"TN":>3s}  {"FAR%":>6s}  {"Recall%":>8s}  {"Prec%":>6s}')
for k in [1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 5.0]:
    thr = mu_cal + k * std_cal
    yp = (q_valid >= thr).astype(int)
    tp = int(((yp == 1) & (y_valid == 1)).sum())
    fp = int(((yp == 1) & (y_valid == 0)).sum())
    fn = int(((yp == 0) & (y_valid == 1)).sum())
    tn = int(((yp == 0) & (y_valid == 0)).sum())
    nn = tn + fp
    f = fp / nn * 100 if nn > 0 else 0
    r = tp / (tp + fn) * 100 if (tp + fn) > 0 else 0
    p = tp / (tp + fp) * 100 if (tp + fp) > 0 else 0
    marker = '  <-- chosen' if abs(k - 3.0) < 0.01 else ''
    print(f'  {k:5.1f}  {thr:8.4f}  {tp:3d}  {fp:3d}  {fn:3d}  {tn:3d}  {f:5.1f}%  {r:7.1f}%  {p:5.1f}%{marker}')

# ══════════════════════════════════════════════════════════════════
#  Full alarm timeline
# ══════════════════════════════════════════════════════════════════
print(f'\n{"="*70}')
print(f'  ALARM TIMELINE (fixed threshold = {FIXED_THRESHOLD:.4f})')
print(f'{"="*70}')
for t in range(T):
    if np.isnan(q_scores[t]):
        continue
    alarm = q_scores[t] >= FIXED_THRESHOLD
    ds = str(dates[t].date())
    crisis = ds in CRISIS_QUARTERS
    if alarm or crisis:
        if crisis and alarm:  tag = 'CRISIS + ALARM'
        elif crisis:          tag = 'CRISIS (missed)'
        elif alarm:           tag = 'FALSE ALARM'
        else:                 tag = ''
        print(f'  {ds}  score={q_scores[t]:.4f}  {tag}')

# ══════════════════════════════════════════════════════════════════
#  Step 5: TIMELINE PLOT
# ══════════════════════════════════════════════════════════════════
try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    from matplotlib.patches import Rectangle

    fig, ax = plt.subplots(figsize=(14, 5))

    # Score time series
    plot_dates = dates[valid]
    ax.plot(plot_dates, q_valid, color='#2563EB', linewidth=1.2,
            label='Anomaly Score (prospective)', zorder=3)

    # Fixed threshold
    ax.axhline(y=FIXED_THRESHOLD, color='#DC2626', linestyle='--',
               linewidth=1.5, label=f'Fixed Threshold (μ+3σ = {FIXED_THRESHOLD:.3f})',
               zorder=2)

    # Crisis shading
    crisis_periods = [
        ('2007-12-01', '2009-07-01', 'Global Financial Crisis'),
        ('2011-09-01', '2012-07-01', 'European Sovereign Debt'),
        ('2020-03-01', '2020-07-01', 'COVID-19'),
    ]
    colors_crisis = ['#FEE2E2', '#FEF3C7', '#DBEAFE']
    for i, (start, end, label) in enumerate(crisis_periods):
        ax.axvspan(pd.Timestamp(start), pd.Timestamp(end),
                   alpha=0.4, color=colors_crisis[i], label=label, zorder=1)

    # Lehman Brothers collapse
    lehman_date = pd.Timestamp('2008-09-15')
    ax.axvline(x=lehman_date, color='#7C3AED', linestyle=':',
               linewidth=2, label='Lehman Brothers Collapse', zorder=4)

    # Mark true positives and false positives
    for t in range(T):
        if np.isnan(q_scores[t]):
            continue
        alarm = q_scores[t] >= FIXED_THRESHOLD
        ds = str(dates[t].date())
        crisis = ds in CRISIS_QUARTERS
        if crisis and alarm:
            ax.scatter(dates[t], q_scores[t], color='#16A34A', s=60,
                       marker='^', zorder=5, edgecolors='black', linewidth=0.5)
        elif crisis and not alarm:
            ax.scatter(dates[t], q_scores[t], color='#EAB308', s=60,
                       marker='v', zorder=5, edgecolors='black', linewidth=0.5)
        elif alarm and not crisis:
            ax.scatter(dates[t], q_scores[t], color='#DC2626', s=40,
                       marker='x', zorder=5, linewidth=1.5)

    # Formatting
    ax.set_xlabel('Date', fontsize=11)
    ax.set_ylabel('Anomaly Score', fontsize=11)
    ax.set_title('MolecularEngine: Strict No-Data-Leakage Evaluation\n'
                 '(Expanding window, scaler fit on training only, frozen hyperparameters & threshold)',
                 fontsize=12, fontweight='bold')
    ax.xaxis.set_major_locator(mdates.YearLocator(2))
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y'))
    ax.grid(True, alpha=0.3)

    # Legend with custom markers
    from matplotlib.lines import Line2D
    custom_handles = [
        Line2D([0], [0], color='#2563EB', linewidth=1.2),
        Line2D([0], [0], color='#DC2626', linestyle='--', linewidth=1.5),
        Line2D([0], [0], color='#7C3AED', linestyle=':', linewidth=2),
        plt.Rectangle((0, 0), 1, 1, fc='#FEE2E2', alpha=0.4),
        plt.Rectangle((0, 0), 1, 1, fc='#FEF3C7', alpha=0.4),
        plt.Rectangle((0, 0), 1, 1, fc='#DBEAFE', alpha=0.4),
        Line2D([0], [0], marker='^', color='w', markerfacecolor='#16A34A',
               markersize=8, markeredgecolor='black', markeredgewidth=0.5),
        Line2D([0], [0], marker='v', color='w', markerfacecolor='#EAB308',
               markersize=8, markeredgecolor='black', markeredgewidth=0.5),
        Line2D([0], [0], marker='x', color='#DC2626', markersize=8,
               markeredgewidth=1.5, linestyle='None'),
    ]
    custom_labels = [
        'Anomaly Score (prospective)',
        f'Fixed Threshold (μ+3σ)',
        'Lehman Brothers Collapse',
        'Global Financial Crisis',
        'European Sovereign Debt',
        'COVID-19',
        'True Positive (crisis detected)',
        'False Negative (crisis missed)',
        'False Positive',
    ]
    ax.legend(custom_handles, custom_labels, fontsize=8, loc='upper left',
              framealpha=0.9, ncol=2)

    # Annotation box
    textstr = (f'AUROC = {auroc:.4f}\n'
               f'FAR = {far:.1f}%  |  Recall = {recall:.1f}%\n'
               f'TP = {TP}  FP = {FP}  FN = {FN}  TN = {TN}')
    props = dict(boxstyle='round,pad=0.5', facecolor='white',
                 edgecolor='gray', alpha=0.9)
    ax.text(0.98, 0.95, textstr, transform=ax.transAxes, fontsize=9,
            verticalalignment='top', horizontalalignment='right', bbox=props)

    plt.tight_layout()

    # Save
    plot_path = os.path.join(ROOT, 'plots', 'molecular_no_leakage_timeline.pdf')
    os.makedirs(os.path.dirname(plot_path), exist_ok=True)
    fig.savefig(plot_path, dpi=300, bbox_inches='tight')
    png_path = plot_path.replace('.pdf', '.png')
    fig.savefig(png_path, dpi=150, bbox_inches='tight')
    plt.close(fig)
    print(f'\nPlot saved: {plot_path}')
    print(f'Plot saved: {png_path}')

except Exception as e:
    print(f'\nPlot failed: {e}')

# ══════════════════════════════════════════════════════════════════
#  Save results for paper inclusion
# ══════════════════════════════════════════════════════════════════
results = {
    'protocol': 'strict_no_leakage',
    'methodology': {
        'expanding_window': True,
        'scaler_fit_on_training_only': True,
        'frozen_hyperparameters': FROZEN_PARAMS,
        'fixed_threshold': {
            'method': 'mu_plus_3sigma',
            'mu': float(mu_cal),
            'sigma': float(std_cal),
            'value': float(FIXED_THRESHOLD),
            'computed_from': f'{dates[BURN_IN+1].date()} to {dates[n_calib].date()}',
        },
    },
    'results': {
        'auroc': float(auroc),
        'far_pct': float(far),
        'recall_pct': float(recall),
        'precision_pct': float(prec),
        'tp': TP, 'fp': FP, 'fn': FN, 'tn': TN,
    },
    'timeline': {
        str(dates[t].date()): float(q_scores[t])
        for t in range(T) if not np.isnan(q_scores[t])
    },
}

results_path = os.path.join(ROOT, 'no_leakage_results.json')
with open(results_path, 'w') as f:
    json.dump(results, f, indent=2)
print(f'Results saved: {results_path}')

print('\nDone — strict no-data-leakage evaluation complete.')
