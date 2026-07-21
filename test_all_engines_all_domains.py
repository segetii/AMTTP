#!/usr/bin/env python3
"""
All Engines × All Domains — Early Warning Benchmark
====================================================
Tests all 8 physics simulation engines across 5 domains:

  A: G-SIB Global Banking      (GFC 2007-Q3,   unit: quarters)
  B: FDIC US Banks              (GFC 2007-Q3,   unit: quarters)
  C: ERCOT Power Grid           (supply+demand, unit: days)
  D: Protein Folding            (Go-model,      unit: MD frames)
  E: CHB-MIT EEG Seizures       (scalp EEG,     unit: 1-s windows)

Engines tested (8):
  Molecular | Gravity | Mode4 | Mode5 | Mode6 | Mode7 | Hybrid | CanonicalODE

Primary metric : Lead time (periods of advance warning before onset)
Secondary      : Hit rate (bool), FA/100 pre-onset periods, Disc. ratio

No AUC or machine-learning metrics — early warning physics only.
"""
from __future__ import annotations
import sys, os, re, time, json, warnings, gc
import numpy as np

warnings.filterwarnings("ignore")

ROOT = r"c:\amttp"
sys.path.insert(0, os.path.join(ROOT, "research", "udl"))

from udl.system_mode import (
    MolecularEngine, GravityModeEngine,
    Mode4GravityEngine, Mode5GravityEngine,
    Mode6GravityEngine, Mode7GravityEngine,
    HybridGravityEngine, CanonicalODEEngine,
)

# ── paths ─────────────────────────────────────────────────────────────
EEG_DIR   = os.path.join(ROOT, "data", "external_validation", "eeg")
CHBMIT_DIR = os.path.join(EEG_DIR, "chbmit")
GSIB_DIR  = os.path.join(ROOT, "research", "adaptive-friction",
                          "banklevel_enhanced", "gsib_cache_real")
ERCOT_DIR = os.path.join(ROOT, "data", "ercot")
os.makedirs(CHBMIT_DIR, exist_ok=True)

# ── CHB-MIT pipeline constants ─────────────────────────────────────────
SFREQ_TARGET    = 64
WIN_S           = 4
STRIDE_S        = 1
REF_DURATION_S  = 120.0

# ── Engine constants ───────────────────────────────────────────────────
K_NN        = 15
ITERATIONS  = 60

# ══════════════════════════════════════════════════════════════════════
#  ENGINE FACTORY
# ══════════════════════════════════════════════════════════════════════

def make_engines():
    """Return a fresh list of (name, engine) tuples for all 8 engines."""
    return [
        ("Molecular",
         MolecularEngine(k_neighbors=K_NN, iterations=ITERATIONS, use_fused=True)),
        ("Gravity",
         GravityModeEngine(k_neighbors=K_NN, iterations=ITERATIONS, use_fused=True)),
        ("Mode4",
         Mode4GravityEngine(k_neighbors=K_NN, iterations=ITERATIONS, use_fused=True)),
        ("Mode5",
         Mode5GravityEngine(k_neighbors=K_NN, iterations=ITERATIONS, use_fused=True)),
        # Mode6/Mode7 use stacked BSDT posthoc layers — no use_fused parameter
        ("Mode6",
         Mode6GravityEngine(k_neighbors=K_NN, iterations=ITERATIONS, posthoc="quadsurf")),
        ("Mode7",
         Mode7GravityEngine(k_neighbors=K_NN, iterations=ITERATIONS, posthoc="fisher")),
        ("Hybrid",
         HybridGravityEngine()),
        ("CanonicalODE",
         CanonicalODEEngine(k_neighbors=K_NN, iterations=ITERATIONS,
                            curv_beta=2.0, curv_c=1.0, curv_update_every=5)),
    ]


# ══════════════════════════════════════════════════════════════════════
#  EARLY WARNING METRICS
# ══════════════════════════════════════════════════════════════════════

def early_warning_metrics(scores: np.ndarray, onset_idx: int,
                           roll_win: int = 3,
                           thresh_sigma: float = 2.0) -> dict:
    """
    Compute early-warning quality from anomaly scores.

    Threshold is derived ONLY from the pre-onset window (no label leakage).
    Lead = (onset_idx - first_alarm_idx) periods of advance warning.
    FA rate = distinct alarm bursts per 100 pre-onset periods.
    Disc ratio = mean(post-onset scores) / mean(pre-onset scores).

    Returns dict with: lead, hit, fa_rate, disc_ratio, thresh.
    """
    if onset_idx <= 1 or len(scores) < 2:
        return dict(lead=0, hit=False, fa_rate=0.0, disc_ratio=1.0,
                    thresh=float("nan"))

    # Rolling mean (causal — no future leakage)
    kern = np.ones(roll_win) / roll_win
    roll = np.convolve(scores.astype(float), kern, mode="full")[: len(scores)]

    # Threshold from pre-onset window only
    pre_roll = roll[:onset_idx]
    thresh = float(pre_roll.mean() + thresh_sigma * pre_roll.std())

    # First alarm in pre-onset window → lead time
    lead = 0
    hit = False
    for i in range(onset_idx):
        if roll[i] >= thresh:
            lead = onset_idx - i
            hit = True
            break

    # FA rate: distinct alarm bursts per 100 pre-onset periods
    bursts = 0
    in_burst = False
    for v in pre_roll >= thresh:
        if v and not in_burst:
            bursts += 1
            in_burst = True
        elif not v:
            in_burst = False
    fa_rate = 100.0 * bursts / max(onset_idx, 1)

    # Discrimination ratio: mean post-onset / mean pre-onset
    post = scores[onset_idx:]
    disc = float(post.mean() / (scores[:onset_idx].mean() + 1e-10)) \
           if len(post) > 0 else 1.0

    return dict(
        lead=int(lead),
        hit=bool(hit),
        fa_rate=round(fa_rate, 2),
        disc_ratio=round(disc, 3),
        thresh=round(thresh, 6),
    )


# ══════════════════════════════════════════════════════════════════════
#  UTILITIES
# ══════════════════════════════════════════════════════════════════════

def _clean(X: np.ndarray) -> np.ndarray:
    """Replace non-finite values with column means."""
    X = X.copy().astype(float)
    for c in range(X.shape[1]):
        bad = ~np.isfinite(X[:, c])
        if bad.any():
            good = X[~bad, c]
            X[bad, c] = good.mean() if len(good) > 0 else 0.0
    return X


def _qidx(yr: int, q: int) -> int:
    """Quarters since 2005-Q1."""
    return 4 * (yr - 2005) + (q - 1)


# ══════════════════════════════════════════════════════════════════════
#  DOMAIN A: G-SIB GLOBAL BANKING
# ══════════════════════════════════════════════════════════════════════

def _banking_aggregate(X_panel, meta, start_q, end_q):
    """
    Return (X_quarterly, valid_banks) where X_quarterly[t] is the
    cross-bank mean feature vector at quarter t.
    Stacking banks *vertically* destroys temporal order and compresses
    the pre-onset window to just 6 rows — aggregation by quarter is correct.
    """
    valid_slices = []
    N_meta = min(len(meta), X_panel.shape[1])
    for i in range(N_meta):
        Xb = _clean(X_panel[:, i, :])
        if Xb.shape[0] < end_q:
            continue
        sl = Xb[start_q:end_q]
        if (sl == 0).sum() / sl.size > 0.25:
            continue
        if np.linalg.matrix_rank(sl - sl.mean(0), tol=1e-8) < 2:
            continue
        valid_slices.append(sl)
    if not valid_slices:
        return None, 0
    # Mean across banks at each quarter → shape (T, n_feat)
    X_q = np.mean(np.stack(valid_slices, axis=0), axis=0)
    return X_q, len(valid_slices)


def load_gsib_banking():
    """
    G-SIB early warning: quarterly cross-bank mean, 2005-Q1 → 2009-Q4.
    Onset = 2007-Q3 (index 10).  10 pre-onset quarters, 10 post-onset.
    """
    npz  = os.path.join(GSIB_DIR, "gsib_real_panel.npz")
    meta_path = os.path.join(GSIB_DIR, "gsib_real_meta.json")
    if not os.path.exists(npz):
        return None, None, None, {"status": "no_data", "path": npz}

    X_panel = np.load(npz)["X"]
    with open(meta_path) as f:
        meta = json.load(f)

    start_q  = 0                   # 2005-Q1
    end_q    = _qidx(2010, 1)      # 20  (exclusive)
    crisis_q = _qidx(2007, 3)      # 10

    X_all, n_banks = _banking_aggregate(X_panel, meta, start_q, end_q)
    if X_all is None:
        return None, None, None, {"status": "no_valid_banks"}

    T = end_q - start_q
    y_all = np.array([1 if t >= (crisis_q - start_q) else 0 for t in range(T)])
    onset_idx = crisis_q - start_q  # = 10

    return X_all, y_all, onset_idx, {
        "domain": "G-SIB Banking", "unit": "quarters",
        "unit_detail": "2005-Q1 … 2009-Q4 (cross-bank mean per quarter)",
        "n_banks": n_banks, "crisis": "2007-Q3",
        "onset_idx": onset_idx, "total_samples": T,
    }


# ══════════════════════════════════════════════════════════════════════
#  DOMAIN B: FDIC US BANKS
# ══════════════════════════════════════════════════════════════════════

_US_NAMES = {
    "jpmorgan", "bank of america", "citigroup", "wells fargo",
    "goldman sachs", "bank of new york", "morgan stanley",
    "state street", "us bancorp",
}


def load_fdic_us():
    """
    US G-SIB banks only, quarterly cross-bank mean, 2005-Q1 → 2009-Q4.
    Onset = 2007-Q3 (index 10).  Same temporal structure as G-SIB global.
    """
    npz  = os.path.join(GSIB_DIR, "gsib_real_panel.npz")
    meta_path = os.path.join(GSIB_DIR, "gsib_real_meta.json")
    if not os.path.exists(npz):
        return None, None, None, {"status": "no_data"}

    X_panel = np.load(npz)["X"]
    with open(meta_path) as f:
        meta = json.load(f)

    start_q  = 0
    end_q    = _qidx(2010, 1)   # 20
    crisis_q = _qidx(2007, 3)   # 10

    # Build US-bank-only panel
    us_indices = []
    for i, bank in enumerate(meta):
        name = (bank.get("name") or bank.get("ticker") or "").lower()
        if any(us in name for us in _US_NAMES) or i < 8:
            us_indices.append(i)

    if not us_indices:
        us_indices = list(range(min(8, len(meta))))  # fallback

    us_panel = X_panel[:, us_indices, :]
    us_meta  = [meta[i] for i in us_indices]

    X_all, n_us = _banking_aggregate(us_panel, us_meta, start_q, end_q)
    if X_all is None:
        return None, None, None, {"status": "no_valid_us_banks"}

    T = end_q - start_q
    y_all = np.array([1 if t >= (crisis_q - start_q) else 0 for t in range(T)])
    onset_idx = crisis_q - start_q  # = 10

    return X_all, y_all, onset_idx, {
        "domain": "FDIC US Banks", "unit": "quarters",
        "unit_detail": "2005-Q1 … 2009-Q4 (cross-bank mean per quarter)",
        "n_us_banks": n_us, "crisis": "2007-Q3",
        "onset_idx": onset_idx, "total_samples": T,
    }


# ══════════════════════════════════════════════════════════════════════
#  DOMAIN C: ERCOT POWER GRID (combined supply + demand)
# ══════════════════════════════════════════════════════════════════════

def load_ercot_combined():
    """ERCOT supply+demand daily aggregate, d=10. Onset = first event day."""
    npz_dem = os.path.join(ERCOT_DIR, "ercot_demand_hourly.npz")
    npz_sup = os.path.join(ERCOT_DIR, "ercot_supply_hourly.npz")
    if not os.path.exists(npz_dem) or not os.path.exists(npz_sup):
        return None, None, None, {"status": "no_data",
                                   "expected": npz_dem}

    dem = np.load(npz_dem, allow_pickle=True)
    sup = np.load(npz_sup, allow_pickle=True)
    X_hr    = np.column_stack([dem["X"], sup["X"]])
    dates_hr = np.array(dem["dates"])
    y_hr    = dem["y"]
    labels_hr = np.array(dem["labels"])
    event_onsets = json.loads(str(dem["event_onsets"]))

    # Daily aggregate
    day_strs   = np.array([d[:10] for d in dates_hr])
    unique_days = np.unique(day_strs)
    N = len(unique_days)
    X_daily = np.empty((N, X_hr.shape[1]))
    y_daily = np.empty(N, dtype=int)
    lab_daily = np.empty(N, dtype=object)
    for i, day in enumerate(unique_days):
        mask = day_strs == day
        X_daily[i] = X_hr[mask].mean(axis=0)
        y_daily[i] = int(y_hr[mask].max())
        nonnorm = labels_hr[mask][labels_hr[mask] != "normal"]
        lab_daily[i] = nonnorm[0] if len(nonnorm) > 0 else "normal"

    X_daily = _clean(X_daily)
    onset_idx = int(np.argmax(y_daily)) if y_daily.any() else N // 2

    # Identify first event
    first_event_str = "unknown"
    for ev, onset_str in event_onsets.items():
        idx = np.where(unique_days >= onset_str[:10])[0]
        if len(idx) > 0:
            first_event_str = f"{ev} @ {onset_str[:10]}"
            break

    return X_daily, y_daily, onset_idx, {
        "domain": "ERCOT Energy Grid", "unit": "days",
        "total_days": N,
        "n_event_days": int(y_daily.sum()),
        "first_event": first_event_str,
        "onset_idx": onset_idx,
    }


# ══════════════════════════════════════════════════════════════════════
#  DOMAIN D: PROTEIN FOLDING (Go-model β-hairpin)
# ══════════════════════════════════════════════════════════════════════

def load_protein():
    """
    Simulate Go-model β-hairpin at T_low (folded) and T_high (unfolded).
    Onset = first T_high frame — the temperature boundary IS the crisis.
    y=0: T_low (folded, normal).  y=1: T_high (unfolded, crisis).
    Lead = how many T_high frames before we could have called the transition.
    """
    sys.path.insert(0, ROOT)
    try:
        from test_protein_folding import ProteinConfig, run_protein_simulation, estimate_Tm
    except ImportError as e:
        return None, None, None, {"status": f"import_error: {e}"}

    cfg = ProteinConfig()

    print("  [Protein] Estimating Tm ...")
    t0 = time.time()
    Tm = estimate_Tm(cfg)
    print(f"  [Protein] Tm ≈ {Tm:.0f} K  ({time.time()-t0:.1f}s)")

    T_low  = 0.5 * Tm
    T_high = 1.8 * Tm

    print(f"  [Protein] Running T_low = {T_low:.0f} K  (normal/folded)")
    t0 = time.time()
    traj_low = run_protein_simulation(
        T_low, cfg,
        n_equil=2000, n_prod=5000, sample_every=50,
        adaptive=False, seed=42, verbose=False)
    print(f"  [Protein] T_low done: {len(traj_low['X_frames'])} frames  "
          f"({time.time()-t0:.1f}s)")

    X_ref = traj_low["X_frames"]   # (n_ref, 12) — normal/folded

    print(f"  [Protein] Running T_high = {T_high:.0f} K  (crisis/unfolded)")
    t0 = time.time()
    traj_high = run_protein_simulation(
        T_high, cfg,
        n_equil=2000, n_prod=5000, sample_every=50,
        adaptive=False, external_ref=X_ref, seed=42, verbose=False)
    print(f"  [Protein] T_high done: {len(traj_high['X_frames'])} frames  "
          f"({time.time()-t0:.1f}s)")

    X_test = traj_high["X_frames"]   # (n_test, 12) — crisis/unfolded

    # Onset IS the temperature boundary: all T_high frames are y=1
    X_all     = np.vstack([X_ref, X_test])
    y_all     = np.concatenate([np.zeros(len(X_ref), dtype=int),
                                 np.ones(len(X_test),  dtype=int)])
    onset_idx = len(X_ref)   # first T_high frame

    print(f"  [Protein] onset_idx={onset_idx}  "
          f"pre={len(X_ref)} folded frames, post={len(X_test)} unfolded frames")

    return X_all, y_all, onset_idx, {
        "domain": "Protein Folding (Go-model β-hairpin)",
        "unit": "MD frames (×50 Langevin steps)",
        "unit_detail": "y=0: T_low (folded normal), y=1: T_high (unfolded crisis)",
        "n_ref_frames": len(X_ref),
        "n_test_frames": len(X_test),
        "Tm_K": round(float(Tm), 1),
        "T_low_K": round(float(T_low), 1),
        "T_high_K": round(float(T_high), 1),
        "onset_idx": onset_idx,
    }


# ══════════════════════════════════════════════════════════════════════
#  DOMAIN E: CHB-MIT EEG SEIZURES
#  (helpers inlined from chbmit_full_benchmark.py — pure Python EDF)
# ══════════════════════════════════════════════════════════════════════

_EDF_WIDTHS = [16, 80, 8, 8, 8, 8, 8, 80, 8, 32]
_EDF_FNAMES = ["label", "transducer", "phys_dim", "phys_min", "phys_max",
               "dig_min", "dig_max", "prefilter", "nsamples", "reserved"]
_EPS = 1e-10


def _parse_summary(text: str) -> list:
    """Parse CHB-MIT *-summary.txt into list of file records."""
    records, current = [], None
    for line in text.splitlines():
        line = line.strip()
        m = re.match(r"^File Name:\s+(\S+)", line, re.IGNORECASE)
        if m:
            current = {"filename": m.group(1), "n_seizures": 0, "seizures": []}
            records.append(current)
            continue
        if current is None:
            continue
        m = re.match(r"Number of Seizures in File:\s+(\d+)", line, re.IGNORECASE)
        if m:
            current["n_seizures"] = int(m.group(1))
            continue
        m = re.match(r"Seizure(?:\s+\d+)?\s+Start Time:\s+(\d+)", line, re.IGNORECASE)
        if m:
            current["seizures"].append({"start": int(m.group(1)), "end": None})
            continue
        m = re.match(r"Seizure(?:\s+\d+)?\s+End Time:\s+(\d+)", line, re.IGNORECASE)
        if m and current["seizures"]:
            current["seizures"][-1]["end"] = int(m.group(1))
    return records


def _get_summary(patient_id: str):
    """Load and parse CHB-MIT summary for patient, downloading if needed."""
    summary_path = os.path.join(CHBMIT_DIR, patient_id,
                                f"{patient_id}-summary.txt")
    if not os.path.exists(summary_path):
        try:
            import wfdb
            wfdb.dl_files("chbmit", CHBMIT_DIR,
                          [f"{patient_id}/{patient_id}-summary.txt"],
                          overwrite=False)
        except Exception:
            pass
    if not os.path.exists(summary_path):
        return None
    with open(summary_path, errors="replace") as f:
        return _parse_summary(f.read())


def _find_edf(patient_id: str, filename: str):
    """Find local EDF path — flat dir first, then structured subdir."""
    flat = os.path.join(EEG_DIR, filename)
    if os.path.exists(flat):
        return flat
    struct = os.path.join(CHBMIT_DIR, patient_id, filename)
    if os.path.exists(struct):
        return struct
    return None


def _ensure_edf(patient_id: str, filename: str):
    """Return EDF path, downloading via wfdb if not present."""
    path = _find_edf(patient_id, filename)
    if path:
        return path
    dest = os.path.join(CHBMIT_DIR, patient_id, filename)
    try:
        import wfdb
        print(f"    Downloading {patient_id}/{filename} ...")
        wfdb.dl_files("chbmit", CHBMIT_DIR,
                      [f"{patient_id}/{filename}"], overwrite=False)
        if os.path.exists(dest):
            return dest
    except Exception as e:
        print(f"    Download failed: {e}")
    return None


def _read_edf_raw(path: str, start_s: float = 0.0, end_s: float = 1e9,
                  max_channels: int = 32):
    """Pure-Python EDF reader (no mne/pyedflib required)."""
    with open(path, "rb") as fh:
        hdr = fh.read(256)
        nr_records   = int(hdr[236:244].strip())
        rec_duration = float(hdr[244:252].strip())
        ns_total     = int(hdr[252:256].strip())
        sig_hdr = fh.read(ns_total * 256)
        ns = min(ns_total, max_channels)

        def _get(fn, si):
            fi   = _EDF_FNAMES.index(fn)
            base = sum(_EDF_WIDTHS[:fi]) * ns_total + si * _EDF_WIDTHS[fi]
            return sig_hdr[base: base + _EDF_WIDTHS[fi]].decode(errors="replace").strip()

        def _sf(fn, si, d=0.0):
            try:
                return float(_get(fn, si))
            except Exception:
                return d

        def _si(fn, si, d=256):
            try:
                return int(_get(fn, si))
            except Exception:
                return d

        labels   = [_get("label", i) for i in range(ns)]
        physmin  = np.array([_sf("phys_min", i, -32768.) for i in range(ns)])
        physmax  = np.array([_sf("phys_max", i,  32767.) for i in range(ns)])
        digmin   = np.array([_sf("dig_min",  i, -32768.) for i in range(ns)])
        digmax   = np.array([_sf("dig_max",  i,  32767.) for i in range(ns)])
        nsamples = np.array([_si("nsamples", i, 256) for i in range(ns_total)])
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

    X = np.concatenate(
        [np.stack(chunks[r], axis=-1) for r in range(n_recs)], axis=0)
    s0 = int((start_s - start_rec * rec_duration) * sfreq)
    s1 = s0 + int((end_s - start_s) * sfreq)
    X  = X[s0: min(s1, X.shape[0])]
    return X, labels, float(sfreq)


def _decimate(data: np.ndarray, factor: int) -> np.ndarray:
    if factor == 1:
        return data
    kernel = np.ones(factor) / factor
    out = np.apply_along_axis(
        lambda x: np.convolve(x, kernel, mode="same"), axis=0, arr=data)
    return out[::factor]


def _load_edf(path: str, target_sfreq: int = 64,
              max_duration_s=None, max_channels: int = 32):
    end_s = max_duration_s if max_duration_s else 1e9
    data, labels, sfreq = _read_edf_raw(path, 0.0, end_s, max_channels)
    native = int(round(sfreq))
    if native > target_sfreq:
        factor = native // target_sfreq
        data = _decimate(data, factor)
    return data, target_sfreq, labels


def _band_power(x: np.ndarray, sfreq: float, lo: float, hi: float) -> float:
    n = len(x)
    if n < 8:
        return 0.0
    freqs = np.fft.rfftfreq(n, d=1.0 / sfreq)
    psd   = np.abs(np.fft.rfft(x)) ** 2
    mask  = (freqs >= lo) & (freqs < hi)
    return float(psd[mask].mean()) if mask.any() else 0.0


def _extract_features(data: np.ndarray, sfreq: float,
                       win_samples: int, stride_samples: int) -> np.ndarray:
    """9 features × n_channels in sliding windows → (n_win, 9*n_ch)."""
    n_samp, n_ch = data.shape
    starts  = np.arange(0, n_samp - win_samples + 1, stride_samples)
    n_win   = len(starts)
    X = np.zeros((n_win, n_ch * 9), dtype=np.float32)
    for wi, st in enumerate(starts):
        seg = data[st: st + win_samples]
        for ci in range(n_ch):
            x   = seg[:, ci].astype(np.float64)
            off = ci * 9
            X[wi, off + 0] = float(x.mean())
            X[wi, off + 1] = float(x.std() + 1e-10)
            X[wi, off + 2] = float(np.log(x.var() + 1e-10))
            X[wi, off + 3] = float(np.mean(np.abs(np.diff(x))))
            X[wi, off + 4] = _band_power(x, sfreq, 0.5,  4.0)
            X[wi, off + 5] = _band_power(x, sfreq, 4.0,  8.0)
            X[wi, off + 6] = _band_power(x, sfreq, 8.0, 13.0)
            X[wi, off + 7] = _band_power(x, sfreq, 13.0, 30.0)
            X[wi, off + 8] = _band_power(x, sfreq, 30.0, 49.0)
    return X


def load_chbmit(patient_ids=("chb01", "chb02", "chb03", "chb05")):
    """
    Load the first usable CHB-MIT patient.
    Returns X_all (n_win × F), y_all, onset_idx, meta.
    """
    win_samples    = WIN_S    * SFREQ_TARGET
    stride_samples = STRIDE_S * SFREQ_TARGET

    for pid in patient_ids:
        print(f"  [CHB-MIT] Trying {pid} ...")
        records = _get_summary(pid)
        if not records:
            print(f"    No summary for {pid}")
            continue

        ref_rec = next((r for r in records if r["n_seizures"] == 0), None)
        seiz_rec = None
        for r in records:
            if r["n_seizures"] > 0:
                for sz in r["seizures"]:
                    if sz.get("end") is not None and sz["start"] >= 180:
                        seiz_rec = r
                        onset_s  = float(sz["start"])
                        offset_s = float(sz["end"])
                        break
            if seiz_rec:
                break

        if not ref_rec or not seiz_rec:
            print(f"    {pid}: no usable reference+seizure pair")
            continue

        ref_path  = _ensure_edf(pid, ref_rec["filename"])
        seiz_path = _ensure_edf(pid, seiz_rec["filename"])
        if not ref_path or not seiz_path:
            print(f"    {pid}: EDF files not available")
            continue

        try:
            ref_data,  _, _ = _load_edf(ref_path,  SFREQ_TARGET, REF_DURATION_S)
            seiz_data, _, _ = _load_edf(seiz_path, SFREQ_TARGET)
        except Exception as e:
            print(f"    {pid}: load error — {e}")
            continue

        n_ch = min(ref_data.shape[1], seiz_data.shape[1])
        ref_data  = ref_data[:,  :n_ch]
        seiz_data = seiz_data[:, :n_ch]

        try:
            X_ref  = _extract_features(ref_data,  SFREQ_TARGET,
                                        win_samples, stride_samples).astype(np.float64)
            X_seiz = _extract_features(seiz_data, SFREQ_TARGET,
                                        win_samples, stride_samples).astype(np.float64)
        except Exception as e:
            print(f"    {pid}: feature extraction error — {e}")
            continue

        n_ref = len(X_ref)
        n_win = len(X_seiz)
        centres_s = (np.arange(n_win) * stride_samples + win_samples / 2.0) / SFREQ_TARGET
        y_seiz    = ((centres_s >= onset_s) & (centres_s <= offset_s)).astype(int)

        if y_seiz.sum() == 0:
            print(f"    {pid}: no ictal windows found")
            continue

        X_all     = np.vstack([X_ref, X_seiz])
        y_all     = np.concatenate([np.zeros(n_ref, dtype=int), y_seiz])
        first_ictal = int(np.argmax(y_seiz))
        onset_idx   = n_ref + first_ictal

        print(f"    {pid}: ref={n_ref}win  seiz={n_win}win  "
              f"ictal={int(y_seiz.sum())}  onset@{onset_idx}")

        return X_all, y_all, onset_idx, {
            "domain": "CHB-MIT EEG Seizures",
            "unit": f"windows ({STRIDE_S}s stride)",
            "patient": pid,
            "onset_s": onset_s,
            "offset_s": offset_s,
            "n_ref_windows": n_ref,
            "n_seiz_windows": n_win,
            "n_ictal_windows": int(y_seiz.sum()),
            "onset_idx": onset_idx,
        }

    return None, None, None, {
        "status": "no_usable_patient",
        "tried": list(patient_ids),
        "hint": "Run chbmit_full_benchmark.py first to download EDF files",
    }


# ══════════════════════════════════════════════════════════════════════
#  PHYSICS SIGNAL ANALYSIS  (γ*, MFLS, ρ_MFLS, curvature)
#
#  These are the INTERNAL signals the engines use.  Rising γ* means
#  the system is applying more adaptive friction because it senses the
#  approach to collapse — that friction IS the early warning.
#  MFLS = ‖∇E_BS‖_F = how hard the BSDT energy gradient is pulling.
#  ρ_MFLS > 1 = state over-amplifies channel risk = real collapse.
#  Curvature > 0 = saddle point, system on the collapse manifold.
# ══════════════════════════════════════════════════════════════════════

def run_physics_signals(label: str, X_all: np.ndarray, onset_idx: int,
                         meta: dict) -> dict:
    """
    Compute γ*, MFLS, ρ_MFLS, E_BS and Morse curvature for each sample.
    Fit BSDTChannels on pre-onset window only (no label leakage).
    Report lead time for each physics signal independently.
    """
    from udl.system_mode import BSDTChannels

    unit = meta.get("unit", "periods")
    ew   = _DOMAIN_EW_PARAMS.get(label, dict(roll_win=3, thresh_sigma=2.0))
    roll_win     = ew["roll_win"]
    thresh_sigma = ew["thresh_sigma"]

    print(f"\n  ── Physics signals: {label}")

    X_pre  = X_all[:onset_idx]
    X_post = X_all[onset_idx:]

    if len(X_pre) < 4:
        print(f"     SKIP — too few pre-onset samples ({len(X_pre)})")
        return {}

    # Fit BSDT on pre-onset reference
    try:
        bsdt = BSDTChannels(k=min(K_NN, len(X_pre) - 2))
        bsdt.fit(X_pre.astype(np.float64))
    except Exception as e:
        print(f"     BSDT fit failed: {e}")
        return {}

    # Compute signals for every sample
    X_f = X_all.astype(np.float64)
    try:
        E_bs   = bsdt.energy(X_f)           # (N,)
        mfls   = bsdt.mfls_state(X_f)       # ‖∇E_BS‖_F
        rho    = bsdt.rho_mfls(X_f)         # ρ_MFLS = MFLS_state / MFLS_channel
        ch     = bsdt.channels(X_f)
    except Exception as e:
        print(f"     Signal computation failed: {e}")
        return {}

    # θ = median pre-onset E_BS (auto-calibration as in CanonicalODE)
    theta = float(np.median(E_bs[:onset_idx]))
    theta = max(theta, 1e-10)

    # γ*(t) = E_BS(t) / (E_BS(t) + θ)   — rises toward 1.0 near collapse
    gamma_star = E_bs / (E_bs + theta)

    signals = {
        "E_BS"      : E_bs,
        "gamma_star": gamma_star,
        "MFLS"      : mfls,
        "rho_MFLS"  : rho,
        "delta_C"   : ch["delta_C"],
        "delta_A"   : ch["delta_A"],
        "delta_T"   : ch["delta_T"],
    }

    # ── Morse curvature on CanonicalODE engine (sample final positions) ──
    # We approximate curvature from the Morse index of the BSDT Hessian
    # on a sliding window around onset rather than per-step.
    # Only compute for modest-size domains (< 500 pre-onset samples) to
    # avoid O(d²) cost on EEG.
    curv_lead = None
    if onset_idx <= 500:
        try:
            # Compute Morse alarm at each pre-onset quarter
            morse_alarms = []
            for t in range(onset_idx):
                # Window of ±2 samples around t for stability
                ws = max(0, t - 2)
                we = min(onset_idx, t + 3)
                Xw = X_f[ws:we]
                if len(Xw) < 3:
                    morse_alarms.append(False)
                    continue
                res = bsdt.morse_alarm(Xw)
                morse_alarms.append(res["alarm"])
            # First persistent Morse alarm (2 consecutive)
            for i in range(len(morse_alarms) - 1):
                if morse_alarms[i] and morse_alarms[i + 1]:
                    curv_lead = onset_idx - i
                    break
        except Exception:
            pass

    # ── Report lead times for each signal ──
    col_w = 12
    print(f"  {'Signal':<14} {'Lead':>{col_w}} {'Hit':>5}  "
          f"description")
    print("  " + "─" * 60)
    results = {}
    for sig_name, arr in signals.items():
        m = early_warning_metrics(arr, onset_idx, roll_win, thresh_sigma)
        lead_str = f"{m['lead']}*" if m["hit"] else str(m["lead"])
        desc = {
            "E_BS"      : "blind-spot energy — direct anomaly signal",
            "gamma_star": "adaptive friction γ* = E/(E+θ) — DAMPING rises pre-collapse",
            "MFLS"      : "‖∇E_BS‖_F — field-line gradient (how hard physics pulls)",
            "rho_MFLS"  : "ρ>1 = state over-amplifies risk = REAL collapse indicator",
            "delta_C"   : "δ_C camouflage channel",
            "delta_A"   : "δ_A activity anomaly (Mahalanobis)",
            "delta_T"   : "δ_T temporal novelty (kNN distance)",
        }.get(sig_name, "")
        print(f"  {sig_name:<14} {lead_str:>{col_w}}   {'YES' if m['hit'] else 'no'}  {desc}")
        results[sig_name] = m

    if curv_lead is not None:
        print(f"  {'Morse(curv)':<14} {str(curv_lead)+'*':>{col_w}}   YES  "
              f"Hessian saddle point (Morse index ≥ 1) — curvature alarm")
        results["Morse_curv"] = {"lead": curv_lead, "hit": True}
    elif onset_idx <= 500:
        print(f"  {'Morse(curv)':<14} {'0':>{col_w}}    no  "
              f"No persistent Morse alarm in pre-onset window")
        results["Morse_curv"] = {"lead": 0, "hit": False}

    return results


# ══════════════════════════════════════════════════════════════════════
#  DOMAIN RUNNER
# ══════════════════════════════════════════════════════════════════════

# Per-domain early-warning parameters (roll_win, thresh_sigma)
# Quarterly banking data: no rolling (1), lower sigma (1.5) — few samples
# Daily ERCOT: roll 5-day window, 2-sigma
# Protein frames: roll 3, 2-sigma — clear temperature boundary
# EEG windows: roll 60s, 2-sigma — brain signals need smoothing
_DOMAIN_EW_PARAMS = {
    "A: G-SIB Banking":   dict(roll_win=1, thresh_sigma=1.5),
    "B: FDIC US Banks":   dict(roll_win=1, thresh_sigma=1.5),
    "C: ERCOT Grid":      dict(roll_win=5, thresh_sigma=2.0),
    "D: Protein Folding": dict(roll_win=3, thresh_sigma=2.0),
    "E: CHB-MIT EEG":     dict(roll_win=60, thresh_sigma=2.0),
}


def run_domain(label: str, X_all: np.ndarray, y_all: np.ndarray,
               onset_idx: int, meta: dict) -> list:
    """Run all 8 engines on one domain. Print lead-time table. Return results."""
    unit = meta.get("unit", "periods")
    unit_detail = meta.get("unit_detail", "")
    ew = _DOMAIN_EW_PARAMS.get(label, dict(roll_win=3, thresh_sigma=2.0))
    roll_win     = ew["roll_win"]
    thresh_sigma = ew["thresh_sigma"]

    print(f"\n{'═'*72}")
    print(f"  DOMAIN : {label}")
    if unit_detail:
        print(f"  Data   : {X_all.shape}  {unit_detail}")
    else:
        print(f"  Data   : {X_all.shape}  unit={unit}")
    print(f"  Onset  : index {onset_idx} / {len(X_all)}  "
          f"({onset_idx} pre-onset, {len(X_all)-onset_idx} post-onset)")
    print(f"  Params : roll_win={roll_win}, thresh={thresh_sigma}σ  "
          f"(threshold from pre-onset only — no label leakage)")
    print(f"{'═'*72}")
    print(f"  {'Engine':<14} {'Lead':>8} {'Hit':>5} {'FA/100':>8} "
          f"{'Disc×':>7}  [s]    "
          f"  Lead = periods before onset, * = alarm fired")
    print("  " + "─" * 68)

    engines = make_engines()
    results = []

    for name, eng in engines:
        t0 = time.time()
        try:
            scores = eng.fit_score(X_all, y_all)
            if scores is None or len(scores) != len(X_all):
                raise ValueError(f"unexpected scores shape {getattr(scores,'shape',None)}")
            m = early_warning_metrics(scores, onset_idx, roll_win, thresh_sigma)
            elapsed = time.time() - t0
            lead_str = f"{m['lead']}*" if m["hit"] else f"{m['lead']}"
            print(f"  {name:<14} {lead_str:>8} "
                  f"{'YES' if m['hit'] else 'no':>5} "
                  f"{m['fa_rate']:>8.2f} "
                  f"{m['disc_ratio']:>7.3f}  {elapsed:>4.0f}")
            results.append({"engine": name, **m,
                             "elapsed_s": round(elapsed, 1),
                             "n_samples": len(X_all),
                             "onset_idx": onset_idx})
        except Exception as e:
            elapsed = time.time() - t0
            msg = str(e)[:60]
            print(f"  {name:<14} {'ERROR':>8}       {msg}  {elapsed:>4.0f}")
            results.append({"engine": name, "error": str(e),
                             "elapsed_s": round(elapsed, 1)})
        gc.collect()

    return results


# ══════════════════════════════════════════════════════════════════════
#  SUMMARY PRINTER
# ══════════════════════════════════════════════════════════════════════

def print_summary(all_results: dict, domain_meta: dict):
    domains  = list(all_results.keys())
    eng_names = []
    for dom in domains:
        for r in all_results[dom]:
            if "error" not in r and r.get("engine") and r["engine"] not in eng_names:
                eng_names.append(r["engine"])

    print(f"\n{'█'*72}")
    print("  CROSS-DOMAIN EARLY WARNING SUMMARY")
    print("  Lead time = periods of advance warning before onset (higher=better)")
    print("  FA/100    = false alarm bursts per 100 pre-onset periods (lower=better)")
    print("  Disc×     = mean(post-onset score) / mean(pre-onset score) (higher=better)")
    print("  *         = alarm actually fired before onset (hit=True)")
    print(f"{'█'*72}")

    # ── Domain key ────────────────────────────────────────────────────
    print("\n  DOMAIN KEY")
    for dom in domains:
        m = domain_meta.get(dom, {})
        unit = m.get("unit_detail") or m.get("unit", "periods")
        onset = m.get("onset_idx", "?")
        print(f"  {dom:<22}  onset@{onset}  [{unit}]")

    # ── Table A: Best lead per domain ─────────────────────────────────
    print(f"\n  TABLE A — Best Lead per Domain (best = longest lead with alarm fired)")
    print(f"  {'Domain':<22} {'Best engine':<14} {'Lead':>6} "
          f"{'FA/100':>7} {'Disc×':>7}")
    print("  " + "─" * 62)
    for dom, results in all_results.items():
        hit_results = [r for r in results if "error" not in r and r.get("hit")]
        no_hit      = [r for r in results if "error" not in r and not r.get("hit")]
        if hit_results:
            best = max(hit_results, key=lambda r: r.get("lead", 0))
            flag = "*"
        elif no_hit:
            best = max(no_hit, key=lambda r: r.get("disc_ratio", 0))
            flag = "(no hit — best disc)"
        else:
            print(f"  {dom:<22} skipped")
            continue
        print(f"  {dom:<22} {best['engine']:<14} {best.get('lead',0):>6}{flag}"
              f" {best.get('fa_rate',0):>7.2f} {best.get('disc_ratio',1):>7.3f}")

    # ── Table B: Lead matrix (all engines × all domains) ──────────────
    print(f"\n  TABLE B — Lead Time Matrix  (* = alarm fired, blank = ERR)")
    labels_short = [d.split(":")[0].strip() + ":" + d.split(":")[1][:8].strip()
                    for d in domains]
    col_w = 11
    hdr = f"  {'Engine':<14}" + "".join(f" {lb:>{col_w}}" for lb in labels_short)
    print(hdr)
    print("  " + "─" * (14 + (col_w + 1) * len(domains)))
    for eng in eng_names:
        row = f"  {eng:<14}"
        for dom in domains:
            rec = next((r for r in all_results[dom] if r.get("engine") == eng), None)
            if rec is None or "error" in rec:
                cell = "-"
            else:
                lead = rec.get("lead", 0)
                mark = "*" if rec.get("hit") else ""
                cell = f"{lead}{mark}"
            row += f" {cell:>{col_w}}"
        print(row)

    # ── Table C: CanonicalODE vs Gravity ─────────────────────────────
    print(f"\n  TABLE C — CanonicalODE vs Gravity  (Δlead = ODE − Gravity)")
    print(f"  {'Domain':<22} {'CanODE':>8} {'Gravity':>9} {'Δlead':>8}")
    print("  " + "─" * 52)
    for dom, results in all_results.items():
        c = next((r for r in results if r.get("engine") == "CanonicalODE"), None)
        g = next((r for r in results if r.get("engine") == "Gravity"),       None)
        if c and g and "error" not in c and "error" not in g:
            delta = c.get("lead", 0) - g.get("lead", 0)
            print(f"  {dom:<22} {c.get('lead',0):>8} {g.get('lead',0):>9}"
                  f" {delta:>+8}")
        else:
            print(f"  {dom:<22} {'—':>8} {'—':>9}")


# ══════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════

DOMAINS = [
    ("A: G-SIB Banking",   load_gsib_banking),
    ("B: FDIC US Banks",   load_fdic_us),
    ("C: ERCOT Grid",      load_ercot_combined),
    ("D: Protein Folding", load_protein),
    ("E: CHB-MIT EEG",     load_chbmit),
]


def main():
    t_start = time.time()
    print("=" * 72)
    print("  ALL ENGINES × ALL DOMAINS — EARLY WARNING BENCHMARK")
    print("  8 physics engines  ×  5 domains")
    print("  Primary metric: Lead time (periods before onset)  [*=hit]")
    print("  No AUC, no machine learning metrics.")
    print("=" * 72)

    all_results: dict  = {}
    domain_meta: dict  = {}

    for label, loader in DOMAINS:
        print(f"\n{'─'*72}")
        print(f"  Loading: {label}")
        t0 = time.time()

        X_all, y_all, onset_idx, meta = loader()
        load_t = time.time() - t0
        domain_meta[label] = meta

        if X_all is None:
            status = meta.get("status", "unknown")
            print(f"  SKIPPED ({status})")
            all_results[label] = [{"engine": "—", "status": "skipped",
                                   "reason": status}]
            continue

        print(f"  Loaded: {X_all.shape}  onset@{onset_idx}  ({load_t:.1f}s)")

        # ── Physics signals (γ*, MFLS, curvature) ──────────────────
        sig_results = run_physics_signals(label, X_all, onset_idx, meta)
        domain_meta[label]["physics_signals"] = sig_results

        # ── Engine scores ───────────────────────────────────────────
        results = run_domain(label, X_all, y_all, onset_idx, meta)
        all_results[label] = results

    print_summary(all_results, domain_meta)

    # ── Save JSON ────────────────────────────────────────────────────
    def _jsonify(obj):
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return str(obj)

    out_path = os.path.join(ROOT, "all_engines_all_domains_results.json")
    with open(out_path, "w") as f:
        json.dump({"meta": domain_meta, "results": all_results,
                   "total_elapsed_s": round(time.time() - t_start, 1)},
                  f, indent=2, default=_jsonify)
    print(f"\n  Results → {out_path}")
    print(f"  Total elapsed: {time.time()-t_start:.0f}s")


if __name__ == "__main__":
    main()
