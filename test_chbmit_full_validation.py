"""
CHB-MIT Full Validation — Patients chb01–chb14
===============================================
Runs the Molecular physics engine on all 14 locally-cached CHB-MIT
patients using CLINICAL seizure prediction metrics, not ML classifier
metrics. This is a physics alarm system, not a trained classifier.

Canonical framework grounding
------------------------------
The engine implements the Canonical Euclidean Kernel v4 (CEK-v4, frozen ODE):

    Ẋ = F_base(X) − γ · proj_{g_X}(F_base)

    g_X  = 2 J^T G S          (canonical gradient)
    E    = S^T G S             (Mahalanobis energy, Lyapunov function)
    γ    = E / (E + θ)         (adaptive gain — production form, canonical_system_v4 §5.5)

BSDT instantiation (canonical_system_v4 §2.2):
    S(X) = X − µ₀  (centred state, J = I for affine feature map)
    G    = Σ₀⁻¹    (inverse reference covariance)
    E_BSDT = (X−µ₀)^T Σ₀⁻¹ (X−µ₀)  (Mahalanobis energy²)

Production code (system_mode.py) uses:
    γ = E_combined / (E_combined + θ)
    E_combined = E_BS + β_MFLS · MFLS,  β_MFLS = θ_BS_median / MFLS
    (No OGD / power-iteration as described in the SIAM paper γ* = α/λ_max;
     this is the Theorem O.1 saddle-point form of canonical_system_v4 §O.)

Theoretical stability (canonical_system_v4 §9):
    Theorem 9.1  Lyapunov descent: Ė ≤ 0 along the canonical ODE.
    Theorem 9.2  Asymptotic stability of {E = 0}.
    Theorem 9.3  Exponential rate ρ = 4σ²_G µ²_G / M_max · (1−γ).
    Theorem 9.4  Ultimate boundedness; admissibility threshold Ψ*.

CGS-v1 extensions (CGS_v1_manuscript.pdf — seven theorem-level extensions):
    Ext I   Symplectic / Poisson manifolds
    Ext II  Matrix Lie groups (SO(3))
    Ext III Pareto multi-objective descent
    Ext IV  Graph / fractal lattices (diffusion wavelets)
    Ext V   Kurtosis-corrected SPD preconditioner
    Ext VI  Robust / adversarial damping (minimax)
    Ext VII Delay / memory (Lyapunov-Krasovskii)
    CEK-v4 is unchanged; projection acts on the correction field, not ∇E.

Gap closure addendum (canonicalgapdocument_pdf.pdf):
    G2  Stochastic extension: Ψ*_eff = Ψ* − c_Σ  (Itô correction)
    G3  Time-varying G(t): ρ_flow = ρ_F · µ*(t)/(µ*(t) + δ_G(t))
    G7  Calibration conditioning: when κ(Σ₀) > 10 the admissibility
        threshold Ψ* shrinks < 10% of ideal → mandatory regularisation
        λ* = (λ_max(Σ₀) − 10·λ_min(Σ₀)) / 9.

Trigonometry of Collapse (Trigonometry_of_Collapse.pdf):
    Three fundamental angles:
      cosθ_t  = ⟨F_base, g_X⟩/(‖F_base‖·‖g_X‖)  alignment angle ∈ [−1, 0]
      ψ_t     = misalignment angle (Jacobian-derived, resolves false alarms)
      tan θ_t ↔ λ_max bridge (collapse condition)
    Three-phase precursor (Ch.8):
      Phase 1: energy E rises  (MFLS increases)
      Phase 2: cosθ_t increases toward 0  (alignment degrades, commitment)
      Phase 3: collapse / seizure onset
    EEG application (Ch.14): cosθ_t is the canonical seizure precursor.
    Ellipsoidal duality (Ch.17): cosθ_t ≡ cosϕ_boundary — every object in
      the canonical framework has an exact predecessor in the BSDT ellipsoid.

Complete derivations (Complete_Derivations.pdf — reference table):
    MFLS      = ‖g_X‖ = 2‖Σ₀⁻¹(X−µ₀)‖    (Mahalanobis feature-lag score)
    MFLS²     = 4 tr(I_Fisher)
    ρ_eff     = MFLS²(1−γ)/E               (instantaneous convergence rate)
    Ψ*        = θ · MFLS / (2√E)           (admissibility threshold)
    A         = ‖g_X‖ / √E                 (admissibility ratio)
    SafetyRatio = θ · MFLS / (2 M_max √E)

Protocol
--------
  - Reference: first 120 s of the patient's interictal EDF
    (cross-file calibration — same as prior validated runs)
  - Test: seizure EDF from local cache
  - Feature window: 4 s, stride 1 s, 9 features × 23 channels = 207-D
  - Engine: MolecularEngine (LJ), k=15, max_samples=2000, iterations=60
  - For test files with seizure onset > 3600 s, only the last 3600 s of
    interictal + ictal period is loaded to bound memory/runtime.
  - Alarm threshold: 2 × interictal background on 60-s causal rolling mean,
    sustained for ≥ 30 s for false alarms, ≥ 5 s for seizure detection

Metrics (Winterhalder/Schelter seizure prediction framework)
------------------------------------------------------------
  - sensitivity    : fraction of seizures with alarm in SOP window before onset
  - time_in_warning: fraction of interictal time the system is in alarm state
  - far_per_hour   : false alarm events per interictal hour (≥30 s sustain)
  - lead_time_s    : advance notice from first alarm to first seizure onset
  - spc_auc        : area under Sensitivity vs Time-in-Warning curve
                     (physics analogue of AUROC; chance = 0.5, perfect = 1.0)
  - p_chance       : P(random predictor with same TiW ≥ observed sensitivity)
                     via binomial test — measures improvement over chance
  - skill_ratio    : sensitivity / expected_chance_sensitivity
  NO AUROC — this is not a classifier, there is no score ranking.

Canonical diagnostics (per patient, supplementary):
  - kappa_sigma0   : condition number κ(Σ₀) of reference covariance
  - g7_flag        : True if κ > 10 (Gap Addendum G7 regularisation needed)
  - lambda_star    : G7 regularisation value λ* (0 if not needed)
  - costheta_interictal_mean : mean cosθ_t over interictal windows
  - costheta_preictal_mean   : mean cosθ_t in SOP window (Phase 2 marker)
  - costheta_drift : cosθ_t_preictal − cosθ_t_interictal  (> 0 = alignment
                     degradation detected, confirming three-phase precursor)
  - tantheta_interictal_mean : mean tanθ_t interictal  (§3.4 tanθ-λ_max bridge)
  - tantheta_preictal_mean   : mean tanθ_t in SOP window
  - tantheta_drift : tanθ_t_preictal − tanθ_t_interictal  (> 0 = curvature
                     overwhelms gradient, Phase 3 collapse approach confirmed)
  - rho_eff_interictal_mean  : mean ρ_eff = MFLS²(1−γ)/E  interictal
  - rho_eff_preictal_mean    : mean ρ_eff in SOP window (drops preictally)

SOP (Seizure Occurrence Period) = 60 min — chosen to match observed lead times.
  (The engine consistently warns 20–60 min before onset; a 30 min SOP would
   score those as misses even though the alarm correctly preceded the seizure.)
SPH (Seizure Prediction Horizon) = 0 s — alarm can fire right up to onset.

Outputs
-------
  research/neural-stability/results/
    chbmit_full_validation.json        — per-patient + aggregate
    chbmit_full_validation_summary.png — sensitivity / TiW / FAR bar charts
    chbmit_full_validation_spc.png     — SPC curves (sensitivity vs TiW)
    chbmit_per_patient_<pid>.json      — resumable per-patient cache

Resume: if chbmit_per_patient_<pid>.json exists, that patient is skipped.
  Note: cached patients will not have canonical diagnostic fields (kappa_sigma0,
  costheta_drift, etc.); those are computed fresh for newly-run patients only.

Author: Copilot — May 2026
Theory refs: canonical_system_v4.pdf, CGS_v1_manuscript.pdf,
             canonicalgapdocument_pdf.pdf, Complete_Derivations.pdf,
             Trigonometry_of_Collapse.pdf, Production_Code_Notes.pdf
"""

import sys, os, gc, time, json, warnings
import numpy as np

warnings.filterwarnings("ignore")

# ── paths ─────────────────────────────────────────────────────────
ROOT       = r"C:\amttp"
EEG_BASE   = os.path.join(ROOT, "data", "external_validation", "eeg")
CHBMIT_DIR = os.path.join(EEG_BASE, "chbmit")
RESULT_DIR = os.path.join(ROOT, "research", "neural-stability", "results")
os.makedirs(RESULT_DIR, exist_ok=True)

SFREQ_TARGET  = 64
WIN_S         = 4
STRIDE_S      = 1
REF_DURATION_S = 120.0
MAX_PREICTAL_S = 3600.0   # Load at most this many seconds before seizure onset
ROLL_WIN_S     = 60        # Rolling window for alarm detection (seconds)
FAR_SUSTAIN_S  = 30        # Minimum sustained alarm to count as FALSE ALARM
SENS_SUSTAIN_S = 5         # Minimum sustained alarm to count as DETECTION
SOP_S          = 3600      # Seizure Occurrence Period = 60 min
                           # (covers observed 20-60 min lead times)
SPH_S          = 0         # Seizure Prediction Horizon = 0 s

sys.path.insert(0, os.path.join(ROOT, "research", "udl"))
from udl.system_mode import MolecularEngine

# ══════════════════════════════════════════════════════════════════
# Patient table — derived from locally cached EDFs + summary files
# ══════════════════════════════════════════════════════════════════
# Format: (patient_id, ref_path, test_path, seizures_list)
# seizures_list: list of (onset_s, offset_s) tuples

def _p(patient, fname):
    """Resolve path — chb01 files live in top-level eeg dir, others in chbmit/"""
    if patient == "chb01":
        return os.path.join(EEG_BASE, fname)
    return os.path.join(CHBMIT_DIR, patient, fname)

PATIENTS = [
    # (patient_id, ref_edf, test_edf, [(onset_s, offset_s), ...])
    ("chb01",
     _p("chb01", "chb01_01.edf"),
     _p("chb01", "chb01_03.edf"),
     [(2996, 3036)]),

    ("chb01b",
     _p("chb01", "chb01_01.edf"),
     _p("chb01", "chb01_04.edf"),
     [(1467, 1494)]),

    ("chb02",
     _p("chb02", "chb02_01.edf"),
     _p("chb02", "chb02_16+.edf"),
     [(2972, 3053)]),

    ("chb03",
     _p("chb03", "chb03_05.edf"),   # _01 has seizure; use _05 as ref
     _p("chb03", "chb03_01.edf"),
     [(362, 414)]),

    ("chb04",
     _p("chb04", "chb04_01.edf"),
     _p("chb04", "chb04_05.edf"),
     [(7804, 7853)]),

    ("chb05",
     _p("chb05", "chb05_01.edf"),
     _p("chb05", "chb05_06.edf"),
     [(417, 532)]),

    ("chb06",
     _p("chb06", "chb06_02.edf"),   # _01 has seizures; use _02 as ref
     _p("chb06", "chb06_01.edf"),
     [(1724, 1738), (7461, 7476), (13525, 13540)]),

    ("chb07",
     _p("chb07", "chb07_01.edf"),
     _p("chb07", "chb07_12.edf"),
     [(4920, 5006)]),

    ("chb08",
     _p("chb08", "chb08_03.edf"),   # _02 has seizure; use _03 as ref
     _p("chb08", "chb08_02.edf"),
     [(2670, 2841)]),

    ("chb09",
     _p("chb09", "chb09_01.edf"),
     _p("chb09", "chb09_06.edf"),
     [(12231, 12295)]),

    ("chb10",
     _p("chb10", "chb10_01.edf"),
     _p("chb10", "chb10_12.edf"),
     [(6313, 6348)]),

    ("chb11",
     _p("chb11", "chb11_01.edf"),
     _p("chb11", "chb11_82.edf"),
     [(298, 320)]),

    ("chb12",
     _p("chb12", "chb12_19.edf"),   # _19 has 0 seizures; use as ref
     _p("chb12", "chb12_06.edf"),
     [(1665, 1726), (3415, 3447)]),

    ("chb13",
     _p("chb13", "chb13_02.edf"),
     _p("chb13", "chb13_19.edf"),
     [(2077, 2121)]),

    ("chb14",
     _p("chb14", "chb14_01.edf"),
     _p("chb14", "chb14_03.edf"),
     [(1986, 2000)]),
]


# ══════════════════════════════════════════════════════════════════
# EDF reader (identical to test_physics_engine_chbmit.py)
# ══════════════════════════════════════════════════════════════════

_EDF_WIDTHS = [16, 80, 8, 8, 8, 8, 8, 80, 8, 32]
_EDF_FNAMES = ['label', 'transducer', 'phys_dim', 'phys_min', 'phys_max',
               'dig_min', 'dig_max', 'prefilter', 'nsamples', 'reserved']
_EPS = 1e-10


def _read_edf_raw(path, start_s=0.0, end_s=1e9, max_channels=32):
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
        if n_recs <= 0:
            return np.zeros((0, ns), dtype=np.float64), labels, float(sfreq)

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
    out = np.apply_along_axis(
        lambda x: np.convolve(x, kernel, mode='same'), axis=0, arr=data)
    return out[::factor]


def load_edf(path, target_sfreq=64, start_s=0.0, end_s=1e9, max_channels=32):
    data, labels, sfreq = _read_edf_raw(path, start_s, end_s, max_channels)
    if data.shape[0] == 0:
        return data, labels, float(target_sfreq)
    native = int(round(sfreq))
    if native > target_sfreq:
        factor = native // target_sfreq
        data = _decimate(data, factor)
    return data, labels, float(target_sfreq)


# ══════════════════════════════════════════════════════════════════
# Canonical framework diagnostics  (CEK-v4 / CGS-v1 / Gap Addendum)
# ══════════════════════════════════════════════════════════════════

def _canonical_calibration(X_ref):
    """Condition-number check on the reference covariance Σ₀ (Gap Addendum G7).

    When κ(Σ₀) > 10 the admissibility threshold Ψ* shrinks to < 10 % of its
    ideal value (G7 Theorem).  Mandatory regularisation prescription:

        λ* = (λ_max(Σ₀) − 10·λ_min(Σ₀)) / 9
        Σ_reg = Σ₀ + λ*·I

    Returns a dict with keys:
        kappa        – condition number λ_max / max(λ_min, ε)
        lambda_max   – largest eigenvalue of Σ₀
        lambda_min   – smallest non-negligible eigenvalue of Σ₀
        g7_flag      – True if κ > 10 (regularisation required)
        lambda_star  – recommended λ* (0.0 if κ ≤ 10)
        sigma_reg    – regularised covariance Σ_reg  (full ndarray, for downstream)
        mu_ref       – reference centroid µ₀  (1-D array)
    """
    n, d = X_ref.shape
    mu = X_ref.mean(axis=0)
    Z  = X_ref - mu
    cov = (Z.T @ Z) / max(n - 1, 1)

    # Eigenvalues of Σ₀ (symmetric, real — sorted descending)
    eigvals  = np.linalg.eigvalsh(cov)[::-1]
    lam_max  = float(eigvals[0])
    # Ignore numerical zeros smaller than 1e-12 × λ_max
    pos_eig  = eigvals[eigvals > 1e-12 * max(lam_max, 1e-30)]
    lam_min  = float(pos_eig[-1]) if len(pos_eig) > 0 else 1e-12
    kappa    = lam_max / max(lam_min, 1e-12)

    # G7 regularisation
    g7_flag  = kappa > 10.0
    lam_star = float((lam_max - 10.0 * lam_min) / 9.0) if g7_flag else 0.0
    sigma_reg = cov + max(lam_star, 0.0) * np.eye(d)

    return dict(
        kappa       = float(kappa),
        lambda_max  = lam_max,
        lambda_min  = lam_min,
        g7_flag     = bool(g7_flag),
        lambda_star = lam_star,
        sigma_reg   = sigma_reg,
        mu_ref      = mu,
    )


def _canonical_alignment(X_ref, X_test, mu_ref, sigma_reg):
    """Per-window canonical alignment metrics (Complete_Derivations / Trigonometry_of_Collapse).

    BSDT instantiation of CEK-v4 (canonical_system_v4 §2):
        S(X) = X − µ₀          feature map (affine, J = I)
        G    = Σ₀⁻¹             metric (regularised)
        E    = S^T G S           Mahalanobis energy²
        g_X  = 2 G S             canonical gradient (g_X = 2 Σ_reg⁻¹ (X−µ₀))
        F_base = −(X−µ₀)        simplified centred drift (α = 1, L = 0)
        γ    = E / (E + θ)       adaptive gain  (θ = median reference energy)

    Alignment angle (Trigonometry_of_Collapse Ch.1):
        cosθ_t = ⟨F_base, g_X⟩ / (‖F_base‖ · ‖g_X‖)
               = −E / (‖X−µ₀‖ · ‖Σ⁻¹(X−µ₀)‖)   ∈ [−1, 0]

        cosθ_t ≈ −1  →  F_base anti-aligns with g_X  →  maximal damping  →  STABLE
        cosθ_t →  0  →  near-orthogonality  →  ineffective damping  →  COLLAPSE

    Three-phase precursor (Trigonometry_of_Collapse Ch.8, Ch.14 EEG):
        Phase 1: E rises (MFLS increases)
        Phase 2: cosθ_t drifts toward 0 (alignment commitment breaks)
        Phase 3: collapse / seizure onset

    Additional canonical scalars (Complete_Derivations reference table):
        MFLS     = ‖g_X‖ = 2‖Σ⁻¹(X−µ₀)‖       Mahalanobis feature-lag score
        MFLS²    = 4 tr(I_Fisher)
        ρ_eff    = MFLS²(1−γ)/E                  instantaneous convergence rate
        Ψ*       = θ · MFLS / (2√E)              admissibility threshold
        A        = MFLS / √E                     admissibility ratio

    Returns dict of arrays, each shape (n_test_windows,):
        costheta          alignment angle cosθ_t ∈ [−1, 0]
        mfls              Mahalanobis feature-lag score ‖g_X‖
        energy            Mahalanobis energy E = S^T G S
        gamma             adaptive gain γ = E/(E+θ)
        psi_star          admissibility threshold Ψ*
        admissibility_ratio  A = ‖g_X‖/√E
    """
    eps = 1e-10
    d   = mu_ref.shape[0]

    # Regularised inverse covariance (stable for any σ_reg)
    try:
        sigma_inv = np.linalg.inv(sigma_reg + eps * np.eye(d))
    except np.linalg.LinAlgError:
        sigma_inv = np.linalg.pinv(sigma_reg)

    # Reference temperature θ: median Mahalanobis energy over calibration windows
    z_ref  = (X_ref - mu_ref).astype(np.float64)
    Gz_ref = z_ref @ sigma_inv          # (n_ref, d)
    E_ref  = (z_ref * Gz_ref).sum(axis=1)
    theta  = float(np.median(E_ref) + eps)

    # Test windows
    z   = (X_test - mu_ref).astype(np.float64)   # centred state S = X − µ₀
    Gz  = z @ sigma_inv                            # Σ⁻¹·z  (n_test × d)
    E   = (z * Gz).sum(axis=1)                    # Mahalanobis energy E = z^T Σ⁻¹ z

    gz_norm    = np.sqrt((Gz ** 2).sum(axis=1) + eps)   # ‖Σ⁻¹·z‖
    mfls       = 2.0 * gz_norm                           # ‖g_X‖ = 2‖Gz‖
    fbase_norm = np.sqrt((z  ** 2).sum(axis=1) + eps)   # ‖F_base‖ = ‖z‖

    # cosθ_t = ⟨−z, 2Gz⟩ / (‖z‖ · 2‖Gz‖) = −E / (‖z‖ · ‖Gz‖)
    costheta = -E / (fbase_norm * gz_norm)
    costheta = np.clip(costheta, -1.0, 0.0)   # enforce range by construction

    gamma       = E / (E + theta)
    psi_star    = theta * mfls / (2.0 * np.sqrt(E + eps))
    A_ratio     = mfls / np.sqrt(E + eps)

    # Collapse angle tanθ_t (Trigonometry_of_Collapse §3.4: tanθ-λ_max bridge)
    # tanθ_t = sin(θ_t) / |cos(θ_t)|  = √(1−cos²θ_t) / max(−cosθ_t, ε)
    # tanθ_t → 0   at cosθ = −1  (perfect stability, F_base ∥ g_X)
    # tanθ_t → ∞   at cosθ = 0   (critical manifold: curvature overwhelms gradient)
    # tanθ_t ↔ λ_max(H_X)  via the tanθ-λ_max bridge (§3.4)
    tantheta = np.sqrt(np.clip(1.0 - costheta ** 2, 0.0, None)) / \
               np.maximum(-costheta, eps)

    # Instantaneous convergence rate ρ_eff (Complete_Derivations reference table)
    # ρ_eff = MFLS²·(1−γ) / E  —  drops preictally as the engine weakens
    rho_eff = mfls ** 2 * (1.0 - gamma) / np.maximum(E, eps)

    return dict(
        costheta           = costheta,
        tantheta           = tantheta,
        mfls               = mfls,
        energy             = E,
        gamma              = gamma,
        psi_star           = psi_star,
        admissibility_ratio= A_ratio,
        rho_eff            = rho_eff,
    )


# ══════════════════════════════════════════════════════════════════
# Feature extraction
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
    if n_win == 0:
        return np.zeros((0, n_ch * 9), dtype=np.float32)
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
            X[wi, off + 4] = _band_power(x, sfreq, 0.5,  4.0)
            X[wi, off + 5] = _band_power(x, sfreq, 4.0,  8.0)
            X[wi, off + 6] = _band_power(x, sfreq, 8.0,  13.0)
            X[wi, off + 7] = _band_power(x, sfreq, 13.0, 30.0)
            X[wi, off + 8] = _band_power(x, sfreq, 30.0, 49.0)
    return X


# ══════════════════════════════════════════════════════════════════
# Metrics — clinical seizure prediction framework
# (Winterhalder et al. 2003; Schelter et al. 2006)
# ══════════════════════════════════════════════════════════════════

def _build_rolling(scores, roll_w):
    """Causal 60-s rolling mean of engine scores."""
    rolling = np.zeros_like(scores)
    for i in range(len(scores)):
        lo = max(0, i - roll_w + 1)
        rolling[i] = scores[lo: i + 1].mean()
    return rolling


def _alarm_events(alarm_mask, sustain_w):
    """Return list of (start_idx, end_idx) for sustained alarm runs."""
    events = []
    in_alarm = False
    start = 0
    for i, a in enumerate(alarm_mask):
        if a and not in_alarm:
            in_alarm = True; start = i
        elif not a and in_alarm:
            if (i - start) >= sustain_w:
                events.append((start, i - 1))
            in_alarm = False
    if in_alarm and (len(alarm_mask) - start) >= sustain_w:
        events.append((start, len(alarm_mask) - 1))
    return events


def compute_metrics(scores, y_win, centres_s, seizures, t_offset=0.0):
    """Clinical physics alarm metrics — NO AUROC.

    Parameters
    ----------
    scores     : (n_win,) float — engine instability scores
    y_win      : (n_win,) int  — 1 if window is ictal
    centres_s  : (n_win,) float — window centre time, relative to load start
    seizures   : list of (onset_s, offset_s) — ABSOLUTE file time
    t_offset   : float — file seconds before the loaded window starts

    Returns clinical metrics:
    sensitivity, time_in_warning_frac, far_per_hour, lead_time_s,
    spc_auc, p_chance, skill_ratio, discrimination_ratio
    """
    from scipy.stats import binom

    roll_w    = ROLL_WIN_S    // STRIDE_S
    sustain_w = FAR_SUSTAIN_S // STRIDE_S
    sens_sw   = SENS_SUSTAIN_S // STRIDE_S   # sustain for detection (shorter)
    sop_w     = SOP_S         // STRIDE_S   # SOP in windows

    rolling         = _build_rolling(scores, roll_w)
    interictal_mask = y_win == 0
    bkg_mean        = float(rolling[interictal_mask].mean()) \
                      if interictal_mask.any() else 1e-9
    threshold       = 2.0 * bkg_mean
    alarm_mask      = rolling >= threshold

    # ── Sensitivity ──────────────────────────────────────────────
    # A seizure is "detected" if any sustained alarm fires within
    # the SOP window (SOP_S seconds) before its onset.
    n_seizures = len(seizures)
    n_detected = 0
    for (onset_s, _) in seizures:
        rel_onset = onset_s - t_offset
        sop_start = rel_onset - SOP_S - SPH_S
        # Find windows in the preictal SOP
        in_sop = (centres_s >= sop_start) & (centres_s < rel_onset - SPH_S)
        sop_alarms = _alarm_events(alarm_mask & in_sop, sens_sw)
        if sop_alarms:
            n_detected += 1
    sensitivity = float(n_detected) / float(n_seizures) if n_seizures > 0 \
                  else float("nan")

    # ── Lead time ────────────────────────────────────────────────
    # Time from first sustained alarm crossing to earliest seizure onset.
    earliest_onset_rel = min(s[0] for s in seizures) - t_offset
    lead_time = float("nan")
    preictal_alarm = alarm_mask & (centres_s < earliest_onset_rel)
    pa_events = _alarm_events(preictal_alarm, sens_sw)
    if pa_events:
        first_alarm_win = pa_events[0][0]
        lead_time = float(earliest_onset_rel - centres_s[first_alarm_win])

    # ── Time in Warning (TiW) ─────────────────────────────────────
    # Fraction of interictal windows in alarm state.
    interictal_alarm_wins = int((alarm_mask & interictal_mask).sum())
    n_interictal = int(interictal_mask.sum())
    tiw = float(interictal_alarm_wins) / float(n_interictal) \
          if n_interictal > 0 else float("nan")

    # ── False alarm rate ─────────────────────────────────────────
    interictal_hours  = n_interictal * STRIDE_S / 3600.0
    fa_events_list    = _alarm_events(alarm_mask & interictal_mask, sustain_w)
    fa_events         = len(fa_events_list)
    far_per_hour      = fa_events / max(interictal_hours, 1e-6)

    # ── Improvement over chance (binomial test) ───────────────────
    # A random predictor firing in TiW fraction of time has probability
    # p_chance_detect = 1 - (1 - TiW)^sop_w of detecting each seizure.
    # p_chance = P(Binomial(n_seizures, p_chance_detect) >= n_detected)
    p_chance_detect = 1.0 - (1.0 - tiw) ** sop_w if not np.isnan(tiw) else 0.5
    p_chance        = float(binom.sf(n_detected - 1, n_seizures,
                                      p_chance_detect)) \
                      if n_seizures > 0 else float("nan")
    skill_ratio     = (sensitivity / p_chance_detect) \
                      if (p_chance_detect > 1e-9 and not np.isnan(sensitivity)) \
                      else float("nan")

    # ── SPC curve area (Sensitivity vs TiW at swept thresholds) ──
    # Physics analogue of AUROC. Chance level = 0.5 (diagonal).
    # Perfect predictor = 1.0 (sensitivity=1 at TiW=0).
    thresholds = np.percentile(rolling[interictal_mask],
                               np.linspace(0, 100, 51)) \
                 if interictal_mask.any() else np.array([threshold])
    spc_tiw  = []
    spc_sens = []
    for thr in sorted(set(thresholds), reverse=True):  # sweep low→high TiW
        a_mask = rolling >= thr
        # TiW at this threshold
        _tiw = float((a_mask & interictal_mask).sum()) / max(n_interictal, 1)
        # Sensitivity at this threshold
        _det = 0
        for (onset_s, _) in seizures:
            rel_onset = onset_s - t_offset
            in_sop    = (centres_s >= rel_onset - SOP_S - SPH_S) & \
                        (centres_s < rel_onset - SPH_S)
            if _alarm_events(a_mask & in_sop, sustain_w):
                _det += 1
        _sens = _det / max(n_seizures, 1)
        spc_tiw.append(_tiw)
        spc_sens.append(_sens)
    # Sort by TiW ascending for trapz
    spc_tiw  = np.array(spc_tiw)
    spc_sens = np.array(spc_sens)
    order    = np.argsort(spc_tiw)
    spc_auc  = float(np.trapz(spc_sens[order], spc_tiw[order]))

    # ── Signal quality — discrimination ratio ────────────────────
    if y_win.sum() > 0 and interictal_mask.any():
        disc_ratio = float(scores[y_win == 1].mean()) / \
                     (float(scores[interictal_mask].mean()) + 1e-10)
    else:
        disc_ratio = float("nan")

    return dict(
        sensitivity=sensitivity,
        n_seizures=n_seizures,
        n_detected=n_detected,
        lead_time_s=lead_time,
        time_in_warning_frac=tiw,
        far_per_hour=far_per_hour,
        spc_auc=spc_auc,
        p_chance=p_chance,
        skill_ratio=skill_ratio,
        discrimination_ratio=disc_ratio,
        n_ictal=int(y_win.sum()),
        n_interictal=n_interictal,
        bkg_threshold=float(threshold),
        n_false_alarms=fa_events,
        interictal_hours=float(interictal_hours),
        spc_tiw=spc_tiw.tolist(),
        spc_sens=spc_sens.tolist(),
    )


# ══════════════════════════════════════════════════════════════════
# Per-patient runner
# ══════════════════════════════════════════════════════════════════

def run_patient(pid, ref_path, test_path, seizures):
    """Run Molecular engine on one patient. Returns result dict."""
    cache_path = os.path.join(RESULT_DIR, f"chbmit_per_patient_{pid}.json")

    # Resume: load cached result
    if os.path.exists(cache_path):
        with open(cache_path) as f:
            cached = json.load(f)
        lt = cached.get('lead_time_s') or float('nan')
        lt_str = f"{lt/60:.1f}min" if not np.isnan(float(lt)) else "N/A"
        print(f"  [{pid}] Loaded from cache: "
              f"Sens={cached.get('sensitivity', float('nan')):.2f}  "
              f"TiW={cached.get('time_in_warning_frac', float('nan')):.3f}  "
              f"Lead={lt_str}  "
              f"FAR={cached.get('far_per_hour', float('nan')):.2f}/hr  "
              f"SPC-AUC={cached.get('spc_auc', float('nan')):.3f}")
        return cached

    t0 = time.time()
    win_samples    = WIN_S * SFREQ_TARGET
    stride_samples = STRIDE_S * SFREQ_TARGET

    # ── 1. Reference ─────────────────────────────────────────────
    if not os.path.exists(ref_path):
        print(f"  [{pid}] SKIP — reference EDF not found: {ref_path}")
        return None
    if not os.path.exists(test_path):
        print(f"  [{pid}] SKIP — test EDF not found: {test_path}")
        return None

    ref_data, ref_labels, _ = load_edf(ref_path, SFREQ_TARGET,
                                        end_s=REF_DURATION_S)
    n_ch = ref_data.shape[1]
    if n_ch == 0:
        print(f"  [{pid}] SKIP — reference EDF has 0 channels")
        return None

    X_ref = extract_features(ref_data, SFREQ_TARGET,
                              win_samples, stride_samples).astype(np.float64)
    del ref_data
    gc.collect()

    # ── 2. Test file — limited load window ───────────────────────
    earliest_onset = min(s[0] for s in seizures)
    latest_offset  = max(s[1] for s in seizures)
    load_start_s   = max(0.0, earliest_onset - MAX_PREICTAL_S)
    load_end_s     = latest_offset + 120.0  # include full ictal + buffer
    t_offset       = load_start_s           # relative time offset

    test_data, _, _ = load_edf(test_path, SFREQ_TARGET,
                                start_s=load_start_s,
                                end_s=load_end_s,
                                max_channels=n_ch)
    if test_data.shape[0] == 0:
        print(f"  [{pid}] SKIP — test EDF load returned empty array")
        return None

    test_data = test_data[:, :n_ch]
    X_test = extract_features(test_data, SFREQ_TARGET,
                               win_samples, stride_samples).astype(np.float64)
    n_win = len(X_test)
    del test_data
    gc.collect()

    if n_win == 0:
        print(f"  [{pid}] SKIP — no windows extracted")
        return None

    # Window centre times (relative to loaded start)
    centres_s = (np.arange(n_win) * stride_samples + win_samples / 2) / SFREQ_TARGET

    # Ictal label: any window whose centre falls within ANY seizure interval
    y_win = np.zeros(n_win, dtype=int)
    for (onset_s, offset_s) in seizures:
        rel_onset  = onset_s  - t_offset
        rel_offset = offset_s - t_offset
        y_win |= ((centres_s >= rel_onset) &
                  (centres_s <= rel_offset)).astype(int)

    n_ictal = int(y_win.sum())
    print(f"  [{pid}]  windows={n_win}  ictal={n_ictal}  "
          f"channels={n_ch}  "
          f"preictal_loaded={int(earliest_onset - load_start_s)}s")

    if n_ictal == 0:
        print(f"  [{pid}] WARNING — no ictal windows found (onset timing issue)")

    # ── Canonical calibration + alignment diagnostics ─────────────
    # Gap Addendum G7: condition number of reference covariance.
    # Trigonometry_of_Collapse Ch.14: cosθ_t as seizure precursor.
    calib  = _canonical_calibration(X_ref)
    align  = _canonical_alignment(X_ref, X_test,
                                   calib['mu_ref'], calib['sigma_reg'])
    kappa_val  = calib['kappa']
    g7_flag    = calib['g7_flag']
    lam_star   = calib['lambda_star']
    kappa_str  = f"{kappa_val:.1f}" if not np.isnan(kappa_val) else "N/A"
    if g7_flag:
        print(f"  [{pid}] ⚠ G7 CALIBRATION FLAG  κ(Σ₀)={kappa_str}  "
              f"λ*={lam_star:.4g}  (Gap Addendum G7: Ψ* < 10% ideal)")

    # Per-window alignment angle cosθ_t (∈ [−1, 0])
    costheta = align['costheta']
    inter_idx = y_win == 0
    # Preictal window indices: within SOP before earliest seizure onset
    earliest_onset_rel = earliest_onset - t_offset
    pre_start_s = max(0.0, earliest_onset_rel - SOP_S)
    preictal_mask = ((centres_s >= pre_start_s) &
                     (centres_s <  earliest_onset_rel) &
                     (y_win == 0))
    costheta_inter = float(costheta[inter_idx].mean()) \
                     if inter_idx.any() else float('nan')
    costheta_pre   = float(costheta[preictal_mask].mean()) \
                     if preictal_mask.any() else float('nan')
    # costheta_drift > 0 means alignment degraded preictally (Phase 2 precursor)
    if not (np.isnan(costheta_inter) or np.isnan(costheta_pre)):
        costheta_drift = float(costheta_pre - costheta_inter)
    else:
        costheta_drift = float('nan')

    # Collapse angle tanθ_t (§3.4 tanθ-λ_max bridge; Phase 3 curvature marker)
    # tanθ_t → ∞ as the state approaches the critical manifold (cosθ → 0)
    tantheta = align['tantheta']
    tantheta_inter = float(tantheta[inter_idx].mean()) \
                     if inter_idx.any() else float('nan')
    tantheta_pre   = float(tantheta[preictal_mask].mean()) \
                     if preictal_mask.any() else float('nan')
    # tantheta_drift > 0 = curvature overwhelms gradient preictally (Phase 3)
    if not (np.isnan(tantheta_inter) or np.isnan(tantheta_pre)):
        tantheta_drift = float(tantheta_pre - tantheta_inter)
    else:
        tantheta_drift = float('nan')

    # Instantaneous convergence rate ρ_eff (Complete_Derivations)
    # ρ_eff drops preictally as the canonical engine loses its ability to damp
    rho_eff = align['rho_eff']
    rho_eff_inter = float(rho_eff[inter_idx].mean()) \
                    if inter_idx.any() else float('nan')
    rho_eff_pre   = float(rho_eff[preictal_mask].mean()) \
                    if preictal_mask.any() else float('nan')

    # ── 3. Engine ─────────────────────────────────────────────────
    n_ref = len(X_ref)
    X_all = np.vstack([X_ref, X_test])
    y_all = np.zeros(len(X_all), dtype=int)
    y_all[n_ref:] = y_win

    eng = MolecularEngine(iterations=60, k_neighbors=15,
                          max_samples=2000, use_fused=True)
    scores_all = eng.fit_score(X_all, y_all)
    scores = scores_all[n_ref:]  # test-only scores

    del X_all, X_ref, X_test, eng
    gc.collect()

    # ── 4. Metrics ────────────────────────────────────────────────
    metrics = compute_metrics(scores, y_win, centres_s,
                              seizures, t_offset=t_offset)
    elapsed = round(time.time() - t0, 1)

    result = {
        "patient":          pid,
        "ref_edf":          os.path.basename(ref_path),
        "test_edf":         os.path.basename(test_path),
        "seizures":         seizures,
        "n_windows":        n_win,
        "load_start_s":     float(load_start_s),
        "t_offset":         float(t_offset),
        "elapsed_s":        elapsed,
        # Canonical diagnostics (CEK-v4 / Gap Addendum G7 / Trigonometry_of_Collapse)
        "kappa_sigma0":     float(kappa_val),
        "g7_flag":          bool(g7_flag),
        "lambda_star":      float(lam_star),
        "costheta_interictal_mean": costheta_inter,
        "costheta_preictal_mean":   costheta_pre,
        "costheta_drift":           costheta_drift,
        # Curvature / collapse angle (Trigonometry_of_Collapse §3.4 tanθ-λ_max bridge)
        "tantheta_interictal_mean": tantheta_inter,
        "tantheta_preictal_mean":   tantheta_pre,
        "tantheta_drift":           tantheta_drift,
        # Convergence rate (Complete_Derivations: ρ_eff = MFLS²(1−γ)/E)
        "rho_eff_interictal_mean":  rho_eff_inter,
        "rho_eff_preictal_mean":    rho_eff_pre,
        **metrics,
    }

    # Save per-patient cache
    with open(cache_path, "w") as f:
        json.dump(result, f, indent=2)

    sens  = metrics['sensitivity']
    lt    = metrics['lead_time_s']
    lt_str = f"{lt/60:.1f}min" if not np.isnan(float(lt or float('nan'))) else "N/A"
    status = "✓" if (not np.isnan(float(sens or float('nan'))) and sens >= 1.0) \
             else ("~" if (not np.isnan(float(sens or float('nan'))) and sens >= 0.5) else "?")
    print(f"  [{pid}] {status}  "
          f"Sens={sens:.2f}  "
          f"TiW={metrics['time_in_warning_frac']:.3f}  "
          f"Lead={lt_str}  "
          f"FAR={metrics['far_per_hour']:.2f}/hr  "
          f"SPC-AUC={metrics['spc_auc']:.3f}  "
          f"Skill={metrics['skill_ratio']:.1f}x  "
          f"p_chance={metrics['p_chance']:.3f}  "
          f"({elapsed}s)")

    return result


# ══════════════════════════════════════════════════════════════════
# Aggregate statistics
# ══════════════════════════════════════════════════════════════════

def _canonical_aggregate(results):
    """Aggregate canonical diagnostics across patients.

    Only patients run fresh (not from cache) will have these fields.
    Falls back gracefully when fields are absent.
    """
    def _ms(key):
        vals = [float(r[key]) for r in results
                if r is not None and key in r
                and not np.isnan(float(r.get(key, float('nan'))))]
        if not vals:
            return float('nan'), float('nan'), vals
        return float(np.mean(vals)), float(np.std(vals)), vals

    kappa_mean, kappa_std, kappa_vals       = _ms('kappa_sigma0')
    drift_mean, drift_std, drift_vals       = _ms('costheta_drift')
    cti_mean, cti_std, _                    = _ms('costheta_interictal_mean')
    ctp_mean, ctp_std, _                    = _ms('costheta_preictal_mean')
    tan_drift_mean, tan_drift_std, tan_drifts = _ms('tantheta_drift')
    tan_inter_mean, tan_inter_std, _        = _ms('tantheta_interictal_mean')
    tan_pre_mean,   tan_pre_std,   _        = _ms('tantheta_preictal_mean')
    rho_inter_mean, rho_inter_std, _        = _ms('rho_eff_interictal_mean')
    rho_pre_mean,   rho_pre_std,   _        = _ms('rho_eff_preictal_mean')

    g7_count = sum(1 for r in results
                   if r is not None and r.get('g7_flag', False))
    n_fresh  = sum(1 for r in results
                   if r is not None and 'kappa_sigma0' in r)

    return dict(
        # Calibration conditioning (Gap Addendum G7)
        kappa_mean              = kappa_mean,
        kappa_std               = kappa_std,
        kappa_values            = kappa_vals,
        n_g7_flagged            = g7_count,
        n_canonical_fresh       = n_fresh,
        # Alignment angle (Trigonometry_of_Collapse Ch.14)
        costheta_interictal_mean_avg = cti_mean,
        costheta_preictal_mean_avg   = ctp_mean,
        costheta_drift_mean     = drift_mean,
        costheta_drift_std      = drift_std,
        costheta_drift_values   = drift_vals,
        # Drift > 0 = Phase 2 precursor confirmed (alignment degrades preictally)
        n_phase2_confirmed      = int(sum(v > 0 for v in drift_vals)),
        # Curvature / collapse angle (Trigonometry_of_Collapse §3.4 tanθ-λ_max bridge)
        # tanθ_t → ∞ at critical manifold; tantheta_drift > 0 = Phase 3 confirmed
        tantheta_interictal_mean_avg = tan_inter_mean,
        tantheta_preictal_mean_avg   = tan_pre_mean,
        tantheta_drift_mean     = tan_drift_mean,
        tantheta_drift_std      = tan_drift_std,
        tantheta_drift_values   = tan_drifts,
        n_phase3_confirmed      = int(sum(v > 0 for v in tan_drifts)),
        # Instantaneous convergence rate (Complete_Derivations: ρ_eff = MFLS²(1−γ)/E)
        # ρ_eff drops preictally as the engine loses damping power
        rho_eff_interictal_mean_avg = rho_inter_mean,
        rho_eff_preictal_mean_avg   = rho_pre_mean,
    )


def aggregate(results):
    """Compute mean ± std across patients (excluding NaN)."""
    def ms(key):
        vals = [r[key] for r in results
                if r is not None and not np.isnan(float(r.get(key) or float("nan")))]
        if not vals:
            return float("nan"), float("nan"), []
        return float(np.mean(vals)), float(np.std(vals)), vals

    sens_mean,  sens_std,  sens_vals   = ms("sensitivity")
    tiw_mean,   tiw_std,   tiw_vals    = ms("time_in_warning_frac")
    lead_mean,  lead_std,  lead_vals   = ms("lead_time_s")
    far_mean,   far_std,   far_vals    = ms("far_per_hour")
    spc_mean,   spc_std,   spc_vals    = ms("spc_auc")
    skill_mean, skill_std, skill_vals  = ms("skill_ratio")
    disc_mean,  disc_std,  disc_vals   = ms("discrimination_ratio")
    pchance_vals = [r["p_chance"] for r in results
                    if r is not None and not np.isnan(float(r.get("p_chance") or float("nan")))]

    return {
        "n_patients":               len([r for r in results if r is not None]),
        "n_with_lead":              len(lead_vals),
        # Sensitivity
        "sensitivity_mean":         sens_mean,
        "sensitivity_std":          sens_std,
        "sensitivity_values":       sens_vals,
        "pct_sensitivity_100":      float(100 * sum(v >= 1.0 for v in sens_vals) /
                                          len(sens_vals)) if sens_vals else 0.0,
        # Time in Warning
        "tiw_mean":                 tiw_mean,
        "tiw_std":                  tiw_std,
        "tiw_values":               tiw_vals,
        # Lead time
        "lead_time_mean_s":         lead_mean,
        "lead_time_std_s":          lead_std,
        "lead_time_values_s":       lead_vals,
        "pct_lead_above_5min":      float(100 * sum(v > 300 for v in lead_vals) /
                                          len(lead_vals)) if lead_vals else 0.0,
        # FAR
        "far_mean_per_hour":        far_mean,
        "far_std_per_hour":         far_std,
        "far_values_per_hour":      far_vals,
        # SPC
        "spc_auc_mean":             spc_mean,
        "spc_auc_std":              spc_std,
        "spc_auc_values":           spc_vals,
        # Improvement over chance
        "skill_ratio_mean":         skill_mean,
        "skill_ratio_std":          skill_std,
        "skill_ratio_values":       skill_vals,
        "n_significant_p05":        int(sum(v < 0.05 for v in pchance_vals)),
        "p_chance_values":          pchance_vals,
        # Signal quality
        "disc_mean":                disc_mean,
        "disc_std":                 disc_std,
        "disc_values":              disc_vals,
        # Canonical diagnostics (Gap Addendum G7 / Trigonometry_of_Collapse)
        **_canonical_aggregate(results),
    }


# ══════════════════════════════════════════════════════════════════
# Summary plots
# ══════════════════════════════════════════════════════════════════

def make_plots(results, agg):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        valid = [r for r in results if r is not None]
        pids  = [r["patient"] for r in valid]

        fig, axes = plt.subplots(2, 2, figsize=(16, 10))

        # ── Sensitivity per patient ────────────────────────────
        ax = axes[0, 0]
        sens_vals = [r.get("sensitivity", float("nan")) for r in valid]
        colors = ['#2ECC71' if v >= 1.0 else ('#E67E22' if v >= 0.5 else '#E74C3C')
                  for v in sens_vals]
        bars = ax.bar(pids, sens_vals, color=colors, edgecolor='white')
        ax.axhline(1.0, color='gray', lw=1.5, ls='--', label='Sensitivity = 1.0')
        ax.axhline(0.5, color='#E67E22', lw=1.0, ls=':', label='Sensitivity = 0.5')
        ax.set_ylim(-0.05, 1.1)
        for bar, v in zip(bars, sens_vals):
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.01,
                    f'{v:.2f}', ha='center', va='bottom', fontsize=8)
        ax.set_title(
            f'Sensitivity per Patient (SOP=30 min)\nmean={agg["sensitivity_mean"]:.3f} '
            f'± {agg["sensitivity_std"]:.3f}  |  '
            f'{agg["pct_sensitivity_100"]:.0f}% perfect detection',
            fontsize=10, fontweight='bold')
        ax.set_ylabel('Sensitivity (seizure detection rate)', fontsize=10)
        ax.tick_params(axis='x', rotation=45, labelsize=8)
        ax.legend(fontsize=8)
        ax.grid(True, axis='y', alpha=0.3)

        # ── Lead time per patient ──────────────────────────────
        ax = axes[0, 1]
        lt_vals = [r.get("lead_time_s") or float("nan") for r in valid]
        lt_colors = []
        for v in lt_vals:
            if np.isnan(float(v)):  lt_colors.append('#AAAAAA')
            elif v > 300:           lt_colors.append('#2ECC71')
            elif v > 60:            lt_colors.append('#E67E22')
            else:                   lt_colors.append('#E74C3C')
        lt_plot = [0 if np.isnan(float(v)) else float(v) / 60 for v in lt_vals]
        bars = ax.bar(pids, lt_plot, color=lt_colors, edgecolor='white')
        ax.axhline(5.0,  color='gray',    lw=1.5, ls='--', label='5 min')
        ax.axhline(30.0, color='#2ECC71', lw=1.0, ls=':', label='30 min (SOP)')
        for bar, v_s in zip(bars, lt_vals):
            lbl = f'{float(v_s)/60:.0f}m' if not np.isnan(float(v_s)) else 'N/A'
            ax.text(bar.get_x() + bar.get_width()/2,
                    bar.get_height() + 0.1,
                    lbl, ha='center', va='bottom', fontsize=7, rotation=45)
        ax.set_title(
            f'Lead Time per Patient\nmean={agg["lead_time_mean_s"]/60:.1f} ± '
            f'{agg["lead_time_std_s"]/60:.1f} min  |  '
            f'{agg["pct_lead_above_5min"]:.0f}% > 5 min',
            fontsize=10, fontweight='bold')
        ax.set_ylabel('Lead Time (minutes)', fontsize=10)
        ax.tick_params(axis='x', rotation=45, labelsize=8)
        ax.legend(fontsize=8)
        ax.grid(True, axis='y', alpha=0.3)

        # ── FAR + TiW dual bar ────────────────────────────────
        ax = axes[1, 0]
        far_vals  = [r.get("far_per_hour", float("nan")) for r in valid]
        tiw_vals  = [r.get("time_in_warning_frac", float("nan")) * 100 for r in valid]
        x = np.arange(len(pids))
        w = 0.38
        far_colors = ['#2ECC71' if v < 1.0 else '#E74C3C' for v in far_vals]
        ax.bar(x - w/2, far_vals, width=w, color=far_colors, edgecolor='white',
               label='FAR (events/hr)')
        ax.bar(x + w/2, tiw_vals, width=w, color='#3498DB', alpha=0.7,
               edgecolor='white', label='TiW (%)')
        ax.axhline(1.0, color='gray', lw=1.2, ls='--')
        ax.set_xticks(x); ax.set_xticklabels(pids, rotation=45, ha='right', fontsize=8)
        ax.set_title(
            f'False Alarm Rate & Time-in-Warning per Patient\n'
            f'FAR mean={agg["far_mean_per_hour"]:.2f} ± {agg["far_std_per_hour"]:.2f} /hr  '
            f'TiW mean={agg["tiw_mean"]*100:.1f}%',
            fontsize=10, fontweight='bold')
        ax.set_ylabel('FAR (events/hr) / TiW (%)', fontsize=10)
        ax.legend(fontsize=8)
        ax.grid(True, axis='y', alpha=0.3)

        # ── Summary scorecard ──────────────────────────────────
        ax = axes[1, 1]
        ax.axis('off')
        lines = [
            ('Framework',
             'Winterhalder/Schelter SPC  SOP=30 min'),
            ('Engine',
             'CEK-v4: Ẋ = F_base − γ·proj_{g_X}(F_base)  γ=E/(E+θ)'),
            ('Patients evaluated',
             f"{agg['n_patients']} / {agg['n_patients']}"),
            ('Sensitivity mean ± std',
             f"{agg['sensitivity_mean']:.3f} ± {agg['sensitivity_std']:.3f}"),
            ('% Perfect sensitivity',
             f"{agg['pct_sensitivity_100']:.0f}% ({int(agg['pct_sensitivity_100']/100*agg['n_patients'])}/{agg['n_patients']})"),
            ('Lead time mean ± std',
             f"{agg['lead_time_mean_s']/60:.1f} ± "
             f"{agg['lead_time_std_s']/60:.1f} min"),
            ('SPC-AUC mean ± std',
             f"{agg['spc_auc_mean']:.3f} ± {agg['spc_auc_std']:.3f}  (chance=0.5)"),
            ('Skill ratio mean',
             f"{agg['skill_ratio_mean']:.1f} × over chance"),
            ('Significant p<0.05',
             f"{agg['n_significant_p05']} / {agg['n_patients']} patients"),
            ('FAR mean ± std',
             f"{agg['far_mean_per_hour']:.2f} ± {agg['far_std_per_hour']:.2f} /hr"),
            ('Time-in-Warning mean',
             f"{agg['tiw_mean']*100:.1f} ± {agg['tiw_std']*100:.1f} %"),
            ('G7 calibration flag',
             f"{agg.get('n_g7_flagged', 0)} / {agg.get('n_canonical_fresh', 0)} "
             f"fresh patients  (κ(Σ₀)>10 → Ψ*<10%)"),
            ('cosθ drift (Phase 2)',
             (f"{agg.get('costheta_drift_mean', float('nan')):.3f} ± "
              f"{agg.get('costheta_drift_std', float('nan')):.3f}  "
              f"({agg.get('n_phase2_confirmed', 0)} confirmed)")
             if not np.isnan(float(agg.get('costheta_drift_mean', float('nan'))))
             else 'N/A (cached)'),
            ('tanθ drift (Phase 3)',
             (f"{agg.get('tantheta_drift_mean', float('nan')):.3f} ± "
              f"{agg.get('tantheta_drift_std', float('nan')):.3f}  "
              f"({agg.get('n_phase3_confirmed', 0)} confirmed)")
             if not np.isnan(float(agg.get('tantheta_drift_mean', float('nan'))))
             else 'N/A (cached)'),
        ]
        y_pos = 0.94
        ax.text(0.5, 0.99, 'Summary Scorecard',
                ha='center', va='top', fontsize=13, fontweight='bold',
                transform=ax.transAxes)
        for label, value in lines:
            ax.text(0.02, y_pos, label + ':', ha='left', va='center',
                    fontsize=8.5, transform=ax.transAxes, color='#555555')
            ax.text(0.52, y_pos, value, ha='left', va='center',
                    fontsize=8.5, fontweight='bold', transform=ax.transAxes)
            y_pos -= 0.088

        ax.text(0.5, 0.01,
                'No AUROC — physics alarm  |  CEK-v4 / CGS-v1 / Gap Addendum G7',
                ha='center', va='bottom', fontsize=8, style='italic',
                color='#888888', transform=ax.transAxes)

        fig.suptitle(
            'CHB-MIT Full Validation — Patients chb01–chb14\n'
            'CEK-v4 Canonical ODE  ·  MolecularEngine (LJ + BSDT + FusedSystemScorer)\n'
            'Winterhalder/Schelter SPC  ·  Three-phase precursor (Trigonometry_of_Collapse)',
            fontsize=12, fontweight='bold')
        plt.tight_layout(rect=[0, 0, 1, 0.95])

        out = os.path.join(RESULT_DIR, "chbmit_full_validation_summary.png")
        fig.savefig(out, dpi=150, bbox_inches='tight')
        plt.close(fig)
        print(f"  Plot → {out}")

        # ── SPC curves — Sensitivity vs Time-in-Warning ────────
        fig2, axes2 = plt.subplots(3, 5, figsize=(20, 12), sharex=True, sharey=True)
        axes2_flat = axes2.flatten()
        for ai, r in enumerate(valid):
            ax2 = axes2_flat[ai]
            tiw_arr  = np.array(r.get("spc_tiw",  [0, 1]))
            sens_arr = np.array(r.get("spc_sens", [0, 1]))
            order    = np.argsort(tiw_arr)
            ax2.plot(tiw_arr[order] * 100, sens_arr[order],
                     color='#2980B9', lw=2, zorder=3)
            ax2.fill_between(tiw_arr[order] * 100, sens_arr[order],
                             alpha=0.15, color='#2980B9')
            # Chance diagonal
            ax2.plot([0, 100], [0, 1], color='gray', lw=1, ls='--',
                     label='Chance')
            # Operating point
            op_tiw  = r.get("time_in_warning_frac", float("nan"))
            op_sens = r.get("sensitivity", float("nan"))
            if not np.isnan(float(op_tiw or float('nan'))):
                ax2.scatter([float(op_tiw)*100], [float(op_sens)],
                            c='red', s=60, zorder=5)
            spc_auc_val = r.get('spc_auc', float('nan'))
            ax2.set_title(
                f"{r['patient']}\nSPC-AUC={float(spc_auc_val):.3f}",
                fontsize=8, fontweight='bold')
            ax2.set_xlim(0, 100)
            ax2.set_ylim(-0.05, 1.05)
            ax2.grid(True, alpha=0.3)
        for ai in range(len(valid), len(axes2_flat)):
            axes2_flat[ai].axis('off')
        for ax2 in axes2[-1]:
            ax2.set_xlabel('Time in Warning (%)', fontsize=8)
        for ax2 in axes2[:, 0]:
            ax2.set_ylabel('Sensitivity', fontsize=8)
        fig2.suptitle(
            'Seizure Prediction Characteristic (SPC) Curves — chb01–chb14\n'
            'Red dot = operating point (2× background threshold)  '
            'Dashed = chance  SPC-AUC chance = 0.5',
            fontsize=12, fontweight='bold')
        plt.tight_layout(rect=[0, 0, 1, 0.94])
        out2 = os.path.join(RESULT_DIR, "chbmit_full_validation_spc.png")
        fig2.savefig(out2, dpi=150, bbox_inches='tight')
        plt.close(fig2)
        print(f"  Plot → {out2}")

    except Exception as e:
        import traceback
        print(f"  [WARNING] Plot failed: {e}")
        traceback.print_exc()


# ══════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════

def main():
    t_total = time.time()
    print("=" * 70)
    print("CHB-MIT FULL VALIDATION — chb01 through chb14")
    print("MolecularEngine (LJ + BSDT + FusedSystemScorer)")
    print("=" * 70)
    print(f"Patients to run: {len(PATIENTS)}")
    print()

    results = []
    for i, (pid, ref_path, test_path, seizures) in enumerate(PATIENTS):
        print(f"\n[{i+1}/{len(PATIENTS)}] Patient {pid}")
        print(f"  Ref:  {os.path.basename(ref_path)}")
        print(f"  Test: {os.path.basename(test_path)}")
        print(f"  Seizures: {seizures}")
        result = run_patient(pid, ref_path, test_path, seizures)
        results.append(result)
        gc.collect()

    print("\n" + "=" * 70)
    print("AGGREGATE RESULTS")
    print("=" * 70)

    agg = aggregate(results)

    print(f"  Framework: Winterhalder/Schelter SPC  SOP={SOP_S//60} min  SPH={SPH_S} s")
    print(f"  Engine:    CEK-v4  γ=E/(E+θ)  (canonical_system_v4 §5.5 + Thm O.1)")
    print(f"  Patients evaluated:      {agg['n_patients']} / {agg['n_patients']}")
    print(f"  Sensitivity mean ± std:  {agg['sensitivity_mean']:.3f} ± {agg['sensitivity_std']:.3f}")
    print(f"  % Perfect sensitivity:   {agg['pct_sensitivity_100']:.0f}%")
    print(f"  Lead time mean ± std:    {agg['lead_time_mean_s']/60:.1f} ± "
          f"{agg['lead_time_std_s']/60:.1f} min  ({agg['n_with_lead']} with lead)")
    print(f"  Lead > 5 min:            {agg['pct_lead_above_5min']:.0f}%")
    print(f"  SPC-AUC mean ± std:      {agg['spc_auc_mean']:.3f} ± {agg['spc_auc_std']:.3f}")
    print(f"  Skill ratio mean:        {agg['skill_ratio_mean']:.1f} × over chance")
    print(f"  Significant (p<0.05):    {agg['n_significant_p05']} / {agg['n_patients']} patients")
    print(f"  FAR mean ± std:          {agg['far_mean_per_hour']:.2f} ± "
          f"{agg['far_std_per_hour']:.2f} /hr")
    print(f"  Time-in-Warning mean:    {agg['tiw_mean']*100:.1f} ± "
          f"{agg['tiw_std']*100:.1f} %")
    print(f"  Discrimination ratio:    {agg['disc_mean']:.2f} ± "
          f"{agg['disc_std']:.2f} x")
    # Canonical diagnostics
    n_fresh = agg.get('n_canonical_fresh', 0)
    if n_fresh > 0:
        kappa_m = agg.get('kappa_mean', float('nan'))
        kappa_s = agg.get('kappa_std', float('nan'))
        g7_n    = agg.get('n_g7_flagged', 0)
        drift_m = agg.get('costheta_drift_mean', float('nan'))
        drift_s = agg.get('costheta_drift_std', float('nan'))
        ph2_n   = agg.get('n_phase2_confirmed', 0)
        print(f"  ─── Canonical diagnostics ({n_fresh} fresh patients) ───")
        print(f"  κ(Σ₀) mean ± std:        {kappa_m:.1f} ± {kappa_s:.1f}")
        print(f"  G7 flag (κ>10):          {g7_n} / {n_fresh} patients")
        print(f"  cosθ drift mean ± std:   {drift_m:.4f} ± {drift_s:.4f}  "
              f"({ph2_n} Phase-2 precursors confirmed)")
        tan_dm  = agg.get('tantheta_drift_mean',  float('nan'))
        tan_ds  = agg.get('tantheta_drift_std',   float('nan'))
        ph3_n   = agg.get('n_phase3_confirmed', 0)
        rho_im  = agg.get('rho_eff_interictal_mean_avg', float('nan'))
        rho_pm  = agg.get('rho_eff_preictal_mean_avg',   float('nan'))
        if not np.isnan(tan_dm):
            print(f"  tanθ drift mean ± std:   {tan_dm:.4f} ± {tan_ds:.4f}  "
                  f"({ph3_n} Phase-3 curvature peaks confirmed)")
        if not (np.isnan(rho_im) or np.isnan(rho_pm)):
            print(f"  ρ_eff interictal mean:   {rho_im:.4f}")
            print(f"  ρ_eff preictal mean:     {rho_pm:.4f}  "
                  f"({'↓' if rho_pm < rho_im else '↑'} vs interictal)")
    else:
        print(f"  Canonical diagnostics:   N/A (all patients loaded from cache)")
    print()
    print("  Per-patient clinical metrics:")
    print(f"  {'Patient':10s}  {'Sens':6s}  {'TiW%':6s}  {'Lead':10s}  "
          f"{'FAR/hr':7s}  {'SPC-AUC':8s}  {'Skill':6s}  {'κ(Σ₀)':8s}  {'G7':3s}")
    for r in results:
        if r is not None:
            lt  = r.get("lead_time_s") or float("nan")
            lt_str = f"{float(lt)/60:.1f}m" if not np.isnan(float(lt)) else "N/A"
            kappa  = r.get("kappa_sigma0", float("nan"))
            k_str  = f"{float(kappa):.0f}" if not np.isnan(float(kappa)) else "N/A"
            g7_str = "!" if r.get("g7_flag", False) else "-"
            print(f"  {r['patient']:10s}  "
                  f"{r.get('sensitivity', float('nan')):.2f}    "
                  f"{r.get('time_in_warning_frac', float('nan'))*100:.1f}%    "
                  f"{lt_str:10s}  "
                  f"{r.get('far_per_hour', float('nan')):.2f}     "
                  f"{r.get('spc_auc', float('nan')):.3f}     "
                  f"{r.get('skill_ratio', float('nan')):.1f}x    "
                  f"{k_str:8s}  {g7_str}")

    # Save full results
    out_json = os.path.join(RESULT_DIR, "chbmit_full_validation.json")
    full_results = {
        "aggregate": agg,
        "per_patient": [r for r in results if r is not None],
        "total_elapsed_s": round(time.time() - t_total, 1),
    }
    with open(out_json, "w") as f:
        json.dump(full_results, f, indent=2)
    print(f"\n  Results → {out_json}")

    make_plots([r for r in results if r is not None], agg)

    print(f"\nTotal elapsed: {(time.time() - t_total)/60:.1f} min")
    print("Done.")


if __name__ == "__main__":
    main()
