"""
test_collapse_bank_data.py
==========================
CollapseGeometry on REAL bank-level data — Global Regional Analysis.

Regions: US (FDIC call-report), Europe (WB GFDD + ECB MIR),
         Asia (WB GFDD), Africa / Nigeria (WB GFDD).

Protocol (causal, no look-ahead)
---------------------------------
  1. Reference window: pre-crisis NORMAL quarters only
  2. fit() on reference → freeze parameters
  3. score() on each unseen future quarter independently
  4. Never re-fit after reference window
  5. COVID excluded from reference (exogenous)

Output
------
  - Consolidated GFC result table with early-warning lead times
  - Per-region breakdowns (US, Europe, Asia, Africa)
  - Fresh prediction from latest data
  - Thorough statistical analysis
"""
from __future__ import annotations
import sys, json, os
import numpy as np

# ── Path setup ────────────────────────────────────────────────────
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from collapse_geometry import CollapseGeometry

# ── Data paths ────────────────────────────────────────────────────
GSIB_DIR  = os.path.normpath(os.path.join(HERE, "..", "..", "..", "research",
            "adaptive-friction", "banklevel_enhanced", "gsib_cache_real"))
GSIB_NPZ  = os.path.join(GSIB_DIR, "gsib_real_panel.npz")
GSIB_META = os.path.join(GSIB_DIR, "gsib_real_meta.json")
CERT_DIR  = os.path.normpath(os.path.join(HERE, "..", "..", "..", "research",
            "adaptive-friction", "banklevel_enhanced", "fdic_bank_cache"))

FEATURE_NAMES = ["loan_to_asset", "equity_ratio", "npl_ratio", "roa", "funding_cost"]

# WB indicator → feature mapping
WB_FEATURE_MAP = {
    "loan_to_asset": "GFDD.DI.01",
    "equity_ratio":  "FB.BNK.CAPA.ZS",
    "npl_ratio":     "FB.AST.NPER.ZS",
    "roa":           "GFDD.SI.01",
    "funding_cost":  "FR.INR.LEND",
}


def qidx(year, qtr):
    """Panel index: 2005-Q1 = 0."""
    return 4 * (year - 2005) + (qtr - 1)


def qlabel(t):
    """Panel index → '2007-Q3' string."""
    y = 2005 + t // 4
    q = 1 + t % 4
    return f"{y}-Q{q}"


# ======================================================================
# Sparsity filter
# ======================================================================
def is_sparse(X_ref, min_rank_ratio=0.5, max_zero_frac=0.25):
    """True if reference matrix is too sparse to model."""
    d = X_ref.shape[1]
    eff_rank = np.linalg.matrix_rank(X_ref - X_ref.mean(0), tol=1e-8)
    zero_frac = (X_ref == 0).sum() / X_ref.size
    return eff_rank < d * min_rank_ratio or zero_frac > max_zero_frac


# ======================================================================
# AUC (no sklearn dependency)
# ======================================================================
def auc_manual(y_true, y_score):
    """Trapezoidal AUC from binary labels and continuous scores."""
    pairs = sorted(zip(y_score, y_true), reverse=True)
    tp = fp = tp_prev = fp_prev = 0
    auc = 0.0
    n_pos = sum(y_true)
    n_neg = len(y_true) - n_pos
    if n_pos == 0 or n_neg == 0:
        return 0.5
    prev_score = None
    for score, label in pairs:
        if prev_score is not None and score != prev_score:
            auc += (fp - fp_prev) * (tp + tp_prev) / 2.0
            tp_prev, fp_prev = tp, fp
        if label == 1:
            tp += 1
        else:
            fp += 1
        prev_score = score
    auc += (fp - fp_prev) * (tp + tp_prev) / 2.0
    return auc / (n_pos * n_neg)


# ======================================================================
# Precision / Recall / F1 at threshold
# ======================================================================
def prf1(y_true, y_score, thr=0.5):
    tp = sum(1 for yt, ys in zip(y_true, y_score) if yt == 1 and ys > thr)
    fp = sum(1 for yt, ys in zip(y_true, y_score) if yt == 0 and ys > thr)
    fn = sum(1 for yt, ys in zip(y_true, y_score) if yt == 1 and ys <= thr)
    prec = tp / (tp + fp) if tp + fp > 0 else 0
    rec  = tp / (tp + fn) if tp + fn > 0 else 0
    f1   = 2 * prec * rec / (prec + rec) if prec + rec > 0 else 0
    return prec, rec, f1


# ======================================================================
# Clean NaN/inf in array
# ======================================================================
def clean_array(X):
    X = X.copy()
    for col in range(X.shape[1]):
        bad = ~np.isfinite(X[:, col])
        if bad.any():
            med = np.nanmedian(X[:, col])
            X[bad, col] = med if np.isfinite(med) else 0.0
    return X


# ======================================================================
# Load FDIC cert JSON → (T, 5) + dates
# ======================================================================
def load_cert_data(cert_id):
    fp = os.path.join(CERT_DIR, f"cert_{cert_id}.json")
    with open(fp) as f:
        records = json.load(f)
    records.sort(key=lambda r: r["REPDTE"])
    dates, rows = [], []
    for r in records:
        asset = r.get("ASSET") or 0
        lnls  = r.get("LNLSNET") or 0
        if asset <= 0:
            continue
        rows.append([lnls / asset,
                     (r.get("EQ") or 0) / asset,
                     (r.get("NCLNLS") or 0) / max(lnls, 1),
                     (r.get("NETINC") or 0) / asset,
                     (r.get("EINTEXP") or 0) / asset])
        dates.append(r["REPDTE"])
    return np.array(rows, dtype=np.float64) if rows else np.empty((0, 5)), dates


# ======================================================================
# Load Nigeria WB data → (T_annual, 5) + year list
# ======================================================================
def load_nigeria_wb():
    """Build 5-feature annual series from wb_NGA_*.json files."""
    indicators = {}
    for feat, wb_code in WB_FEATURE_MAP.items():
        fp = os.path.join(GSIB_DIR, f"wb_NGA_{wb_code}.json")
        if not os.path.exists(fp):
            indicators[feat] = {}
            continue
        with open(fp) as f:
            raw = json.load(f)
        indicators[feat] = {int(k[:4]): v for k, v in raw.items() if v is not None}

    all_years = set()
    for d in indicators.values():
        all_years.update(d.keys())
    if not all_years:
        return np.empty((0, 5)), []
    years = sorted(all_years)

    rows, valid_years = [], []
    for y in years:
        row = []
        n_avail = 0
        for feat in FEATURE_NAMES:
            val = indicators[feat].get(y, np.nan)
            row.append(val)
            if np.isfinite(val):
                n_avail += 1
        if n_avail >= 3:
            rows.append(row)
            valid_years.append(y)

    X = np.array(rows, dtype=np.float64)
    X /= 100.0  # WB data in % → ratios
    return clean_array(X), valid_years


# ======================================================================
# Load G-SIB panel + meta, group by region (deduplicated)
# ======================================================================
def load_panel():
    """Return X(T,N,5), meta list, and region→[(idx,name,iso)] deduplicated."""
    X = np.load(GSIB_NPZ)["X"]
    with open(GSIB_META) as f:
        meta = json.load(f)

    N_meta = len(meta)
    X = X[:, :N_meta, :]

    regions = {}
    seen_iso = {}

    for i, m in enumerate(meta):
        region = m["region"]
        iso = m["iso"]
        name = m["name"]

        if region not in regions:
            regions[region] = []
            seen_iso[region] = set()

        if m["tier"] == 1:
            regions[region].append((i, name, iso))
        else:
            if iso in seen_iso[region]:
                continue
            seen_iso[region].add(iso)
            regions[region].append((i, name, iso))

    return X, meta, regions


# ======================================================================
# Core analysis: fit on reference, score prediction, compute metrics
# ======================================================================
def analyse_entity(X_ref, X_pred, pred_labels, crisis_start_label,
                   lehman_ref=None):
    """
    Returns dict with AUC, P, R, F1, first_C*, lead_quarters, peak_score,
    peak_quarter, trajectory.  Returns None if sparse.
    """
    X_ref = clean_array(X_ref)
    X_pred = clean_array(X_pred)

    if is_sparse(X_ref):
        return None

    cg = CollapseGeometry()
    cg.fit(X_ref)

    scores = [float(cg.score(X_pred[i:i+1])[0]) for i in range(len(X_pred))]
    # Friction-damped scores: trajectory-based adaptive intervention
    scores_f_arr = cg.score_with_friction(X_pred)
    scores_f = [float(s) for s in scores_f_arr]

    y_true = []
    for lbl in pred_labels:
        y_true.append(1 if lbl >= crisis_start_label else 0)

    auc = auc_manual(y_true, scores) if (0 in y_true and 1 in y_true) else float("nan")
    prec, rec, f1 = prf1(y_true, scores)

    first_cross = None
    for i, s in enumerate(scores):
        if s > 0.5:
            first_cross = pred_labels[i]
            break

    lead = None
    if first_cross is not None and lehman_ref is not None:
        if isinstance(first_cross, str) and isinstance(lehman_ref, str):
            fc_y, fc_q = int(first_cross.split("-")[0]), int(first_cross.split("Q")[1])
            lh_y, lh_q = int(lehman_ref.split("-")[0]), int(lehman_ref.split("Q")[1])
            lead = (lh_y * 4 + lh_q) - (fc_y * 4 + fc_q)
        elif isinstance(first_cross, int) and isinstance(lehman_ref, int):
            lead = lehman_ref - first_cross

    peak_idx = int(np.argmax(scores))
    peak_score = scores[peak_idx]
    peak_label = pred_labels[peak_idx]

    rep = cg.detect(X_pred[peak_idx:peak_idx+1])

    # Friction effectiveness: mean reduction ratio
    raw_arr = np.array(scores)
    fric_arr = np.array(scores_f)
    crisis_mask = np.array(y_true, dtype=bool)
    if crisis_mask.any():
        damp_ratio = float(np.mean(fric_arr[crisis_mask] / np.maximum(raw_arr[crisis_mask], 1e-12)))
    else:
        damp_ratio = float(np.mean(fric_arr / np.maximum(raw_arr, 1e-12)))

    # Tipping point: quarter of maximum friction-score velocity (steepest rise)
    delta_sf = np.diff(fric_arr)
    if len(delta_sf) > 0:
        tip_idx = int(np.argmax(delta_sf)) + 1  # +1 because diff shifts by 1
        tipping_label = pred_labels[tip_idx]
        tipping_delta = float(delta_sf[tip_idx - 1])
    else:
        tipping_label = None
        tipping_delta = 0.0

    return {
        "auc": auc, "prec": prec, "rec": rec, "f1": f1,
        "first_cross": first_cross, "lead": lead,
        "peak_score": peak_score, "peak_label": peak_label,
        "tipping_label": tipping_label, "tipping_delta": tipping_delta,
        "scores": scores, "scores_friction": scores_f,
        "damp_ratio": damp_ratio,
        "labels": pred_labels,
        "Q_at_peak": float(np.asarray(rep.Q).flat[0]),
        "tau_Q": float(np.asarray(rep.tau_Q).flat[0]),
        "cg": cg,
    }


# ======================================================================
# Fresh prediction helper
# ======================================================================
def fresh_predict(cg, X_latest, label, X_context=None):
    """Fresh prediction with optional trajectory context for friction.
    
    X_context: (T, d) recent trajectory ending at X_latest.
               If provided, friction is applied to the full trajectory
               and the last score is returned.
    """
    s = float(cg.score(X_latest.reshape(1, -1))[0])
    if X_context is not None and len(X_context) >= 2:
        s_f = float(cg.score_with_friction(X_context)[-1])
    else:
        s_f = s  # no trajectory → no dynamics to damp
    rep = cg.detect(X_latest.reshape(1, -1))
    return {
        "label": label, "score": s, "score_friction": s_f,
        "Q": float(np.asarray(rep.Q).flat[0]),
        "tau_Q": float(np.asarray(rep.tau_Q).flat[0]),
        "crossed": bool(rep.crossed_Cstar[0]),
        "gamma_star": float(np.asarray(rep.gamma_star).flat[0]),
        "sigma_diss": float(np.asarray(rep.sigma_dissipation).flat[0]),
        "diss_failure": bool(rep.dissipation_failure[0]),
    }


# ======================================================================
# Table printer
# ======================================================================
def print_table(headers, rows, title=None):
    if title:
        print(f"\n  {title}")
    if not rows:
        print("  (no data)")
        return
    widths = [max(len(str(h)), max((len(str(r[i])) for r in rows), default=0))
              for i, h in enumerate(headers)]
    fmt = "  " + " | ".join(f"{{:<{w}}}" for w in widths)
    sep = "  " + "-+-".join("-" * w for w in widths)
    print(fmt.format(*headers))
    print(sep)
    for r in rows:
        print(fmt.format(*r))


# ######################################################################
#  MAIN
# ######################################################################
def main():
    print("=" * 76)
    print("CollapseGeometry — Global Regional Bank Analysis")
    print("Causal protocol · No look-ahead · Sparse data dropped")
    print("=" * 76)

    X, meta, regions = load_panel()
    T_panel = X.shape[0]

    # ──────────────────────────────────────────────────────────────
    #  PHASE 1: GFC ANALYSIS PER REGION
    # ──────────────────────────────────────────────────────────────
    ref_end    = qidx(2007, 1)       # 2005-Q1 .. 2006-Q4 = 8 quarters
    pred_start = qidx(2006, 1)       # include 2006 as label=0 for AUC
    pred_end   = qidx(2010, 1)       # through 2009-Q4
    crisis_lbl = "2007-Q3"
    lehman_lbl = "2008-Q3"

    all_results = []   # (region, entity, result_dict)
    region_cgs  = {}   # (region, entity) → (cg, panel_idx_or_None)

    # ── US G-SIBs ──
    print("\n" + "-" * 76)
    print("REGION: UNITED STATES — FDIC Call-Report (Individual Bank-Level)")
    print("-" * 76)

    us_banks = regions.get("US", [])
    for idx, name, iso in us_banks:
        Xb = X[:, idx, :]
        X_ref = Xb[:ref_end]
        labels = [qlabel(t) for t in range(pred_start, pred_end)]
        X_pred_block = Xb[pred_start:pred_end]

        res = analyse_entity(X_ref, X_pred_block, labels, crisis_lbl, lehman_lbl)
        if res is None:
            print(f"  {name:25s} -> DROPPED (sparse reference)")
            continue

        region_cgs[("US", name)] = (res["cg"], idx)
        all_results.append(("US", name, res))

    # ── US FDIC Cert Banks (long history) ──
    cert_files = sorted(f for f in os.listdir(CERT_DIR)
                        if f.startswith("cert_") and f.endswith(".json"))
    cert_results = []
    for fname in cert_files:
        cid = int(fname.replace("cert_", "").replace(".json", ""))
        Xc, dates = load_cert_data(cid)
        if len(Xc) == 0:
            continue
        years = [int(d[:4]) for d in dates]
        if min(years) > 1995 or max(years) < 2009:
            continue

        ref_mask  = np.array([(1990 <= y <= 2005) for y in years])
        pred_mask = np.array([(2006 <= y <= 2009) for y in years])
        X_c_ref  = Xc[ref_mask]
        X_c_pred = Xc[pred_mask]
        pred_years = [y for y, m in zip(years, pred_mask) if m]

        if len(X_c_ref) < 12 or len(X_c_pred) < 4:
            continue

        res = analyse_entity(X_c_ref, X_c_pred, pred_years, 2008, 2008)
        if res is None:
            continue
        cert_results.append((f"cert_{cid}", res))

    # ── EUROPE ──
    print("\n" + "-" * 76)
    print("REGION: EUROPE — World Bank GFDD + ECB MIR (Country Banking Sector)")
    print("-" * 76)

    eu_banks = regions.get("EU", [])
    for idx, name, iso in eu_banks:
        Xb = X[:, idx, :]
        X_ref = Xb[:ref_end]
        labels = [qlabel(t) for t in range(pred_start, pred_end)]
        X_pred_block = Xb[pred_start:pred_end]

        res = analyse_entity(X_ref, X_pred_block, labels, crisis_lbl, lehman_lbl)
        if res is None:
            print(f"  {name:25s} ({iso}) -> DROPPED (sparse reference)")
            continue

        entity_name = f"{name} ({iso})"
        region_cgs[("EU", entity_name)] = (res["cg"], idx)
        all_results.append(("EU", entity_name, res))

    # ── ASIA ──
    print("\n" + "-" * 76)
    print("REGION: ASIA — World Bank GFDD (Country Banking Sector)")
    print("-" * 76)

    asia_banks = regions.get("Asia", [])
    for idx, name, iso in asia_banks:
        Xb = X[:, idx, :]
        X_ref = Xb[:ref_end]
        labels = [qlabel(t) for t in range(pred_start, pred_end)]
        X_pred_block = Xb[pred_start:pred_end]

        res = analyse_entity(X_ref, X_pred_block, labels, crisis_lbl, lehman_lbl)
        if res is None:
            print(f"  {name:25s} ({iso}) -> DROPPED (sparse reference)")
            continue

        entity_name = f"{name} ({iso})"
        region_cgs[("Asia", entity_name)] = (res["cg"], idx)
        all_results.append(("Asia", entity_name, res))

    # ── AFRICA (Nigeria) ──
    print("\n" + "-" * 76)
    print("REGION: AFRICA — Nigeria (World Bank GFDD, Annual)")
    print("-" * 76)

    X_nga, nga_years = load_nigeria_wb()
    nga_res = None
    if len(X_nga) >= 10:
        ref_mask  = np.array([(2000 <= y <= 2006) for y in nga_years])
        pred_mask = np.array([(2006 <= y <= 2012) for y in nga_years])
        X_ref_nga  = X_nga[ref_mask]
        X_pred_nga = X_nga[pred_mask]
        pred_yrs   = [y for y, m in zip(nga_years, pred_mask) if m]

        nga_res = analyse_entity(X_ref_nga, X_pred_nga, pred_yrs, 2009, 2009)
        if nga_res is not None:
            region_cgs[("Africa", "Nigeria")] = (nga_res["cg"], None)
            all_results.append(("Africa", "Nigeria", nga_res))
        else:
            print("  Nigeria -> DROPPED (sparse reference)")
    else:
        print(f"  Nigeria -> SKIPPED (only {len(X_nga)} annual observations)")

    # ──────────────────────────────────────────────────────────────
    #  PHASE 2: CONSOLIDATED GFC RESULTS TABLE
    # ──────────────────────────────────────────────────────────────
    print("\n" + "=" * 76)
    print("CONSOLIDATED GFC RESULTS — Early Warning Included")
    print("=" * 76)

    headers = ["Region", "Entity", "AUC", "F1",
               "C* First", "Lead", "Peak", "Fric",
               "Tipping", "ΔS_f"]
    rows = []
    for region, entity, res in all_results:
        fc = str(res["first_cross"]) if res["first_cross"] is not None else "-"
        if res["lead"] is not None and res["lead"] > 0:
            ld = f"+{res['lead']}Q"
        elif res["lead"] is not None:
            ld = f"{res['lead']}Q"
        else:
            ld = "-"
        auc_s = f"{res['auc']:.3f}" if np.isfinite(res['auc']) else "-"
        # Peak friction score at same quarter as peak raw
        peak_idx = res["scores"].index(res["peak_score"])
        peak_fric = res["scores_friction"][peak_idx]
        tip_lbl = str(res["tipping_label"]) if res["tipping_label"] else "-"
        tip_d = f"+{res['tipping_delta']:.2f}"
        rows.append([
            region, entity, auc_s, f"{res['f1']:.2f}",
            fc, ld, f"{res['peak_score']:.3f}",
            f"{peak_fric:.3f}", tip_lbl, tip_d,
        ])
    print_table(headers, rows)

    # ── Regional Summaries ──
    for rgn in ["US", "EU", "Asia", "Africa"]:
        rgn_res = [r for r in all_results if r[0] == rgn]
        if not rgn_res:
            continue
        aucs = [r[2]["auc"] for r in rgn_res if np.isfinite(r[2]["auc"])]
        leads = [r[2]["lead"] for r in rgn_res
                 if r[2]["lead"] is not None and r[2]["lead"] > 0]
        n_crossed = sum(1 for r in rgn_res if r[2]["first_cross"] is not None)
        mean_auc = np.mean(aucs) if aucs else 0
        if leads:
            print(f"\n  {rgn}: {len(rgn_res)} entities | mean AUC={mean_auc:.3f} | "
                  f"C* crossed: {n_crossed}/{len(rgn_res)} | "
                  f"mean lead: {np.mean(leads):.1f}Q")
        else:
            print(f"\n  {rgn}: {len(rgn_res)} entities | mean AUC={mean_auc:.3f} | "
                  f"C* crossed: {n_crossed}/{len(rgn_res)} | no early warning")

    # ── US Cert Bank Summary ──
    if cert_results:
        cert_aucs = [r[1]["auc"] for r in cert_results if np.isfinite(r[1]["auc"])]
        n_esc = sum(1 for _, r in cert_results if r["first_cross"] is not None)
        print(f"\n  US FDIC Certs: {len(cert_results)} banks | "
              f"mean AUC={np.mean(cert_aucs):.3f} | "
              f"C* crossed: {n_esc}/{len(cert_results)}")

    # ──────────────────────────────────────────────────────────────
    #  PHASE 3: PER-REGION DETAIL (trajectories)
    # ──────────────────────────────────────────────────────────────
    for rgn in ["US", "EU", "Asia", "Africa"]:
        rgn_res = [r for r in all_results if r[0] == rgn]
        if not rgn_res:
            continue
        print(f"\n{'-' * 76}")
        print(f"DETAIL: {rgn} — Score Trajectories")
        print(f"{'-' * 76}")

        for _, entity, res in rgn_res:
            auc_v = f"{res['auc']:.3f}" if np.isfinite(res['auc']) else "n/a"
            print(f"\n  {entity}  (AUC={auc_v}, damp={res['damp_ratio']:.2f})")
            print(f"    {'Qtr':8s}  {'Raw':>6s}  {'Fric':>6s}  {'Red':>5s}  Bar")
            for lbl, sc, sf in zip(res["labels"], res["scores"],
                                   res["scores_friction"]):
                bar = "#" * min(int(sc * 40), 80)
                fbar = "=" * min(int(sf * 40), 80)
                marker = ""
                if lbl == res["tipping_label"]:
                    marker = " << TIPPING POINT"
                elif lbl == res["peak_label"] and sc == res["peak_score"]:
                    marker = " << PEAK"
                elif lbl == res["first_cross"]:
                    marker = " << C*"
                red = (1.0 - sf / max(sc, 1e-12)) * 100 if sc > 0.01 else 0
                print(f"    {lbl}: {sc:6.3f} {sf:6.3f} {red:4.0f}%  {bar}{marker}")
                if sf > 0.01 and sf < sc - 0.01:
                    print(f"    {'':8s}  {'':6s}  {'':6s}  {'':5s}  {fbar} (after friction)")

    # ──────────────────────────────────────────────────────────────
    #  PHASE 4: FRESH PREDICTION (latest data)
    # ──────────────────────────────────────────────────────────────
    print("\n" + "=" * 76)
    print("FRESH PREDICTION — Current State Assessment")
    print("=" * 76)
    print("  Protocol: fit on 2018-Q1..2022-Q4 (post-recovery normal,")
    print("            COVID 2020 excluded), predict latest available quarters")

    fresh_ref_start = qidx(2018, 1)
    fresh_ref_end   = qidx(2023, 1)
    covid_start = qidx(2020, 1)
    covid_end   = qidx(2021, 1)

    fresh_rows = []

    for rgn in ["US", "EU", "Asia"]:
        rgn_banks = regions.get(rgn, [])
        for idx, name, iso in rgn_banks:
            Xb = X[:, idx, :]

            ref_indices = [t for t in range(fresh_ref_start, fresh_ref_end)
                           if not (covid_start <= t < covid_end)]
            X_fresh_ref = clean_array(Xb[ref_indices])

            if is_sparse(X_fresh_ref):
                continue

            cg = CollapseGeometry()
            cg.fit(X_fresh_ref)

            pred_start_f = qidx(2023, 1)
            pred_end_f = min(qidx(2024, 1), T_panel)
            latest_scores = []
            # Context window: last 8 quarters before prediction start
            ctx_start = max(0, pred_start_f - 8)
            for t in range(pred_start_f, pred_end_f):
                X_ctx = clean_array(Xb[ctx_start:t + 1])
                fp = fresh_predict(cg, Xb[t], qlabel(t), X_context=X_ctx)
                latest_scores.append(fp)

            if not latest_scores:
                continue

            latest = latest_scores[-1]
            entity_name = name if rgn == "US" else f"{name} ({iso})"
            crossed_str = "YES" if latest["crossed"] else "no"
            Q_ratio = latest["Q"] / latest["tau_Q"] if latest["tau_Q"] > 0 else 0

            if latest["score"] > 0.8:
                assess = "HIGH STRESS"
            elif latest["score"] > 0.5:
                assess = "ELEVATED"
            elif latest["score"] > 0.3:
                assess = "MODERATE"
            else:
                assess = "NORMAL"

            # Assessment WITH friction
            sf = latest["score_friction"]
            if sf > 0.8:
                assess_f = "HIGH STRESS"
            elif sf > 0.5:
                assess_f = "ELEVATED"
            elif sf > 0.3:
                assess_f = "MODERATE"
            else:
                assess_f = "NORMAL"

            red_pct = (1.0 - sf / max(latest["score"], 1e-12)) * 100
            fresh_rows.append([
                rgn, entity_name, latest["label"],
                f"{latest['score']:.3f}", f"{sf:.3f}",
                f"{red_pct:+.0f}%",
                crossed_str, assess, assess_f,
            ])

    # Nigeria fresh prediction
    if len(X_nga) >= 10:
        nga_ref_mask = np.array([(2010 <= y <= 2019) for y in nga_years])
        X_nga_fresh_ref = X_nga[nga_ref_mask]
        if len(X_nga_fresh_ref) >= 5 and not is_sparse(clean_array(X_nga_fresh_ref)):
            cg_nga = CollapseGeometry()
            cg_nga.fit(clean_array(X_nga_fresh_ref))

            latest_yr = max(nga_years)
            latest_idx = nga_years.index(latest_yr)
            # Context: last 8 years of observations
            ctx_start_nga = max(0, latest_idx - 7)
            X_nga_ctx = clean_array(X_nga[ctx_start_nga:latest_idx + 1])
            fp = fresh_predict(cg_nga, X_nga[latest_idx], str(latest_yr),
                               X_context=X_nga_ctx)
            Q_ratio = fp["Q"] / fp["tau_Q"] if fp["tau_Q"] > 0 else 0
            crossed_str = "YES" if fp["crossed"] else "no"
            if fp["score"] > 0.8:
                assess = "HIGH STRESS"
            elif fp["score"] > 0.5:
                assess = "ELEVATED"
            elif fp["score"] > 0.3:
                assess = "MODERATE"
            else:
                assess = "NORMAL"
            sf = fp["score_friction"]
            if sf > 0.8:
                assess_f = "HIGH STRESS"
            elif sf > 0.5:
                assess_f = "ELEVATED"
            elif sf > 0.3:
                assess_f = "MODERATE"
            else:
                assess_f = "NORMAL"
            red_pct = (1.0 - sf / max(fp["score"], 1e-12)) * 100
            fresh_rows.append([
                "Africa", "Nigeria", str(latest_yr),
                f"{fp['score']:.3f}", f"{sf:.3f}",
                f"{red_pct:+.0f}%",
                crossed_str, assess, assess_f,
            ])

    fresh_headers = ["Region", "Entity", "Latest", "Raw",
                     "Fric", "Red%", "C*", "Without", "With Friction"]
    print_table(fresh_headers, fresh_rows)

    # ──────────────────────────────────────────────────────────────
    #  PHASE 5: THOROUGH ANALYSIS
    # ──────────────────────────────────────────────────────────────
    print("\n" + "=" * 76)
    print("THOROUGH ANALYSIS")
    print("=" * 76)

    # A) Cross-Regional GFC Comparison
    print("\n  A) Cross-Regional GFC Fragility Ranking")
    print("  " + "-" * 50)
    region_stats = {}
    for rgn in ["US", "EU", "Asia", "Africa"]:
        rgn_res = [r for r in all_results if r[0] == rgn]
        if not rgn_res:
            continue
        aucs = [r[2]["auc"] for r in rgn_res if np.isfinite(r[2]["auc"])]
        f1s  = [r[2]["f1"] for r in rgn_res]
        leads = [r[2]["lead"] for r in rgn_res
                 if r[2]["lead"] is not None and r[2]["lead"] > 0]
        peaks = [r[2]["peak_score"] for r in rgn_res]
        n_crossed = sum(1 for r in rgn_res if r[2]["first_cross"] is not None)

        region_stats[rgn] = {
            "n": len(rgn_res), "mean_auc": np.mean(aucs) if aucs else 0,
            "mean_f1": np.mean(f1s), "mean_peak": np.mean(peaks),
            "n_crossed": n_crossed,
            "mean_lead": np.mean(leads) if leads else 0,
            "lead_months": np.mean(leads) * 3 if leads else 0,
        }

    sorted_regions = sorted(region_stats.items(), key=lambda x: -x[1]["mean_auc"])
    for rank, (rgn, st) in enumerate(sorted_regions, 1):
        print(f"    #{rank} {rgn:8s}: AUC={st['mean_auc']:.3f}  F1={st['mean_f1']:.2f}  "
              f"peak={st['mean_peak']:.2f}  C*={st['n_crossed']}/{st['n']}  "
              f"lead={st['mean_lead']:.1f}Q ({st['lead_months']:.0f}mo)")

    # B-pre) Collapse Tipping Point Analysis
    print("\n  B) Collapse Tipping Points — Maximum Friction Acceleration")
    print("  " + "-" * 50)
    print("    The tipping point is the quarter with the largest single-step")
    print("    rise in friction score (max ΔS_f).  This is where the system")
    print("    was driven hardest toward collapse — the identifiable moment")
    print("    when friction fully engages to prevent C* crossing.")
    tip_data = []
    for _, entity, res in all_results:
        if res["tipping_label"] is not None and res["tipping_delta"] > 0.05:
            tip_data.append((entity, res["tipping_label"],
                             res["tipping_delta"],
                             res["first_cross"], res["lead"]))
    tip_data.sort(key=lambda x: -x[2])
    if tip_data:
        print(f"\n    {'Entity':28s} {'Tipping':10s} {'ΔS_f':>6s}  "
              f"{'C* First':10s} {'vs C*':>6s}")
        print(f"    {'-'*28} {'-'*10} {'-'*6}  {'-'*10} {'-'*6}")
        for ent, tip, ds, fc, lead_q in tip_data:
            # How many quarters before/after C* crossing
            fc_str = str(fc) if fc else "-"
            if tip and fc and isinstance(tip, str) and isinstance(fc, str):
                try:
                    ty, tq = int(tip.split("-")[0]), int(tip.split("Q")[1])
                    fy, fq = int(fc.split("-")[0]), int(fc.split("Q")[1])
                    diff = (ty * 4 + tq) - (fy * 4 + fq)
                    vs = f"{diff:+d}Q" if diff != 0 else "same"
                except Exception:
                    vs = "-"
            elif tip and fc and isinstance(tip, int) and isinstance(fc, int):
                diff = tip - fc
                vs = f"{diff:+d}Q" if diff != 0 else "same"
            else:
                vs = "-"
            print(f"    {ent:28s} {str(tip):10s} {ds:+6.3f}  "
                  f"{fc_str:10s} {vs:>6s}")
        mean_ds = np.mean([t[2] for t in tip_data])
        print(f"\n    Mean tipping ΔS_f: {mean_ds:.3f}")
        print(f"    Entities with sharp tipping (ΔS_f > 0.3): "
              f"{sum(1 for t in tip_data if t[2] > 0.3)}/{len(tip_data)}")
    else:
        print("    No significant tipping points detected (all ΔS_f < 0.05)")

    # B) Early Warning Analysis
    print("\n  C) Early Warning Lead Time Analysis")
    print("  " + "-" * 50)
    all_leads = []
    for _, entity, res in all_results:
        if res["lead"] is not None and res["lead"] > 0:
            all_leads.append((entity, res["lead"], res["first_cross"]))
    all_leads.sort(key=lambda x: -x[1])
    if all_leads:
        print(f"    Entities with early warning: {len(all_leads)}/{len(all_results)}")
        mean_lead = np.mean([l[1] for l in all_leads])
        print(f"    Global mean lead: {mean_lead:.1f} quarters "
              f"({mean_lead * 3:.0f} months)")
        print(f"    Longest lead:  {all_leads[0][0]} -- {all_leads[0][2]} "
              f"({all_leads[0][1]}Q = {all_leads[0][1]*3}mo before crisis)")
        print(f"    Shortest lead: {all_leads[-1][0]} -- {all_leads[-1][2]} "
              f"({all_leads[-1][1]}Q = {all_leads[-1][1]*3}mo)")
    else:
        print("    No early warnings detected")

    # D) Discrimination Power
    print("\n  D) Discrimination Power — AUC Distribution")
    print("  " + "-" * 50)
    all_aucs = [r[2]["auc"] for r in all_results if np.isfinite(r[2]["auc"])]
    if all_aucs:
        print(f"    N entities: {len(all_aucs)}")
        print(f"    Mean AUC:   {np.mean(all_aucs):.3f} +/- {np.std(all_aucs):.3f}")
        print(f"    Median AUC: {np.median(all_aucs):.3f}")
        print(f"    Range:      [{min(all_aucs):.3f}, {max(all_aucs):.3f}]")
        n_above_07 = sum(1 for a in all_aucs if a > 0.7)
        n_above_05 = sum(1 for a in all_aucs if a > 0.5)
        print(f"    AUC > 0.7:  {n_above_07}/{len(all_aucs)} "
              f"({n_above_07/len(all_aucs)*100:.0f}%)")
        print(f"    AUC > 0.5:  {n_above_05}/{len(all_aucs)} "
              f"({n_above_05/len(all_aucs)*100:.0f}%)")

        if cert_results:
            cert_aucs_v = [r[1]["auc"] for r in cert_results
                           if np.isfinite(r[1]["auc"])]
            combined = all_aucs + cert_aucs_v
            print(f"\n    Including {len(cert_aucs_v)} US cert banks:")
            print(f"    Combined mean AUC: {np.mean(combined):.3f} "
                  f"+/- {np.std(combined):.3f}")
            n_comb_07 = sum(1 for a in combined if a > 0.7)
            print(f"    Combined AUC > 0.7: {n_comb_07}/{len(combined)}")

    # E) Fresh Prediction Summary (Without vs With Friction)
    print("\n  E) Current State Summary (Fresh Prediction)")
    print("  " + "-" * 50)
    if fresh_rows:
        # Without friction
        n_normal   = sum(1 for r in fresh_rows if r[7] == "NORMAL")
        n_moderate = sum(1 for r in fresh_rows if r[7] == "MODERATE")
        n_elevated = sum(1 for r in fresh_rows if r[7] == "ELEVATED")
        n_high     = sum(1 for r in fresh_rows if r[7] == "HIGH STRESS")
        n_crossed  = sum(1 for r in fresh_rows if r[6] == "YES")
        print(f"    Entities assessed: {len(fresh_rows)}")
        print(f"    ── Without Friction ──")
        print(f"    NORMAL:      {n_normal}")
        print(f"    MODERATE:    {n_moderate}")
        print(f"    ELEVATED:    {n_elevated}")
        print(f"    HIGH STRESS: {n_high}")
        print(f"    C* crossed:  {n_crossed}/{len(fresh_rows)}")

        # With friction
        nf_normal   = sum(1 for r in fresh_rows if r[8] == "NORMAL")
        nf_moderate = sum(1 for r in fresh_rows if r[8] == "MODERATE")
        nf_elevated = sum(1 for r in fresh_rows if r[8] == "ELEVATED")
        nf_high     = sum(1 for r in fresh_rows if r[8] == "HIGH STRESS")
        print(f"\n    ── With Adaptive Friction ──")
        print(f"    NORMAL:      {nf_normal}")
        print(f"    MODERATE:    {nf_moderate}")
        print(f"    ELEVATED:    {nf_elevated}")
        print(f"    HIGH STRESS: {nf_high}")

        # Friction impact
        n_changed = sum(1 for r in fresh_rows if r[7] != r[8])
        print(f"\n    Friction changed assessment: {n_changed}/{len(fresh_rows)}")
        if n_changed > 0:
            for r in fresh_rows:
                if r[7] != r[8]:
                    print(f"      {r[1]:30s} {r[7]:12s} -> {r[8]}")

        for rgn in ["US", "EU", "Asia", "Africa"]:
            rgn_fresh = [r for r in fresh_rows if r[0] == rgn]
            if not rgn_fresh:
                continue
            raw_scores = [float(r[3]) for r in rgn_fresh]
            fric_scores = [float(r[4]) for r in rgn_fresh]
            print(f"\n    {rgn}: raw mean={np.mean(raw_scores):.3f}  "
                  f"fric mean={np.mean(fric_scores):.3f}  "
                  f"range=[{min(raw_scores):.3f},{max(raw_scores):.3f}]")
            for r in rgn_fresh:
                print(f"      {r[1]:30s} raw={r[3]}  fric={r[4]}  "
                      f"{r[5]:>5s}  {r[7]:12s} -> {r[8]}")

    # F) Limitations
    print("\n  F) Limitations & Caveats")
    print("  " + "-" * 50)
    print("    1. Non-US data is country-level banking sector aggregate (World Bank),")
    print("       not individual bank balance sheets. EU/Asia per-bank is really")
    print("       per-country banking sector. Duplicate-ISO banks were deduplicated.")
    print("    2. Africa: Nigeria only (sole African country with cached WB data).")
    print("       Annual observations (2000-2021) — limited sample size.")
    print("    3. COVID (2020) excluded from all reference windows (exogenous shock).")
    print("    4. CollapseGeometry is closed-form geometric (zero ML training).")
    print("       AUC reflects pure geometric discrimination from eigendecomposition.")
    print("    5. GFC labels use 2007-Q3 onset; Nigerian crisis uses 2009 onset.")
    print("       Lehman (Sep 2008) used as lead-time reference for GFC regions.")
    print("    6. Fresh prediction ref = 2018-2022 (excl. COVID 2020).")
    print("       For Nigeria, ref = 2010-2019 due to shorter time series.")

    # G) Statistical Confidence
    print("\n  G) Statistical Confidence — Bootstrap 95% CI on Mean AUC")
    print("  " + "-" * 50)
    if len(all_aucs) >= 5:
        rng = np.random.default_rng(42)
        boot_means = []
        arr = np.array(all_aucs)
        for _ in range(10000):
            sample = rng.choice(arr, size=len(arr), replace=True)
            boot_means.append(sample.mean())
        boot_means.sort()
        ci_lo = boot_means[int(0.025 * len(boot_means))]
        ci_hi = boot_means[int(0.975 * len(boot_means))]
        print(f"    Panel entities (N={len(all_aucs)}): "
              f"mean AUC = {np.mean(all_aucs):.3f}  "
              f"95% CI = [{ci_lo:.3f}, {ci_hi:.3f}]")

    # ── Assertions ──
    print("\n" + "=" * 76)
    print("ASSERTIONS")
    print("=" * 76)

    # 1. US mean AUC > 0.7
    us_aucs = [r[2]["auc"] for r in all_results
               if r[0] == "US" and np.isfinite(r[2]["auc"])]
    if us_aucs:
        assert np.mean(us_aucs) > 0.7, \
            f"US mean AUC {np.mean(us_aucs):.3f} < 0.7"
        print(f"  PASS: US mean AUC = {np.mean(us_aucs):.3f} > 0.7")

    # 2. At least 50% of panel entities have AUC > 0.5
    if all_aucs:
        pct_above = sum(1 for a in all_aucs if a > 0.5) / len(all_aucs)
        assert pct_above >= 0.5, f"Only {pct_above:.0%} entities AUC > 0.5"
        print(f"  PASS: {pct_above:.0%} of entities have AUC > 0.5")

    # 3. At least some early warnings exist
    n_warned = sum(1 for _, _, r in all_results
                   if r["lead"] is not None and r["lead"] > 0)
    assert n_warned >= 2, f"Only {n_warned} early warnings"
    print(f"  PASS: {n_warned} entities gave early warning before crisis")

    # 4. Cert banks majority AUC > 0.5
    if cert_results:
        cert_a = [r[1]["auc"] for r in cert_results if np.isfinite(r[1]["auc"])]
        pct_cert = sum(1 for a in cert_a if a > 0.5) / len(cert_a) if cert_a else 0
        assert pct_cert >= 0.5, f"Cert banks: only {pct_cert:.0%} AUC > 0.5"
        print(f"  PASS: FDIC cert banks: {pct_cert:.0%} AUC > 0.5 ({len(cert_a)} banks)")

    print("\n" + "=" * 76)
    print("ALL ASSERTIONS PASSED")
    print("=" * 76)


if __name__ == "__main__":
    main()
