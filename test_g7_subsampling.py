"""
G7 Subsampling Diagnostic
=========================
Tests whether the universally-observed G7 flag (κ(Σ₀) > 10) is a genuine
geometric invariant of CHB-MIT EEG or a dimensionality artifact caused by
d >> n_ref (rank-deficient covariance).

Method
------
For each patient's reference file:
  1. Extract full feature matrix X_ref  (n_ref × d_full)
  2. For d_target in [207, 150, 100, 50, 25]:
       Repeat N_REP=30 random column-subsamplings:
         - Subsample d_target columns
         - Compute Σ₀ (sample covariance)
         - Eigenspectrum: effective rank, κ = λ_max / λ_min_pos
         - G7 flag: κ > 10
  3. Report: mean κ ± std, G7 rate, effective rank, Δ(d − n_ref)

Critical threshold: n_ref ≈ 117 windows (120 s at stride=1 s, 4 s window)
  d > n_ref  →  rank-deficient by construction  →  κ = ∞ (λ_min ≈ 0)
  d < n_ref  →  covariance can be full-rank; G7 now reflects genuine data geometry

Interpretation guide
--------------------
  If G7 rate stays 100% down through d=25: genuine geometric invariant.
  If G7 collapses when d < n_ref: high-dimensional artifact (λ_min → 0 mechanically).

Patients tested (representative sample covering n_ch=23 and n_ch=28):
  chb01, chb04, chb06, chb09, chb12
"""

import sys, os, warnings
import numpy as np

warnings.filterwarnings("ignore")

ROOT       = r"C:\amttp"
EEG_BASE   = os.path.join(ROOT, "data", "external_validation", "eeg")
CHBMIT_DIR = os.path.join(EEG_BASE, "chbmit")

SFREQ_TARGET   = 64
WIN_S          = 4
STRIDE_S       = 1
REF_DURATION_S = 120.0
N_REP          = 30                           # random draws per (patient, d)
D_TARGETS      = [207, 150, 100, 50, 25]      # feature-dimensionality sweep

# ── Copy of EDF / feature utilities from test_chbmit_full_validation ──────────

_EDF_WIDTHS = [16, 80, 8, 8, 8, 8, 8, 80, 8, 32]
_EDF_FNAMES = ['label', 'transducer', 'phys_dim', 'phys_min', 'phys_max',
               'dig_min', 'dig_max', 'prefilter', 'nsamples', 'reserved']
_EPS = 1e-10


def _read_edf_raw(path, end_s=1e9):
    with open(path, "rb") as fh:
        hdr = fh.read(256)
        nr_records   = int(hdr[236:244].strip())
        rec_duration = float(hdr[244:252].strip())
        ns_total     = int(hdr[252:256].strip())
        sig_hdr = fh.read(ns_total * 256)
        ns = min(ns_total, 32)

        def _get(fn, si):
            fi   = _EDF_FNAMES.index(fn)
            base = sum(_EDF_WIDTHS[:fi]) * ns_total + si * _EDF_WIDTHS[fi]
            return sig_hdr[base: base + _EDF_WIDTHS[fi]].decode(errors='replace').strip()
        def _sf(fn, si, d=0.0):
            try: return float(_get(fn, si))
            except: return d
        def _si(fn, si, d=256):
            try: return int(_get(fn, si))
            except: return d

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
        end_rec = min(nr_records, int(np.ceil(end_s / rec_duration)))
        n_recs  = end_rec

        fh.seek(header_bytes)
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
    s1 = int(end_s * sfreq)
    return X[:s1], float(sfreq)


def _decimate(data, factor):
    kernel = np.ones(factor) / factor
    out = np.apply_along_axis(lambda x: np.convolve(x, kernel, mode='same'), 0, data)
    return out[::factor]


def load_ref(path):
    data, sfreq = _read_edf_raw(path, end_s=REF_DURATION_S)
    native = int(round(sfreq))
    if native > SFREQ_TARGET:
        data = _decimate(data, native // SFREQ_TARGET)
    return data


def _band_power(x, sfreq, lo, hi):
    n = len(x)
    freqs = np.fft.rfftfreq(n, 1.0 / sfreq)
    psd   = np.abs(np.fft.rfft(x * np.hanning(n))) ** 2
    mask  = (freqs >= lo) & (freqs < hi)
    return float(np.log(psd[mask].mean() + 1e-30))


def extract_features(data):
    n_samp, n_ch = data.shape
    win_samples    = WIN_S * SFREQ_TARGET
    stride_samples = STRIDE_S * SFREQ_TARGET
    starts = np.arange(0, n_samp - win_samples + 1, stride_samples)
    n_win  = len(starts)
    if n_win == 0:
        return np.zeros((0, n_ch * 9), dtype=np.float64)
    X = np.zeros((n_win, n_ch * 9), dtype=np.float64)
    for wi, st in enumerate(starts):
        seg = data[st: st + win_samples]
        for ci in range(n_ch):
            x   = seg[:, ci]
            off = ci * 9
            X[wi, off + 0] = x.mean()
            X[wi, off + 1] = x.std() + 1e-10
            X[wi, off + 2] = np.log(x.var() + 1e-10)
            X[wi, off + 3] = np.mean(np.abs(np.diff(x)))
            X[wi, off + 4] = _band_power(x, SFREQ_TARGET, 0.5,  4.0)
            X[wi, off + 5] = _band_power(x, SFREQ_TARGET, 4.0,  8.0)
            X[wi, off + 6] = _band_power(x, SFREQ_TARGET, 8.0,  13.0)
            X[wi, off + 7] = _band_power(x, SFREQ_TARGET, 13.0, 30.0)
            X[wi, off + 8] = _band_power(x, SFREQ_TARGET, 30.0, 49.0)
    return X


# ── Core subsampling probe ────────────────────────────────────────────────────

def probe_g7(X_ref, d_target, rng):
    """One random-subsample probe.

    Returns
    -------
    kappa       : condition number λ_max / λ_min_pos
    eff_rank    : number of eigenvalues > 1e-12 * λ_max
    g7_flag     : kappa > 10
    lam_max     : largest eigenvalue
    lam_min_pos : smallest positive eigenvalue (or 1e-12 if none)
    """
    n, d_full = X_ref.shape
    d = min(d_target, d_full)   # can't subsample more than we have

    cols = rng.choice(d_full, size=d, replace=False)
    Xs   = X_ref[:, cols]

    mu  = Xs.mean(axis=0)
    Z   = Xs - mu
    cov = (Z.T @ Z) / max(n - 1, 1)

    eigvals  = np.linalg.eigvalsh(cov)[::-1]          # descending
    lam_max  = float(eigvals[0])
    pos_mask = eigvals > 1e-12 * max(lam_max, 1e-30)
    eff_rank = int(pos_mask.sum())
    lam_min  = float(eigvals[pos_mask][-1]) if eff_rank > 0 else 1e-12
    kappa    = lam_max / max(lam_min, 1e-12)

    return dict(
        kappa       = float(kappa),
        eff_rank    = eff_rank,
        g7_flag     = bool(kappa > 10.0),
        lam_max     = lam_max,
        lam_min_pos = lam_min,
    )


# ── Patient registry (subset) ──────────────────────────────────────────────────

def _p(patient, fname):
    if patient == "chb01":
        return os.path.join(EEG_BASE, fname)
    return os.path.join(CHBMIT_DIR, patient, fname)


PROBE_PATIENTS = [
    # (id,    ref_edf)
    ("chb01",  _p("chb01",  "chb01_01.edf")),
    ("chb04",  _p("chb04",  "chb04_01.edf")),
    ("chb06",  _p("chb06",  "chb06_02.edf")),
    ("chb09",  _p("chb09",  "chb09_01.edf")),
    ("chb12",  _p("chb12",  "chb12_19.edf")),
]


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    rng = np.random.default_rng(42)

    print("=" * 72)
    print("G7 SUBSAMPLING DIAGNOSTIC — κ(Σ₀) vs feature dimensionality")
    print("Gap Addendum G7: κ(Σ₀) > 10  →  Ψ* < 10% ideal  →  regularise")
    print("=" * 72)
    print(f"  N_REP={N_REP} random draws per (patient, d_target)")
    print(f"  d_targets = {D_TARGETS}")
    print(f"  REF_DURATION = {REF_DURATION_S:.0f} s  →  n_ref ≈ "
          f"{int(REF_DURATION_S - WIN_S) + 1} windows  (d>n: rank-deficient region)")
    print()

    # --- Per-patient results -------------------------------------------------
    # results[pid][d] = list of probe dicts
    all_results = {}

    for pid, ref_path in PROBE_PATIENTS:
        if not os.path.exists(ref_path):
            print(f"  [{pid}] SKIP — {ref_path} not found")
            continue

        print(f"  Loading {pid} reference ...", end=" ", flush=True)
        raw = load_ref(ref_path)
        X_full = extract_features(raw)
        n_ref, d_full = X_full.shape
        print(f"n_ref={n_ref}  d_full={d_full}")

        all_results[pid] = {}
        for d_target in D_TARGETS:
            probes = [probe_g7(X_full, d_target, rng) for _ in range(N_REP)]
            all_results[pid][d_target] = probes

    # --- Aggregate table -------------------------------------------------------
    print()
    print("─" * 72)
    print(f"{'Patient':<10}  {'d':>5}  {'n_ref':>6}  {'d/n':>5}  "
          f"{'κ mean':>14}  {'κ std':>12}  {'G7%':>5}  "
          f"{'eff_rank':>8}  {'λ_min mean':>12}")
    print("─" * 72)

    grand_kappa_by_d = {d: [] for d in D_TARGETS}
    grand_g7_by_d    = {d: [] for d in D_TARGETS}

    for pid, ref_path in PROBE_PATIENTS:
        if pid not in all_results:
            continue
        # infer n_ref from d=207 probe (same X_full)
        first_probe = all_results[pid][D_TARGETS[0]][0]
        raw2 = load_ref(ref_path)
        Xf   = extract_features(raw2)
        n_ref = Xf.shape[0]

        for d_target in D_TARGETS:
            probes = all_results[pid][d_target]
            kappas   = np.array([p['kappa']    for p in probes])
            eff_r    = np.array([p['eff_rank']  for p in probes])
            g7_flags = np.array([p['g7_flag']   for p in probes])
            lmins    = np.array([p['lam_min_pos'] for p in probes])

            d_actual = min(d_target, Xf.shape[1])
            ratio    = d_actual / n_ref

            # clamp κ for display (numerical ∞ → 1e15)
            kappa_disp = np.minimum(kappas, 1e15)

            print(f"  {pid:<8}  {d_actual:>5}  {n_ref:>6}  {ratio:>5.2f}  "
                  f"  {kappa_disp.mean():>12.3e}  {kappa_disp.std():>12.3e}  "
                  f"  {g7_flags.mean()*100:>4.0f}%  "
                  f"  {eff_r.mean():>7.1f}  "
                  f"  {lmins.mean():>12.3e}")

            grand_kappa_by_d[d_target].extend(kappa_disp.tolist())
            grand_g7_by_d[d_target].extend(g7_flags.tolist())

        print()

    # --- Grand aggregate -------------------------------------------------------
    print("─" * 72)
    print(f"{'ALL':<10}  {'d':>5}  {'':>6}  {'':>5}  "
          f"{'κ mean':>14}  {'κ std':>12}  {'G7%':>5}  {'':>8}  {'':>12}")
    print("─" * 72)
    for d in D_TARGETS:
        kv = np.array(grand_kappa_by_d[d])
        gv = np.array(grand_g7_by_d[d])
        print(f"  {'ALL':<8}  {d:>5}  {'':>6}  {'':>5}  "
              f"  {kv.mean():>12.3e}  {kv.std():>12.3e}  "
              f"  {gv.mean()*100:>4.0f}%")

    # --- Interpretation --------------------------------------------------------
    print()
    print("=" * 72)
    print("INTERPRETATION")
    print("=" * 72)
    n_ref_nominal = int(REF_DURATION_S - WIN_S) + 1
    print(f"  n_ref (nominal) = {n_ref_nominal} windows")
    print(f"  Rank-deficient regime: d > {n_ref_nominal}  →  d in "
          f"{[d for d in D_TARGETS if d > n_ref_nominal]}")
    print(f"  Full-rank capable:     d < {n_ref_nominal}  →  d in "
          f"{[d for d in D_TARGETS if d < n_ref_nominal]}")
    print()

    # Determine verdict from grand aggregate G7 rates
    rates = {d: np.mean(grand_g7_by_d[d]) * 100 for d in D_TARGETS}
    below_n = [(d, rates[d]) for d in D_TARGETS if d < n_ref_nominal]
    if below_n:
        low_d, low_rate = min(below_n, key=lambda x: x[0])
        if low_rate >= 95:
            print(f"  VERDICT → G7 is a GENUINE GEOMETRIC INVARIANT")
            print(f"  (G7 rate at d={low_d} is {low_rate:.0f}% — survives full-rank regime)")
        elif low_rate <= 10:
            print(f"  VERDICT → G7 is a HIGH-DIMENSIONAL ARTIFACT")
            print(f"  (G7 rate collapses to {low_rate:.0f}% at d={low_d} < n_ref)")
        else:
            print(f"  VERDICT → G7 is MIXED: partly artifact + partly genuine signal")
            print(f"  (G7 rate at d={low_d}: {low_rate:.0f}% — partial collapse at full-rank boundary)")
    print()


if __name__ == "__main__":
    main()
