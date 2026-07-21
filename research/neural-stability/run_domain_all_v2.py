"""
run_domain_all_v2.py
====================
Master runner — executes all 6 domain v2 simulations sequentially,
collects results, prints a cross-domain comparison table, and saves a
consolidated summary JSON + a cross-domain comparison figure.

Domains:
  I   Protein Folding       domain_v2_protein.py
  II  Epidemiology          domain_v2_epidemiology.py
  III Information Flow      domain_v2_information_flow.py
  IV  Weather / Climate     domain_v2_weather.py
  V   Quantum Decoherence   domain_v2_quantum.py
  VI  Cybersecurity         domain_v2_cybersecurity.py

Author: Odeyemi Olusegun Israel
"""
from __future__ import annotations
import json, os, sys, time, traceback
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec

BASE = os.path.dirname(os.path.abspath(__file__))
if BASE not in sys.path:
    sys.path.insert(0, BASE)

OUTDIR    = os.path.join(BASE, "figures")
RESULTDIR = os.path.join(BASE, "results")
os.makedirs(OUTDIR, exist_ok=True)
os.makedirs(RESULTDIR, exist_ok=True)
SUMMARY_JSON = os.path.join(RESULTDIR, "domain_all_v2_summary.json")
SUMMARY_PNG  = os.path.join(OUTDIR,    "domain_all_v2_comparison.png")

NAVY, GOLD, RUST, TEAL, GREEN = "#1f3b73", "#c9a227", "#a23a1f", "#1a5f5f", "#2d7a2d"

# ─── domain registry ──────────────────────────────────────────────────────────
DOMAINS = [
    dict(id="I",   label="Protein\nFolding",       module="domain_v2_protein",
         result_json=os.path.join(RESULTDIR, "domain_v2_protein.json")),
    dict(id="II",  label="Epidemiology",            module="domain_v2_epidemiology",
         result_json=os.path.join(RESULTDIR, "domain_v2_epidemiology.json")),
    dict(id="III", label="Information\nFlow",       module="domain_v2_information_flow",
         result_json=os.path.join(RESULTDIR, "domain_v2_information_flow.json")),
    dict(id="IV",  label="Weather /\nClimate",      module="domain_v2_weather",
         result_json=os.path.join(RESULTDIR, "domain_v2_weather.json")),
    dict(id="V",   label="Quantum\nDecoherence",    module="domain_v2_quantum",
         result_json=os.path.join(RESULTDIR, "domain_v2_quantum.json")),
    dict(id="VI",  label="Cybersecurity",           module="domain_v2_cybersecurity",
         result_json=os.path.join(RESULTDIR, "domain_v2_cybersecurity.json")),
]


# ─── runner helpers ───────────────────────────────────────────────────────────

def run_domain(domain: dict) -> dict:
    """
    Import the domain module and call its main().
    Returns a status dict.
    """
    t0 = time.time()
    try:
        mod = __import__(domain["module"])
        mod.main()
        elapsed = time.time() - t0
        return dict(ok=True, elapsed=elapsed, error=None)
    except Exception as e:
        elapsed = time.time() - t0
        print(f"\n  [ERROR] {domain['module']} failed: {e}")
        traceback.print_exc()
        return dict(ok=False, elapsed=elapsed, error=str(e))


def load_result(domain: dict) -> dict | None:
    """Load the JSON result written by the domain script."""
    path = domain["result_json"]
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None


def _metric(result: dict | None, key: str, default=float("nan")):
    if result is None:
        return default
    v = result.get(key, default)
    if isinstance(v, dict):
        # nested improvement dict
        v2 = v.get("v2", {})
        if isinstance(v2, dict):
            return v2.get(key.replace("v2_",""), default)
    return v if v is not None else default


def extract_v2_precision(result: dict | None) -> float:
    if result is None: return float("nan")
    imp = result.get("improvement", {})
    return float(imp.get("v2", {}).get("precision", float("nan")))


def extract_v1_precision(result: dict | None) -> float:
    if result is None: return float("nan")
    imp = result.get("improvement", {})
    return float(imp.get("v1", {}).get("precision", float("nan")))


def extract_v2_f1(result: dict | None) -> float:
    if result is None: return float("nan")
    imp = result.get("improvement", {})
    return float(imp.get("v2", {}).get("f1", float("nan")))


def extract_v1_f1(result: dict | None) -> float:
    if result is None: return float("nan")
    imp = result.get("improvement", {})
    return float(imp.get("v1", {}).get("f1", float("nan")))


# ─── comparison figure ────────────────────────────────────────────────────────

def make_comparison_figure(results: list[dict | None], domain_labels: list[str]) -> None:
    n = len(results)
    v1_prec = [extract_v1_precision(r) for r in results]
    v2_prec = [extract_v2_precision(r) for r in results]
    v1_f1   = [extract_v1_f1(r) for r in results]
    v2_f1   = [extract_v2_f1(r) for r in results]
    v1_alm  = [float(_metric(r, "v1_alarms", 0)) for r in results]
    v2_alm  = [float(_metric(r, "v2_alarms", 0)) for r in results]
    cb_sup  = [float(_metric(r, "cb_suppress_pct", 0)) for r in results]
    gate_v  = [float(_metric(r, "conf_veto_pct", 0)) for r in results]
    lead_v1 = [float(_metric(r, "lead_time_v1", 0)) for r in results]
    lead_v2 = [float(_metric(r, "lead_time_v2", 0)) for r in results]
    # protein stores them under results.proteins[0]
    for i, r in enumerate(results):
        if r is not None and "proteins" in r:
            p = r["proteins"][0] if r["proteins"] else {}
            imp = p.get("improvement", {})
            v1_prec[i] = float(imp.get("v1", {}).get("precision", float("nan")))
            v2_prec[i] = float(imp.get("v2", {}).get("precision", float("nan")))
            v1_f1[i]   = float(imp.get("v1", {}).get("f1", float("nan")))
            v2_f1[i]   = float(imp.get("v2", {}).get("f1", float("nan")))
            v1_alm[i]  = float(p.get("v1_n_alarms", 0))
            v2_alm[i]  = float(p.get("v2_n_alarms", 0))
            cb_sup[i]  = float(p.get("cb_suppress_pct", 0))
            gate_v[i]  = float(p.get("conf_gate_veto_pct", 0))

    x    = np.arange(n)
    w    = 0.35
    labs = domain_labels

    def _nan_bar(ax, x_pos, vals, color, label, **kw):
        """Plot bars, shading NaN positions."""
        heights = [v if not np.isnan(v) else 0 for v in vals]
        bars = ax.bar(x_pos, heights, color=color, label=label, **kw)
        for xi, v in zip(x_pos, vals):
            if np.isnan(v):
                ax.text(xi, 0.02, "N/A", ha="center", va="bottom", fontsize=6, color="gray")
        return bars

    fig = plt.figure(figsize=(18, 12), facecolor="white")
    gs  = GridSpec(2, 3, figure=fig, hspace=0.55, wspace=0.40)

    # 1. Precision v1 vs v2
    ax = fig.add_subplot(gs[0, 0])
    _nan_bar(ax, x - w/2, v1_prec, GOLD, "v1 baseline", width=w)
    _nan_bar(ax, x + w/2, v2_prec, NAVY, "v2 gated",    width=w)
    ax.set_xticks(x); ax.set_xticklabels(labs, fontsize=7)
    ax.set_title("Precision: v1 vs v2", fontsize=10, fontweight="bold")
    ax.set_ylabel("Precision"); ax.set_ylim(0, 1.1); ax.legend(fontsize=8)
    ax.axhline(0.47, ls="--", color=RUST, lw=0.8)

    # 2. F1 v1 vs v2
    ax = fig.add_subplot(gs[0, 1])
    _nan_bar(ax, x - w/2, v1_f1, GOLD, "v1 baseline", width=w)
    _nan_bar(ax, x + w/2, v2_f1, NAVY, "v2 gated",    width=w)
    ax.set_xticks(x); ax.set_xticklabels(labs, fontsize=7)
    ax.set_title("F1 Score: v1 vs v2", fontsize=10, fontweight="bold")
    ax.set_ylabel("F1"); ax.set_ylim(0, 1.1); ax.legend(fontsize=8)

    # 3. Alarm counts
    ax = fig.add_subplot(gs[0, 2])
    _nan_bar(ax, x - w/2, v1_alm, GOLD, "v1 alarms", width=w)
    _nan_bar(ax, x + w/2, v2_alm, NAVY, "v2 alarms", width=w)
    ax.set_xticks(x); ax.set_xticklabels(labs, fontsize=7)
    ax.set_title("Alarm Counts: v1 vs v2", fontsize=10, fontweight="bold")
    ax.set_ylabel("# alarms"); ax.legend(fontsize=8)

    # 4. Gate veto + CB suppress
    ax = fig.add_subplot(gs[1, 0])
    _nan_bar(ax, x - w/2, gate_v, GOLD, "Gate veto %", width=w)
    _nan_bar(ax, x + w/2, cb_sup, TEAL, "CB suppress %", width=w)
    ax.set_xticks(x); ax.set_xticklabels(labs, fontsize=7)
    ax.set_title("Gate Veto & CB Suppress (%)", fontsize=10, fontweight="bold")
    ax.set_ylabel("% alarms filtered"); ax.legend(fontsize=8)

    # 5. Lead time comparison
    ax = fig.add_subplot(gs[1, 1])
    _nan_bar(ax, x - w/2, lead_v1, GOLD, "lead_v1", width=w)
    _nan_bar(ax, x + w/2, lead_v2, NAVY, "lead_v2", width=w)
    ax.set_xticks(x); ax.set_xticklabels(labs, fontsize=7)
    ax.set_title("Lead Time (steps before crisis)", fontsize=10, fontweight="bold")
    ax.set_ylabel("Steps"); ax.legend(fontsize=8)

    # 6. Net precision improvement
    ax = fig.add_subplot(gs[1, 2])
    delta = [v2 - v1 if not (np.isnan(v2) or np.isnan(v1)) else 0.0
             for v1, v2 in zip(v1_prec, v2_prec)]
    colors_d = [GREEN if d >= 0 else RUST for d in delta]
    ax.bar(x, delta, color=colors_d, width=0.6)
    ax.axhline(0, color="black", lw=0.8)
    ax.set_xticks(x); ax.set_xticklabels(labs, fontsize=7)
    ax.set_title("Net Precision Improvement (v2 − v1)", fontsize=10, fontweight="bold")
    ax.set_ylabel("Δ Precision")

    fig.suptitle(
        "Cross-Domain BSDT Algorithm Benchmark — v2 (tbr0p47 ConfidenceGate + CB halt/resume)\n"
        "FrozenCanonicalV4 engine applied to 6 scientific domains with real data",
        fontsize=12, fontweight="bold"
    )
    fig.savefig(SUMMARY_PNG, dpi=130, bbox_inches="tight")
    plt.close(fig)
    print(f"\n  Comparison figure → {SUMMARY_PNG}")


# ─── main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    print("=" * 72)
    print("  BSDT CROSS-DOMAIN v2 — ALL DOMAINS MASTER RUNNER")
    print("  Algorithm: FrozenCanonicalV4 + tbr0p47 ConfidenceGate + CB halt/resume")
    print("=" * 72)
    print()

    run_summary = []
    results     = []

    for domain in DOMAINS:
        header = f"Domain {domain['id']}: {domain['label'].replace(chr(10), ' ')}"
        print(f"\n{'─'*68}")
        print(f"  {header}")
        print(f"{'─'*68}")
        status = run_domain(domain)
        result = load_result(domain)
        run_summary.append(dict(
            domain_id   = domain["id"],
            label       = domain["label"].replace("\n", " "),
            module      = domain["module"],
            ok          = status["ok"],
            elapsed_s   = round(status["elapsed"], 2),
            error       = status["error"],
        ))
        results.append(result)

    # ── Cross-domain comparison table ─────────────────────────────────────────
    print("\n\n" + "=" * 72)
    print("  CROSS-DOMAIN COMPARISON TABLE")
    print("=" * 72)
    print(f"  {'Dom':<5} {'Domain':<22} {'v1_alm':>7} {'v2_alm':>7} "
          f"{'prec_v1':>8} {'prec_v2':>8} {'f1_v1':>7} {'f1_v2':>7} "
          f"{'lead_v1':>8} {'lead_v2':>8} {'cb_sup%':>8}")
    print("  " + "-" * 92)

    for i, (domain, r) in enumerate(zip(DOMAINS, results)):
        if r is None:
            print(f"  {domain['id']:<5} {domain['label'].replace(chr(10),' '):<22}  FAILED")
            continue

        # Extract from top-level or protein sub-list
        v1_alm = _metric(r, "v1_alarms", "?")
        v2_alm = _metric(r, "v2_alarms", "?")
        if r.get("proteins"):
            p   = r["proteins"][0]
            imp = p.get("improvement", {})
            p1  = imp.get("v1",{}).get("precision", float("nan"))
            p2  = imp.get("v2",{}).get("precision", float("nan"))
            f1  = imp.get("v1",{}).get("f1", float("nan"))
            f2  = imp.get("v2",{}).get("f1", float("nan"))
            v1_alm = p.get("v1_n_alarms", "?")
            v2_alm = p.get("v2_n_alarms", "?")
            cb_sup = p.get("cb_suppress_pct", float("nan"))
            lv1    = p.get("lead_time_v1", "?")
            lv2    = p.get("lead_time_v2", "?")
        else:
            imp = r.get("improvement", {})
            p1  = imp.get("v1",{}).get("precision", float("nan"))
            p2  = imp.get("v2",{}).get("precision", float("nan"))
            f1  = imp.get("v1",{}).get("f1", float("nan"))
            f2  = imp.get("v2",{}).get("f1", float("nan"))
            cb_sup = r.get("cb_suppress_pct", float("nan"))
            lv1    = r.get("lead_time_v1", "?")
            lv2    = r.get("lead_time_v2", "?")

        label = domain['label'].replace('\n', ' ')
        print(f"  {domain['id']:<5} {label:<22} {v1_alm:>7} {v2_alm:>7} "
              f"  {p1:>6.3f}   {p2:>6.3f}  {f1:>5.3f}  {f2:>5.3f} "
              f"  {str(lv1):>7}  {str(lv2):>7}  {cb_sup:>7.1f}%")

    print("=" * 72)

    # ── timing table ──────────────────────────────────────────────────────────
    print("\n  TIMING:")
    total_time = sum(s["elapsed_s"] for s in run_summary)
    for s in run_summary:
        status_str = "✓" if s["ok"] else "✗"
        print(f"  {status_str} {s['label']:<30} {s['elapsed_s']:>7.1f}s"
              + (f"  ERROR: {s['error'][:60]}" if s["error"] else ""))
    print(f"  Total: {total_time:.1f}s")

    # ── comparison figure ─────────────────────────────────────────────────────
    make_comparison_figure(results, [d["label"] for d in DOMAINS])

    # ── save summary JSON ─────────────────────────────────────────────────────
    payload = dict(
        version="v2",
        engine="FrozenCanonicalV4",
        gateway="tbr0p47_ConfidenceGate + DomainCircuitBreaker",
        domains=run_summary,
        results={d["id"]: r for d, r in zip(DOMAINS, results) if r is not None},
    )
    def _j(o):
        if isinstance(o, np.ndarray): return o.tolist()
        if isinstance(o, (np.integer,)): return int(o)
        if isinstance(o, (np.floating,)): return float(o)
        raise TypeError(type(o))
    with open(SUMMARY_JSON, "w") as f:
        json.dump(payload, f, indent=2, default=_j)
    print(f"\n  Summary JSON → {SUMMARY_JSON}")
    print("  Done.")
    print("=" * 72)


if __name__ == "__main__":
    main()
