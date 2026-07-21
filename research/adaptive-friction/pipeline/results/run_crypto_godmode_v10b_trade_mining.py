"""
Crypto Godmode v10b — Trade Data Mining / False-Break Analysis
==============================================================

Reads the v10 clustered trade CSV and adds path-dependent trade diagnostics:

  - MFE / MAE from intratrade OHLC path
  - profit/loss attribution by cluster and asset
  - "right but reverted" / false-break classification
  - stop-loss vs take-profit behavior

Definitions:
  MFE = max favorable excursion during trade
  MAE = max adverse excursion during trade

  false_break:
      net loser that moved at least 50% of its TP distance in the right
      direction, then reverted and closed <= 0.

  hard_false_break:
      net loser that moved at least 75% of its TP distance in the right
      direction, then reverted and closed <= 0.

  clean_loss:
      net loser with MFE < 25% of TP distance; it was wrong immediately.

  clean_win:
      net winner with MFE >= TP distance or TP exit.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from run_crypto_pairs_v34_full_combined import OUT_DIR
from run_crypto_godmode_v8_multiasset_shell import fetch_futures_ohlcv_symbol


OUT_DIR_ = Path(OUT_DIR)
TRADES_CSV = OUT_DIR_ / "crypto_godmode_v10_cluster_trades.csv"
OUT_CSV = OUT_DIR_ / "crypto_godmode_v10b_trade_mining.csv"
OUT_JSON = OUT_DIR_ / "crypto_godmode_v10b_trade_mining.json"
BAR = "=" * 116


def _excursions(row: pd.Series, ohlc: pd.DataFrame) -> dict:
    entry_t = pd.Timestamp(row["entry_time"])
    exit_t = pd.Timestamp(row["exit_time"])
    entry = float(row["entry_price"])
    direction = int(row["direction"])
    path = ohlc[(ohlc.index >= entry_t) & (ohlc.index <= exit_t)]
    if path.empty:
        return dict(mfe=0.0, mae=0.0, close_path_ret=0.0, bars_seen=0)

    if direction > 0:
        fav = path["high"] / entry - 1.0
        adv = path["low"] / entry - 1.0
        close_path_ret = float(path["close"].iloc[-1] / entry - 1.0)
    else:
        fav = entry / path["low"] - 1.0
        adv = entry / path["high"] - 1.0
        close_path_ret = float(entry / path["close"].iloc[-1] - 1.0)

    return dict(
        mfe=float(fav.max()),
        mae=float(adv.min()),
        close_path_ret=close_path_ret,
        bars_seen=int(len(path)),
    )


def enrich_trades(df: pd.DataFrame) -> pd.DataFrame:
    ohlc_map = {sym: fetch_futures_ohlcv_symbol(sym) for sym in sorted(df["symbol"].unique())}
    rows = []
    for _, row in df.iterrows():
        ex = _excursions(row, ohlc_map[row["symbol"]])
        rows.append(ex)
    ex_df = pd.DataFrame(rows)
    out = pd.concat([df.reset_index(drop=True), ex_df], axis=1)

    tp_dist = out["take_distance"].astype(float).clip(lower=1e-9)
    sl_dist = out["stop_distance"].astype(float).clip(lower=1e-9)
    out["mfe_to_tp"] = out["mfe"] / tp_dist
    out["mae_to_sl"] = out["mae"].abs() / sl_dist
    out["gave_back_pct"] = (out["mfe"] - out["net_pnl_pct"] / 100.0).clip(lower=0.0)
    out["gave_back_of_mfe"] = np.where(out["mfe"] > 1e-9, out["gave_back_pct"] / out["mfe"], 0.0)

    net = out["net_pnl_pct"].astype(float)
    out["is_profit"] = net > 0
    out["is_loss"] = net <= 0
    out["false_break"] = (out["is_loss"] & (out["mfe_to_tp"] >= 0.50))
    out["hard_false_break"] = (out["is_loss"] & (out["mfe_to_tp"] >= 0.75))
    out["clean_loss"] = (out["is_loss"] & (out["mfe_to_tp"] < 0.25))
    out["clean_win"] = (out["is_profit"] & ((out["mfe_to_tp"] >= 1.0) | (out["exit_reason"] == "tp")))
    out["scratch_revert"] = (out["is_loss"] & (out["mfe_to_tp"].between(0.25, 0.50, inclusive="left")))

    def label(r):
        if r["clean_win"]:
            return "clean_win"
        if r["hard_false_break"]:
            return "hard_false_break"
        if r["false_break"]:
            return "false_break"
        if r["scratch_revert"]:
            return "scratch_revert"
        if r["clean_loss"]:
            return "clean_loss"
        if r["is_profit"]:
            return "small_win"
        return "other_loss"

    out["trade_archetype"] = out.apply(label, axis=1)
    return out


def _group_summary(df: pd.DataFrame, by: list[str]) -> list[dict]:
    rows = []
    for key, g in df.groupby(by):
        if not isinstance(key, tuple):
            key = (key,)
        d = {name: val for name, val in zip(by, key)}
        d.update(dict(
            n=int(len(g)),
            win_pct=float(g["is_profit"].mean()),
            avg_net=float(g["net_pnl_pct"].mean()),
            sum_net=float(g["net_pnl_pct"].sum()),
            sum_k=float(g["k_scaled_pnl_pct"].sum()),
            avg_mfe=float(g["mfe"].mean()),
            avg_mae=float(g["mae"].mean()),
            avg_mfe_to_tp=float(g["mfe_to_tp"].mean()),
            false_break_pct=float(g["false_break"].mean()),
            hard_false_break_pct=float(g["hard_false_break"].mean()),
            clean_loss_pct=float(g["clean_loss"].mean()),
            clean_win_pct=float(g["clean_win"].mean()),
            stop_pct=float((g["exit_reason"] == "stop").mean()),
            tp_pct=float((g["exit_reason"] == "tp").mean()),
            trail_pct=float((g["exit_reason"] == "trail_exit").mean()),
        ))
        rows.append(d)
    return rows


def print_cluster_mining(cluster_rows: list[dict]):
    print(f"\n  {'C':>2} {'N':>5} {'Win%':>6} {'AvgNet%':>9} {'SumK%':>9} {'MFE/TP':>7} "
          f"{'False%':>7} {'HardFB%':>8} {'CleanLoss%':>10} {'CleanWin%':>9} {'Stop%':>7} {'TP%':>7}")
    print("  " + "─" * 112)
    for r in sorted(cluster_rows, key=lambda x: x["cluster"]):
        print(f"  {int(r['cluster']):>2} {r['n']:>5} {r['win_pct']:>5.1%} {r['avg_net']:>+8.3f}% "
              f"{r['sum_k']:>+8.2f}% {r['avg_mfe_to_tp']:>7.2f} {r['false_break_pct']:>6.1%} "
              f"{r['hard_false_break_pct']:>7.1%} {r['clean_loss_pct']:>9.1%} {r['clean_win_pct']:>8.1%} "
              f"{r['stop_pct']:>6.1%} {r['tp_pct']:>6.1%}")


def main():
    t0 = time.time()
    print(BAR)
    print("  CRYPTO GODMODE v10b — TRADE DATA MINING / FALSE-BREAK ANALYSIS")
    print(BAR)
    if not TRADES_CSV.exists():
        raise FileNotFoundError(f"Missing {TRADES_CSV}; run run_crypto_godmode_v10_cluster.py first")

    print(f"\n[1] Loading clustered trades: {TRADES_CSV}")
    df = pd.read_csv(TRADES_CSV, parse_dates=["entry_time", "exit_time"])
    print(f"  rows={len(df):,} OOS={(df['is_oos'] == 1).sum():,}")

    print("\n[2] Computing intratrade MFE/MAE from futures OHLC ...")
    enriched = enrich_trades(df)
    oos = enriched[enriched["is_oos"] == 1].copy()

    cluster_rows = _group_summary(oos, ["cluster"])
    asset_rows = _group_summary(oos, ["asset"])
    archetype_rows = _group_summary(oos, ["trade_archetype"])
    cluster_asset_rows = _group_summary(oos, ["cluster", "asset"])

    print(f"\n{BAR}")
    print("  CLUSTER PROFIT / LOSS / FALSE-BREAK ATTRIBUTION")
    print(BAR)
    print_cluster_mining(cluster_rows)

    print("\n  Archetype attribution:")
    print(f"  {'archetype':<18} {'N':>5} {'Win%':>6} {'AvgNet%':>9} {'SumK%':>9} {'MFE/TP':>7}")
    print("  " + "─" * 70)
    for r in sorted(archetype_rows, key=lambda x: x["sum_k"]):
        print(f"  {r['trade_archetype']:<18} {r['n']:>5} {r['win_pct']:>5.1%} {r['avg_net']:>+8.3f}% "
              f"{r['sum_k']:>+8.2f}% {r['avg_mfe_to_tp']:>7.2f}")

    print("\n  Asset attribution:")
    for r in sorted(asset_rows, key=lambda x: x["sum_k"], reverse=True):
        print(f"    {r['asset'].upper():<3}: n={r['n']:>4} win={r['win_pct']:.1%} avgNet={r['avg_net']:+.3f}% "
              f"sumK={r['sum_k']:+.2f}% false={r['false_break_pct']:.1%} cleanLoss={r['clean_loss_pct']:.1%}")

    worst_false = sorted(cluster_asset_rows, key=lambda x: x["false_break_pct"] * x["n"], reverse=True)[:8]
    print("\n  Highest false-break cluster×asset pockets:")
    for r in worst_false:
        print(f"    C{int(r['cluster'])}-{str(r['asset']).upper():<3}: n={r['n']:>4} false={r['false_break_pct']:.1%} "
              f"hard={r['hard_false_break_pct']:.1%} avgNet={r['avg_net']:+.3f}% sumK={r['sum_k']:+.2f}%")

    worst_loss = sorted(cluster_asset_rows, key=lambda x: x["sum_k"])[:8]
    print("\n  Worst cluster×asset PnL pockets:")
    for r in worst_loss:
        print(f"    C{int(r['cluster'])}-{str(r['asset']).upper():<3}: n={r['n']:>4} win={r['win_pct']:.1%} "
              f"avgNet={r['avg_net']:+.3f}% sumK={r['sum_k']:+.2f}% false={r['false_break_pct']:.1%}")

    best_profit = sorted(cluster_asset_rows, key=lambda x: x["sum_k"], reverse=True)[:8]
    print("\n  Best cluster×asset PnL pockets:")
    for r in best_profit:
        print(f"    C{int(r['cluster'])}-{str(r['asset']).upper():<3}: n={r['n']:>4} win={r['win_pct']:.1%} "
              f"avgNet={r['avg_net']:+.3f}% sumK={r['sum_k']:+.2f}% cleanWin={r['clean_win_pct']:.1%}")

    enriched.to_csv(OUT_CSV, index=False)
    payload = dict(
        meta=dict(version="godmode_v10b_trade_mining", false_break="loss with MFE >= 50% TP distance",
                  hard_false_break="loss with MFE >= 75% TP distance", elapsed=time.time() - t0),
        cluster=cluster_rows,
        asset=asset_rows,
        archetype=archetype_rows,
        cluster_asset=cluster_asset_rows,
    )
    with open(OUT_JSON, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, default=float)
    print(f"\n  Saved enriched trades → {OUT_CSV}")
    print(f"  Saved report → {OUT_JSON}")
    print(f"  elapsed={time.time()-t0:.1f}s")
    print(BAR)


if __name__ == "__main__":
    main()