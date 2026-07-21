"""
run_crypto_directional_model_v3_tbml.py
=======================================
PhD-grade directional modeling upgrade:

1) Triple-barrier event labeling (TBML) with a directional side prior.
2) Purged/embargo time-series cross-validation for model selection.
3) Two independent model families (logistic + gradient boosting), blended.
4) Causal feature lagging, non-overlapping daily events, transaction costs.
5) Hard deployment gate with statistical and economic constraints.

This separates concerns correctly:
- SIDE model (signed direction): from stable momentum prior.
- META model (probability that taking that side is profitable): from
  independent features + TBML labels.

Final position at each event t:

    side_t = sign(mom_168_t)
    p_t    = 0.5 * p_logit_t + 0.5 * p_hgb_t
    conf_t = clip((p_t - p_cut)/(1-p_cut), 0, 1)
    pos_t  = side_t * conf_t * vol_target_scale_t * risk_gate_t

where risk_gate_t is non-negative only (never flips side).
"""
from __future__ import annotations

import json
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

DATA_PATH = Path(r"C:\amttp\data\processed\unified_crypto_1h_20210101_to_20260601.parquet")
OUT_DIR = Path(__file__).parent / "directional_model_v3_tbml"

# Event sampling and forecasting horizon
EVENT_HOUR = 0
HORIZON_H = 24

# Walk-forward controls
TRAIN_START = pd.Timestamp("2021-01-01")
TEST_START = pd.Timestamp("2023-01-01")
MIN_TRAIN_DAYS = 365
MAX_TRAIN_DAYS = 730
REFIT_EVERY_DAYS = 30

# Triple barrier controls
TP_SIGMA = 1.2
SL_SIGMA = 1.0
MIN_EDGE_COST_BPS = 8.0

# Trading controls
TC_BPS = 5.0
TARGET_DAILY_VOL = 0.01
MAX_GROSS = 1.0
P_CUT = 0.52

# Deployment gates
AUC_GATE = 0.53
HIT_GATE = 0.53
SHARPE_IMPROVEMENT_GATE = 0.10
POS_YEARS_GATE = 3

warnings.filterwarnings("ignore", category=UserWarning, module=r"sklearn\\.impute")


def _finite(x: pd.Series) -> pd.Series:
    return x.replace([np.inf, -np.inf], np.nan)


def signed_sharpe(x: pd.Series) -> float:
    s = x.std(ddof=0)
    return float(x.mean() / s * np.sqrt(365.25)) if s > 1e-12 else 0.0


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """Causal predictor matrix (all features shifted by 1 hour)."""
    r_eth = df["ret_eth"].fillna(0.0)
    r_btc = df["ret_btc"].fillna(0.0)

    def risk_adj_mom(r: pd.Series, h: int) -> pd.Series:
        c = r.rolling(h, min_periods=max(12, h // 3)).sum()
        s = r.rolling(h, min_periods=max(12, h // 3)).std() * np.sqrt(h)
        return _finite(c / s.replace(0.0, np.nan))

    vol_24 = r_eth.rolling(24, min_periods=12).std()
    vol_168 = r_eth.rolling(168, min_periods=48).std()
    vol_regime = (vol_24 / vol_168.replace(0.0, np.nan)).clip(0.1, 5.0)

    f = pd.DataFrame(index=df.index)
    f["mom_24"] = risk_adj_mom(r_eth, 24)
    f["mom_72"] = risk_adj_mom(r_eth, 72)
    f["mom_168"] = risk_adj_mom(r_eth, 168)
    f["rel_mom_72"] = risk_adj_mom(r_eth - r_btc, 72)

    f["vol_24"] = vol_24
    f["vol_168"] = vol_168
    f["vol_regime"] = vol_regime

    f["vol_eth_z"] = df.get("vol_eth_z", pd.Series(np.nan, index=df.index))
    f["btc_dom_z"] = df.get("btc_dom_z", pd.Series(np.nan, index=df.index))
    f["cross_disp_z"] = df.get("cross_disp_z", pd.Series(np.nan, index=df.index))

    funding = _finite(df.get("ms_eth_funding_rate", pd.Series(np.nan, index=df.index)))
    fz_num = funding - funding.rolling(168, min_periods=48).mean()
    fz_den = funding.rolling(168, min_periods=48).std().replace(0.0, np.nan)
    f["funding_z"] = _finite(fz_num / fz_den)

    tbr = df.get("ms_eth_taker_buy_ratio", pd.Series(np.nan, index=df.index))
    f["taker_imbalance"] = _finite(2.0 * tbr - 1.0)

    f["oi_pct_1h"] = _finite(df.get("ms_eth_oi_pct_1h", pd.Series(np.nan, index=df.index))).clip(-0.10, 0.10)
    f["oi_z"] = _finite(df.get("ms_eth_oi_z", pd.Series(np.nan, index=df.index))).clip(-5.0, 5.0)
    f["lsr_z"] = _finite(df.get("ms_eth_lsr_z", pd.Series(np.nan, index=df.index))).clip(-5.0, 5.0)
    f["top_lsr_z"] = _finite(df.get("ms_eth_top_lsr_z", pd.Series(np.nan, index=df.index))).clip(-5.0, 5.0)
    f["taker_ls_z"] = _finite(df.get("ms_eth_taker_ls_z", pd.Series(np.nan, index=df.index))).clip(-5.0, 5.0)

    # Interaction set (best empirical candidates + conservative extras)
    f["x_funding_mom"] = -f["funding_z"] * f["mom_168"]
    f["x_toplsr_oi"] = f["top_lsr_z"] * f["oi_pct_1h"] * 10.0
    f["x_taker_mom"] = f["taker_imbalance"] * f["mom_168"]
    f["x_lsr_vol"] = -f["lsr_z"] * (f["vol_regime"] - 1.0).clip(0.0, 3.0)

    return f.replace([np.inf, -np.inf], np.nan).shift(1)


def event_index(df: pd.DataFrame) -> pd.DatetimeIndex:
    return df.index[df.index.hour == EVENT_HOUR]


def build_side(df_feat: pd.DataFrame) -> pd.Series:
    """Directional side prior from robust momentum.

    This keeps direction source simple and stable while the meta model decides
    when to act on it.
    """
    s = np.sign(df_feat["mom_168"].fillna(0.0))
    s[s == 0] = 1.0
    return s


@dataclass
class TripleBarrierResult:
    meta_label: pd.Series
    realized_side_ret: pd.Series
    event_end_time: pd.Series


def triple_barrier_meta_labels(
    ret_hourly: pd.Series,
    event_times: Iterable[pd.Timestamp],
    side: pd.Series,
    sigma_event: pd.Series,
    horizon_h: int = HORIZON_H,
    tp_sigma: float = TP_SIGMA,
    sl_sigma: float = SL_SIGMA,
) -> TripleBarrierResult:
    """Compute meta-label y in {0,1} based on which barrier is hit first.

    For each event t:
      path_u = side_t * cumulative_return(t+1..u), u in [1..horizon]
      TP = +tp_sigma * sigma_t
      SL = -sl_sigma * sigma_t

    y_t = 1 if TP hit first or vertical barrier return > min edge threshold
          0 otherwise.
    """
    idx = ret_hourly.index
    pos = pd.Series(np.arange(len(idx)), index=idx)

    y = pd.Series(np.nan, index=event_times, dtype=float)
    side_ret = pd.Series(np.nan, index=event_times, dtype=float)
    end_time = pd.Series(pd.NaT, index=event_times)

    min_edge = MIN_EDGE_COST_BPS / 10_000.0

    for t in event_times:
        if t not in pos:
            continue
        i0 = int(pos[t])
        i1 = min(i0 + horizon_h, len(idx) - 1)
        if i1 <= i0:
            continue

        path = ret_hourly.iloc[i0 + 1 : i1 + 1].fillna(0.0).cumsum()
        s = float(side.loc[t])
        signed_path = s * path

        sig = float(sigma_event.loc[t]) if np.isfinite(sigma_event.loc[t]) else np.nan
        if not np.isfinite(sig) or sig <= 0:
            continue
        tp = tp_sigma * sig
        sl = -sl_sigma * sig

        hit_tp = signed_path[signed_path >= tp]
        hit_sl = signed_path[signed_path <= sl]

        if len(hit_tp) and len(hit_sl):
            first_tp = hit_tp.index[0]
            first_sl = hit_sl.index[0]
            first = min(first_tp, first_sl)
            r_final = float(signed_path.loc[first])
            y.loc[t] = 1.0 if first_tp <= first_sl else 0.0
            end_time.loc[t] = first
        elif len(hit_tp):
            first = hit_tp.index[0]
            r_final = float(signed_path.loc[first])
            y.loc[t] = 1.0
            end_time.loc[t] = first
        elif len(hit_sl):
            first = hit_sl.index[0]
            r_final = float(signed_path.loc[first])
            y.loc[t] = 0.0
            end_time.loc[t] = first
        else:
            r_final = float(signed_path.iloc[-1])
            y.loc[t] = 1.0 if r_final > min_edge else 0.0
            end_time.loc[t] = idx[i1]

        side_ret.loc[t] = r_final

    return TripleBarrierResult(meta_label=y, realized_side_ret=side_ret, event_end_time=end_time)


def make_daily_panel(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series, pd.Series, pd.Series]:
    feat = build_features(df)
    eidx = event_index(df)

    X = feat.loc[eidx].copy()
    side = build_side(feat).reindex(eidx)

    sigma_event = (df["ret_eth"].rolling(24, min_periods=12).std() * np.sqrt(HORIZON_H)).reindex(eidx)

    tb = triple_barrier_meta_labels(
        ret_hourly=df["ret_eth"].fillna(0.0),
        event_times=eidx,
        side=side,
        sigma_event=sigma_event,
    )

    y_meta = tb.meta_label
    side_ret = tb.realized_side_ret
    return X, y_meta, side, side_ret


def logit_pipeline(C: float) -> Pipeline:
    return Pipeline([
        ("imputer", SimpleImputer(strategy="median", add_indicator=True)),
        ("scale", StandardScaler()),
        ("clf", LogisticRegression(C=C, penalty="l2", solver="lbfgs", max_iter=1000)),
    ])


def hgb_model(max_depth: int, lr: float) -> HistGradientBoostingClassifier:
    return HistGradientBoostingClassifier(
        learning_rate=lr,
        max_depth=max_depth,
        max_iter=250,
        min_samples_leaf=20,
        l2_regularization=0.1,
        random_state=42,
    )


def purged_splits(index: pd.DatetimeIndex, n_splits: int = 4, embargo_days: int = 2) -> list[tuple[np.ndarray, np.ndarray]]:
    n = len(index)
    fold = n // n_splits
    out = []
    for k in range(n_splits):
        i0 = k * fold
        i1 = (k + 1) * fold if k < n_splits - 1 else n
        test_idx = np.arange(i0, i1)

        t0 = index[i0]
        t1 = index[i1 - 1]
        emb = pd.Timedelta(days=embargo_days)

        train_mask = (index < t0 - emb) | (index > t1 + emb)
        train_idx = np.where(train_mask)[0]
        if len(train_idx) > 50 and len(test_idx) > 20:
            out.append((train_idx, test_idx))
    return out


def cv_auc_for_model(X: pd.DataFrame, y: pd.Series) -> dict:
    """Purged CV hyperparameter selection for two independent learners."""
    data = X.copy()
    target = y.copy()
    ok = target.notna()
    data = data.loc[ok]
    target = target.loc[ok]

    # Smaller split count keeps walk-forward runtime bounded while preserving
    # time-order validation with purge + embargo.
    splits = purged_splits(data.index, n_splits=3, embargo_days=2)

    # Drop columns with no observed values in the current train block.
    keep_cols = [c for c in data.columns if data[c].notna().any()]
    data = data[keep_cols]

    best_logit = {"C": 0.05, "auc": -np.inf}
    for C in (0.05, 0.1):
        aucs = []
        for tr, te in splits:
            mdl = logit_pipeline(C)
            mdl.fit(data.iloc[tr], target.iloc[tr].astype(int))
            p = mdl.predict_proba(data.iloc[te])[:, 1]
            y_te = target.iloc[te].astype(int)
            if y_te.nunique() > 1:
                aucs.append(roc_auc_score(y_te, p))
        if aucs:
            a = float(np.mean(aucs))
            if a > best_logit["auc"]:
                best_logit = {"C": C, "auc": a}

    best_hgb = {"max_depth": 3, "lr": 0.05, "auc": -np.inf}
    for d in (2, 3):
        for lr in (0.05, 0.08):
            aucs = []
            for tr, te in splits:
                imp = SimpleImputer(strategy="median")
                Xtr = imp.fit_transform(data.iloc[tr])
                Xte = imp.transform(data.iloc[te])
                mdl = hgb_model(d, lr)
                mdl.fit(Xtr, target.iloc[tr].astype(int))
                p = mdl.predict_proba(Xte)[:, 1]
                y_te = target.iloc[te].astype(int)
                if y_te.nunique() > 1:
                    aucs.append(roc_auc_score(y_te, p))
            if aucs:
                a = float(np.mean(aucs))
                if a > best_hgb["auc"]:
                    best_hgb = {"max_depth": d, "lr": lr, "auc": a}

    return {"logit": best_logit, "hgb": best_hgb, "keep_cols": keep_cols}


def simulate_meta_strategy(
    X: pd.DataFrame,
    y_meta: pd.Series,
    side: pd.Series,
    side_ret: pd.Series,
) -> tuple[pd.DataFrame, dict]:
    """Walk-forward training with monthly refits + blended meta probabilities."""
    rows = []
    last_refit = None
    logit_fit = None
    hgb_fit = None
    hgb_imp = None

    # Volatility/risk scaling at event times
    vol_scale = (TARGET_DAILY_VOL / X["vol_24"].replace(0.0, np.nan)).clip(upper=1.0).fillna(0.0)
    risk_gate = (1.0 / X["vol_regime"].clip(lower=0.8, upper=2.0)).clip(0.5, 1.0).fillna(0.7)

    for t in X.index:
        if t < TEST_START:
            continue

        eligible = (
            (X.index >= TRAIN_START)
            & (X.index < t - pd.Timedelta(hours=HORIZON_H))
            & y_meta.notna()
            & side_ret.notna()
        )
        tr_idx = X.index[eligible]
        if len(tr_idx) > MAX_TRAIN_DAYS:
            tr_idx = tr_idx[-MAX_TRAIN_DAYS:]
        if len(tr_idx) < MIN_TRAIN_DAYS or y_meta.loc[tr_idx].nunique() < 2:
            continue

        if logit_fit is None or (t - last_refit).days >= REFIT_EVERY_DAYS:
            params = cv_auc_for_model(X.loc[tr_idx], y_meta.loc[tr_idx])

            keep_cols = params["keep_cols"]
            if len(keep_cols) < 4:
                # Too little observable information for a reliable refit.
                continue
            X_train = X.loc[tr_idx, keep_cols]

            logit_fit = logit_pipeline(params["logit"]["C"])
            logit_fit.fit(X_train, y_meta.loc[tr_idx].astype(int))

            hgb_imp = SimpleImputer(strategy="median")
            Xtr_hgb = hgb_imp.fit_transform(X_train)
            hgb_fit = hgb_model(params["hgb"]["max_depth"], params["hgb"]["lr"])
            hgb_fit.fit(Xtr_hgb, y_meta.loc[tr_idx].astype(int))

            last_refit = t

        x_now = X.loc[[t], keep_cols]
        p1 = float(logit_fit.predict_proba(x_now)[:, 1][0])
        p2 = float(hgb_fit.predict_proba(hgb_imp.transform(x_now))[:, 1][0])
        p = 0.5 * (p1 + p2)

        conf = float(np.clip((p - P_CUT) / (1.0 - P_CUT), 0.0, 1.0))
        s = float(side.loc[t]) if np.isfinite(side.loc[t]) else 0.0
        pos = s * conf * float(vol_scale.loc[t]) * float(risk_gate.loc[t])
        pos = float(np.clip(pos, -MAX_GROSS, MAX_GROSS))

        rows.append((t, p1, p2, p, conf, s, pos, y_meta.loc[t], side_ret.loc[t]))

    pred = pd.DataFrame(
        rows,
        columns=["timestamp", "p_logit", "p_hgb", "p_meta", "confidence", "side", "position", "label", "side_ret"],
    ).set_index("timestamp")

    if pred.empty:
        return pred, {"error": "no_oos_predictions"}

    pred["turnover"] = pred["position"].diff().abs().fillna(pred["position"].abs())
    pred["net_return"] = pred["position"] * pred["side_ret"] - pred["turnover"] * (TC_BPS / 10_000.0)
    pred["equity"] = (1.0 + pred["net_return"]).cumprod() * 100_000.0

    valid = pred["label"].notna()
    auc = roc_auc_score(pred.loc[valid, "label"].astype(int), pred.loc[valid, "p_meta"]) if valid.sum() and pred.loc[valid, "label"].nunique() > 1 else np.nan
    hit = ((pred.loc[valid, "p_meta"] >= 0.5) == pred.loc[valid, "label"].astype(bool)).mean() if valid.sum() else np.nan
    rho = spearmanr(pred.loc[valid, "p_meta"], pred.loc[valid, "label"]).statistic if valid.sum() > 20 else np.nan

    eq = pred["equity"]
    dd = eq / eq.cummax() - 1.0
    years = len(pred) / 365.25
    cagr = (eq.iloc[-1] / eq.iloc[0]) ** (1.0 / years) - 1.0 if years else np.nan

    m = {
        "variant": "v3_tbml_meta_ensemble",
        "final": float(eq.iloc[-1]),
        "cagr": float(cagr),
        "sharpe": signed_sharpe(pred["net_return"]),
        "maxdd": float(dd.min()),
        "calmar": float(cagr / abs(dd.min())) if dd.min() < 0 else np.nan,
        "auc": float(auc),
        "hit_rate": float(hit),
        "spearman_rho": float(rho),
        "avg_turnover": float(pred["turnover"].mean()),
        "n_days": int(len(pred)),
    }
    return pred, m


def naive_baseline(X: pd.DataFrame, side_ret: pd.Series, side: pd.Series) -> tuple[pd.DataFrame, dict]:
    idx = X.index[X.index >= TEST_START]
    out = pd.DataFrame(index=idx)
    vol_scale = (TARGET_DAILY_VOL / X.loc[idx, "vol_24"].replace(0.0, np.nan)).clip(upper=1.0).fillna(0.0)
    out["position"] = side.loc[idx].fillna(0.0) * vol_scale
    out["side_ret"] = side_ret.loc[idx]
    out["turnover"] = out["position"].diff().abs().fillna(out["position"].abs())
    out["net_return"] = out["position"] * out["side_ret"] - out["turnover"] * (TC_BPS / 10_000.0)
    out["equity"] = (1.0 + out["net_return"]).cumprod() * 100_000.0

    eq = out["equity"]
    dd = eq / eq.cummax() - 1.0
    years = len(out) / 365.25
    cagr = (eq.iloc[-1] / eq.iloc[0]) ** (1.0 / years) - 1.0 if years else np.nan

    m = {
        "variant": "z_baseline_mom_side",
        "final": float(eq.iloc[-1]),
        "cagr": float(cagr),
        "sharpe": signed_sharpe(out["net_return"]),
        "maxdd": float(dd.min()),
        "calmar": float(cagr / abs(dd.min())) if dd.min() < 0 else np.nan,
        "auc": float("nan"),
        "hit_rate": float("nan"),
        "spearman_rho": float("nan"),
        "avg_turnover": float(out["turnover"].mean()),
        "n_days": int(len(out)),
    }
    return out, m


def yearly_metrics(pred: pd.DataFrame, variant: str, with_prob: bool) -> pd.DataFrame:
    rows = []
    for year, g in pred.groupby(pred.index.year):
        if len(g) < 20:
            continue
        eq = (1.0 + g["net_return"]).cumprod() * 100_000.0
        dd = eq / eq.cummax() - 1.0
        auc = np.nan
        if with_prob and "p_meta" in g and g["label"].notna().sum() > 10 and g["label"].nunique() > 1:
            auc = roc_auc_score(g["label"].astype(int), g["p_meta"])
        rows.append({
            "variant": variant,
            "year": int(year),
            "sharpe": signed_sharpe(g["net_return"]),
            "cagr": float((eq.iloc[-1] / eq.iloc[0]) ** (365.25 / len(g)) - 1.0),
            "maxdd": float(dd.min()),
            "auc": float(auc),
        })
    return pd.DataFrame(rows)


def deployment_decision(summary: pd.DataFrame, yearly: pd.DataFrame) -> dict:
    model_row = summary.loc[summary["variant"] == "v3_tbml_meta_ensemble"].iloc[0]
    base_row = summary.loc[summary["variant"] == "z_baseline_mom_side"].iloc[0]

    pos_years = int((yearly[yearly["variant"] == "v3_tbml_meta_ensemble"]["sharpe"] > 0).sum())

    passes_auc = bool(model_row["auc"] >= AUC_GATE)
    passes_hit = bool(model_row["hit_rate"] >= HIT_GATE)
    passes_sharpe_increment = bool(model_row["sharpe"] >= base_row["sharpe"] + SHARPE_IMPROVEMENT_GATE)
    passes_years = bool(pos_years >= POS_YEARS_GATE)
    deployable = passes_auc and passes_hit and passes_sharpe_increment and passes_years

    return {
        "deployable": deployable,
        "selected_variant": "v3_tbml_meta_ensemble" if deployable else None,
        "fallback": None if deployable else "canonical_tanh_momentum",
        "model_auc": float(model_row["auc"]),
        "model_hit_rate": float(model_row["hit_rate"]),
        "model_sharpe": float(model_row["sharpe"]),
        "baseline_sharpe": float(base_row["sharpe"]),
        "positive_years": pos_years,
        "gates": {
            "auc": float(AUC_GATE),
            "hit_rate": float(HIT_GATE),
            "sharpe_increment": float(SHARPE_IMPROVEMENT_GATE),
            "positive_years": int(POS_YEARS_GATE),
        },
        "passed": {
            "auc": passes_auc,
            "hit_rate": passes_hit,
            "sharpe_increment": passes_sharpe_increment,
            "positive_years": passes_years,
        },
    }


def print_summary(rows: list[dict]) -> None:
    print("\n=== v3 TBML Meta-Label Ensemble (OOS) ===")
    print(f"{'variant':<26}{'final$':>11}{'sharpe':>9}{'cagr':>9}{'maxdd':>9}{'auc':>8}{'hit':>8}{'spear':>8}{'t/o':>8}")
    print("-" * 102)
    for r in rows:
        def f(v, fmt):
            return fmt.format(v) if not (isinstance(v, float) and np.isnan(v)) else "    nan"
        print(
            f"{r['variant']:<26}{f(r['final'], '{:>11,.0f}')}{f(r['sharpe'], '{:>9.3f}')}{f(r['cagr']*100, '{:>8.2f}%')}"
            f"{f(r['maxdd']*100, '{:>8.2f}%')}{f(r['auc'], '{:>8.3f}')}{f(r['hit_rate'], '{:>8.3f}')}{f(r['spearman_rho'], '{:>8.4f}')}{f(r['avg_turnover'], '{:>8.4f}') }"
        )


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df = pd.read_parquet(DATA_PATH).sort_index()

    X, y_meta, side, side_ret = make_daily_panel(df)

    pred_model, m_model = simulate_meta_strategy(X, y_meta, side, side_ret)
    pred_base, m_base = naive_baseline(X, side_ret, side)

    if pred_model.empty:
        raise RuntimeError("No OOS predictions generated; check label availability and train window.")

    pred_model.to_csv(OUT_DIR / "v3_tbml_meta_ensemble_predictions.csv")
    pred_base.to_csv(OUT_DIR / "z_baseline_mom_side_predictions.csv")

    summary = pd.DataFrame([m_model, m_base])
    summary.to_csv(OUT_DIR / "summary.csv", index=False)
    (OUT_DIR / "summary.json").write_text(json.dumps([m_model, m_base], indent=2))

    yearly = pd.concat([
        yearly_metrics(pred_model, "v3_tbml_meta_ensemble", with_prob=True),
        yearly_metrics(pred_base, "z_baseline_mom_side", with_prob=False),
    ], ignore_index=True)
    yearly.to_csv(OUT_DIR / "yearly_metrics.csv", index=False)

    decision = deployment_decision(summary, yearly)
    (OUT_DIR / "deployment_decision.json").write_text(json.dumps(decision, indent=2))

    print_summary([m_model, m_base])
    print("\n=== Yearly Sharpe ===")
    print(yearly.pivot_table(index="variant", columns="year", values="sharpe", aggfunc="first").to_string())
    print("\nDeployment decision:", json.dumps(decision, indent=2))


if __name__ == "__main__":
    main()
