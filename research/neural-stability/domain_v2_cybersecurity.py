"""
domain_v2_cybersecurity.py
===========================
Domain VI (REAL DATA v2) — Cybersecurity: TON-IoT intrusion detection.

Data source:  C:\\amttp\\data\\external_validation\\cyber\\ton_iot_network.csv
              TON-IoT 2020 dataset — network flow-level features with
              binary label (0=normal, 1=attack).

v2 improvements over cyber_frozen_window_validation.py:
  * ConfidenceGate: veto alarm when per-flow entropy rate < 0.47th percentile
    (require elevated flow-entropy diversity to confirm attack class)
  * DomainCircuitBreaker: after DDoS/attack confirmed (score +8% above peak),
    suppress until traffic entropy returns toward baseline within 1%

Engine:  STRICT LOCKED CANONICAL-v4 ODE  (canonical_v4_engine.py)
         Agents = flows (N random samples per window), features = network flow stats:
         [bytes_in, bytes_out, pkts_in, pkts_out, duration, proto_enc, entropy]

Crisis ground truth:  label == 1 (attack) per time window.
"""
from __future__ import annotations
import json, os, sys
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from canonical_v4_engine import FrozenCanonicalV4
from canonical_v4_paper_style import evaluate_paper_style, channel_dominance_weighted, first_alarm_lead
from domain_bsdt_gateway_v2 import run_v2_gateway, percentile_rank_norm

CSV_PATH  = r"c:\amttp\data\external_validation\cyber\ton_iot_network.csv"
OUTDIR    = r"c:\amttp\research\neural-stability\figures"
RESULTDIR = r"c:\amttp\research\neural-stability\results"
os.makedirs(OUTDIR, exist_ok=True); os.makedirs(RESULTDIR, exist_ok=True)
OUT_PNG   = os.path.join(OUTDIR,    "domain_v2_cybersecurity.png")
OUT_JSON  = os.path.join(RESULTDIR, "domain_v2_cybersecurity.json")

NAVY, GOLD, RUST, TEAL = "#1f3b73", "#c9a227", "#a23a1f", "#1a5f5f"

WINDOW_SIZE    = 200      # flows per temporal window
STEP_SIZE      = 50       # stride for sliding windows
N_AGENTS       = 20       # flows sampled per window as "agents"
MAX_WINDOWS    = 500      # cap for feasible run time
REF_WIN_COUNT  = 20       # first N windows as normal reference
CB_WINDOW      = 60       # windows rolling max


# ─── feature cols ─────────────────────────────────────────────────────────────

CANDIDATE_FEATURES = [
    # numeric flow stats — pick whichever are present
    "src_bytes", "dst_bytes", "sbytes", "dbytes",
    "src_pkts", "dst_pkts", "spkts", "dpkts",
    "duration", "conn_state_enc", "proto_enc",
    "bytes_in", "bytes_out", "pkts_in", "pkts_out",
    "flow_duration", "tot_fwd_pkts", "tot_bwd_pkts",
    "total_fwd_packets", "total_backward_packets",
    "fwd_pkt_len_mean", "bwd_pkt_len_mean",
    "flow_byts_s", "flow_pkts_s",
]
CANDIDATE_LABELS = ["label", "Label", "class", "Class", "attack", "Attack"]


def load_ton_iot(csv_path: str, max_rows: int = MAX_WINDOWS * WINDOW_SIZE) -> tuple[pd.DataFrame, str]:
    """
    Load TON-IoT CSV, auto-detect feature and label columns.
    Returns (df, label_col).
    """
    df = pd.read_csv(csv_path, nrows=max_rows, low_memory=False)
    df.columns = df.columns.str.strip()

    label_col = next((c for c in CANDIDATE_LABELS if c in df.columns), None)
    if label_col is None:
        # Try to find by content
        for c in df.columns:
            try:
                uv = df[c].dropna().astype(str).str.lower().unique()
                if set(uv) <= {"0","1","normal","attack","benign","anomaly"}:
                    label_col = c; break
            except Exception:
                pass
    if label_col is None:
        raise ValueError(f"Cannot find label column in {csv_path}. "
                         f"Columns: {list(df.columns)[:20]}")

    print(f"  Label column: '{label_col}'  unique={df[label_col].unique()[:5]}")

    # Encode label to 0/1
    lv = df[label_col].astype(str).str.lower()
    df["_label_bin"] = lv.map(lambda x: 0 if x in ["0","normal","benign"] else 1).fillna(0).astype(int)

    return df, label_col


def select_features(df: pd.DataFrame) -> list[str]:
    """Pick available numeric feature columns."""
    numeric_cols = [c for c in CANDIDATE_FEATURES if c in df.columns]
    if len(numeric_cols) >= 3:
        return numeric_cols[:10]
    # Fallback: all numeric except label
    num = df.select_dtypes(include="number").columns.tolist()
    return [c for c in num if "_label" not in c][:10]


def flow_entropy(flows: np.ndarray) -> float:
    """
    Compute Shannon entropy of per-column distributions (bytes/pkts diversity).
    High entropy = diverse flow mix = more varied (possibly attack) traffic.
    """
    entropies = []
    for col in flows.T:
        col = col[np.isfinite(col)]
        if len(col) < 2: continue
        edges     = np.histogram_bin_edges(col, bins=min(20, len(col)//2))
        counts, _ = np.histogram(col, bins=edges)
        probs     = counts / (counts.sum() + 1e-12)
        probs     = probs[probs > 0]
        entropies.append(-np.sum(probs * np.log2(probs + 1e-12)))
    return float(np.mean(entropies)) if entropies else 0.0


def build_temporal_windows(df: pd.DataFrame, feat_cols: list[str]
                           ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Slide a window over sorted flows to create temporal feature matrix.

    Returns:
        X_windows : (num_windows, N_AGENTS * len(feat_cols)) — flattened agent features
        labels    : (num_windows,) — fraction of attack flows per window
        entropies : (num_windows,) — flow entropy for confidence gate
    """
    n_rows   = len(df)
    idxs     = range(0, n_rows - WINDOW_SIZE, STEP_SIZE)
    if not list(idxs):
        idxs = [0]

    rng      = np.random.default_rng(42)
    windows  = []; labels_w = []; ent_w = []

    for i, start in enumerate(idxs):
        if i >= MAX_WINDOWS: break
        chunk   = df.iloc[start:start+WINDOW_SIZE]
        F       = chunk[feat_cols].values.astype(float)
        lbl     = chunk["_label_bin"].values

        # Replace inf/nan
        F = np.nan_to_num(F, nan=0.0, posinf=0.0, neginf=0.0)

        # Log-transform skewed byte / packet counts
        F = np.sign(F) * np.log1p(np.abs(F))

        # Sample N_AGENTS rows
        idx_  = rng.choice(len(F), size=min(N_AGENTS, len(F)), replace=False)
        agents = F[idx_]    # (N_AGENTS, n_features)

        windows.append(agents.flatten())
        labels_w.append(lbl.mean())
        ent_w.append(flow_entropy(F))

    X  = np.array(windows, dtype=float)   # (T, N_AGENTS * n_features)
    L  = np.array(labels_w)               # (T,)
    E  = np.array(ent_w)                  # (T,)
    return X, L, E


def main() -> None:
    print("=" * 68)
    print("  DOMAIN VI v2 — Cybersecurity: TON-IoT Intrusion Detection")
    print("=" * 68)

    if not os.path.exists(CSV_PATH):
        print(f"  [ERROR] TON-IoT CSV not found: {CSV_PATH}")
        return

    print(f"  Loading {CSV_PATH} ...")
    df, label_col = load_ton_iot(CSV_PATH)
    print(f"  Rows: {len(df)}  Attack fraction: {df['_label_bin'].mean():.3f}")

    feat_cols = select_features(df)
    print(f"  Features ({len(feat_cols)}): {feat_cols}")

    print(f"  Building temporal windows (size={WINDOW_SIZE}, step={STEP_SIZE}) ...")
    X, labels, entropies = build_temporal_windows(df, feat_cols)
    T = len(X)
    print(f"  Windows: T={T}  attack_fraction_mean={labels.mean():.3f}")

    # Reference: first REF_WIN_COUNT windows (normal period)
    ref_mask = np.zeros(T, dtype=bool)
    ref_mask[:min(REF_WIN_COUNT, T//5)] = True

    engine = FrozenCanonicalV4(alpha_base=1.0)
    engine.fit(X[ref_mask])
    result = engine.evaluate(X)

    ps = evaluate_paper_style(engine, X, X[ref_mask])

    # Crisis mask: windows with > 50% attack flows
    crisis_mask = labels > 0.5

    # Confidence gate: per-window flow entropy normalised to [0,1]
    conf_signal = percentile_rank_norm(entropies, window=30)

    v2 = run_v2_gateway(
        v1_alarms     = ps.alarms_paper,
        anomaly_score = result.score,
        conf_signal   = conf_signal,
        crisis_mask   = crisis_mask,
        conf_threshold= 0.47,
        halt_frac     = 0.08,
        resume_frac   = 0.01,
        cb_window     = CB_WINDOW,
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

    fig, axes = plt.subplots(3, 1, figsize=(15, 10), facecolor="white")

    ax = axes[0]
    ax.fill_between(t, 0, labels, color=RUST, alpha=0.6, label="Attack fraction")
    ax.plot(t, labels, color=RUST, lw=1.0)
    ax.axhline(0.5, color=NAVY, ls="--", lw=1, label="Crisis threshold (50%)")
    ax.set_title("TON-IoT: per-window attack fraction", fontsize=10, fontweight="bold")
    ax.set_ylabel("Attack fraction"); ax.set_ylim(0, 1.1); ax.legend(fontsize=8)

    ax = axes[1]
    ax.plot(t, result.score, color=TEAL, lw=1.4, label="Canonical V4 score")
    ax.scatter(t[al1], result.score[al1], color=GOLD, s=20, zorder=5, label=f"v1 alarms ({al1.sum()})")
    ax.scatter(t[al2], result.score[al2], color=NAVY, s=20, marker="^", zorder=6, label=f"v2 alarms ({al2.sum()})")
    ax.fill_between(t, 0, result.score.max()*1.1, where=cr, color=RUST, alpha=0.10)
    ax.set_title("Canonical V4 score + v2 gated alarms", fontsize=10, fontweight="bold")
    ax.set_ylabel("Anomaly score"); ax.legend(fontsize=8)

    ax = axes[2]
    ax.plot(t, conf_signal, color=GOLD, lw=1.2, label="Flow entropy (pct rank)")
    ax.axhline(0.47, color=NAVY, ls="--", lw=1.0, label="Gate threshold (0.47)")
    cb_on = np.array(v2["cb_info"].get("cb_halted", [False]*T), dtype=float)
    ax.fill_between(t, 0, 1, where=cb_on.astype(bool), color=RUST, alpha=0.25, label="CB halted")
    ax.fill_between(t, 0, 1, where=cr, color=TEAL, alpha=0.12, label="Crisis (attack)")
    ax.set_title("Confidence gate signal & circuit breaker", fontsize=10, fontweight="bold")
    ax.set_xlabel("Window index"); ax.set_ylim(-0.05, 1.15); ax.legend(fontsize=8)

    fig.suptitle("Domain VI v2 — Cybersecurity: TON-IoT 2020\n"
                 "FrozenCanonicalV4 + tbr0p47 ConfidenceGate + CB halt/resume",
                 fontsize=11, fontweight="bold")
    fig.tight_layout(rect=[0,0,1,0.96])
    fig.savefig(OUT_PNG, dpi=130, bbox_inches="tight")
    plt.close(fig)
    print(f"\n  Figure → {OUT_PNG}")

    payload = dict(
        domain="cybersecurity",
        version="v2",
        engine="FrozenCanonicalV4",
        gateway="tbr0p47_ConfidenceGate + DomainCircuitBreaker",
        data_source="TON-IoT 2020 network traffic",
        T=T,
        window_size=WINDOW_SIZE,
        step_size=STEP_SIZE,
        n_agents_per_window=N_AGENTS,
        features=feat_cols,
        crisis_windows=int(crisis_mask.sum()),
        v1_alarms=int(al1.sum()),
        v2_alarms=int(al2.sum()),
        lead_time_v1=lead_v1,
        lead_time_v2=lead_v2,
        conf_veto_pct=v2["conf_info"]["veto_pct"],
        cb_suppress_pct=v2["cb_info"]["suppress_pct"],
        improvement=imp,
        channel_dominance=channel_dominance_weighted(ps, crisis_mask if crisis_mask.any() else np.ones(T, bool)),
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
