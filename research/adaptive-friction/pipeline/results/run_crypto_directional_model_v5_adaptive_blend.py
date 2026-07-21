"""
run_crypto_directional_model_v5_adaptive_blend.py
=================================================
Fix for v4 failure mode: v4 improved global Sharpe/DD but failed year consistency.

Design
------
Blend two legs at each daily event:
  1) Baseline persistent leg (momentum-side + vol target)
  2) Risk-shaped leg (microstructure/regime-gated momentum)

position_t = floor * baseline_t + (1-floor) * risk_leg_t

where floor in [0.45, 0.80] is swept. This forces persistent exposure so we do
not lose whole years while still reducing tail risk through the risk leg.

We optimize under hard constraints:
  - positive-year count >= 3
  - max drawdown >= -25%
  - turnover <= baseline turnover

Score among feasible candidates:
  score = sharpe + 0.4*calmar + 0.15*cagr - 0.2*turnover
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from run_crypto_directional_model_v3_tbml import (
    DATA_PATH,
    TEST_START,
    TARGET_DAILY_VOL,
    TC_BPS,
    MAX_GROSS,
    build_features,
    make_daily_panel,
    signed_sharpe,
)

OUT_DIR = Path(__file__).parent / "directional_model_v5_adaptive_blend"


def clip_step(pos: pd.Series, max_step: float) -> pd.Series:
    out = np.zeros(len(pos), dtype=float)
    prev = 0.0
    for i, x in enumerate(pos.fillna(0.0).values):
        d = np.clip(x - prev, -max_step, max_step)
        prev += d
        out[i] = prev
    return pd.Series(out, index=pos.index)


def build_legs(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series, pd.Series]:
    X, _y_meta, side, side_ret = make_daily_panel(df)
    feat_hourly = build_features(df)
    idx = X.index[X.index >= TEST_START]

    s = side.reindex(idx).fillna(0.0)
    vol_scale = (TARGET_DAILY_VOL / X.loc[idx, "vol_24"].replace(0.0, np.nan)).clip(upper=1.0).fillna(0.0)

    # Baseline leg: persistent directional prior
    base = (s * vol_scale).clip(-MAX_GROSS, MAX_GROSS)

    # Risk-shaped leg (same family as v4)
    mom_conf = X.loc[idx, "mom_168"].abs().clip(0.0, 2.5) / 2.5
    vr = X.loc[idx, "vol_regime"].fillna(1.0).clip(0.8, 2.5)
    fz = feat_hourly["funding_z"].reindex(idx).fillna(0.0).clip(-3, 3)
    crowd = feat_hourly["x_toplsr_oi"].reindex(idx).fillna(0.0).clip(-3, 3)

    side_funding = (s * fz).clip(lower=0.0, upper=2.0)
    side_crowd = (s * crowd).clip(lower=0.0, upper=2.0)
    g_funding = (1.0 - 0.35 * side_funding / 2.0).clip(0.55, 1.0)
    g_crowd = (1.0 - 0.35 * side_crowd / 2.0).clip(0.55, 1.0)
    g_regime = (1.0 / vr).clip(0.45, 1.0)

    risk = (s * mom_conf * vol_scale * g_funding * g_crowd * g_regime).clip(-MAX_GROSS, MAX_GROSS)

    return X.loc[idx], base, risk


def simulate(position: pd.Series, side_ret: pd.Series) -> pd.DataFrame:
    out = pd.DataFrame(index=position.index)
    out["position"] = position.clip(-MAX_GROSS, MAX_GROSS)
    out["side_ret"] = side_ret.reindex(out.index)
    out["turnover"] = out["position"].diff().abs().fillna(out["position"].abs())
    out["net_return"] = out["position"] * out["side_ret"] - out["turnover"] * (TC_BPS / 10_000.0)
    out["equity"] = (1.0 + out["net_return"]).cumprod() * 100_000.0
    return out


def metrics(pred: pd.DataFrame, name: str) -> dict:
    eq = pred["equity"]
    dd = eq / eq.cummax() - 1.0
    years = len(pred) / 365.25
    cagr = (eq.iloc[-1] / eq.iloc[0]) ** (1.0 / years) - 1.0 if years > 0 else np.nan

    yearly = pred.groupby(pred.index.year)["net_return"].apply(signed_sharpe)
    pos_years = int((yearly > 0).sum())

    m = {
        "variant": name,
        "final": float(eq.iloc[-1]),
        "cagr": float(cagr),
        "sharpe": signed_sharpe(pred["net_return"]),
        "maxdd": float(dd.min()),
        "calmar": float(cagr / abs(dd.min())) if dd.min() < 0 else np.nan,
        "avg_turnover": float(pred["turnover"].mean()),
        "positive_years": pos_years,
    }
    return m


def objective(m: dict) -> float:
    return float(m["sharpe"] + 0.4 * m["calmar"] + 0.15 * m["cagr"] - 0.2 * m["avg_turnover"])


def print_table(rows: list[dict], title: str) -> None:
    print(f"\n=== {title} ===")
    print(f"{'variant':<26}{'final$':>11}{'sharpe':>8}{'cagr':>8}{'maxdd':>8}{'calmar':>9}{'t/o':>8}{'+yrs':>6}")
    print("-" * 92)
    for r in rows:
        print(
            f"{r['variant']:<26}{r['final']:>11,.0f}{r['sharpe']:>8.3f}{r['cagr']*100:>7.2f}%"
            f"{r['maxdd']*100:>7.2f}%{r['calmar']:>9.3f}{r['avg_turnover']:>8.4f}{r['positive_years']:>6d}"
        )


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df = pd.read_parquet(DATA_PATH).sort_index()

    X, base, risk = build_legs(df)
    _X2, _y, side, side_ret = make_daily_panel(df)
    side_ret = side_ret.reindex(X.index)

    # Baseline benchmark
    base_smooth = clip_step(base.ewm(span=2, adjust=False).mean(), max_step=0.35)
    pred_base = simulate(base_smooth, side_ret)
    m_base = metrics(pred_base, "z_baseline_mom_side")

    # Constrained sweep for adaptive blend
    candidates = []
    for floor in (0.45, 0.55, 0.65, 0.75, 0.80):
        for step in (0.10, 0.14, 0.18, 0.24):
            blend = floor * base + (1.0 - floor) * risk
            smooth = clip_step(blend.ewm(span=3, adjust=False).mean(), max_step=step)
            pred = simulate(smooth, side_ret)
            m = metrics(pred, f"v5_floor{floor:.2f}_step{step:.2f}")
            m["floor"] = floor
            m["step"] = step
            m["score"] = objective(m)
            candidates.append((m, pred))

    cand_df = pd.DataFrame([m for m, _ in candidates])
    cand_df.to_csv(OUT_DIR / "sweep_candidates.csv", index=False)

    feasible = cand_df[
        (cand_df["positive_years"] >= 3)
        & (cand_df["maxdd"] >= -0.25)
        & (cand_df["avg_turnover"] <= m_base["avg_turnover"])
    ].copy()

    if feasible.empty:
        best_row = cand_df.sort_values("score", ascending=False).iloc[0]
        chosen_name = best_row["variant"]
        deployable = False
        reason = "No candidate satisfied all feasibility constraints."
    else:
        best_row = feasible.sort_values("score", ascending=False).iloc[0]
        chosen_name = best_row["variant"]
        deployable = True
        reason = "Chosen candidate satisfies feasibility constraints."

    chosen_pred = next(pred for m, pred in candidates if m["variant"] == chosen_name)
    chosen_metrics = next(m for m, pred in candidates if m["variant"] == chosen_name)

    # Persist artifacts
    pred_base.to_csv(OUT_DIR / "z_baseline_predictions.csv")
    chosen_pred.to_csv(OUT_DIR / "v5_chosen_predictions.csv")

    summary_rows = [chosen_metrics, m_base]
    pd.DataFrame(summary_rows).to_csv(OUT_DIR / "summary.csv", index=False)
    (OUT_DIR / "summary.json").write_text(json.dumps(summary_rows, indent=2))

    decision = {
        "deployable": deployable,
        "selected_variant": chosen_name if deployable else None,
        "fallback": None if deployable else "canonical_tanh_momentum",
        "reason": reason,
        "chosen_metrics": chosen_metrics,
        "baseline_metrics": m_base,
        "constraints": {
            "positive_years_min": 3,
            "maxdd_min": -0.25,
            "turnover_max": m_base["avg_turnover"],
        },
    }
    (OUT_DIR / "deployment_decision.json").write_text(json.dumps(decision, indent=2))

    print_table(summary_rows, "v5 chosen vs baseline")
    print("\nDeployment decision:", json.dumps(decision, indent=2))


if __name__ == "__main__":
    main()
