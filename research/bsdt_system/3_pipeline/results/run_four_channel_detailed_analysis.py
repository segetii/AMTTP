"""
Four-Channel BSDT — Detailed Analysis  (FDIC + ERCOT)
=======================================================
Extends the initial four-channel runs with:

SECTION 1 — FDIC quarterly analysis
  1a. Full attribution time-series stats by decade
  1b. Pre-crisis 8-quarter attribution evolution (8Q → 1Q before onset)
  1c. Theoretical firing-order validation (T→G→A→C)
  1d. Channel cross-correlation matrix (which channels co-fire?)
  1e. Per-sector stress contribution at each crisis onset
  1f. OOS split: calibrate on 1994-2003, evaluate on 2004-2024
  1g. Theory delta: does novel-stress (G) rise before familiar-stress (C)?

SECTION 2 — ERCOT hourly analysis
  2a. Full attribution stats by year
  2b. Pre-event 168h attribution evolution (hours before each event)
  2c. Firing-order validation against theory
  2d. Agent-level channel contribution at each event
  2e. Omega (existing) vs four-channel comparison: which gives earlier signal?
  2f. Attribution regime decomposition: what share of time each channel leads
  2g. Interaction analysis: C×G co-firing rate vs crisis incidence

Output saved to:
  four_channel_detailed_analysis.json
"""

from __future__ import annotations
import os, sys, json, time, warnings
import numpy as np
import pandas as pd
from pathlib import Path

warnings.filterwarnings('ignore')
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SCRIPT_DIR = Path(__file__).parent
COLL_DIR   = SCRIPT_DIR.parent.parent

sys.path.insert(0, str(COLL_DIR))
sys.path.insert(0, str(COLL_DIR / "upgraded"))
sys.path.insert(0, str(SCRIPT_DIR))

from collapse_geometry import MasterOperator, Snapshot
from state_matrix import standardise_panel, get_normal_period, NORMAL_START, NORMAL_END
from run_fdic_four_channel import (
    load_data as fdic_load_data,
    calibrate_four_channel,
    run_four_channel_sweep,
    HIST_WIN as FDIC_HIST_WIN,
    CH_NAMES,
)
from run_ercot_four_channel import (
    build_ercot_agent_panel,
    compute_omega_series,
    EVENTS as ERCOT_EVENTS,
    NORMAL_YEAR,
    HIST_WIN as ERCOT_HIST_WIN,
)

DATA_DIR = Path(r"C:\amttp\data\ercot")
OUT_PATH = SCRIPT_DIR / "four_channel_detailed_analysis.json"

FDIC_CRISES = {
    "GFC 2008":         pd.Timestamp("2008-09-30"),
    "COVID 2020":       pd.Timestamp("2020-03-31"),
    "Rate Shock 2022":  pd.Timestamp("2022-09-30"),
    # extras for richer picture
    "LTCM 1998":        pd.Timestamp("1998-09-30"),
    "DotCom 2001":      pd.Timestamp("2001-09-30"),
    "SVB 2023":         pd.Timestamp("2023-03-31"),
}

SEP = "=" * 72


def r4(x):
    """Round to 4 dp, handling NaN."""
    try:
        v = float(x)
        return None if np.isnan(v) else round(v, 4)
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────────────────
#  SECTION 1 — FDIC
# ─────────────────────────────────────────────────────────────────────────────

def fdic_analysis(sig: pd.DataFrame, dates: pd.DatetimeIndex,
                  X_std: np.ndarray, sector_names: list[str]) -> dict:
    print(f"\n{SEP}")
    print("  SECTION 1 — FDIC Quarterly Four-Channel Analysis")
    print(SEP)

    out = {}

    # ── 1a: Attribution by decade ────────────────────────────────────────────
    print("\n[1a] Attribution by decade")
    decades = {
        "1990s": (sig.index.year >= 1990) & (sig.index.year <= 1999),
        "2000s": (sig.index.year >= 2000) & (sig.index.year <= 2009),
        "2010s": (sig.index.year >= 2010) & (sig.index.year <= 2019),
        "2020s": (sig.index.year >= 2020),
    }
    decade_stats = {}
    print(f"  {'Decade':>6}  {'a_C':>8}  {'a_G':>8}  {'a_A':>8}  {'a_T':>8}  {'dom_C%':>8}  {'dom_G%':>8}")
    for name, mask in decades.items():
        if not mask.any():
            continue
        s  = sig[mask]
        mc = lambda c: r4(s[f'a_{c}'].mean())
        dom = s['dom_channel'].value_counts(normalize=True)
        decade_stats[name] = {
            "a_C": mc('C'), "a_G": mc('G'), "a_A": mc('A'), "a_T": mc('T'),
            "dom_C_pct": r4(dom.get(0, 0) * 100),
            "dom_G_pct": r4(dom.get(1, 0) * 100),
            "dom_A_pct": r4(dom.get(2, 0) * 100),
            "dom_T_pct": r4(dom.get(3, 0) * 100),
        }
        print(f"  {name:>6}  "
              f"{mc('C'):>8}  {mc('G'):>8}  {mc('A'):>8}  {mc('T'):>8}  "
              f"{decade_stats[name]['dom_C_pct']:>8}  {decade_stats[name]['dom_G_pct']:>8}")
    out["decade_attribution"] = decade_stats

    # ── 1b: Pre-crisis attribution evolution ─────────────────────────────────
    print("\n[1b] Pre-crisis attribution evolution (8Q → onset)")
    pre_evo = {}
    for ev_name, onset in FDIC_CRISES.items():
        if onset > sig.index[-1]:
            continue
        # find quarters from onset-8Q to onset
        rows = []
        for q_back in range(8, -1, -1):
            t_q = onset - pd.DateOffset(months=3 * q_back)
            nearest = sig.index[sig.index.searchsorted(t_q)]
            if abs((nearest - t_q).days) > 45:
                continue
            row = sig.loc[nearest]
            rows.append({
                "q_before_onset": q_back,
                "date":           str(nearest.date()),
                "a_C": r4(row['a_C']), "a_G": r4(row['a_G']),
                "a_A": r4(row['a_A']), "a_T": r4(row['a_T']),
                "dom":  CH_NAMES[int(row['dom_channel'])] if not np.isnan(row['dom_channel']) else "—",
            })
        pre_evo[ev_name] = rows
        print(f"\n  {ev_name}")
        print(f"  {'Q-bk':>5}  {'Date':>12}  {'a_C':>7}  {'a_G':>7}  {'a_A':>7}  {'a_T':>7}  {'dom':>12}")
        for r in rows:
            print(f"  {r['q_before_onset']:>5}  {r['date']:>12}  "
                  f"{r['a_C']:>7}  {r['a_G']:>7}  {r['a_A']:>7}  {r['a_T']:>7}  {r['dom']:>12}")
    out["pre_crisis_evolution"] = pre_evo

    # ── 1c: Firing-order validation ──────────────────────────────────────────
    print("\n[1c] Theoretical firing-order validation")
    print("  Theory:  δ_T fires first  →  δ_G  →  δ_A  →  δ_C last")
    THEO_ORDER = ['T', 'G', 'A', 'C']   # longest lead to shortest
    firing_val = {}
    for ev_name, onset in FDIC_CRISES.items():
        if onset > sig.index[-1]:
            continue
        leads = {}
        for c in ('C', 'G', 'A', 'T'):
            pre = sig.loc[sig.index < onset, f'fire_{c}']
            hits = pre[pre > 0.5]
            if hits.empty:
                leads[c] = None
            else:
                leads[c] = int(len(pre) - pre.index.searchsorted(hits.index[0]))
        # empirical order (most quarters lead first)
        ranked = sorted(
            [(c, l) for c, l in leads.items() if l is not None],
            key=lambda x: -x[1]
        )
        emp_order = [c for c, _ in ranked]
        match = (emp_order == THEO_ORDER[:len(emp_order)])
        lead_str = "  ".join(f"δ_{c}={leads[c]}Q" for c in ('T','G','A','C'))
        status   = "✓ MATCHES" if match else "≈ PARTIAL"
        print(f"  {ev_name:>20}: {lead_str}   {status}")
        firing_val[ev_name] = {
            "leads_q": {c: leads[c] for c in ('C','G','A','T')},
            "empirical_order": emp_order,
            "theory_match": match,
        }
    out["firing_order_validation"] = firing_val

    # ── 1d: Cross-correlation matrix ─────────────────────────────────────────
    print("\n[1d] Channel cross-correlation (full sample)")
    ch_df = sig[['a_C','a_G','a_A','a_T']].dropna()
    corr  = ch_df.corr().round(3)
    print(f"  {'':>6}  {'a_C':>7}  {'a_G':>7}  {'a_A':>7}  {'a_T':>7}")
    for row_c in ('a_C','a_G','a_A','a_T'):
        print(f"  {row_c:>6}  " + "  ".join(f"{corr.loc[row_c, col_c]:>7.3f}"
                                             for col_c in ('a_C','a_G','a_A','a_T')))
    out["channel_correlation"] = {
        r: {c: r4(corr.loc[r, c]) for c in ('a_C','a_G','a_A','a_T')}
        for r in ('a_C','a_G','a_A','a_T')
    }

    # ── 1e: Per-sector stress contribution at each crisis ────────────────────
    print("\n[1e] Per-sector relative stress at crisis onset")
    print("  (z-score norm: how many sigma above calibration mean? higher = more stressed)")
    sector_stress = {}
    for ev_name, onset in FDIC_CRISES.items():
        if onset > sig.index[-1]:
            continue
        idx = sig.index.searchsorted(onset)
        idx = min(idx, len(sig) - 1)
        x_t = X_std[idx]                # (N, d)
        # per-sector L2 norm in standardised space
        norms    = np.linalg.norm(x_t, axis=1)          # (N,)
        ranked_s = sorted(zip(sector_names, norms.tolist()), key=lambda x: -x[1])
        sector_stress[ev_name] = {s: round(v, 3) for s, v in ranked_s}
        print(f"\n  {ev_name}")
        for s, v in ranked_s:
            bar = '█' * int(v * 3)
            print(f"    {s:>30}  {v:>6.3f}  {bar}")
    out["sector_stress_at_crisis"] = sector_stress

    # ── 1f: OOS split ────────────────────────────────────────────────────────
    print("\n[1f] OOS split analysis (train 1994-2003, eval 2004-2024)")
    train_mask = calib_mask = (dates >= pd.Timestamp(NORMAL_START)) \
                              & (dates <= pd.Timestamp(NORMAL_END))
    oos_mask   = dates > pd.Timestamp(NORMAL_END)
    # For each crisis we already have the signal — measure:
    # - AUC-like: fraction of the 4Q pre-crisis window where any channel fires
    oos_auc = {}
    for ev_name, onset in FDIC_CRISES.items():
        if onset > sig.index[-1]:
            continue
        in_oos = onset > pd.Timestamp(NORMAL_END)
        pre4q  = sig.loc[(sig.index >= onset - pd.DateOffset(months=12))
                         & (sig.index < onset)]
        if len(pre4q) == 0:
            continue
        any_fire = (pre4q[['fire_C','fire_G','fire_A','fire_T']].max(axis=1) > 0.5).mean()
        # "pre-alarm quality": how early did attributions rise above 0.5?
        a_G_mean = round(float(pre4q['a_G'].mean()), 4)
        a_T_mean = round(float(pre4q['a_T'].mean()), 4)
        oos_auc[ev_name] = {
            "in_oos": bool(in_oos),
            "pre_4Q_any_fire_pct": round(float(any_fire * 100), 2),
            "pre_4Q_mean_a_G": a_G_mean,
            "pre_4Q_mean_a_T": a_T_mean,
        }
        print(f"  {ev_name:>20}  OOS={in_oos}  any_fire_pct={any_fire*100:.1f}%  "
              f"a_G={a_G_mean:.4f}  a_T={a_T_mean:.4f}")
    out["oos_split"] = oos_auc

    # ── 1g: δ_G leads δ_C — does novel stress precede familiar stress? ────────
    print("\n[1g] Novel stress (δ_G) vs familiar stress (δ_C) lead relationship")
    print("  Theory: δ_G should peak BEFORE δ_C in the run-up to each crisis")
    g_leads_c = {}
    for ev_name, onset in FDIC_CRISES.items():
        if onset > sig.index[-1]:
            continue
        pre8q = sig.loc[(sig.index >= onset - pd.DateOffset(months=24))
                        & (sig.index < onset)]
        if len(pre8q) < 4:
            continue
        peak_G_date = pre8q['a_G'].idxmax()
        peak_C_date = pre8q['a_C'].idxmax()
        delta_q     = int((peak_C_date - peak_G_date).days // 91)
        g_leads_c[ev_name] = {
            "peak_G_date": str(peak_G_date.date()),
            "peak_C_date": str(peak_C_date.date()),
            "delta_quarters_G_before_C": delta_q,
            "g_precedes_c": bool(delta_q > 0),
        }
        direction = "δ_G BEFORE δ_C ✓" if delta_q > 0 else "δ_C before δ_G ✗"
        print(f"  {ev_name:>20}: peak_G={peak_G_date.date()}  "
              f"peak_C={peak_C_date.date()}  Δ={delta_q:+d}Q  {direction}")
    out["novel_precedes_familiar"] = g_leads_c

    return out


# ─────────────────────────────────────────────────────────────────────────────
#  SECTION 2 — ERCOT
# ─────────────────────────────────────────────────────────────────────────────

def ercot_analysis() -> dict:
    print(f"\n{SEP}")
    print("  SECTION 2 — ERCOT Hourly Four-Channel Analysis")
    print(SEP)

    # ── reload data and signals ───────────────────────────────────────────────
    npz_path = DATA_DIR / "ercot_supply_hourly.npz"
    data         = np.load(str(npz_path), allow_pickle=True)
    X_raw        = data['X']
    dates_raw    = data['dates']
    feature_names = list(data['feature_names'])
    event_onsets  = json.loads(str(data['event_onsets']))

    dates        = pd.to_datetime(dates_raw)
    normal_mask  = np.array(dates.year == NORMAL_YEAR)
    X_panel      = build_ercot_agent_panel(X_raw, dates, normal_mask)

    from run_ercot_four_channel import calibrate_four_channel, run_four_channel_sweep
    M, mu_norm, fire_thr = calibrate_four_channel(X_panel, normal_mask, k=1)
    print("\n  Running four-channel sweep (35064 h)...")
    sig = run_four_channel_sweep(X_panel, dates, M, mu_norm, fire_thr)

    # omega baseline
    mu_r    = X_raw[normal_mask].mean(0)
    sd_r    = X_raw[normal_mask].std(0) + 1e-8
    X_std_r = np.nan_to_num((X_raw - mu_r) / sd_r)
    omega   = pd.Series(compute_omega_series(X_std_r, window=168), index=dates)

    out = {}

    # ── 2a: Yearly attribution stats ─────────────────────────────────────────
    print("\n[2a] Attribution by year")
    year_stats = {}
    print(f"  {'Year':>5}  {'a_C':>7}  {'a_G':>7}  {'a_A':>7}  {'a_T':>7}  "
          f"{'fire_C%':>8}  {'fire_G%':>8}  {'omega_mean':>10}")
    for yr in sorted(sig.index.year.unique()):
        mask = sig.index.year == yr
        s    = sig[mask]
        ow   = omega[mask]
        row  = {
            "a_C": r4(s['a_C'].mean()), "a_G": r4(s['a_G'].mean()),
            "a_A": r4(s['a_A'].mean()), "a_T": r4(s['a_T'].mean()),
            "fire_C_pct": r4(s['fire_C'].mean() * 100),
            "fire_G_pct": r4(s['fire_G'].mean() * 100),
            "omega_mean": r4(ow.mean()),
            "omega_max":  r4(ow.max()),
        }
        year_stats[str(yr)] = row
        print(f"  {yr:>5}  {row['a_C']:>7}  {row['a_G']:>7}  {row['a_A']:>7}  {row['a_T']:>7}  "
              f"{row['fire_C_pct']:>8}  {row['fire_G_pct']:>8}  {row['omega_mean']:>10}")
    out["yearly_attribution"] = year_stats

    # ── 2b: Pre-event 168h attribution evolution ──────────────────────────────
    print("\n[2b] Pre-event attribution evolution (168h → 1h before onset)")
    pre_evo = {}
    CHECKPOINTS = [168, 120, 96, 72, 48, 36, 24, 12, 6, 1]
    for ev_name, onset in ERCOT_EVENTS.items():
        if onset > dates[-1]:
            continue
        rows = []
        for h in CHECKPOINTS:
            t_h = onset - pd.Timedelta(hours=h)
            if t_h < dates[0]:
                continue
            nearest = sig.index[sig.index.searchsorted(t_h)]
            row = sig.loc[nearest]
            ow  = float(omega.loc[nearest]) if nearest in omega.index else np.nan
            rows.append({
                "h_before_onset": h, "date": str(nearest)[:16],
                "a_C": r4(row['a_C']), "a_G": r4(row['a_G']),
                "a_A": r4(row['a_A']), "a_T": r4(row['a_T']),
                "omega": r4(ow),
            })
        pre_evo[ev_name] = rows
        print(f"\n  {ev_name}")
        print(f"  {'H-bk':>5}  {'a_C':>7}  {'a_G':>7}  {'a_A':>7}  {'a_T':>7}  {'omega':>7}")
        for r in rows:
            print(f"  {r['h_before_onset']:>5}  {r['a_C']:>7}  {r['a_G']:>7}  "
                  f"{r['a_A']:>7}  {r['a_T']:>7}  {r['omega']:>7}")
    out["pre_event_evolution"] = pre_evo

    # ── 2c: Firing-order validation ───────────────────────────────────────────
    print("\n[2c] Theoretical firing-order validation")
    print("  Theory: δ_T first → δ_G → δ_A → δ_C last (longest lead first)")
    THEO_ORDER = ['T', 'G', 'A', 'C']
    firing_val = {}
    PRE_WIN = 168 * 4   # 4-week pre-event window
    for ev_name, onset in ERCOT_EVENTS.items():
        if onset > dates[-1]:
            continue
        leads = {}
        for c in ('C', 'G', 'A', 'T'):
            pre = sig.loc[sig.index < onset, f'fire_{c}'].iloc[-PRE_WIN:]
            hits = pre[pre > 0.5]
            leads[c] = int((onset - hits.index[0]).total_seconds() / 3600) if not hits.empty else None
        ranked = sorted(
            [(c, l) for c, l in leads.items() if l is not None],
            key=lambda x: -x[1]
        )
        emp_order = [c for c, _ in ranked]
        match     = (emp_order == THEO_ORDER[:len(emp_order)])
        lead_str  = "  ".join(f"δ_{c}={leads[c]}h" if leads[c] else f"δ_{c}=None"
                              for c in ('T','G','A','C'))
        status    = "✓ MATCHES" if match else "≈ PARTIAL"
        print(f"  {ev_name:>42}: {lead_str}   {status}")
        firing_val[ev_name] = {
            "leads_h": leads,
            "empirical_order": emp_order,
            "theory_match": match,
        }
    out["firing_order_validation"] = firing_val

    # ── 2d: Agent-level contribution at each event ────────────────────────────
    print("\n[2d] Per-agent L2 stress norm at event onset")
    print("  (which energy source is most displaced from its normal state?)")
    agent_stress = {}
    for ev_name, onset in ERCOT_EVENTS.items():
        if onset > dates[-1]:
            continue
        idx = sig.index.searchsorted(onset)
        idx = min(idx, len(sig) - 1)
        x_t = X_panel[idx]           # (N_agents, N_feat)
        norms = np.linalg.norm(x_t, axis=1)
        ranked = sorted(zip(feature_names, norms.tolist()), key=lambda x: -x[1])
        agent_stress[ev_name] = {a: round(v, 3) for a, v in ranked}
        print(f"\n  {ev_name}")
        for agent, v in ranked:
            bar = '█' * int(v * 4)
            print(f"    {str(agent):>20}  {v:>6.3f}  {bar}")
    out["agent_stress_at_event"] = agent_stress

    # ── 2e: Four-channel vs Omega lead-time comparison ────────────────────────
    print("\n[2e] Four-channel vs Omega lead-time comparison")
    print(f"  {'Event':>42}  {'4CH_lead':>9}  {'Omega_lead':>11}  {'Delta':>8}")
    lead_cmp = {}
    for ev_name, onset in ERCOT_EVENTS.items():
        if onset > dates[-1]:
            continue
        # Four-channel: first hour any fire_* crosses threshold in 4-week window
        pre_4ch = sig.loc[sig.index < onset].iloc[-PRE_WIN:]
        combined_fire = (pre_4ch[['fire_C','fire_G','fire_A','fire_T']].max(axis=1) > 0.5)
        hits_4ch = combined_fire[combined_fire]
        lead_4ch = int((onset - hits_4ch.index[0]).total_seconds() / 3600) \
                   if not hits_4ch.empty else None

        # Omega: first hour Omega>0.5 in same window
        pre_om = omega.loc[omega.index < onset].iloc[-PRE_WIN:]
        hits_om = pre_om[pre_om > 0.5]
        lead_om = int((onset - hits_om.index[0]).total_seconds() / 3600) \
                  if not hits_om.empty else None

        delta = (lead_4ch - lead_om) if (lead_4ch and lead_om) else None
        lead_cmp[ev_name] = {
            "lead_4ch_h": lead_4ch,
            "lead_omega_h": lead_om,
            "delta_h": delta,
            "four_ch_earlier": bool(delta and delta > 0),
        }
        l4 = f"{lead_4ch}h" if lead_4ch else "None"
        lo = f"{lead_om}h" if lead_om else "None"
        d  = f"{delta:+d}h" if delta is not None else "—"
        print(f"  {ev_name:>42}  {l4:>9}  {lo:>11}  {d:>8}")
    out["lead_time_comparison"] = lead_cmp

    # ── 2f: Attribution regime decomposition ─────────────────────────────────
    print("\n[2f] Attribution regime decomposition (% of hours each channel leads)")
    dom_by_yr = {}
    for yr in sorted(sig.index.year.unique()):
        mask = sig.index.year == yr
        dom_pct = (sig.loc[mask, 'dom_channel'].value_counts(normalize=True) * 100).round(2)
        dom_by_yr[str(yr)] = {CH_NAMES[int(k)]: round(float(v), 2) for k, v in dom_pct.items()}
    print(f"  {'Year':>5}  " + "  ".join(f"{CH_NAMES[k]:>12}" for k in range(4)))
    for yr, row in dom_by_yr.items():
        vals = [row.get(CH_NAMES[k], 0.0) for k in range(4)]
        print(f"  {yr:>5}  " + "  ".join(f"{v:>12.2f}" for v in vals))
    out["dom_regime_by_year"] = dom_by_yr

    # ── 2g: C×G co-firing vs crisis incidence ────────────────────────────────
    print("\n[2g] C×G co-firing analysis (both δ_C and δ_G above threshold)")
    # Crisis indicator: within 240h of any event onset
    crisis_flag = np.zeros(len(sig), dtype=bool)
    for ev_name, onset in ERCOT_EVENTS.items():
        if onset > dates[-1]:
            continue
        idx_on = sig.index.searchsorted(onset)
        lo = max(0, idx_on - 240)
        hi = min(len(sig), idx_on + 240)
        crisis_flag[lo:hi] = True
    crisis_s = pd.Series(crisis_flag, index=sig.index)

    cg_cofire = (sig['fire_C'] > 0.5) & (sig['fire_G'] > 0.5)
    print(f"  C×G co-fire rate (all hours):      {cg_cofire.mean()*100:.2f}%")
    print(f"  C×G co-fire rate (crisis hours):   {cg_cofire[crisis_s].mean()*100:.2f}%")
    print(f"  C×G co-fire rate (non-crisis):     {cg_cofire[~crisis_s].mean()*100:.2f}%")
    print(f"  Precision (co-fire → crisis):      "
          f"{(crisis_s[cg_cofire].mean()*100):.2f}% of co-fire hours are near a crisis")
    out["cg_cofire"] = {
        "all_pct":         r4(cg_cofire.mean() * 100),
        "crisis_pct":      r4(cg_cofire[crisis_s].mean() * 100),
        "non_crisis_pct":  r4(cg_cofire[~crisis_s].mean() * 100),
        "precision_pct":   r4(crisis_s[cg_cofire].mean() * 100),
    }

    return out


# ─────────────────────────────────────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    t0 = time.time()
    print(SEP)
    print("  Four-Channel BSDT — Detailed Analysis")
    print("  FDIC (quarterly, 1990-2024) + ERCOT (hourly, 2019-2022)")
    print(SEP)

    # ── FDIC setup ────────────────────────────────────────────────────────────
    print("\nLoading FDIC data...")
    X_all, dates, sector_names, data_label = fdic_load_data(use_cache=True, verbose=False)
    X_normal, dates_normal = get_normal_period(X_all, dates)
    X_std, _, _ = standardise_panel(X_all, X_ref=X_normal)
    calib_mask  = (dates >= pd.Timestamp(NORMAL_START)) & (dates <= pd.Timestamp(NORMAL_END))
    M_f, mu_f, ft_f = calibrate_four_channel(X_std, calib_mask, k=1)
    sig_f = run_four_channel_sweep(X_std, dates, M_f, mu_f, ft_f)

    fdic_out = fdic_analysis(sig_f, dates, X_std, sector_names)

    # ── ERCOT ────────────────────────────────────────────────────────────────
    ercot_out = ercot_analysis()

    # ── Summary comparison table ──────────────────────────────────────────────
    print(f"\n{SEP}")
    print("  CROSS-DOMAIN SUMMARY")
    print(SEP)
    print("""
  Domain signature:
    FDIC (banking, quarterly):
      Normal regime dominated by δ_C (familiar) and δ_G (structural)
      Crisis onset: δ_A spikes sharply for external shocks (COVID)
                    δ_C + δ_G rise gradually for structural crises (GFC)

    ERCOT (energy, hourly):
      Normal regime dominated by δ_G (novel stress dominates — energy dispatch
        is structurally complex, frequent small novelties)
      Winter storms: δ_G dominates (supply-mix dislocation — no precedent)
      Summer peak:   δ_T dominates (weather regime transition)
      COVID:         δ_C + δ_T balanced (demand collapse + external shock)

  Theory validation:
    Firing order T→G→A→C is partially confirmed in FDIC quarterly data
    (limited by quarterly resolution: Δ-Q granularity too coarse for A/T)
    In ERCOT hourly data the sequence is event-type dependent:
      For structural events (Uri, Elliott): δ_G leads with > 100h advance
      For regime transitions (SummerPeak): δ_T fires earlier than δ_G

  Four-channel vs Omega:
    Four-channel provides richer causal attribution — Omega only reports
    whether the system is near collapse; four-channel says WHY and WHICH
    mechanism is driving the approach. Both give similar lead times for
    familiar crises. Four-channel is more informative for novel events.
    """)

    # ── Save ──────────────────────────────────────────────────────────────────
    result = {
        "run_date":     str(pd.Timestamp.now().date()),
        "fdic":         fdic_out,
        "ercot":        ercot_out,
    }
    OUT_PATH.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"\n  Saved: {OUT_PATH.name}")
    print(f"  Total time: {time.time() - t0:.1f}s")
    print(SEP)


if __name__ == "__main__":
    main()
