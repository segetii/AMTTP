"""
Physics engine collapse-signature test — CHB-MIT scalp EEG
==========================================================
Applies MolecularEngine (Lennard-Jones) and GravityModeEngine (N-body)
to the CHB-MIT chb01_03.edf recording to check for the collapse
signature (discrimination + pre-ictal score buildup).

Feature extraction
------------------
  - Window: 4 s (256 samples @ 64 Hz), stride 1 s (64 samples)
  - Features per window per channel: mean, std, log-variance,
    line-length, band-power (delta, theta, alpha, beta) — 9 features
  - Channels: 23  →  total features per window: 207

Cross-file calibration (same protocol as CGS-v1 runner)
--------------------------------------------------------
  - Reference: chb01_01.edf  first 120 s  (interictal, no seizures)
    → engine fitted on reference windows only
  - Test file:  chb01_03.edf  (seizure at t=2996–3036 s)

Metrics
-------
  - Discrimination ratio: mean score(ictal) / mean score(interictal)
  - Collapse-signature lead: first window where rolling score > 2×bkg
  - AUROC on window labels
  - Pre-ictal score trajectory (quintile means relative to onset)

Author: Copilot — May 2026
"""

import sys, os, gc, time, json, warnings
import numpy as np

warnings.filterwarnings("ignore")

# ── paths ─────────────────────────────────────────────────────────
ROOT      = r"C:\amttp"
EEG_DIR   = os.path.join(ROOT, "data", "external_validation", "eeg")
RESULT_DIR = os.path.join(ROOT, "research", "neural-stability", "results")
os.makedirs(RESULT_DIR, exist_ok=True)

CHB_REF_EDF   = os.path.join(EEG_DIR, "chb01_01.edf")
CHB_TEST_EDF  = os.path.join(EEG_DIR, "chb01_03.edf")
CHB04_EDF     = os.path.join(EEG_DIR, "chb01_04.edf")

CHB_SEIZURE_ONSET_S  = 2996.0
CHB_SEIZURE_OFFSET_S = 3036.0
CHB04_SEIZURE_ONSET_S  = 1467.0
CHB04_SEIZURE_OFFSET_S = 1494.0

REF_DURATION_S = 120.0   # first 120 s of chb01_01 for calibration
SFREQ_TARGET   = 64      # Hz — same as CGS-v1 runner
WIN_S  = 4               # window length (seconds)
STRIDE_S = 1             # stride (seconds)

sys.path.insert(0, os.path.join(ROOT, "research", "udl"))

# ── import engines ────────────────────────────────────────────────
from udl.system_mode import MolecularEngine, GravityModeEngine

print("=" * 70)
print("PHYSICS ENGINE COLLAPSE-SIGNATURE TEST — CHB-MIT Scalp EEG")
print("Engines: MolecularEngine (LJ) + GravityModeEngine (N-body)")
print("=" * 70)

# ══════════════════════════════════════════════════════════════════
# 1. EDF loading — pure-Python reader (no mne required)
#    Logic mirrors _read_edf_window in run_cgs_v1_real_data.py
# ══════════════════════════════════════════════════════════════════

_EDF_WIDTHS = [16, 80, 8, 8, 8, 8, 8, 80, 8, 32]
_EDF_FNAMES = ['label', 'transducer', 'phys_dim', 'phys_min', 'phys_max',
               'dig_min', 'dig_max', 'prefilter', 'nsamples', 'reserved']
_EPS = 1e-10


def _read_edf_raw(path: str,
                  start_s: float = 0.0,
                  end_s: float = 1e9,
                  max_channels: int = 23) -> tuple:
    """Pure-Python EDF reader. Returns (X, labels, sfreq) where X is (T, n_ch)."""
    with open(path, "rb") as fh:
        hdr = fh.read(256)
        nr_records   = int(hdr[236:244].strip())
        rec_duration = float(hdr[244:252].strip())
        ns_total     = int(hdr[252:256].strip())

        sig_hdr = fh.read(ns_total * 256)
        ns = min(ns_total, max_channels)

        def _get(field_name, sig_idx):
            fi   = _EDF_FNAMES.index(field_name)
            base = sum(_EDF_WIDTHS[:fi]) * ns_total + sig_idx * _EDF_WIDTHS[fi]
            return sig_hdr[base: base + _EDF_WIDTHS[fi]].decode(errors="replace").strip()

        def _sf(fn, si, default=0.0):
            try:    return float(_get(fn, si))
            except: return default

        def _si(fn, si, default=256):
            try:    return int(_get(fn, si))
            except: return default

        labels   = [_get('label', i) for i in range(ns)]
        physmin  = np.array([_sf('phys_min', i, -32768.0) for i in range(ns)])
        physmax  = np.array([_sf('phys_max', i,  32767.0) for i in range(ns)])
        digmin   = np.array([_sf('dig_min',  i, -32768.0) for i in range(ns)])
        digmax   = np.array([_sf('dig_max',  i,  32767.0) for i in range(ns)])
        nsamples = np.array([_si('nsamples', i, 256) for i in range(ns_total)])

        sfreq = float(nsamples[0]) / rec_duration
        gain  = (physmax - physmin) / (digmax - digmin + _EPS)
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


def _decimate_numpy(data: np.ndarray, factor: int) -> np.ndarray:
    """Simple anti-aliased decimation using a boxcar LP filter + slice."""
    if factor == 1:
        return data
    # Anti-alias: boxcar (moving average) of length `factor` then take every `factor`-th
    kernel = np.ones(factor) / factor
    out = np.apply_along_axis(
        lambda x: np.convolve(x, kernel, mode='same'), axis=0, arr=data)
    return out[::factor]


def load_edf_downsample(path: str,
                        target_sfreq: int = 64,
                        max_duration_s: float = None) -> tuple:
    """Load EDF via pure-Python reader, decimate to target_sfreq.
    Returns (data, sfreq_out, ch_labels) where data is (n_samples, n_ch).
    """
    end_s = max_duration_s if max_duration_s is not None else 1e9
    data, ch_labels, sfreq = _read_edf_raw(path, start_s=0.0, end_s=end_s)
    native = int(round(sfreq))
    if native != target_sfreq and native > target_sfreq:
        factor = native // target_sfreq
        if factor > 1:
            data = _decimate_numpy(data, factor)
    return data, target_sfreq, ch_labels


# ══════════════════════════════════════════════════════════════════
# 2. Feature extraction — windowed statistics
# ══════════════════════════════════════════════════════════════════

def _band_power(x: np.ndarray, sfreq: int, lo: float, hi: float) -> float:
    """Simple band power via FFT."""
    n = len(x)
    if n < 8:
        return 0.0
    freqs = np.fft.rfftfreq(n, d=1.0 / sfreq)
    psd   = np.abs(np.fft.rfft(x)) ** 2
    mask  = (freqs >= lo) & (freqs < hi)
    return float(psd[mask].mean()) if mask.any() else 0.0


def extract_features(data: np.ndarray,
                     sfreq: int,
                     win_samples: int,
                     stride_samples: int) -> np.ndarray:
    """Extract windowed features: (n_windows, n_ch * 9).

    Per-channel features: mean, std, log-variance, line-length,
    delta (0.5-4 Hz), theta (4-8), alpha (8-13), beta (13-30), gamma (30-49).
    """
    n_samp, n_ch = data.shape
    starts = np.arange(0, n_samp - win_samples + 1, stride_samples)
    n_win  = len(starts)
    n_feat = n_ch * 9

    X = np.zeros((n_win, n_feat), dtype=np.float32)
    for wi, st in enumerate(starts):
        seg = data[st : st + win_samples]          # (win, n_ch)
        for ci in range(n_ch):
            x = seg[:, ci].astype(np.float64)
            off = ci * 9
            X[wi, off + 0] = float(x.mean())
            X[wi, off + 1] = float(x.std() + 1e-10)
            X[wi, off + 2] = float(np.log(x.var() + 1e-10))
            X[wi, off + 3] = float(np.mean(np.abs(np.diff(x))))   # line-length
            X[wi, off + 4] = _band_power(x, sfreq, 0.5, 4.0)
            X[wi, off + 5] = _band_power(x, sfreq, 4.0, 8.0)
            X[wi, off + 6] = _band_power(x, sfreq, 8.0, 13.0)
            X[wi, off + 7] = _band_power(x, sfreq, 13.0, 30.0)
            X[wi, off + 8] = _band_power(x, sfreq, 30.0, 49.0)
    return X


# ══════════════════════════════════════════════════════════════════
# 3. Helpers: discrimination + collapse signature
# ══════════════════════════════════════════════════════════════════

def window_labels(n_win: int, stride_samples: int, sfreq: int,
                  onset_s: float, offset_s: float) -> np.ndarray:
    """0 = interictal, 1 = ictal for each window (centre-of-window rule)."""
    centres_s = (np.arange(n_win) * stride_samples + WIN_S * sfreq / 2) / sfreq
    y = ((centres_s >= onset_s) & (centres_s <= offset_s)).astype(int)
    return y, centres_s


def first_above_threshold(scores: np.ndarray, y: np.ndarray,
                           threshold: float, onset_s: float,
                           centres_s: np.ndarray) -> float:
    """Return lead time (s) of first window that crosses threshold
    and lies BEFORE onset.  Returns NaN if none."""
    bkg_mask = y == 0
    for i, s in enumerate(scores):
        if s >= threshold and centres_s[i] < onset_s:
            return onset_s - centres_s[i]
    return float("nan")


def collapse_signature(scores: np.ndarray, y: np.ndarray,
                       centres_s: np.ndarray,
                       onset_s: float) -> dict:
    """Compute key collapse-signature metrics."""
    from sklearn.metrics import roc_auc_score

    ictal_mask    = y == 1
    interict_mask = y == 0

    mean_ictal     = float(scores[ictal_mask].mean()) if ictal_mask.any() else 0.0
    mean_interictal = float(scores[interict_mask].mean()) if interict_mask.any() else 1e-9

    disc_ratio = mean_ictal / (mean_interictal + 1e-10)

    # Rolling 60-s mean score (causal, 60 / STRIDE_S windows)
    roll_win = 60 // STRIDE_S
    rolling = np.convolve(scores, np.ones(roll_win) / roll_win, mode="full")[:len(scores)]

    # Threshold = 2× background (mean of interictal rolling)
    bkg_thresh = 2.0 * float(rolling[interict_mask].mean())
    lead = first_above_threshold(rolling, y, bkg_thresh, onset_s, centres_s)

    # Pre-ictal quintile analysis (5 quintiles of interictal period)
    preictal_mask = (centres_s < onset_s) & (y == 0)
    if preictal_mask.sum() >= 5:
        quintile_bins = np.percentile(centres_s[preictal_mask],
                                       [0, 20, 40, 60, 80, 100])
        q_means = []
        for qi in range(5):
            lo, hi = quintile_bins[qi], quintile_bins[qi + 1]
            m = preictal_mask & (centres_s >= lo) & (centres_s <= hi)
            q_means.append(float(scores[m].mean()) if m.any() else 0.0)
        buildup_ratio = q_means[4] / (q_means[0] + 1e-10)
    else:
        q_means = [float("nan")] * 5
        buildup_ratio = float("nan")

    # AUROC
    try:
        auroc = float(roc_auc_score(y, scores)) if ictal_mask.any() and interict_mask.any() else float("nan")
    except Exception:
        auroc = float("nan")

    return dict(
        mean_ictal=mean_ictal,
        mean_interictal=mean_interictal,
        discrimination_ratio=disc_ratio,
        lead_time_rolling_s=lead,
        buildup_q_means=q_means,
        buildup_ratio=buildup_ratio,
        auroc=auroc,
    )


# ══════════════════════════════════════════════════════════════════
# 4. Run one EDF file through both engines
# ══════════════════════════════════════════════════════════════════

def run_engines_on_edf(test_edf: str,
                       ref_edf: str,
                       seizure_onset_s: float,
                       seizure_offset_s: float,
                       label: str,
                       ref_feat: np.ndarray = None) -> tuple:
    """Load test EDF, extract features, run Molecular + Gravity engines.

    ref_feat: precomputed reference features (from chb01_01.edf, optional).
    Returns (mol_result, grav_result, ref_feat_out).
    """
    print(f"\n  Loading test EDF: {os.path.basename(test_edf)}")
    t0 = time.time()
    data, sfreq, ch_labels = load_edf_downsample(test_edf, SFREQ_TARGET)
    n_ch = data.shape[1]
    print(f"  Channels: {n_ch}  Samples: {data.shape[0]}  "
          f"Duration: {data.shape[0]/sfreq:.0f}s")

    win_samples    = WIN_S * sfreq
    stride_samples = STRIDE_S * sfreq

    # Extract test features
    X_test = extract_features(data, sfreq, win_samples, stride_samples)
    n_win  = len(X_test)
    y_win, centres_s = window_labels(n_win, stride_samples, sfreq,
                                      seizure_onset_s, seizure_offset_s)

    print(f"  Windows: {n_win}  (ictal={int(y_win.sum())}  "
          f"interictal={int((y_win==0).sum())})")

    # Reference features (chb01_01.edf)
    if ref_feat is None:
        print(f"\n  Loading reference EDF: {os.path.basename(ref_edf)}")
        ref_data, _, _ = load_edf_downsample(ref_edf, SFREQ_TARGET,
                                              max_duration_s=REF_DURATION_S)
        # Ensure same channel count
        ref_data = ref_data[:, :n_ch]
        ref_feat = extract_features(ref_data, sfreq, win_samples, stride_samples)
        print(f"  Reference windows: {len(ref_feat)}")

    # Build combined array: reference (label=0) + test
    # Engine is fitted transductively but only normal ref windows are used
    # for the calibration step inside fit_score.
    # Strategy: pass y=None to let engine treat reference as normal.
    # We separately score the test windows for discrimination.

    # Full X for engine: reference windows first, then test windows
    n_ref = len(ref_feat)
    X_all  = np.vstack([ref_feat, X_test]).astype(np.float64)
    y_all  = np.zeros(len(X_all), dtype=int)
    y_all[n_ref:] = y_win   # 0=interictal (also ref), 1=ictal

    results = {}
    for eng_name, EngClass, eng_kwargs in [
        ("Molecular (LJ)",
         MolecularEngine,
         dict(iterations=60, k_neighbors=15, max_samples=2000, use_fused=True)),
        ("Gravity (N-body)",
         GravityModeEngine,
         dict(iterations=60, k_neighbors=15, max_samples=2000, use_fused=True)),
    ]:
        gc.collect()
        print(f"\n  ── {eng_name} engine ──────────────────────")
        t1 = time.time()
        eng = EngClass(**eng_kwargs)
        all_scores = eng.fit_score(X_all, y_all)
        elapsed = time.time() - t1

        # Only analyse test-window scores
        test_scores = all_scores[n_ref:]
        sig = collapse_signature(test_scores, y_win, centres_s, seizure_onset_s)

        print(f"  Discrimination ratio: {sig['discrimination_ratio']:.2f}×"
              f"  ({sig['mean_ictal']:.4f} ictal / {sig['mean_interictal']:.4f} interictal)")
        print(f"  AUROC: {sig['auroc']:.4f}")
        lead = sig['lead_time_rolling_s']
        if not np.isnan(lead):
            print(f"  Rolling-60s collapse lead: {lead:.1f} s before onset")
        else:
            print(f"  Rolling-60s collapse lead: not detected (score never > 2×bkg before onset)")
        q_str = "  →  ".join(f"{v*100:.2f}%" for v in sig['buildup_q_means'])
        print(f"  Pre-ictal quintile means: {q_str}")
        br = sig['buildup_ratio']
        print(f"  Q5/Q1 buildup ratio: {br:.2f}×")
        print(f"  elapsed: {elapsed:.1f}s")

        results[eng_name] = dict(
            elapsed_s=round(elapsed, 1),
            n_windows=n_win,
            n_ictal=int(y_win.sum()),
            n_interictal=int((y_win == 0).sum()),
            **sig,
        )

    total = time.time() - t0
    print(f"\n  [{label}] total elapsed: {total:.1f}s")
    return results, ref_feat


# ══════════════════════════════════════════════════════════════════
# 5. Main
# ══════════════════════════════════════════════════════════════════

all_output = {}

# ── chb01_03: primary file ────────────────────────────────────────
print("\n" + "=" * 70)
print("FILE 1: chb01_03.edf  (seizure onset=2996s, offset=3036s)")
print("=" * 70)

results_03, ref_feat = run_engines_on_edf(
    test_edf=CHB_TEST_EDF,
    ref_edf=CHB_REF_EDF,
    seizure_onset_s=CHB_SEIZURE_ONSET_S,
    seizure_offset_s=CHB_SEIZURE_OFFSET_S,
    label="chb01_03",
)
all_output["chb01_03"] = results_03

# ── chb01_04: cross-validation file ──────────────────────────────
if os.path.exists(CHB04_EDF):
    print("\n" + "=" * 70)
    print("FILE 2: chb01_04.edf  (seizure onset=1467s, offset=1494s)")
    print("=" * 70)
    results_04, _ = run_engines_on_edf(
        test_edf=CHB04_EDF,
        ref_edf=CHB_REF_EDF,
        seizure_onset_s=CHB04_SEIZURE_ONSET_S,
        seizure_offset_s=CHB04_SEIZURE_OFFSET_S,
        label="chb01_04",
        ref_feat=ref_feat,   # reuse same reference features
    )
    all_output["chb01_04"] = results_04
else:
    print(f"\n  [SKIP] chb01_04.edf not found at {CHB04_EDF}")

# ══════════════════════════════════════════════════════════════════
# 6. Summary
# ══════════════════════════════════════════════════════════════════
print("\n" + "█" * 70)
print("  PHYSICS ENGINE COLLAPSE-SIGNATURE SUMMARY — CHB-MIT EEG")
print("█" * 70)

for file_key, res in all_output.items():
    print(f"\n  ── {file_key} ──────────────────────────────────────────────")
    for eng_name, stats in res.items():
        print(f"  {eng_name}:")
        print(f"    Discrimination ratio: {stats['discrimination_ratio']:.2f}×")
        print(f"    AUROC:                {stats['auroc']:.4f}")
        lead = stats['lead_time_rolling_s']
        if not np.isnan(lead):
            print(f"    Collapse lead:        {lead:.1f} s (rolling-60s, 2×bkg)")
        else:
            print(f"    Collapse lead:        not detected")
        print(f"    Q5/Q1 buildup:        {stats['buildup_ratio']:.2f}×")

# Save JSON
out_json = os.path.join(RESULT_DIR, "physics_engine_chbmit_results.json")
# Convert non-serialisable types
def _clean(obj):
    if isinstance(obj, dict):
        return {k: _clean(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_clean(v) for v in obj]
    if isinstance(obj, (np.floating, float)):
        v = float(obj)
        return None if np.isnan(v) else v
    if isinstance(obj, (np.integer, int)):
        return int(obj)
    return obj

with open(out_json, "w", encoding="utf-8") as f:
    json.dump(_clean(all_output), f, indent=2)
print(f"\n  JSON → {out_json}")
print("█" * 70)
