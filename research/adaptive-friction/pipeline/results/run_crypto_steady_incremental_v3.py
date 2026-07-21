from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

ASSETS = ["eth", "btc", "sol"]
INIT = 100_000.0


def zscore(s: pd.Series, win: int) -> pd.Series:
    mu = s.rolling(win, min_periods=win).mean()
    sd = s.rolling(win, min_periods=win).std()
    return (s - mu) / (sd + 1e-9)


def ann_sqrt() -> float:
    return np.sqrt(24.0 * 365.25)


def equity_metrics(eq: pd.Series) -> dict:
    r = eq.pct_change().fillna(0.0)
    dd = (eq / eq.cummax()) - 1.0
    years = max((eq.index[-1] - eq.index[0]).days / 365.25, 1e-9)
    cagr = float((eq.iloc[-1] / eq.iloc[0]) ** (1.0 / years) - 1.0)
    sharpe = float(ann_sqrt() * r.mean() / (r.std() + 1e-12))
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


def build_signals(df: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame(index=df.index)

    # Mild market regime proxy (avoid aggressive beta in high-stress zones)
    market_stress = zscore(df["spread_ret_eb"].abs().fillna(0.0), 96).clip(-3, 3)
    beta_scale = (1.0 - 0.25 * market_stress.clip(lower=0)).clip(lower=0.40, upper=1.00)

    # BTC anchor return for relative-value transforms
    r_btc = df["ret_btc"].fillna(0.0)

    for a in ASSETS:
        r = df[f"ret_{a}"].fillna(0.0)
        p = df[a].astype(float)

        # 1) Relative-value mean reversion vs BTC
        rel = r - r_btc
        rel_z = zscore(rel, 48).fillna(0.0)
        s_rel = np.tanh(-0.90 * rel_z)

        # 2) Microstructure carry/crowding (contrarian)
        fz = df.get(f"ms_{a}_funding_z", pd.Series(0.0, index=df.index)).fillna(0.0)
        lz = df.get(f"ms_{a}_lsr_z", pd.Series(0.0, index=df.index)).fillna(0.0)
        tlz = df.get(f"ms_{a}_top_lsr_z", pd.Series(0.0, index=df.index)).fillna(0.0)
        tz = df.get(f"ms_{a}_tbr_z", pd.Series(0.0, index=df.index)).fillna(0.0)
        tks = df.get(f"ms_{a}_taker_ls_z", pd.Series(0.0, index=df.index)).fillna(0.0)

        s_carry = np.tanh(-0.45 * fz - 0.25 * lz - 0.20 * tlz + 0.10 * tz + 0.10 * tks)

        # 3) Low-weight trend for persistence participation
        ema_f = p.ewm(span=18, adjust=False).mean()
        ema_s = p.ewm(span=96, adjust=False).mean()
        trend = np.tanh((ema_f - ema_s) / (p.rolling(72, min_periods=36).std() + 1e-9))

        sig = 0.55 * s_rel + 0.30 * s_carry + 0.15 * trend

        # Volatility-aware dampening
        rv = r.rolling(72, min_periods=36).std().fillna(r.std())
        damp = (0.015 / (rv + 1e-9)).clip(lower=0.55, upper=1.45)

        out[f"sig_{a}"] = (sig * damp * beta_scale).shift(1).fillna(0.0)

    return out


def simulate(
    df: pd.DataFrame,
    tc_bps: float = 2.0,
    target_gross: float = 1.20,
    min_gross: float = 0.80,
    max_step: float = 0.04,
    target_vol_annual: float = 0.10,
) -> tuple[pd.Series, pd.DataFrame]:
    sig = build_signals(df)
    ret = df[[f"ret_{a}" for a in ASSETS]].fillna(0.0)
    rolling_vol = ret.rolling(96, min_periods=48).std().clip(lower=1e-6)

    w_prev = pd.Series(0.0, index=ASSETS)
    eq = INIT
    peak = INIT
    strat_hist: list[float] = []

    rows = []
    tc = tc_bps / 10_000.0
    target_hv = target_vol_annual / ann_sqrt()

    for t in df.index:
        s = pd.Series({a: float(sig.at[t, f"sig_{a}"]) for a in ASSETS})
        iv = 1.0 / rolling_vol.loc[t].rename(lambda c: c.replace("ret_", ""))
        iv = iv.replace([np.inf, -np.inf], np.nan).fillna(0.0)

        raw = s * iv

        # Dollar-neutral base to avoid moonshot beta concentration
        raw = raw - raw.mean()

        gross_raw = float(np.abs(raw).sum())
        if gross_raw > 1e-12:
            w_tgt = raw * (target_gross / gross_raw)
        else:
            w_tgt = raw.copy()

        gross_tgt = float(np.abs(w_tgt).sum())
        if 0 < gross_tgt < min_gross:
            w_tgt *= (min_gross / gross_tgt)

        # Drawdown throttle for steadier path
        dd = 1.0 - eq / max(peak, 1e-12)
        if dd <= 0.08:
            dd_scale = 1.0
        elif dd >= 0.16:
            dd_scale = 0.30
        else:
            dd_scale = 1.0 - (dd - 0.08) * (1.0 - 0.30) / (0.16 - 0.08)
        w_tgt *= dd_scale

        # Realized strategy vol targeting
        if len(strat_hist) >= 72:
            rv = float(pd.Series(strat_hist[-168:]).std())
            lev = np.clip(target_hv / max(rv, 1e-9), 0.50, 1.30)
            w_tgt *= lev
        else:
            lev = 1.0

        # Turnover limiter
        delta = (w_tgt - w_prev).clip(lower=-max_step, upper=max_step)
        w = w_prev + delta

        # Soft gross cap after limiter
        g = float(np.abs(w).sum())
        if g > target_gross:
            w *= (target_gross / g)

        r_t = ret.loc[t].rename(lambda c: c.replace("ret_", ""))
        turnover = float(np.abs(w - w_prev).sum())
        pnl = float((w_prev * r_t).sum() - tc * turnover)

        eq *= (1.0 + pnl)
        peak = max(peak, eq)
        strat_hist.append(pnl)

        rows.append({
            "time": t,
            "w_eth": float(w.get("eth", 0.0)),
            "w_btc": float(w.get("btc", 0.0)),
            "w_sol": float(w.get("sol", 0.0)),
            "gross": float(np.abs(w).sum()),
            "turnover": turnover,
            "dd_scale": dd_scale,
            "vol_lev": float(lev),
            "ret": pnl,
            "equity": eq,
        })

        w_prev = w

    details = pd.DataFrame(rows).set_index("time")
    eq = details["equity"].copy()
    return eq, details


def main() -> None:
    ap = argparse.ArgumentParser(description="Steady incremental v3 (market-neutral + carry + throttles)")
    ap.add_argument("--input", default=r"c:\amttp\data\processed\unified_crypto_1h_20210101_to_20260601.parquet")
    ap.add_argument("--out-dir", default=r"c:\amttp\research\adaptive-friction\pipeline\results\steady_incremental_v3")
    ap.add_argument("--tc-bps", type=float, default=2.0)
    ap.add_argument("--target-gross", type=float, default=1.20)
    ap.add_argument("--min-gross", type=float, default=0.80)
    ap.add_argument("--target-vol-annual", type=float, default=0.10)
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

    monthly = details["ret"].resample("ME").sum()
    m["months_positive_rate"] = float((monthly > 0).mean())
    m["median_month_ret"] = float(monthly.median())
    m["best_5m_share"] = float(monthly.sort_values(ascending=False).head(5).sum() / max(monthly.sum(), 1e-12))

    eq.to_csv(out_dir / "equity_curve.csv", header=True)
    details.to_csv(out_dir / "hourly_details.csv")
    monthly.to_csv(out_dir / "monthly_returns.csv", header=True)
    with open(out_dir / "summary.json", "w", encoding="utf-8") as f:
        json.dump(m, f, indent=2)

    print(f"Saved: {out_dir / 'equity_curve.csv'}")
    print(f"Saved: {out_dir / 'hourly_details.csv'}")
    print(f"Saved: {out_dir / 'monthly_returns.csv'}")
    print(f"Saved: {out_dir / 'summary.json'}")
    print("Summary:")
    for k in [
        "final", "return_pct", "cagr", "sharpe", "maxdd", "calmar",
        "avg_gross", "avg_turnover", "positive_hour_rate", "months_positive_rate",
        "median_month_ret", "best_5m_share"
    ]:
        print(f"  {k}: {m[k]}")


if __name__ == "__main__":
    main()
