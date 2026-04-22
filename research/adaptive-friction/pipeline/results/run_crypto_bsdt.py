"""
Crypto BSDT: Ω × (MFLS/γ) × Direction — ETH/BTC Directional + Pair Model
==========================================================================

Three setups:
  A. Directional:  ETH/USD — Ω + A + phase (crash→short, recovery→long)
  B. Relative:     ETH/BTC pair — ΔMFLS = MFLS_ETH − MFLS_BTC as direction
  C. Hybrid:       System-wide crash → directional short;
                   ETH/BTC diverge (ΔMFLS > threshold) → pair trade

Per-asset BSDT:
  Feature vector for asset i: [ret_i, vol_i, ret_BTC, vol_BTC]
  This captures both own dynamics and market-wide coupling.
  Ω_joint: computed from all-asset correlation matrix [ETH, BTC] returns + vols.

Key question answered:
  "When does ETH track BTC (use directional) vs diverge (use pairs)?"
  Measured by: rolling corr(ETH_ret, BTC_ret) — low = divergence, pairs win.

Train: 2019–2022 | Test: 2023–2026 (no look-ahead expanding quantiles)
"""

import numpy as np
import pandas as pd
import json
import warnings
warnings.filterwarnings('ignore')
import yfinance as yf
from scipy import stats

OUT_DIR = r"C:\amttp\research\adaptive-friction\pipeline\results"

# ─────────────────────────────────────────────────────────────────────────────
#  DATA FETCH + FEATURE ENGINEERING
# ─────────────────────────────────────────────────────────────────────────────
def fetch_and_prepare():
    print("  Fetching ETH, BTC, SOL...")
    raw = {}
    for tk in ['ETH-USD', 'BTC-USD', 'SOL-USD']:
        raw[tk] = yf.download(tk, start='2019-01-01', progress=False, auto_adjust=True)['Close'].squeeze()

    df = pd.DataFrame({
        'eth': raw['ETH-USD'],
        'btc': raw['BTC-USD'],
        'sol': raw['SOL-USD'],
    }).dropna(subset=['eth','btc'])

    # Daily log-returns
    df['ret_eth'] = np.log(df['eth'] / df['eth'].shift(1))
    df['ret_btc'] = np.log(df['btc'] / df['btc'].shift(1))
    df['ret_sol'] = np.log(df['sol'] / df['sol'].shift(1))

    # Realised vol (20d rolling std annualised)
    WINDOW = 20
    df['vol_eth'] = df['ret_eth'].rolling(WINDOW).std() * np.sqrt(252)
    df['vol_btc'] = df['ret_btc'].rolling(WINDOW).std() * np.sqrt(252)
    df['vol_sol'] = df['ret_sol'].rolling(WINDOW).std() * np.sqrt(252)

    # Standardise features (rolling z-score, no look-ahead)
    def rolling_z(s, w=252):
        mu  = s.rolling(w, min_periods=60).mean()
        sig = s.rolling(w, min_periods=60).std()
        return (s - mu) / (sig + 1e-9)

    for col in ['ret_eth','vol_eth','ret_btc','vol_btc','ret_sol','vol_sol']:
        df[f'{col}_z'] = rolling_z(df[col])

    # ETH/BTC ratio (for pair PnL)
    df['eth_btc_ratio'] = df['eth'] / df['btc']
    df['ret_ethbtc'] = np.log(df['eth_btc_ratio'] / df['eth_btc_ratio'].shift(1))

    df = df.dropna()
    print(f"  Data: {df.index[0].date()} → {df.index[-1].date()}  n={len(df)}")
    return df


# ─────────────────────────────────────────────────────────────────────────────
#  BSDT METRICS (Ω, MFLS, γ, dir) PER ASSET AND JOINT
# ─────────────────────────────────────────────────────────────────────────────
def compute_bsdt(df, features, window=60, rho=0.9, ell=1.0):
    """
    For a given feature matrix, compute rolling:
      Ω = ρ · ℓ · λ_max(W)        where W = |corr| (row-normalised)
      MFLS = ‖∇E_BS‖ ≈ ‖X − μ_X‖  (L2 distance from rolling mean, scaled by λ_max)
      γ    = adaptive friction ∈(0,1): γ = 1 / (1 + Ω_smoothed)
      dir  = sign of dominant eigenvector loading on first feature (returns)
    """
    X = df[features].values
    T = len(X)
    omega = np.full(T, np.nan)
    mfls  = np.full(T, np.nan)
    gamma = np.full(T, np.nan)
    dirx  = np.full(T, np.nan)

    for t in range(window, T):
        wd = X[t - window:t + 1]
        # Remove rows with NaN
        wd = wd[np.all(np.isfinite(wd), axis=1)]
        if len(wd) < window // 2:
            continue

        # Correlation matrix → weight matrix W
        corr = np.corrcoef(wd.T)
        if not np.all(np.isfinite(corr)):
            corr = np.where(np.isfinite(corr), corr, 0.0)
            np.fill_diagonal(corr, 1.0)
        W = np.abs(corr)
        row_sums = W.sum(axis=1, keepdims=True)
        W = W / (row_sums + 1e-12)

        eigvals, eigvecs = np.linalg.eigh(W)
        lam_max = eigvals[-1]
        v_max   = eigvecs[:, -1]

        # Ω
        omega[t] = rho * ell * lam_max

        # MFLS: ‖X_t − μ‖ scaled by λ_max
        mu_wd   = wd.mean(axis=0)
        dist    = np.linalg.norm(X[t] - mu_wd)
        mfls[t] = dist * lam_max

        # γ: adaptive friction — falls as Ω rises
        # Use smoothed Ω over last 20 steps
        omega_hist = omega[max(0,t-20):t+1]
        omega_hist = omega_hist[np.isfinite(omega_hist)]
        om_smooth  = omega_hist.mean() if len(omega_hist) > 0 else omega[t]
        gamma[t]   = 1.0 / (1.0 + om_smooth)

        # Direction: sign of eigenvector loading on first feature (returns_z)
        # Sign convention: largest-abs component positive
        dom = np.argmax(np.abs(v_max))
        if v_max[dom] < 0:
            v_max = -v_max
        dirx[t] = v_max[0]     # loading on first feature = returns_z

    idx = df.index
    return (pd.Series(omega, index=idx),
            pd.Series(mfls,  index=idx),
            pd.Series(gamma, index=idx),
            pd.Series(dirx,  index=idx))


# ─────────────────────────────────────────────────────────────────────────────
#  PHASE DETECTION (adapted for crypto)
# ─────────────────────────────────────────────────────────────────────────────
def detect_phase(omega, ret21, ret5, window=252):
    """
    0=QUIET, 1=STRESS, 2=CRASH, 3=RECOVERY
    Crypto uses tighter thresholds: crash_ret21=-5% (more volatile than SP500)
    """
    CRASH_THRESH = -0.05   # 21d log-return < -5%
    RECOV_THRESH = 0.00
    CONFIRM_RET5 = 0.02    # 5d return > +2% to confirm recovery

    q50 = omega.expanding(60).quantile(0.50)
    q75 = omega.expanding(60).quantile(0.75)

    domega = omega.diff().rolling(5).mean()

    elevated = omega >= q50
    high     = omega >= q75
    rising   = domega > 0
    falling  = ret21 < CRASH_THRESH
    recov    = ret21 >= RECOV_THRESH

    raw = np.ones(len(omega), dtype=int)
    raw[~elevated.values]                                     = 0
    raw[elevated.values & rising.values & falling.values]    = 2
    raw[high.values & recov.values & ~(elevated.values & rising.values & falling.values)] = 3

    # Recovery confirmation: 5d return > +2%
    r5 = ret5.values
    for t in range(1, len(raw)):
        if raw[t] == 3 and not (np.isfinite(r5[t]) and r5[t] > CONFIRM_RET5):
            raw[t] = 1
        if raw[t] == 2 and not (np.isfinite(r5[t]) and r5[t] < -0.03):
            raw[t] = 1

    return pd.Series(raw, index=omega.index, name='phase')


# ─────────────────────────────────────────────────────────────────────────────
#  POSITIONS
# ─────────────────────────────────────────────────────────────────────────────
def setup_a_directional(df, omega_eth, mfls_eth, gamma_eth, phase_eth):
    """
    Setup A: Trade ETH/USD directionally.
    position = w1(Ω_eth) × w2(MFLS_eth/γ_eth) × direction_phase
    """
    activity = mfls_eth / (gamma_eth + 1e-9)

    w1 = omega_eth.expanding(60).rank(pct=True)
    w2 = activity.expanding(60).rank(pct=True)

    # Gate: w1 >= Q50, w2 >= Q33
    w1_g = w1.where(w1 >= 0.50, 0.0)
    w2_g = w2.where(w2 >= 0.33, 0.0)

    grad = np.sign(df['ret_eth'].rolling(5).mean())   # short-term momentum as gradient proxy
    mom  = np.sign(df['ret_eth'].rolling(21).mean())  # 21d momentum

    ph = phase_eth.values
    d  = np.zeros(len(df))
    d[ph == 2] = mom.values[ph == 2]   # crash → follow momentum (usually short)
    d[ph == 3] = grad.values[ph == 3]  # recovery → gradient (long)
    d = pd.Series(d, index=df.index)

    pos = d * w1_g * w2_g
    return pos.clip(-1, 1)


def setup_b_relative(df, omega_eth, omega_btc, mfls_eth, mfls_btc,
                      gamma_eth, gamma_btc, omega_joint):
    """
    Setup B: ETH/BTC pair trade.
    ΔMFLS = MFLS_ETH/γ_ETH − MFLS_BTC/γ_BTC
    When ΔMFLS > threshold → ETH leads instability → long ETH / short BTC
    When ΔMFLS < threshold → BTC leads → short ETH / long BTC
    Gate: Ω_joint must be elevated (system-wide stress required)
    """
    act_eth = mfls_eth / (gamma_eth + 1e-9)
    act_btc = mfls_btc / (gamma_btc + 1e-9)

    delta_act = act_eth - act_btc

    # Normalise ΔMFLS using expanding percentile
    delta_rank = delta_act.expanding(60).rank(pct=True)

    # Joint Ω gate: only trade when system-wide stress elevated
    joint_q50 = omega_joint.expanding(60).quantile(0.50)
    active_joint = (omega_joint >= joint_q50).astype(float)

    # Direction: +1 = long ETH/short BTC, -1 = short ETH/long BTC
    # Use mid threshold: trade when divergence is strong (rank > 0.70 or < 0.30)
    direction = pd.Series(0.0, index=df.index)
    direction[delta_rank >= 0.70] = +1.0   # ETH leads → long ETH/BTC
    direction[delta_rank <= 0.30] = -1.0   # BTC leads → short ETH/BTC

    pos = direction * active_joint
    return pos, delta_act


def setup_c_hybrid(df, pos_a, pos_b, omega_joint, rolling_corr_ethbtc):
    """
    Setup C: Hybrid — directional when ETH and BTC co-move,
                       pairs when they diverge.

    Switch rule:
      if rolling_corr > 0.80: use Setup A (directional, high coupling)
      if rolling_corr < 0.60: use Setup B (pairs, divergence)
      otherwise: average or flat
    """
    pos = pd.Series(0.0, index=df.index)
    for i in range(len(df)):
        c = rolling_corr_ethbtc.iloc[i]
        if np.isnan(c):
            continue
        if c > 0.80:
            pos.iloc[i] = pos_a.iloc[i]       # coupled → directional
        elif c < 0.60:
            pos.iloc[i] = pos_b.iloc[i]       # diverging → pair
        else:
            pos.iloc[i] = 0.5 * pos_a.iloc[i] + 0.5 * pos_b.iloc[i]
    return pos


# ─────────────────────────────────────────────────────────────────────────────
#  SIMULATION
# ─────────────────────────────────────────────────────────────────────────────
def simulate(pos, ret, label=""):
    """
    For pair trades: ret = ret_ethbtc (ETH/BTC ratio return).
    For directional: ret = ret_eth.
    """
    r   = ret.fillna(0).values
    p   = pos.shift(1).fillna(0).values
    pnl = p * r

    cum      = np.cumprod(1 + pnl)
    bh       = np.cumprod(1 + r)
    roll_max = np.maximum.accumulate(cum)
    max_dd   = (cum / roll_max - 1).min()

    active   = pnl[p != 0]
    sharpe   = (active.mean() / (np.std(active) + 1e-12)) * np.sqrt(252) if len(active) > 0 else 0.0
    hit_rate = (active > 0).mean() if len(active) > 0 else np.nan

    q10      = np.quantile(r, 0.10)
    tail_m   = r <= q10
    tail_pos = p[tail_m & (p != 0)]
    tail_ret = r[tail_m & (p != 0)]
    tail_acc = (np.sign(tail_pos) == np.sign(tail_ret)).mean() if len(tail_pos) > 0 else np.nan
    tail_pnl = (tail_pos * tail_ret).mean() if len(tail_pos) > 0 else np.nan

    leverage = np.abs(p).mean()
    bh_sh    = (r.mean() / (r.std() + 1e-12)) * np.sqrt(252)
    bh_dd    = (bh / np.maximum.accumulate(bh) - 1).min()

    return dict(
        label=label,
        sharpe=round(float(sharpe), 4),
        sharpe_per_lev=round(float(sharpe/(leverage+1e-9)), 4),
        max_dd=round(float(max_dd), 4),
        cum_return=round(float(cum[-1]-1), 4),
        active_days=int((p!=0).sum()),
        total_days=len(p),
        hit_rate=round(float(hit_rate), 4) if not np.isnan(hit_rate) else None,
        tail_acc=round(float(tail_acc), 4) if not np.isnan(tail_acc) else None,
        tail_pnl=round(float(tail_pnl), 6) if not np.isnan(tail_pnl) else None,
        leverage=round(float(leverage), 4),
        bh_sharpe=round(float(bh_sh), 4),
        bh_max_dd=round(float(bh_dd), 4),
        bh_cum=round(float(bh[-1]-1), 4),
    )


# ─────────────────────────────────────────────────────────────────────────────
#  DIVERGENCE ANALYSIS
# ─────────────────────────────────────────────────────────────────────────────
def divergence_analysis(df, pos_a, pos_b, rolling_corr, test_mask):
    """
    Show: when corr(ETH,BTC) is low, does Setup B beat Setup A?
    """
    print("\n── ETH/BTC Coupling vs Strategy Performance ────────────────────────")
    print(f"  {'Coupling regime':<20}  {'n_days':>7}  {'Corr_range':>12}  "
          f"{'A_daily_ret':>12}  {'B_daily_ret':>12}")

    buckets = [
        ('high_coupling',  0.80, 1.00),
        ('medium_coupling',0.60, 0.80),
        ('low_coupling',   -1.0, 0.60),
    ]
    r_eth     = df['ret_eth'].fillna(0)
    r_ethbtc  = df['ret_ethbtc'].fillna(0)
    results   = {}

    for name, lo, hi in buckets:
        m = test_mask & (rolling_corr >= lo) & (rolling_corr < hi)
        n = m.sum()
        if n < 10:
            print(f"  {name:<20}  {n:>7}  {'---':>12}  {'---':>12}  {'---':>12}")
            continue

        pnl_a = (pos_a.shift(1).fillna(0) * r_eth)[m]
        pnl_b = (pos_b.shift(1).fillna(0) * r_ethbtc)[m]
        active_a = pnl_a[pos_a.shift(1).fillna(0)[m] != 0]
        active_b = pnl_b[pos_b.shift(1).fillna(0)[m] != 0]
        sh_a = (active_a.mean()/(active_a.std()+1e-12))*np.sqrt(252) if len(active_a)>5 else np.nan
        sh_b = (active_b.mean()/(active_b.std()+1e-12))*np.sqrt(252) if len(active_b)>5 else np.nan
        sh_a_s = f"{sh_a:>+12.3f}" if not np.isnan(sh_a) else "         n/a"
        sh_b_s = f"{sh_b:>+12.3f}" if not np.isnan(sh_b) else "         n/a"
        crng   = f"{lo:.2f}–{min(hi,1.0):.2f}"
        print(f"  {name:<20}  {n:>7}  {crng:>12}  {sh_a_s}  {sh_b_s}")
        results[name] = dict(n=int(n), sharpe_A=_s(sh_a), sharpe_B=_s(sh_b))

    return results


def _s(x):
    return round(float(x), 4) if x is not None and not np.isnan(x) else None


# ─────────────────────────────────────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────────────────────────────────────
def main():
    print("=" * 72)
    print("  CRYPTO BSDT: Ω × (MFLS/γ) × Direction (ETH + BTC)")
    print("=" * 72)

    df = fetch_and_prepare()

    train_mask = df.index < '2023-01-01'
    test_mask  = df.index >= '2023-01-01'
    print(f"  Train: {df[train_mask].index[0].date()} → {df[train_mask].index[-1].date()}  "
          f"n={train_mask.sum()}")
    print(f"  Test:  {df[test_mask].index[0].date()} → {df[test_mask].index[-1].date()}  "
          f"n={test_mask.sum()}")

    # ── Compute BSDT per asset ────────────────────────────────────────────
    print("\n[1] Computing BSDT metrics...")

    # ETH: feature vector = [ret_eth_z, vol_eth_z, ret_btc_z, vol_btc_z]
    eth_feats = ['ret_eth_z', 'vol_eth_z', 'ret_btc_z', 'vol_btc_z']
    print("  ETH features:", eth_feats)
    omega_eth, mfls_eth, gamma_eth, dir_eth = compute_bsdt(df, eth_feats, window=60)

    # BTC: feature vector = [ret_btc_z, vol_btc_z, ret_eth_z, vol_eth_z]
    btc_feats = ['ret_btc_z', 'vol_btc_z', 'ret_eth_z', 'vol_eth_z']
    print("  BTC features:", btc_feats)
    omega_btc, mfls_btc, gamma_btc, dir_btc = compute_bsdt(df, btc_feats, window=60)

    # Joint Ω: all 4 assets' returns
    joint_feats = ['ret_eth_z', 'ret_btc_z', 'vol_eth_z', 'vol_btc_z']
    print("  Joint features:", joint_feats)
    omega_joint, mfls_joint, gamma_joint, _ = compute_bsdt(df, joint_feats, window=60)

    # Rolling ETH/BTC correlation (60d)
    rolling_corr = df['ret_eth'].rolling(60).corr(df['ret_btc'])

    # ── BSDT stats ───────────────────────────────────────────────────────
    print("\n── BSDT stats (full history) ────────────────────────────────────────")
    print(f"  {'Metric':<20}  {'ETH':>8}  {'BTC':>8}  {'Joint':>8}")
    for label, s_eth, s_btc, s_jt in [
        ('Ω median', omega_eth, omega_btc, omega_joint),
        ('Ω max',    omega_eth, omega_btc, omega_joint),
        ('MFLS median', mfls_eth, mfls_btc, mfls_joint),
        ('γ median',    gamma_eth, gamma_btc, gamma_joint),
    ]:
        fn = np.median if 'median' in label else np.nanmax
        nm = lambda s: f"{fn(s.dropna().values):>8.4f}"
        print(f"  {label:<20}  {nm(s_eth)}  {nm(s_btc)}  {nm(s_jt)}")

    corr_ω  = omega_eth.dropna().corr(omega_btc.dropna())
    print(f"\n  Corr(Ω_ETH, Ω_BTC)       = {corr_ω:+.4f}")
    print(f"  Mean rolling corr(ETH,BTC) = {rolling_corr.dropna().mean():+.4f}  (test)")

    # ── Phase detection for ETH ──────────────────────────────────────────
    print("\n[2] Detecting phases (ETH)...")
    ret21_eth = df['ret_eth'].rolling(21).sum()   # 21-day cumulative log-ret
    ret5_eth  = df['ret_eth'].rolling(5).sum()
    phase_eth = detect_phase(omega_eth, ret21_eth, ret5_eth)

    phase_names = {0:'QUIET', 1:'STRESS', 2:'CRASH', 3:'RECOVERY'}
    print(f"\n  Phase distribution (test 2023+):")
    for ph, name in phase_names.items():
        n   = (phase_eth[test_mask] == ph).sum()
        pct = n / test_mask.sum() * 100
        print(f"    {name:<12}: {n:>4}  ({pct:>5.1f}%)")

    # ── Build positions ──────────────────────────────────────────────────
    print("\n[3] Building positions...")
    pos_a = setup_a_directional(df, omega_eth, mfls_eth, gamma_eth, phase_eth)
    pos_b, delta_act = setup_b_relative(df, omega_eth, omega_btc, mfls_eth, mfls_btc,
                                         gamma_eth, gamma_btc, omega_joint)
    pos_c = setup_c_hybrid(df, pos_a, pos_b, omega_joint, rolling_corr)

    # ── Simulate (test only) ─────────────────────────────────────────────
    print("\n[4] Simulating (test 2023-2026)...")
    ret_eth_test    = df.loc[test_mask, 'ret_eth']
    ret_ethbtc_test = df.loc[test_mask, 'ret_ethbtc']

    sims = {
        'A_directional_eth':  simulate(pos_a[test_mask], ret_eth_test,    'A_directional'),
        'B_pairs_ethbtc':     simulate(pos_b[test_mask], ret_ethbtc_test,  'B_pairs'),
        'C_hybrid':           simulate(pos_c[test_mask], ret_eth_test,     'C_hybrid'),
    }

    # ── Print results ─────────────────────────────────────────────────────
    print(f"\n── PnL Comparison (test 2023–2026) ──────────────────────────────────")
    print(f"  {'Strategy':<26}  {'Sharpe':>7}  {'Sh/Lev':>7}  {'MaxDD':>7}  "
          f"{'CumRet':>8}  {'TailAcc':>8}  {'Active%':>8}")
    print("─" * 83)

    ref = sims['A_directional_eth']
    print(f"  {'ETH Buy & Hold':<26}  {ref['bh_sharpe']:>+7.3f}  {'---':>7}  "
          f"{ref['bh_max_dd']:>7.3f}  {ref['bh_cum']:>+8.3f}  {'---':>8}  {'100%':>8}")
    for name, r in sims.items():
        apct = r['active_days'] / r['total_days'] * 100
        tail = f"{r['tail_acc']:.3f}" if r['tail_acc'] is not None else "  n/a"
        print(f"  {name:<26}  {r['sharpe']:>+7.3f}  {r['sharpe_per_lev']:>+7.3f}  "
              f"{r['max_dd']:>7.3f}  {r['cum_return']:>+8.3f}  {tail:>8}  {apct:>7.1f}%")

    # ── Divergence analysis ───────────────────────────────────────────────
    div_results = divergence_analysis(df, pos_a, pos_b, rolling_corr, test_mask)

    # ── ΔMFLS stats ───────────────────────────────────────────────────────
    print("\n── ΔMFLS = A_ETH − A_BTC: when ETH leads vs BTC leads ──────────────")
    da_test = delta_act[test_mask]
    print(f"  % of test days ETH leads (ΔMFLS > 0):  {(da_test > 0).mean()*100:.1f}%")
    print(f"  % of test days BTC leads (ΔMFLS < 0):  {(da_test < 0).mean()*100:.1f}%")
    print(f"  Mean ΔMFLS when ETH is in CRASH phase: "
          f"{da_test[phase_eth[test_mask]==2].mean():.2f}")
    print(f"  Mean ΔMFLS when ETH is in RECOVERY:   "
          f"{da_test[phase_eth[test_mask]==3].mean():.2f}")

    # ── Crisis periods ────────────────────────────────────────────────────
    print("\n── Crisis period breakdown (Setup A directional) ────────────────────")
    crises = {
        '2022_crypto_winter': ('2022-01-01', '2022-12-31'),
        '2023_recovery':      ('2023-01-01', '2023-12-31'),
        '2024_bull_run':      ('2024-01-01', '2024-12-31'),
        '2025_bear':          ('2025-01-01', '2026-04-22'),
    }
    for label, (s, e) in crises.items():
        m = (df.index >= s) & (df.index <= e)
        if m.sum() < 20:
            continue
        r = simulate(pos_a[m], df.loc[m, 'ret_eth'], label=label)
        bh_r = simulate(pd.Series(1.0, index=df.index[m]), df.loc[m, 'ret_eth'], label='bh')
        print(f"  {label:<25}: Strat Sharpe={r['sharpe']:>+7.3f}  "
              f"MaxDD={r['max_dd']:>7.3f}  BH_Sharpe={bh_r['bh_sharpe']:>+7.3f}")

    # ── Save ─────────────────────────────────────────────────────────────
    output = {
        "model": "Crypto BSDT: ETH/BTC Directional + Pair Model",
        "architecture": {
            "setup_A": "ETH/USD directional: w1(Ω_eth) × w2(MFLS_eth/γ_eth) × phase_direction",
            "setup_B": "ETH/BTC pair: ΔMFLS = A_eth−A_btc, gate on Ω_joint",
            "setup_C": "Hybrid: rolling_corr(ETH,BTC) > 0.80 → A; < 0.60 → B; else blend",
        },
        "pnl_results": sims,
        "divergence_analysis": div_results,
        "key_insights": {
            "omega_coupling": round(float(corr_ω), 4),
            "delta_mfls_interpretation":
                "ΔMFLS > 0 means ETH activity exceeds BTC → ETH leads instability. "
                "Use long ETH/short BTC. Negative = BTC dominates.",
            "hybrid_logic":
                "When ETH-BTC correlation is high, pair trades cancel out → use directional. "
                "When correlation is low, divergence is present → pair trade captures the spread.",
        }
    }

    out_json = f"{OUT_DIR}/crypto_bsdt_results.json"
    with open(out_json, 'w') as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\n✓ Saved: {out_json}")
    print("\n" + "=" * 72)
    print("  CRYPTO BSDT — COMPLETE")
    print("=" * 72)


if __name__ == '__main__':
    main()
