"""
Crypto BSDT v23 — Tensor Representation Comparison
====================================================

Runs the same v22 pipeline under five different state-tensor representations
and compares trading results side-by-side.

  REPR-1  plain         (T, N=4, d=2)        ret_z + vol_z  [v22 baseline]
  REPR-2  udl           (T, N=4, d=8)        UDLTransform: stat+chaos+spec+geom -> PCA-8
  REPR-3  rtd           (T, N=4, d=n_eigs+6) ReducedTensorDescriptor
  REPR-4  coverage      (T, N=4, d=D_ops)    UDLPostSimScorer: Phase+Topo+Kernel+Rank
  REPR-5  mdn           (T, N=4, d=5)        AnomalyTensor: per-law magnitudes + novelty

Only the panel-building stage changes. Everything downstream (calibrate_frozen_engine,
patch_precursor_scale, emit_global_signals, two-layer alarms, Kramers leverage,
ALLOC_V21 allocator, simulate_from_pnl) is IDENTICAL for every representation.

NOTE: calibrate_frozen_engine hardcodes LedoitWolfNetwork.from_panel(X[..., 0])
      so only channel-0 feeds the correlation network regardless of d.
      MasterOperator, EWS, and Kramers use the full d-dimensional state.
"""
from __future__ import annotations
import os, sys, json, time
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")

from pathlib import Path
import numpy as np
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ── reuse v19/v22 stacks ─────────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent))
import run_crypto_pairs_v19 as v19
from run_crypto_pairs_v19 import (
    fetch_and_prepare, add_cross_market_features,
    fetch_binance_funding, add_leverage_features,
    compute_bsdt, compute_gamma_rank, compute_activity_signals,
    compute_state_vector, compute_geom_signals_v18_smooth,
    apply_geom_penalties_v18, compute_leverage_dial,
    compute_rolling_spread_v8, SpreadUDLClassifier,
    compute_manifold_validity, detect_phase,
    route_pair_v7, route_btcalt_macro, setup_a_directional,
    get_daily_pnl, compute_cs_weights,
    simulate_from_pnl, equity_at_K, find_best_K,
    _build_state_panel,
    TRAIN_START, TRAIN_END, TEST_START, OUT_DIR,
    GAMMA_SCORE_WIN,
)
from run_crypto_pairs_v22 import (
    calibrate_frozen_engine,    # re-exported from v21
    apply_alarm_latch,          # re-exported from v21
    patch_precursor_scale,
    emit_global_signals,
    two_layer_from_signals,
    rolling_layer_b_alarm,
    HISTORY_LEN, ALARM_LATCH_DAYS,
    LAYER_A_THRESHOLD, LAYER_B_N_SIGMA, ROLL_WIN,
    LEV_LO, LEV_HI, KRAMERS_TAU,
    ALLOC_V21,
)

# ── collapse_geometry (adaptive-friction package) ─────────────────────────────
sys.path.insert(0, r'C:\amttp\research\adaptive-friction')
from collapse_geometry import (
    MasterOperator, Snapshot, LedoitWolfNetwork,
    LyapunovCertificate, CollapseGeometry,
    EarlyWarning, PrecursorScale,
    InformationGeometry, StochasticExtension,
)

# UDLTransform + private domain classes
_HAS_UDL = False
try:
    from collapse_geometry.udl_transform import (
        UDLTransform,
        _StatFeatures, _ChaosFeatures, _SpecFeatures, _GeomFeatures,
    )
    _HAS_UDL = True
except ImportError as _e:
    print(f"  [v23] WARNING: UDLTransform unavailable ({_e})")

# ReducedTensorDescriptor + UDLPostSimScorer from production system_mode
_HAS_SYSMODE = False
try:
    sys.path.insert(0, r'C:\amttp\src')
    from system_mode import ReducedTensorDescriptor, UDLPostSimScorer  # type: ignore
    _HAS_SYSMODE = True
except Exception as _e:
    print(f"  [v23] WARNING: system_mode unavailable ({_e})")

# AnomalyTensor (MDN) from research/udl
_HAS_ANOMALY = False
try:
    sys.path.insert(0, r'C:\amttp\research\udl')
    from udl.tensor import AnomalyTensor  # type: ignore
    _HAS_ANOMALY = True
except Exception as _e:
    print(f"  [v23] WARNING: AnomalyTensor unavailable ({_e})")


# ═══════════════════════════════════════════════════════════════════════════
#   HELPER: flatten-fit-transform for 2D-API transforms (RTD, Coverage)
# ═══════════════════════════════════════════════════════════════════════════

def _flat_fit_transform(transformer, X_panel: np.ndarray,
                        train_mask_arr: np.ndarray) -> np.ndarray:
    """Flatten (T, N, d) -> (T*N, d), fit on train rows, transform all.

    Returns (T, N, d_out) panel.
    """
    T, N, d = X_panel.shape
    X_flat  = X_panel.reshape(T * N, d)
    X_train = X_panel[train_mask_arr].reshape(-1, d)
    transformer.fit(X_train)
    X_out   = transformer.transform(X_train[:1])   # probe to get d_out then discard
    d_out   = X_out.shape[1]
    # Transform all at once for efficiency
    out     = transformer.transform(X_flat)        # (T*N, d_out)
    out     = np.nan_to_num(out, nan=0.0, posinf=0.0, neginf=0.0)
    return out.reshape(T, N, d_out).astype(np.float64)


# ═══════════════════════════════════════════════════════════════════════════
#   PANEL BUILDERS — one per representation
# ═══════════════════════════════════════════════════════════════════════════

def build_panel_plain(df, train_mask_arr=None) -> np.ndarray:
    """REPR-1: plain (T, 4, 2) ret_z + vol_z — v22 baseline."""
    return _build_state_panel(df)


def build_panel_udl(df, train_mask_arr: np.ndarray) -> np.ndarray:
    """REPR-2: (T, 4, 8) via UDLTransform.

    UDLTransform.fit() and .transform() both expect 3D (T0, N, d).
    """
    if not _HAS_UDL:
        raise RuntimeError("UDLTransform not available")
    X_plain = _build_state_panel(df)
    udl = UDLTransform(n_components=8, standardize=True)
    udl.fit(X_plain[train_mask_arr])
    X_out = udl.transform(X_plain)          # (T, N, 8)
    X_out = np.nan_to_num(X_out, nan=0.0, posinf=0.0, neginf=0.0)
    return X_out.astype(np.float64)


def build_panel_rtd(df, train_mask_arr: np.ndarray) -> np.ndarray:
    """REPR-3: (T, 4, n_eigs+6) via ReducedTensorDescriptor.

    With d=2: n_eigs = min(2, 10) = 2 -> d_out = 8.
    """
    if not _HAS_SYSMODE:
        raise RuntimeError("ReducedTensorDescriptor not available (system_mode missing)")
    X_plain = _build_state_panel(df)
    rtd = ReducedTensorDescriptor(k_neighbors=15, eps_hessian=1e-4)
    return _flat_fit_transform(rtd, X_plain, train_mask_arr)


def build_panel_coverage(df, train_mask_arr: np.ndarray) -> np.ndarray:
    """REPR-4: (T, 4, D_ops) via UDLPostSimScorer (Phase+Topo+Kernel+Rank).

    Falls back to UDLTransform if import or fit fails.
    """
    if not _HAS_SYSMODE:
        raise RuntimeError("UDLPostSimScorer not available (system_mode missing)")
    X_plain = _build_state_panel(df)
    cov = UDLPostSimScorer(k=15, max_dim=12, n_components=8)
    return _flat_fit_transform(cov, X_plain, train_mask_arr)


def build_panel_mdn(df, train_mask_arr: np.ndarray) -> np.ndarray:
    """REPR-5: (T, 4, 5) MDN — per-law magnitudes (4) + novelty (1).

    Pipeline:
      1. z-normalise the plain (T*4, 2) flat panel
      2. Apply each domain class to produce R=(T*4, 17)
      3. AnomalyTensor.build(R, law_dims=[5,3,4,5]) -> TensorResult
      4. Feature vector: [law_magnitudes(4), novelty(1)] -> z-score vs train
    """
    if not (_HAS_UDL and _HAS_ANOMALY):
        missing = []
        if not _HAS_UDL:     missing.append("UDLTransform domain classes")
        if not _HAS_ANOMALY: missing.append("AnomalyTensor")
        raise RuntimeError(f"MDN unavailable: {', '.join(missing)}")

    X_plain = _build_state_panel(df)
    T, N, d = X_plain.shape
    X_flat  = X_plain.reshape(T * N, d)

    # z-normalise using train stats
    X_train_flat = X_plain[train_mask_arr].reshape(-1, d)
    mu_in = X_train_flat.mean(axis=0)
    sd_in = X_train_flat.std(axis=0) + 1e-10
    X_std       = (X_flat       - mu_in) / sd_in
    X_std_train = (X_train_flat - mu_in) / sd_in

    # Build 17D representation via domain operators
    stat  = _StatFeatures().fit(X_std_train)
    chaos = _ChaosFeatures().fit(X_std_train)
    spec  = _SpecFeatures().fit(X_std_train)
    geom  = _GeomFeatures(n_pca=min(2, d)).fit(X_std_train)

    R_all   = np.hstack([stat.transform(X_std),
                         chaos.transform(X_std),
                         spec.transform(X_std),
                         geom.transform(X_std)])       # (T*N, 17)
    R_train = np.hstack([stat.transform(X_std_train),
                         chaos.transform(X_std_train),
                         spec.transform(X_std_train),
                         geom.transform(X_std_train)]) # (n_train*N, 17)
    R_all   = np.nan_to_num(R_all,   nan=0.0, posinf=0.0, neginf=0.0)
    R_train = np.nan_to_num(R_train, nan=0.0, posinf=0.0, neginf=0.0)

    law_dims = [5, 3, 4, 5]
    at = AnomalyTensor()
    at.fit(R_train)
    res_train = at.build(R_train, law_dims)
    at.store_ref_law_stats(res_train)
    res_all   = at.build(R_all,   law_dims)

    lm   = res_all.law_magnitudes      # (T*N, 4)
    nov  = res_all.novelty[:, None]    # (T*N, 1)

    lm_train  = res_train.law_magnitudes
    nov_train = res_train.novelty[:, None]
    lm_mu = lm_train.mean(0);  lm_sd = lm_train.std(0) + 1e-10
    nov_mu = float(nov_train.mean()); nov_sd = float(nov_train.std()) + 1e-10

    lm_z  = (lm  - lm_mu)  / lm_sd
    nov_z = (nov - nov_mu) / nov_sd

    X_mdn = np.hstack([lm_z, nov_z])
    X_mdn = np.nan_to_num(X_mdn, nan=0.0, posinf=0.0, neginf=0.0)
    return X_mdn.reshape(T, N, 5).astype(np.float64)


REPR_BUILDERS: dict = {
    'plain':    build_panel_plain,
    'udl':      build_panel_udl,
    'rtd':      build_panel_rtd,
    'coverage': build_panel_coverage,
    'mdn':      build_panel_mdn,
}

REPR_LABELS: dict = {
    'plain':    'plain (d=2)             ',
    'udl':      'UDLTransform (d=8)      ',
    'rtd':      'ReducedTensor (d=n+6)   ',
    'coverage': 'CoverageTensor (d=D_ops)',
    'mdn':      'MDN (d=5)              ',
}

# Layer A rolling calibration: fire when precursor_score > rolling μ + LAYER_A_N_SIGMA·σ
# (1-day lagged, no lookahead — same design as rolling Layer B).
# 1.28σ ≈ 90th percentile tail; makes alarm rate representation-scale-independent.
LAYER_A_N_SIGMA       = 1.28
LAYER_A_TRAIN_QUANTILE = 90.0   # kept for diagnostics only


# ═══════════════════════════════════════════════════════════════════════════
#   SHARED PIPELINE RUNNER — identical for all 5 representations
# ═══════════════════════════════════════════════════════════════════════════

def run_repr_pipeline(X_panel: np.ndarray,
                      train_mask_arr: np.ndarray,
                      df: pd.DataFrame,
                      test_mask,
                      pnl_v18s: pd.Series) -> tuple:
    """Run the frozen v22 engine on a given (T, N, d_out) state panel.

    Both Layer A and Layer B use rolling thresholds (1-day lagged, no lookahead),
    making alarm calibration representation-scale-independent:
      Layer A: precursor_score > rolling μ + LAYER_A_N_SIGMA · σ  (1.28σ ≈ 90th pct)
      Layer B: geom_score      > rolling μ + LAYER_B_N_SIGMA · σ  (1.00σ ≈ 84th pct)

    Returns (sim_dict, pnl_series, diagnostic_dict).
    """
    # Calibrate engine on the new panel shape (frozen on train window)
    M, net, geom, lyap, info, ews, e_star, sigma_n = calibrate_frozen_engine(
        X_panel, train_mask_arr)
    patch_precursor_scale(ews, M, X_panel[train_mask_arr])

    # Full signal sweep (all T rows)
    F = emit_global_signals(df, X_panel, M, net, geom, lyap, ews, sigma_n)

    # Rolling Layer A — same design as rolling Layer B
    _, alarm_A = rolling_layer_b_alarm(
        F['precursor_score'].fillna(0.0),
        n_sigma=LAYER_A_N_SIGMA, win=ROLL_WIN, min_periods=60)

    # Rolling Layer B (unchanged from v22)
    _, alarm_B = rolling_layer_b_alarm(
        F['geom_score'].fillna(0.0),
        n_sigma=LAYER_B_N_SIGMA, win=ROLL_WIN, min_periods=60)

    # Compose two-layer signal
    layer = pd.Series('', index=F.index)
    layer[alarm_A &  alarm_B] = 'AB'
    layer[alarm_A & ~alarm_B] = 'A'
    layer[~alarm_A & alarm_B] = 'B'
    F = F.copy()
    F['layer']     = layer
    F['alarm_A']   = alarm_A.astype(int)
    F['alarm_B']   = alarm_B.astype(int)
    F['alarm_raw'] = (alarm_A | alarm_B).astype(int)

    # Compute calibrated rolling threshold for diagnostics
    pre_train = F.loc[df.index[train_mask_arr], 'precursor_score'].dropna()
    a_thresh_diag = float(np.percentile(pre_train.values, LAYER_A_TRAIN_QUANTILE)) \
                    if len(pre_train) >= 30 else np.nan
    print(f"  [v23] Rolling Layer A (n_sigma={LAYER_A_N_SIGMA})  "
          f"train-90th for reference: {a_thresh_diag:.4f}")

    alarm_latched = apply_alarm_latch(F, min_steps=ALARM_LATCH_DAYS)
    layers        = F['layer'].fillna('').values

    # v21-style four-state global gate
    g_pos  = np.ones(len(F))
    g_cash = np.zeros(len(F))
    last_layer = ""
    for i, (lat, ly) in enumerate(zip(alarm_latched.values, layers)):
        if lat:
            if ly:
                last_layer = ly
            ps, cs = ALLOC_V21.get(last_layer or "B", ALLOC_V21["B"])
        else:
            last_layer = ""
            ps, cs = ALLOC_V21[""]
        g_pos[i], g_cash[i] = ps, cs

    # Kramers leverage damp (same formula as v21_full in v22)
    p_kr    = F['kramers_p'].fillna(0.0).clip(0.0, 1.0).values
    lev     = np.clip(g_pos * (1.0 - p_kr), LEV_LO, LEV_HI)
    lev_s   = pd.Series(lev, index=F.index).ewm(span=5, adjust=False).mean()
    lev_s   = lev_s.clip(lower=LEV_LO, upper=LEV_HI)

    pnl = pnl_v18s * g_pos * (1.0 - g_cash) * lev_s.values
    sim = simulate_from_pnl(pnl[test_mask].fillna(0.0))

    diag = {
        'panel_d':             int(X_panel.shape[2]),
        'layer_A_days':        int(F[test_mask]['alarm_A'].sum()),
        'layer_B_days':        int(F[test_mask]['alarm_B'].sum()),
        'latched_days':        int(alarm_latched[test_mask].sum()),
        'mean_lev':            float(lev_s[test_mask].mean()),
        'a_threshold_calib':   float(a_thresh_diag),
        'e_star':              float(e_star),
        'sigma_n':             float(sigma_n),
    }
    return sim, pnl, diag


# ═══════════════════════════════════════════════════════════════════════════
#   MAIN
# ═══════════════════════════════════════════════════════════════════════════

def main():
    out_dir = Path(OUT_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 96)
    print("  CRYPTO BSDT v23 — Tensor Representation Comparison")
    print("  plain | UDLTransform | ReducedTensor | CoverageTensor | MDN")
    print("=" * 96)

    # ── data ─────────────────────────────────────────────────────────────────
    print("\n[1] Fetching and preparing data ...")
    df = fetch_and_prepare()
    df = add_cross_market_features(df)
    funding = fetch_binance_funding(symbols=['ETHUSDT', 'BTCUSDT'], start='2020-06-01')
    df = add_leverage_features(df, funding)

    train_mask     = (df.index >= TRAIN_START) & (df.index <= TRAIN_END)
    test_mask      = df.index >= TEST_START
    train_mask_arr = np.asarray(train_mask, dtype=bool)

    print(f"  Train {df[train_mask].index[0].date()} -> {df[train_mask].index[-1].date()}"
          f"  ({int(train_mask.sum())}d)")
    print(f"  Test  {df[test_mask].index[0].date()}  -> {df[test_mask].index[-1].date()}"
          f"  ({int(test_mask.sum())}d)")

    # ── shared v18_smooth baseline PnL ───────────────────────────────────────
    print("\n[2] Building shared v18_smooth baseline ...")
    feats_strat = ['ret_eth_z', 'ret_btc_z', 'ret_sol_z', 'ret_bnb_z',
                   'vol_eth_z', 'vol_btc_z', 'btc_dom_z', 'cross_disp_z']
    feats_ext   = feats_strat + ['ret_spx_z', 'dvix_z', 'ret_dxy_z']

    omega_strat, mfls_eth, gamma_eth = compute_bsdt(df, feats_strat, window=60)
    omega_ext,   _,        _         = compute_bsdt(df, feats_ext,   window=60)
    A_eth, A_rank, dA_fast, dA_rank  = compute_activity_signals(mfls_eth, gamma_eth)
    gamma_rank  = compute_gamma_rank(omega_ext, min_periods=60)
    lev_mult    = compute_leverage_dial(gamma_rank)

    ret7  = df['ret_eth'].rolling(7).sum()
    ret3  = df['ret_eth'].rolling(3).sum()
    phase = detect_phase(omega_strat, ret7, ret3, df['btc_dom_z'])
    pos_A_dir = setup_a_directional(df, omega_strat, mfls_eth, gamma_eth, phase)

    pairs_def = [
        ('P1_ETH_BTC', 'log_eth', 'log_btc', 'ret_eth', 'ret_btc'),
        ('P2_ETH_SOL', 'log_eth', 'log_sol', 'ret_eth', 'ret_sol'),
        ('P3_ETH_BNB', 'log_eth', 'log_bnb', 'ret_eth', 'ret_bnb'),
    ]
    pair_data = {}
    for key, col_a, col_b, ret_a, ret_b in pairs_def:
        sd = compute_rolling_spread_v8(
            df[col_a], df[col_b], df[ret_a], df[ret_b],
            train_mask=train_mask, beta_window=252)
        clf = SpreadUDLClassifier(window=20, n_ref_dirs=100).fit(
            sd['spread'][train_mask].dropna())
        udl_s, udl_m, udl_n = clf.classify_series(sd['spread'])
        sd['udl_state'] = udl_s
        mval, _ = compute_manifold_validity(sd['z'], sd['sret'])
        sd['manifold_valid'] = mval
        pair_data[key] = sd

    pair_pos = {k: route_pair_v7(omega_strat, A_rank, pair_data[k]['z'],
                                  pair_data[k]['udl_state'], pair_data[k]['poa'],
                                  pair_data[k]['manifold_valid'])
                for k, *_ in pairs_def}
    pos_btc_macro, pos_alt_macro = route_btcalt_macro(df, omega_strat, A_rank, dA_rank)

    pnl_base = {
        'A_directional': get_daily_pnl(pos_A_dir, df['ret_eth']),
        'P1_ETH_BTC':    get_daily_pnl(pair_pos['P1_ETH_BTC'],
                                        pair_data['P1_ETH_BTC']['sret']),
        'P2_ETH_SOL':    get_daily_pnl(pair_pos['P2_ETH_SOL'],
                                        pair_data['P2_ETH_SOL']['sret']),
        'P3_ETH_BNB':    get_daily_pnl(pair_pos['P3_ETH_BNB'],
                                        pair_data['P3_ETH_BNB']['sret']),
        'M1_ALT_macro':  get_daily_pnl(pos_alt_macro, df['ret_eth']),
        'M1_BTC_macro':  get_daily_pnl(pos_btc_macro, df['ret_btc']),
    }
    V_state  = compute_state_vector(omega_strat, gamma_rank, mfls_eth, dA_fast)
    phi_18s, align_18s = compute_geom_signals_v18_smooth(V_state)
    lev_v18s = apply_geom_penalties_v18(lev_mult, phi_18s, align_18s)
    cs_wts   = compute_cs_weights(pnl_base, window=GAMMA_SCORE_WIN)
    n_s      = len(pnl_base)
    pnl_v10  = pd.Series(0.0, index=df.index)
    for k in pnl_base:
        pnl_v10 += cs_wts[k].shift(1).fillna(1.0 / n_s) * pnl_base[k]
    pnl_v18s = pnl_v10 * lev_v18s.shift(1).fillna(1.0)

    sim_base = simulate_from_pnl(pnl_v18s[test_mask].fillna(0.0))
    print(f"  v18_smooth baseline: Sharpe {sim_base['sharpe']:+.4f}  "
          f"MaxDD {sim_base['max_dd']:+.4f}  CAGR {100*sim_base['cagr']:+.2f}%")

    # ── run each representation ───────────────────────────────────────────────
    results: dict = {}

    for repr_key in ['plain', 'udl', 'rtd', 'coverage', 'mdn']:
        print(f"\n{'─'*72}")
        print(f"  [{repr_key.upper()}]  {REPR_LABELS[repr_key].strip()}")
        builder = REPR_BUILDERS[repr_key]
        t0 = time.time()
        try:
            if repr_key == 'plain':
                X_panel = builder(df)
            else:
                X_panel = builder(df, train_mask_arr)
            print(f"  Panel shape: {X_panel.shape}  (built in {time.time()-t0:.1f}s)")
            t1 = time.time()
            sim, pnl_out, diag = run_repr_pipeline(
                X_panel, train_mask_arr, df, test_mask, pnl_v18s)
            elapsed = time.time() - t1
            results[repr_key] = {
                'sim': sim, 'pnl': pnl_out, 'diag': diag,
                'panel_shape': list(X_panel.shape), 'run_time_s': round(elapsed, 1),
            }
            print(f"  Pipeline done in {elapsed:.1f}s")
            print(f"    d={diag['panel_d']}  "
                  f"LayerA={diag['layer_A_days']}d  "
                  f"LayerB={diag['layer_B_days']}d  "
                  f"Latched={diag['latched_days']}d  "
                  f"A-thresh={diag['a_threshold_calib']:.4f}  "
                  f"e*={diag['e_star']:.2f}  sigma_n={diag['sigma_n']:.3f}")
            print(f"    Sharpe {sim['sharpe']:+.4f}  "
                  f"MaxDD {sim['max_dd']:+.4f}  "
                  f"CAGR {100*sim['cagr']:+.2f}%  "
                  f"Active {int(sim['active_days'])}d")
        except Exception as e_run:
            import traceback
            print(f"  ERROR: {e_run}")
            traceback.print_exc()
            results[repr_key] = {'sim': None, 'error': str(e_run)}

    # ── comparison table ──────────────────────────────────────────────────────
    print("\n" + "=" * 96)
    print("  v23 TENSOR REPRESENTATION COMPARISON  (test period, K=1 gross)")
    print("=" * 96)
    print(f"  {'Repr':<26}  {'d':>4}  {'Sharpe':>8}  {'MaxDD':>8}  "
          f"{'CAGR%':>8}  {'Active':>7}  {'A-days':>7}  {'B-days':>7}  {'A-thr':>7}")
    print("  " + "-" * 90)

    base_sharpe = sim_base['sharpe']
    best_sharpe = base_sharpe
    best_key    = 'baseline'

    act_base = int(pnl_v18s[test_mask].abs().gt(1e-9).sum())
    print(f"  {'v18_smooth (no engine)':<26}  {'2':>4}  "
          f"{sim_base['sharpe']:+8.4f}  {sim_base['max_dd']:+8.4f}  "
          f"{100*sim_base['cagr']:+7.2f}%  {act_base:6d}d  {'--':>7}  {'--':>7}")

    for rk in ['plain', 'udl', 'rtd', 'coverage', 'mdn']:
        res = results.get(rk, {})
        if res.get('sim') is None:
            err = res.get('error', 'unknown')[:50]
            print(f"  {REPR_LABELS[rk]:<26}  {'?':>4}  {'ERROR':>8}  {err}")
            continue
        s  = res['sim']
        d  = res['diag']['panel_d']
        ad = res['diag']['layer_A_days']
        bd = res['diag']['layer_B_days']
        act = int(res['pnl'][test_mask].abs().gt(1e-9).sum())
        marker = ' <--' if s['sharpe'] > best_sharpe else ''
        if s['sharpe'] > best_sharpe:
            best_sharpe, best_key = s['sharpe'], rk
        # Confidence vs baseline
        delta = s['sharpe'] - base_sharpe
        delta_str = f"({delta:+.3f})" if abs(delta) > 0.001 else ""
        print(f"  {REPR_LABELS[rk]:<26}  {d:>4}  "
              f"{s['sharpe']:+8.4f}  {s['max_dd']:+8.4f}  "
              f"{100*s['cagr']:+7.2f}%  {act:6d}d  {ad:6d}d  {bd:6d}d  "
              f"{res['diag']['a_threshold_calib']:7.4f}  "
              f"{delta_str}{marker}")

    print()
    print(f"  Best representation: {best_key}  (Sharpe {best_sharpe:+.4f}  "
          f"vs baseline {base_sharpe:+.4f})")

    # ── K-sweep on winner ─────────────────────────────────────────────────────
    if best_key not in ('baseline',) and results.get(best_key, {}).get('sim'):
        best_pnl = results[best_key]['pnl']
        print(f"\n  K-sweep on [{best_key}]:")
        print(f"  {'K':>5}  {'mode':<10}  {'Sharpe':>8}  {'CAGR%':>8}  "
              f"{'Final $':>12}  {'PnL $':>12}  {'MaxDD%':>8}")
        print("  " + "-" * 78)
        for K in (1, 2, 3, 5, 10):
            for mode, bps in (('gross', 0.0), ('net 5bp', 5.0)):
                m = equity_at_K(best_pnl[test_mask].fillna(0.0),
                                K=float(K), tcost_bps=bps, init=1200.0)
                print(f"  {K:5d}  {mode:<10}  {m['sh']:+8.3f}  "
                      f"{100*m['cagr']:+7.2f}%  "
                      f"${m['final']:10,.2f}  ${m['pnl']:+10,.2f}  "
                      f"{100*m['max_dd']:+7.2f}%")
        bK = find_best_K(best_pnl[test_mask].fillna(0.0),
                         tcost_bps=5.0, init=1200.0, max_dd_limit=0.40)
        if bK:
            print(f"\n  Best K net 5bp (MaxDD<=40%): K={bK['K']:.2f}  "
                  f"Final ${bK['final']:,.2f}  Sharpe {bK['sh']:+.3f}  "
                  f"CAGR {100*bK['cagr']:.1f}%")

    # ── also K-sweep on plain for direct comparison with v22 ─────────────────
    if 'plain' in results and results['plain'].get('sim'):
        plain_pnl = results['plain']['pnl']
        bK_plain = find_best_K(plain_pnl[test_mask].fillna(0.0),
                               tcost_bps=5.0, init=1200.0, max_dd_limit=0.40)
        if bK_plain:
            print(f"\n  [plain] Best K net 5bp: K={bK_plain['K']:.2f}  "
                  f"Final ${bK_plain['final']:,.2f}  Sharpe {bK_plain['sh']:+.3f}  "
                  f"(v22 reference: K=9.25 -> $2,593  Sharpe +0.644)")

    # ── save JSON ─────────────────────────────────────────────────────────────
    print("\n  Saving results ...")

    def _to_serialisable(v):
        if isinstance(v, (np.integer, np.floating)):
            return float(v)
        if isinstance(v, np.ndarray):
            return v.tolist()
        return v

    out = {
        'protocol': 'v23 tensor representation comparison',
        'baseline': {k: _to_serialisable(v)
                     for k, v in sim_base.items()},
        'variants': {
            rk: {
                'panel_shape': res.get('panel_shape'),
                'diag':        res.get('diag'),
                'sim':         {k: _to_serialisable(v)
                                for k, v in (res.get('sim') or {}).items()},
                'run_time_s':  res.get('run_time_s'),
                'error':       res.get('error'),
            }
            for rk, res in results.items()
        },
        'best_repr':       best_key,
        'best_sharpe':     float(best_sharpe),
        'baseline_sharpe': float(base_sharpe),
    }
    jp = out_dir / 'crypto_bsdt_v23_results.json'
    jp.write_text(json.dumps(out, indent=2, default=str))
    print(f"  Saved -> {jp}")
    print("=" * 96)


if __name__ == "__main__":
    main()
