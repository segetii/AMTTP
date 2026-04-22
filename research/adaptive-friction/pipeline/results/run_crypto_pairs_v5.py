"""
Crypto BSDT v5 — Unified Pair Classifier + Regime Router
=========================================================

Architecture upgrade from v4:

v4 problem:
  × "pair-specific rules" — fragile, not generalizable
  × ΔA too slow (5d diff) — misses fast crypto build-up
  × A conflated two roles: filter + phase detector
  × BTC/ALT treated as spread (wrong physics)

v5 design:
  ✓ Unified 3-class pair taxonomy (daily, mechanical):
      Class A — Equilibrium    : half-life < 7d, β stable  → mean reversion
      Class B — Drifting equil : half-life 7-30d or β drifting → reversion + rolling β
      Class C — Flow system    : half-life > 30d or β unstable  → continuation / macro

  ✓ A split into two roles:
      A_level  → gate: "is system active enough to trade?" (A ≥ Q33)
      ΔA_fast  → phase: "is instability accelerating?"  (1d diff, 2d smooth)

  ✓ BTC/ALT redesigned as dominance rotation macro trade:
      Ω gate + btc_dom_z → long BTC when capital flight
      Ω gate + cross_disp_z → long ALT basket when dispersion rising

  ✓ Routing:
      if Ω < Q50: no trade
      if Ω ≥ Q50 and A_level ≥ Q33:
          if pair_class = A or B: reversion  (rolling β for B)
          if pair_class = C:      continuation (if ΔA_fast rising) else skip

Pairs:
  P1. ETH/BTC     (expect Class A — fast equilibrium)
  P2. ETH/SOL     (expect Class B — drifting equilibrium)
  P3. ETH/BNB     (expect Class B — moderate drift)
  M1. BTC/ALT     (expect Class C — flow, macro rotation redesign)
"""

import numpy as np
import pandas as pd
import json
import warnings
warnings.filterwarnings('ignore')
import yfinance as yf
from numpy.linalg import eigh
from scipy import stats

OUT_DIR     = r"C:\amttp\research\adaptive-friction\pipeline\results"
TRAIN_START = '2021-01-01'
TRAIN_END   = '2022-12-31'
TEST_START  = '2023-01-01'


# ─────────────────────────────────────────────────────────────────────────────
#  DATA
# ─────────────────────────────────────────────────────────────────────────────
def fetch_and_prepare():
    print("  Fetching BTC, ETH, SOL, BNB ...")
    raw = {}
    for tk in ['BTC-USD', 'ETH-USD', 'SOL-USD', 'BNB-USD']:
        raw[tk] = yf.download(tk, start='2020-06-01', progress=False,
                              auto_adjust=True)['Close'].squeeze()
    df = pd.DataFrame({
        'btc': raw['BTC-USD'], 'eth': raw['ETH-USD'],
        'sol': raw['SOL-USD'], 'bnb': raw['BNB-USD'],
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
    for c in ['ret_btc','ret_eth','ret_sol','ret_bnb',
              'vol_btc','vol_eth','btc_dom','cross_disp']:
        df[f'{c}_z'] = z(df[c])
    for h in [3, 5, 7]:
        df[f'ret{h}_eth'] = df['ret_eth'].rolling(h).sum()
        df[f'ret{h}_btc'] = df['ret_btc'].rolling(h).sum()
    df = df.dropna()
    print(f"  Data: {df.index[0].date()} → {df.index[-1].date()}  n={len(df)}")
    return df


# ─────────────────────────────────────────────────────────────────────────────
#  BSDT ENGINE
# ─────────────────────────────────────────────────────────────────────────────
def compute_bsdt(df, features, window=60):
    X = df[features].values
    T = len(X)
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
        omega[t] = 0.9 * lam_max
        mfls[t]  = np.linalg.norm(X[t] - wd.mean(axis=0)) * lam_max
        oh       = omega[max(0, t-20):t+1]
        gamma[t] = 1.0 / (1.0 + oh[np.isfinite(oh)].mean())
    idx = df.index
    return (pd.Series(omega, index=idx),
            pd.Series(mfls,  index=idx),
            pd.Series(gamma, index=idx))


# ─────────────────────────────────────────────────────────────────────────────
#  PHASE
# ─────────────────────────────────────────────────────────────────────────────
def detect_phase(omega, ret7, ret3, btc_dom_z):
    q50   = omega.expanding(60).quantile(0.50)
    q75   = omega.expanding(60).quantile(0.75)
    elev  = omega >= q50
    high  = omega >= q75
    crash = elev & ((ret7 < -0.10) | (btc_dom_z > 1.5)) & (ret3 < 0)
    recov = high & (ret3 > 0.03) & ~crash
    raw   = np.ones(len(omega), dtype=int)
    raw[~elev.values]   = 0
    raw[crash.values]   = 2
    raw[recov.values]   = 3
    return pd.Series(raw, index=omega.index)


# ─────────────────────────────────────────────────────────────────────────────
#  A: LEVEL (filter) vs ΔA_FAST (phase detector)
#  KEY FIX: separate two roles + use 1d diff / 2d smooth
# ─────────────────────────────────────────────────────────────────────────────
def compute_activity_signals(mfls, gamma):
    A       = mfls / (gamma + 1e-9)
    A_rank  = A.expanding(60).rank(pct=True)             # level filter
    dA_fast = A.diff(1).rolling(2).mean()                # fast acceleration (1d diff, 2d smooth)
    dA_rank = dA_fast.expanding(60).rank(pct=True)       # phase detector
    return A, A_rank, dA_fast, dA_rank


# ─────────────────────────────────────────────────────────────────────────────
#  ROLLING SPREAD + HALF-LIFE CLASSIFIER  (NEW in v5)
# ─────────────────────────────────────────────────────────────────────────────
def compute_rolling_spread_and_classifier(log_a, log_b, beta_window=252,
                                           zscore_window=60, half_life_window=60):
    """
    For each day t:
      1. Fit OLS β on trailing beta_window → spread S_t
      2. Compute z-score of S_t over zscore_window
      3. Fit AR(1) on S over half_life_window → rolling half-life
      4. Compute β stability = rolling std of β estimates (60d)

    Returns: z_spread, betas, half_life, beta_stability
    """
    la = log_a.values
    lb = log_b.values
    n  = len(la)
    spread      = np.full(n, np.nan)
    betas       = np.full(n, np.nan)
    half_lives  = np.full(n, np.nan)
    beta_stab   = np.full(n, np.nan)

    for t in range(beta_window, n):
        wla = la[t - beta_window:t]
        wlb = lb[t - beta_window:t]
        X   = np.column_stack([np.ones(beta_window), wlb])
        try:
            coefs        = np.linalg.lstsq(X, wla, rcond=None)[0]
            alpha, beta  = coefs[0], coefs[1]
            spread[t]    = la[t] - alpha - beta * lb[t]
            betas[t]     = beta
        except Exception:
            pass

    # β stability: rolling 60d std of β estimates
    b_ser = pd.Series(betas)
    beta_stab_s = b_ser.rolling(60, min_periods=20).std()

    # Rolling half-life from AR(1) on spread
    S_ser = pd.Series(spread)
    for t in range(half_life_window + beta_window, n):
        S_win = spread[t - half_life_window:t]
        valid = S_win[np.isfinite(S_win)]
        if len(valid) < 30:
            continue
        mu_s = valid.mean()
        dS   = np.diff(valid)
        S_lag = valid[:-1] - mu_s
        if S_lag.std() < 1e-9:
            continue
        try:
            phi = np.corrcoef(S_lag, dS)[0, 1]
            if -1 < phi < 0:
                half_lives[t] = np.log(0.5) / np.log(1 + phi)
        except Exception:
            pass

    # Z-score of spread
    mu_s  = S_ser.rolling(zscore_window, min_periods=30).mean()
    sd_s  = S_ser.rolling(zscore_window, min_periods=30).std()
    z     = (S_ser - mu_s) / (sd_s + 1e-9)

    idx = log_a.index
    return (pd.Series(z.values,         index=idx, name='z'),
            pd.Series(betas,            index=idx, name='beta'),
            pd.Series(half_lives,       index=idx, name='half_life'),
            pd.Series(beta_stab_s.values, index=idx, name='beta_stab'))


def classify_pair_daily(half_life, beta_stab,
                         hl_fast=7.0, hl_slow=30.0, beta_thresh=0.12):
    """
    Daily mechanical classification:
      Class A (equilibrium):         half_life < hl_fast   AND beta_stab < beta_thresh
      Class B (drifting equilibrium): hl_fast ≤ half_life < hl_slow  OR beta_stab moderate
      Class C (flow):                 half_life ≥ hl_slow  OR beta_stab ≥ beta_thresh
    Returns int series: 0=A, 1=B, 2=C
    """
    hl   = half_life.fillna(999)
    bs   = beta_stab.fillna(999)
    cls  = np.ones(len(hl), dtype=int)  # default B
    cls[(hl.values < hl_fast) & (bs.values < beta_thresh)]   = 0  # A
    cls[(hl.values >= hl_slow) | (bs.values >= beta_thresh)] = 2  # C
    return pd.Series(cls, index=half_life.index, name='pair_class')


# ─────────────────────────────────────────────────────────────────────────────
#  POSITIONS — UNIFIED ROUTER
# ─────────────────────────────────────────────────────────────────────────────
def route_pair(omega, A_rank, dA_rank, z_spread, pair_class,
               z_threshold=1.0, label=""):
    """
    Unified routing:
      Gate: Ω ≥ Q50  AND  A_level ≥ Q33  AND  |z| > z_threshold

      Class A/B (equilibrium):    direction = -sign(z)   [revert]
      Class C (flow):             direction = +sign(z)   [continue]
                                  conditional on dA_rank ≥ Q50 (ΔA accelerating)

      Size: min(|z|, 2) / 2
    """
    omega_q50 = omega.expanding(60).quantile(0.50)
    omega_gate = omega >= omega_q50
    active_gate = A_rank >= 0.33
    spread_gate = np.abs(z_spread) > z_threshold
    gate        = omega_gate & active_gate & spread_gate

    pc   = pair_class.values
    z_v  = z_spread.values
    dA_v = dA_rank.values

    direction = np.zeros(len(z_v))
    for i in range(len(z_v)):
        if not gate.iloc[i]:
            continue
        c = pc[i]
        if c == 0 or c == 1:                     # equilibrium → revert
            direction[i] = -np.sign(z_v[i])
        elif c == 2:                              # flow → continue IF ΔA rising
            if np.isfinite(dA_v[i]) and dA_v[i] >= 0.50:
                direction[i] = np.sign(z_v[i])
            # else: no trade (flow without acceleration = noise)

    size = np.minimum(np.abs(z_spread.values), 2.0) / 2.0
    pos  = pd.Series(direction * size, index=omega.index).clip(-1, 1)
    return pos


def route_btcalt_macro(df, omega, A_rank, dA_rank):
    """
    BTC/ALT macro rotation — NOT a spread trade.

    Logic:
      Capital flight (BTC dominance rising):
        btc_dom_z > +1.0 AND Ω ≥ Q50 AND A_rank ≥ Q33
        → trade BTC/USD long (held in BTC position separately)

      Dispersion rising (alt season building):
        btc_dom_z < -1.0 AND cross_disp_z > +1.0 AND Ω ≥ Q50
        → trade ALT basket long (ETH as proxy)

      Size: proportional to |btc_dom_z|, capped at 1.0

    Returns: pos_btc (BTC trade), pos_alt (ALT/ETH trade)
    """
    omega_q50  = omega.expanding(60).quantile(0.50)
    omega_gate = omega >= omega_q50
    active     = A_rank >= 0.33

    dom_z  = df['btc_dom_z']
    disp_z = df['cross_disp_z']

    btc_flight   = omega_gate & active & (dom_z > 1.0)
    alt_season   = omega_gate & active & (dom_z < -1.0) & (disp_z > 1.0)
    # If ΔA accelerating, allow weaker signal
    da_active    = dA_rank >= 0.50
    btc_flight_w = omega_gate & active & da_active & (dom_z > 0.5)
    alt_season_w = omega_gate & active & da_active & (dom_z < -0.5) & (disp_z > 0.5)

    pos_btc = pd.Series(0.0, index=df.index)
    pos_alt = pd.Series(0.0, index=df.index)

    pos_btc[btc_flight]   = np.minimum(dom_z[btc_flight], 2.0) / 2.0
    pos_btc[btc_flight_w & ~btc_flight] = 0.5 * np.minimum(dom_z[btc_flight_w & ~btc_flight], 1.0)
    pos_alt[alt_season]   = 1.0
    pos_alt[alt_season_w & ~alt_season] = 0.5

    return pos_btc.clip(0, 1), pos_alt.clip(0, 1)


def setup_a_directional(df, omega, mfls, gamma, phase):
    """v2 directional baseline — kept for comparison."""
    A    = mfls / (gamma + 1e-9)
    w1   = omega.expanding(60).rank(pct=True)
    w2   = A.expanding(60).rank(pct=True)
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
#  PnL / IC
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
    bh_sh    = (r.mean() / (r.std() + 1e-12)) * np.sqrt(252)
    bh_dd    = (bh / np.maximum.accumulate(bh) - 1).min()
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
    print("  CRYPTO BSDT v5 — Unified Pair Classifier + Regime Router")
    print("  New: daily pair taxonomy (A/B/C) + fast ΔA + BTC/ALT redesigned")
    print("=" * 72)

    df = fetch_and_prepare()
    train_mask = (df.index >= TRAIN_START) & (df.index <= TRAIN_END)
    test_mask  = df.index >= TEST_START
    print(f"  Train: {df[train_mask].index[0].date()} → {df[train_mask].index[-1].date()}")
    print(f"  Test:  {df[test_mask].index[0].date()} → {df[test_mask].index[-1].date()}  n={test_mask.sum()}")

    # ── BSDT ─────────────────────────────────────────────────────────────
    feats = ['ret_eth_z','ret_btc_z','ret_sol_z','ret_bnb_z',
             'vol_eth_z','vol_btc_z','btc_dom_z','cross_disp_z']
    print("\n[1]  Computing BSDT metrics ...")
    omega, mfls_eth, gamma_eth = compute_bsdt(df, feats, window=60)

    # ── Activity: level (filter) vs fast ΔA (phase) ──────────────────────
    print("\n[2]  Computing A_level and ΔA_fast (1d diff, 2d smooth) ...")
    A_eth, A_rank, dA_fast, dA_rank = compute_activity_signals(mfls_eth, gamma_eth)

    # Diagnostic: is fast ΔA cleaner than slow?
    print(f"\n  Fast ΔA diagnostic [test]:")
    for q_lo, q_hi, label in [(0.0, 0.33, 'Low ΔA  (<Q33)'),
                               (0.33, 0.66, 'Mid ΔA  (Q33-Q66)'),
                               (0.66, 1.0,  'High ΔA (>Q66)')]:
        m = test_mask & (dA_rank >= q_lo) & (dA_rank < q_hi)
        a5 = A_eth[m].median()
        o5 = omega[m].median()
        print(f"    {label:<20}: n={m.sum():>4}  A_med={a5:.3f}  Ω_med={o5:.4f}")

    # ── Phase detection ───────────────────────────────────────────────────
    ret7  = df['ret_eth'].rolling(7).sum()
    ret3  = df['ret_eth'].rolling(3).sum()
    phase = detect_phase(omega, ret7, ret3, df['btc_dom_z'])

    # ── Rolling spread + daily pair classification ────────────────────────
    print("\n[3]  Rolling spread computation + daily pair classification ...")
    pairs = [
        ('P1_ETH_BTC', 'log_eth', 'log_btc',         'ret_eth', 'ret_btc'),
        ('P2_ETH_SOL', 'log_eth', 'log_sol',          'ret_eth', 'ret_sol'),
        ('P3_ETH_BNB', 'log_eth', 'log_bnb',          'ret_eth', 'ret_bnb'),
    ]
    pair_data = {}
    for key, col_a, col_b, ret_a, ret_b in pairs:
        print(f"  {key}: ", end='', flush=True)
        z, betas, hl, bstab = compute_rolling_spread_and_classifier(
            df[col_a], df[col_b], beta_window=252, zscore_window=60)
        pair_class = classify_pair_daily(hl, bstab, hl_fast=7.0, hl_slow=30.0, beta_thresh=0.12)
        # Spread return
        b_series  = betas.fillna(betas.median())
        sret      = (df[ret_a] - b_series * df[ret_b]) / (1.0 + b_series.abs() + 1e-9)
        pair_data[key] = dict(z=z, betas=betas, hl=hl, bstab=bstab,
                              pair_class=pair_class, sret=sret,
                              ret_a=ret_a, ret_b=ret_b)

        # Classification summary [test]
        t_cls = pair_class[test_mask]
        n_a   = (t_cls == 0).sum()
        n_b   = (t_cls == 1).sum()
        n_c   = (t_cls == 2).sum()
        hl_med = hl[test_mask].dropna().median()
        bs_med = bstab[test_mask].dropna().median()
        print(f"  hl_med={hl_med:.1f}d  β_stab={bs_med:.3f}  "
              f"[A:{n_a}days B:{n_b}days C:{n_c}days]")

    # ── Build positions ───────────────────────────────────────────────────
    print("\n[4]  Building positions (unified router) ...")
    pos_A_dir = setup_a_directional(df, omega, mfls_eth, gamma_eth, phase)

    pair_positions = {}
    for key, _, _, _, _ in pairs:
        pd_ = pair_data[key]
        pos = route_pair(omega, A_rank, dA_rank, pd_['z'], pd_['pair_class'],
                         z_threshold=1.0, label=key)
        pair_positions[key] = pos

    # BTC/ALT macro rotation (redesigned — two separate trades)
    pos_btc_macro, pos_alt_macro = route_btcalt_macro(df, omega, A_rank, dA_rank)

    # ── Simulate [test] ───────────────────────────────────────────────────
    print(f"\n[5]  Simulating (test {TEST_START}→2026) ...")
    ret_eth = df.loc[test_mask, 'ret_eth']
    ret_btc = df.loc[test_mask, 'ret_btc']
    fwd21   = df['ret_eth'].rolling(21).sum().shift(-21)

    sims = {}
    sims['A_directional'] = simulate(pos_A_dir[test_mask], ret_eth, 'A_directional')
    for key, _, _, _, _ in pairs:
        sims[key] = simulate(pair_positions[key][test_mask],
                             pair_data[key]['sret'][test_mask], key)
    sims['M1_BTC_macro'] = simulate(pos_btc_macro[test_mask], ret_btc, 'M1_BTC_macro')
    sims['M1_ALT_macro'] = simulate(pos_alt_macro[test_mask], ret_eth, 'M1_ALT_macro')

    # Combined portfolio: equal weight active strategies
    pos_combined = (pos_A_dir + pair_positions['P1_ETH_BTC'] +
                    pair_positions['P2_ETH_SOL'] + pos_btc_macro) / 4.0
    sims['COMBINED_4way'] = simulate(
        pos_combined[test_mask],
        ret_eth,   # approximate — ETH as proxy
        'COMBINED_4way')

    ic_res = {}
    ic_res['A_directional'] = ic_metric(pos_A_dir[test_mask], fwd21[test_mask], 'A_dir')
    for key, _, _, _, _ in pairs:
        ic_res[key] = ic_metric(pair_positions[key][test_mask], fwd21[test_mask], key)

    # ── Results table ─────────────────────────────────────────────────────
    print()
    print(f"── PnL (test {TEST_START}–2026)  vs  v4 reference ─────────────────────")
    v4_ref = {'A_directional': 0.535, 'P1_ETH_BTC': 0.758,
              'P2_ETH_SOL_roll': 0.835, 'P3_ETH_BNB': 1.251, 'P4_BTC_ALT': -0.450}
    print(f"  {'Strategy':<22}  {'v4':>6}  {'v5 Sh':>7}  {'Sh/Lev':>7}  "
          f"{'MaxDD':>7}  {'CumRet':>8}  {'TailAcc':>8}  {'Active%':>7}")
    print("─" * 84)
    bhr = sims['A_directional']
    print(f"  {'ETH Buy&Hold':<22}  {'':>6}  {bhr['bh_sharpe']:>+7.3f}  "
          f"{'   ---':>7}  {bhr['bh_max_dd']:>7.3f}  {bhr['bh_cum']:>+8.3f}  "
          f"{'    ---':>8}  {'100.0%':>7}")
    print()
    v4_key_map = {'P2_ETH_SOL': 'P2_ETH_SOL_roll', 'P3_ETH_BNB': 'P3_ETH_BNB'}
    for name, r in sims.items():
        pct   = r['active_days'] / r['total_days'] * 100
        ta    = f"{r['tail_acc']:.3f}" if r['tail_acc'] is not None else "    n/a"
        v4k   = v4_key_map.get(name, name)
        v4_s  = f"{v4_ref[v4k]:>+6.3f}" if v4k in v4_ref else "      "
        delta = ""
        if v4k in v4_ref:
            d = r['sharpe'] - v4_ref[v4k]
            delta = f"  Δ{d:>+.3f}"
        print(f"  {name:<22}  {v4_s}  {r['sharpe']:>+7.3f}  {r['sharpe_per_lev']:>+7.3f}  "
              f"{r['max_dd']:>7.3f}  {r['cum_return']:>+8.3f}  {ta:>8}  {pct:>6.1f}%{delta}")

    print(f"\n── IC (H=21d) ───────────────────────────────────────────────────────")
    for name, r in ic_res.items():
        ic_s = f"{r['ic']:>+8.4f}" if r['ic'] is not None else "     n/a"
        print(f"  {name:<22}: n={r['n']:>4}  IC={ic_s}  acc={r['acc'] if r['acc'] else 'n/a'}")

    # ── Pair classification summary [test] ────────────────────────────────
    print(f"\n── Daily pair classification [test] ─────────────────────────────────")
    print(f"  {'Pair':<14}  {'Class A%':>9}  {'Class B%':>9}  {'Class C%':>9}  "
          f"{'hl_min':>8}  {'hl_med':>8}  {'hl_max':>8}")
    print("─" * 70)
    class_names = {0: 'A(equil)', 1: 'B(drift)', 2: 'C(flow)'}
    for key, _, _, _, _ in pairs:
        pd_ = pair_data[key]
        t_cls = pd_['pair_class'][test_mask]
        hl_t  = pd_['hl'][test_mask].dropna()
        total = len(t_cls)
        pA = (t_cls == 0).sum() / total * 100
        pB = (t_cls == 1).sum() / total * 100
        pC = (t_cls == 2).sum() / total * 100
        hl_mn = hl_t.min() if len(hl_t) > 0 else np.nan
        hl_md = hl_t.median() if len(hl_t) > 0 else np.nan
        hl_mx = hl_t.max() if len(hl_t) > 0 else np.nan
        print(f"  {key:<14}  {pA:>8.1f}%  {pB:>8.1f}%  {pC:>8.1f}%  "
              f"{hl_mn:>8.1f}  {hl_md:>8.1f}  {hl_mx:>8.1f}")

    # ── Theory validation: class-conditional spread accuracy ─────────────
    print(f"\n── Theory validation: reversion accuracy by pair class ──────────────")
    for key, _, _, _, _ in pairs:
        pd_ = pair_data[key]
        z   = pd_['z']
        sr  = pd_['sret']
        fwd5 = sr.rolling(5).sum().shift(-5)
        print(f"  {key}:")
        for cls, cname in class_names.items():
            m = test_mask & (pd_['pair_class'] == cls) & (np.abs(z) > 1.0)
            n = m.sum()
            if n < 10:
                print(f"    {cname:<12}: n too small ({n})")
                continue
            z_sign   = np.sign(z[m])
            fv       = np.sign(fwd5[m].fillna(0))
            rev_acc  = ((-z_sign) == fv).mean()
            cont_acc = (  z_sign  == fv).mean()
            expected = "REVERT" if cls < 2 else "CONTINUE"
            result   = "REVERT" if rev_acc > 0.52 else "CONTINUE" if cont_acc > 0.52 else "mixed"
            match    = "✓" if result == expected else "✗"
            print(f"    {cname:<12}: n={n:>4}  rev={rev_acc:.3f}  cont={cont_acc:.3f}"
                  f"  expected={expected}  got={result}  {match}")
        print()

    # ── BTC/ALT macro: by btc_dom_z regime ───────────────────────────────
    print(f"── BTC/ALT macro rotation analysis [test] ──────────────────────────")
    dom_z = df['btc_dom_z']
    for label, pos, ret_col in [
        ('BTC long (dom_z>1)', pos_btc_macro[test_mask], ret_btc),
        ('ALT long (dom_z<-1)', pos_alt_macro[test_mask], ret_eth),
    ]:
        act = (pos > 0).sum()
        if act < 5:
            print(f"  {label}: too few active days ({act})")
            continue
        r = simulate(pos, ret_col, label)
        print(f"  {label:<28}: Sharpe {r['sharpe']:>+6.3f}  MaxDD {r['max_dd']:>7.3f}  "
              f"active {r['active_days']}/{r['total_days']}")

    # ── Crisis breakdown ──────────────────────────────────────────────────
    crises = {
        '2022_winter':   ('2022-01-01', '2022-12-31'),
        '2023_recovery': ('2023-01-01', '2023-12-31'),
        '2024_bull':     ('2024-01-01', '2024-12-31'),
        '2025_bear':     ('2025-01-01', '2025-12-31'),
    }
    print(f"\n── Crisis Sharpe ────────────────────────────────────────────────────")
    print(f"  {'Period':<18}  {'v2_A':>7}  {'P1_ETH/BTC':>11}  "
          f"{'P2_ETH/SOL':>11}  {'BTC_macro':>10}")
    print("─" * 64)
    def c_sh(pos, ret_s, cs, ce):
        m = (df.index >= cs) & (df.index <= ce)
        if m.sum() < 5: return "    n/a"
        return f"{simulate(pos[m], ret_s[m])['sharpe']:>+7.3f}"
    for cname, (cs, ce) in crises.items():
        va  = c_sh(pos_A_dir, df['ret_eth'], cs, ce)
        p1  = c_sh(pair_positions['P1_ETH_BTC'], pair_data['P1_ETH_BTC']['sret'], cs, ce)
        p2  = c_sh(pair_positions['P2_ETH_SOL'], pair_data['P2_ETH_SOL']['sret'], cs, ce)
        bm  = c_sh(pos_btc_macro, df['ret_btc'], cs, ce)
        print(f"  {cname:<18}  {va}  {p1:>11}  {p2:>11}  {bm:>10}")

    # ─────────────────────────────────────────────────────────────────────
    #  SAVE
    # ─────────────────────────────────────────────────────────────────────
    def _clean(obj):
        if isinstance(obj, dict):   return {k: _clean(v) for k, v in obj.items()}
        if isinstance(obj, list):   return [_clean(v) for v in obj]
        if isinstance(obj, float) and np.isnan(obj): return None
        if isinstance(obj, (np.integer, np.floating)): return obj.item()
        return obj

    # Classify distribution [test]
    class_dist = {}
    for key, _, _, _, _ in pairs:
        t_cls = pair_data[key]['pair_class'][test_mask]
        class_dist[key] = {
            'class_A_pct': round(float((t_cls == 0).mean() * 100), 1),
            'class_B_pct': round(float((t_cls == 1).mean() * 100), 1),
            'class_C_pct': round(float((t_cls == 2).mean() * 100), 1),
            'hl_median':   round(float(pair_data[key]['hl'][test_mask].dropna().median()), 2)
                           if len(pair_data[key]['hl'][test_mask].dropna()) > 0 else None,
        }

    results = {
        "model": "Crypto BSDT v5 — Unified Pair Classifier + Regime Router",
        "version": "v5",
        "architecture": {
            "pair_taxonomy": {
                "Class_A": "fast equilibrium (hl<7d, beta stable) → mean reversion",
                "Class_B": "drifting equilibrium (7d≤hl<30d) → reversion with rolling β",
                "Class_C": "flow system (hl≥30d or beta unstable) → continuation (ΔA gated)",
            },
            "A_split": {
                "A_level":  "filter: is system active? (A ≥ Q33)",
                "dA_fast":  "phase: is instability accelerating? (1d diff, 2d smooth)",
            },
            "BTC_ALT": "redesigned as capital rotation macro trade (not spread)",
        },
        "pair_classification": _clean(class_dist),
        "pnl_results": _clean(sims),
        "ic_results":  _clean(ic_res),
        "crisis_breakdown": _clean({
            cname: {
                "A_dir": simulate(pos_A_dir[(df.index >= cs) & (df.index <= ce)],
                                  df.loc[(df.index >= cs) & (df.index <= ce), 'ret_eth'])['sharpe'],
                "P1":    simulate(pair_positions['P1_ETH_BTC'][(df.index >= cs) & (df.index <= ce)],
                                  pair_data['P1_ETH_BTC']['sret'][(df.index >= cs) & (df.index <= ce)])['sharpe'],
                "P2":    simulate(pair_positions['P2_ETH_SOL'][(df.index >= cs) & (df.index <= ce)],
                                  pair_data['P2_ETH_SOL']['sret'][(df.index >= cs) & (df.index <= ce)])['sharpe'],
                "BTC_macro": simulate(pos_btc_macro[(df.index >= cs) & (df.index <= ce)],
                                      df.loc[(df.index >= cs) & (df.index <= ce), 'ret_btc'])['sharpe'],
            }
            for cname, (cs, ce) in crises.items()
            if ((df.index >= cs) & (df.index <= ce)).sum() >= 10
        }),
        "v4_vs_v5_headline": _clean({
            "P1_ETH_BTC":   {"v4": 0.758,  "v5": sims['P1_ETH_BTC']['sharpe']},
            "P2_ETH_SOL":   {"v4": 0.835,  "v5": sims['P2_ETH_SOL']['sharpe']},
            "P3_ETH_BNB":   {"v4": 1.251,  "v5": sims['P3_ETH_BNB']['sharpe']},
            "BTC_ALT_macro":{"v4_spread": -0.450, "v5_macro": sims['M1_BTC_macro']['sharpe']},
        }),
    }
    out_path = f"{OUT_DIR}\\crypto_bsdt_v5_results.json"
    with open(out_path, 'w') as f:
        json.dump(_clean(results), f, indent=2)
    print(f"\n  Results saved → {out_path}")

    print("\n" + "=" * 72)
    print("  SUMMARY")
    print("=" * 72)
    best = max(sims.values(), key=lambda r: r['sharpe'])
    print(f"  Best Sharpe:  {best['label']} ({best['sharpe']:+.3f})")
    print(f"  v4 → v5 key deltas:")
    print(f"    P1 ETH/BTC : v4 +0.758 → v5 {sims['P1_ETH_BTC']['sharpe']:+.3f}")
    print(f"    P2 ETH/SOL : v4 +0.835 → v5 {sims['P2_ETH_SOL']['sharpe']:+.3f}")
    print(f"    P3 ETH/BNB : v4 +1.251 → v5 {sims['P3_ETH_BNB']['sharpe']:+.3f}")
    print(f"    BTC/ALT    : v4 (spread) -0.450 → v5 (macro) {sims['M1_BTC_macro']['sharpe']:+.3f}")
    print()
    print(f"  Theory: pair classes should predict reversion (A,B) or continuation (C)")
    print("=" * 72)


if __name__ == '__main__':
    main()
