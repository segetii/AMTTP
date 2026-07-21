from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


ASSETS = ["eth", "btc", "sol"]


def _zscore(s: pd.Series, win: int) -> pd.Series:
    mu = s.rolling(win, min_periods=win).mean()
    sd = s.rolling(win, min_periods=win).std()
    return (s - mu) / (sd + 1e-9)


def _annualize_factor() -> float:
    return np.sqrt(24.0 * 365.25)


def equity_metrics(eq: pd.Series) -> dict:
    r = eq.pct_change().fillna(0.0)
    dd = (eq / eq.cummax()) - 1.0
    years = max((eq.index[-1] - eq.index[0]).days / 365.25, 1e-9)
    cagr = float((eq.iloc[-1] / eq.iloc[0]) ** (1.0 / years) - 1.0)
    sharpe = float(_annualize_factor() * r.mean() / (r.std() + 1e-12))
    maxdd = float(dd.min())
    calmar = float(cagr / max(abs(maxdd), 1e-9))
    return {
        "start": str(eq.index[0]),
        "end": str(eq.index[-1]),
        "final": float(eq.iloc[-1]),
        "return_pct": float(eq.iloc[-1] / eq.iloc[0] - 1.0),
        "cagr": cagr,
        "sharpe": sharpe,
        "maxdd": maxdd,
        "calmar": calmar,
    }


def build_signals(df: pd.DataFrame, feature_lag: int = 1) -> pd.DataFrame:
    out = pd.DataFrame(index=df.index)

    for a in ASSETS:
        # Price and return primitives
        p = df[a].astype(float)
        r = df[f"ret_{a}"].astype(float)

        # Trend signal: normalized EMA spread
        ema_fast = p.ewm(span=12, adjust=False).mean()
        ema_slow = p.ewm(span=72, adjust=False).mean()
        trend_raw = (ema_fast - ema_slow) / (p.rolling(48, min_periods=24).std() + 1e-9)
        trend = np.tanh(trend_raw)

        # Mean-reversion signal: fade short-term overextension
        r_z = _zscore(r, win=48)
        mean_rev = np.tanh(-0.8 * r_z)

        # Microstructure crowding/flow signal (if available)
        fz = df.get(f"ms_{a}_funding_z", pd.Series(0.0, index=df.index)).fillna(0.0)
        lz = df.get(f"ms_{a}_lsr_z", pd.Series(0.0, index=df.index)).fillna(0.0)
        tlz = df.get(f"ms_{a}_top_lsr_z", pd.Series(0.0, index=df.index)).fillna(0.0)
        tz = df.get(f"ms_{a}_tbr_z", pd.Series(0.0, index=df.index)).fillna(0.0)
        tks = df.get(f"ms_{a}_taker_ls_z", pd.Series(0.0, index=df.index)).fillna(0.0)
        oi = df.get(f"ms_{a}_oi_z", pd.Series(0.0, index=df.index)).fillna(0.0)

        crowd = np.tanh(-0.45 * fz - 0.30 * lz - 0.25 * tlz)
        flow = np.tanh(0.25 * tz + 0.25 * tks + 0.15 * oi)
        micro = 0.7 * crowd + 0.3 * flow

        # Balanced blend to avoid moonshot dependence
        sig = 0.45 * trend + 0.25 * mean_rev + 0.30 * micro
        sig = pd.Series(sig, index=df.index).ewm(span=8, adjust=False).mean()

        if feature_lag > 0:
            sig = sig.shift(feature_lag)

        out[f"sig_{a}"] = sig

    return out.fillna(0.0)


def simulate(
    df: pd.DataFrame,
    tc_bps: float = 4.0,
    init_equity: float = 100_000.0,
    target_gross: float = 1.00,
    min_gross: float = 0.55,
    max_step: float = 0.08,
    target_vol_annual: float = 0.18,
) -> tuple[pd.Series, pd.DataFrame]:
    idx = df.index
    ret = df[[f"ret_{a}" for a in ASSETS]].astype(float).fillna(0.0)
    sig = build_signals(df, feature_lag=1)

    # Inverse-vol risk balancing per asset
    rolling_vol = ret.rolling(72, min_periods=36).std().clip(lower=1e-6)

    w_prev = pd.Series(0.0, index=ASSETS)
    eq = init_equity
    peak = init_equity

    eq_hist = []
    rows = []

    target_hv = target_vol_annual / _annualize_factor()
    tc = tc_bps / 10_000.0

    strat_ret_hist = []

    for t in idx:
        s = pd.Series({a: float(sig.at[t, f"sig_{a}"]) for a in ASSETS})
        iv = 1.0 / rolling_vol.loc[t].rename(lambda c: c.replace("ret_", ""))
        iv = iv.replace([np.inf, -np.inf], np.nan).fillna(0.0)

        raw = np.tanh(1.25 * s) * iv

        gross_raw = float(np.abs(raw).sum())
        if gross_raw > 1e-12:
            w_tgt = raw * (target_gross / gross_raw)
        else:
            w_tgt = raw.copy()

        # Keep strategy regularly active (anti-moonshot)
        gross_tgt = float(np.abs(w_tgt).sum())
        if 0 < gross_tgt < min_gross:
            w_tgt = w_tgt * (min_gross / gross_tgt)

        # Drawdown governor for smoother path
        dd = 1.0 - eq / max(peak, 1e-12)
        if dd <= 0.10:
            dd_scale = 1.0
        elif dd >= 0.22:
            dd_scale = 0.45
        else:
            dd_scale = 1.0 - (dd - 0.10) * (1.0 - 0.45) / (0.22 - 0.10)
        w_tgt *= dd_scale

        # Vol targeting from realized strategy vol
        if len(strat_ret_hist) >= 48:
            rv = float(pd.Series(strat_ret_hist[-96:]).std())
            lev = np.clip(target_hv / max(rv, 1e-9), 0.55, 1.35)
            w_tgt *= lev
        else:
            lev = 1.0

        # Turnover limiter to reduce lumpy behavior
        delta = (w_tgt - w_prev).clip(lower=-max_step, upper=max_step)
        w = w_prev + delta

        # PnL and costs
        r_t = ret.loc[t].rename(lambda c: c.replace("ret_", ""))
        gross_turnover = float(np.abs(w - w_prev).sum())
        pnl = float((w_prev * r_t).sum() - tc * gross_turnover)

        eq = eq * (1.0 + pnl)
        peak = max(peak, eq)

        strat_ret_hist.append(pnl)
        eq_hist.append(eq)
        rows.append({
            "time": t,
            "w_eth": float(w.get("eth", 0.0)),
            "w_btc": float(w.get("btc", 0.0)),
            "w_sol": float(w.get("sol", 0.0)),
            "gross": float(np.abs(w).sum()),
            "turnover": gross_turnover,
            "dd_scale": dd_scale,
            "vol_lev": float(lev),
            "ret": pnl,
            "equity": eq,
        })

        w_prev = w

    eq_series = pd.Series(eq_hist, index=idx, name="equity")
    details = pd.DataFrame(rows).set_index("time")
    return eq_series, details


def main() -> None:
    ap = argparse.ArgumentParser(description="Steady incremental crypto strategy (anti-moonshot design)")
    ap.add_argument(
        "--input",
        default=r"c:\amttp\data\processed\unified_crypto_1h_20210101_to_20260601.parquet",
        help="Path to unified dataset parquet",
    )
    ap.add_argument("--out-dir", default=r"c:\amttp\research\adaptive-friction\pipeline\results\steady_incremental_v1")
    ap.add_argument("--tc-bps", type=float, default=4.0)
    ap.add_argument("--target-gross", type=float, default=1.00)
    ap.add_argument("--min-gross", type=float, default=0.55)
    ap.add_argument("--target-vol-annual", type=float, default=0.18)
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    df = pd.read_parquet(args.input).sort_index()
    eq, details = simulate(
        df,
        tc_bps=args.tc_bps,
        target_gross=args.target_gross,
        min_gross=args.min_gross,
        target_vol_annual=args.target_vol_annual,
    )

    m = equity_metrics(eq)
    m["avg_gross"] = float(details["gross"].mean())
    m["median_gross"] = float(details["gross"].median())
    m["avg_turnover"] = float(details["turnover"].mean())
    m["positive_hour_rate"] = float((details["ret"] > 0).mean())
    m["months_positive_rate"] = float((details["ret"].resample("ME").sum() > 0).mean())

    eq.to_csv(out_dir / "equity_curve.csv", header=True)
    details.to_csv(out_dir / "hourly_details.csv")
    with open(out_dir / "summary.json", "w", encoding="utf-8") as f:
        json.dump(m, f, indent=2)

    print("Saved:", out_dir / "equity_curve.csv")
    print("Saved:", out_dir / "hourly_details.csv")
    print("Saved:", out_dir / "summary.json")
    print("Summary:")
    for k in [
        "final", "return_pct", "cagr", "sharpe", "maxdd", "calmar",
        "avg_gross", "avg_turnover", "positive_hour_rate", "months_positive_rate"
    ]:
        print(f"  {k}: {m[k]}")


if __name__ == "__main__":
    main()
