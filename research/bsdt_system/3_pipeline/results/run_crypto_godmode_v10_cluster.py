"""
Crypto Godmode v10 — Trade Clustering for v9 Multi-Asset Champion
=================================================================

Clusters every trade from the v9 practical champion:

  signal        = Godmode v_anneal w_star
  assets        = BTCUSDT + ETHUSDT + SOLUSDT
  ZE7 threshold = 0.150
  Q multiplier  = 1.00
  allocation    = 1/3 per asset
  CB            = 8% halt / 1% resume / 180d

The goal is to identify which entry regimes/trade patterns drive the edge and
which patterns create drawdown, now that the old multi-asset execution shell has
been rebuilt around the canonical signal.
"""
from __future__ import annotations

import os
import sys
import json
import time
import warnings
from collections import deque
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler

os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")
warnings.filterwarnings("ignore")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, r"C:\amttp\research\adaptive-friction")

from run_crypto_pairs_v34_full_combined import OUT_DIR, TEST_START, TRAIN_START, build_1h_df
from run_crypto_canonical_v4 import _stats
from run_crypto_godmode_v1 import KAPPA_A, W_TARGET_A1, build_w_star, build_b_aligned, calibrate, run_godmode_sweep
from test_psi_adaptive_y import BASE
from test_daily_geometry_stop_tp_ohlc import get_channel_series
from simulate_master_strategy import (
    INIT,
    RT_COST,
    FUND_HOURLY,
    DYN_K,
    DYN_DD_SOFT,
    DYN_DD_STOP,
    DYN_Y_FLOOR,
    simulate_combined,
    equity_metrics,
)
from simulate_v63_quadrant import CB_HALT, CB_RESUME, CB_WINDOW_DAYS, ZE7_MIN_FORCE
from run_crypto_godmode_v8_multiasset_shell import ASSETS, fetch_futures_ohlcv_symbol, build_asset_inputs
from run_crypto_godmode_v9_multiasset_tune import attach_q_hot


OUT_DIR_ = Path(OUT_DIR)
BAR = "=" * 116
TEST_TS = pd.Timestamp(TEST_START)

CHAMPION_ZE7 = 0.150
CHAMPION_QBOOST = 1.00
CHAMPION_ALLOC = 1.0 / 3.0


def _with_champion_size(p: dict) -> dict:
    out = dict(p)
    q_hot = np.asarray(p.get("q_hot", np.zeros(len(p["psi_y"]), dtype=bool)), dtype=bool)
    out["q_mult_custom"] = np.where(q_hot, CHAMPION_QBOOST, 1.0)
    out["psi_y"] = np.asarray(p["psi_y"], dtype=float) * out["q_mult_custom"] * CHAMPION_ALLOC
    return out


def simulate_records_ze7(asset: str,
                         symbol: str,
                         p: dict,
                         ch: dict) -> tuple[pd.Series, list[dict], dict]:
    """Per-asset OHLC simulator with trade records and ZE7 entry gate."""
    op = p["op"]; hi = p["hi"]; lo = p["lo"]; cl = p["cl"]
    hpos_arr = p["hpos"]; dpos_arr = p["dpos"]; dactive_arr = p["dactive"]
    psi_y = np.asarray(p["psi_y"], dtype=float)
    hours = p["hours"]
    ze7_arr = np.asarray(p["ze7"], dtype=float)
    q_mult = np.asarray(p.get("q_mult_custom", np.ones(len(hours))), dtype=float)
    sl = BASE["sl_mult"] * p["daily_vol"]
    tp = BASE["tp_mult"] * p["daily_vol"]
    trail_trigger = 1.5 * p["daily_vol"]
    trail_dist = 0.75 * p["daily_vol"]

    zE7 = ch["E7"].reindex(hours, method="ffill").shift(1).fillna(0.0)
    zdG = ch["dG"].reindex(hours, method="ffill").shift(1).fillna(0.0)
    zE6 = ch["E6"].reindex(hours, method="ffill").shift(1).fillna(0.0)
    zdT = ch["dT"].reindex(hours, method="ffill").shift(1).fillna(0.0)

    cl_s = pd.Series(cl.astype(float), index=hours)
    ret_24h = cl_s.pct_change(24).fillna(0.0).values
    ret_7d = cl_s.pct_change(168).fillna(0.0).values
    vol_24h = np.log(cl_s / cl_s.shift(1)).rolling(24).std().fillna(0.0).values * np.sqrt(24 * 365.25)

    n = len(op)
    ret = np.zeros(n, dtype=float)
    pos = 0.0; size = 1.0; entry = 0.0
    stop_px = 0.0; take_px = 0.0
    trail_active = False; trail_ext = 0.0
    cur: dict | None = None
    trades: list[dict] = []
    counts = dict(entries=0, exits=0, longs=0, shorts=0, stop=0, tp=0,
                  trail_exit=0, signal_exit=0, close_end=0, vetoed_force=0,
                  skipped_daily_filter=0, active_hours=0)

    for i in range(n):
        hpos = int(hpos_arr[i]); hactive = hpos != 0
        dpos = int(dpos_arr[i]); dact = bool(dactive_arr[i])
        scale = float(psi_y[i])

        if hactive:
            if dact and hpos == dpos:
                pass
            elif dact and hpos != dpos:
                hactive = False; hpos = 0; counts["skipped_daily_filter"] += 1
            else:
                scale *= 0.5
        if hactive and scale <= 1e-12:
            hactive = False; hpos = 0

        if pos != 0:
            counts["active_hours"] += 1
            exit_ret = None; reason = None
            if pos > 0:
                if hi[i] >= take_px:
                    exit_ret = take_px / entry - 1.0; reason = "tp"
                else:
                    trail_ext = max(trail_ext, hi[i])
                    if trail_ext / entry - 1.0 >= trail_trigger:
                        trail_active = True
                    if trail_active:
                        stop_px = max(stop_px, trail_ext * (1.0 - trail_dist))
                    if lo[i] <= stop_px:
                        exit_ret = stop_px / entry - 1.0
                        reason = "trail_exit" if trail_active else "stop"
            else:
                if lo[i] <= take_px:
                    exit_ret = entry / take_px - 1.0; reason = "tp"
                else:
                    trail_ext = min(trail_ext, lo[i])
                    if entry / trail_ext - 1.0 >= trail_trigger:
                        trail_active = True
                    if trail_active:
                        stop_px = min(stop_px, trail_ext * (1.0 + trail_dist))
                    if hi[i] >= stop_px:
                        exit_ret = entry / stop_px - 1.0
                        reason = "trail_exit" if trail_active else "stop"

            if exit_ret is None and hactive and hpos == -pos:
                exit_ret = (op[i] / entry - 1.0) if pos > 0 else (entry / op[i] - 1.0)
                reason = "signal_exit"

            if exit_ret is not None:
                net = float(exit_ret) - RT_COST
                ret[i] += size * net
                counts[reason] += 1; counts["exits"] += 1
                if cur is not None:
                    cur.update(dict(
                        exit_time=hours[i], holding_bars=i - cur["_bar"],
                        gross_pnl_pct=float(exit_ret) * 100.0,
                        net_pnl_pct=net * 100.0,
                        scaled_pnl_pct=size * net * 100.0,
                        k_scaled_pnl_pct=DYN_K * size * net * 100.0,
                        exit_reason=reason,
                        was_winner=int(net > 0),
                        trail_active_at_exit=int(trail_active),
                    ))
                    trades.append(cur); cur = None
                pos = 0.0; size = 1.0; entry = 0.0
                stop_px = 0.0; take_px = 0.0; trail_active = False; trail_ext = 0.0
            else:
                ret[i] -= size * FUND_HOURLY

        if pos == 0 and hactive:
            if abs(ze7_arr[i]) < CHAMPION_ZE7:
                counts["vetoed_force"] += 1
                continue
            ts = hours[i]
            pos = float(hpos); size = float(scale); entry = float(op[i]); trail_ext = entry; trail_active = False
            if pos > 0:
                stop_px = entry * (1.0 - sl); take_px = entry * (1.0 + tp); counts["longs"] += 1
            else:
                stop_px = entry * (1.0 + sl); take_px = entry * (1.0 - tp); counts["shorts"] += 1
            counts["entries"] += 1
            cur = dict(
                _bar=i, asset=asset, symbol=symbol, entry_time=ts, is_oos=int(ts >= TEST_TS),
                direction=int(pos), size=float(size), psi_y=float(psi_y[i]), q_mult=float(q_mult[i]),
                entry_price=float(entry), stop_distance=float(sl), take_distance=float(tp),
                zE7=float(zE7.iloc[i]), zdG=float(zdG.iloc[i]), zE6=float(zE6.iloc[i]), zdT=float(zdT.iloc[i]),
                abs_zE7=abs(float(zE7.iloc[i])), abs_zdG=abs(float(zdG.iloc[i])),
                abs_zE6=abs(float(zE6.iloc[i])), abs_zdT=abs(float(zdT.iloc[i])),
                channel_mag=(abs(float(zE7.iloc[i])) + abs(float(zdG.iloc[i])) + abs(float(zE6.iloc[i])) + abs(float(zdT.iloc[i]))) / 4.0,
                asset_ret_24h=float(ret_24h[i]), asset_ret_7d=float(ret_7d[i]), asset_annvol_24h=float(vol_24h[i]),
                hour=ts.hour, dow=ts.dayofweek, month=ts.month,
                hour_sin=np.sin(2 * np.pi * ts.hour / 24), hour_cos=np.cos(2 * np.pi * ts.hour / 24),
                dow_sin=np.sin(2 * np.pi * ts.dayofweek / 7), dow_cos=np.cos(2 * np.pi * ts.dayofweek / 7),
                month_sin=np.sin(2 * np.pi * ts.month / 12), month_cos=np.cos(2 * np.pi * ts.month / 12),
            )

    if pos != 0:
        i = n - 1
        gross = (cl[i] / entry - 1.0) if pos > 0 else (entry / cl[i] - 1.0)
        net = gross - RT_COST
        ret[i] += size * net
        counts["close_end"] += 1; counts["exits"] += 1
        if cur is not None:
            cur.update(dict(exit_time=hours[i], holding_bars=i - cur["_bar"], gross_pnl_pct=gross * 100.0,
                            net_pnl_pct=net * 100.0, scaled_pnl_pct=size * net * 100.0,
                            k_scaled_pnl_pct=DYN_K * size * net * 100.0, exit_reason="close_end",
                            was_winner=int(net > 0), trail_active_at_exit=int(trail_active)))
            trades.append(cur)

    return pd.Series(ret, index=hours), trades, counts


def add_cb_context(trades: pd.DataFrame, unit_sum: pd.Series) -> pd.DataFrame:
    """Replay combined CB engine and attach equity state at each entry."""
    window_bars = CB_WINDOW_DAYS * 24
    mono: deque = deque()
    eq = INIT; peak = INIT; halted = False
    eq_map = {}; ath_dd_map = {}; cb_dd_map = {}; y_map = {}; halted_map = {}
    for i, ur in enumerate(unit_sum.values):
        while mono and mono[0][0] <= i - window_bars:
            mono.popleft()
        while mono and mono[-1][1] <= eq:
            mono.pop()
        mono.append((i, eq))
        roll_peak = mono[0][1]
        ath_dd = max(0.0, 1.0 - eq / max(peak, 1e-12))
        cb_dd = max(0.0, 1.0 - eq / max(roll_peak, 1e-12))
        if not halted and cb_dd >= CB_HALT:
            halted = True
        elif halted and cb_dd <= CB_RESUME:
            halted = False
        if halted:
            y = 0.0
        elif ath_dd <= DYN_DD_SOFT:
            y = 1.0
        elif ath_dd >= DYN_DD_STOP:
            y = DYN_Y_FLOOR
        else:
            y = DYN_Y_FLOOR + (1.0 - DYN_Y_FLOOR) * (DYN_DD_STOP - ath_dd) / (DYN_DD_STOP - DYN_DD_SOFT)
        eq *= 1.0 + max(DYN_K * y * float(ur), -0.95)
        peak = max(peak, eq)
        ts = unit_sum.index[i]
        eq_map[ts] = eq; ath_dd_map[ts] = ath_dd; cb_dd_map[ts] = cb_dd; y_map[ts] = y; halted_map[ts] = int(halted)
    out = trades.copy()
    out["eq_at_entry"] = out["entry_time"].map(eq_map).fillna(INIT)
    out["ath_dd_at_entry"] = out["entry_time"].map(ath_dd_map).fillna(0.0)
    out["cb_dd_at_entry"] = out["entry_time"].map(cb_dd_map).fillna(0.0)
    out["y_at_entry"] = out["entry_time"].map(y_map).fillna(1.0)
    out["cb_halted_at_entry"] = out["entry_time"].map(halted_map).fillna(0)
    return out


def cluster_trades(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    work = df[df["is_oos"] == 1].copy()
    asset_dummies = pd.get_dummies(work["asset"], prefix="asset", dtype=float)
    base_features = work[[
        "direction", "size", "psi_y", "q_mult",
        "zE7", "zdG", "zE6", "zdT", "abs_zE7", "abs_zdG", "abs_zE6", "abs_zdT", "channel_mag",
        "asset_ret_24h", "asset_ret_7d", "asset_annvol_24h",
        "hour_sin", "hour_cos", "dow_sin", "dow_cos", "month_sin", "month_cos",
        "ath_dd_at_entry", "cb_dd_at_entry", "y_at_entry",
    ]].astype(float)
    feat = pd.concat([base_features, asset_dummies], axis=1).fillna(0.0)
    X = StandardScaler().fit_transform(feat.values)
    pca_full = PCA().fit(X)
    cum = np.cumsum(pca_full.explained_variance_ratio_)
    n_pca = min(int(np.argmax(cum >= 0.90)) + 1, 12, X.shape[1])
    Xp = PCA(n_components=n_pca, random_state=42).fit_transform(X)

    km_results = {}
    sample = min(len(Xp), 2000)
    for k in range(3, 9):
        km = KMeans(n_clusters=k, random_state=42, n_init=30, max_iter=500)
        labels = km.fit_predict(Xp)
        sil = silhouette_score(Xp, labels, sample_size=sample, random_state=42)
        km_results[k] = (sil, labels)
    best_k = max(km_results, key=lambda k: km_results[k][0])
    work["cluster"] = km_results[best_k][1]
    work["pc1"] = Xp[:, 0]; work["pc2"] = Xp[:, 1]
    meta = dict(best_k=best_k, silhouette=float(km_results[best_k][0]), n_pca=n_pca,
                explained_90=float(cum[n_pca - 1]), features=list(feat.columns))
    return work, meta


def main():
    t0 = time.time()
    OUT_DIR_.mkdir(parents=True, exist_ok=True)
    print(BAR)
    print("  CRYPTO GODMODE v10 — TRADE CLUSTERING FOR v9 CHAMPION")
    print(BAR)

    print("\n[1] Loading data and rebuilding v9 champion signals ...")
    df, has_sol = build_1h_df(start="2021-01-01", end="2026-05-01")
    train_mask = np.asarray((df.index >= TRAIN_START) & (df.index < TEST_START))
    test_mask = np.asarray(df.index >= TEST_START)
    ohlc_map = {symbol: fetch_futures_ohlcv_symbol(symbol) for _, symbol, _, _ in ASSETS}
    ch = get_channel_series()
    w_star = build_w_star(df, W_TARGET=W_TARGET_A1)
    b_aligned = build_b_aligned(w_star)
    Sigma_f, theta, diag = calibrate(df, train_mask, w_star, b_aligned, kappa=KAPPA_A, label="v10")
    log_ann = run_godmode_sweep(df, train_mask, test_mask, w_star, b_aligned, Sigma_f, theta,
                                kappa=KAPPA_A, anneal=True, label="v10_anneal")
    inputs_noq = build_asset_inputs(df, log_ann, w_star, ch, ohlc_map, signal_kind="wstar", use_quadrant=False)
    inputs_q = build_asset_inputs(df, log_ann, w_star, ch, ohlc_map, signal_kind="wstar", use_quadrant=True)
    inputs = attach_q_hot(inputs_noq, inputs_q)

    print("\n[2] Simulating v9 champion and recording trades ...")
    all_trades: list[dict] = []
    unit_sum: pd.Series | None = None
    counts = {}
    for asset, symbol, _, _ in ASSETS:
        p = _with_champion_size(inputs[asset])
        unit, trades, cnt = simulate_records_ze7(asset, symbol, p, ch)
        unit_sum = unit if unit_sum is None else unit_sum.add(unit, fill_value=0.0)
        all_trades.extend(trades)
        counts[asset] = cnt
        print(f"  {asset.upper()}: trades={len(trades):,} entries={cnt['entries']:,} veto={cnt['vetoed_force']:,} "
              f"tp={cnt['tp']:,} stop={cnt['stop']:,} trail={cnt['trail_exit']:,}")
    assert unit_sum is not None
    unit_sum = unit_sum.sort_index().fillna(0.0)
    zero = pd.Series(np.zeros(len(unit_sum)), index=unit_sum.index)
    eq_res = simulate_combined(unit_sum, zero, K_normal=DYN_K, K_crash=0.0,
                               dd_soft=DYN_DD_SOFT, dd_stop=DYN_DD_STOP, y_floor=DYN_Y_FLOOR,
                               cb_halt=CB_HALT, cb_resume=CB_RESUME, cb_window_days=CB_WINDOW_DAYS, use_cb=True)
    trades_df = pd.DataFrame(all_trades).drop(columns=["_bar"], errors="ignore")
    trades_df = add_cb_context(trades_df, unit_sum)

    print("\n[3] Clustering OOS trades ...")
    clustered, meta = cluster_trades(trades_df)
    print(f"  OOS trades={len(clustered):,} best_k={meta['best_k']} silhouette={meta['silhouette']:+.4f} n_pca={meta['n_pca']}")

    print(f"\n{BAR}")
    print("  CLUSTER SUMMARY — OOS TRADES")
    print(BAR)
    summary_rows = []
    header = (f"  {'C':>2} {'N':>5} {'Win%':>6} {'AvgNet%':>9} {'SumK%':>9} {'AvgH':>7} "
              f"{'Long%':>6} {'BTC%':>6} {'ETH%':>6} {'SOL%':>6} {'zE7':>7} {'zdG':>7} "
              f"{'Vol':>7} {'DD@E':>7} {'ExitMode':>12}")
    print(header); print("  " + "─" * 112)
    for c in sorted(clustered["cluster"].unique()):
        g = clustered[clustered["cluster"] == c]
        row = dict(
            cluster=int(c), n=int(len(g)), win=float(g["was_winner"].mean()),
            avg_net=float(g["net_pnl_pct"].mean()), sum_k=float(g["k_scaled_pnl_pct"].sum()),
            avg_hold=float(g["holding_bars"].mean()), long_pct=float((g["direction"] > 0).mean()),
            btc_pct=float((g["asset"] == "btc").mean()), eth_pct=float((g["asset"] == "eth").mean()),
            sol_pct=float((g["asset"] == "sol").mean()), mean_zE7=float(g["zE7"].mean()),
            mean_zdG=float(g["zdG"].mean()), mean_vol=float(g["asset_annvol_24h"].mean()),
            mean_dd=float(g["ath_dd_at_entry"].mean()), exit_mode=str(g["exit_reason"].value_counts().idxmax()),
        )
        summary_rows.append(row)
        print(f"  {row['cluster']:>2} {row['n']:>5} {row['win']:>5.1%} {row['avg_net']:>+8.3f}% "
              f"{row['sum_k']:>+8.2f}% {row['avg_hold']:>6.1f} {row['long_pct']:>5.1%} "
              f"{row['btc_pct']:>5.1%} {row['eth_pct']:>5.1%} {row['sol_pct']:>5.1%} "
              f"{row['mean_zE7']:>+6.3f} {row['mean_zdG']:>+6.3f} {row['mean_vol']:>6.2f} "
              f"{row['mean_dd']:>6.2%} {row['exit_mode']:>12}")

    worst = min(summary_rows, key=lambda r: r["avg_net"])
    best = max(summary_rows, key=lambda r: r["avg_net"])
    print(f"\n  Best cluster : C{best['cluster']} avgNet={best['avg_net']:+.3f}% sumK={best['sum_k']:+.2f}% n={best['n']}")
    print(f"  Worst cluster: C{worst['cluster']} avgNet={worst['avg_net']:+.3f}% sumK={worst['sum_k']:+.2f}% n={worst['n']}")

    print("\n  Equity check:")
    m = equity_metrics(eq_res["eq"][eq_res["eq"].index >= TEST_TS], "v10_cluster_replay")
    print(f"    final=${m['final']:,.2f} CAGR={m['cagr']:+.2%} Sharpe={m['sharpe']:+.3f} MaxDD={m['maxdd']:+.2%} Calmar={m['calmar']:+.3f}")

    out_csv = OUT_DIR_ / "crypto_godmode_v10_cluster_trades.csv"
    clustered.to_csv(out_csv, index=False)
    payload = dict(
        meta=dict(version="godmode_v10_cluster", champion=dict(ze7=CHAMPION_ZE7, qboost=CHAMPION_QBOOST, alloc=CHAMPION_ALLOC),
                  cluster=meta, theta=diag["theta"], elapsed=time.time() - t0),
        equity=equity_metrics(eq_res["eq"][eq_res["eq"].index >= TEST_TS]),
        counts=counts,
        summary=summary_rows,
        best_cluster=best,
        worst_cluster=worst,
        continuous_reference=_stats(log_ann["pnl"].iloc[test_mask]),
    )
    out_json = OUT_DIR_ / "crypto_godmode_v10_cluster.json"
    with open(out_json, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, default=float)
    print(f"\n  Saved trades → {out_csv}")
    print(f"  Saved report → {out_json}")
    print(f"  elapsed={time.time()-t0:.1f}s")
    print(BAR)


if __name__ == "__main__":
    main()