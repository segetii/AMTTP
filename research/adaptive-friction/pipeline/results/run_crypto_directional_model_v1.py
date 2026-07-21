"""
Causal, walk-forward direction model for the crypto BSDT stack.

This is deliberately separate from the canonical ODE:
  * An independently trained signed predictor D_t supplies price direction.
  * BSDT/energy quantities are allowed to scale risk only; they never select
    long versus short.

Forecast target
---------------
At each daily rebalance timestamp t, predict whether the *next non-overlapping*
24-hour ETH return is positive:

    y_t = 1[ sum_{j=1}^{24} r_ETH(t+j) > 0 ].

All predictors are lagged by one hour. Training examples are sampled once per
24 hours, so labels do not overlap. A logistic classifier is retrained only
from observations available at t - 24h, eliminating target leakage.

Target construction for canonical integration
---------------------------------------------
    D_t       = beta_0 + beta^T z_t                 # signed, odd predictor
    p_t       = sigmoid(D_t)                         # P(next-day return > 0)
    confidence= max(0, |2p_t - 1| - tau)/(1-tau)    # [0,1]
    q_t       = sign(2p_t-1) * confidence * v_t * g_t
    b_dir,t   = tau_dir * q_t

where `v_t` is inverse realised-volatility targeting and `g_t` is a bounded,
non-negative BSDT risk gate. Only `D_t` determines the side. This avoids the
invalid use of an even energy/cosine quantity as a direction source.

Run:
    py run_crypto_directional_model_v1.py

Outputs (under directional_model_v1/): out-of-sample daily predictions,
equity curves, coefficients, metrics and the independent feature ablations.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

DATA_PATH = Path(r"C:\amttp\data\processed\unified_crypto_1h_20210101_to_20260601.parquet")
OUT_DIR = Path(__file__).parent / "directional_model_v1"

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

# Groups make the ablation test prespecified rather than a feature search.
FEATURE_GROUPS = {
    "momentum": ["mom_24", "mom_72", "mom_168", "rel_mom_72"],
    "regime": ["vol_24", "vol_168", "vol_eth_z", "btc_dom_z", "cross_disp_z"],
    "microstructure": [
        "funding_z", "taker_imbalance", "oi_1h", "oi_24h", "oi_z",
        "lsr_z", "top_lsr_z", "taker_ls_z",
    ],
}


def signed_sharpe(x: pd.Series) -> float:
    vol = x.std(ddof=0)
    return float(x.mean() / vol * np.sqrt(365.25)) if vol > 1e-12 else 0.0


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """Build signed predictors, then lag all of them one bar.

    Normalised cumulative returns give momentum comparable across volatility
    regimes. Funding/OI/order-flow variables add an independent perp-market
    view that raw price momentum does not observe.
    """
    r_eth = df["ret_eth"].fillna(0.0)
    r_btc = df["ret_btc"].fillna(0.0)
    vol_24 = r_eth.rolling(24, min_periods=12).std()
    vol_168 = r_eth.rolling(168, min_periods=48).std()

    def risk_adjusted_sum(r: pd.Series, h: int) -> pd.Series:
        cumulative = r.rolling(h, min_periods=max(12, h // 3)).sum()
        scale = r.rolling(h, min_periods=max(12, h // 3)).std() * np.sqrt(h)
        return cumulative / scale.replace(0.0, np.nan)

    f = pd.DataFrame(index=df.index)
    f["mom_24"] = risk_adjusted_sum(r_eth, 24)
    f["mom_72"] = risk_adjusted_sum(r_eth, 72)
    f["mom_168"] = risk_adjusted_sum(r_eth, 168)
    f["rel_mom_72"] = risk_adjusted_sum(r_eth - r_btc, 72)
    f["vol_24"] = vol_24
    f["vol_168"] = vol_168

    # Existing standardized BSDT/regime fields.
    for col in ("vol_eth_z", "btc_dom_z", "cross_disp_z"):
        f[col] = df[col] if col in df else np.nan

    # Perpetual-futures fields. `reindex` allows the script to run against a
    # smaller historical dataset while clearly recording unavailable features.
    f["funding_z"] = df.get("ms_eth_funding_z", pd.Series(np.nan, index=df.index))
    tbr = df.get("ms_eth_taker_buy_ratio", pd.Series(np.nan, index=df.index))
    f["taker_imbalance"] = 2.0 * (tbr - 0.5)
    f["oi_1h"] = df.get("ms_eth_oi_pct_1h", pd.Series(np.nan, index=df.index))
    f["oi_24h"] = df.get("ms_eth_oi_pct_24h", pd.Series(np.nan, index=df.index))
    f["oi_z"] = df.get("ms_eth_oi_z", pd.Series(np.nan, index=df.index))
    f["lsr_z"] = df.get("ms_eth_lsr_z", pd.Series(np.nan, index=df.index))
    f["top_lsr_z"] = df.get("ms_eth_top_lsr_z", pd.Series(np.nan, index=df.index))
    f["taker_ls_z"] = df.get("ms_eth_taker_ls_z", pd.Series(np.nan, index=df.index))

    # Essential: no predictor at time t may observe bar t's close/data.
    return f.replace([np.inf, -np.inf], np.nan).shift(1)


def make_daily_panel(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series, pd.Series]:
    features = build_features(df)
    future_return = df["ret_eth"].fillna(0.0).rolling(HORIZON_H).sum().shift(-HORIZON_H)
    daily = df.index.hour == REBALANCE_HOUR
    X = features.loc[daily].copy()
    y_return = future_return.loc[daily].copy()
    y = (y_return > 0.0).astype(float)
    # Last HORIZON_H labels are unknowable; mark them missing rather than zero.
    y.loc[y_return.isna()] = np.nan
    return X, y, y_return


def model() -> Pipeline:
    # L2 regularisation prevents unstable signs in collinear momentum features.
    return Pipeline([
        ("imputer", SimpleImputer(strategy="median", add_indicator=True)),
        ("scale", StandardScaler()),
        ("logit", LogisticRegression(C=0.05, penalty="l2", solver="lbfgs", max_iter=1000)),
    ])


def simulate(daily_ret: pd.Series, position: pd.Series) -> tuple[pd.Series, pd.Series]:
    pos = position.reindex(daily_ret.index).fillna(0.0).clip(-MAX_GROSS, MAX_GROSS)
    turnover = pos.diff().abs().fillna(pos.abs())
    net = pos * daily_ret - turnover * (TC_BPS / 10_000.0)
    return net, (1.0 + net).cumprod() * 100_000.0


def metrics(net: pd.Series, equity: pd.Series, prob: pd.Series, y: pd.Series) -> dict:
    dd = equity / equity.cummax() - 1.0
    years = len(net) / 365.25
    cagr = (equity.iloc[-1] / equity.iloc[0]) ** (1.0 / years) - 1.0 if years else np.nan
    valid = prob.notna() & y.notna() & (y.nunique() > 1)
    auc = roc_auc_score(y[valid].astype(int), prob[valid]) if valid.sum() and y[valid].nunique() > 1 else np.nan
    hit = ((prob[valid] >= 0.5) == y[valid].astype(bool)).mean() if valid.sum() else np.nan
    return {
        "final": float(equity.iloc[-1]), "cagr": float(cagr),
        "sharpe": signed_sharpe(net), "maxdd": float(dd.min()),
        "calmar": float(cagr / abs(dd.min())) if dd.min() < 0 else np.nan,
        "avg_turnover": float(position_turnover(net, equity)),
        "auc": float(auc), "hit_rate": float(hit), "n_days": int(len(net)),
    }


def naive_momentum_baseline(X: pd.DataFrame, future_ret: pd.Series) -> tuple[pd.DataFrame, dict]:
    """Matched daily benchmark for the model.

    It uses the same rebalance clock, volatility cap, transaction-cost model,
    and out-of-sample interval. This is the appropriate comparison for judging
    whether statistical learning adds directional information beyond the
    existing 7-day price-momentum source.
    """
    out = pd.DataFrame(index=X.index[X.index >= TEST_START])
    out["forward_return"] = future_ret.reindex(out.index)
    direction = np.sign(X.loc[out.index, "mom_168"].fillna(0.0))
    daily_vol = X.loc[out.index, "vol_24"] * np.sqrt(24.0)
    vol_scale = (TARGET_DAILY_VOL / daily_vol.replace(0.0, np.nan)).clip(upper=1.0).fillna(0.0)
    out["position"] = direction * vol_scale
    out["turnover"] = out["position"].diff().abs().fillna(out["position"].abs())
    out["net_return"], out["equity"] = simulate(out["forward_return"], out["position"])
    # Momentum is a signed score rather than a probability. `prob_up` is only
    # present to keep the result schema identical to model variants.
    out["prob_up"] = np.nan
    out["label"] = (out["forward_return"] > 0.0).astype(float)
    m = metrics(out["net_return"], out["equity"], out["prob_up"], out["label"])
    m["variant"] = "Z_naive_7d_momentum"
    m["avg_turnover"] = float(out["turnover"].mean())
    return out, m


def position_turnover(net: pd.Series, equity: pd.Series) -> float:
    # Placeholder kept separate so metrics stays agnostic to construction.
    # Real turnover is set by the caller after constructing the position.
    return float("nan")


def walk_forward(X: pd.DataFrame, y: pd.Series, future_ret: pd.Series, feature_names: list[str], name: str) -> tuple[pd.DataFrame, dict, pd.DataFrame]:
    records = []
    coefficient_rows = []
    last_refit = None
    fitted = None

    for t in X.index:
        if t < TEST_START:
            continue
        # Information available at time t: features already lagged one hour;
        # labels must finish at or before t-HORIZON_H.
        eligible = (X.index >= TRAIN_START) & (X.index < t - pd.Timedelta(hours=HORIZON_H)) & y.notna()
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
            # Imputer adds missingness indicators; retain primary feature coefs.
            coefficient_rows.append(pd.Series(coefs[:len(feature_names)], index=feature_names, name=t))

        p = float(fitted.predict_proba(X.loc[[t], feature_names])[:, 1][0])
        records.append((t, p, y.loc[t], future_ret.loc[t]))

    pred = pd.DataFrame(records, columns=["timestamp", "prob_up", "label", "forward_return"]).set_index("timestamp")
    signed_edge = 2.0 * pred["prob_up"] - 1.0
    confidence = ((signed_edge.abs() - CONFIDENCE_THRESHOLD) / (1.0 - CONFIDENCE_THRESHOLD)).clip(0.0, 1.0)
    direction = np.sign(signed_edge)
    # Daily inverse-vol target: cap exposure, never amplify a weak forecast.
    rv = future_ret.index.to_series().map(lambda x: np.nan)  # index placeholder for alignment
    daily_vol = X["vol_24"].reindex(pred.index) * np.sqrt(24.0)
    vol_scale = (TARGET_DAILY_VOL / daily_vol.replace(0.0, np.nan)).clip(upper=1.0).fillna(0.0)
    pred["position"] = direction * confidence * vol_scale
    pred["turnover"] = pred["position"].diff().abs().fillna(pred["position"].abs())
    net, equity = simulate(pred["forward_return"], pred["position"])
    pred["net_return"] = net
    pred["equity"] = equity

    m = metrics(net, equity, pred["prob_up"], pred["label"])
    m["variant"] = name
    m["avg_turnover"] = float(pred["turnover"].mean())
    return pred, m, pd.DataFrame(coefficient_rows)


def print_summary(rows: list[dict]) -> None:
    print("\n=== Walk-forward direction ablation (OOS only; daily non-overlapping labels) ===")
    print(f"{'variant':<28}{'final $':>13}{'sharpe':>9}{'cagr':>9}{'maxdd':>9}{'auc':>8}{'hit':>8}{'turnover':>10}")
    print("-" * 102)
    for r in rows:
        print(f"{r['variant']:<28}{r['final']:>13,.0f}{r['sharpe']:>9.3f}{r['cagr']*100:>8.2f}%{r['maxdd']*100:>8.2f}%{r['auc']:>8.3f}{r['hit_rate']:>8.3f}{r['avg_turnover']:>10.4f}")


def yearly_metrics(pred: pd.DataFrame, variant: str) -> pd.DataFrame:
    """Year-by-year net performance exposes a result driven by one regime."""
    rows = []
    for year, g in pred.groupby(pred.index.year):
        if len(g) < 20:
            continue
        eq = (1.0 + g["net_return"]).cumprod() * 100_000.0
        m = metrics(g["net_return"], eq, g["prob_up"], g["label"])
        m.update(variant=variant, year=int(year))
        rows.append(m)
    return pd.DataFrame(rows)


def deployment_decision(summary: pd.DataFrame, yearly: pd.DataFrame) -> dict:
    """A predeclared gate; this prevents backtest-only activation.

    A model must demonstrate probability ordering (AUC >= 0.52), improve on
    the matched momentum benchmark by at least 0.10 Sharpe, and have positive
    Sharpe in at least 3 of the 4 completed calendar years. If no variant
    passes, the correct executable action is **flat for model alpha** and the
    existing momentum target remains the fallback direction source.
    """
    baseline = summary.loc[summary["variant"] == "Z_naive_7d_momentum"].iloc[0]
    candidates = summary[summary["variant"] != "Z_naive_7d_momentum"].copy()
    candidates["passes_auc"] = candidates["auc"] >= 0.52
    candidates["passes_sharpe_increment"] = candidates["sharpe"] >= baseline["sharpe"] + 0.10
    positive_years = yearly.groupby("variant")["sharpe"].apply(lambda x: int((x > 0.0).sum()))
    candidates["positive_years"] = candidates["variant"].map(positive_years).fillna(0).astype(int)
    candidates["passes_year_consistency"] = candidates["positive_years"] >= 3
    candidates["passes_all"] = (
        candidates["passes_auc"]
        & candidates["passes_sharpe_increment"]
        & candidates["passes_year_consistency"]
    )
    viable = candidates[candidates["passes_all"]]
    if viable.empty:
        return {
            "deployable": False,
            "selected_variant": None,
            "fallback": "canonical_tanh_momentum",
            "reason": "No independent model meets predeclared OOS AUC, matched-baseline Sharpe, and year-consistency gates.",
        }
    chosen = viable.sort_values("sharpe", ascending=False).iloc[0]
    return {
        "deployable": True,
        "selected_variant": chosen["variant"],
        "fallback": None,
        "reason": "Selected model passes predeclared OOS gates; retain live shadow monitoring.",
    }


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df = pd.read_parquet(DATA_PATH).sort_index()
    X, y, forward_ret = make_daily_panel(df)
    rows = []

    variants = {
        "A_momentum_only": FEATURE_GROUPS["momentum"],
        "B_momentum_regime": FEATURE_GROUPS["momentum"] + FEATURE_GROUPS["regime"],
        "C_full_independent": FEATURE_GROUPS["momentum"] + FEATURE_GROUPS["regime"] + FEATURE_GROUPS["microstructure"],
    }
    all_yearly = []
    for name, cols in variants.items():
        pred, row, coefs = walk_forward(X, y, forward_ret, cols, name)
        pred.to_csv(OUT_DIR / f"{name}_predictions.csv")
        coefs.to_csv(OUT_DIR / f"{name}_coefficients.csv")
        rows.append(row)
        all_yearly.append(yearly_metrics(pred, name))

    baseline_pred, baseline_row = naive_momentum_baseline(X, forward_ret)
    baseline_pred.to_csv(OUT_DIR / "Z_naive_7d_momentum_predictions.csv")
    rows.append(baseline_row)
    all_yearly.append(yearly_metrics(baseline_pred, baseline_row["variant"]))

    summary = pd.DataFrame(rows)
    summary.to_csv(OUT_DIR / "summary.csv", index=False)
    yearly = pd.concat(all_yearly, ignore_index=True)
    yearly.to_csv(OUT_DIR / "yearly_metrics.csv", index=False)
    decision = deployment_decision(summary, yearly)
    (OUT_DIR / "summary.json").write_text(json.dumps(rows, indent=2))
    (OUT_DIR / "deployment_decision.json").write_text(json.dumps(decision, indent=2))
    print_summary(rows)
    print("\nDeployment decision:", json.dumps(decision, indent=2))


if __name__ == "__main__":
    main()
