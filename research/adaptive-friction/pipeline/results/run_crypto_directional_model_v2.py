"""
run_crypto_directional_model_v2.py
===================================
Targeted interaction-feature ablation to isolate which specific combinations
of momentum and perpetual-market microstructure variables contribute real
out-of-sample directional edge.

Background (from v1 results)
------------------------------
The v1 walk-forward experiment found:
  * Momentum-only AUC 0.464 → below random (mean-reversion regime 2023-26)
  * Momentum + regime AUC 0.481 → still sub-0.50
  * Full feature set AUC 0.496, Sharpe 0.925, CAGR 6% → not classifiable
    as genuine directional skill (AUC below 0.50, hit 49.4%)
  * 7-day naive momentum Sharpe 0.992 via large position / high DD

The key open question: which microstructure interactions carry the profitable
structure hidden in variant C?

Methodology
-----------
Each "variant" below is tested with:
  1. Non-overlapping daily labels  y_t = 1[ret_eth(t → t+24h) > 0]
  2. All features lagged 1h (no lookahead)
  3. Rolling train window: 12-month warm-up, max 24-month window
  4. Refit monthly
  5. L2-regularized logistic regression (C=0.05)
  6. OOS period: 2023-01-01 to end of dataset
  7. Vol-targeted position sizing, 5bp round-trip cost
  8. Hard deployment gate: AUC >= 0.52, hit >= 0.52, positive Sharpe in >= 3 years

Interaction families tested
----------------------------
  F1  funding_x_oi    : funding_z * clip(oi_pct_1h,...)  — crowded+expensive
  F2  funding_x_mom   : funding_z * mom_168              — carry vs trend
  F3  taker_x_mom     : taker_imbalance * mom_168        — order flow agrees with trend
  F4  lsr_x_vol       : lsr_z * vol_regime               — extreme positioning near vol spike
  F5  top_lsr_x_oi    : top_lsr_z * oi_pct_1h           — pro-trader positioning change
  F6  oi_momentum     : signed oi_z * mom_168            — institutional positioning agrees with price
  F7  composite       : best-of-all interactions by expected Spearman(signal, next_ret)

All models are compared against the identical matched naive-momentum baseline
and the C_full_independent variant from v1.

Outputs (directional_model_v2/)
-------------------------------
  {variant}_predictions.csv, {variant}_coefficients.csv,
  summary.csv, summary.json, yearly_metrics.csv, deployment_decision.json
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

DATA_PATH = Path(r"C:\amttp\data\processed\unified_crypto_1h_20210101_to_20260601.parquet")
OUT_DIR = Path(__file__).parent / "directional_model_v2"

HORIZON_H = 24
REBALANCE_HOUR = 0
TRAIN_START = pd.Timestamp("2021-01-01")
TEST_START = pd.Timestamp("2023-01-01")
MIN_TRAIN_DAYS = 365
MAX_TRAIN_DAYS = 730
REFIT_EVERY_DAYS = 30
TC_BPS = 5.0
TARGET_DAILY_VOL = 0.01
MAX_GROSS = 1.0
CONFIDENCE_THRESHOLD = 0.02
AUC_GATE = 0.52
HIT_GATE = 0.52
POS_YEARS_GATE = 3


def _finite(s: pd.Series) -> pd.Series:
    return s.replace([np.inf, -np.inf], np.nan)


def signed_sharpe(x: pd.Series) -> float:
    vol = x.std(ddof=0)
    return float(x.mean() / vol * np.sqrt(365.25)) if vol > 1e-12 else 0.0


def build_base(df: pd.DataFrame) -> pd.DataFrame:
    """Build raw (not-yet-lagged) base features used by all interaction families."""
    r_eth = df["ret_eth"].fillna(0.0)
    r_btc = df["ret_btc"].fillna(0.0)
    vol_24 = r_eth.rolling(24, min_periods=12).std()
    vol_168 = r_eth.rolling(168, min_periods=48).std()
    vol_regime = (vol_24 / vol_168.replace(0, np.nan)).fillna(1.0).clip(0.1, 5.0)

    def risk_adj(r: pd.Series, h: int) -> pd.Series:
        cumret = r.rolling(h, min_periods=max(12, h // 3)).sum()
        scale = r.rolling(h, min_periods=max(12, h // 3)).std() * np.sqrt(h)
        return _finite(cumret / scale.replace(0, np.nan))

    b = pd.DataFrame(index=df.index)
    b["mom_24"]  = risk_adj(r_eth, 24)
    b["mom_72"]  = risk_adj(r_eth, 72)
    b["mom_168"] = risk_adj(r_eth, 168)
    b["mom_720"] = risk_adj(r_eth, 720)
    b["rel_mom_72"] = risk_adj(r_eth - r_btc, 72)

    b["vol_24"]  = vol_24
    b["vol_168"] = vol_168
    b["vol_regime"] = vol_regime
    b["vol_eth_z"]   = df.get("vol_eth_z",   pd.Series(np.nan, index=df.index))
    b["btc_dom_z"]   = df.get("btc_dom_z",   pd.Series(np.nan, index=df.index))
    b["cross_disp_z"] = df.get("cross_disp_z", pd.Series(np.nan, index=df.index))

    # --- raw microstructure (inf-safe) ---
    funding   = _finite(df.get("ms_eth_funding_rate",    pd.Series(np.nan, index=df.index)))
    funding_z_raw = (funding - funding.rolling(168, min_periods=48).mean())
    funding_vol   = funding.rolling(168, min_periods=48).std().replace(0, np.nan)
    b["funding_z"]      = _finite(funding_z_raw / funding_vol)
    b["taker_imbalance"]= _finite(2.0 * df.get("ms_eth_taker_buy_ratio", pd.Series(np.nan, index=df.index)) - 1.0)
    b["oi_pct_1h"]      = _finite(df.get("ms_eth_oi_pct_1h", pd.Series(np.nan, index=df.index))).clip(-0.10, 0.10)
    b["oi_z"]           = _finite(df.get("ms_eth_oi_z",       pd.Series(np.nan, index=df.index))).clip(-5, 5)
    b["lsr_z"]          = _finite(df.get("ms_eth_lsr_z",      pd.Series(np.nan, index=df.index))).clip(-5, 5)
    b["top_lsr_z"]      = _finite(df.get("ms_eth_top_lsr_z",  pd.Series(np.nan, index=df.index))).clip(-5, 5)
    b["taker_ls_z"]     = _finite(df.get("ms_eth_taker_ls_z", pd.Series(np.nan, index=df.index))).clip(-5, 5)
    return b


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add prespecified interaction terms then lag everything one hour."""
    b = build_base(df)

    # --- F1: crowded expensive (high funding + surging OI → bearish; fade crowding) ---
    b["F1_funding_x_oi"] = -b["funding_z"] * b["oi_pct_1h"].clip(-0.05, 0.05) * 10.0

    # --- F2: carry vs trend (funding cost diverges from direction of price) ---
    b["F2_funding_x_mom"] = -b["funding_z"] * b["mom_168"]

    # --- F3: taker flow agrees with trend (confirmation) ---
    b["F3_taker_x_mom"] = b["taker_imbalance"] * b["mom_168"]

    # --- F4: extreme positioning near vol spike → regime instability ---
    b["F4_lsr_x_vol"] = -b["lsr_z"] * (b["vol_regime"] - 1.0).clip(0, 3)

    # --- F5: pro-trader position change (top-trader LSR) with recent OI flow ---
    b["F5_top_lsr_x_oi"] = b["top_lsr_z"] * b["oi_pct_1h"] * 10.0

    # --- F6: institutional positioning agrees with price direction ---
    b["F6_oi_signed_mom"] = np.sign(b["oi_z"]) * b["mom_168"]

    # --- F7: composite signed rank of all F1-F6 → single robust aggregation ---
    interaction_cols = [f"F{i}" for i in range(1, 7)]
    interaction_cols_full = [c for c in b.columns if c.startswith("F")]
    ranks = b[interaction_cols_full].rank(pct=True, axis=0) - 0.5
    b["F7_composite"] = ranks.mean(axis=1)

    # --- taker_ls_z included standalone to separate its contribution ---
    b["F8_taker_ls_standalone"] = b["taker_ls_z"]

    return b.replace([np.inf, -np.inf], np.nan).shift(1)


# Prespecified feature sets for each ablation variant.
VARIANTS: dict[str, list[str]] = {
    # Interaction families one at a time (add momentum as a baseline pairing)
    "F1_funding_oi":       ["mom_168", "funding_z", "oi_pct_1h", "F1_funding_x_oi"],
    "F2_funding_mom":      ["mom_168", "funding_z", "F2_funding_x_mom"],
    "F3_taker_mom":        ["mom_168", "taker_imbalance", "F3_taker_x_mom"],
    "F4_lsr_vol":          ["mom_168", "lsr_z", "vol_regime", "F4_lsr_x_vol"],
    "F5_top_lsr_oi":       ["mom_168", "top_lsr_z", "oi_pct_1h", "F5_top_lsr_x_oi"],
    "F6_oi_signed_mom":    ["mom_168", "oi_z", "F6_oi_signed_mom"],
    "F7_composite":        ["mom_168", "F7_composite"],
    "F8_taker_ls":         ["mom_168", "F8_taker_ls_standalone"],
    # Progressive build-up of best interactions
    "G1_all_interactions": [
        "mom_168", "rel_mom_72",
        "F1_funding_x_oi", "F2_funding_x_mom", "F3_taker_x_mom",
        "F4_lsr_x_vol", "F5_top_lsr_x_oi", "F6_oi_signed_mom",
        "F7_composite",
    ],
    "G2_interactions_regime": [
        "mom_168", "mom_72", "rel_mom_72",
        "btc_dom_z", "cross_disp_z", "vol_eth_z",
        "F1_funding_x_oi", "F2_funding_x_mom", "F3_taker_x_mom",
        "F4_lsr_x_vol", "F5_top_lsr_x_oi", "F6_oi_signed_mom",
        "F7_composite",
    ],
}


def model() -> Pipeline:
    return Pipeline([
        ("imputer", SimpleImputer(strategy="median", add_indicator=True)),
        ("scale",   StandardScaler()),
        ("logit",   LogisticRegression(C=0.05, penalty="l2", solver="lbfgs", max_iter=1000)),
    ])


def walk_forward(
    X: pd.DataFrame,
    y: pd.Series,
    forward_ret: pd.Series,
    feature_names: list[str],
    name: str,
) -> tuple[pd.DataFrame, dict, pd.DataFrame]:
    records = []
    coefficient_rows = []
    last_refit = None
    fitted = None

    for t in X.index:
        if t < TEST_START:
            continue
        eligible = (
            (X.index >= TRAIN_START)
            & (X.index < t - pd.Timedelta(hours=HORIZON_H))
            & y.notna()
        )
        train_idx = X.index[eligible]
        if len(train_idx) > MAX_TRAIN_DAYS:
            train_idx = train_idx[-MAX_TRAIN_DAYS:]
        if len(train_idx) < MIN_TRAIN_DAYS or y.loc[train_idx].nunique() < 2:
            continue

        if fitted is None or (t - last_refit).days >= REFIT_EVERY_DAYS:
            fitted = model()
            fitted.fit(X.loc[train_idx, feature_names], y.loc[train_idx].astype(int))
            last_refit = t
            coefs = fitted.named_steps["logit"].coef_[0]
            coefficient_rows.append(
                pd.Series(coefs[:len(feature_names)], index=feature_names, name=t)
            )

        p = float(fitted.predict_proba(X.loc[[t], feature_names])[:, 1][0])
        records.append((t, p, y.loc[t], forward_ret.loc[t]))

    if not records:
        return pd.DataFrame(), {"variant": name, "error": "no predictions"}, pd.DataFrame()

    pred = pd.DataFrame(
        records, columns=["timestamp", "prob_up", "label", "forward_return"]
    ).set_index("timestamp")

    signed_edge = 2.0 * pred["prob_up"] - 1.0
    confidence  = ((signed_edge.abs() - CONFIDENCE_THRESHOLD) / (1.0 - CONFIDENCE_THRESHOLD)).clip(0.0, 1.0)
    direction   = np.sign(signed_edge)
    daily_vol   = X["vol_24"].reindex(pred.index) * np.sqrt(24.0)
    vol_scale   = (TARGET_DAILY_VOL / daily_vol.replace(0.0, np.nan)).clip(upper=1.0).fillna(0.0)

    pred["position"] = direction * confidence * vol_scale
    pos = pred["position"].clip(-MAX_GROSS, MAX_GROSS)
    turnover = pos.diff().abs().fillna(pos.abs())
    pred["net_return"] = pos * pred["forward_return"] - turnover * (TC_BPS / 10_000.0)
    equity = (1.0 + pred["net_return"]).cumprod() * 100_000.0
    pred["equity"]   = equity
    pred["turnover"] = turnover

    valid  = pred["prob_up"].notna() & pred["label"].notna()
    auc    = roc_auc_score(pred.loc[valid, "label"].astype(int), pred.loc[valid, "prob_up"]) if valid.sum() and pred.loc[valid, "label"].nunique() > 1 else np.nan
    hit    = ((pred.loc[valid, "prob_up"] >= 0.5) == pred.loc[valid, "label"].astype(bool)).mean() if valid.sum() else np.nan

    dd     = equity / equity.cummax() - 1.0
    years  = len(pred) / 365.25
    cagr   = (equity.iloc[-1] / equity.iloc[0]) ** (1.0 / years) - 1.0 if years else np.nan

    spear  = spearmanr(pred.loc[valid, "prob_up"], pred.loc[valid, "label"]).statistic if valid.sum() > 10 else np.nan

    m = {
        "variant":       name,
        "final":         float(equity.iloc[-1]),
        "cagr":          float(cagr),
        "sharpe":        signed_sharpe(pred["net_return"]),
        "maxdd":         float(dd.min()),
        "calmar":        float(cagr / abs(dd.min())) if dd.min() < 0 else np.nan,
        "avg_turnover":  float(pred["turnover"].mean()),
        "auc":           float(auc),
        "hit_rate":      float(hit),
        "spearman_rho":  float(spear),
        "n_days":        int(len(pred)),
    }
    return pred, m, pd.DataFrame(coefficient_rows)


def naive_momentum_baseline(X: pd.DataFrame, forward_ret: pd.Series) -> tuple[pd.DataFrame, dict]:
    idx = X.index[X.index >= TEST_START]
    out = pd.DataFrame(index=idx)
    out["forward_return"] = forward_ret.reindex(idx)
    direction   = np.sign(X.loc[idx, "mom_168"].fillna(0.0))
    daily_vol   = X.loc[idx, "vol_24"] * np.sqrt(24.0)
    vol_scale   = (TARGET_DAILY_VOL / daily_vol.replace(0.0, np.nan)).clip(upper=1.0).fillna(0.0)
    pos         = direction * vol_scale
    turnover    = pos.diff().abs().fillna(pos.abs())
    out["position"]   = pos
    out["turnover"]   = turnover
    out["net_return"] = pos * out["forward_return"] - turnover * (TC_BPS / 10_000.0)
    equity = (1.0 + out["net_return"]).cumprod() * 100_000.0
    out["equity"] = equity
    out["prob_up"] = np.nan
    out["label"]   = (out["forward_return"] > 0.0).astype(float)

    dd    = equity / equity.cummax() - 1.0
    years = len(out) / 365.25
    cagr  = (equity.iloc[-1] / equity.iloc[0]) ** (1.0 / years) - 1.0 if years else np.nan
    m = {
        "variant":       "Z_naive_7d_momentum",
        "final":         float(equity.iloc[-1]),
        "cagr":          float(cagr),
        "sharpe":        signed_sharpe(out["net_return"]),
        "maxdd":         float(dd.min()),
        "calmar":        float(cagr / abs(dd.min())) if dd.min() < 0 else np.nan,
        "avg_turnover":  float(out["turnover"].mean()),
        "auc":           float("nan"),
        "hit_rate":      float("nan"),
        "spearman_rho":  float("nan"),
        "n_days":        int(len(out)),
    }
    return out, m


def yearly_metrics(pred: pd.DataFrame, variant: str) -> pd.DataFrame:
    rows = []
    for year, g in pred.groupby(pred.index.year):
        if len(g) < 20:
            continue
        eq   = (1.0 + g["net_return"]).cumprod() * 100_000.0
        valid = g["label"].notna() & g.get("prob_up", pd.Series(np.nan, index=g.index)).notna()
        auc  = roc_auc_score(g.loc[valid, "label"].astype(int), g.loc[valid, "prob_up"]) \
               if valid.sum() > 5 and g.loc[valid, "label"].nunique() > 1 and "prob_up" in g.columns else np.nan
        rows.append({
            "variant": variant, "year": int(year),
            "sharpe":  signed_sharpe(g["net_return"]),
            "cagr":    float((eq.iloc[-1] / eq.iloc[0]) ** (365.25 / len(g)) - 1.0),
            "maxdd":   float((eq / eq.cummax() - 1.0).min()),
            "auc":     float(auc),
        })
    return pd.DataFrame(rows)


def spearman_feature_ranking(X: pd.DataFrame, y: pd.Series, feature_names: list[str]) -> pd.DataFrame:
    """Rank features by |Spearman rho| with next-day label on OOS period only."""
    oos = (X.index >= TEST_START) & y.notna()
    rows = []
    for f in feature_names:
        col = X.loc[oos, f].replace([np.inf, -np.inf], np.nan).dropna()
        common_idx = col.index.intersection(y[oos].dropna().index)
        if len(common_idx) < 50:
            rows.append({"feature": f, "spearman_rho": np.nan, "p_value": np.nan})
            continue
        rho, pval = spearmanr(col.loc[common_idx], y.loc[common_idx])
        rows.append({"feature": f, "spearman_rho": float(rho), "p_value": float(pval)})
    return pd.DataFrame(rows).sort_values("spearman_rho", key=abs, ascending=False)


def make_daily_panel(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series, pd.Series]:
    features     = build_features(df)
    future_return = df["ret_eth"].fillna(0.0).rolling(HORIZON_H).sum().shift(-HORIZON_H)
    daily         = df.index.hour == REBALANCE_HOUR
    X             = features.loc[daily].copy()
    y_return      = future_return.loc[daily].copy()
    y             = (y_return > 0.0).astype(float)
    y.loc[y_return.isna()] = np.nan
    return X, y, y_return


def deployment_decision(summary: pd.DataFrame, yearly: pd.DataFrame) -> dict:
    baseline   = summary.loc[summary["variant"] == "Z_naive_7d_momentum"].iloc[0]
    candidates = summary[summary["variant"] != "Z_naive_7d_momentum"].copy()
    pos_years  = yearly.groupby("variant")["sharpe"].apply(lambda x: int((x > 0.0).sum()))
    candidates["positive_years"]            = candidates["variant"].map(pos_years).fillna(0).astype(int)
    candidates["passes_auc"]               = candidates["auc"]      >= AUC_GATE
    candidates["passes_hit"]               = candidates["hit_rate"] >= HIT_GATE
    candidates["passes_sharpe_increment"]  = candidates["sharpe"]   >= baseline["sharpe"] + 0.10
    candidates["passes_year_consistency"]  = candidates["positive_years"] >= POS_YEARS_GATE
    candidates["passes_all"]               = (
        candidates["passes_auc"]
        & candidates["passes_hit"]
        & candidates["passes_sharpe_increment"]
        & candidates["passes_year_consistency"]
    )
    viable = candidates[candidates["passes_all"]]
    if viable.empty:
        # Report which gate individual candidates came closest to meeting.
        best = candidates.sort_values("sharpe", ascending=False).iloc[0]
        return {
            "deployable":        False,
            "selected_variant":  None,
            "fallback":          "canonical_tanh_momentum",
            "best_candidate":    best["variant"],
            "best_auc":          float(best["auc"]),
            "best_sharpe":       float(best["sharpe"]),
            "best_positive_years": int(best["positive_years"]),
            "gates_status": {
                "auc_gate":            float(AUC_GATE),
                "hit_gate":            float(HIT_GATE),
                "sharpe_increment":    float(0.10),
                "year_consistency":    int(POS_YEARS_GATE),
            },
            "reason": (
                f"No variant passed all gates. Best was {best['variant']} "
                f"(AUC={best['auc']:.3f}, Sharpe={best['sharpe']:.3f}, "
                f"pos_years={int(best['positive_years'])})."
            ),
        }
    chosen = viable.sort_values("sharpe", ascending=False).iloc[0]
    return {
        "deployable":        True,
        "selected_variant":  chosen["variant"],
        "auc":               float(chosen["auc"]),
        "sharpe":            float(chosen["sharpe"]),
        "positive_years":    int(chosen["positive_years"]),
        "fallback":          None,
        "reason":            "Selected variant passes all predeclared gates.",
    }


def print_summary(rows: list[dict]) -> None:
    print("\n=== Walk-forward interaction ablation (OOS only, daily non-overlapping) ===")
    print(f"{'variant':<28}{'final$':>10}{'sharpe':>8}{'cagr':>8}{'maxdd':>8}{'auc':>8}{'hit':>7}{'spear':>8}{'t/o':>7}")
    print("-" * 100)
    for r in rows:
        def fmt(v, fmt_str):
            return fmt_str.format(v) if not (isinstance(v, float) and np.isnan(v)) else "     nan"
        print(
            f"{r['variant']:<28}"
            f"{fmt(r['final'], '{:>10,.0f}')}"
            f"{fmt(r['sharpe'], '{:>8.3f}')}"
            f"{fmt(r['cagr']*100, '{:>7.2f}%')}"
            f"{fmt(r['maxdd']*100, '{:>7.2f}%')}"
            f"{fmt(r['auc'], '{:>8.3f}')}"
            f"{fmt(r['hit_rate'], '{:>7.3f}')}"
            f"{fmt(r['spearman_rho'], '{:>8.4f}')}"
            f"{fmt(r['avg_turnover'], '{:>7.4f}')}"
        )


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df = pd.read_parquet(DATA_PATH).sort_index()
    X, y, forward_ret = make_daily_panel(df)

    # Feature-level Spearman diagnostic before any model is fit.
    all_feature_cols = [c for c in X.columns if c not in ("vol_24",)]
    rank_df = spearman_feature_ranking(X, y, all_feature_cols)
    rank_df.to_csv(OUT_DIR / "feature_spearman_ranking.csv", index=False)
    print("\n=== Feature Spearman rho vs next-day label (top 15) ===")
    print(rank_df.head(15).to_string(index=False))

    rows = []
    all_yearly = []
    for name, cols in VARIANTS.items():
        print(f"\n  → running {name} ({len(cols)} features) ...")
        pred, row, coefs = walk_forward(X, y, forward_ret, cols, name)
        if pred.empty:
            print(f"    [SKIP] {name}: {row.get('error')}")
            continue
        pred.to_csv(OUT_DIR / f"{name}_predictions.csv")
        coefs.to_csv(OUT_DIR / f"{name}_coefficients.csv")
        rows.append(row)
        all_yearly.append(yearly_metrics(pred, name))

    baseline_pred, baseline_row = naive_momentum_baseline(X, forward_ret)
    baseline_pred.to_csv(OUT_DIR / "Z_naive_7d_momentum_predictions.csv")
    rows.append(baseline_row)
    all_yearly.append(yearly_metrics(baseline_pred, "Z_naive_7d_momentum"))

    summary = pd.DataFrame(rows)
    yearly  = pd.concat(all_yearly, ignore_index=True)
    summary.to_csv(OUT_DIR / "summary.csv", index=False)
    yearly.to_csv(OUT_DIR / "yearly_metrics.csv", index=False)

    print_summary(rows)
    print("\n=== Year-by-year (Sharpe) ===")
    pivot = yearly.pivot_table(index="variant", columns="year", values="sharpe", aggfunc="first")
    print(pivot.to_string())

    decision = deployment_decision(summary, yearly)
    (OUT_DIR / "summary.json").write_text(json.dumps(rows, indent=2))
    (OUT_DIR / "deployment_decision.json").write_text(json.dumps(decision, indent=2))
    print("\nDeployment decision:", json.dumps(decision, indent=2))


if __name__ == "__main__":
    main()
