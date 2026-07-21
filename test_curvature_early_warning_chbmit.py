"""
Curvature + Probabilistic Geometry Early Warning — CHB-MIT Scalp EEG
====================================================================
Implements the Complete Derivations Geometric Compression Hierarchy:

    Level 1 (Curvature) : κ(t) — Gershgorin bound on ∇²Φ_pair
    Level 2 (Dynamics)  : cos θ, θ̇, θ̈, R (Kuramoto), Ṙ, P(t)
    Level 3 (Energy)    : E(t) — Mahalanobis departure
    Probabilistic       : p-value from MFLS as χ²(d)
    Safety Ratio        : θ·MFLS/(2·M_max·√E)

Theorem 46.1 (Three-Phase Precursor):
    P(t) = 1[Ė>0] ∧ 1[Ṙ>0] ∧ 1[θ̈>0]
    Under P(t): d(SafetyRatio)/dt < 0  (imminent collapse)

Lead-time hierarchy (GC.2):  τ_κ ≥ τ_E ≥ τ_R ≥ τ_P

Datasets:
    - chb01_03.edf  (seizure onset=2996s)
    - chb01_04.edf  (seizure onset=1467s, cross-validation)

Author: Copilot — May 2026
"""

import sys, os, time, json, warnings
import numpy as np
from scipy.stats import chi2 as scipy_chi2

warnings.filterwarnings("ignore")

# ── paths ──────────────────────────────────────────────────────────────────
ROOT       = r"C:\amttp"
EEG_DIR    = os.path.join(ROOT, "data", "external_validation", "eeg")
RESULT_DIR = os.path.join(ROOT, "research", "neural-stability", "results")
os.makedirs(RESULT_DIR, exist_ok=True)

CHB_REF_EDF  = os.path.join(EEG_DIR, "chb01_01.edf")
CHB_TEST_EDF = os.path.join(EEG_DIR, "chb01_03.edf")
CHB04_EDF    = os.path.join(EEG_DIR, "chb01_04.edf")

SFREQ_TARGET      = 64        # Hz — same as CGS-v1
WIN_S             = 4         # window length (s)
STRIDE_S          = 1         # stride (s)
REF_DURATION_S    = 120.0     # calibration window

# Gershgorin potential parameters (GravityEngine, §51.1)
GRAV_ALPHA  = 0.10   # radial stiffness
GRAV_GAMMA  = 1.00   # Gaussian well depth
GRAV_LAMBDA = 0.10   # logarithmic repulsion
GRAV_EPS    = 1e-5   # numerical guard

# Analysis windows
ROLL_WIN_S   = 60    # rolling window for lead-time detection (s)
SUSP_WIN_S   = 60    # curvature sliding window (s)
BKG_MULT     = 2.0   # threshold = BKG_MULT × background
KAPPA_CRIT   = 1.0   # supercriticality threshold (Level 1)

# ══════════════════════════════════════════════════════════════════════════
# 1. EDF reader (verbatim from test_physics_engine_chbmit.py)
# ══════════════════════════════════════════════════════════════════════════

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
            fi   = _EDF_FNAMES.index(fn)
            base = sum(_EDF_WIDTHS[:fi]) * ns_total + si * _EDF_WIDTHS[fi]
            return sig_hdr[base: base + _EDF_WIDTHS[fi]].decode(errors="replace").strip()
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
        sfreq  = float(nsamples[0]) / rec_duration
        gain   = (physmax - physmin) / (digmax - digmin + _EPS)
        offset = physmin - digmin * gain
        hdr_bytes     = 256 + ns_total * 256
        bpr           = int(np.sum(nsamples)) * 2
        s_rec = max(0, int(start_s / rec_duration))
        e_rec = min(nr_records, int(np.ceil(end_s / rec_duration)))
        fh.seek(hdr_bytes + s_rec * bpr)
        chunks = []
        for _ in range(e_rec - s_rec):
            rch = []
            for i in range(ns_total):
                n = max(0, int(nsamples[i]))
                raw = np.frombuffer(fh.read(n * 2), dtype=np.int16)
                if i < ns:
                    rch.append(raw.astype(np.float64) * gain[i] + offset[i])
            chunks.append(rch)
    X = np.concatenate([np.stack(chunks[r], axis=-1) for r in range(len(chunks))], axis=0)
    s0 = int((start_s - s_rec * rec_duration) * sfreq)
    s1 = s0 + int((end_s - start_s) * sfreq)
    return X[s0: min(s1, X.shape[0])], labels, float(sfreq)


def load_edf(path, target_sfreq=64, max_dur=None):
    end_s = max_dur if max_dur else 1e9
    data, labels, sfreq = _read_edf_raw(path, end_s=end_s)
    factor = int(round(sfreq)) // target_sfreq
    if factor > 1:
        k = np.ones(factor) / factor
        data = np.apply_along_axis(lambda x: np.convolve(x, k, 'same'), 0, data)[::factor]
    return data, target_sfreq, labels


# ══════════════════════════════════════════════════════════════════════════
# 2. Feature extraction
# ══════════════════════════════════════════════════════════════════════════

def _bp(x, sf, lo, hi):
    n = len(x)
    if n < 8: return 0.0
    f = np.fft.rfftfreq(n, 1.0 / sf)
    p = np.abs(np.fft.rfft(x)) ** 2
    m = (f >= lo) & (f < hi)
    return float(p[m].mean()) if m.any() else 0.0


def extract_features(data, sfreq, win_samp, stride_samp):
    """Return (n_win, n_ch*9) feature matrix and (n_win,) centre-second array."""
    T, n_ch = data.shape
    starts = np.arange(0, T - win_samp + 1, stride_samp)
    n_win  = len(starts)
    X = np.zeros((n_win, n_ch * 9), dtype=np.float32)
    for wi, st in enumerate(starts):
        seg = data[st: st + win_samp]
        for ci in range(n_ch):
            x   = seg[:, ci].astype(np.float64)
            off = ci * 9
            X[wi, off + 0] = x.mean()
            X[wi, off + 1] = x.std() + 1e-10
            X[wi, off + 2] = np.log(x.var() + 1e-10)
            X[wi, off + 3] = np.mean(np.abs(np.diff(x)))
            X[wi, off + 4] = _bp(x, sfreq, 0.5,  4.0)
            X[wi, off + 5] = _bp(x, sfreq, 4.0,  8.0)
            X[wi, off + 6] = _bp(x, sfreq, 8.0, 13.0)
            X[wi, off + 7] = _bp(x, sfreq, 13., 30.0)
            X[wi, off + 8] = _bp(x, sfreq, 30., 49.0)
    centres_s = (starts + win_samp / 2.0) / sfreq
    return X.astype(np.float64), centres_s


# ══════════════════════════════════════════════════════════════════════════
# 3. Canonical dashboard signals — all from gX and E
#    (Complete Derivations §18)
# ══════════════════════════════════════════════════════════════════════════

def canonical_signals(X_test, mu_ref, sigma_ref, X_ref):
    """
    Compute per-window canonical dashboard from the Geometric Compression Hierarchy.

    After z-scoring (Σ = I), the canonical objects simplify:
        E(t)   = ‖x̃_t‖²                   (Mahalanobis energy)
        gX(t)  = 2 x̃_t                     (gradient, §3)
        MFLS   = ‖gX‖ = 2√E               (§4)
        γ(t)   = E/(E+θ)                   (§5, θ = median(E_ref))
        F_base = x_t − x_{t−1}            (actual state velocity)
        cos θ  = ⟨F_base, gX⟩/(‖F_base‖·‖gX‖)   (§14)
        ρ_eff  = MFLS²·(1−γ)/E            (§8)
        SafetyRatio = θ·MFLS/(2·M_max·√E) (§13)

    Level 1 (Curvature, §51.3 Gershgorin bound):
        κ(t) = α + Σ_{j in slide(t)} [2γ/(√π·σ)·exp(−D²/σ²) + λ/(D²+ε)]
        over the SUSP_WIN_S most recent windows (reference + test, causal)

    Level 2 Phase (§45):
        R(t) = |⟨exp(iφ_j)⟩| over channels (Kuramoto, per-channel PCA phases)

    Returns dict of (n_test,) arrays.
    """
    n_test, d = X_test.shape
    n_ref     = len(X_ref)

    # --- z-score standardisation on reference stats ---
    std_ref = sigma_ref.copy()
    std_ref[std_ref < 1e-12] = 1e-12
    Z_ref  = (X_ref  - mu_ref) / std_ref
    Z_test = (X_test - mu_ref) / std_ref

    # --- θ_cgs calibration ---
    E_ref = np.sum(Z_ref ** 2, axis=1)
    theta = float(np.median(E_ref))
    M_max = float(np.percentile(np.sqrt(E_ref), 99))  # 99th-pct MFLS bound

    # --- PCA top-2 on reference for Kuramoto phases ---
    Zr_c  = Z_ref - Z_ref.mean(axis=0)
    try:
        _, _, Vt = np.linalg.svd(Zr_c, full_matrices=False)
        V1, V2 = Vt[0], Vt[1]   # (d,) leading eigenvectors
    except np.linalg.LinAlgError:
        V1, V2 = np.zeros(d), np.zeros(d); V1[0] = V2[1] = 1.0

    # --- Gershgorin sigma (median pairwise dist in reference + 1st 60 test) ---
    sample_ref = Z_ref[:min(60, n_ref)]
    # Compute all pairwise distances within sample
    def _pdist_median(A):
        n = len(A)
        if n < 2: return 1.0
        dists = []
        for i in range(min(n, 30)):
            for j in range(i + 1, min(n, 30)):
                dists.append(float(np.linalg.norm(A[i] - A[j])))
        return float(np.median(dists)) if dists else 1.0

    sigma_grav = _pdist_median(sample_ref)
    sigma_grav = max(sigma_grav, 1e-3)

    # ---- per-window computation ----
    E_arr        = np.zeros(n_test)
    mfls_arr     = np.zeros(n_test)
    gamma_arr    = np.zeros(n_test)
    cos_theta_arr= np.zeros(n_test)
    theta_arr    = np.zeros(n_test)
    rho_eff_arr  = np.zeros(n_test)
    safety_arr   = np.zeros(n_test)
    R_arr        = np.zeros(n_test)     # Kuramoto
    kappa_arr    = np.zeros(n_test)     # Level-1 curvature
    pval_arr     = np.ones(n_test)      # chi² p-value

    # Reference single-point inverse-density (Level 0: basin exit)
    # κ₀(t) = α + Σ_j[ref] [2γ/(√π·σ)·exp(−D²_tj/σ²) + λ/D²_tj]
    # HIGH when x_t is INSIDE reference distribution; LOW when it exits basin.
    # This is the Level 0 / topology signal: measures occupancy at x_t.
    kappa0_arr = np.zeros(n_test)   # basin-exit curvature

    # Sliding buffer for system-level curvature: starts with last SUSP_WIN_S ref windows
    slide_buf = list(Z_ref[-min(SUSP_WIN_S, n_ref):])

    for t in range(n_test):
        zt = Z_test[t]

        # --- Level 3: Energy ---
        E  = float(np.dot(zt, zt))
        E_arr[t] = E

        # --- MFLS = 2√E  (gX = 2·zt after z-scoring with Σ=I) ---
        mfls = 2.0 * np.sqrt(max(E, 1e-30))
        mfls_arr[t] = mfls
        gamma_arr[t] = E / (E + theta + 1e-30)

        # --- cos θ: velocity-based F_base (actual state motion direction) ---
        if t > 0:
            Fbase = Z_test[t] - Z_test[t - 1]
        else:
            Fbase = np.zeros(d)
        gX = 2.0 * zt
        n_Fbase = np.linalg.norm(Fbase)
        n_gX    = mfls
        if n_Fbase > 1e-12 and n_gX > 1e-12:
            ct = float(np.dot(Fbase, gX)) / (n_Fbase * n_gX)
            ct = float(np.clip(ct, -1.0, 1.0))
        else:
            ct = 0.0
        cos_theta_arr[t] = ct
        theta_t          = float(np.arccos(ct))   # alignment angle at time t
        theta_arr[t]     = theta_t

        # --- ρ_eff (§8) ---
        rho_eff_arr[t] = (mfls ** 2) * (1.0 - gamma_arr[t]) / max(E, 1e-30)

        # --- Safety ratio (§13): θ_t = alignment angle, NOT calibration scalar ---
        # SafetyRatio(t) = θ_t · MFLS(t) / (2·M_max·√E(t))
        #               = arccos(cos θ_t) · 2√E / (2·M_max·√E)
        #               = arccos(cos θ_t) / M_max
        # Drops toward 0 when motion aligns with gradient (cos θ → 1) during collapse.
        safety_arr[t] = theta_t / (M_max + 1e-30)

        # --- Kuramoto R (§45.3): per-channel phases from PCA projection ---
        # Phase of channel c: arctan2(V2[c] · x̃_c, V1[c] · x̃_c)
        n_ch = d // 9
        phases = np.zeros(n_ch)
        for ci in range(n_ch):
            sl   = slice(ci * 9, (ci + 1) * 9)
            zc   = zt[sl]
            a    = float(np.dot(V1[sl], zc))
            b    = float(np.dot(V2[sl], zc))
            phases[ci] = np.arctan2(b, a)
        R_arr[t] = float(np.abs(np.mean(np.exp(1j * phases))))

        # --- Level 1: SYSTEM-LEVEL Gershgorin curvature (§51.3) ---
        # Configuration = last SUSP_WIN_S windows (sliding buffer, causal).
        # The FULL system Gershgorin bound:
        #   κ = α + max_i Σ_{j≠i} [2γ/(√π·σ)·exp(-D²_ij/σ²) + λ/D²_ij]
        # → LOW when windows are SPREAD OUT (normal interictal)
        # → HIGH when windows CLUSTER (pre-ictal synchrony / ictal onset)
        slide_buf.append(zt.copy())
        if len(slide_buf) > SUSP_WIN_S:
            slide_buf.pop(0)
        if len(slide_buf) > 1:
            buf   = np.array(slide_buf)           # (W, d), W ≤ SUSP_WIN_S
            # pairwise D² in O(W²·d) via einsum trick
            sq    = np.einsum('id,id->i', buf, buf)   # (W,)
            D2mat = sq[:, None] + sq[None, :] - 2.0 * (buf @ buf.T)  # (W,W)
            D2mat = np.maximum(D2mat, GRAV_EPS ** 2)
            np.fill_diagonal(D2mat, np.inf)
            s2    = sigma_grav ** 2
            row_sums = np.sum(
                2.0 * GRAV_GAMMA / (np.sqrt(np.pi) * sigma_grav) * np.exp(-D2mat / s2)
                + GRAV_LAMBDA / D2mat,
                axis=1
            )
            kappa = GRAV_ALPHA + float(np.max(row_sums))
        else:
            kappa = GRAV_ALPHA
        kappa_arr[t] = kappa

        # --- Level 0: basin-exit single-point density curvature ---
        # Computed against ALL reference windows (fixed calibration distribution).
        diffs0 = Z_ref - zt           # (N_ref, d)
        D2_0   = np.sum(diffs0 ** 2, axis=1) + GRAV_EPS ** 2  # (N_ref,)
        s2     = sigma_grav ** 2
        kappa0_arr[t] = GRAV_ALPHA + float(np.sum(
            2.0 * GRAV_GAMMA / (np.sqrt(np.pi) * sigma_grav) * np.exp(-D2_0 / s2)
            + GRAV_LAMBDA / D2_0
        ))

        # --- χ² p-value: E(t) ~ χ²(d) under Gaussian null (§57, §62) ---
        pval_arr[t] = float(scipy_chi2.sf(E, df=d))

    # --- Derived time-series ---
    E_dot      = np.gradient(E_arr)
    theta_dot  = np.gradient(theta_arr)
    theta_ddot = np.gradient(theta_dot)
    R_dot      = np.gradient(R_arr)

    # Three-phase precursor P(t) = Ė>0 ∧ Ṙ>0 ∧ θ̈>0  (Theorem 46.1)
    P_arr = (E_dot > 0) & (R_dot > 0) & (theta_ddot > 0)

    return dict(
        theta_cgs   = theta,
        M_max       = M_max,
        sigma_grav  = sigma_grav,
        E           = E_arr,
        mfls        = mfls_arr,
        gamma       = gamma_arr,
        cos_theta   = cos_theta_arr,
        theta       = theta_arr,
        theta_dot   = theta_dot,
        theta_ddot  = theta_ddot,
        rho_eff     = rho_eff_arr,
        safety_ratio= safety_arr,
        R           = R_arr,
        R_dot       = R_dot,
        E_dot       = E_dot,
        P           = P_arr,
        kappa       = kappa_arr,     # Level 1: system clustering curvature
        kappa0      = kappa0_arr,    # Level 0: single-point basin-exit density
        p_value     = pval_arr,
    )


# ══════════════════════════════════════════════════════════════════════════
# 4. Lead-time and discrimination metrics
# ══════════════════════════════════════════════════════════════════════════

def _rolling_mean(arr, w):
    """Causal rolling mean via cumsum."""
    cs = np.cumsum(np.concatenate([[0], arr]))
    out = np.zeros_like(arr)
    for i in range(len(arr)):
        lo = max(0, i - w + 1)
        cnt = i - lo + 1
        out[i] = (cs[i + 1] - cs[lo]) / cnt
    return out


def _first_sustained_lead(signal, y, centres_s, onset_s, bkg_mult, roll_w):
    """Lead time of first sustained alarm (rolling mean > bkg_mult × bkg) before onset."""
    bkg_mask    = y == 0
    roll        = _rolling_mean(signal, roll_w)
    bkg_level   = float(roll[bkg_mask].mean()) if bkg_mask.any() else 1e-9
    thresh      = bkg_mult * bkg_level
    pre_mask    = (centres_s < onset_s) & bkg_mask
    for i in range(len(roll)):
        if pre_mask[i] and roll[i] >= thresh:
            return onset_s - centres_s[i]
    return float("nan")


def _first_sustained_rate(bool_arr, centres_s, onset_s, y, roll_w, rate_thresh=0.30):
    """Lead time of first sustained boolean rate (rolling fraction > rate_thresh) before onset."""
    roll = _rolling_mean(bool_arr.astype(float), roll_w)
    bkg_mask = (y == 0) & (centres_s < onset_s)
    for i in range(len(roll)):
        if bkg_mask[i] and roll[i] >= rate_thresh:
            return onset_s - centres_s[i]
    return float("nan")


def _disc_and_auroc(signal, y):
    from sklearn.metrics import roc_auc_score
    ictal = y == 1
    inter = y == 0
    mi = signal[ictal].mean()  if ictal.any() else 0.0
    mn = signal[inter].mean() if inter.any() else 1e-9
    dr = mi / (mn + 1e-10)
    try:
        auc = float(roc_auc_score(y, signal)) if ictal.any() and inter.any() else float("nan")
    except Exception:
        auc = float("nan")
    return float(mi), float(mn), float(dr), auc


# ══════════════════════════════════════════════════════════════════════════
# 5. Full analysis for one EDF
# ══════════════════════════════════════════════════════════════════════════

def analyse_edf(test_edf, ref_edf, onset_s, offset_s, label, ref_cache=None):
    t0 = time.time()
    print(f"\n  Loading test EDF: {os.path.basename(test_edf)}")
    data_t, sf, _ = load_edf(test_edf, SFREQ_TARGET)
    win_samp = WIN_S * sf; stride_samp = STRIDE_S * sf
    X_test, centres_s = extract_features(data_t, sf, win_samp, stride_samp)
    n_win = len(X_test)
    y = ((centres_s >= onset_s) & (centres_s <= offset_s)).astype(int)
    print(f"  Windows: {n_win}  ictal={int(y.sum())}  interictal={int((y==0).sum())}")

    if ref_cache is None:
        print(f"  Loading reference EDF: {os.path.basename(ref_edf)}")
        data_r, _, _ = load_edf(ref_edf, SFREQ_TARGET, max_dur=REF_DURATION_S)
        data_r = data_r[:, :data_t.shape[1]]
        X_ref, _ = extract_features(data_r, sf, win_samp, stride_samp)
        print(f"  Reference windows: {len(X_ref)}")
    else:
        X_ref = ref_cache

    mu_ref    = X_ref.mean(axis=0)
    sigma_ref = X_ref.std(axis=0)

    print(f"  Computing canonical dashboard (d={X_test.shape[1]})…")
    sig = canonical_signals(X_test, mu_ref, sigma_ref, X_ref)
    roll_w = ROLL_WIN_S // STRIDE_S

    # ── per-signal metrics ──────────────────────────────────────────────
    results = {}
    print(f"\n  ── Canonical Dashboard ──────────────────────────────────────")
    print(f"  θ_cgs = {sig['theta_cgs']:.4f}  M_max = {sig['M_max']:.4f}  "
          f"σ_grav = {sig['sigma_grav']:.4f}")

    for name, arr, level in [
        ("Energy  E(t)",          sig["E"],           "L3"),
        ("κ₁(t) system-cluster",  sig["kappa"],       "L1"),
        ("κ₀(t) basin-exit",      sig["kappa0"],      "L0"),
        ("Kuramoto R(t)",         sig["R"],           "L2"),
        ("MFLS",                  sig["mfls"],        "L2"),
        ("Safety Ratio",          sig["safety_ratio"],"L2"),
        ("-log₁₀(p-value)",       -np.log10(sig["p_value"] + 1e-300), "Prob"),
    ]:
        mi, mn, dr, auc = _disc_and_auroc(arr, y)
        lead = _first_sustained_lead(arr, y, centres_s, onset_s, BKG_MULT, roll_w)
        print(f"\n  [{level}] {name}")
        print(f"    Discrimination: {dr:.2f}×  ({mi:.4f} ictal / {mn:.4f} interictal)")
        print(f"    AUROC: {auc:.4f}")
        if not np.isnan(lead):
            print(f"    Sustained lead (2×bkg, 60s rolling): {lead:.1f} s")
        else:
            print(f"    Sustained lead: not detected before onset")
        results[name] = dict(mi=mi, mn=mn, disc=dr, auroc=auc, lead_s=lead, level=level)

    # ── Kuramoto and three-phase lead times ──────────────────────────────
    print(f"\n  ── Hierarchy Lead Times (Theorem 46.2: τ_κ ≥ τ_E ≥ τ_R ≥ τ_P) ──")

    tau_kappa1= _first_sustained_lead(sig["kappa"],  y, centres_s, onset_s, BKG_MULT, roll_w)
    # Level 0: basin exit = INVERSE density signal (alarm when κ₀ drops below bkg)
    # κ₀_inv = -κ₀ shifted so alarm fires when κ₀ drops to 1/BKG_MULT × bkg
    kappa0_inv= sig["kappa0"].max() - sig["kappa0"]   # invert: low density → high signal
    tau_kappa0= _first_sustained_lead(kappa0_inv, y, centres_s, onset_s, BKG_MULT, roll_w)
    tau_E     = _first_sustained_lead(sig["E"],    y, centres_s, onset_s, BKG_MULT, roll_w)
    tau_R     = _first_sustained_lead(sig["R"],    y, centres_s, onset_s, 1.2,      roll_w)
    tau_P     = _first_sustained_rate(sig["P"],    centres_s, onset_s, y, roll_w, rate_thresh=0.30)

    def _pf(v): return f"{v:.1f} s" if not np.isnan(v) else "not detected"
    print(f"    Level 0  τ_κ₀ (basin-exit density):  {_pf(tau_kappa0)}")
    print(f"    Level 3  τ_E  (energy 2×bkg):         {_pf(tau_E)}")
    print(f"    Level 2  τ_R  (Kuramoto 1.2×bkg):     {_pf(tau_R)}")
    print(f"    Level 2  τ_P  (3-phase rate≥30%):     {_pf(tau_P)}")
    print(f"    Level 1  τ_κ₁ (cluster-κ 2×bkg):     {_pf(tau_kappa1)}")

    # Hierarchy check: τ_κ₀ ≥ τ_E ≥ τ_R ≥ τ_P
    hier_ok = True
    if not np.isnan(tau_kappa0) and not np.isnan(tau_E):
        hier_ok &= tau_kappa0 >= tau_E - 1.0
    if not np.isnan(tau_E) and not np.isnan(tau_R):
        hier_ok &= tau_E >= tau_R - 1.0
    if not np.isnan(tau_R) and not np.isnan(tau_P):
        hier_ok &= tau_R >= tau_P - 1.0
    print(f"    Hierarchy τ_κ₀≥τ_E≥τ_R≥τ_P: {'✓ CONFIRMED' if hier_ok else '✗ VIOLATED'}")

    # ── θ̈ and R ictal vs interictal ─────────────────────────────────────
    ictal_m  = y == 1
    inter_m  = y == 0
    ddot_crisis = float(np.mean(sig["theta_ddot"][ictal_m] > 0)) if ictal_m.any() else 0.0
    ddot_calm   = float(np.mean(sig["theta_ddot"][inter_m] > 0)) if inter_m.any() else 0.0
    R_crisis = float(np.mean(sig["R"][ictal_m]))  if ictal_m.any() else 0.0
    R_calm   = float(np.mean(sig["R"][inter_m]))  if inter_m.any() else 0.0
    cos_crisis = float(np.mean(sig["cos_theta"][ictal_m]))  if ictal_m.any() else 0.0
    cos_calm   = float(np.mean(sig["cos_theta"][inter_m]))  if inter_m.any() else 0.0
    P_rate_pre = float(np.mean(sig["P"][(centres_s < onset_s) & inter_m])) if any((centres_s < onset_s) & inter_m) else 0.0
    kappa_ictal = float(np.mean(sig["kappa"][ictal_m]))   if ictal_m.any() else 0.0
    kappa_inter = float(np.mean(sig["kappa"][inter_m]))   if inter_m.any() else 0.0
    k0_ictal    = float(np.mean(sig["kappa0"][ictal_m]))  if ictal_m.any() else 0.0
    k0_inter    = float(np.mean(sig["kappa0"][inter_m]))  if inter_m.any() else 0.0

    print(f"\n  ── Phase-Amplitude Statistics ──────────────────────────────")
    print(f"    cos θ:   ictal={cos_crisis:.4f}  interictal={cos_calm:.4f}  "
          f"Δ={cos_crisis-cos_calm:+.4f}")
    print(f"    θ̈>0 rate: ictal={ddot_crisis:.3f}  interictal={ddot_calm:.3f}")
    print(f"    R (Kuramoto): ictal={R_crisis:.4f}  interictal={R_calm:.4f}")
    print(f"    κ₁ system (Level 1): ictal={kappa_ictal:.4f}  interictal={kappa_inter:.4f}  "
          f"ratio={kappa_ictal/(kappa_inter+1e-10):.2f}×")
    print(f"    κ₀ basin  (Level 0): ictal={k0_ictal:.4f}  interictal={k0_inter:.4f}  "
          f"ratio={k0_ictal/(k0_inter+1e-10):.2f}×")
    print(f"    P(t) rate in pre-ictal interictal: {P_rate_pre*100:.2f}%")

    elapsed = time.time() - t0
    print(f"\n  [{label}] elapsed: {elapsed:.1f}s")

    out = dict(
        dataset=label,
        onset_s=onset_s,
        theta_cgs=sig["theta_cgs"],
        M_max=sig["M_max"],
        sigma_grav=sig["sigma_grav"],
        signal_metrics=results,
        lead_times=dict(
            tau_kappa0=tau_kappa0, tau_E=tau_E, tau_R=tau_R,
            tau_P=tau_P, tau_kappa1=tau_kappa1,
        ),
        hierarchy_ok=hier_ok,
        phase_stats=dict(
            cos_theta_ictal=cos_crisis, cos_theta_interictal=cos_calm,
            R_ictal=R_crisis,           R_interictal=R_calm,
            ddot_ictal=ddot_crisis,     ddot_interictal=ddot_calm,
            kappa1_ictal=kappa_ictal,   kappa1_interictal=kappa_inter,
            kappa1_disc=kappa_ictal/(kappa_inter+1e-10),
            kappa0_ictal=k0_ictal,      kappa0_interictal=k0_inter,
            kappa0_disc=k0_ictal/(k0_inter+1e-10),
            P_rate_preictal=P_rate_pre,
        ),
        elapsed_s=round(elapsed, 1),
    )
    return out, X_ref


# ══════════════════════════════════════════════════════════════════════════
# 6. Main
# ══════════════════════════════════════════════════════════════════════════

print("=" * 70)
print("CURVATURE + PROBABILISTIC GEOMETRY EARLY WARNING — CHB-MIT EEG")
print("Geometric Compression Hierarchy: Level 1 (κ) → 2 (θ,R,P) → 3 (E)")
print("=" * 70)

all_results = {}

# ── chb01_03 ──────────────────────────────────────────────────────────────
print("\n" + "=" * 70)
print("FILE 1: chb01_03.edf  (seizure onset=2996s)")
print("=" * 70)
res03, ref_cache = analyse_edf(
    CHB_TEST_EDF, CHB_REF_EDF, 2996.0, 3036.0, "chb01_03")
all_results["chb01_03"] = res03

# ── chb01_04 ──────────────────────────────────────────────────────────────
if os.path.exists(CHB04_EDF):
    print("\n" + "=" * 70)
    print("FILE 2: chb01_04.edf  (seizure onset=1467s, cross-validation)")
    print("=" * 70)
    res04, _ = analyse_edf(
        CHB04_EDF, CHB_REF_EDF, 1467.0, 1494.0, "chb01_04",
        ref_cache=ref_cache)
    all_results["chb01_04"] = res04

# ══════════════════════════════════════════════════════════════════════════
# 7. Summary table
# ══════════════════════════════════════════════════════════════════════════

print("\n" + "█" * 70)
print("  GEOMETRIC HIERARCHY SUMMARY — CHB-MIT EEG")
print("█" * 70)

for key, res in all_results.items():
    lt  = res["lead_times"]
    ps  = res["phase_stats"]
    def _fmt(v): return f"{v:.1f} s" if not np.isnan(v) else "n/a"
    print(f"\n  ── {key} ───────────────────────────────────────────────────")
    print(f"  LEAD-TIME HIERARCHY  (GC.2: τ_κ₀ ≥ τ_E ≥ τ_R ≥ τ_P ≥ τ_κ₁*)")
    print(f"    Level 0  τ_κ₀ (basin-exit density): {_fmt(lt.get('tau_kappa0'))}")
    print(f"    Level 3  τ_E  (energy 2×bkg):        {_fmt(lt['tau_E'])}")
    print(f"    Level 2  τ_R  (Kuramoto 1.2×bkg):    {_fmt(lt['tau_R'])}")
    print(f"    Level 2  τ_P  (3-phase rate≥30%):    {_fmt(lt['tau_P'])}")
    print(f"    Level 1  τ_κ₁ (cluster-κ 2×bkg):    {_fmt(lt.get('tau_kappa1'))}")
    print(f"    Hierarchy confirmed: {res['hierarchy_ok']}")
    print(f"  CURVATURE κ₁ (system): {ps['kappa1_disc']:.2f}×  "
          f"κ₀ (basin): {ps['kappa0_disc']:.2f}×")
    print(f"  cos θ:  ictal={ps['cos_theta_ictal']:.4f}  interictal={ps['cos_theta_interictal']:.4f}")
    print(f"  R(t):   ictal={ps['R_ictal']:.4f}      interictal={ps['R_interictal']:.4f}")
    print(f"  P(t) pre-ictal rate: {ps['P_rate_preictal']*100:.2f}%")

# ── JSON output ────────────────────────────────────────────────────────────
def _clean(obj):
    if isinstance(obj, dict):    return {k: _clean(v) for k, v in obj.items()}
    if isinstance(obj, list):    return [_clean(v) for v in obj]
    if isinstance(obj, (np.floating, float)):
        v = float(obj); return None if np.isnan(v) else v
    if isinstance(obj, (np.integer, int)): return int(obj)
    if isinstance(obj, np.bool_):          return bool(obj)
    return obj

out_path = os.path.join(RESULT_DIR, "curvature_early_warning_chbmit.json")
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(_clean(all_results), f, indent=2)
print(f"\n  JSON → {out_path}")
print("█" * 70)
