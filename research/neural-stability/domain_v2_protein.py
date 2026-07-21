"""
domain_v2_protein.py
====================
Domain I (REAL DATA v2) — Protein Folding: RCSB PDB B-factor profiles.

Data:  RCSB Protein Data Bank REST API — B-factors (temperature factors)
       per residue for 3 benchmark proteins:
         1UBQ  Ubiquitin         76  residues   room-temperature crystal
         1VII  Villin headpiece  35  residues   ultra-fast folder
         2CI2  Chymotrypsin inh  65  residues   two-state folder at Tm

B-factor interpretation:
  B_i = (8π²/3) <u_i²>  where u_i is the mean-square displacement.
  High B-factor → high mobility / flexibility → disorder / misfolding risk.
  Low B-factor  → rigid, ordered structure.

v2 improvements over test_protein_folding.py
  * Real experimental PDB data instead of synthetic Cα Go-model
  * ConfidenceGate: veto alarm when aggregate B-factor rate-of-change ≤ 0
    (flexibility must be actively increasing to fire a misfolding alarm)
  * DomainCircuitBreaker: after widespread misfolding alarm, suppress
    individual-residue alarms until B-factor normalises

Engine:  STRICT LOCKED CANONICAL-v4 ODE  (canonical_v4_engine.py)
         FrozenCanonicalV4 with reference window = low-B-factor (ordered) residues.

Author: Odeyemi Olusegun Israel
"""
from __future__ import annotations
import json, os, sys, io
import urllib.request
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from canonical_v4_engine import FrozenCanonicalV4
from canonical_v4_paper_style import evaluate_paper_style, channel_dominance_weighted, first_alarm_lead
from domain_bsdt_gateway_v2 import run_v2_gateway, rolling_derivative

OUTDIR    = r"c:\amttp\research\neural-stability\figures"
RESULTDIR = r"c:\amttp\research\neural-stability\results"
os.makedirs(OUTDIR, exist_ok=True); os.makedirs(RESULTDIR, exist_ok=True)
OUT_PNG   = os.path.join(OUTDIR,    "domain_v2_protein.png")
OUT_JSON  = os.path.join(RESULTDIR, "domain_v2_protein.json")

NAVY, GOLD, RUST, TEAL = "#1f3b73", "#c9a227", "#a23a1f", "#1a5f5f"

PDB_IDS = ["1UBQ", "1VII", "2CI2"]
PROTEIN_NAMES = {
    "1UBQ": "Ubiquitin (76 res)",
    "1VII": "Villin Headpiece (35 res)",
    "2CI2": "Chymotrypsin Inhibitor 2 (65 res)",
}

# Crisis definition: residues with B-factor > μ+2σ of the full protein = "hot" / disordered
CRISIS_B_ZSCORE = 2.0
# Reference window: residues with below-median B-factor (ordered core)
REF_B_FRACTION  = 0.50   # bottom half = ordered reference


# ─── PDB B-factor loader ──────────────────────────────────────────────────────

def fetch_pdb_bfactors(pdb_id: str, timeout: int = 15) -> dict:
    """
    Fetch PDB file from RCSB and parse Cα B-factors per residue.
    Returns {
        'residues': list of residue numbers,
        'bfactors': np.ndarray (n_residues,),
        'chain':    str,
    }
    Falls back to None on network error.
    """
    url = f"https://files.rcsb.org/download/{pdb_id.upper()}.pdb"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            text = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"  [WARN] Could not fetch {pdb_id} from RCSB: {e}")
        return None

    # Parse ATOM records for Cα (CA) atoms
    residues, bfactors = [], []
    seen_res = set()
    for line in text.splitlines():
        if not line.startswith("ATOM"):
            continue
        atom_name = line[12:16].strip()
        if atom_name != "CA":
            continue
        try:
            res_seq = int(line[22:26])
            b       = float(line[60:66])
            chain   = line[21].strip()
        except (ValueError, IndexError):
            continue
        if res_seq in seen_res:
            continue
        seen_res.add(res_seq)
        residues.append(res_seq)
        bfactors.append(b)

    if not bfactors:
        print(f"  [WARN] No Cα B-factors parsed for {pdb_id}")
        return None

    idx  = np.argsort(residues)
    return dict(
        pdb_id   = pdb_id,
        residues = [residues[i] for i in idx],
        bfactors = np.array([bfactors[i] for i in idx], dtype=float),
        chain    = chain,
        n_res    = len(residues),
    )


def bfactors_to_state_matrix(bfactors: np.ndarray, window: int = 5) -> np.ndarray:
    """
    Convert per-residue B-factors to a (T, n_agents, n_features) array
    where each "timestep" is a sliding window of residues along the sequence.

    T       = len(bfactors)
    agents  = individual residues  (N = len(bfactors))
    features = [B_raw, B_z, B_rolling_mean, B_rolling_std, B_gradient]
    → reshaped to (T=1, N, 5) for FrozenCanonicalV4 operating on residues as agents

    We treat the RESIDUE axis as the time axis (profile along chain = temporal
    sequence of structural states from N-terminus to C-terminus).
    """
    n   = len(bfactors)
    mu  = bfactors.mean(); sigma = bfactors.std() + 1e-8
    b_z = (bfactors - mu) / sigma

    roll_mu  = np.array([bfactors[max(0, i-window):i+1].mean() for i in range(n)])
    roll_std = np.array([bfactors[max(0, i-window):i+1].std()+1e-8 for i in range(n)])
    grad     = np.gradient(bfactors)

    X = np.stack([bfactors, b_z, roll_mu, roll_std, grad], axis=1)   # (n, 5)
    return X   # treated as (T=n_residues, n_features=5)


# ─── main ─────────────────────────────────────────────────────────────────────

def run_protein(pdb_id: str) -> dict | None:
    print(f"\n  [{pdb_id}] Fetching B-factors from RCSB PDB ...")
    data = fetch_pdb_bfactors(pdb_id)
    if data is None:
        return None

    bf    = data["bfactors"]
    n_res = len(bf)
    print(f"  [{pdb_id}] n_residues={n_res}  B_mean={bf.mean():.2f}  B_max={bf.max():.2f}")

    # State matrix: (T=n_res, d=5)
    X = bfactors_to_state_matrix(bf)

    # Reference: bottom REF_B_FRACTION of residues (ordered core)
    ref_cutoff = np.percentile(bf, REF_B_FRACTION * 100)
    ref_mask   = bf <= ref_cutoff   # (n_res,) bool — ordered residues

    # Canonical v4 engine (residues as agents, B-factor features)
    engine = FrozenCanonicalV4(alpha_base=1.0)
    engine.fit(X[ref_mask])
    result = engine.evaluate(X)

    # Paper-style presentation
    ps = evaluate_paper_style(engine, X, X[ref_mask])

    # Crisis ground truth: residues with B > μ+2σ = disordered
    b_mu, b_s  = bf.mean(), bf.std()
    crisis_mask = bf > (b_mu + CRISIS_B_ZSCORE * b_s)

    # Confidence gate signal: rolling derivative of B-factor
    conf_signal = rolling_derivative(bf, window=5)   # flexibility rate-of-change

    # v2 gateway
    v2 = run_v2_gateway(
        v1_alarms    = ps.alarms_paper,
        anomaly_score= result.score,
        conf_signal  = conf_signal,
        crisis_mask  = crisis_mask,
        conf_threshold = 0.47,
        halt_frac    = 0.08,
        resume_frac  = 0.01,
        cb_window    = min(20, n_res // 4),   # adaptive window for short chains
    )

    return dict(
        pdb_id=pdb_id,
        name=PROTEIN_NAMES.get(pdb_id, pdb_id),
        n_res=n_res,
        b_mean=float(bf.mean()),
        b_std=float(bf.std()),
        crisis_residues=int(crisis_mask.sum()),
        ref_residues=int(ref_mask.sum()),
        engine="FrozenCanonicalV4",
        v1_n_alarms=int(ps.alarms_paper.sum()),
        v2_n_alarms=int(v2["alarms_v2"].sum()),
        conf_gate_veto_pct=v2["conf_info"]["veto_pct"],
        cb_suppress_pct=v2["cb_info"]["suppress_pct"],
        improvement=v2.get("improvement", {}),
        theta=float(result.threshold),
        mean_E=float(result.E.mean()),
        lead_time_v1=first_alarm_lead(ps.alarms_paper, int(np.argmax(crisis_mask)) if crisis_mask.any() else len(crisis_mask)),
        lead_time_v2=first_alarm_lead(v2["alarms_v2"], int(np.argmax(crisis_mask)) if crisis_mask.any() else len(crisis_mask)),
        channel_dom=channel_dominance_weighted(ps, crisis_mask if crisis_mask.any() else np.ones(len(crisis_mask), bool)),
        # arrays for plotting (store as lists)
        bfactors=bf.tolist(),
        score_v1=result.score.tolist(),
        alarms_v1=ps.alarms_paper.astype(int).tolist(),
        alarms_v2=v2["alarms_v2"].astype(int).tolist(),
        crisis_mask=crisis_mask.astype(int).tolist(),
    )


def main() -> None:
    print("=" * 68)
    print("  DOMAIN I v2 — Protein Folding (RCSB PDB real B-factor data)")
    print("=" * 68)

    all_results = []
    for pdb_id in PDB_IDS:
        r = run_protein(pdb_id)
        if r is not None:
            all_results.append(r)

    if not all_results:
        print("  [ERROR] No PDB data could be fetched. Check network connection.")
        return

    # ── Plot ─────────────────────────────────────────────────────────────────
    n_prot = len(all_results)
    fig = plt.figure(figsize=(16, 4.5 * n_prot), facecolor="white")
    gs  = GridSpec(n_prot, 3, figure=fig, hspace=0.55, wspace=0.38)

    for row, r in enumerate(all_results):
        bf = np.array(r["bfactors"])
        sc = np.array(r["score_v1"])
        al1 = np.array(r["alarms_v1"], dtype=bool)
        al2 = np.array(r["alarms_v2"], dtype=bool)
        cr  = np.array(r["crisis_mask"], dtype=bool)
        resi = np.arange(len(bf))

        ax0 = fig.add_subplot(gs[row, 0])
        ax0.plot(resi, bf, color=NAVY, lw=1.5, label="B-factor")
        ax0.axhline(np.mean(bf) + 2*np.std(bf), color=RUST, ls="--", lw=1, label="μ+2σ (crisis)")
        ax0.scatter(resi[cr],  bf[cr],  color=RUST, s=20, zorder=5, label="Disordered")
        ax0.set_title(f"{r['name']}\nB-factor profile", fontsize=9, fontweight="bold")
        ax0.set_xlabel("Residue"); ax0.set_ylabel("B-factor (Å²)")
        ax0.legend(fontsize=7)

        ax1 = fig.add_subplot(gs[row, 1])
        ax1.plot(resi, sc, color=TEAL, lw=1.5, label="Canonical score")
        ax1.scatter(resi[al1], sc[al1], color=GOLD,  s=25, zorder=5, label=f"v1 alarms ({al1.sum()})")
        ax1.scatter(resi[al2], sc[al2], color=NAVY,  s=25, marker="^", zorder=6, label=f"v2 alarms ({al2.sum()})")
        ax1.set_title("Canonical V4 + v2 Gates", fontsize=9, fontweight="bold")
        ax1.set_xlabel("Residue"); ax1.set_ylabel("Anomaly score")
        ax1.legend(fontsize=7)

        ax2 = fig.add_subplot(gs[row, 2])
        imp = r.get("improvement", {})
        v1m = imp.get("v1", {}); v2m = imp.get("v2", {})
        cats = ["Precision", "Recall", "F1", "Lead\nsteps"]
        v1v  = [v1m.get("precision",0), v1m.get("recall",0), v1m.get("f1",0), v1m.get("lead_steps",0)/max(len(bf),1)*10]
        v2v  = [v2m.get("precision",0), v2m.get("recall",0), v2m.get("f1",0), v2m.get("lead_steps",0)/max(len(bf),1)*10]
        x    = np.arange(len(cats))
        ax2.bar(x - 0.2, v1v, 0.35, color=GOLD, label="v1 (baseline)")
        ax2.bar(x + 0.2, v2v, 0.35, color=NAVY, label="v2 (gated)")
        ax2.set_xticks(x); ax2.set_xticklabels(cats, fontsize=8)
        ax2.set_title("v1 → v2 Improvement", fontsize=9, fontweight="bold")
        ax2.legend(fontsize=7)

    fig.suptitle("Domain I v2 — Protein Folding: RCSB PDB Real B-factor Data\n"
                 "FrozenCanonicalV4 + tbr0p47 ConfidenceGate + CB halt/resume",
                 fontsize=11, fontweight="bold", y=1.01)
    fig.savefig(OUT_PNG, dpi=130, bbox_inches="tight")
    plt.close(fig)
    print(f"\n  Figure → {OUT_PNG}")

    # Summary
    print("\n  PDB     N_res  v1_alarms  v2_alarms  lead_v1  lead_v2  prec_v1  prec_v2")
    print("  " + "-" * 75)
    for r in all_results:
        imp = r.get("improvement", {})
        print(f"  {r['pdb_id']:<7} {r['n_res']:>5}  {r['v1_n_alarms']:>9}  "
              f"{r['v2_n_alarms']:>9}  {r['lead_time_v1']:>7}  {r['lead_time_v2']:>7}  "
              f"{imp.get('v1',{}).get('precision',0):>7.3f}  "
              f"{imp.get('v2',{}).get('precision',0):>7.3f}")

    # Save
    payload = dict(
        domain="protein_folding",
        version="v2",
        engine="FrozenCanonicalV4",
        gateway="tbr0p47_ConfidenceGate + DomainCircuitBreaker",
        data_source="RCSB PDB REST API",
        proteins=all_results,
    )
    # strip numpy arrays for JSON
    def _j(o):
        if isinstance(o, np.ndarray): return o.tolist()
        if isinstance(o, (np.integer,)): return int(o)
        if isinstance(o, (np.floating,)): return float(o)
        raise TypeError(type(o))
    with open(OUT_JSON, "w") as f:
        json.dump(payload, f, indent=2, default=_j)
    print(f"  JSON  → {OUT_JSON}")
    print("=" * 68)


if __name__ == "__main__":
    main()
