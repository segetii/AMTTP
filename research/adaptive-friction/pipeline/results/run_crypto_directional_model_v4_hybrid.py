"""
run_crypto_directional_model_v4_hybrid.py
=========================================
Deterministic "best executable now" model:

- Direction source: robust momentum side (same stable prior as v3).
- No weak-probability classifier dependency.
- Risk shaping from independent microstructure + regime gates.
- Daily non-overlapping event returns with transaction costs.

Goal: preserve directional edge while reducing catastrophic drawdown from
always-on momentum.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from run_crypto_directional_model_v3_tbml import (
    DATA_PATH,
    OUT_DIR as OUT_DIR_V3,
    TEST_START,
    TC_BPS,
    TARGET_DAILY_VOL,
    MAX_GROSS,
    build_features,
    make_daily_panel,
    signed_sharpe,
)

OUT_DIR = Path(__file__).parent / "directional_model_v4_hybrid"

SHARPE_GATE = 1.0
MAXDD_GATE = -0.20
POS_YEARS_GATE = 3


def clip_step(pos: pd.Series, max_step: float = 0.20) -> pd.Series:
    """Limit day-to-day position jumps to reduce churn and slippage spikes."""
    out = np.zeros(len(pos), dtype=float)
    prev = 0.0
    for i, x in enumerate(pos.fillna(0.0).values):
        delta = np.clip(x - prev, -max_step, max_step)
        prev = prev + delta
        out[i] = prev
    return pd.Series(out, index=pos.index)


def run_hybrid(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    X, _y_meta, side, side_ret = make_daily_panel(df)
    feat_hourly = build_features(df)
    daily_idx = X.index

    # Side prior: robust momentum sign from v3 panel.
    s = side.reindex(daily_idx).fillna(0.0)

    # Confidence from momentum magnitude (bounded).
    mom_conf = X["mom_168"].abs().clip(0.0, 2.5) / 2.5

    # Vol target scale.
    vol_scale = (TARGET_DAILY_VOL / X["vol_24"].replace(0.0, np.nan)).clip(upper=1.0).fillna(0.0)

    # Pull microstructure from hourly features aligned to daily events.
    fz = feat_hourly["funding_z"].reindex(daily_idx).fillna(0.0).clip(-3, 3)
    crowd = feat_hourly["x_toplsr_oi"].reindex(daily_idx).fillna(0.0).clip(-3, 3)
    vr = X["vol_regime"].fillna(1.0).clip(0.8, 2.5)

    # If the strategy side is aligned with crowded / expensive carry,
    # cut risk. This is a one-sided penalty and never flips direction.
    side_funding = (s * fz).clip(lower=0.0, upper=2.0)
    side_crowd = (s * crowd).clip(lower=0.0, upper=2.0)

    g_funding = (1.0 - 0.35 * side_funding / 2.0).clip(0.55, 1.0)
    g_crowd = (1.0 - 0.35 * side_crowd / 2.0).clip(0.55, 1.0)
    g_regime = (1.0 / vr).clip(0.45, 1.0)

    raw_pos = s * mom_conf * vol_scale * g_funding * g_crowd * g_regime
    raw_pos = raw_pos.clip(-MAX_GROSS, MAX_GROSS)

    # Smooth + step-limit for execution realism.
    smooth = raw_pos.ewm(span=3, adjust=False).mean()
    pos = clip_step(smooth, max_step=0.18).clip(-MAX_GROSS, MAX_GROSS)

    out = pd.DataFrame(index=daily_idx)
    out["position"] = pos
    out["side"] = s
    out["side_ret"] = side_ret.reindex(daily_idx)
    out["turnover"] = out["position"].diff().abs().fillna(out["position"].abs())
    out["net_return"] = out["position"] * out["side_ret"] - out["turnover"] * (TC_BPS / 10_000.0)
    out = out[out.index >= TEST_START].copy()
    out["equity"] = (1.0 + out["net_return"]).cumprod() * 100_000.0

    eq = out["equity"]
    dd = eq / eq.cummax() - 1.0
    years = len(out) / 365.25
    cagr = (eq.iloc[-1] / eq.iloc[0]) ** (1.0 / years) - 1.0 if years > 0 else np.nan

    m = {
        "variant": "v4_hybrid_mom_micro_risk",
        "final": float(eq.iloc[-1]),
        "cagr": float(cagr),
        "sharpe": signed_sharpe(out["net_return"]),
        "maxdd": float(dd.min()),
        "calmar": float(cagr / abs(dd.min())) if dd.min() < 0 else np.nan,
        "avg_turnover": float(out["turnover"].mean()),
        "n_days": int(len(out)),
    }
    return out, m


def baseline(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    X, _y_meta, side, side_ret = make_daily_panel(df)
    idx = X.index[X.index >= TEST_START]
    vol_scale = (TARGET_DAILY_VOL / X.loc[idx, "vol_24"].replace(0.0, np.nan)).clip(upper=1.0).fillna(0.0)

    out = pd.DataFrame(index=idx)
    out["position"] = side.loc[idx].fillna(0.0) * vol_scale
    out["side_ret"] = side_ret.loc[idx]
    out["turnover"] = out["position"].diff().abs().fillna(out["position"].abs())
    out["net_return"] = out["position"] * out["side_ret"] - out["turnover"] * (TC_BPS / 10_000.0)
    out["equity"] = (1.0 + out["net_return"]).cumprod() * 100_000.0

    eq = out["equity"]
    dd = eq / eq.cummax() - 1.0
    years = len(out) / 365.25
    cagr = (eq.iloc[-1] / eq.iloc[0]) ** (1.0 / years) - 1.0 if years > 0 else np.nan

    m = {
        "variant": "z_baseline_mom_side",
        "final": float(eq.iloc[-1]),
        "cagr": float(cagr),
        "sharpe": signed_sharpe(out["net_return"]),
        "maxdd": float(dd.min()),
        "calmar": float(cagr / abs(dd.min())) if dd.min() < 0 else np.nan,
        "avg_turnover": float(out["turnover"].mean()),
        "n_days": int(len(out)),
    }
    return out, m


def yearly_metrics(pred: pd.DataFrame, variant: str) -> pd.DataFrame:
    rows = []
    for year, g in pred.groupby(pred.index.year):
        if len(g) < 20:
            continue
        eq = (1.0 + g["net_return"]).cumprod() * 100_000.0
        dd = eq / eq.cummax() - 1.0
        rows.append({
            "variant": variant,
            "year": int(year),
            "sharpe": signed_sharpe(g["net_return"]),
            "cagr": float((eq.iloc[-1] / eq.iloc[0]) ** (365.25 / len(g)) - 1.0),
            "maxdd": float(dd.min()),
        })
    return pd.DataFrame(rows)


def print_summary(rows: list[dict]) -> None:
    print("\n=== v4 Hybrid deterministic model ===")
    print(f"{'variant':<28}{'final$':>12}{'sharpe':>9}{'cagr':>9}{'maxdd':>9}{'calmar':>9}{'turnover':>10}")
    print("-" * 96)
    for r in rows:
        print(
            f"{r['variant']:<28}{r['final']:>12,.0f}{r['sharpe']:>9.3f}{r['cagr']*100:>8.2f}%"
            f"{r['maxdd']*100:>8.2f}%{r['calmar']:>9.3f}{r['avg_turnover']:>10.4f}"
        )


def deployment_decision(summary: pd.DataFrame, yearly: pd.DataFrame) -> dict:
    m = summary.loc[summary["variant"] == "v4_hybrid_mom_micro_risk"].iloc[0]
    b = summary.loc[summary["variant"] == "z_baseline_mom_side"].iloc[0]
    pos_years = int((yearly[yearly["variant"] == "v4_hybrid_mom_micro_risk"]["sharpe"] > 0).sum())

    passes = {
        "sharpe": bool(m["sharpe"] >= SHARPE_GATE),
        "maxdd": bool(m["maxdd"] >= MAXDD_GATE),
        "sharpe_vs_baseline": bool(m["sharpe"] >= b["sharpe"] + 0.05),
        "positive_years": bool(pos_years >= POS_YEARS_GATE),
    }
    deployable = all(passes.values())
    return {
        "deployable": deployable,
        "selected_variant": "v4_hybrid_mom_micro_risk" if deployable else None,
        "fallback": None if deployable else "canonical_tanh_momentum",
        "model": {
            "sharpe": float(m["sharpe"]),
            "maxdd": float(m["maxdd"]),
            "cagr": float(m["cagr"]),
            "turnover": float(m["avg_turnover"]),
            "positive_years": pos_years,
        },
        "baseline": {
            "sharpe": float(b["sharpe"]),
            "maxdd": float(b["maxdd"]),
            "cagr": float(b["cagr"]),
            "turnover": float(b["avg_turnover"]),
        },
        "gates": {
            "sharpe": SHARPE_GATE,
            "maxdd": MAXDD_GATE,
            "sharpe_vs_baseline_increment": 0.05,
            "positive_years": POS_YEARS_GATE,
        },
        "passed": passes,
    }


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df = pd.read_parquet(DATA_PATH).sort_index()

    p_hybrid, m_hybrid = run_hybrid(df)
    p_base, m_base = baseline(df)

    p_hybrid.to_csv(OUT_DIR / "v4_hybrid_predictions.csv")
    p_base.to_csv(OUT_DIR / "z_baseline_predictions.csv")

    summary = pd.DataFrame([m_hybrid, m_base])
    yearly = pd.concat([
        yearly_metrics(p_hybrid, m_hybrid["variant"]),
        yearly_metrics(p_base, m_base["variant"]),
    ], ignore_index=True)

    summary.to_csv(OUT_DIR / "summary.csv", index=False)
    yearly.to_csv(OUT_DIR / "yearly_metrics.csv", index=False)
    (OUT_DIR / "summary.json").write_text(json.dumps([m_hybrid, m_base], indent=2))
    decision = deployment_decision(summary, yearly)
    (OUT_DIR / "deployment_decision.json").write_text(json.dumps(decision, indent=2))

    print_summary([m_hybrid, m_base])
    print("\n=== Yearly Sharpe ===")
    print(yearly.pivot_table(index="variant", columns="year", values="sharpe", aggfunc="first").to_string())
    print("\nDeployment decision:", json.dumps(decision, indent=2))


if __name__ == "__main__":
    main()
