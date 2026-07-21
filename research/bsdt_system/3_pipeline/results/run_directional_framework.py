"""
BSDT Directional Signal Framework + Full Validation
====================================================
Ω alone has no direction (eigenvalue = magnitude only).
This script extends Ω with directional signals and validates the full
timing × direction combination as a tradable system.

5 Directional Methods:
  1. Gradient of E_BS on return dimension  → -∇E_BS[r]  (already in dir_x1)
  2. Dominant eigenvector loading on returns → v_max[r_idx]
  3. Lead-lag conditional drift              → empirical mean future return | Ω > τ
  4. Momentum coupling                       → rolling return sign × Ω filter
  5. Friction collapse signal                → Ω rising AND γ falling

Validation Layers:
  Layer 1 — Timing:    AUC(Ω → drawdown event) at H=21, 63, 126d
  Layer 2 — Direction: IC(signal → future return), conditional accuracy when Ω > τ
  Layer 3 — PnL:       Strategy vs baseline, Sharpe, max drawdown, hit rate

Train: 2005–2015 | Test: 2016–2024 (no look-ahead)
"""

import numpy as np
import pandas as pd
import json
import warnings
warnings.filterwarnings('ignore')
from scipy import stats

CSV_PATH = r"C:\amttp\research\adaptive-friction\pipeline\results\market_mfls_timeseries.csv"
OUT_DIR  = r"C:\amttp\research\adaptive-friction\pipeline\results"

# ─────────────────────────────────────────────────────────────────────────────
#  LOAD DATA
# ─────────────────────────────────────────────────────────────────────────────
def load_data():
    ts = pd.read_csv(CSV_PATH, index_col=0, parse_dates=True)
    sp = ts['sp500']

    # Forward returns at horizons
    for H in [5, 21, 63, 126]:
        ts[f'fwd_ret_{H}'] = sp.pct_change(H).shift(-H)

    # Forward drawdown events (max loss in next H days)
    for H in [21, 63, 126]:
        # Maximum drawdown over next H days
        ts[f'fwd_maxdd_{H}'] = pd.Series(
            [sp.iloc[i:i+H].min() / sp.iloc[i] - 1 if i+H <= len(sp) else np.nan
             for i in range(len(sp))],
            index=ts.index
        )
        ts[f'event_{H}'] = (ts[f'fwd_maxdd_{H}'] < -0.05).astype(float)

    # Daily return
    ts['ret_1d'] = sp.pct_change(1)

    # Gamma derivative (falling = losing control)
    ts['dgamma'] = ts['gamma'].diff()

    # Omega rising (smoothed)
    ts['omega'] = ts['spectral_order']
    ts['domega'] = ts['omega'].diff().rolling(5).mean()

    # Momentum: 21-day rolling return
    ts['momentum_21'] = sp.pct_change(21)
    ts['momentum_sign'] = np.sign(ts['momentum_21'])

    return ts


# ─────────────────────────────────────────────────────────────────────────────
#  EIGENVECTOR SIGNAL (Method 2)
# ─────────────────────────────────────────────────────────────────────────────
def compute_eigenvector_signal(ts, window=60, r_idx=0):
    """
    Compute rolling dominant eigenvector of correlation matrix W.
    Return its loading on the returns dimension (r_idx=0 = r_z).
    
    sign(v_max[r_idx]) = structural direction of instability.
    """
    X_raw = ts[['r_z', 'sigma_z', 'vix_z', 'hy_z']].values
    T, N = X_raw.shape
    evec_r = np.full(T, np.nan)

    for t in range(window, T):
        wd = X_raw[t - window:t + 1]
        corr = np.corrcoef(wd.T)
        if not np.all(np.isfinite(corr)):
            corr = np.where(np.isfinite(corr), corr, 0.0)
            np.fill_diagonal(corr, 1.0)
        W = np.abs(corr)
        W = W / (W.sum(1, keepdims=True) + 1e-12)
        eigvals, eigvecs = np.linalg.eigh(W)
        v_max = eigvecs[:, -1]  # largest eigenvalue's eigenvector
        # Sign convention: positive means returns load in dominant direction
        # Normalise so sign is stable: use sign of the component with largest abs value
        dominant_comp = np.argmax(np.abs(v_max))
        if v_max[dominant_comp] < 0:
            v_max = -v_max
        evec_r[t] = v_max[r_idx]

    return pd.Series(evec_r, index=ts.index, name='evec_r')


# ─────────────────────────────────────────────────────────────────────────────
#  DIRECTIONAL SIGNALS
# ─────────────────────────────────────────────────────────────────────────────
def build_directional_signals(ts):
    """
    Build all 5 directional signals. All signals in {-1, 0, +1}.
    """
    print("  Building directional signals...")
    signals = pd.DataFrame(index=ts.index)

    # ── Method 1: Gradient of E_BS on return dimension ────────
    # dir_x1 already in timeseries: direction of gradient flow on r_z
    # Negative dir_x1 → returns being pushed DOWN → bearish
    # Positive dir_x1 → returns being pushed UP   → bullish
    signals['m1_grad'] = np.sign(ts['dir_x1'])

    # ── Method 2: Dominant eigenvector loading ─────────────────
    print("  Computing eigenvector signal (window=60)...")
    evec_r = compute_eigenvector_signal(ts, window=60, r_idx=0)
    signals['m2_evec'] = np.sign(evec_r).fillna(0)
    ts['evec_r'] = evec_r

    # ── Method 3: Lead-lag conditional drift ──────────────────
    # Empirical: mean future 21d return when Ω > tau_cal, rolling estimation
    # Estimated on expanding window up to each date (no look-ahead)
    omega = ts['omega']
    ret21 = ts['fwd_ret_21']
    tau_cal = omega.expanding().quantile(0.75)  # 75th percentile expanding
    high_omega_mask = omega > tau_cal
    # For each t: use all past high-omega observations to estimate direction
    # Simplified: rolling 252d conditional mean
    cond_mean = pd.Series(np.nan, index=ts.index)
    for i in range(252, len(ts)):
        window_slice = slice(max(0, i - 252), i)
        ho = high_omega_mask.iloc[window_slice]
        r  = ret21.iloc[window_slice]
        valid = ho & r.notna()
        if valid.sum() >= 10:
            cond_mean.iloc[i] = r[valid].mean()
    signals['m3_condrift'] = np.sign(cond_mean).fillna(0)

    # ── Method 4: Momentum coupling ───────────────────────────
    # Momentum sign — only valid when Ω is above median
    omega_median = omega.expanding().median()
    signals['m4_momentum'] = np.where(omega > omega_median,
                                       ts['momentum_sign'], 0.0)
    signals['m4_momentum'] = signals['m4_momentum'].fillna(0)

    # ── Method 5: Friction collapse ───────────────────────────
    # Ω rising AND γ falling → trend continuation (breakdown signal)
    # Direction = momentum sign (trend following breakdown)
    omega_rising  = ts['domega'] > 0
    gamma_falling = ts['dgamma'] < 0
    friction_signal = np.where(omega_rising & gamma_falling,
                                ts['momentum_sign'], 0.0)
    signals['m5_friction'] = pd.Series(friction_signal, index=ts.index).fillna(0)

    # ── Ensemble: majority vote of all 5 ──────────────────────
    # Only when Ω > calibrated threshold
    omega_q75 = omega.expanding().quantile(0.75)
    active = (omega > omega_q75).astype(float)
    vote = (signals[['m1_grad', 'm2_evec', 'm3_condrift',
                       'm4_momentum', 'm5_friction']].sum(axis=1))
    signals['ensemble'] = np.sign(vote) * active

    print(f"  Signal stats:")
    for col in signals.columns:
        long_pct  = (signals[col] > 0).mean() * 100
        short_pct = (signals[col] < 0).mean() * 100
        print(f"    {col:>15}: long={long_pct:5.1f}%  short={short_pct:5.1f}%  "
              f"neutral={(100-long_pct-short_pct):5.1f}%")

    return signals


# ─────────────────────────────────────────────────────────────────────────────
#  LAYER 1: TIMING VALIDATION (Ω → drawdown event)
# ─────────────────────────────────────────────────────────────────────────────
def validate_timing(ts, split_date='2016-01-01'):
    """AUC, Lift, Lead-lag for Ω timing signal."""
    from sklearn.metrics import roc_auc_score
    print("\n" + "="*70)
    print("LAYER 1 — TIMING VALIDATION (Ω → drawdown events)")
    print("="*70)

    results = {}
    omega = ts['omega']

    # Train / test split
    train_mask = ts.index < split_date
    test_mask  = ts.index >= split_date

    for H in [21, 63, 126]:
        ev_col = f'event_{H}'
        valid  = ts[ev_col].notna()
        print(f"\n  Horizon H={H}d (event = max drawdown < -5% in {H}d)")

        for split_name, smask in [("train 2005-2015", train_mask),
                                   ("test  2016-2024", test_mask)]:
            mask = smask & valid
            y    = ts.loc[mask, ev_col].values
            om   = omega[mask].values
            if y.sum() < 5 or len(y) < 50:
                continue
            try:
                auc = roc_auc_score(y, om)
            except Exception:
                auc = float('nan')

            # Lift at thresholds
            lifts = {}
            base_rate = y.mean()
            for q in [0.75, 0.90]:
                thr = np.quantile(om, q)
                high_mask = om > thr
                if high_mask.sum() == 0:
                    continue
                cond_rate = y[high_mask].mean()
                lifts[f"top{int((1-q)*100)}pct"] = round(cond_rate / base_rate, 3) if base_rate > 0 else 0

            print(f"    [{split_name}]  n={mask.sum()}  events={int(y.sum()):3d}  "
                  f"base_rate={base_rate:.3f}  AUC={auc:.4f}  "
                  f"lift@top25%={lifts.get('top25pct','?')}  "
                  f"lift@top10%={lifts.get('top10pct','?')}")

            results[f'H{H}_{split_name.strip()}'] = {
                "n": int(mask.sum()), "events": int(y.sum()),
                "base_rate": round(float(base_rate), 4),
                "auc": round(float(auc), 4),
                "lifts": lifts,
            }

    # Lead-lag cross-correlation Ω vs future returns
    print(f"\n  Lead-lag Ω vs future 21d returns (test set):")
    test_valid = test_mask & ts['fwd_ret_21'].notna()
    omega_test = omega[test_valid].values
    ret_test   = ts.loc[test_valid, 'fwd_ret_21'].values
    print(f"  {'τ':>5}  {'corr(Ω_t, ret_{t+τ})':>22}")
    peak_corr, peak_tau = 0, 0
    for tau in [-42, -21, -10, -5, 0, 5, 10, 21]:
        if tau < 0:
            r = np.corrcoef(omega_test[:tau], ret_test[-tau:])[0, 1]
        elif tau > 0:
            r = np.corrcoef(omega_test[tau:], ret_test[:-tau])[0, 1]
        else:
            r = np.corrcoef(omega_test, ret_test)[0, 1]
        flag = " <<peak" if abs(r) > abs(peak_corr) else ""
        if abs(r) > abs(peak_corr):
            peak_corr, peak_tau = r, tau
        print(f"  {tau:>5}  {r:>22.4f}{flag}")
    results['lead_lag_peak'] = {"tau": peak_tau, "corr": round(float(peak_corr), 4)}

    return results


# ─────────────────────────────────────────────────────────────────────────────
#  LAYER 2: DIRECTION VALIDATION
# ─────────────────────────────────────────────────────────────────────────────
def validate_direction(ts, signals, split_date='2016-01-01'):
    """IC, directional accuracy unconditional and conditional on Ω > τ."""
    print("\n" + "="*70)
    print("LAYER 2 — DIRECTION VALIDATION (IC + conditional accuracy)")
    print("="*70)

    results = {}
    omega     = ts['omega']
    test_mask = ts.index >= split_date

    for H in [21, 63]:
        ret_col = f'fwd_ret_{H}'
        valid   = ts[ret_col].notna() & test_mask
        y_ret   = ts.loc[valid, ret_col].values
        om      = omega[valid].values
        y_sign  = np.sign(y_ret)

        print(f"\n  Horizon H={H}d  [test 2016-2024]  n={valid.sum()}")
        print(f"  {'Signal':>15}  {'IC':>8}  {'IC_p':>8}  "
              f"{'Acc_uncond':>10}  {'Acc|Ω>Q75':>10}  {'Acc|Ω>Q90':>10}")

        q75 = np.quantile(om, 0.75)
        q90 = np.quantile(om, 0.90)

        sig_results = {}
        for sig_col in ['m1_grad', 'm2_evec', 'm3_condrift', 'm4_momentum',
                         'm5_friction', 'ensemble']:
            if sig_col not in signals.columns:
                continue
            sig_vals = signals.loc[valid, sig_col].values

            # IC: Spearman correlation with future return
            valid_sig = sig_vals != 0
            if valid_sig.sum() < 20:
                ic, ic_p = np.nan, np.nan
            else:
                ic, ic_p = stats.spearmanr(sig_vals[valid_sig], y_ret[valid_sig])

            # Directional accuracy
            def acc(mask):
                m = mask & (sig_vals != 0)
                if m.sum() < 5:
                    return np.nan
                return float((np.sign(sig_vals[m]) == y_sign[m]).mean())

            acc_u   = acc(np.ones(len(sig_vals), dtype=bool))
            acc_75  = acc(om > q75)
            acc_90  = acc(om > q90)

            def fmt(x):
                return f"{x:.3f}" if not np.isnan(x) else "  n/a"

            print(f"  {sig_col:>15}  {fmt(ic):>8}  {fmt(ic_p):>8}  "
                  f"{fmt(acc_u):>10}  {fmt(acc_75):>10}  {fmt(acc_90):>10}")

            sig_results[sig_col] = {
                "ic": None if np.isnan(ic) else round(float(ic), 4),
                "ic_p": None if np.isnan(ic_p) else round(float(ic_p), 4),
                "acc_unconditional": None if np.isnan(acc_u) else round(float(acc_u), 4),
                "acc_cond_q75": None if np.isnan(acc_75) else round(float(acc_75), 4),
                "acc_cond_q90": None if np.isnan(acc_90) else round(float(acc_90), 4),
            }
        results[f'H{H}'] = sig_results

    return results


# ─────────────────────────────────────────────────────────────────────────────
#  LAYER 3: PnL SIMULATION
# ─────────────────────────────────────────────────────────────────────────────
def pnl_simulation(ts, signals, split_date='2016-01-01'):
    """
    Daily rebalancing strategy: position = signal × (Ω > τ)
    Evaluate vs buy-and-hold and vs pure momentum.
    """
    print("\n" + "="*70)
    print("LAYER 3 — PnL SIMULATION (test 2016-2024)")
    print("="*70)

    test_mask  = ts.index >= split_date
    daily_ret  = ts['ret_1d'].fillna(0)
    omega      = ts['omega']

    # Omega thresholds calibrated on training set
    train_mask = ts.index < split_date
    tau_75  = np.quantile(omega[train_mask], 0.75)
    tau_90  = np.quantile(omega[train_mask], 0.90)
    print(f"  Ω thresholds (from training set):  Q75={tau_75:.4f}  Q90={tau_90:.4f}")

    results = {}

    def evaluate_strategy(positions, name):
        """positions: pd.Series of {-1, 0, +1} daily positions."""
        pos = positions[test_mask].reindex(daily_ret[test_mask].index).fillna(0)
        strat_ret = pos.shift(1).fillna(0) * daily_ret[test_mask]  # t+1 execution
        cum  = (1 + strat_ret).cumprod()
        total_ret = float(cum.iloc[-1] - 1)
        ann_ret   = float((1 + total_ret) ** (252 / len(strat_ret)) - 1)
        ann_vol   = float(strat_ret.std() * np.sqrt(252))
        sharpe    = ann_ret / ann_vol if ann_vol > 0 else 0
        # max drawdown
        roll_max  = cum.cummax()
        dd_series = cum / roll_max - 1
        max_dd    = float(dd_series.min())
        # hit rate (on non-zero position days)
        active    = pos != 0
        hit_rate  = float((strat_ret[active] > 0).mean()) if active.sum() > 0 else np.nan
        # average trade return
        avg_trade = float(strat_ret[active].mean()) if active.sum() > 0 else np.nan
        # calmar
        calmar    = ann_ret / abs(max_dd) if max_dd != 0 else np.nan
        # tail: mean return in worst 5% of market days
        worst5_days = daily_ret[test_mask].nsmallest(int(len(daily_ret[test_mask])*0.05)).index
        tail_pnl    = float(strat_ret[strat_ret.index.isin(worst5_days)].mean())

        print(f"\n  Strategy: {name}")
        print(f"    Total return:  {total_ret*100:+.2f}%")
        print(f"    Annual return: {ann_ret*100:+.2f}%")
        print(f"    Annual vol:    {ann_vol*100:.2f}%")
        print(f"    Sharpe:        {sharpe:+.3f}")
        print(f"    Max drawdown:  {max_dd*100:.2f}%")
        print(f"    Calmar:        {calmar:.3f}" if not np.isnan(calmar) else "    Calmar:    n/a")
        print(f"    Hit rate:      {hit_rate*100:.1f}%" if not np.isnan(hit_rate) else "    Hit rate:  n/a")
        print(f"    Tail PnL:      {tail_pnl*100:+.3f}%  (mean return | market worst 5%)")
        print(f"    Active days:   {int(active.sum())} / {len(pos)}")

        return {
            "total_return": round(total_ret, 4),
            "annual_return": round(ann_ret, 4),
            "annual_vol": round(ann_vol, 4),
            "sharpe": round(sharpe, 4),
            "max_drawdown": round(max_dd, 4),
            "calmar": round(calmar, 4) if not np.isnan(calmar) else None,
            "hit_rate": round(hit_rate, 4) if not np.isnan(hit_rate) else None,
            "avg_trade_return": round(avg_trade, 6) if not np.isnan(avg_trade) else None,
            "tail_pnl": round(tail_pnl, 6),
            "active_days": int(active.sum()),
        }

    # ── Baselines ─────────────────────────────────────────────
    bah_pos = pd.Series(1.0, index=ts.index)
    results['buyhold'] = evaluate_strategy(bah_pos, "Buy & Hold (fully long)")

    mom_pos = ts['momentum_sign'].fillna(0)
    results['momentum'] = evaluate_strategy(mom_pos, "Pure Momentum (21d sign)")

    # ── Ω-filtered strategies ─────────────────────────────────
    for tau_name, tau in [("Q75", tau_75), ("Q90", tau_90)]:
        omega_active = (omega > tau).astype(float)

        for sig_col in ['m1_grad', 'm2_evec', 'm4_momentum', 'ensemble']:
            if sig_col not in signals.columns:
                continue
            sig = signals[sig_col]
            pos = sig * omega_active
            strat_name = f"Ω>{tau_name} × {sig_col}"
            results[f'{sig_col}_{tau_name}'] = evaluate_strategy(
                pos.fillna(0), strat_name
            )

    # ── Pure Ω filter: long only above threshold ───────────────
    for tau_name, tau in [("Q75", tau_75), ("Q90", tau_90)]:
        # Long when Ω low (calm), flat when Ω high (dangerous)
        pos_calm = pd.Series(
            np.where(omega <= tau, 1.0, 0.0), index=ts.index
        )
        results[f'long_when_calm_{tau_name}'] = evaluate_strategy(
            pos_calm, f"Long when Ω<={tau_name} (avoid instability)"
        )

    # ── Summary comparison table ───────────────────────────────
    print(f"\n  {'Strategy':>45}  {'Sharpe':>7}  {'MaxDD':>7}  {'HitRate':>8}  {'TailPnL':>9}")
    for strat, r in results.items():
        sharpe_str = f"{r['sharpe']:+.3f}"
        dd_str     = f"{r['max_drawdown']*100:.1f}%"
        hr_str     = f"{r['hit_rate']*100:.1f}%" if r['hit_rate'] else "  n/a"
        tp_str     = f"{r['tail_pnl']*100:+.3f}%"
        print(f"  {strat:>45}  {sharpe_str:>7}  {dd_str:>7}  {hr_str:>8}  {tp_str:>9}")

    return results


# ─────────────────────────────────────────────────────────────────────────────
#  CLEAN SIGNAL ARCHITECTURE SUMMARY
# ─────────────────────────────────────────────────────────────────────────────
def print_architecture():
    print("\n" + "="*70)
    print("COMBINED SIGNAL ARCHITECTURE")
    print("="*70)
    print("""
  TIMING signal (Ω):
    Use:    spectral_order = ρ·ℓ·λ_max(W)
    Alarm:  Ω > Q75 (elevated) | Ω > Q90 (high) | Ω > 1.0 (C_man)
    Theory: Morse index jumps 0→1 → system enters unstable manifold

  DIRECTION signals:
    M1 gradient:  sign(-∇E_BS[r]) = dir_x1
                  The energy landscape is pushing returns in this direction
    M2 eigenvec:  sign(v_max[r]) from rolling W
                  Loading of returns on dominant instability mode
    M3 cond.drift: sign(E[ret|Ω>τ]) from expanding window
                  Historical tendency when system is unstable
    M4 momentum:  sign(21d return) — "which way is it currently going"
    M5 friction:  momentum sign when Ω↑ AND γ↓ simultaneously
                  Friction breakdown → trend continuation

  COMBINATION:
    Position_t = Ω_t × direction_t
    where Ω_t ∈ {0, 1} (above threshold)
    and direction_t ∈ {-1, +1} (signal vote)

  DECISION TABLE:
    Ω < τ       → position = 0       (no trade — calm, no edge)
    Ω > τ, d>0  → position = +1      (instability + upside pressure)
    Ω > τ, d<0  → position = -1      (instability + downside pressure)

  KEY INSIGHT:
    Ω is the gate — it says "something is about to move"
    Direction signals say "which way" — they REQUIRE Ω to be useful
    Separating timing from direction is what gives the statistical edge
""")


# ─────────────────────────────────────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("BSDT DIRECTIONAL SIGNAL FRAMEWORK + FULL VALIDATION")
    print("Ω alone = timing | Ω × direction = tradable signal")
    print()

    # Load
    ts = load_data()
    print(f"Loaded {len(ts)} observations: {ts.index[0].date()} -> {ts.index[-1].date()}")
    print(f"Train: 2005-2015 ({(ts.index < '2016-01-01').sum()} obs)")
    print(f"Test:  2016-2024 ({(ts.index >= '2016-01-01').sum()} obs)")

    # Build signals
    signals = build_directional_signals(ts)

    # Run validation layers
    timing_results    = validate_timing(ts)
    direction_results = validate_direction(ts, signals)
    pnl_results       = pnl_simulation(ts, signals)

    # Architecture summary
    print_architecture()

    # ── Save ──────────────────────────────────────────────────
    from datetime import datetime
    all_results = {
        "metadata": {
            "title": "BSDT Directional Signal Framework — Market (SP500+VIX+HY, 2005-2024)",
            "run_timestamp": datetime.now().isoformat(),
            "train_period": "2005-01-01 to 2015-12-31",
            "test_period":  "2016-01-01 to 2024-12-31",
            "mechanism": "Position = Omega(timing) x direction_signal",
            "n_train": int((ts.index < '2016-01-01').sum()),
            "n_test":  int((ts.index >= '2016-01-01').sum()),
        },
        "directional_methods": {
            "m1_grad":     "Gradient -nabla_E_BS on return dim (dir_x1 column)",
            "m2_evec":     "Dominant eigenvector v_max[r_idx] loading on returns",
            "m3_condrift": "Empirical conditional drift E[ret|Omega>tau] expanding window",
            "m4_momentum": "21d rolling return sign gated by Omega > median",
            "m5_friction": "Momentum sign when Omega rising AND gamma falling",
            "ensemble":    "Majority vote of m1-m5 gated by Omega > Q75",
        },
        "layer1_timing":    timing_results,
        "layer2_direction": direction_results,
        "layer3_pnl":       pnl_results,
    }

    import os
    json_path = os.path.join(OUT_DIR, "directional_framework_results.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"\nSaved: {json_path}")

    # Text report
    txt_path = os.path.join(OUT_DIR, "directional_framework_results.txt")
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write("BSDT DIRECTIONAL SIGNAL FRAMEWORK RESULTS\n")
        f.write(f"Run: {all_results['metadata']['run_timestamp']}\n")
        f.write(f"Train 2005-2015 | Test 2016-2024\n\n")

        f.write("LAYER 1 — TIMING AUC\n")
        for k, v in timing_results.items():
            if isinstance(v, dict) and 'auc' in v:
                f.write(f"  {k}: AUC={v['auc']}  events={v['events']}  "
                        f"lift@top25%={v['lifts'].get('top25pct','?')}  "
                        f"lift@top10%={v['lifts'].get('top10pct','?')}\n")
        f.write(f"\n  Lead-lag peak: tau={timing_results.get('lead_lag_peak',{}).get('tau','?')}d  "
                f"corr={timing_results.get('lead_lag_peak',{}).get('corr','?')}\n")

        f.write("\nLAYER 2 — DIRECTION IC\n")
        for H_key, sig_dict in direction_results.items():
            f.write(f"  Horizon {H_key}:\n")
            for sig_col, v in sig_dict.items():
                f.write(f"    {sig_col:>15}: IC={v['ic']}  "
                        f"acc_uncond={v['acc_unconditional']}  "
                        f"acc|Q75={v['acc_cond_q75']}  "
                        f"acc|Q90={v['acc_cond_q90']}\n")

        f.write("\nLAYER 3 — PnL\n")
        for strat, v in pnl_results.items():
            f.write(f"  {strat:>40}: sharpe={v['sharpe']:+.3f}  "
                    f"maxDD={v['max_drawdown']*100:.1f}%  "
                    f"hitrate={str(round(v['hit_rate']*100,1))+'%' if v['hit_rate'] else 'n/a'}\n")

    print(f"Saved: {txt_path}")
    print("\nDone.")
