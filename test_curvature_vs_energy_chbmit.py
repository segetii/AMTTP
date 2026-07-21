"""
Curvature vs Energy Information Test — CHB-MIT chb01_03
=======================================================

Tests the hypothesis:  I(Collapse ; λ_max) > I(Collapse ; E)

Each test window is characterised at all five levels of the collapse
geometry hierarchy, then mutual information with the future seizure
label is measured as a function of lead time τ.

Hierarchy
---------
  C0  Support geometry     — BSDTChannels reference distribution
  C1  Interaction landscape — LJ potential Φ(X) per context
  C2  Curvature spectrum   — λ_max(D²Φ_pair) over rolling context
  C3  Topology             — Morse kNN score from reference
  C4  Energy compression   — E_BS = Σδ_i²  (canonical scalar)

Question: how much information is lost at each projection?

Protocol
--------
  - Reference: chb01_01.edf  first 120 s  (interictal calibration)
  - Test:      chb01_03.edf  (seizure onset 2996 s, offset 3036 s)
  - Windows:   4 s, stride 1 s  →  207-dim feature vectors
  - Context:   60-window rolling context for C1/C2 estimation
  - MI method: sklearn KSG estimator (k-NN, continuous)
  - Lead times: τ = 0, 30, 60, 90, 120, 180, 240, 300 s

Outputs
-------
  research/neural-stability/results/
    curvature_vs_energy_signals.png  — 5-panel time-series
    curvature_vs_energy_mi.png       — MI vs lead-time curves
    curvature_vs_energy_hierarchy.png — info-loss bar chart at τ=60s
    curvature_vs_energy_results.json — full numeric results

Author: Copilot — May 2026
"""

import sys, os, gc, time, json, warnings
import numpy as np

warnings.filterwarnings("ignore")

# ── paths ─────────────────────────────────────────────────────────
ROOT       = r"C:\amttp"
EEG_DIR    = os.path.join(ROOT, "data", "external_validation", "eeg")
RESULT_DIR = os.path.join(ROOT, "research", "neural-stability", "results")
PLOT_DIR   = RESULT_DIR
os.makedirs(RESULT_DIR, exist_ok=True)

CHB_REF_EDF  = os.path.join(EEG_DIR, "chb01_01.edf")
CHB_TEST_EDF = os.path.join(EEG_DIR, "chb01_03.edf")

SEIZURE_ONSET_S  = 2996.0
SEIZURE_OFFSET_S = 3036.0
REF_DURATION_S   = 120.0

SFREQ_TARGET  = 64
WIN_S         = 4
STRIDE_S      = 1
CONTEXT_WIN   = 60   # rolling context windows for C1/C2 (60 s)
K_NEIGHBORS   = 12   # kNN for Hessian + BSDT
SIGMA_LJ      = 1.0
EPSILON_LJ    = 1.0
ALPHA_RADIAL  = 0.1

LEAD_TIMES_S  = [0, 30, 60, 90, 120, 180, 240, 300]

sys.path.insert(0, os.path.join(ROOT, "research", "udl"))

# ── imports ───────────────────────────────────────────────────────
from sklearn.preprocessing import StandardScaler
from sklearn.neighbors import NearestNeighbors
from sklearn.feature_selection import mutual_info_regression
from udl.system_mode import BSDTChannels, MorseTopologyAlarm

print("=" * 70)
print("CURVATURE vs ENERGY INFORMATION TEST — CHB-MIT chb01_03")
print("I(Collapse ; λ_max) vs I(Collapse ; E_BS) at multiple lead times")
print("=" * 70)


# ══════════════════════════════════════════════════════════════════
# EDF reader  (identical to test_physics_engine_chbmit.py)
# ══════════════════════════════════════════════════════════════════

_EDF_WIDTHS = [16, 80, 8, 8, 8, 8, 8, 80, 8, 32]
_EDF_FNAMES = ['label', 'transducer', 'phys_dim', 'phys_min', 'phys_max',
               'dig_min', 'dig_max', 'prefilter', 'nsamples', 'reserved']
_EPS = 1e-10


def _read_edf_raw(path, start_s=0.0, end_s=1e9, max_channels=23):
    with open(path, "rb") as fh:
        hdr = fh.read(256)
        nr_records   = int(hdr[236:244].strip())
        rec_duration = float(hdr[244:252].strip())
        ns_total     = int(hdr[252:256].strip())
        sig_hdr = fh.read(ns_total * 256)
        ns = min(ns_total, max_channels)

        def _get(fn, si):
            fi = _EDF_FNAMES.index(fn)
            base = sum(_EDF_WIDTHS[:fi]) * ns_total + si * _EDF_WIDTHS[fi]
            return sig_hdr[base: base + _EDF_WIDTHS[fi]].decode(errors='replace').strip()

        def _sf(fn, si, d=0.0):
            try: return float(_get(fn, si))
            except: return d

        def _si(fn, si, d=256):
            try: return int(_get(fn, si))
            except: return d

        labels   = [_get('label', i) for i in range(ns)]
        physmin  = np.array([_sf('phys_min', i, -32768.) for i in range(ns)])
        physmax  = np.array([_sf('phys_max', i,  32767.) for i in range(ns)])
        digmin   = np.array([_sf('dig_min',  i, -32768.) for i in range(ns)])
        digmax   = np.array([_sf('dig_max',  i,  32767.) for i in range(ns)])
        nsamples = np.array([_si('nsamples', i, 256) for i in range(ns_total)])
        sfreq    = float(nsamples[0]) / rec_duration
        gain     = (physmax - physmin) / (digmax - digmin + _EPS)
        offset_cal = physmin - digmin * gain

        header_bytes     = 256 + ns_total * 256
        bytes_per_record = int(np.sum(nsamples)) * 2
        start_rec = max(0, int(start_s / rec_duration))
        end_rec   = min(nr_records, int(np.ceil(end_s / rec_duration)))
        n_recs    = end_rec - start_rec

        fh.seek(header_bytes + start_rec * bytes_per_record)
        chunks = []
        for _ in range(n_recs):
            rec_ch = []
            for i in range(ns_total):
                n_samp = max(0, int(nsamples[i]))
                raw = np.frombuffer(fh.read(n_samp * 2), dtype=np.int16)
                if i < ns:
                    rec_ch.append(raw.astype(np.float64) * gain[i] + offset_cal[i])
            chunks.append(rec_ch)

    X = np.concatenate([np.stack(chunks[r], axis=-1) for r in range(n_recs)], axis=0)
    s0 = int((start_s - start_rec * rec_duration) * sfreq)
    s1 = s0 + int((end_s - start_s) * sfreq)
    X  = X[s0: min(s1, X.shape[0])]
    return X, labels, float(sfreq)


def _decimate(data, factor):
    if factor == 1:
        return data
    kernel = np.ones(factor) / factor
    out = np.apply_along_axis(lambda x: np.convolve(x, kernel, mode='same'),
                               axis=0, arr=data)
    return out[::factor]


def load_edf(path, target_sfreq=64, max_duration_s=None):
    end_s = max_duration_s or 1e9
    data, labels, sfreq = _read_edf_raw(path, 0.0, end_s)
    native = int(round(sfreq))
    if native > target_sfreq:
        factor = native // target_sfreq
        data = _decimate(data, factor)
    return data, target_sfreq, labels


# ══════════════════════════════════════════════════════════════════
# Feature extraction  (identical to test_physics_engine_chbmit.py)
# ══════════════════════════════════════════════════════════════════

def _band_power(x, sfreq, lo, hi):
    n = len(x)
    if n < 8:
        return 0.0
    freqs = np.fft.rfftfreq(n, d=1.0 / sfreq)
    psd   = np.abs(np.fft.rfft(x)) ** 2
    mask  = (freqs >= lo) & (freqs < hi)
    return float(psd[mask].mean()) if mask.any() else 0.0


def extract_features(data, sfreq, win_samples, stride_samples):
    n_samp, n_ch = data.shape
    starts  = np.arange(0, n_samp - win_samples + 1, stride_samples)
    n_win   = len(starts)
    n_feat  = n_ch * 9
    X = np.zeros((n_win, n_feat), dtype=np.float32)
    for wi, st in enumerate(starts):
        seg = data[st: st + win_samples]
        for ci in range(n_ch):
            x   = seg[:, ci].astype(np.float64)
            off = ci * 9
            X[wi, off + 0] = float(x.mean())
            X[wi, off + 1] = float(x.std() + 1e-10)
            X[wi, off + 2] = float(np.log(x.var() + 1e-10))
            X[wi, off + 3] = float(np.mean(np.abs(np.diff(x))))
            X[wi, off + 4] = _band_power(x, sfreq, 0.5, 4.0)
            X[wi, off + 5] = _band_power(x, sfreq, 4.0, 8.0)
            X[wi, off + 6] = _band_power(x, sfreq, 8.0, 13.0)
            X[wi, off + 7] = _band_power(x, sfreq, 13.0, 30.0)
            X[wi, off + 8] = _band_power(x, sfreq, 30.0, 49.0)
    return X


# ══════════════════════════════════════════════════════════════════
# C1 / C2  — LJ energy + Hessian λ_max on a particle cloud
# ══════════════════════════════════════════════════════════════════

def lj_forces_batch(X, k=K_NEIGHBORS, eps=1e-5):
    """Lennard-Jones forces — kNN limited (same as MolecularEngine)."""
    n, d = X.shape
    k_ = min(k, n - 1)
    nn = NearestNeighbors(n_neighbors=k_ + 1, algorithm='auto')
    nn.fit(X.astype(np.float32))
    _, indices = nn.kneighbors(X.astype(np.float32))
    nbr_idx = indices[:, 1:]

    X_nbrs = X[nbr_idx]
    diff   = X[:, None, :] - X_nbrs
    r_sq   = np.sum(diff ** 2, axis=2, keepdims=True) + eps
    r      = np.sqrt(r_sq)
    sr6    = (SIGMA_LJ / r) ** 6
    sr12   = sr6 ** 2
    F_mag  = 24 * EPSILON_LJ / r * (2 * sr12 - sr6)
    forces = np.sum(F_mag * (diff / r), axis=1)
    return forces


def lj_energy_batch(X, mu, k=K_NEIGHBORS, eps=1e-5):
    """Total LJ + radial energy — kNN limited."""
    n  = len(X)
    E_radial = 0.5 * ALPHA_RADIAL * np.sum((X - mu) ** 2)
    E_lj = 0.0
    if n > 1:
        k_ = min(k, n - 1)
        nn = NearestNeighbors(n_neighbors=k_ + 1, algorithm='auto')
        nn.fit(X.astype(np.float32))
        dists, _ = nn.kneighbors(X.astype(np.float32))
        r   = dists[:, 1:] + eps
        sr6 = (SIGMA_LJ / r) ** 6
        sr12 = sr6 ** 2
        E_lj = float(0.5 * 4 * EPSILON_LJ * np.sum(sr12 - sr6))
    return E_radial + E_lj


def hessian_lambda_max(X, n_power_iters=4, fd_eps=1e-4,
                       max_pts=150, k=K_NEIGHBORS):
    """
    λ_max(D²Φ_pair)  via matrix-free power iteration.

    Identical logic to MolecularEngine._pairwise_hessian_lambda_max().
    This is the C2 signal: curvature of the interaction landscape.
    """
    n, d = X.shape
    if n > max_pts:
        rng = np.random.RandomState(7)
        idx = rng.choice(n, max_pts, replace=False)
        Xs  = X[idx]
    else:
        Xs = X
    ns = len(Xs)

    rng = np.random.RandomState(42)
    v   = rng.randn(ns, d).astype(np.float64)
    v  /= (np.linalg.norm(v) + 1e-15)

    lambda_est = 1.0
    for _ in range(n_power_iters):
        F_plus  = lj_forces_batch(Xs + fd_eps * v, k=min(k, ns - 1))
        F_minus = lj_forces_batch(Xs - fd_eps * v, k=min(k, ns - 1))
        Hv      = -(F_plus - F_minus) / (2.0 * fd_eps)

        denom      = float(np.sum(v * v)) + 1e-15
        lambda_est = float(np.sum(v * Hv)) / denom

        norm_Hv = np.linalg.norm(Hv)
        if norm_Hv < 1e-15:
            break
        v = Hv / norm_Hv

    return max(abs(lambda_est), 1e-10)


# ══════════════════════════════════════════════════════════════════
# Mutual information utility  (KSG via sklearn)
# ══════════════════════════════════════════════════════════════════

def mi_signal_label(signal, labels, n_neighbors=5):
    """MI between a continuous 1-D signal and a binary label array.
    Uses sklearn KSG estimator (n_neighbors controls bias/variance).
    Returns MI in nats.
    """
    s = np.asarray(signal, dtype=np.float64).reshape(-1, 1)
    y = np.asarray(labels, dtype=np.float64)
    if s.shape[0] != y.shape[0] or len(np.unique(y)) < 2:
        return 0.0
    # mutual_info_regression returns MI in nats
    mi = mutual_info_regression(s, y, n_neighbors=n_neighbors,
                                 random_state=42)
    return float(mi[0])


def mi_at_lead(signal, y_full, centres_s, lead_tau_s,
               onset_s=SEIZURE_ONSET_S, offset_s=SEIZURE_OFFSET_S):
    """MI( signal(t) , label(t + lead_tau_s) ).

    For each time index i, ask: does signal(i) predict whether
    the brain will be in seizure τ seconds later?

    label(t) = 1 if t ∈ [onset, offset].
    We shift the label backward by τ so signal(i) is matched with
    the label τ seconds in the future.
    """
    n = len(signal)
    # future label: y_future[i] = 1 if centres_s[i] + tau is ictal
    future_t = centres_s + lead_tau_s
    y_future  = ((future_t >= onset_s) & (future_t <= offset_s)).astype(int)

    # Keep only windows where both signal and future label are valid
    valid = np.ones(n, dtype=bool)
    # Discard windows whose future falls after the recording
    max_t = centres_s[-1]
    valid &= (centres_s + lead_tau_s <= max_t + 5.0)

    if valid.sum() < 20 or y_future[valid].sum() < 1:
        return 0.0

    return mi_signal_label(signal[valid], y_future[valid])


# ══════════════════════════════════════════════════════════════════
# Main pipeline
# ══════════════════════════════════════════════════════════════════

def main():
    t_start = time.time()
    win_samples    = WIN_S * SFREQ_TARGET
    stride_samples = STRIDE_S * SFREQ_TARGET

    # ── 1. Load reference (chb01_01, first 120 s) ─────────────────
    print(f"\n[1/5] Loading reference: chb01_01.edf (first {REF_DURATION_S:.0f} s)")
    ref_data, _, _ = load_edf(CHB_REF_EDF, SFREQ_TARGET, REF_DURATION_S)
    n_ch = ref_data.shape[1]
    X_ref = extract_features(ref_data, SFREQ_TARGET, win_samples, stride_samples)
    X_ref = X_ref.astype(np.float64)
    print(f"  Reference windows: {len(X_ref)}  Features: {X_ref.shape[1]}")

    # ── 2. Load test (chb01_03, full recording) ────────────────────
    print(f"\n[2/5] Loading test: chb01_03.edf")
    test_data, _, _ = load_edf(CHB_TEST_EDF, SFREQ_TARGET)
    test_data = test_data[:, :n_ch]
    X_test = extract_features(test_data, SFREQ_TARGET, win_samples, stride_samples)
    X_test = X_test.astype(np.float64)
    n_win  = len(X_test)

    # Window centre times
    centres_s = (np.arange(n_win) * stride_samples + win_samples / 2) / SFREQ_TARGET
    y_win = ((centres_s >= SEIZURE_ONSET_S) &
             (centres_s <= SEIZURE_OFFSET_S)).astype(int)
    print(f"  Test windows: {n_win}  Duration: {centres_s[-1]:.0f} s")
    print(f"  Ictal: {int(y_win.sum())}  Interictal: {int((y_win==0).sum())}")

    # ── 3. Calibrate C3/C4 scorers on reference ───────────────────
    print(f"\n[3/5] Calibrating C3 (Morse) + C4 (BSDT) on reference")
    scaler = StandardScaler()
    X_ref_norm  = scaler.fit_transform(X_ref)
    X_test_norm = scaler.transform(X_test)

    # C3: MorseTopologyAlarm
    morse = MorseTopologyAlarm(k=K_NEIGHBORS)
    morse.fit(X_ref_norm)

    # C4: BSDTChannels
    bsdt = BSDTChannels(k=K_NEIGHBORS)
    bsdt.fit(X_ref_norm)

    print("  Scorers fitted.")

    # ── 4. Rolling C1/C2 time series ──────────────────────────────
    print(f"\n[4/5] Computing rolling signals (context={CONTEXT_WIN} windows)")
    print(f"  Signals: λ_max (C2), E_lj (C1), E_BS (C4), Morse (C3)")

    n_valid  = n_win - CONTEXT_WIN + 1  # windows with full context
    t_idx    = np.arange(CONTEXT_WIN - 1, n_win)  # last index of each context

    lam_max_ts  = np.zeros(n_valid)   # C2: Hessian curvature
    e_lj_ts     = np.zeros(n_valid)   # C1: LJ landscape energy (mean)
    e_bs_ts     = np.zeros(n_valid)   # C4: BSDT blind-spot energy (mean)
    morse_ts    = np.zeros(n_valid)   # C3: Morse topology score (mean)

    report_every = max(1, n_valid // 20)

    for i in range(n_valid):
        ctx_start = i
        ctx_end   = i + CONTEXT_WIN
        ctx       = X_test_norm[ctx_start: ctx_end]   # (60, 207)

        # C1: LJ energy (mean per particle)
        mu_ctx  = ctx.mean(axis=0)
        e_lj_ts[i] = lj_energy_batch(ctx, mu_ctx) / CONTEXT_WIN

        # C2: Hessian λ_max of pairwise LJ potential
        lam_max_ts[i] = hessian_lambda_max(ctx)

        # C3: mean Morse score over context
        morse_ts[i] = float(morse.score(ctx).mean())

        # C4: mean BSDT energy over context
        e_bs_ts[i] = float(bsdt.energy(ctx).mean())

        if (i + 1) % report_every == 0 or i == n_valid - 1:
            pct = 100 * (i + 1) / n_valid
            print(f"  {pct:5.1f}%  t={centres_s[t_idx[i]]:.0f}s  "
                  f"λ_max={lam_max_ts[i]:.3f}  "
                  f"E_lj={e_lj_ts[i]:.3f}  "
                  f"E_BS={e_bs_ts[i]:.3f}  "
                  f"Morse={morse_ts[i]:.3f}")

    # Align centres to the LAST window of each context
    centres_ctx = centres_s[t_idx]
    y_ctx       = y_win[t_idx]

    # Smooth all signals with a 30-s causal rolling mean to reduce noise
    def causal_smooth(x, w=30):
        out = np.zeros_like(x)
        for i in range(len(x)):
            lo = max(0, i - w + 1)
            out[i] = x[lo: i + 1].mean()
        return out

    lam_s  = causal_smooth(lam_max_ts)
    e_lj_s = causal_smooth(e_lj_ts)
    e_bs_s = causal_smooth(e_bs_ts)
    mor_s  = causal_smooth(morse_ts)

    # ── 5. Mutual information at each lead time ───────────────────
    print(f"\n[5/5] Computing MI at lead times: {LEAD_TIMES_S} s")

    signals = {
        'C2_lambda_max':  lam_s,
        'C1_E_lj':        e_lj_s,
        'C4_E_BS':        e_bs_s,
        'C3_Morse':       mor_s,
    }
    mi_table = {name: [] for name in signals}

    for tau in LEAD_TIMES_S:
        for name, sig in signals.items():
            mi = mi_at_lead(sig, y_ctx, centres_ctx, tau)
            mi_table[name].append(mi)
        vals = {n: f"{mi_table[n][-1]:.4f}" for n in signals}
        print(f"  τ={tau:4d}s  " + "  ".join(f"{k}={v}" for k, v in vals.items()))

    # ── Summary: information loss chain ───────────────────────────
    tau_60_idx = LEAD_TIMES_S.index(60) if 60 in LEAD_TIMES_S else 0
    print("\n── Information at τ=60 s (C0→C4 chain) ──")
    chain_order = ['C2_lambda_max', 'C1_E_lj', 'C3_Morse', 'C4_E_BS']
    for name in chain_order:
        mi_val = mi_table[name][tau_60_idx]
        print(f"  {name:20s}  MI={mi_val:.4f} nats")

    lam_mi_60  = mi_table['C2_lambda_max'][tau_60_idx]
    e_bs_mi_60 = mi_table['C4_E_BS'][tau_60_idx]
    compression_loss = lam_mi_60 - e_bs_mi_60
    print(f"\n  Compression loss C2→C4 at τ=60s: {compression_loss:+.4f} nats")
    if compression_loss > 0.01:
        print("  → λ_max carries MORE collapse information than E_BS.")
        print("    The C2→C4 compression is LOSSY in the seizure-predictive regime.")
    elif compression_loss < -0.01:
        print("  → E_BS carries MORE collapse information than λ_max.")
        print("    The canonical compression PRESERVES and even enhances information.")
    else:
        print("  → λ_max ≈ E_BS. The compression is information-preserving.")

    elapsed = time.time() - t_start

    # ── Save JSON results ──────────────────────────────────────────
    results = {
        "dataset":           "CHB-MIT chb01_03",
        "seizure_onset_s":   SEIZURE_ONSET_S,
        "n_windows":         int(n_win),
        "context_windows":   CONTEXT_WIN,
        "lead_times_s":      LEAD_TIMES_S,
        "mi_table":          mi_table,
        "compression_loss_tau60_nats": float(compression_loss),
        "elapsed_s":         round(elapsed, 1),
        "hierarchy": {
            "C1_E_lj_description":    "LJ interaction landscape energy (mean per context)",
            "C2_lambda_max_description": "Curvature λ_max of D²Φ_pair (power iteration)",
            "C3_Morse_description":   "Morse kNN topology score (mean per context)",
            "C4_E_BS_description":    "BSDT blind-spot energy Σδ_i² (canonical compression)",
        }
    }
    out_json = os.path.join(RESULT_DIR, "curvature_vs_energy_results.json")
    with open(out_json, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\n  Results → {out_json}")

    # ── Plots ──────────────────────────────────────────────────────
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.gridspec as gridspec

        # ── Plot 1: Time series (5 panels) ──────────────────────
        fig = plt.figure(figsize=(16, 14))
        gs  = gridspec.GridSpec(5, 1, hspace=0.45)

        signal_defs = [
            ('C2  λ_max(D²Φ_pair)',  lam_s,  '#E74C3C', 'Curvature'),
            ('C1  E_lj  (mean)',      e_lj_s, '#E67E22', 'LJ Energy'),
            ('C3  Morse score',       mor_s,  '#9B59B6', 'Topology'),
            ('C4  E_BS  (mean)',      e_bs_s, '#2ECC71', 'BSDT Energy'),
        ]

        axes = [fig.add_subplot(gs[i]) for i in range(5)]

        for ax_i, (title, sig, col, _) in enumerate(signal_defs):
            ax = axes[ax_i]
            ax.plot(centres_ctx / 60, sig, color=col, lw=1.0, alpha=0.85,
                    label=title)
            ax.axvline(SEIZURE_ONSET_S / 60, color='red', lw=1.5,
                       ls='--', label='Seizure onset' if ax_i == 0 else '_')
            ax.axvspan(SEIZURE_ONSET_S / 60, SEIZURE_OFFSET_S / 60,
                       alpha=0.12, color='red', label='Ictal' if ax_i == 0 else '_')
            ax.set_ylabel(title, fontsize=8)
            ax.set_xlim(centres_ctx[0] / 60, centres_ctx[-1] / 60)
            ax.tick_params(labelsize=7)
            ax.grid(True, alpha=0.25)
            if ax_i == 0:
                ax.legend(fontsize=7, loc='upper left')

        # Bottom panel: all normalised together for comparison
        ax = axes[4]
        colours = ['#E74C3C', '#E67E22', '#9B59B6', '#2ECC71']
        for (title, sig, col, short), c in zip(signal_defs, colours):
            mn, mx = sig.min(), sig.max()
            norm = (sig - mn) / (mx - mn + 1e-15)
            ax.plot(centres_ctx / 60, norm, color=c, lw=1.0, alpha=0.75,
                    label=short)
        ax.axvline(SEIZURE_ONSET_S / 60, color='red', lw=1.5, ls='--')
        ax.axvspan(SEIZURE_ONSET_S / 60, SEIZURE_OFFSET_S / 60,
                   alpha=0.12, color='red')
        ax.set_ylabel('Normalised [0,1]', fontsize=8)
        ax.set_xlabel('Time (minutes)', fontsize=9)
        ax.legend(fontsize=7, ncol=4, loc='upper left')
        ax.tick_params(labelsize=7)
        ax.grid(True, alpha=0.25)

        fig.suptitle(
            'Collapse Geometry Hierarchy — CHB-MIT chb01_03\n'
            'C1: LJ Landscape → C2: Curvature λ_max → C3: Topology → C4: Energy E_BS',
            fontsize=11, fontweight='bold')

        out_ts = os.path.join(PLOT_DIR, "curvature_vs_energy_signals.png")
        fig.savefig(out_ts, dpi=150, bbox_inches='tight')
        plt.close(fig)
        print(f"  Plot → {out_ts}")

        # ── Plot 2: MI vs lead time ──────────────────────────────
        fig, ax = plt.subplots(figsize=(10, 6))
        mi_defs = [
            ('C2  λ_max', 'C2_lambda_max', '#E74C3C', 'o-'),
            ('C1  E_lj',  'C1_E_lj',       '#E67E22', 's-'),
            ('C3  Morse', 'C3_Morse',       '#9B59B6', '^-'),
            ('C4  E_BS',  'C4_E_BS',        '#2ECC71', 'D-'),
        ]
        for label, key, col, mk in mi_defs:
            ax.plot(LEAD_TIMES_S, mi_table[key], mk, color=col,
                    lw=2.0, ms=7, label=label)

        # Shade the C2 > C4 region
        lam_arr = np.array(mi_table['C2_lambda_max'])
        e_arr   = np.array(mi_table['C4_E_BS'])
        diff    = lam_arr - e_arr
        if diff.max() > 0:
            ax.fill_between(LEAD_TIMES_S,
                            np.minimum(lam_arr, e_arr),
                            np.maximum(lam_arr, e_arr),
                            where=diff > 0,
                            alpha=0.15, color='#E74C3C',
                            label='λ_max > E_BS (curvature advantage)')
        if (-diff).max() > 0:
            ax.fill_between(LEAD_TIMES_S,
                            np.minimum(lam_arr, e_arr),
                            np.maximum(lam_arr, e_arr),
                            where=diff < 0,
                            alpha=0.15, color='#2ECC71',
                            label='E_BS > λ_max (energy advantage)')

        ax.set_xlabel('Lead time τ (seconds)', fontsize=11)
        ax.set_ylabel('Mutual Information (nats)', fontsize=11)
        ax.set_title(
            'I(Collapse ; Signal) vs Lead Time τ\n'
            'CHB-MIT chb01_03 — Seizure onset 2996 s',
            fontsize=12, fontweight='bold')
        ax.legend(fontsize=9)
        ax.grid(True, alpha=0.3)
        ax.set_xlim(min(LEAD_TIMES_S), max(LEAD_TIMES_S))

        out_mi = os.path.join(PLOT_DIR, "curvature_vs_energy_mi.png")
        fig.savefig(out_mi, dpi=150, bbox_inches='tight')
        plt.close(fig)
        print(f"  Plot → {out_mi}")

        # ── Plot 3: Information loss hierarchy bar chart ─────────
        fig, axes = plt.subplots(1, 2, figsize=(13, 5))

        # Left: MI at τ=60s for each layer
        chain_names = ['C1\nE_lj', 'C2\nλ_max', 'C3\nMorse', 'C4\nE_BS']
        chain_keys  = ['C1_E_lj', 'C2_lambda_max', 'C3_Morse', 'C4_E_BS']
        chain_cols  = ['#E67E22', '#E74C3C', '#9B59B6', '#2ECC71']
        mi_vals_60  = [mi_table[k][tau_60_idx] for k in chain_keys]

        bars = axes[0].bar(chain_names, mi_vals_60, color=chain_cols,
                           edgecolor='white', linewidth=1.2)
        for bar, v in zip(bars, mi_vals_60):
            axes[0].text(bar.get_x() + bar.get_width() / 2,
                         bar.get_height() + 0.0005,
                         f'{v:.4f}', ha='center', va='bottom', fontsize=9)
        axes[0].set_ylabel('MI at τ=60 s (nats)', fontsize=10)
        axes[0].set_title('Information per Hierarchy Layer\n(τ = 60 s lead)', fontsize=11)
        axes[0].grid(True, axis='y', alpha=0.3)

        # Add arrow chain C1→C2→C3→C4 with loss annotations
        mi_prev = mi_vals_60[0]
        for j in range(1, len(mi_vals_60)):
            loss = mi_prev - mi_vals_60[j]
            col  = '#E74C3C' if loss > 0.001 else '#2ECC71'
            x_mid = j - 0.5
            axes[0].annotate(
                f'Δ={loss:+.4f}',
                xy=(j, mi_vals_60[j] + max(mi_vals_60) * 0.05),
                xytext=(x_mid, max(mi_vals_60) * 0.85),
                arrowprops=dict(arrowstyle='->', color=col, lw=1.2),
                fontsize=7, color=col, ha='center'
            )
            mi_prev = mi_vals_60[j]

        # Right: MI curves as a compact heatmap (signals × lead times)
        mi_matrix = np.array([mi_table[k] for k in chain_keys])
        im = axes[1].imshow(mi_matrix, aspect='auto', cmap='YlOrRd',
                            interpolation='nearest')
        axes[1].set_xticks(range(len(LEAD_TIMES_S)))
        axes[1].set_xticklabels([f'{t}s' for t in LEAD_TIMES_S], fontsize=8)
        axes[1].set_yticks(range(len(chain_keys)))
        axes[1].set_yticklabels(chain_names, fontsize=9)
        axes[1].set_xlabel('Lead time τ', fontsize=10)
        axes[1].set_title('MI Heatmap (nats)\nSignal × Lead Time', fontsize=11)
        plt.colorbar(im, ax=axes[1], shrink=0.8)
        for r in range(mi_matrix.shape[0]):
            for c in range(mi_matrix.shape[1]):
                axes[1].text(c, r, f'{mi_matrix[r, c]:.3f}',
                             ha='center', va='center', fontsize=6,
                             color='black' if mi_matrix[r, c] < mi_matrix.max() * 0.7
                             else 'white')

        fig.suptitle(
            'Collapse Geometry Hierarchy — Information Loss Chain\n'
            'C1 (Landscape) → C2 (Curvature) → C3 (Topology) → C4 (Energy)',
            fontsize=12, fontweight='bold')
        plt.tight_layout()

        out_hier = os.path.join(PLOT_DIR, "curvature_vs_energy_hierarchy.png")
        fig.savefig(out_hier, dpi=150, bbox_inches='tight')
        plt.close(fig)
        print(f"  Plot → {out_hier}")

    except Exception as plot_err:
        print(f"  [WARNING] Plot error: {plot_err}")

    print(f"\nTotal elapsed: {time.time() - t_start:.1f} s")
    print("Done.")
    return results


if __name__ == "__main__":
    main()
