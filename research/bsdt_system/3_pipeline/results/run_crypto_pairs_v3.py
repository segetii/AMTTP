"""
Crypto BSDT v3 — Spread + Ω/A Regime-Conditional Pairs
=======================================================

Root cause fixed from v2:
  × v2 pairs: ΔA → relative direction  (wrong: trades volatility asymmetry, not mispricing)
  ✓ v3 pairs: spread z-score → direction, A → regime mode (revert vs continue)

Core architecture (the fix):
  MISSING PIECE (v2): a notion of equilibrium between assets
  NEW (v3):
    Axis 1 — Systemic instability  : Ω, A  → "is the system active?"
    Axis 2 — Relative mispricing   : cointegrating spread S_t → "who is off equilibrium?"

Trading logic:
  Gate:   Ω ≥ Q50  AND  |z_spread| > 1.0
  Then:
    A_rank < Q33  (quiet/normal activity)   → mean REVERSION  (fade large spread)
    A_rank ≥ Q66  (high instability)        → CONTINUATION    (follow spread direction)
    mid-A                                   → no trade

Why this works:
  - Low A:  normal market; large spread deviations are transient → revert
  - High A: stressed market; large deviations persist / widen → trend

Pairs tested:
  P1. ETH/BTC     hierarchical pair   (expected: weakest — high corr 0.85)
  P2. ETH/SOL     horizontal pair     (expected: best    — independent catalysts)
  P3. ETH/BNB     utility pair        (different tokenomics)
  P4. BTC/ALT     macro pair          (BTC vs equal-weight ALT basket)

Enhancement to directional (v2 Setup A):
  D_enhanced:  ETH/USD directional + ΔA leverage scaling
    pos_size *= (1 + 0.5 × normalised(A_ETH - A_BTC))
  Correct use of ΔA: sizing, NOT direction
"""

import numpy as np
import pandas as pd
import json
import warnings
warnings.filterwarnings('ignore')
import yfinance as yf
from numpy.linalg import eigh
from scipy import stats

OUT_DIR = r"C:\amttp\research\adaptive-friction\pipeline\results"

TRAIN_START = '2021-01-01'
TRAIN_END   = '2022-12-31'
TEST_START  = '2023-01-01'


# ─────────────────────────────────────────────────────────────────────────────
#  DATA  (identical to v2)
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
        df[f'ret_{a}']  = np.log(df[a] / df[a].shift(1))
        df[f'log_{a}']  = np.log(df[a])

    # Equal-weight ALT basket (for BTC/ALT spread)
    df['alt_basket']     = np.exp((df['log_eth'] + df['log_sol'] + df['log_bnb']) / 3)
    df['log_alt_basket'] = np.log(df['alt_basket'])
    df['ret_alt_basket'] = np.log(df['alt_basket'] / df['alt_basket'].shift(1))

    # BTC dominance proxy
    df['alt_ret_eq'] = (df['ret_eth'] + df['ret_sol'] + df['ret_bnb']) / 3
    df['btc_dom']    = df['ret_btc'] - df['alt_ret_eq']
    df['cross_disp'] = df[['ret_btc', 'ret_eth', 'ret_sol', 'ret_bnb']].std(axis=1)

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
#  BSDT ENGINE  (identical to v2)
# ─────────────────────────────────────────────────────────────────────────────
def compute_bsdt(df, features, window=60, rho=0.9, ell=1.0):
    X     = df[features].values
    T     = len(X)
    omega = np.full(T, np.nan)
    mfls  = np.full(T, np.nan)
    gamma = np.full(T, np.nan)
    dirx  = np.full(T, np.nan)

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
        eigvals, eigvecs = eigh(W)
        lam_max  = eigvals[-1]
        v_max    = eigvecs[:, -1]
        omega[t] = rho * ell * lam_max
        mu_wd    = wd.mean(axis=0)
        dist     = np.linalg.norm(X[t] - mu_wd)
        mfls[t]  = dist * lam_max
        om_hist  = omega[max(0, t - 20):t + 1]
        om_hist  = om_hist[np.isfinite(om_hist)]
        gamma[t] = 1.0 / (1.0 + (om_hist.mean() if len(om_hist) > 0 else omega[t]))
        dom      = np.argmax(np.abs(v_max))
        if v_max[dom] < 0:
            v_max = -v_max
        dirx[t] = v_max[0]

    idx = df.index
    return (pd.Series(omega, index=idx, name='omega'),
            pd.Series(mfls,  index=idx, name='mfls'),
            pd.Series(gamma, index=idx, name='gamma'),
            pd.Series(dirx,  index=idx, name='dirx'))


# ─────────────────────────────────────────────────────────────────────────────
#  PHASE DETECTOR  (identical to v2)
# ─────────────────────────────────────────────────────────────────────────────
def detect_phase_crypto(omega, ret7, ret3, btc_dom_z,
                        crash_ret7=-0.10, recov_ret3=0.03):
    q50      = omega.expanding(60).quantile(0.50)
    q75      = omega.expanding(60).quantile(0.75)
    elevated = omega >= q50
    high     = omega >= q75
    hard_crash   = (ret7 < crash_ret7)
    btc_flight   = (btc_dom_z > 1.5)
    in_fall      = (ret3 < 0)
    crash_cond   = elevated & (hard_crash | btc_flight) & in_fall
    recov_cond   = high & (ret3 > recov_ret3) & ~crash_cond
    raw = np.ones(len(omega), dtype=int)
    raw[~elevated.values]   = 0
    raw[crash_cond.values]  = 2
    raw[recov_cond.values]  = 3
    return pd.Series(raw, index=omega.index, name='phase')


# ─────────────────────────────────────────────────────────────────────────────
#  COINTEGRATION SPREAD  (NEW in v3)
# ─────────────────────────────────────────────────────────────────────────────
def compute_cointegration_params(log_a, log_b, train_mask):
    """
    OLS regression:  log_A = alpha + beta × log_B  (on training period only)
    Returns baseline parameters and stationarity diagnostics.

    Half-life of mean reversion from AR(1):  half_life = log(0.5) / log(rho_ar1)
    """
    la = log_a[train_mask].values
    lb = log_b[train_mask].values

    # OLS  [no look-ahead: uses only train data]
    X     = np.column_stack([np.ones(len(lb)), lb])
    coefs = np.linalg.lstsq(X, la, rcond=None)[0]
    alpha, beta = coefs[0], coefs[1]

    # Residual spread in training period
    S_train = la - alpha - beta * lb
    mu_s    = S_train.mean()
    sigma_s = S_train.std()

    # AR(1) half-life (mean-reversion speed)
    dS = np.diff(S_train)
    S_lag = S_train[:-1] - mu_s
    if S_lag.std() > 1e-9:
        rho_ar1 = np.corrcoef(S_lag, dS)[0, 1]
        # AR(1) coef:  ΔS = phi*(S-mu)  →  phi = corr(S_lag, ΔS)
        phi      = rho_ar1
        if phi < 0 and phi > -1:
            half_life = np.log(0.5) / np.log(1 + phi)   # positive if phi < 0
        else:
            half_life = np.nan
    else:
        half_life = np.nan

    # Akaike-like stationarity: fraction of time spread crosses zero
    zero_crossings = (np.sign(S_train[1:] - mu_s) != np.sign(S_train[:-1] - mu_s)).mean()

    return dict(alpha=alpha, beta=beta, mu_s=mu_s, sigma_s=sigma_s,
                half_life=half_life, zero_crossings=float(zero_crossings),
                n_train=int(train_mask.sum()))


def compute_spread_zscore(log_a, log_b, params):
    """
    Compute out-of-sample spread z-score using fixed baseline params.
    z_t = (S_t - mu_s) / sigma_s   where S_t = log_A - alpha - beta*log_B
    """
    S  = log_a.values - params['alpha'] - params['beta'] * log_b.values
    z  = (S - params['mu_s']) / (params['sigma_s'] + 1e-9)
    return pd.Series(z, index=log_a.index, name='z_spread')


# ─────────────────────────────────────────────────────────────────────────────
#  POSITIONS
# ─────────────────────────────────────────────────────────────────────────────
def setup_a_directional_v2(df, omega, mfls, gamma, phase):
    """v2 Setup A baseline (ETH/USD directional).  Reproduced unchanged for comparison."""
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
    d    = pd.Series(d, index=df.index)
    return (d * w1_g * w2_g).clip(-1, 1)


def setup_d_enhanced(df, omega, mfls_eth, mfls_btc, gamma_eth, gamma_btc, phase):
    """
    ETH/USD directional (v2 A) + ΔA leverage scaling.

    ΔA = A_ETH - A_BTC tells us which asset has higher instability:
      ΔA >> 0 → ETH significantly more unstable → scale UP ETH position
      ΔA << 0 → BTC more unstable              → scale DOWN ETH position

    This is the CORRECT use of ΔA: adjust SIZE, not direction.
    Leverage factor: 1.0 at neutral, 1.5 at max ETH dominance, 0.5 at min.
    """
    A_eth = mfls_eth / (gamma_eth + 1e-9)
    A_btc = mfls_btc / (gamma_btc + 1e-9)

    delta_a      = A_eth - A_btc
    da_rank      = delta_a.expanding(60).rank(pct=True)   # 0→1
    da_norm      = 2 * da_rank - 1                        # -1→+1
    lev_factor   = (1.0 + 0.5 * da_norm).clip(0.5, 1.5)

    pos_base = setup_a_directional_v2(df, omega, mfls_eth, gamma_eth, phase)
    return (pos_base * lev_factor).clip(-1, 1)


def setup_regime_pairs_v3(df, omega, mfls, gamma, z_spread, pair_ret_col,
                           z_threshold=1.0, label="pairs_v3"):
    """
    Regime-conditional pairs:
      Gate: Ω ≥ Q50  AND  |z_spread| > z_threshold
      Low A  (< Q33):  mean REVERSION  [fade large spread deviations]
      High A (≥ Q66):  CONTINUATION    [follow large spread deviations]
      Mid A:           no trade

    Size: proportional to |z_spread|, capped at 2σ:
      size = min(|z|, 2) / 2   [0.5 at z=1, 1.0 at z=2+]

    Direction (+1 = long spread = long asset_A / short asset_B):
      REVERSION:     z > 0 → -1  (A stretched above equil → fade → short spread)
                     z < 0 → +1  (A below equil → buy spread)
      CONTINUATION:  z > 0 → +1  (momentum → long spread)
                     z < 0 → -1  (momentum → short spread)
    """
    activity = mfls / (gamma + 1e-9)
    omega_q50 = omega.expanding(60).quantile(0.50)
    a_rank    = activity.expanding(60).rank(pct=True)

    omega_gate  = omega >= omega_q50
    spread_gate = np.abs(z_spread) > z_threshold
    combined    = omega_gate & spread_gate

    low_a  = a_rank < 0.33
    high_a = a_rank >= 0.66

    reversion_dir    = -np.sign(z_spread)    # fade spread
    continuation_dir =  np.sign(z_spread)    # follow spread

    direction = pd.Series(0.0, index=df.index)
    rev_mask  = combined & low_a
    cont_mask = combined & high_a

    direction[rev_mask]  = reversion_dir[rev_mask]
    direction[cont_mask] = continuation_dir[cont_mask]

    # Size proportional to confidence in spread deviation
    size = np.minimum(np.abs(z_spread), 2.0) / 2.0

    return (direction * size).clip(-1, 1)


# ─────────────────────────────────────────────────────────────────────────────
#  PnL SIMULATION  (identical to v2)
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
    acc      = (np.sign(pos[nz].values) == np.sign(fwd[nz].values)).mean()
    return dict(label=label, n=int(n), ic=round(float(ic_v), 4), acc=round(float(acc), 3))


def crisis_sharpe(pos, ret, periods):
    out = {}
    for name, (s, e) in periods.items():
        mask = (ret.index >= s) & (ret.index <= e)
        if mask.sum() < 5:
            continue
        out[name] = simulate(pos[mask], ret[mask], label=name)['sharpe']
    return out


# ─────────────────────────────────────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────────────────────────────────────
def main():
    print("=" * 72)
    print("  CRYPTO BSDT v3 — Spread + Ω/A Regime-Conditional Pairs")
    print("  Fixing v2: replace ΔA→direction with spread z-score + regime mode")
    print("=" * 72)

    df = fetch_and_prepare()

    train_mask = (df.index >= TRAIN_START) & (df.index <= TRAIN_END)
    test_mask  = df.index >= TEST_START
    print(f"  Train: {df[train_mask].index[0].date()} → {df[train_mask].index[-1].date()}  n={train_mask.sum()}")
    print(f"  Test:  {df[test_mask].index[0].date()} → {df[test_mask].index[-1].date()}  n={test_mask.sum()}")

    # ── BSDT features (same 8-dim space as v2) ───────────────────────────
    feats = ['ret_eth_z', 'ret_btc_z', 'ret_sol_z', 'ret_bnb_z',
             'vol_eth_z', 'vol_btc_z', 'btc_dom_z', 'cross_disp_z']
    btc_feats = ['ret_btc_z', 'ret_eth_z', 'ret_sol_z', 'ret_bnb_z',
                 'vol_btc_z', 'vol_eth_z', 'btc_dom_z', 'cross_disp_z']

    print("\n[1]  Computing BSDT metrics (window=60d) ...")
    omega_eth, mfls_eth, gamma_eth, _ = compute_bsdt(df, feats,     window=60)
    omega_btc, mfls_btc, gamma_btc, _ = compute_bsdt(df, btc_feats, window=60)

    # ── Phase detection ───────────────────────────────────────────────────
    ret7_eth  = df['ret_eth'].rolling(7).sum()
    ret3_eth  = df['ret_eth'].rolling(3).sum()
    phase     = detect_phase_crypto(omega_eth, ret7_eth, ret3_eth, df['btc_dom_z'])

    phase_names = {0: 'QUIET', 1: 'STRESS', 2: 'CRASH', 3: 'RECOVERY'}
    print(f"\n  Phase distribution [test]:")
    for ph, name in phase_names.items():
        n   = (phase[test_mask] == ph).sum()
        pct = n / test_mask.sum() * 100
        print(f"    {name:<12}: n={n:>4}  ({pct:>5.1f}%)")

    # ─────────────────────────────────────────────────────────────────────
    #  COINTEGRATION ANALYSIS  (NEW — validates pairs before trading)
    # ─────────────────────────────────────────────────────────────────────
    print("\n[2]  Cointegration analysis (OLS on TRAIN, out-of-sample spread in TEST) ...")
    print()

    pair_configs = [
        ('P1_ETH_BTC',     'log_eth',         'log_btc',         'ret_eth',         'ETH/BTC'),
        ('P2_ETH_SOL',     'log_eth',         'log_sol',         'ret_eth',         'ETH/SOL'),
        ('P3_ETH_BNB',     'log_eth',         'log_bnb',         'ret_eth',         'ETH/BNB'),
        ('P4_BTC_ALT',     'log_btc',         'log_alt_basket',  'ret_btc',         'BTC/ALT'),
    ]

    coint_params = {}
    spread_z_series = {}
    spread_ret_series = {}

    print(f"  {'Pair':<14}  {'beta':>6}  {'half-life':>10}  {'Z-cross%':>9}  "
          f"{'z_min':>7}  {'z_max':>7}  {'|z|>1%':>7}")
    print("─" * 68)

    for key, col_a, col_b, ret_col, label in pair_configs:
        params = compute_cointegration_params(df[col_a], df[col_b], train_mask)
        coint_params[key] = params

        z_full = compute_spread_zscore(df[col_a], df[col_b], params)
        spread_z_series[key] = z_full

        # Spread return: d(S_t) ≈ ret_A - beta * ret_B
        # Dollar-neutral pair return: (ret_A - beta * ret_B) / (1 + beta)
        beta_ab = params['beta']
        ret_a   = df[ret_col]
        # figure out ret_b from col_b
        b_asset = col_b.replace('log_', 'ret_')
        if b_asset == 'ret_alt_basket':
            ret_b = df['ret_alt_basket']
        else:
            ret_b = df[b_asset]
        spread_ret = (ret_a - beta_ab * ret_b) / (1.0 + abs(beta_ab) + 1e-9)
        spread_ret_series[key] = spread_ret

        z_test = z_full[test_mask]
        hl_str = f"{params['half_life']:.1f}d" if not np.isnan(params['half_life']) else "   inf"
        print(f"  {label:<14}  {params['beta']:>6.3f}  {hl_str:>10}  "
              f"{params['zero_crossings']*100:>8.1f}%  "
              f"{z_test.min():>7.2f}  {z_test.max():>7.2f}  "
              f"{(np.abs(z_test) > 1).mean()*100:>6.1f}%")

    # ─────────────────────────────────────────────────────────────────────
    #  BUILD POSITIONS
    # ─────────────────────────────────────────────────────────────────────
    print("\n[3]  Building positions ...")

    # Setup A: v2 directional baseline (comparison)
    pos_A = setup_a_directional_v2(df, omega_eth, mfls_eth, gamma_eth, phase)

    # Setup D: enhanced with ΔA sizing
    pos_D = setup_d_enhanced(df, omega_eth, mfls_eth, mfls_btc, gamma_eth, gamma_btc, phase)

    # Pairs P1-P4 with spread model
    pair_positions = {}
    for key, col_a, col_b, ret_col, label in pair_configs:
        pair_positions[key] = setup_regime_pairs_v3(
            df, omega_eth, mfls_eth, gamma_eth,
            spread_z_series[key], ret_col, z_threshold=1.0, label=label
        )

    # ─────────────────────────────────────────────────────────────────────
    #  SIMULATE (test 2023→ )
    # ─────────────────────────────────────────────────────────────────────
    print(f"\n[4]  Simulating (test {TEST_START}→2026) ...")

    ret_eth_test = df.loc[test_mask, 'ret_eth']
    fwd21_eth    = df['ret_eth'].rolling(21).sum().shift(-21)

    sims = {}

    # Directional: trade ETH, so use ret_eth
    sims['A_v2_baseline']  = simulate(pos_A[test_mask],  ret_eth_test, label='A_v2_baseline')
    sims['D_delta_a_sized'] = simulate(pos_D[test_mask], ret_eth_test, label='D_delta_a_sized')

    # Pairs: trade spread return of each pair
    for key, col_a, col_b, ret_col, label in pair_configs:
        pos_p  = pair_positions[key]
        s_ret  = spread_ret_series[key]
        sims[key] = simulate(pos_p[test_mask], s_ret[test_mask], label=label)

    # IC
    ic_results = {}
    ic_results['A_v2_baseline']   = ic_metric(pos_A[test_mask],  fwd21_eth[test_mask], 'A_baseline')
    ic_results['D_delta_a_sized'] = ic_metric(pos_D[test_mask],  fwd21_eth[test_mask], 'D_enhanced')
    for key, col_a, col_b, ret_col, label in pair_configs:
        fwd_b = df['ret_eth'].rolling(21).sum().shift(-21) if col_a == 'log_eth' else \
                df['ret_btc'].rolling(21).sum().shift(-21)
        ic_results[key] = ic_metric(pair_positions[key][test_mask], fwd_b[test_mask], label)

    # ─────────────────────────────────────────────────────────────────────
    #  PRINT RESULTS
    # ─────────────────────────────────────────────────────────────────────
    print()
    print(f"── PnL Comparison (test {TEST_START}–2026) ─────────────────────────────")
    print(f"  {'Strategy':<22}  {'Sharpe':>7}  {'Sh/Lev':>7}  {'MaxDD':>7}  "
          f"{'CumRet':>8}  {'TailAcc':>8}  {'Active%':>7}")
    print("─" * 78)
    bh_ref = sims['A_v2_baseline']
    print(f"  {'ETH Buy&Hold':<22}  {bh_ref['bh_sharpe']:>+7.3f}  {'   ---':>7}  "
          f"{bh_ref['bh_max_dd']:>7.3f}  {bh_ref['bh_cum']:>+8.3f}  {'    ---':>8}  {'100.0%':>7}")
    print()
    for name, r in sims.items():
        pct = r['active_days'] / r['total_days'] * 100
        ta  = f"{r['tail_acc']:.3f}" if r['tail_acc'] is not None else "    n/a"
        flag = " ← v2 baseline" if name == 'A_v2_baseline' else ""
        flag = " ← ΔA sizing"   if name == 'D_delta_a_sized' else flag
        print(f"  {name:<22}  {r['sharpe']:>+7.3f}  {r['sharpe_per_lev']:>+7.3f}  "
              f"{r['max_dd']:>7.3f}  {r['cum_return']:>+8.3f}  {ta:>8}  {pct:>6.1f}%{flag}")

    print(f"\n── IC (H=21d) ───────────────────────────────────────────────────────")
    for name, r in ic_results.items():
        ic_s = f"{r['ic']:>+8.4f}" if r['ic'] is not None else "     n/a"
        ac_s = f"{r['acc']:.3f}"   if r['acc'] is not None else "  n/a"
        print(f"  {name:<22}: n={r['n']:>4}  IC={ic_s}  acc={ac_s}")

    # ── Phase-conditional pairs performance ──────────────────────────────
    print(f"\n── Pairs performance by regime [test] ──────────────────────────────")
    print(f"  Best pair candidates: ETH/SOL and BTC/ALT (less hierarchical)")
    print()
    for key, col_a, col_b, ret_col, label in [
        ('P2_ETH_SOL', 'log_eth', 'log_sol', 'ret_eth', 'ETH/SOL'),
        ('P4_BTC_ALT', 'log_btc', 'log_alt_basket', 'ret_btc', 'BTC/ALT'),
    ]:
        pos_p = pair_positions[key]
        s_ret = spread_ret_series[key]
        print(f"  {label}:")
        for ph, pname in phase_names.items():
            ph_mask = (phase == ph) & test_mask
            n       = ph_mask.sum()
            if n < 10:
                continue
            r = simulate(pos_p[ph_mask], s_ret[ph_mask], label=pname)
            active_pct = r['active_days'] / r['total_days'] * 100
            print(f"    {pname:<12}: Sharpe {r['sharpe']:>+6.3f}  "
                  f"MaxDD {r['max_dd']:>7.3f}  active {active_pct:>5.1f}%  n={n}")
        print()

    # ── Spread diagnostic: regime-conditional accuracy ────────────────────
    print(f"── Spread direction accuracy by A-regime (validates the theory) ────")
    print()
    activity = mfls_eth / (gamma_eth + 1e-9)
    a_rank   = activity.expanding(60).rank(pct=True)

    for key, col_a, col_b, ret_col, label in [
        ('P2_ETH_SOL', 'log_eth', 'log_sol', 'ret_eth', 'ETH/SOL'),
        ('P4_BTC_ALT', 'log_btc', 'log_alt_basket', 'ret_btc', 'BTC/ALT'),
    ]:
        z   = spread_z_series[key]
        s_r = spread_ret_series[key]
        print(f"  {label}  (z>1 gate, A-regime split):")
        for a_name, a_lo, a_hi in [('Low A (<Q33)',  0.0,  0.33),
                                    ('Mid A (Q33-Q66)', 0.33, 0.66),
                                    ('High A (>Q66)', 0.66, 1.0)]:
            m = test_mask & (np.abs(z) > 1.0) & (a_rank >= a_lo) & (a_rank < a_hi)
            n = m.sum()
            if n < 5:
                print(f"    {a_name:<20}: n too small")
                continue
            # predicted: revert= -sign(z), continue= +sign(z)
            # forward 5d spread return
            fwd5_s = s_r.rolling(5).sum().shift(-5)
            z_sign = np.sign(z[m])
            fwd_sign = np.sign(fwd5_s[m])
            revert_acc   = ((-z_sign) == fwd_sign).mean()   # fade accuracy
            continue_acc = (  z_sign  == fwd_sign).mean()   # follow accuracy
            print(f"    {a_name:<20}: n={n:>4}  "
                  f"revert_acc={revert_acc:.3f}  continue_acc={continue_acc:.3f}  "
                  f"→ edge={'REVERT' if revert_acc > 0.52 else 'CONTINUE' if continue_acc > 0.52 else 'none'}")
        print()

    # ── Crisis breakdown ──────────────────────────────────────────────────
    crises = {
        '2022_winter':   ('2022-01-01', '2022-12-31'),
        '2023_recovery': ('2023-01-01', '2023-12-31'),
        '2024_bull':     ('2024-01-01', '2024-12-31'),
        '2025_bear':     ('2025-01-01', '2025-12-31'),
    }
    print(f"── Crisis Sharpe: v2_A vs D_enhanced vs best pairs ─────────────────")
    print(f"  {'Period':<18}  {'v2_A':>8}  {'D_enh':>8}  {'ETH/SOL':>9}  {'BTC/ALT':>9}")
    print("─" * 62)
    for cname, (cs, ce) in crises.items():
        cm = (df.index >= cs) & (df.index <= ce)
        if cm.sum() < 10:
            continue
        def sh(pos, ret, mask):
            r  = simulate(pos[mask], ret[mask])
            return f"{r['sharpe']:>+8.3f}"
        va  = sh(pos_A, df['ret_eth'], cm)
        vd  = sh(pos_D, df['ret_eth'], cm)
        p2  = sh(pair_positions['P2_ETH_SOL'], spread_ret_series['P2_ETH_SOL'], cm)
        p4  = sh(pair_positions['P4_BTC_ALT'], spread_ret_series['P4_BTC_ALT'], cm)
        print(f"  {cname:<18}  {va}  {vd}  {p2}  {p4}")

    # ─────────────────────────────────────────────────────────────────────
    #  SAVE RESULTS
    # ─────────────────────────────────────────────────────────────────────
    def _clean(obj):
        if isinstance(obj, dict):
            return {k: _clean(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_clean(v) for v in obj]
        if isinstance(obj, float) and np.isnan(obj):
            return None
        if isinstance(obj, (np.integer, np.floating)):
            return obj.item()
        return obj

    results = {
        "model": "Crypto BSDT v3 — Spread + Ω/A Regime-Conditional Pairs",
        "version": "v3",
        "key_fix": (
            "v2 pairs traded ΔA→direction (volatility asymmetry). "
            "v3 trades spread z-score with A-regime gate: "
            "low A→revert, high A→continue. Correct architecture."
        ),
        "cointegration": {
            k: {
                "beta": round(float(v['beta']), 4),
                "half_life_days": round(float(v['half_life']), 1) if not np.isnan(v['half_life']) else None,
                "zero_crossings": round(v['zero_crossings'], 3),
                "n_train": v['n_train'],
            }
            for k, v in coint_params.items()
        },
        "pnl_results": _clean(sims),
        "ic_results":  _clean(ic_results),
        "crisis_breakdown": {
            cname: {
                "v2_A":    simulate(pos_A[  (df.index >= cs) & (df.index <= ce)],
                                    df.loc[(df.index >= cs) & (df.index <= ce), 'ret_eth'])['sharpe'],
                "D_enh":   simulate(pos_D[  (df.index >= cs) & (df.index <= ce)],
                                    df.loc[(df.index >= cs) & (df.index <= ce), 'ret_eth'])['sharpe'],
                "P2_ETH_SOL": simulate(
                    pair_positions['P2_ETH_SOL'][(df.index >= cs) & (df.index <= ce)],
                    spread_ret_series['P2_ETH_SOL'][(df.index >= cs) & (df.index <= ce)])['sharpe'],
                "P4_BTC_ALT": simulate(
                    pair_positions['P4_BTC_ALT'][(df.index >= cs) & (df.index <= ce)],
                    spread_ret_series['P4_BTC_ALT'][(df.index >= cs) & (df.index <= ce)])['sharpe'],
            }
            for cname, (cs, ce) in crises.items()
            if ((df.index >= cs) & (df.index <= ce)).sum() >= 10
        },
    }

    out_path = f"{OUT_DIR}\\crypto_bsdt_v3_results.json"
    with open(out_path, 'w') as f:
        json.dump(_clean(results), f, indent=2)
    print(f"\n  Results saved → {out_path}")

    # ── Final summary ─────────────────────────────────────────────────────
    print("\n" + "=" * 72)
    print("  SUMMARY")
    print("=" * 72)
    best_sharpe = max(sims.values(), key=lambda r: r['sharpe'])
    best_dd     = min((r for r in sims.values() if r['max_dd'] is not None),
                      key=lambda r: abs(r['max_dd']))
    print(f"  Best Sharpe      : {best_sharpe['label']} ({best_sharpe['sharpe']:+.3f})")
    print(f"  Best MaxDD       : {best_dd['label']} ({best_dd['max_dd']:.3f})")
    print(f"  v2_A (baseline)  : Sharpe {sims['A_v2_baseline']['sharpe']:+.3f}  "
          f"MaxDD {sims['A_v2_baseline']['max_dd']:.3f}")
    print(f"  D_enhanced       : Sharpe {sims['D_delta_a_sized']['sharpe']:+.3f}  "
          f"MaxDD {sims['D_delta_a_sized']['max_dd']:.3f}")
    print()
    print("  Key diagnostic: spread direction accuracy by A-regime")
    print("  → If Low-A revert_acc > 0.52 and High-A continue_acc > 0.52:")
    print("    the regime-conditional framework is validated on crypto.")
    print("=" * 72)


if __name__ == '__main__':
    main()
