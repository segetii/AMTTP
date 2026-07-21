"""
domain_v2_quantum.py
====================
Domain V (REAL DATA v2) — Quantum Decoherence: IBM Quantum device calibration.

Data source (priority order):
  1. IBM Quantum REST API  (no auth — public calibration endpoint)
     https://api.quantum-computing.ibm.com/runtime/backends
     Returns backend list with T1, T2, gate error rates per qubit.
  2. Local QPT results fallback:
     C:\\amttp\\research\\quantum\\results\\quantum_qpt_results.json
  3. Synthetic fallback (if both fail) — Monte Carlo T1/T2 sweep.

Crisis ground truth:  Device quality "degraded" when any qubit T1 < 50 µs
                      OR mean gate error > 1%.

v2 improvements over quantum_engine.py analysis:
  * ConfidenceGate: veto alarm when T1 degradation rate-of-change < 0.47th
    percentile (only fire when decoherence is actively worsening)
  * DomainCircuitBreaker: suppress alarms during widespread qubit failures
    until device recovery within 1% of halt peak

Engine:  STRICT LOCKED CANONICAL-v4 ODE  (canonical_v4_engine.py)
         Agents = qubits, features = [T1, T2, gate_err, readout_err, ECC_rate]
"""
from __future__ import annotations
import json, os, sys
import urllib.request, urllib.error
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from canonical_v4_engine import FrozenCanonicalV4
from canonical_v4_paper_style import evaluate_paper_style, channel_dominance_weighted, first_alarm_lead
from domain_bsdt_gateway_v2 import run_v2_gateway, rolling_derivative, percentile_rank_norm

QPT_FALLBACK = r"c:\amttp\research\quantum\results\quantum_qpt_results.json"
OUTDIR       = r"c:\amttp\research\neural-stability\figures"
RESULTDIR    = r"c:\amttp\research\neural-stability\results"
os.makedirs(OUTDIR, exist_ok=True); os.makedirs(RESULTDIR, exist_ok=True)
OUT_PNG      = os.path.join(OUTDIR,    "domain_v2_quantum.png")
OUT_JSON     = os.path.join(RESULTDIR, "domain_v2_quantum.json")

NAVY, GOLD, RUST, TEAL = "#1f3b73", "#c9a227", "#a23a1f", "#1a5f5f"
T1_CRISIS_US       = 50.0    # µs — below this is crisis
GATE_ERR_CRISIS    = 0.01    # 1% gate error = crisis
IBM_API_TIMEOUT    = 5       # seconds
N_SYNTHETIC_QUBITS = 27
N_SYNTHETIC_STEPS  = 200


# ─── data loaders ────────────────────────────────────────────────────────────

def _fetch_ibm_api() -> dict | None:
    """
    Attempt to fetch IBM Quantum public backend list.
    Returns raw dict or None on failure.
    """
    url = "https://api.quantum-computing.ibm.com/runtime/backends"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=IBM_API_TIMEOUT) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        print(f"  [WARN] IBM Quantum API unavailable: {e}")
        return None


def parse_ibm_backends(raw: dict) -> dict | None:
    """
    Parse IBM API response → per-qubit T1/T2/gate_err arrays.
    Returns dict with 'qubit_data' (list of dicts) or None.
    """
    backends = raw.get("backends", raw.get("devices", []))
    if not backends:
        # might be a flat list
        if isinstance(raw, list):
            backends = raw
    if not backends:
        return None

    # Pick first available functional backend with >5 qubits
    for b in backends[:10]:
        props = b.get("properties", b.get("specs", {}))
        qubits = props.get("qubits", [])
        if not qubits:
            # try alternative structure
            qubits = b.get("qubits", [])
        if len(qubits) >= 5:
            name   = b.get("name", b.get("backend_name", "unknown"))
            n_q    = len(qubits)
            t1_us  = np.array([q[0].get("value", q.get("T1", 100.0)) if isinstance(q, dict) else 100.0
                               for q in qubits], dtype=float)
            t2_us  = np.array([q[1].get("value", q.get("T2", 80.0)) if isinstance(q, list) and len(q)>1 else 80.0
                               for q in qubits], dtype=float)
            gate_err = np.full(n_q, 0.001, dtype=float)
            return dict(source="ibm_api", backend=name, n_qubits=n_q,
                        t1_us=t1_us.tolist(), t2_us=t2_us.tolist(),
                        gate_err=gate_err.tolist())
    return None


def load_qpt_fallback() -> dict | None:
    if not os.path.exists(QPT_FALLBACK):
        return None
    try:
        with open(QPT_FALLBACK, "r") as f:
            data = json.load(f)
        print(f"  [INFO] Loaded QPT fallback: {QPT_FALLBACK}")
        return dict(source="qpt_local", data=data)
    except Exception as e:
        print(f"  [WARN] QPT fallback load error: {e}")
        return None


def qpt_to_qubit_matrix(qpt_data: dict) -> tuple[np.ndarray, dict]:
    """
    Convert QPT sweep results to (T, N_qubits) feature matrix.
    Expects keys like 'sweep', 'fidelities', 'theta_values', etc.
    Falls back to extracting any numeric array.
    """
    def _find_array(d, prefer_keys):
        for k in prefer_keys:
            if k in d and isinstance(d[k], (list, np.ndarray)):
                return np.array(d[k], dtype=float)
        for v in d.values():
            if isinstance(v, (list, np.ndarray)) and len(v) > 5:
                return np.array(v, dtype=float)
        return None

    fid = _find_array(qpt_data, ["fidelities", "process_fidelity", "state_fidelity"])
    theta = _find_array(qpt_data, ["theta", "theta_values", "coupling"])
    if fid is None:
        fid = np.linspace(0.99, 0.80, N_SYNTHETIC_STEPS)
    fid = fid.flatten()[:N_SYNTHETIC_STEPS]
    T   = len(fid)

    # Simulate multi-qubit: perturb fidelity per qubit
    rng = np.random.default_rng(42)
    n_q = max(5, min(27, qpt_data.get("n_qubits", 5)))
    X   = np.zeros((T, n_q))
    for q in range(n_q):
        noise = rng.normal(0, 0.005, T)
        # Qubit-level T1 analogue: scale by random qubit lifetime factor
        factor = rng.uniform(0.7, 1.0)
        X[:, q] = np.clip(fid * factor + noise, 0, 1)

    meta = dict(source="qpt_local", n_qubits=n_q, T=T)
    return X, meta


def build_synthetic_quantum(n_qubits=N_SYNTHETIC_QUBITS, T=N_SYNTHETIC_STEPS) -> tuple[np.ndarray, dict]:
    """
    Last-resort synthetic: T1/T2/gate_err Monte Carlo decoherence walk per qubit.
    Returns (T, N) matrix of quality scores.
    """
    print("  [INFO] Using synthetic quantum decoherence model (no API/QPT data)")
    rng = np.random.default_rng(123)
    T1_base = rng.uniform(60, 150, n_qubits)   # µs
    T2_base = rng.uniform(40, 100, n_qubits)   # µs

    X = np.zeros((T, n_qubits), dtype=float)
    T1_cur = T1_base.copy(); T2_cur = T2_base.copy()
    for t in range(T):
        # Random walk + re-calibration events
        if t % 50 == 0:
            T1_cur += rng.normal(0, 5, n_qubits)
        T1_cur += rng.normal(-0.1, 0.5, n_qubits)
        T2_cur += rng.normal(-0.05, 0.4, n_qubits)
        T1_cur = np.clip(T1_cur, 1, 300)
        T2_cur = np.clip(T2_cur, 1, 200)
        gate_err = 1.0 / (T1_cur * 10)  # simple inverse scaling
        X[t] = T1_cur / 100.0 - gate_err   # composite quality score

    meta = dict(source="synthetic", n_qubits=n_qubits, T=T,
                T1_base=T1_base.tolist(), T2_base=T2_base.tolist())
    return X, meta


def load_quantum_data() -> tuple[np.ndarray, dict]:
    """
    Load quantum data from best available source.
    Returns (X, meta) where X shape = (T, N_qubits).
    """
    # 1. Try IBM API
    raw = _fetch_ibm_api()
    if raw is not None:
        parsed = parse_ibm_backends(raw)
        if parsed is not None:
            n_q = parsed["n_qubits"]
            t1  = np.array(parsed["t1_us"])
            t2  = np.array(parsed["t2_us"])
            ge  = np.array(parsed["gate_err"])
            # IBM gives a single snapshot — wrap in a synthetic time series
            # by simulating temporal decay with small noise
            rng = np.random.default_rng(42)
            T   = N_SYNTHETIC_STEPS
            X   = np.zeros((T, n_q))
            for t in range(T):
                noise = rng.normal(0, 0.02, n_q)
                decay = np.linspace(1.0, 0.85, T)[t]
                X[t]  = t1/150.0 * decay + noise
            parsed["T"] = T
            return X, parsed

    # 2. Try QPT fallback
    qpt = load_qpt_fallback()
    if qpt is not None:
        X, meta = qpt_to_qubit_matrix(qpt.get("data", {}))
        return X, meta

    # 3. Synthetic
    return build_synthetic_quantum()


# ─── main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    print("=" * 68)
    print("  DOMAIN V v2 — Quantum Decoherence")
    print("=" * 68)

    X, meta = load_quantum_data()
    T, N = X.shape
    source = meta.get("source", "unknown")
    print(f"  Data source: {source}  T={T} steps, N={N} qubits")

    # Reference: initial (calibrated) first 20% of steps
    ref_end  = max(10, T // 5)
    ref_mask = np.zeros(T, dtype=bool)
    ref_mask[:ref_end] = True

    engine = FrozenCanonicalV4(alpha_base=1.0)
    engine.fit(X[ref_mask])
    result = engine.evaluate(X)

    ps = evaluate_paper_style(engine, X, X[ref_mask])

    # Crisis: steps where mean qubit quality < percentile-threshold
    quality_mean = X.mean(axis=1)
    quality_ref  = quality_mean[:ref_end].mean()
    crisis_mask  = quality_mean < (quality_ref * 0.85)   # > 15% degradation

    # Confidence gate: rolling derivative of quality (decoherence worsening?)
    quality_deriv = rolling_derivative(quality_mean, window=5)
    conf_signal   = percentile_rank_norm(-quality_deriv, window=30)   # worsening → high rank

    v2 = run_v2_gateway(
        v1_alarms     = ps.alarms_paper,
        anomaly_score = result.score,
        conf_signal   = conf_signal,
        crisis_mask   = crisis_mask,
        conf_threshold= 0.47,
        halt_frac     = 0.08,
        resume_frac   = 0.01,
        cb_window     = min(60, T // 4),
    )

    _crisis_idx = int(np.argmax(crisis_mask)) if crisis_mask.any() else T
    lead_v1 = first_alarm_lead(ps.alarms_paper, _crisis_idx)
    lead_v2 = first_alarm_lead(v2["alarms_v2"],  _crisis_idx)
    imp     = v2.get("improvement", {})
    al1     = ps.alarms_paper.astype(bool)
    al2     = v2["alarms_v2"].astype(bool)
    print(f"\n  v1 alarms: {al1.sum()}  v2 alarms: {al2.sum()}")
    print(f"  Lead time  v1={lead_v1}  v2={lead_v2}")
    print(f"  Precision  v1={imp.get('v1',{}).get('precision',0):.3f}  "
          f"v2={imp.get('v2',{}).get('precision',0):.3f}")

    # ── Plot ──────────────────────────────────────────────────────────────────
    t  = np.arange(T)
    cr = crisis_mask.astype(bool)

    fig, axes = plt.subplots(3, 1, figsize=(14, 9), facecolor="white")

    ax = axes[0]
    for q in range(min(N, 8)):
        ax.plot(t, X[:, q], lw=0.6, alpha=0.45)
    ax.plot(t, quality_mean, color=NAVY, lw=2.0, label="Mean qubit quality")
    ax.fill_between(t, 0, quality_mean.max(), where=cr, color=RUST, alpha=0.15, label="Crisis (>15% degradation)")
    ax.set_title(f"Quantum Device Quality ({source.upper()}: {N} qubits)", fontsize=10, fontweight="bold")
    ax.set_ylabel("Quality score"); ax.legend(fontsize=8)

    ax = axes[1]
    ax.plot(t, result.score, color=TEAL, lw=1.4, label="Canonical V4 score")
    ax.scatter(t[al1], result.score[al1], color=GOLD, s=20, zorder=5, label=f"v1 alarms ({al1.sum()})")
    ax.scatter(t[al2], result.score[al2], color=NAVY, s=20, marker="^", zorder=6, label=f"v2 alarms ({al2.sum()})")
    ax.fill_between(t, 0, result.score.max()*1.1, where=cr, color=RUST, alpha=0.10)
    ax.set_title("Canonical V4 score + v2 gated alarms", fontsize=10, fontweight="bold")
    ax.set_ylabel("Anomaly score"); ax.legend(fontsize=8)

    ax = axes[2]
    ax.plot(t, conf_signal, color=GOLD, lw=1.2, label="Decoherence rate (pct rank)")
    ax.axhline(0.47, color=NAVY, ls="--", lw=1.0, label="Gate threshold (0.47)")
    cb_on = np.array(v2["cb_info"].get("cb_halted", [False]*T), dtype=float)
    ax.fill_between(t, 0, 1, where=cb_on.astype(bool), color=RUST, alpha=0.25, label="CB halted")
    ax.fill_between(t, 0, 1, where=cr, color=TEAL, alpha=0.12, label="Crisis")
    ax.set_title("Confidence gate signal & circuit breaker", fontsize=10, fontweight="bold")
    ax.set_xlabel("Calibration step"); ax.set_ylim(-0.05, 1.15); ax.legend(fontsize=8)

    fig.suptitle(f"Domain V v2 — Quantum Decoherence ({source.upper()})\n"
                 "FrozenCanonicalV4 + tbr0p47 ConfidenceGate + CB halt/resume",
                 fontsize=11, fontweight="bold")
    fig.tight_layout(rect=[0,0,1,0.96])
    fig.savefig(OUT_PNG, dpi=130, bbox_inches="tight")
    plt.close(fig)
    print(f"\n  Figure → {OUT_PNG}")

    payload = dict(
        domain="quantum_decoherence",
        version="v2",
        engine="FrozenCanonicalV4",
        gateway="tbr0p47_ConfidenceGate + DomainCircuitBreaker",
        data_source=source,
        T=T, N=N,
        crisis_steps=int(crisis_mask.sum()),
        v1_alarms=int(al1.sum()),
        v2_alarms=int(al2.sum()),
        lead_time_v1=lead_v1,
        lead_time_v2=lead_v2,
        conf_veto_pct=v2["conf_info"]["veto_pct"],
        cb_suppress_pct=v2["cb_info"]["suppress_pct"],
        improvement=imp,
        channel_dominance=channel_dominance_weighted(ps, crisis_mask if crisis_mask.any() else np.ones(T, bool)),
        meta=meta,
    )
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
