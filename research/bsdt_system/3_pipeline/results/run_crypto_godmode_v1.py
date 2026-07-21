"""
Crypto Godmode v1 — Full Exploitation of the Canonical Engine
=============================================================

Implements the Godmode trading framework from /Godmode document:
  §2  BSDT origin → choose (S, G, F_base, θ) so S=0 is the trading thesis
  thm:z2  long/short symmetry → cos θ ≤ 0 always in aligned geometry
  §10  predictive scalars cockpit: cos θ, ‖g_X‖, E, γ, ρ_eff
  App. N  θ-annealing (v_anneal)
  App. P  multi-engine passivity by construction (v_multi)

Root bug fixed:
  OLD: w_star = zeros(3)  → F_base = -κw → pushes flat → fights momentum
  NEW: w_star_t = tanh(mom) × W_TARGET    (per-bar, in weight space)
       b_t      = A_FACTORS @ w_star_t    (derived, so E=0 AT the momentum target)

Strategies (6 new + 3 baselines):
  v_god_A1   W_TARGET=0.30, κ=0.15, b_t=A·w_star, conviction=-cos_θ
  v_god_A2   W_TARGET=0.40, κ=0.15, same
  v_god_A3   W_TARGET=0.30, κ=0.10, same
  v_god_B    W_TARGET=0.30, κ=0.15, b_t has separate rotation signal
  v_multi    App. P two-engine: trend engine A + rotation engine B, forces summed
  v_anneal   W_TARGET=0.30, κ=0.15, intraday θ schedule (App. N)
  v4_raw     old baseline (re-run for clean comparison)
  v60        old champion (re-run)
  long_only  equal-weight benchmark
"""
from __future__ import annotations
import os, sys, json, time, warnings
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")
from pathlib import Path
import numpy as np
import pandas as pd
warnings.filterwarnings('ignore')

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, r'C:\amttp\research\adaptive-friction')

from collapse_geometry.canonical import (
    TradingDomain, verification_checklist, verify_gradient_fd,
)
from run_crypto_canonical_v4 import (
    A_FACTORS, N_STATE, K_FACTOR,
    EPSILON, DT, THETA_PCTILE,
    LW_SHRINK_FLOOR,
    ledoit_wolf_cov, rescale_to_correlation,
    _stats, _net_ret, print_yoy_table,
)
from run_crypto_canonical_v58_v60 import (
    print_dollar_simulation,
    run_canonical_sweep as _run_v4_sweep,   # for baseline v4_raw + v60
    overlay_v60,
)
from run_crypto_pairs_v34_full_combined import (
    OUT_DIR, TEST_START, TRAIN_START,
    build_1h_df,
)

OUT_DIR_ = Path(OUT_DIR)
ANN_1H   = 252.0 * 24
BPD      = 24

# ═══════════════════════════════════════════════════════════════════════════
#  GODMODE HYPER-PARAMETERS
# ═══════════════════════════════════════════════════════════════════════════

KAPPA_A      = 0.15     # alpha-tracking strength (stronger than old 0.05)
KAPPA_A3     = 0.10     # gentler variant for v_god_A3
KAPPA_B_ROT  = 0.10     # rotation engine B in v_multi

W_TARGET_A1  = 0.30     # per-asset momentum target amplitude (v_god_A1, A3, B, multi, anneal)
W_TARGET_A2  = 0.40     # higher exposure variant (v_god_A2)
W_BOX        = 0.50     # hard per-asset clip (ODE breathing room above target)

TARGET_ROT   = 0.20     # rotation-only amplitude for v_god_B rotation rows
MOM_WIN_DIR  = 7 * BPD  # 7-day directional momentum window
MOM_WIN_ROT  = 3 * BPD  # 3-day rotation momentum window
TANH_S       = 2.0      # tanh steepness (identical to old engine)

CONV_MIN     = 0.20     # minimum conviction floor (prevents zero sizing on neutral bars)
CONV_MAX     = 1.00     # conviction ceiling

# v_anneal intraday θ schedule (App. N)
ANNEAL_AMP   = 0.50     # θ(t) = θ_base × (1 + AMP × cos(2π(hour-12)/24))
ANNEAL_PEAK  = 12       # UTC hour at which θ is LOWEST (most exploitative)

# Multi-engine (App. P)
THETA_B_SCALE = 0.50    # θ_B = THETA_B_SCALE × θ_A  (rotation engine tighter)


# ═══════════════════════════════════════════════════════════════════════════
#  SIGNAL BUILDERS
# ═══════════════════════════════════════════════════════════════════════════

def _tanh_signal(r: np.ndarray, win: int, tanh_s: float = TANH_S) -> np.ndarray:
    """Smooth tanh-momentum signal ∈ (-1, +1).

    m(t) = Σ_{s=t-win}^{t-1} r_s     (shifted-1 to avoid lookahead)
    std  = rolling std of m over 2*win
    out  = tanh(tanh_s × m / std)
    """
    sr    = pd.Series(r)
    m     = sr.rolling(win, min_periods=BPD).sum().shift(1).fillna(0.0)
    m_std = m.rolling(min(2 * win, len(r)), min_periods=win // 2).std()
    m_std = m_std.replace(0, np.nan).bfill().fillna(1.0).clip(lower=1e-9)
    return np.tanh(tanh_s * m / m_std).values


def build_w_star(df: pd.DataFrame, W_TARGET: float = W_TARGET_A1) -> np.ndarray:
    """Per-bar momentum target IN WEIGHT SPACE  (T × 3).

    Instead of purely naive return momentum, uses the true Structural Eigenvector
    Loading (Contribution 3) patched in to get geometric direction.
    """
    import sys
    if r"C:\amttp" not in sys.path:
        sys.path.insert(0, r"C:\amttp")
    from crypto_eigen_direction_patch import compute_crypto_eigen_direction
    
    # Needs to be sure these columns are generated for the patch
    feats_strat = ['ret_eth_z','vol_eth_z','btc_dom_z','cross_disp_z']
    
    # 1. Dynamically build Z-scores missing from the raw God Mode dataframe
    if not all(c in df.columns for c in feats_strat):
        df_temp = pd.DataFrame(index=df.index)
        df_temp['ret_eth'] = df['ret_eth'].fillna(0)
        df_temp['ret_eth_z'] = (df_temp['ret_eth'] - df_temp['ret_eth'].rolling(60).mean()) / (df_temp['ret_eth'].rolling(60).std() + 1e-8)
        
        vol_eth = df_temp['ret_eth'].rolling(24).std()
        df_temp['vol_eth_z'] = (vol_eth - vol_eth.rolling(60).mean()) / (vol_eth.rolling(60).std() + 1e-8)
        
        df_temp['btc_dom_z'] = (df['btc_dom'] - df['btc_dom'].rolling(60).mean()) / (df['btc_dom'].rolling(60).std() + 1e-8)
        
        disp = df['spread_ret_eb'].abs()
        df_temp['cross_disp_z'] = (disp - disp.rolling(60).mean()) / (disp.rolling(60).std() + 1e-8)
        
        for c in feats_strat:
            df[c] = df_temp[c].fillna(0)

    # 2. Extract Structural Loading
    evec_dir = compute_crypto_eigen_direction(df, feats_strat, window=60, ret_idx=0).fillna(0).values
    
    # 3. Maintain volatility limits with a smoothed geometry target
    s_eth = pd.Series(np.sign(evec_dir)).ewm(span=MOM_WIN_DIR).mean().values
    s_btc = s_eth  # Use the same dominant macro-structural direction
    s_sol = s_eth

    return np.column_stack([s_btc, s_eth, s_sol]) * W_TARGET   # (T, 3)


def build_b_aligned(w_star_arr: np.ndarray) -> np.ndarray:
    """Derive b_t = A_FACTORS @ w_star_t   ∀ t.  (T × 5)

    This is the ONLY correct way to set b_t so that E(w_star_t) = 0 ∀ t.
    S(w) = Aw - b_t;  at w=w_star_t:  S = A·w_star_t - A·w_star_t = 0.
    """
    return w_star_arr @ A_FACTORS.T   # (T, K_FACTOR)


def build_b_hybrid(df: pd.DataFrame, w_star_arr: np.ndarray) -> np.ndarray:
    """Hybrid b_t for v_god_B:  directional rows from A[:3]·w_star_dir,
    rotation rows from independent tanh-spread signals.

    Rows 0-2: b_t[0:3] = (A[:3] @ w_star_t).  E_dir = 0 at w=w_star_t.
    Rows 3-4: b_t[3:5] = [tanh(mom_eth-btc), tanh(mom_eth-sol)] × TARGET_ROT
              (independent 3d rotation signal, as in the old engine).
    """
    T   = len(df)
    b_t = np.zeros((T, K_FACTOR), dtype=float)

    # Rows 0-2: aligned with momentum target
    b_full     = build_b_aligned(w_star_arr)
    b_t[:, :3] = b_full[:, :3]

    # Rows 3-4: independent rotation signals
    r_btc  = df['ret_btc'].fillna(0.0).values
    r_eth  = df['ret_eth'].fillna(0.0).values
    r_sol  = df['ret_sol'].fillna(0.0).values if 'ret_sol' in df.columns else r_eth
    b_t[:, 3] = _tanh_signal(r_eth - r_btc, MOM_WIN_ROT) * TARGET_ROT
    b_t[:, 4] = _tanh_signal(r_eth - r_sol, MOM_WIN_ROT) * TARGET_ROT

    return b_t


def build_rotation_b_only(df: pd.DataFrame) -> np.ndarray:
    """Rotation-only factor targets for multi-engine Engine B.  (T × 2)

    Uses only the 2 rotation rows (f4=eth-btc, f5=eth-sol).
    b_rot_t = [tanh(mom_spread_eb), tanh(mom_spread_es)] × TARGET_ROT
    """
    r_btc = df['ret_btc'].fillna(0.0).values
    r_eth = df['ret_eth'].fillna(0.0).values
    r_sol = df['ret_sol'].fillna(0.0).values if 'ret_sol' in df.columns else r_eth
    b_eb  = _tanh_signal(r_eth - r_btc, MOM_WIN_ROT) * TARGET_ROT
    b_es  = _tanh_signal(r_eth - r_sol, MOM_WIN_ROT) * TARGET_ROT
    return np.column_stack([b_eb, b_es])   # (T, 2)


# ═══════════════════════════════════════════════════════════════════════════
#  CALIBRATION
# ═══════════════════════════════════════════════════════════════════════════

def calibrate(df: pd.DataFrame,
              train_mask: np.ndarray,
              w_star_arr: np.ndarray,
              b_arr: np.ndarray,
              kappa: float = KAPPA_A,
              label: str = '') -> tuple[np.ndarray, float, dict]:
    """Shared calibration: Ledoit-Wolf Σ_f, θ = P50 of training E.

    Uses the ALIGNED geometry (b_t = A·w_star_t) so θ is calibrated to the
    actual energy distribution, not to an artificial zero-target.
    """
    from run_crypto_canonical_v4 import build_factor_returns
    factor_R   = build_factor_returns(df)
    Sigma_raw, lw_delta = ledoit_wolf_cov(factor_R[train_mask])
    Sigma_f    = rescale_to_correlation(Sigma_raw)
    G_cal      = np.linalg.inv(Sigma_f)

    # θ: P50 of E_train computed at w=0 (initial state), using per-bar b_t
    b_train    = b_arr[train_mask]
    E_train    = np.einsum('ti,ij,tj->t', b_train, G_cal, b_train)
    theta_cal  = max(float(np.percentile(E_train, THETA_PCTILE)), 1e-3)

    if label:
        print(f"  [{label}] LW δ={lw_delta:.3f}  θ(P{THETA_PCTILE})={theta_cal:.4f}")

    # §10 verification at a representative training point
    w_rep = np.zeros(N_STATE)
    b_rep = b_arr[np.where(train_mask)[0][-1]]
    sys0  = TradingDomain(A=A_FACTORS, b=b_rep, Sigma=Sigma_f,
                          kappa=kappa, w_star=w_star_arr[np.where(train_mask)[0][-1]],
                          theta=theta_cal, epsilon=EPSILON).build()
    chk   = verification_checklist(sys0, np.array([0.10, 0.15, 0.05]))
    print(chk.summary())
    if not chk.all_passed:
        raise RuntimeError(f"§10 checklist failed for {label}")
    fd    = verify_gradient_fd(sys0, np.array([0.10, 0.15, 0.05]), h=1e-6)
    print(f"  [{label}] FD gradient: max_abs={fd['max_abs_error']:.2e}  passed={fd['passed']}")

    diag = {'lw_delta': lw_delta, 'theta': theta_cal,
            'checklist': chk.all_passed, 'fd_max_abs': fd['max_abs_error']}
    return Sigma_f, theta_cal, diag


# ═══════════════════════════════════════════════════════════════════════════
#  PER-BAR PREDICTIVE SCALARS (shared helper)
# ═══════════════════════════════════════════════════════════════════════════

def _predictive_scalars(sys_t, w: np.ndarray) -> dict:
    """Compute the §10 five-scalar dashboard for one bar."""
    gw       = sys_t.gradient(w)
    Fb       = np.asarray(sys_t.F_base(w), dtype=float)
    E_t      = sys_t.energy(w)
    gma      = sys_t.gain(w)
    dEdt     = sys_t.dE_dt(w)
    rhs      = sys_t.rhs(w)

    Fb_n     = float(np.linalg.norm(Fb))
    gw_n     = float(np.linalg.norm(gw))
    denom    = Fb_n * gw_n
    cos_th   = float(Fb @ gw) / denom if denom > 1e-12 else 0.0
    v_E      = -dEdt
    rho_eff  = v_E / max(E_t, 1e-9)

    return dict(E=E_t, gamma=gma, dE_dt=dEdt, rhs=rhs, gw=gw,
                cos_theta=cos_th, mfls=gw_n, v_E=v_E, rho_eff=rho_eff,
                rhs_norm=float(np.linalg.norm(rhs)))


# ═══════════════════════════════════════════════════════════════════════════
#  SINGLE-ENGINE SWEEP — aligned geometry
# ═══════════════════════════════════════════════════════════════════════════

def run_godmode_sweep(df: pd.DataFrame,
                      train_mask: np.ndarray,
                      test_mask: np.ndarray,
                      w_star_arr: np.ndarray,
                      b_arr: np.ndarray,
                      Sigma_f: np.ndarray,
                      theta_base: float,
                      kappa: float = KAPPA_A,
                      W_box: float = W_BOX,
                      anneal: bool = False,
                      label: str = '') -> pd.DataFrame:
    """Per-bar ODE sweep for all aligned single-engine variants.

    Key differences from old run_canonical_sweep:
    1. w_star_t updates per bar (F_base tracks momentum target, not zero)
    2. b_t = A·w_star_t (E=0 at target by construction)
    3. No overlay: conviction from clip(-cos_theta_lag, CONV_MIN, CONV_MAX)
    4. θ can vary per-bar (v_anneal) via anneal=True
    5. W_box replaces old W_MAX

    Regime alarms are LOGGED but NOT used as filters in v1:
      stop_flag  = γ > 0.90   (far from target, strong caution)
      stale_flag = ρ_eff < 0.1 × ρ_typ_train
      drift_flag = cos_theta > 0  (misaligned — rare in aligned geometry)
    """
    T = len(df)
    R = np.column_stack([
        df['ret_btc'].fillna(0.0).values,
        df['ret_eth'].fillna(0.0).values,
        df['ret_sol'].fillna(0.0).values if 'ret_sol' in df.columns
            else df['ret_eth'].fillna(0.0).values,
    ])

    # Calibrate training ρ_typ for stale alarm
    rho_train = []
    for t in np.where(train_mask)[0][::50]:   # subsample for speed
        sys_t = TradingDomain(A=A_FACTORS, b=b_arr[t], Sigma=Sigma_f,
                              kappa=kappa, w_star=w_star_arr[t],
                              theta=theta_base, epsilon=EPSILON).build()
        sc = _predictive_scalars(sys_t, np.zeros(N_STATE))
        if sc['rho_eff'] > 0:
            rho_train.append(sc['rho_eff'])
    rho_typ = float(np.median(rho_train)) if rho_train else 1.0

    # Intraday anneal: hour array
    hours = df.index.hour if anneal else None

    # Log allocation
    keys = ['E', 'gamma', 'dE_dt', 'cos_theta', 'mfls', 'v_E', 'rho_eff',
            'rhs_norm', 'w_btc', 'w_eth', 'w_sol', 'pnl', 'pnl_long_only',
            'stop_flag', 'stale_flag', 'drift_flag', 'conviction', 'theta_t']
    log  = {k: np.zeros(T) for k in keys}

    w            = np.zeros(N_STATE, dtype=float)
    cos_th_prev  = 0.0      # lagged cos_theta (causal)
    t0           = time.time()

    for t in range(T):
        # Per-bar θ: flat or annealed
        if anneal:
            hr = int(hours[t])
            theta_t = theta_base * (1.0 + ANNEAL_AMP * np.cos(
                2.0 * np.pi * (hr - ANNEAL_PEAK) / 24.0))
        else:
            theta_t = theta_base

        sys_t = TradingDomain(
            A=A_FACTORS, b=b_arr[t], Sigma=Sigma_f,
            kappa=kappa, w_star=w_star_arr[t],
            theta=theta_t, epsilon=EPSILON,
        ).build()

        sc = _predictive_scalars(sys_t, w)

        # Conviction: clip(-cos_theta[t-1], CONV_MIN, CONV_MAX)
        # Negative cos_theta means F_base and g_X are aligned (good).
        # cos_theta ≤ 0 always holds in the aligned geometry.
        conviction = float(np.clip(-cos_th_prev, CONV_MIN, CONV_MAX))

        # ODE step with conviction scaling
        w_new = w + DT * sc['rhs'] * conviction
        w_new = np.clip(w_new, -W_box, W_box)

        # Regime alarm flags (informational)
        stop_flag  = 1.0 if sc['gamma'] > 0.90 else 0.0
        stale_flag = 1.0 if (sc['rho_eff'] > 0 and sc['rho_eff'] < 0.1 * rho_typ) else 0.0
        drift_flag = 1.0 if sc['cos_theta'] > 0.0 else 0.0

        log['E'][t]          = sc['E']
        log['gamma'][t]      = sc['gamma']
        log['dE_dt'][t]      = sc['dE_dt']
        log['cos_theta'][t]  = sc['cos_theta']
        log['mfls'][t]       = sc['mfls']
        log['v_E'][t]        = sc['v_E']
        log['rho_eff'][t]    = sc['rho_eff']
        log['rhs_norm'][t]   = sc['rhs_norm']
        log['w_btc'][t]      = w_new[0]
        log['w_eth'][t]      = w_new[1]
        log['w_sol'][t]      = w_new[2]
        log['pnl'][t]        = float(w_new @ R[t])
        log['pnl_long_only'][t] = float(R[t].mean())
        log['stop_flag'][t]  = stop_flag
        log['stale_flag'][t] = stale_flag
        log['drift_flag'][t] = drift_flag
        log['conviction'][t] = conviction
        log['theta_t'][t]    = theta_t

        w           = w_new
        cos_th_prev = sc['cos_theta']   # update lag

        if t > 0 and (t % 5000) == 0:
            elapsed = time.time() - t0
            print(f"    [{label}] {t:>6}/{T}  ({elapsed:>5.1f}s)")

    print(f"  [{label}] sweep done: {T:,} bars  {time.time()-t0:.1f}s")
    return pd.DataFrame(log, index=df.index)


# ═══════════════════════════════════════════════════════════════════════════
#  MULTI-ENGINE SWEEP  (App. P — port-Hamiltonian)
# ═══════════════════════════════════════════════════════════════════════════

def run_multi_sweep(df: pd.DataFrame,
                    train_mask: np.ndarray,
                    test_mask: np.ndarray,
                    w_star_arr: np.ndarray,
                    b_aligned_arr: np.ndarray,
                    b_rot_arr: np.ndarray,
                    Sigma_f: np.ndarray,
                    theta_A: float) -> pd.DataFrame:
    """App. P: two engines on same state w, forces summed.

    Engine A (trend):    A_FACTORS (5×3), b_t = A·w_star_t, θ_A, κ_A=0.15
    Engine B (rotation): A_ROT = A_FACTORS[3:] (2×3), b_t = b_rot_t, θ_B=0.5·θ_A, κ_B=0.10
                         w_star_B = zeros (rotation target is zero net-long/short)

    Aggregate RHS: ẇ = rhs_A(w) + rhs_B(w)
    Passive by Theorem thm:multi (Appendix P): Ḣ ≤ ⟨∇H, ΣF_base_i⟩  (App. P).
    """
    T     = len(df)
    R     = np.column_stack([
        df['ret_btc'].fillna(0.0).values,
        df['ret_eth'].fillna(0.0).values,
        df['ret_sol'].fillna(0.0).values if 'ret_sol' in df.columns
            else df['ret_eth'].fillna(0.0).values,
    ])
    A_ROT     = A_FACTORS[3:]                    # (2, 3)
    theta_B   = THETA_B_SCALE * theta_A
    w_star_B  = np.zeros(N_STATE, dtype=float)

    # Rotation-factor covariance (2×2, Ledoit-Wolf from training)
    from run_crypto_canonical_v4 import build_factor_returns
    factor_R_full = build_factor_returns(df)      # (T, 5)
    factor_R_rot  = factor_R_full[:, 3:]          # (T, 2) rotation factors only
    Sigma_rot_raw, _ = ledoit_wolf_cov(factor_R_rot[train_mask])
    # Rescale to correlation
    d    = np.sqrt(np.maximum(np.diag(Sigma_rot_raw), 1e-30))
    dinv = np.diag(1.0 / d)
    Sigma_rot = dinv @ Sigma_rot_raw @ dinv
    Sigma_rot = 0.5 * (Sigma_rot + Sigma_rot.T)

    keys = ['E_A', 'E_B', 'gamma_A', 'gamma_B', 'cos_theta_A', 'rho_eff_A',
            'w_btc', 'w_eth', 'w_sol', 'pnl', 'pnl_long_only', 'conviction']
    log  = {k: np.zeros(T) for k in keys}

    w           = np.zeros(N_STATE, dtype=float)
    cos_th_prev = 0.0
    t0          = time.time()

    for t in range(T):
        # Engine A
        sys_A = TradingDomain(
            A=A_FACTORS, b=b_aligned_arr[t], Sigma=Sigma_f,
            kappa=KAPPA_A, w_star=w_star_arr[t],
            theta=theta_A, epsilon=EPSILON,
        ).build()

        # Engine B (rotation-only, 2-factor sub-system)
        sys_B = TradingDomain(
            A=A_ROT, b=b_rot_arr[t], Sigma=Sigma_rot,
            kappa=KAPPA_B_ROT, w_star=w_star_B,
            theta=theta_B, epsilon=EPSILON,
        ).build()

        sc_A = _predictive_scalars(sys_A, w)

        # Engine B rhs in R^3 (gradient = 2·A_ROT^T·G_rot·S_B → lives in R^3)
        rhs_B = sys_B.rhs(w)    # A_ROT is (2,3), so gradient ∈ R^3 ✓

        # Aggregate force (App. P: just sum)
        rhs_total = sc_A['rhs'] + rhs_B

        conviction = float(np.clip(-cos_th_prev, CONV_MIN, CONV_MAX))
        w_new      = np.clip(w + DT * rhs_total * conviction, -W_BOX, W_BOX)

        log['E_A'][t]        = sc_A['E']
        log['E_B'][t]        = sys_B.energy(w)
        log['gamma_A'][t]    = sc_A['gamma']
        log['gamma_B'][t]    = sys_B.gain(w)
        log['cos_theta_A'][t]= sc_A['cos_theta']
        log['rho_eff_A'][t]  = sc_A['rho_eff']
        log['w_btc'][t]      = w_new[0]
        log['w_eth'][t]      = w_new[1]
        log['w_sol'][t]      = w_new[2]
        log['pnl'][t]        = float(w_new @ R[t])
        log['pnl_long_only'][t] = float(R[t].mean())
        log['conviction'][t]  = conviction

        w           = w_new
        cos_th_prev = sc_A['cos_theta']

        if t > 0 and (t % 5000) == 0:
            print(f"    [v_multi] {t:>6}/{T}  ({time.time()-t0:>5.1f}s)")

    print(f"  [v_multi] sweep done: {T:,} bars  {time.time()-t0:.1f}s")
    return pd.DataFrame(log, index=df.index)


# ═══════════════════════════════════════════════════════════════════════════
#  DIAGNOSTICS PRINTER
# ═══════════════════════════════════════════════════════════════════════════

def print_alignment_check(logs: dict, test_mask: np.ndarray):
    """Prints % bars where cos_theta ≤ 0 per variant.

    In the aligned geometry, cos_theta ≤ 0 should be ≥ 90% of bars.
    This is the machine-checkable proof that F_base and the manifold
    gradient are aligned (Theorem thm:z2 condition).
    """
    print(f"\n  {'Alignment Check — % bars with cos θ ≤ 0   (target ≥ 90%)'}")
    print(f"  {'─'*55}")
    for name, lg in logs.items():
        if 'cos_theta' in lg.columns:
            s   = lg.iloc[test_mask]
            pct = 100.0 * (s['cos_theta'] <= 0.0).mean()
            flag = '' if pct >= 90.0 else '  ← MISALIGNED'
            print(f"  {name:<14}  {pct:>6.1f}%{flag}")


def print_strategy_table(strategies: dict, mask: np.ndarray):
    print(f"\n  {'Strategy':<18}  {'Sharpe':>8}  {'MaxDD':>8}  {'CAGR':>9}  "
          f"{'Active%':>8}  {'$100→':>9}")
    print(f"  {'─'*75}")
    for name, pnl in strategies.items():
        p  = pnl.iloc[mask]
        st = _stats(p)
        ar = float((p.abs() > 1e-12).mean()) * 100
        print(f"  {name:<18}  {st['sharpe']:>+8.3f}  {100*st['max_dd']:>+7.1f}%  "
              f"{100*st['cagr']:>+8.1f}%  {ar:>7.1f}%  ${st['final']:>7.2f}")


# ═══════════════════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════════════════

def main():
    OUT_DIR_.mkdir(parents=True, exist_ok=True)
    SEP = "=" * 100
    print(SEP)
    print("  CRYPTO GODMODE v1 — Full Canonical Exploitation")
    print("  Aligned geometry: w_star_t = momentum target, b_t = A·w_star_t")
    print("  Strategies: v_god_A1/A2/A3, v_god_B, v_multi, v_anneal + 3 baselines")
    print(SEP)

    # ── [1] Data ──────────────────────────────────────────────────────────
    print("\n[1] Fetching Binance 1h data ...")
    df, has_sol = build_1h_df(start='2021-01-01', end='2026-05-01')
    test_mask  = np.asarray(df.index >= TEST_START)
    train_mask = np.asarray((df.index >= TRAIN_START) & (df.index < TEST_START))
    T          = len(df)
    print(f"  Bars: {T:,}   Train: {train_mask.sum():,}   Test: {test_mask.sum():,}   SOL: {has_sol}")

    # ── [2] Signal arrays (built once, reused by all variants) ───────────
    print("\n[2] Building momentum signals ...")
    w_star_A1 = build_w_star(df, W_TARGET=W_TARGET_A1)   # (T, 3)
    w_star_A2 = build_w_star(df, W_TARGET=W_TARGET_A2)
    b_aligned_A1 = build_b_aligned(w_star_A1)             # (T, 5)
    b_aligned_A2 = build_b_aligned(w_star_A2)
    b_hybrid     = build_b_hybrid(df, w_star_A1)           # (T, 5) v_god_B
    b_rot_only   = build_rotation_b_only(df)               # (T, 2) v_multi Engine B
    print(f"  w_star range A1: [{w_star_A1.min():.3f}, {w_star_A1.max():.3f}]")
    print(f"  w_star range A2: [{w_star_A2.min():.3f}, {w_star_A2.max():.3f}]")

    # ── [3] Calibration (shared per W_TARGET) ────────────────────────────
    print("\n[3] Calibrating Σ_f and θ ...")
    Sigma_A1, theta_A1, diag_A1 = calibrate(
        df, train_mask, w_star_A1, b_aligned_A1, kappa=KAPPA_A, label='A1')
    # A2 needs its own θ (different b_t scale)
    Sigma_A2, theta_A2, diag_A2 = calibrate(
        df, train_mask, w_star_A2, b_aligned_A2, kappa=KAPPA_A, label='A2')
    # A3 uses same Sigma as A1 but different kappa (doesn't affect Sigma)
    _, theta_A3, diag_A3 = calibrate(
        df, train_mask, w_star_A1, b_aligned_A1, kappa=KAPPA_A3, label='A3')

    # ── [4] Sweeps ────────────────────────────────────────────────────────
    print("\n[4] Running godmode sweeps ...")

    print("\n  -- v_god_A1  (W_TARGET=0.30, κ=0.15, b=A·w*) --")
    log_A1 = run_godmode_sweep(df, train_mask, test_mask,
                                w_star_A1, b_aligned_A1, Sigma_A1, theta_A1,
                                kappa=KAPPA_A, label='A1')

    print("\n  -- v_god_A2  (W_TARGET=0.40, κ=0.15, b=A·w*) --")
    log_A2 = run_godmode_sweep(df, train_mask, test_mask,
                                w_star_A2, b_aligned_A2, Sigma_A2, theta_A2,
                                kappa=KAPPA_A, label='A2')

    print("\n  -- v_god_A3  (W_TARGET=0.30, κ=0.10, b=A·w*) --")
    log_A3 = run_godmode_sweep(df, train_mask, test_mask,
                                w_star_A1, b_aligned_A1, Sigma_A1, theta_A3,
                                kappa=KAPPA_A3, label='A3')

    print("\n  -- v_god_B   (W_TARGET=0.30, κ=0.15, hybrid b_t) --")
    log_B = run_godmode_sweep(df, train_mask, test_mask,
                               w_star_A1, b_hybrid, Sigma_A1, theta_A1,
                               kappa=KAPPA_A, label='B')

    print("\n  -- v_anneal  (W_TARGET=0.30, κ=0.15, θ-annealed) --")
    log_ann = run_godmode_sweep(df, train_mask, test_mask,
                                 w_star_A1, b_aligned_A1, Sigma_A1, theta_A1,
                                 kappa=KAPPA_A, anneal=True, label='anneal')

    print("\n  -- v_multi   (App. P two-engine: trend + rotation) --")
    log_multi = run_multi_sweep(df, train_mask, test_mask,
                                 w_star_A1, b_aligned_A1, b_rot_only,
                                 Sigma_A1, theta_A1)

    # ── [5] Baselines: v4_raw and v60 ───────────────────────────────────
    print("\n[5] Running baselines (v4_raw, v60, long_only) ...")
    log_base, _ = _run_v4_sweep(df, train_mask, test_mask)
    pnl_v4_raw  = log_base['pnl_raw']
    pnl_v60     = overlay_v60(log_base, train_mask)
    pnl_long    = log_base['pnl_long_only']

    # ── [6] Assemble strategies dict ────────────────────────────────────
    strategies = {
        'v_god_A1':   log_A1['pnl'],
        'v_god_A2':   log_A2['pnl'],
        'v_god_A3':   log_A3['pnl'],
        'v_god_B':    log_B['pnl'],
        'v_anneal':   log_ann['pnl'],
        'v_multi':    log_multi['pnl'],
        'v4_raw':     pnl_v4_raw,
        'v60':        pnl_v60,
        'long_only':  pnl_long,
    }

    logs_with_cos = {
        'v_god_A1': log_A1,
        'v_god_A2': log_A2,
        'v_god_A3': log_A3,
        'v_god_B':  log_B,
        'v_anneal': log_ann,
        # v_multi uses cos_theta_A column with different name
    }

    # ── [7] Reporting ────────────────────────────────────────────────────
    print(f"\n{'═'*100}")
    print("  GODMODE PERFORMANCE  (test 2023→2026, 1× gross)")
    print(f"{'═'*100}")
    print_strategy_table(strategies, test_mask)

    # ── Alignment check (cos θ ≤ 0 % per variant) ──
    print_alignment_check(logs_with_cos, test_mask)

    # ── Predictive quartet diagnostics per godmode variant ──
    print(f"\n  {'─'*70}")
    print("  PREDICTIVE QUARTET DIAGNOSTICS (test window)")
    print(f"  {'─'*70}")
    for name, lg in [('v_god_A1', log_A1), ('v_god_A2', log_A2),
                     ('v_god_A3', log_A3), ('v_god_B', log_B),
                     ('v_anneal', log_ann)]:
        s = lg.iloc[test_mask]
        print(f"\n  [{name}]")
        print(f"    γ:       mean={s['gamma'].mean():.3f}  p95={s['gamma'].quantile(0.95):.3f}")
        print(f"    cos θ:   mean={s['cos_theta'].mean():+.3f}  "
              f"pct≤0={100*(s['cos_theta']<=0).mean():.1f}%")
        print(f"    ρ_eff:   mean={s['rho_eff'].mean():+.3f}  "
              f"p95={s['rho_eff'].quantile(0.95):.3f}")
        print(f"    stop%:   {100*s['stop_flag'].mean():.1f}%    "
              f"stale%: {100*s['stale_flag'].mean():.1f}%    "
              f"drift%: {100*s['drift_flag'].mean():.1f}%")
        print(f"    conv:    mean={s['conviction'].mean():.3f}  "
              f"min={s['conviction'].min():.3f}  max={s['conviction'].max():.3f}")

    # ── Year-on-year K=1 through K=5 ──
    K_LIST = [1, 2, 3, 5]
    for name, pnl in strategies.items():
        print_yoy_table(name, pnl.iloc[test_mask], K_LIST)

    # ── Dollar simulation: $1,000 starting capital ──
    print(f"\n\n{'▓'*110}")
    print(f"  $1,000 DOLLAR SIMULATION  —  quarterly P&L and year-on-year")
    print(f"{'▓'*110}")
    print_dollar_simulation(strategies, test_mask, start_capital=1000.0,
                             K_list=[1, 2, 3, 5])

    # ── Save ──
    out = {
        'meta': {
            'version': 'godmode_v1',
            'W_TARGET_A1': W_TARGET_A1, 'W_TARGET_A2': W_TARGET_A2,
            'W_BOX': W_BOX, 'KAPPA_A': KAPPA_A, 'KAPPA_A3': KAPPA_A3,
            'CONV_MIN': CONV_MIN, 'CONV_MAX': CONV_MAX,
            'ANNEAL_AMP': ANNEAL_AMP,
            'theta_A1': diag_A1['theta'], 'theta_A2': diag_A2['theta'],
            'theta_A3': diag_A3['theta'],
        },
        'calibration': {'A1': diag_A1, 'A2': diag_A2, 'A3': diag_A3},
        'performance': {n: _stats(p.iloc[test_mask]) for n, p in strategies.items()},
    }
    out_path = OUT_DIR_ / 'crypto_godmode_v1.json'
    with open(out_path, 'w') as fh:
        json.dump(out, fh, indent=2, default=float)
    print(f"\n  Saved → {out_path}")
    print(SEP)


if __name__ == '__main__':
    main()
