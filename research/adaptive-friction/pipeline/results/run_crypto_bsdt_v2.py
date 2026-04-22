"""
Crypto BSDT v2 — Crypto-Native Feature Space
=============================================

Root causes fixed from v1:
  ✗ Ω range was 0.049 (ETH+BTC too correlated → λ_max nearly constant)
  ✗ 21d momentum = noise in crypto (fwd_5d accuracy 48.8%)
  ✗ No crypto-native systemic stress signal (was using generic returns/vol only)

Fixes:
  ✓ 4 assets: BTC, ETH, SOL, BNB → 8×8 correlation matrix → real Ω variation
  ✓ BTC Dominance proxy: btc_rel = ret_btc - mean(ret_eth, ret_sol, ret_bnb)
       rising btc_rel → capital rotating to safety within crypto → systemic stress
  ✓ Crash threshold: 7d return < -10% (crypto 3× more volatile than SP500)
  ✓ Direction: 5d momentum (not 21d — crypto mean-reverts over 21d)
  ✓ Recovery confirm: 3d return > +3%

Feature vector per window (8 features):
  [ret_btc_z, ret_eth_z, ret_sol_z, ret_bnb_z,
   vol_btc_z, vol_eth_z, btc_dom_z, cross_vol_z]
  where:
    btc_dom  = ret_btc - equal_weighted_alt_ret  (dominance proxy)
    cross_vol = std(ret_btc, ret_eth, ret_sol, ret_bnb) daily (dispersion)

Train: 2021-01-01 → 2022-12-31 (crypto winter → real stress regime)
Test:  2023-01-01 → 2026-04-22

Setups compared:
  A. ETH/USD directional     (same as before, now properly calibrated)
  B. ETH/BTC pair            (based on Δ_activity)
  C. Hybrid (corr-switching)
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


# ─────────────────────────────────────────────────────────────────────────────
#  DATA + CRYPTO-NATIVE FEATURES
# ─────────────────────────────────────────────────────────────────────────────
def fetch_and_prepare():
    print("  Fetching BTC, ETH, SOL, BNB...")
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

    # Log-returns
    for a in ['btc','eth','sol','bnb']:
        df[f'ret_{a}'] = np.log(df[a] / df[a].shift(1))

    # ETH/BTC ratio
    df['eth_btc']     = df['eth'] / df['btc']
    df['ret_ethbtc']  = np.log(df['eth_btc'] / df['eth_btc'].shift(1))

    # ── Crypto-native systemic features ───────────────────────────────────
    # 1. BTC Dominance proxy: BTC return minus equally-weighted alt return
    #    Rising → capital rotating to BTC "safety" → systemic stress signal
    df['alt_ret_eq'] = (df['ret_eth'] + df['ret_sol'] + df['ret_bnb']) / 3
    df['btc_dom']    = df['ret_btc'] - df['alt_ret_eq']   # + = BTC leads (stress)

    # 2. Cross-asset dispersion: std of all 4 asset returns daily
    #    High dispersion → intra-crypto divergence → instability building
    df['cross_disp'] = df[['ret_btc','ret_eth','ret_sol','ret_bnb']].std(axis=1)

    # 3. Realised vol (20d rolling std × √252)
    for a in ['btc','eth','sol','bnb']:
        df[f'vol_{a}'] = df[f'ret_{a}'].rolling(20).std() * np.sqrt(252)

    # ── Rolling z-scores (252d, no look-ahead) ────────────────────────────
    def z(s, w=252):
        mu = s.rolling(w, min_periods=60).mean()
        sd = s.rolling(w, min_periods=60).std()
        return (s - mu) / (sd + 1e-9)

    for c in ['ret_btc','ret_eth','ret_sol','ret_bnb',
              'vol_btc','vol_eth','vol_sol','vol_bnb',
              'btc_dom','cross_disp']:
        df[f'{c}_z'] = z(df[c])

    # Momentum signals at multiple horizons
    for h in [3, 5, 7, 14, 21]:
        df[f'ret{h}_eth'] = df['ret_eth'].rolling(h).sum()
        df[f'ret{h}_btc'] = df['ret_btc'].rolling(h).sum()

    df = df.dropna()
    print(f"  Data: {df.index[0].date()} → {df.index[-1].date()}  n={len(df)}")
    return df


# ─────────────────────────────────────────────────────────────────────────────
#  BSDT ENGINE (same as base, but on crypto feature space)
# ─────────────────────────────────────────────────────────────────────────────
def compute_bsdt(df, features, window=60, rho=0.9, ell=1.0):
    X   = df[features].values
    T   = len(X)
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
        lam_max = eigvals[-1]
        v_max   = eigvecs[:, -1]

        omega[t] = rho * ell * lam_max

        mu_wd   = wd.mean(axis=0)
        dist    = np.linalg.norm(X[t] - mu_wd)
        mfls[t] = dist * lam_max

        om_hist  = omega[max(0, t-20):t+1]
        om_hist  = om_hist[np.isfinite(om_hist)]
        om_sm    = om_hist.mean() if len(om_hist) > 0 else omega[t]
        gamma[t] = 1.0 / (1.0 + om_sm)

        dom = np.argmax(np.abs(v_max))
        if v_max[dom] < 0:
            v_max = -v_max
        dirx[t] = v_max[0]   # loading on first feature

    idx = df.index
    return (pd.Series(omega, index=idx, name='omega'),
            pd.Series(mfls,  index=idx, name='mfls'),
            pd.Series(gamma, index=idx, name='gamma'),
            pd.Series(dirx,  index=idx, name='dirx'))


# ─────────────────────────────────────────────────────────────────────────────
#  PHASE DETECTION — CRYPTO RECALIBRATED
# ─────────────────────────────────────────────────────────────────────────────
def detect_phase_crypto(omega, ret7, ret3, btc_dom_z,
                        crash_ret7=-0.10, recov_ret3=0.03):
    """
    Crypto-recalibrated phase detector.

    CRASH:    Ω ≥ Q50  AND  (7d_ret < -10% OR btc_dom_z > 1.5)  AND  3d_ret < 0
              → momentum signal (follow the fall)
    RECOVERY: Ω ≥ Q75  AND  3d_ret > +3%  AND  btc_dom_z < 0.5
              → gradient signal (alt season recovery)
    STRESS:   Ω ≥ Q50, else
    QUIET:    Ω < Q50
    """
    q50    = omega.expanding(60).quantile(0.50)
    q75    = omega.expanding(60).quantile(0.75)
    domega = omega.diff().rolling(3).mean()   # faster smoothing for crypto

    elevated = omega >= q50
    high     = omega >= q75
    rising   = domega > 0

    hard_crash   = (ret7 < crash_ret7)          # 7d return < −10%
    btc_flight   = (btc_dom_z > 1.5)            # BTC dominance spiking → stress
    in_fall      = (ret3 < 0)                   # still falling 3d

    crash_cond   = elevated & (hard_crash | btc_flight) & in_fall

    recov_cond   = high & (ret3 > recov_ret3) & ~crash_cond

    raw = np.ones(len(omega), dtype=int)    # STRESS default
    raw[~elevated.values]     = 0           # QUIET
    raw[crash_cond.values]    = 2           # CRASH
    raw[recov_cond.values]    = 3           # RECOVERY

    return pd.Series(raw, index=omega.index, name='phase')


# ─────────────────────────────────────────────────────────────────────────────
#  POSITIONS
# ─────────────────────────────────────────────────────────────────────────────
def setup_a_directional(df, omega, mfls, gamma, phase):
    """
    ETH/USD directional: w1(Ω) × w2(MFLS/γ) × direction
    Direction in CRASH: short (follow fall) = sign of negative 5d momentum
    Direction in RECOVERY: long (gradient = alts recover vs BTC)
    """
    activity = mfls / (gamma + 1e-9)
    w1 = omega.expanding(60).rank(pct=True)
    w2 = activity.expanding(60).rank(pct=True)

    w1_g = w1.where(w1 >= 0.50, 0.0)
    w2_g = w2.where(w2 >= 0.33, 0.0)

    # Direction: 5-day momentum (not 21d — validated as better for crypto)
    mom5 = np.sign(df['ret5_eth'])

    ph   = phase.values
    d    = np.zeros(len(df))
    d[ph == 2] = mom5.values[ph == 2]   # crash → follow 5d momentum (short during falls)
    d[ph == 3] = 1.0                    # recovery → always long ETH (alts recover)
    d = pd.Series(d, index=df.index)

    pos = d * w1_g * w2_g
    return pos.clip(-1, 1)


def setup_b_relative(df, omega_eth, omega_btc, mfls_eth, mfls_btc,
                      gamma_eth, gamma_btc, omega_joint):
    """
    ETH/BTC pair: ΔMFLS/γ direction + joint Ω gate
    """
    act_eth = mfls_eth / (gamma_eth + 1e-9)
    act_btc = mfls_btc / (gamma_btc + 1e-9)
    delta   = act_eth - act_btc
    drank   = delta.expanding(60).rank(pct=True)

    joint_q50 = omega_joint.expanding(60).quantile(0.50)
    active    = (omega_joint >= joint_q50).astype(float)

    direction = pd.Series(0.0, index=df.index)
    direction[drank >= 0.70] = +1.0   # ETH leads → long ETH/short BTC
    direction[drank <= 0.30] = -1.0   # BTC leads → short ETH/long BTC

    return (direction * active).clip(-1, 1)


def setup_c_hybrid(df, pos_a, pos_b, omega_joint, rolling_corr):
    """
    Hybrid: high coupling → directional, low coupling → pairs
    """
    pos = pd.Series(0.0, index=df.index)
    pa  = pos_a.values
    pb  = pos_b.values
    rc  = rolling_corr.values
    for i in range(len(df)):
        if np.isnan(rc[i]):
            continue
        if rc[i] > 0.80:
            pos.iloc[i] = pa[i]
        elif rc[i] < 0.60:
            pos.iloc[i] = pb[i]
        else:
            pos.iloc[i] = 0.5 * pa[i] + 0.5 * pb[i]
    return pos


# ─────────────────────────────────────────────────────────────────────────────
#  PnL SIMULATION
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


def ic(pos, fwd, label=""):
    nz = (pos != 0) & fwd.notna()
    n  = nz.sum()
    if n < 20:
        return dict(label=label, n=int(n), ic=None, acc=None)
    ic_v, _ = stats.spearmanr(pos[nz].values, fwd[nz].values)
    acc      = (np.sign(pos[nz].values) == np.sign(fwd[nz].values)).mean()
    return dict(label=label, n=int(n), ic=round(float(ic_v), 4), acc=round(float(acc), 3))


# ─────────────────────────────────────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────────────────────────────────────
def main():
    print("=" * 72)
    print("  CRYPTO BSDT v2 — Crypto-Native Features")
    print("  Ω × (MFLS/γ) × Direction (BTC+ETH+SOL+BNB)")
    print("=" * 72)

    df = fetch_and_prepare()

    train_mask = (df.index >= '2021-01-01') & (df.index < '2023-01-01')
    test_mask  = df.index >= '2023-01-01'
    print(f"  Train: {df[train_mask].index[0].date()} → {df[train_mask].index[-1].date()}  n={train_mask.sum()}")
    print(f"  Test:  {df[test_mask].index[0].date()} → {df[test_mask].index[-1].date()}  n={test_mask.sum()}")

    # ── Feature sets ─────────────────────────────────────────────────────
    # Full 8-feature vector: 4 returns + 2 vols + btc_dominance + dispersion
    eth_feats   = ['ret_eth_z','ret_btc_z','ret_sol_z','ret_bnb_z',
                   'vol_eth_z','vol_btc_z','btc_dom_z','cross_disp_z']
    btc_feats   = ['ret_btc_z','ret_eth_z','ret_sol_z','ret_bnb_z',
                   'vol_btc_z','vol_eth_z','btc_dom_z','cross_disp_z']
    joint_feats = ['ret_btc_z','ret_eth_z','ret_sol_z','ret_bnb_z',
                   'vol_btc_z','vol_eth_z','btc_dom_z','cross_disp_z']

    print("\n[1] Computing BSDT metrics (window=60d)...")
    omega_eth, mfls_eth, gamma_eth, dir_eth   = compute_bsdt(df, eth_feats,   window=60)
    omega_btc, mfls_btc, gamma_btc, _         = compute_bsdt(df, btc_feats,   window=60)
    omega_jt,  mfls_jt,  gamma_jt,  _         = compute_bsdt(df, joint_feats, window=60)

    # ── Omega diagnostics ─────────────────────────────────────────────────
    print("\n── Ω diagnostics (vs v1 which had span=0.049) ──────────────────────")
    for name, om in [('ETH (v2)', omega_eth), ('BTC (v2)', omega_btc), ('Joint (v2)', omega_jt)]:
        s = om.dropna()
        span = s.max() - s.min()
        print(f"  {name:<14}: min={s.min():.4f}  median={s.median():.4f}  "
              f"max={s.max():.4f}  span={span:.4f}")

    rolling_corr = df['ret_eth'].rolling(60).corr(df['ret_btc'])
    print(f"\n  Rolling corr(ETH,BTC) [test]: median={rolling_corr[test_mask].median():.3f}")

    # ── Phase detection ───────────────────────────────────────────────────
    print("\n[2] Detecting phases (crypto-recalibrated)...")
    ret7_eth  = df['ret_eth'].rolling(7).sum()
    ret3_eth  = df['ret_eth'].rolling(3).sum()
    phase_eth = detect_phase_crypto(omega_eth, ret7_eth, ret3_eth, df['btc_dom_z'])

    phase_names = {0: 'QUIET', 1: 'STRESS', 2: 'CRASH', 3: 'RECOVERY'}
    print(f"\n  Phase distribution [test 2023+]:")
    for ph, name in phase_names.items():
        n   = (phase_eth[test_mask] == ph).sum()
        pct = n / test_mask.sum() * 100
        print(f"    {name:<12}: n={n:>4}  ({pct:>5.1f}%)")

    # ── Momentum validation at different horizons ─────────────────────────
    print("\n── Direction signal: momentum accuracy by horizon ──────────────────")
    for h in [3, 5, 7, 14, 21]:
        fwd = df['ret_eth'].rolling(h).sum().shift(-h)
        mom = np.sign(df[f'ret{h}_eth'])
        val = (mom != 0) & fwd.notna() & test_mask
        if val.sum() > 0:
            accuracy = (np.sign(mom[val]) == np.sign(fwd[val])).mean()
            print(f"  {h:>2}d momentum → fwd_{h:>2}d  accuracy: {accuracy:.3f}")

    # ── Build positions ───────────────────────────────────────────────────
    print("\n[3] Building positions...")
    pos_a = setup_a_directional(df, omega_eth, mfls_eth, gamma_eth, phase_eth)
    pos_b = setup_b_relative(df, omega_eth, omega_btc, mfls_eth, mfls_btc,
                              gamma_eth, gamma_btc, omega_jt)
    pos_c = setup_c_hybrid(df, pos_a, pos_b, omega_jt, rolling_corr)

    # Crash-only: momentum when crash phase only
    crash_only = pd.Series(
        np.where(phase_eth == 2, np.sign(df['ret5_eth']), 0.0),
        index=df.index).fillna(0)

    # ── Simulate (test only) ──────────────────────────────────────────────
    print("\n[4] Simulating (test 2023-2026)...")
    ret_eth_t    = df.loc[test_mask, 'ret_eth']
    ret_ethbtc_t = df.loc[test_mask, 'ret_ethbtc']
    fwd21_eth    = df['ret_eth'].rolling(21).sum().shift(-21)

    sims = {}
    for name, pos, ret_series in [
        ('A_directional_eth',  pos_a,      ret_eth_t),
        ('B_pairs_eth_btc',    pos_b,      ret_ethbtc_t),
        ('C_hybrid',           pos_c,      ret_eth_t),
        ('crash_only_signal',  crash_only, ret_eth_t),
    ]:
        sims[name] = simulate(pos[test_mask], ret_series, label=name)

    ic_results = {}
    for name, pos in [('A_directional', pos_a), ('B_pairs', pos_b)]:
        ic_results[name] = ic(pos[test_mask], fwd21_eth[test_mask], label=name)

    # ── Print results table ───────────────────────────────────────────────
    print(f"\n── PnL Comparison (test 2023–2026) ──────────────────────────────────")
    print(f"  {'Strategy':<26}  {'Sharpe':>7}  {'Sh/Lev':>7}  {'MaxDD':>7}  "
          f"{'CumRet':>8}  {'TailAcc':>8}  {'Active%':>8}")
    print("─" * 84)
    ref = sims['A_directional_eth']
    print(f"  {'ETH Buy&Hold':<26}  {ref['bh_sharpe']:>+7.3f}  {'---':>7}  "
          f"{ref['bh_max_dd']:>7.3f}  {ref['bh_cum']:>+8.3f}  {'---':>8}  {'100.0%':>8}")
    for name, r in sims.items():
        ap   = r['active_days'] / r['total_days'] * 100
        ta   = f"{r['tail_acc']:.3f}" if r['tail_acc'] is not None else "  n/a"
        print(f"  {name:<26}  {r['sharpe']:>+7.3f}  {r['sharpe_per_lev']:>+7.3f}  "
              f"{r['max_dd']:>7.3f}  {r['cum_return']:>+8.3f}  {ta:>8}  {ap:>7.1f}%")

    # ── IC ────────────────────────────────────────────────────────────────
    print(f"\n── IC (H=21d) ───────────────────────────────────────────────────────")
    for name, r in ic_results.items():
        ic_s = f"{r['ic']:>+8.4f}" if r['ic'] is not None else "     n/a"
        ac_s = f"{r['acc']:.3f}"   if r['acc'] is not None else "  n/a"
        print(f"  {name:<24}: n={r['n']:>4}  IC={ic_s}  acc={ac_s}")

    # ── Activity during crash episodes ────────────────────────────────────
    print(f"\n── Activity A = MFLS/γ by phase [test] ─────────────────────────────")
    act_eth = mfls_eth / (gamma_eth + 1e-9)
    print(f"  {'Phase':<12}  {'n':>5}  {'A_median':>10}  {'A_q90':>8}  {'Ω_median':>10}")
    for ph, name in phase_names.items():
        m = (phase_eth[test_mask] == ph)
        n = m.sum()
        if n == 0: continue
        a_sub = act_eth[test_mask][m]
        o_sub = omega_eth[test_mask][m]
        print(f"  {name:<12}  {n:>5}  {a_sub.median():>10.3f}  "
              f"{a_sub.quantile(0.90):>8.3f}  {o_sub.median():>10.4f}")

    # ── Crisis breakdown ──────────────────────────────────────────────────
    print(f"\n── Crisis period breakdown (Setup A) ────────────────────────────────")
    crises = {
        '2022_winter':   ('2022-01-01', '2022-12-31'),
        '2023_recovery': ('2023-01-01', '2023-12-31'),
        '2024_bull_run': ('2024-01-01', '2024-12-31'),
        '2025_bear':     ('2025-01-01', '2026-04-22'),
    }
    for label, (s, e) in crises.items():
        m = (df.index >= s) & (df.index <= e)
        if m.sum() < 20: continue
        r = simulate(pos_a[m], df.loc[m, 'ret_eth'], label=label)
        print(f"  {label:<20}: Sharpe={r['sharpe']:>+7.3f}  MaxDD={r['max_dd']:>6.3f}  "
              f"BH_Sharpe={r['bh_sharpe']:>+7.3f}  Active={r['active_days']}/{r['total_days']}")

    # ── BTC dominance signal validation ──────────────────────────────────
    print(f"\n── BTC Dominance proxy (btc_dom_z) ─────────────────────────────────")
    dom   = df['btc_dom_z'][test_mask]
    r1    = df['ret_eth'][test_mask].shift(-1).fillna(0)
    high_stress = dom > 1.5
    n_hs  = high_stress.sum()
    if n_hs > 0:
        acc_hs = (r1[high_stress] < 0).mean()   # should be negative (ETH falls)
        print(f"  n days btc_dom_z > 1.5: {n_hs}")
        print(f"  ETH next-day negative when BTC dominance spikes: {acc_hs*100:.1f}%")
    low_dom   = dom < -1.0
    n_ld = low_dom.sum()
    if n_ld > 0:
        acc_ld = (r1[low_dom] > 0).mean()   # ETH rallies when alts lead
        print(f"  n days btc_dom_z < -1.0 (alt season): {n_ld}")
        print(f"  ETH next-day positive when alts leading: {acc_ld*100:.1f}%")

    # ── Save ──────────────────────────────────────────────────────────────
    output = {
        "model": "Crypto BSDT v2 — Crypto-Native Feature Space",
        "version": "v2",
        "features": eth_feats,
        "calibration": {
            "crash_threshold_7d":    -0.10,
            "recovery_confirm_3d":   +0.03,
            "btc_dominance_stress":  1.5,
            "direction_window":      5,
            "omega_gate":            "Q50",
            "activity_gate":         "Q33",
        },
        "fixes_from_v1": [
            "Ω feature space: 8-dimensional (4 assets + vols + BTC dominance + dispersion)",
            "Crash threshold: 7d ret < -10% (was 21d < -3% — too loose for crypto volatility)",
            "Direction: 5d momentum (was 21d — proven noise at fwd_5d accuracy 48.8%)",
            "BTC dominance proxy: btc_rel = ret_btc - mean(ret_alts) feeds into both feature matrix and crash trigger",
            "Recovery: always long ETH (alt-season recovery is directional, not gradient-based)",
        ],
        "pnl_results": sims,
        "ic_results": ic_results,
    }

    out_json = f"{OUT_DIR}/crypto_bsdt_v2_results.json"
    with open(out_json, 'w') as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\n✓ Saved: {out_json}")
    print("\n" + "=" * 72)
    print("  CRYPTO BSDT v2 — COMPLETE")
    print("=" * 72)


if __name__ == '__main__':
    main()
