"""
Crypto BSDT v4 — ΔA (Activity Acceleration) + Rolling β
=========================================================

Root cause fixed from v3:
  × v3 regime split used LEVEL A (post-shock noise → no continuation edge)
  ✓ v4 regime split uses ΔA (rate-of-change of activity)

  × v3 ETH/SOL used fixed β from training (SOL 2023-2024 structural break)
  ✓ v4 ETH/SOL uses rolling 252d β (adapts to new SOL/ETH equilibrium)

Core insight:
  HIGH A  ≠  pre-cascade acceleration
  HIGH A  =  post-cascade noise → snapback → reversion dominates

  RISING ΔA + RISING Ω = true build-up phase → continuation possible

Regime logic (v4):
  Gate:         Ω ≥ Q50  AND  |z_spread| > 1.0
  PRE-CASCADE:  ΔA_rank ≥ Q66  (A accelerating, building up)  → continuation
  POST-SHOCK:   ΔA_rank <  Q66 (A flat or falling)             → reversion

Rolling β:
  ETH/SOL: 252d rolling OLS window → β adapts to SOL structural break
  Others:  fixed training β (no structural break detected)

Pairs:
  P1. ETH/BTC     fixed β   (half-life 4.8d, expect reversion)
  P2. ETH/SOL     rolling β (expect continuation edge to emerge)
  P3. ETH/BNB     fixed β   (half-life 14d)
  P4. BTC/ALT     fixed β   (half-life 16.4d, macro rotation)
"""

import numpy as np
import pandas as pd
import json
import warnings
warnings.filterwarnings('ignore')
import yfinance as yf
from numpy.linalg import eigh
from scipy import stats

OUT_DIR    = r"C:\amttp\research\adaptive-friction\pipeline\results"
TRAIN_START = '2021-01-01'
TRAIN_END   = '2022-12-31'
TEST_START  = '2023-01-01'


# ─────────────────────────────────────────────────────────────────────────────
#  DATA  (identical to v2/v3)
# ─────────────────────────────────────────────────────────────────────────────
def fetch_and_prepare():
    print("  Fetching BTC, ETH, SOL, BNB ...")
    raw = {}
    for tk in ['BTC-USD', 'ETH-USD', 'SOL-USD', 'BNB-USD']:
        raw[tk] = yf.download(tk, start='2020-06-01', progress=False,
                              auto_adjust=True)['Close'].squeeze()
    df = pd.DataFrame({
        'btc': raw['BTC-USD'],
        'eth': raw['ETH-USD'],
        'sol': raw['SOL-USD'],
        'bnb': raw['BNB-USD'],
    }).dropna()
    for a in ['btc', 'eth', 'sol', 'bnb']:
        df[f'ret_{a}'] = np.log(df[a] / df[a].shift(1))
        df[f'log_{a}'] = np.log(df[a])
    df['alt_basket']     = np.exp((df['log_eth'] + df['log_sol'] + df['log_bnb']) / 3)
    df['log_alt_basket'] = np.log(df['alt_basket'])
    df['ret_alt_basket'] = np.log(df['alt_basket'] / df['alt_basket'].shift(1))
    df['alt_ret_eq']  = (df['ret_eth'] + df['ret_sol'] + df['ret_bnb']) / 3
    df['btc_dom']     = df['ret_btc'] - df['alt_ret_eq']
    df['cross_disp']  = df[['ret_btc', 'ret_eth', 'ret_sol', 'ret_bnb']].std(axis=1)
    for a in ['btc', 'eth', 'sol', 'bnb']:
        df[f'vol_{a}'] = df[f'ret_{a}'].rolling(20).std() * np.sqrt(252)
    def z(s, w=252):
        mu = s.rolling(w, min_periods=60).mean()
        sd = s.rolling(w, min_periods=60).std()
        return (s - mu) / (sd + 1e-9)
    for c in ['ret_btc', 'ret_eth', 'ret_sol', 'ret_bnb',
              'vol_btc', 'vol_eth', 'btc_dom', 'cross_disp']:
        df[f'{c}_z'] = z(df[c])
    for h in [3, 5, 7, 14, 21]:
        df[f'ret{h}_eth'] = df['ret_eth'].rolling(h).sum()
        df[f'ret{h}_btc'] = df['ret_btc'].rolling(h).sum()
    df = df.dropna()
    print(f"  Data: {df.index[0].date()} → {df.index[-1].date()}  n={len(df)}")
    return df


# ─────────────────────────────────────────────────────────────────────────────
#  BSDT ENGINE  (identical to v2/v3)
# ─────────────────────────────────────────────────────────────────────────────
def compute_bsdt(df, features, window=60, rho=0.9, ell=1.0):
    X     = df[features].values
    T     = len(X)
    omega = np.full(T, np.nan)
    mfls  = np.full(T, np.nan)
    gamma = np.full(T, np.nan)

    for t in range(window, T):
        wd = X[t - window:t + 1]
        wd = wd[np.all(np.isfinite(wd), axis=1)]
        if len(wd) < window // 2:
            continue
        corr = np.corrcoef(wd.T)
        if not np.all(np.isfinite(corr)):
            corr = np.where(np.isfinite(corr), corr, 0.0)
            np.fill_diagonal(corr, 1.0)
        W = np.abs(corr)
        W = W / (W.sum(axis=1, keepdims=True) + 1e-12)
        eigvals, _ = eigh(W)
        lam_max  = eigvals[-1]
        omega[t] = rho * ell * lam_max
        mu_wd    = wd.mean(axis=0)
        mfls[t]  = np.linalg.norm(X[t] - mu_wd) * lam_max
        om_hist  = omega[max(0, t - 20):t + 1]
        om_hist  = om_hist[np.isfinite(om_hist)]
        gamma[t] = 1.0 / (1.0 + (om_hist.mean() if len(om_hist) > 0 else omega[t]))

    idx = df.index
    return (pd.Series(omega, index=idx, name='omega'),
            pd.Series(mfls,  index=idx, name='mfls'),
            pd.Series(gamma, index=idx, name='gamma'))


# ─────────────────────────────────────────────────────────────────────────────
#  PHASE DETECTOR  (identical to v2/v3)
# ─────────────────────────────────────────────────────────────────────────────
def detect_phase_crypto(omega, ret7, ret3, btc_dom_z,
                        crash_ret7=-0.10, recov_ret3=0.03):
    q50      = omega.expanding(60).quantile(0.50)
    q75      = omega.expanding(60).quantile(0.75)
    elevated = omega >= q50
    high     = omega >= q75
    crash_cond  = elevated & ((ret7 < crash_ret7) | (btc_dom_z > 1.5)) & (ret3 < 0)
    recov_cond  = high & (ret3 > recov_ret3) & ~crash_cond
    raw = np.ones(len(omega), dtype=int)
    raw[~elevated.values]   = 0
    raw[crash_cond.values]  = 2
    raw[recov_cond.values]  = 3
    return pd.Series(raw, index=omega.index, name='phase')


# ─────────────────────────────────────────────────────────────────────────────
#  ΔA — ACTIVITY ACCELERATION  (NEW in v4)
# ─────────────────────────────────────────────────────────────────────────────
def compute_delta_a(mfls, gamma, diff_window=5, smooth_window=3):
    """
    ΔA_t = smoothed 5-period change in activity A = MFLS/γ

    Captures build-up phase (pre-cascade) vs post-explosion noise.
    ΔA rising → instability accelerating → pre-cascade → continuation possible
    ΔA flat / falling → post-shock dissipation → reversion dominates
    """
    A = mfls / (gamma + 1e-9)
    dA = A.diff(diff_window).rolling(smooth_window).mean()
    return A, dA


# ─────────────────────────────────────────────────────────────────────────────
#  COINTEGRATION SPREAD — FIXED β  (same as v3)
# ─────────────────────────────────────────────────────────────────────────────
def compute_cointegration_params(log_a, log_b, train_mask):
    la = log_a[train_mask].values
    lb = log_b[train_mask].values
    X  = np.column_stack([np.ones(len(lb)), lb])
    coefs = np.linalg.lstsq(X, la, rcond=None)[0]
    alpha, beta = coefs[0], coefs[1]
    S_train  = la - alpha - beta * lb
    mu_s     = S_train.mean()
    sigma_s  = S_train.std()
    dS       = np.diff(S_train)
    S_lag    = S_train[:-1] - mu_s
    if S_lag.std() > 1e-9:
        phi = np.corrcoef(S_lag, dS)[0, 1]
        half_life = np.log(0.5) / np.log(1 + phi) if (-1 < phi < 0) else np.nan
    else:
        half_life = np.nan
    zero_cross = (np.sign(S_train[1:] - mu_s) != np.sign(S_train[:-1] - mu_s)).mean()
    return dict(alpha=alpha, beta=beta, mu_s=mu_s, sigma_s=sigma_s,
                half_life=half_life, zero_crossings=float(zero_cross),
                n_train=int(train_mask.sum()))


def compute_spread_zscore_fixed(log_a, log_b, params):
    S = log_a.values - params['alpha'] - params['beta'] * log_b.values
    z = (S - params['mu_s']) / (params['sigma_s'] + 1e-9)
    return pd.Series(z, index=log_a.index, name='z_spread')


# ─────────────────────────────────────────────────────────────────────────────
#  ROLLING β SPREAD  (NEW in v4 — for ETH/SOL structural break)
# ─────────────────────────────────────────────────────────────────────────────
def compute_spread_zscore_rolling(log_a, log_b, beta_window=252, zscore_window=60):
    """
    Rolling OLS β:  S_t = log_A_t - alpha_t - beta_t * log_B_t
    β re-estimated each day on trailing beta_window days.
    Spread centred with rolling zscore_window mean/std.

    Handles structural breaks (e.g., SOL repricing in 2023-2024).
    """
    la = log_a.values
    lb = log_b.values
    n  = len(la)
    spread = np.full(n, np.nan)
    betas  = np.full(n, np.nan)

    print(f"    Rolling β ({beta_window}d window) ...", end='', flush=True)
    for t in range(beta_window, n):
        wla = la[t - beta_window:t]
        wlb = lb[t - beta_window:t]
        X   = np.column_stack([np.ones(beta_window), wlb])
        try:
            coefs     = np.linalg.lstsq(X, wla, rcond=None)[0]
            alpha, beta = coefs[0], coefs[1]
            spread[t] = la[t] - alpha - beta * lb[t]
            betas[t]  = beta
        except Exception:
            pass
    print(f" done  β_range=[{np.nanmin(betas):.3f}, {np.nanmax(betas):.3f}]")

    s_series = pd.Series(spread, index=log_a.index)
    mu = s_series.rolling(zscore_window, min_periods=30).mean()
    sd = s_series.rolling(zscore_window, min_periods=30).std()
    z  = (s_series - mu) / (sd + 1e-9)

    return z, pd.Series(betas, index=log_a.index)


# ─────────────────────────────────────────────────────────────────────────────
#  DIRECTIONAL BASELINE  (v2 Setup A, unchanged)
# ─────────────────────────────────────────────────────────────────────────────
def setup_a_directional(df, omega, mfls, gamma, phase):
    activity = mfls / (gamma + 1e-9)
    w1 = omega.expanding(60).rank(pct=True)
    w2 = activity.expanding(60).rank(pct=True)
    w1_g = w1.where(w1 >= 0.50, 0.0)
    w2_g = w2.where(w2 >= 0.33, 0.0)
    mom5 = np.sign(df['ret5_eth'])
    ph   = phase.values
    d    = np.zeros(len(df))
    d[ph == 2] = mom5.values[ph == 2]
    d[ph == 3] = 1.0
    d  = pd.Series(d, index=df.index)
    return (d * w1_g * w2_g).clip(-1, 1)


# ─────────────────────────────────────────────────────────────────────────────
#  REGIME-CONDITIONAL PAIRS  v4: ΔA instead of level A
# ─────────────────────────────────────────────────────────────────────────────
def setup_pairs_v4(df, omega, A, dA, z_spread, z_threshold=1.0):
    """
    v4 regime split — uses ΔA for pre-cascade detection:

    Gate:         Ω ≥ Q50  AND  |z_spread| > z_threshold
    PRE-CASCADE:  dA_rank ≥ Q66  → CONTINUATION  (spread continues in same direction)
    POST-SHOCK:   dA_rank <  Q66  → REVERSION     (spread snaps back)

    Size: min(|z|, 2) / 2   (0.5 at z=1 → 1.0 at z≥2)
    """
    omega_q50 = omega.expanding(60).quantile(0.50)
    dA_rank   = dA.expanding(60).rank(pct=True)

    omega_gate  = omega >= omega_q50
    spread_gate = np.abs(z_spread) > z_threshold
    combined    = omega_gate & spread_gate

    pre_cascade = combined & (dA_rank >= 0.66)   # A accelerating → continuation
    post_shock  = combined & (dA_rank <  0.66)   # A flat/falling → reversion

    direction = pd.Series(0.0, index=df.index)
    direction[post_shock]   = -np.sign(z_spread[post_shock])    # fade
    direction[pre_cascade]  =  np.sign(z_spread[pre_cascade])   # follow

    size = np.minimum(np.abs(z_spread), 2.0) / 2.0
    return (direction * size).clip(-1, 1), pre_cascade, post_shock


# ─────────────────────────────────────────────────────────────────────────────
#  PnL / IC  (identical to v2/v3)
# ─────────────────────────────────────────────────────────────────────────────
def simulate(pos, ret, label=""):
    r   = ret.fillna(0).values
    p   = pos.shift(1).fillna(0).values
    pnl = p * r
    cum = np.cumprod(1 + pnl)
    bh  = np.cumprod(1 + r)
    active   = pnl[p != 0]
    sharpe   = (active.mean() / (np.std(active) + 1e-12)) * np.sqrt(252) if len(active) > 0 else 0.0
    roll_max = np.maximum.accumulate(cum)
    max_dd   = (cum / roll_max - 1).min()
    leverage = np.abs(p).mean()
    hit_rate = (active > 0).mean() if len(active) > 0 else np.nan
    q10      = np.quantile(r, 0.10)
    t_mask   = (r <= q10) & (p != 0)
    tail_acc = (np.sign(p[t_mask]) == np.sign(r[t_mask])).mean() if t_mask.sum() > 0 else np.nan
    tail_pnl = (p[t_mask] * r[t_mask]).mean() if t_mask.sum() > 0 else np.nan
    bh_sh  = (r.mean() / (r.std() + 1e-12)) * np.sqrt(252)
    bh_dd  = (bh / np.maximum.accumulate(bh) - 1).min()
    return dict(
        label=label,
        sharpe=round(float(sharpe), 3),
        sharpe_per_lev=round(float(sharpe / (leverage + 1e-9)), 3),
        max_dd=round(float(max_dd), 3),
        cum_return=round(float(cum[-1] - 1), 3),
        active_days=int((p != 0).sum()),
        total_days=len(p),
        hit_rate=round(float(hit_rate), 3) if not np.isnan(hit_rate) else None,
        tail_acc=round(float(tail_acc), 3) if not np.isnan(tail_acc) else None,
        tail_pnl=round(float(tail_pnl), 5) if not np.isnan(tail_pnl) else None,
        leverage=round(float(leverage), 4),
        bh_sharpe=round(float(bh_sh), 3),
        bh_max_dd=round(float(bh_dd), 3),
        bh_cum=round(float(bh[-1] - 1), 3),
    )


def ic_metric(pos, fwd, label=""):
    nz = (pos != 0) & fwd.notna()
    n  = nz.sum()
    if n < 20:
        return dict(label=label, n=int(n), ic=None, acc=None)
    ic_v, _ = stats.spearmanr(pos[nz].values, fwd[nz].values)
    acc = (np.sign(pos[nz].values) == np.sign(fwd[nz].values)).mean()
    return dict(label=label, n=int(n), ic=round(float(ic_v), 4), acc=round(float(acc), 3))


# ─────────────────────────────────────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────────────────────────────────────
def main():
    print("=" * 72)
    print("  CRYPTO BSDT v4 — ΔA Activity Acceleration + Rolling β")
    print("  Fix: pre-cascade = ΔA rising, not level A high")
    print("=" * 72)

    df = fetch_and_prepare()
    train_mask = (df.index >= TRAIN_START) & (df.index <= TRAIN_END)
    test_mask  = df.index >= TEST_START
    print(f"  Train: {df[train_mask].index[0].date()} → {df[train_mask].index[-1].date()}")
    print(f"  Test:  {df[test_mask].index[0].date()} → {df[test_mask].index[-1].date()}  n={test_mask.sum()}")

    # ── BSDT ─────────────────────────────────────────────────────────────
    feats = ['ret_eth_z', 'ret_btc_z', 'ret_sol_z', 'ret_bnb_z',
             'vol_eth_z', 'vol_btc_z', 'btc_dom_z', 'cross_disp_z']
    btc_feats = ['ret_btc_z', 'ret_eth_z', 'ret_sol_z', 'ret_bnb_z',
                 'vol_btc_z', 'vol_eth_z', 'btc_dom_z', 'cross_disp_z']

    print("\n[1]  Computing BSDT metrics ...")
    omega, mfls_eth, gamma_eth = compute_bsdt(df, feats,     window=60)
    _,     mfls_btc, gamma_btc = compute_bsdt(df, btc_feats, window=60)

    # ── ΔA  (KEY NEW COMPUTATION) ─────────────────────────────────────────
    print("\n[2]  Computing ΔA (activity acceleration) ...")
    A_eth, dA_eth = compute_delta_a(mfls_eth, gamma_eth, diff_window=5, smooth_window=3)
    A_btc, dA_btc = compute_delta_a(mfls_btc, gamma_btc, diff_window=5, smooth_window=3)

    # Diagnostic: is ΔA actually distinguishing regimes?
    dA_rank = dA_eth.expanding(60).rank(pct=True)
    print(f"\n  ΔA diagnostic [test]:")
    for q_lo, q_hi, name in [(0.0, 0.33, 'Low ΔA  (<Q33)'),
                               (0.33, 0.66, 'Mid ΔA  (Q33-Q66)'),
                               (0.66, 1.0,  'High ΔA (>Q66)')]:
        m = test_mask & (dA_rank >= q_lo) & (dA_rank < q_hi)
        n = m.sum()
        a_sub = A_eth[m]
        o_sub = omega[m]
        print(f"    {name:<20}: n={n:>4}  A_med={a_sub.median():.3f}  "
              f"A_q90={a_sub.quantile(0.9):.3f}  Ω_med={o_sub.median():.4f}")

    # ── Phase detection ───────────────────────────────────────────────────
    ret7 = df['ret_eth'].rolling(7).sum()
    ret3 = df['ret_eth'].rolling(3).sum()
    phase = detect_phase_crypto(omega, ret7, ret3, df['btc_dom_z'])

    phase_names = {0: 'QUIET', 1: 'STRESS', 2: 'CRASH', 3: 'RECOVERY'}
    print(f"\n  Phase distribution [test]:")
    for ph, name in phase_names.items():
        n = (phase[test_mask] == ph).sum()
        print(f"    {name:<12}: n={n:>4}  ({n/test_mask.sum()*100:.1f}%)")

    # ── Spread computation ────────────────────────────────────────────────
    print("\n[3]  Computing spreads ...")

    # Fixed-β pairs (no structural break)
    params_ethbtc = compute_cointegration_params(df['log_eth'], df['log_btc'], train_mask)
    params_ethbnb = compute_cointegration_params(df['log_eth'], df['log_bnb'], train_mask)
    params_btcalt = compute_cointegration_params(df['log_btc'], df['log_alt_basket'], train_mask)

    z_ethbtc = compute_spread_zscore_fixed(df['log_eth'], df['log_btc'],         params_ethbtc)
    z_ethbnb = compute_spread_zscore_fixed(df['log_eth'], df['log_bnb'],         params_ethbnb)
    z_btcalt = compute_spread_zscore_fixed(df['log_btc'], df['log_alt_basket'],  params_btcalt)

    # Rolling-β ETH/SOL (handles SOL structural break)
    print("  ETH/SOL:")
    z_ethsol_roll, betas_sol = compute_spread_zscore_rolling(
        df['log_eth'], df['log_sol'], beta_window=252, zscore_window=60)

    # Spread returns (for PnL simulation)
    def spread_ret(log_a, log_b, beta, ret_a_col, ret_b_col):
        """Dollar-neutral pair return: (ret_A - β*ret_B) / (1+|β|)"""
        ra = df[ret_a_col]
        rb = df[ret_b_col]
        if isinstance(beta, pd.Series):
            return (ra - beta * rb) / (1.0 + beta.abs() + 1e-9)
        return (ra - beta * rb) / (1.0 + abs(beta) + 1e-9)

    sret_ethbtc = spread_ret(None, None, params_ethbtc['beta'], 'ret_eth', 'ret_btc')
    sret_ethsol = spread_ret(None, None, betas_sol, 'ret_eth', 'ret_sol')
    sret_ethbnb = spread_ret(None, None, params_ethbnb['beta'], 'ret_eth', 'ret_bnb')
    sret_btcalt = spread_ret(None, None, params_btcalt['beta'], 'ret_btc', 'ret_alt_basket')

    # Cointegration diagnostics
    print(f"\n  {'Pair':<14}  {'beta':>6}  {'half-life':>10}  {'Z-cross%':>9}  "
          f"{'|z|>1% [test]':>14}")
    print("─" * 60)
    for label, params_or_z, z_s in [
        ('ETH/BTC',    params_ethbtc, z_ethbtc),
        ('ETH/SOL',    None,          z_ethsol_roll),
        ('ETH/BNB',    params_ethbnb, z_ethbnb),
        ('BTC/ALT',    params_btcalt, z_btcalt),
    ]:
        zt = z_s[test_mask]
        if params_or_z is not None:
            hl  = params_or_z['half_life']
            hl_s = f"{hl:.1f}d" if not np.isnan(hl) else "   inf"
            be_s = f"{params_or_z['beta']:.3f}"
            zc_s = f"{params_or_z['zero_crossings']*100:.1f}%"
        else:
            hl_s = "rolling"
            be_s = f"{betas_sol[test_mask].median():.3f}m"
            zc_s = f"{(np.diff(np.sign(z_s[test_mask].fillna(0).values)) != 0).mean()*100:.1f}%"
        print(f"  {label:<14}  {be_s:>6}  {hl_s:>10}  "
              f"{zc_s:>9}  {(np.abs(zt) > 1).mean()*100:>13.1f}%")

    # ── Build positions ───────────────────────────────────────────────────
    print("\n[4]  Building positions (v4 ΔA regime split) ...")
    pos_A = setup_a_directional(df, omega, mfls_eth, gamma_eth, phase)

    pos_P1, pre_P1, post_P1 = setup_pairs_v4(df, omega, A_eth, dA_eth, z_ethbtc)
    pos_P2, pre_P2, post_P2 = setup_pairs_v4(df, omega, A_eth, dA_eth, z_ethsol_roll)
    pos_P3, pre_P3, post_P3 = setup_pairs_v4(df, omega, A_eth, dA_eth, z_ethbnb)
    pos_P4, pre_P4, post_P4 = setup_pairs_v4(df, omega, A_eth, dA_eth, z_btcalt)

    # ── Simulate ──────────────────────────────────────────────────────────
    print(f"\n[5]  Simulating (test {TEST_START}→2026) ...")
    ret_eth_test = df.loc[test_mask, 'ret_eth']
    fwd21_eth    = df['ret_eth'].rolling(21).sum().shift(-21)

    sims = {
        'A_directional':   simulate(pos_A[test_mask],  ret_eth_test,              'A_directional'),
        'P1_ETH_BTC':      simulate(pos_P1[test_mask], sret_ethbtc[test_mask],    'P1_ETH_BTC'),
        'P2_ETH_SOL_roll': simulate(pos_P2[test_mask], sret_ethsol[test_mask],    'P2_ETH_SOL_roll'),
        'P3_ETH_BNB':      simulate(pos_P3[test_mask], sret_ethbnb[test_mask],    'P3_ETH_BNB'),
        'P4_BTC_ALT':      simulate(pos_P4[test_mask], sret_btcalt[test_mask],    'P4_BTC_ALT'),
    }

    ic_results = {
        'A_directional':   ic_metric(pos_A[test_mask],  fwd21_eth[test_mask], 'A'),
        'P1_ETH_BTC':      ic_metric(pos_P1[test_mask], fwd21_eth[test_mask], 'P1'),
        'P2_ETH_SOL_roll': ic_metric(pos_P2[test_mask], fwd21_eth[test_mask], 'P2_roll'),
        'P4_BTC_ALT':      ic_metric(pos_P4[test_mask], fwd21_eth[test_mask], 'P4'),
    }

    # ── Results table ─────────────────────────────────────────────────────
    print()
    print(f"── PnL (test {TEST_START}–2026) ─────────────────────────────────────────")
    print(f"  {'Strategy':<22}  {'Sharpe':>7}  {'Sh/Lev':>7}  {'MaxDD':>7}  "
          f"{'CumRet':>8}  {'TailAcc':>8}  {'Active%':>7}")
    print("─" * 78)
    bhr = sims['A_directional']
    print(f"  {'ETH Buy&Hold':<22}  {bhr['bh_sharpe']:>+7.3f}  {'   ---':>7}  "
          f"{bhr['bh_max_dd']:>7.3f}  {bhr['bh_cum']:>+8.3f}  {'    ---':>8}  {'100.0%':>7}")
    print()
    for name, r in sims.items():
        pct = r['active_days'] / r['total_days'] * 100
        ta  = f"{r['tail_acc']:.3f}" if r['tail_acc'] is not None else "    n/a"
        print(f"  {name:<22}  {r['sharpe']:>+7.3f}  {r['sharpe_per_lev']:>+7.3f}  "
              f"{r['max_dd']:>7.3f}  {r['cum_return']:>+8.3f}  {ta:>8}  {pct:>6.1f}%")

    print(f"\n── IC (H=21d) ───────────────────────────────────────────────────────")
    for name, r in ic_results.items():
        ic_s = f"{r['ic']:>+8.4f}" if r['ic'] is not None else "     n/a"
        print(f"  {name:<22}: n={r['n']:>4}  IC={ic_s}  acc={r['acc'] if r['acc'] else 'n/a'}")

    # ── KEY DIAGNOSTIC: ΔA regime accuracy  ──────────────────────────────
    print(f"\n── ΔA regime accuracy: pre-cascade vs post-shock ───────────────────")
    print(f"  (validates the theory: pre-cascade should show continuation edge)")
    print()
    for label, z_s, s_ret_s in [
        ('ETH/BTC',  z_ethbtc,      sret_ethbtc),
        ('ETH/SOL',  z_ethsol_roll, sret_ethsol),
        ('BTC/ALT',  z_btcalt,      sret_btcalt),
    ]:
        fwd5_s = s_ret_s.rolling(5).sum().shift(-5)
        print(f"  {label}   (|z|>1 gate):")
        for regime_name, mask in [('Post-shock (revert)',   post_P1 if 'BTC' in label[:3] else
                                                             post_P2 if 'SOL' in label else post_P4),
                                   ('Pre-cascade (continu)', pre_P1  if 'BTC' in label[:3] else
                                                             pre_P2  if 'SOL' in label else pre_P4)]:
            m = test_mask & mask & (np.abs(z_s) > 1.0)
            n = m.sum()
            if n < 5:
                print(f"    {regime_name:<28}: n too small")
                continue
            z_sign    = np.sign(z_s[m])
            fwd_sign  = np.sign(fwd5_s[m].fillna(0))
            rev_acc  = ((-z_sign) == fwd_sign).mean()
            cont_acc = (  z_sign  == fwd_sign).mean()
            edge_str = "→ REVERT" if rev_acc > 0.52 else "→ CONTINUE" if cont_acc > 0.52 else "→ mixed"
            print(f"    {regime_name:<28}: n={n:>4}  "
                  f"rev={rev_acc:.3f}  cont={cont_acc:.3f}  {edge_str}")
        print()

    # ── Phase-conditional pairs ───────────────────────────────────────────
    print(f"── ETH/SOL (rolling β) by phase ────────────────────────────────────")
    for ph, pname in phase_names.items():
        ph_mask = (phase == ph) & test_mask
        n = ph_mask.sum()
        if n < 10:
            continue
        r = simulate(pos_P2[ph_mask], sret_ethsol[ph_mask], label=pname)
        print(f"  {pname:<12}: Sharpe {r['sharpe']:>+6.3f}  MaxDD {r['max_dd']:>7.3f}  "
              f"active {r['active_days']/r['total_days']*100:.1f}%  n={n}")

    # ── Crisis breakdown ──────────────────────────────────────────────────
    crises = {
        '2022_winter':   ('2022-01-01', '2022-12-31'),
        '2023_recovery': ('2023-01-01', '2023-12-31'),
        '2024_bull':     ('2024-01-01', '2024-12-31'),
        '2025_bear':     ('2025-01-01', '2025-12-31'),
    }
    print(f"\n── Crisis Sharpe ────────────────────────────────────────────────────")
    print(f"  {'Period':<18}  {'v2_A':>7}  {'P1_ETH/BTC':>11}  "
          f"{'P2_SOL_roll':>12}  {'P4_BTC/ALT':>11}")
    print("─" * 66)
    def c_sh(pos, ret_s, cs, ce):
        m = (df.index >= cs) & (df.index <= ce)
        if m.sum() < 5: return "    n/a"
        return f"{simulate(pos[m], ret_s[m])['sharpe']:>+7.3f}"
    for cname, (cs, ce) in crises.items():
        va  = c_sh(pos_A,   df['ret_eth'],  cs, ce)
        p1  = c_sh(pos_P1, sret_ethbtc,    cs, ce)
        p2  = c_sh(pos_P2, sret_ethsol,    cs, ce)
        p4  = c_sh(pos_P4, sret_btcalt,    cs, ce)
        print(f"  {cname:<18}  {va}  {p1:>11}  {p2:>12}  {p4:>11}")

    # ── v3 vs v4 head-to-head ─────────────────────────────────────────────
    print(f"\n── v3 vs v4 comparison (key pairs) ─────────────────────────────────")
    print(f"  {'Pair':<18}  {'v3 Sharpe':>10}  {'v4 Sharpe':>10}  {'delta':>8}")
    v3_sharpes = {'P1_ETH_BTC': 0.656, 'P2_ETH_SOL': -0.900, 'P4_BTC_ALT': 0.685}
    v4_map     = {'P1_ETH_BTC': 'P1_ETH_BTC', 'P2_ETH_SOL': 'P2_ETH_SOL_roll', 'P4_BTC_ALT': 'P4_BTC_ALT'}
    for k, v3_sh in v3_sharpes.items():
        v4_sh = sims[v4_map[k]]['sharpe']
        delta = v4_sh - v3_sh
        flag  = " ✓ improved" if delta > 0.05 else " ✗ regressed" if delta < -0.05 else " ~ stable"
        print(f"  {k:<18}  {v3_sh:>+10.3f}  {v4_sh:>+10.3f}  {delta:>+8.3f}{flag}")

    # ─────────────────────────────────────────────────────────────────────
    #  SAVE
    # ─────────────────────────────────────────────────────────────────────
    def _clean(obj):
        if isinstance(obj, dict):   return {k: _clean(v) for k, v in obj.items()}
        if isinstance(obj, list):   return [_clean(v) for v in obj]
        if isinstance(obj, float) and np.isnan(obj): return None
        if isinstance(obj, (np.integer, np.floating)): return obj.item()
        return obj

    results = {
        "model": "Crypto BSDT v4 — ΔA Activity Acceleration + Rolling β",
        "version": "v4",
        "key_changes_from_v3": [
            "Regime split: ΔA (activity acceleration) instead of level A",
            "ETH/SOL: rolling 252d β instead of fixed training β",
            "Pre-cascade = dA_rank ≥ Q66 → continuation",
            "Post-shock  = dA_rank <  Q66 → reversion",
        ],
        "pnl_results": _clean(sims),
        "ic_results":  _clean(ic_results),
        "crisis_breakdown": _clean({
            cname: {
                "v2_A":          simulate(pos_A[  (df.index >= cs) & (df.index <= ce)],
                                          df.loc[(df.index >= cs) & (df.index <= ce), 'ret_eth'])['sharpe'],
                "P1_ETH_BTC":    simulate(pos_P1[ (df.index >= cs) & (df.index <= ce)],
                                          sret_ethbtc[(df.index >= cs) & (df.index <= ce)])['sharpe'],
                "P2_ETH_SOL_roll": simulate(pos_P2[(df.index >= cs) & (df.index <= ce)],
                                          sret_ethsol[(df.index >= cs) & (df.index <= ce)])['sharpe'],
                "P4_BTC_ALT":    simulate(pos_P4[ (df.index >= cs) & (df.index <= ce)],
                                          sret_btcalt[(df.index >= cs) & (df.index <= ce)])['sharpe'],
            }
            for cname, (cs, ce) in crises.items()
            if ((df.index >= cs) & (df.index <= ce)).sum() >= 10
        }),
        "v3_vs_v4": _clean({k: {"v3": v, "v4": sims[v4_map[k]]['sharpe']}
                             for k, v in v3_sharpes.items()}),
    }
    out_path = f"{OUT_DIR}\\crypto_bsdt_v4_results.json"
    with open(out_path, 'w') as f:
        json.dump(_clean(results), f, indent=2)
    print(f"\n  Results saved → {out_path}")

    print("\n" + "=" * 72)
    print("  SUMMARY")
    print("=" * 72)
    best = max(sims.values(), key=lambda r: r['sharpe'])
    print(f"  Best Sharpe: {best['label']} ({best['sharpe']:+.3f})")
    print(f"  ETH/SOL (rolling β) vs v3 fixed β: "
          f"{sims['P2_ETH_SOL_roll']['sharpe']:+.3f} vs -0.900")
    print(f"  Theory validated if:")
    print(f"    post-shock revert_acc > 0.52  (snapback)   ← expected dominant")
    print(f"    pre-cascade cont_acc  > 0.52  (build-up)   ← only in crypto crashes")
    print("=" * 72)


if __name__ == '__main__':
    main()
