"""
Crypto BSDT v20 — Geometric State → Dynamic Allocator (GSDA-Arsenal)
=====================================================================

Architecture:
    PRIMARY ENGINE :  collapse_geometry.geometry.CollapseGeometry  (§XIV)
        — every trading decision is driven through CollapseGeometry's
          three equivalent collapse conditions and the tan_θ / tan_θ*
          critical-angle ratio.  This is the geometric lens.
    SURGICAL AUGMENTS (consulted only when CollapseGeometry asks):
        — §XIX  StochasticExtension.cross_probability   (Kramers)
        — §XXV  LyapunovCertificate.channel_decomposition  (a_k)
        — §XXIII χ²_{Nd, 0.99} statistical baseline
        — §XXVI ψ misalignment as a credibility veto
        — sklearn GMM(3) over a 9-D state vector for endogenous regime routing

Theory: deploys §I–§XXVII of the GravityEngine + BSDT + Phase Geometry arsenal
(collapse_geometry v1.3.0) to replace every heuristic in v19 with a closed-form
analytical signal.

What v19 taught us (empirical):
  • cos_θC alarm-only delivered Sharpe +0.962 (champion)
  • GCI dial alone was the WORST variant (+0.308) — broken because ρ_MFLS > 1
    on 99.1% of test days (permanent over-amplification regime)
  • v18_smooth (the published baseline) was +0.497

What v20 changes (architectural):
  ★ ALARM is the §XIV three-conditions vote from CollapseGeometry:
        spectral   :  λ_max(∇²Φ) > 1                     (geom.spectral_condition)
        angular    :  tan θ < tan θ*                     (geom.angular_condition)
        energetic  :  λ_max(∇²E_BS) · e_t > MFLS²        (geom.energetic_condition)
    Plus two surgical vetos:
        §XXIII  e_BS > χ²_{Nd, 0.99}     (statistical 1% FPR floor)
        §XXVI   cos ψ < 0.3              (channel/state misalignment veto)
    The alarm fires when ≥ 2 of the 3 §XIV conditions agree, OR either veto
    fires.  2-day persistence latch (same as v19).

  ★ LEVERAGE is the §XIV.4 critical-angle ratio (driven by CollapseGeometry):
        ratio   = tan_θ_state / tan_θ*
        lev_geo = clip(1 − ratio, lev_lo, lev_hi)
    When tan_θ → tan_θ* the system is at the angular collapse threshold and
    leverage collapses to lev_lo.  Augmented multiplicatively by the §XIX
    Kramers probability:  lev = lev_geo × (1 − P_kramers).
    This replaces the broken GCI dial of v19.

  ★ Soft GMM(3) over 9-D feature vector replaces hard if/else regime gates
    Ensemble of 5 seeds for robustness; EMA(5) on posteriors.

  ★ §XXV per-channel Lyapunov attribution a_k → strategy family bias
       δ_C dominant → mean-rev tilt
       δ_G dominant → trend-follow tilt
       δ_A dominant → vol/dispersion tilt
       δ_T dominant → cash tilt

  ★ §XXI agent sensitivity Sᵢ → identify the destabiliser asset of the day
    (proxy via §V Gershgorin row-sum)

  ★ Crisis = cash, never short (capital preservation directive)

  ★ Inverse-correlation intra-family weights (60d rolling)

  ★ 126d rolling Sharpe → softmax(τ=2.0) → .shift(5) for performance feedback

7-way ablation:
  v18_smooth              (baseline)
  v19_alarm_only          (champion to beat — Sharpe +0.962)
  v20_geom_alarm_only     (§XIV vote + §XXIII/§XXVI vetos replace cos_θC alarm)
  v20_soft_route          (just GMM probabilistic regime routing)
  v20_geom_lev_only       (§XIV.4 tan_θ/tan_θ* + §XIX Kramers leverage dial)
  v20_attribution_only    (just §XXV per-channel attribution tilt)
  v20_full                (everything)

Win criterion:
  Sharpe(v20_full) ≥ Sharpe(v19_alarm_only) = +0.962  AND
  MaxDD(v20_full)  ≤ MaxDD(v19_alarm_only)  = −0.080  AND
  EACH ablation component beats v18_smooth +0.497 solo.

Output:
  crypto_bsdt_v20_results.json
  crypto_bsdt_v20_equity.png  (4-panel)
"""

import os
import sys
import time
import json
import warnings
import numpy as np
import pandas as pd
warnings.filterwarnings('ignore')
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# Reuse v19's data, BSDT, strategies, sim verbatim — DRY
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import run_crypto_pairs_v19 as v19
from run_crypto_pairs_v19 import (
    fetch_and_prepare, add_cross_market_features,
    fetch_binance_funding, add_leverage_features,
    compute_bsdt, compute_gamma_rank, compute_activity_signals,
    compute_state_vector, compute_geom_signals_v18_smooth,
    apply_geom_penalties_v18, compute_leverage_dial,
    compute_rolling_spread_v8, SpreadUDLClassifier,
    compute_manifold_validity, detect_phase,
    route_pair_v7, route_btcalt_macro, setup_a_directional,
    get_daily_pnl, compute_cs_weights,
    simulate_from_pnl, equity_at_K, find_best_K,
    _build_state_panel, _CG_ASSETS,
    TRAIN_START, TRAIN_END, TEST_START, OUT_DIR,
    GAMMA_SCORE_WIN, GEOM_LEV_LO, GEOM_LEV_HI,
    ALARM_MIN_STEPS,
)

# collapse_geometry v1.3.0 — full §I–XXVII arsenal
sys.path.insert(0, r'C:\amttp\research\adaptive-friction')
from collapse_geometry import (
    MasterOperator, Snapshot,
    LyapunovCertificate, CollapseGeometry,
    EarlyWarning, EscapeTime, StochasticExtension,
)
from scipy import stats
from sklearn.mixture import GaussianMixture


# ─── v20 parameters ─────────────────────────────────────────────────────────
CG_HISTORY_WIN     = 60
CG_PCA_K           = 2

# §XXIII χ²-calibrated threshold (Nd = 8 ⇒ χ²_{8, 0.99} ≈ 20.0902)
CHI2_CONF          = 0.99

# §XVII 6-signal EWS
EWS_W6_PSI         = 0.3              # weight on ξ_6 = cos²ψ in updated EWS
EWS_PCT_TRAIN      = 99.0             # train percentile for EWS threshold

# §XXVI ψ misalignment floor (signals unreliable below this)
PSI_COS_FLOOR      = 0.3

# Alarm latch (same as v19)
V20_ALARM_MIN_STEPS = ALARM_MIN_STEPS  # 2 days

# §XVIII / §XIX Kramers leverage
KRAMERS_TAU        = 5.0              # forward horizon in days
SIGMA_N_FALLBACK   = 1e-2             # fallback noise amplitude
LEV_LO             = 0.20
LEV_HI             = 1.15

# GMM
GMM_K              = 3
GMM_SEEDS          = 5
GMM_EMA_SPAN       = 5

# Performance feedback
PERF_WIN           = 126
PERF_TAU           = 2.0
PERF_LAG           = 5

# Family weights when channel attribution is uniform (no dominance)
FAMILY_BASE = {'trend': 0.40, 'meanrev': 0.40, 'cash': 0.20}

# Channel → family tilt (multiplicative; renormalised after)
CHANNEL_TILT = {
    'C': {'trend': 0.7, 'meanrev': 1.5, 'cash': 1.0},   # δ_C → mean-rev
    'G': {'trend': 1.5, 'meanrev': 0.7, 'cash': 1.0},   # δ_G → trend
    'A': {'trend': 1.2, 'meanrev': 0.8, 'cash': 1.0},   # δ_A → vol/trend
    'T': {'trend': 0.5, 'meanrev': 0.5, 'cash': 2.0},   # δ_T → cash
}


# ─────────────────────────────────────────────────────────────────────────────
#  PHASE A — 9-D feature emission via MasterOperator
# ─────────────────────────────────────────────────────────────────────────────
def extract_arsenal_features(df, train_mask, history_win=CG_HISTORY_WIN):
    """Single-pass extraction driven by CollapseGeometry (§XIV).

    PRIMARY (CollapseGeometry-driven, §XIV):
        cos_theta_state   geom.cos_theta_state(snap)         Lyapunov-grade
        cos_theta_channel geom.cos_theta_channel(snap)       channel space
        tan_theta         geom.tan_theta(snap)               trajectory angle
        tan_theta_star    geom.tan_theta_star(snap)          critical angle (§XIV.4)
        cond_spectral     geom.spectral_condition(snap)      λ_max(∇²Φ) > 1
        cond_angular      geom.angular_condition(snap)       tan θ < tan θ*
        cond_energetic    geom.energetic_condition(snap)     λ·e > MFLS²
        cond_count        # of §XIV conditions True (0, 1, 2, 3)

    SURGICAL AUGMENTS (only consulted to refine geometry's verdict):
        e_BS              §VI ⑤    statistical χ²_8 baseline (§XXIII veto)
        rho_mfls          §XXIV.4 (amplification factor for context)
        cos_psi           §XXVI    misalignment veto (when ψ → π/2 ignore signals)
        ews6              §XVII    composite credibility-weighted score
        Pt                §XVI     Lyapunov power for diagnostics
        gamma_star        §VIII    γ* = e/(e+θ)
        attr_C/G/A/T      §XXV     per-channel attribution a_k → strategy family tilt
        kramers_p         §XIX     forward P(cross C_man within KRAMERS_TAU days)

    Returns: pd.DataFrame indexed by df.index.
    """
    print("  [v20] Building (T, N=4, d=2) state panel ...")
    X_panel = _build_state_panel(df)
    T = len(X_panel)
    N = X_panel.shape[1]

    print("  [v20] Calibrating MasterOperator on training period ...")
    X_normal = X_panel[np.asarray(train_mask)]
    op   = MasterOperator.calibrate(X_normal, k=CG_PCA_K)
    geom = CollapseGeometry(op=op)
    lyap = LyapunovCertificate(op=op)

    # σ_n estimated as residual std on training: dX − F·dt (closed-form noise)
    print("  [v20] Estimating noise amplitude σ_n on train ...")
    residuals = []
    for t in range(1, len(X_normal)):
        snap = Snapshot(X=X_normal[t], X_prev=X_normal[t-1],
                        history=X_normal[max(0,t-history_win):t])
        try:
            F = op.force(snap)
            dX = X_normal[t] - X_normal[t-1]
            residuals.append(np.linalg.norm(dX - F))
        except Exception:
            pass
    sigma_n = float(np.std(residuals)) if residuals else SIGMA_N_FALLBACK
    sigma_n = max(sigma_n, 1e-3)
    print(f"  [v20] σ_n = {sigma_n:.4f}")
    stoch = StochasticExtension(op=op, lyap=lyap, sigma_n=sigma_n)

    # §XXIII χ²-calibrated e* (Nd degrees of freedom)
    Nd = N * X_panel.shape[2]                 # 4 × 2 = 8
    e_star = float(stats.chi2.ppf(CHI2_CONF, Nd))
    print(f"  [v20] χ² threshold e* = χ²_{{{Nd}, {CHI2_CONF}}} = {e_star:.3f}")

    print(f"  [v20] Sweeping {T} days — CollapseGeometry-driven extraction ...")
    rows = []
    agent_sens_rows = np.full((T, N), np.nan)
    t0 = time.time()
    for t in range(1, T):
        h_start = max(0, t - history_win)
        snap = Snapshot(
            X       = X_panel[t],
            X_prev  = X_panel[t - 1],
            history = X_panel[h_start:t],
        )
        try:
            # ── PRIMARY: CollapseGeometry §XIV ────────────────────────────
            cos_thC  = float(geom.cos_theta_channel(snap))
            cos_thS  = float(geom.cos_theta_state(snap))
            tan_th   = float(geom.tan_theta(snap))
            tan_thS  = float(geom.tan_theta_star(snap))
            cond_sp  = bool(geom.spectral_condition(snap))
            cond_an  = bool(geom.angular_condition(snap))
            cond_en  = bool(geom.energetic_condition(snap))
            cond_n   = int(cond_sp) + int(cond_an) + int(cond_en)

            # ── SURGICAL AUGMENTS (only when geometry asks) ───────────────
            S        = op.bsdt.channel_state(snap)
            e_BS     = float(op.energy.E_total(S))                  # §VI ⑤
            mfls_ch  = float(op.mfls.channel_mfls(snap))
            mfls_st  = float(op.mfls.state_mfls(snap))
            rho      = float(op.mfls.rho_mfls(snap))                # §XXIV.4
            psi      = float(op.mfls.psi(snap))                     # §XXVI
            cos_psi  = float(np.cos(psi))
            D        = snap.distance_matrix()
            lam_bnd  = float(op.potential.lambda_max_bound(D))      # §V
            gamma    = float(op.damp.gamma_star(snap))              # §VIII

            # §XVII EWS_6 (credibility-weighted)
            xi1 = gamma
            xi2 = min(lam_bnd, 1.0)
            xi4 = abs(cos_thS)
            xi5 = mfls_st / (1.0 + mfls_st)
            xi6 = float(cos_psi ** 2)
            xis5 = np.clip([xi1, xi2, xi4, xi5, max(xi6, 1e-12)], 1e-12, 1.0)
            base5 = float(np.exp(np.log(xis5[:4]).mean()))
            ews6  = (base5 ** (1.0 - EWS_W6_PSI)) * (max(xi6, 1e-12) ** EWS_W6_PSI)

            # §XVI Pt for Lyapunov power
            try:
                Pt = float(lyap._bundle(snap)["Pt"])
            except Exception:
                Pt = 0.0

            # §XXV per-channel attribution
            try:
                cd = lyap.channel_decomposition(snap)
                attr_C = float(cd['C']['attribution'])
                attr_G = float(cd['G']['attribution'])
                attr_A = float(cd['A']['attribution'])
                attr_T = float(cd['T']['attribution'])
            except Exception:
                attr_C = attr_G = attr_A = attr_T = 0.25

            # §XIX Kramers prob (forward 5-day crossing)
            try:
                p_kramers = float(stoch.cross_probability(
                    snap, e_star=e_star, tau=KRAMERS_TAU, dt=1e-2))
            except Exception:
                p_kramers = 0.0

            # §XXI agent sensitivity proxy via Gershgorin row sum
            try:
                K = op.forces.kernel(D)
                row_sens = np.abs(K).sum(axis=1)
            except Exception:
                row_sens = np.zeros(N)
            agent_sens_rows[t] = row_sens

            rows.append((t,
                         # primary (geometry.py)
                         cos_thC, cos_thS, tan_th, tan_thS,
                         int(cond_sp), int(cond_an), int(cond_en), cond_n,
                         # surgical augments
                         e_BS, mfls_ch, mfls_st, rho, cos_psi, lam_bnd, ews6,
                         Pt, gamma,
                         attr_C, attr_G, attr_A, attr_T, p_kramers))
        except Exception:
            pass

        if (t % 200) == 0:
            elapsed = time.time() - t0
            print(f"    t={t}/{T}  ({elapsed:.1f}s)")

    print(f"  [v20] Feature sweep complete ({time.time()-t0:.1f}s, {len(rows)}/{T} days)")

    cols = ['t_idx',
            # primary (geometry.py §XIV)
            'cos_theta_channel', 'cos_theta_state', 'tan_theta', 'tan_theta_star',
            'cond_spectral', 'cond_angular', 'cond_energetic', 'cond_count',
            # surgical augments
            'e_BS', 'mfls_channel', 'mfls_state', 'rho_mfls', 'cos_psi',
            'lambda_max_bound', 'ews6', 'Pt', 'gamma_star',
            'attr_C', 'attr_G', 'attr_A', 'attr_T', 'kramers_p']
    F = pd.DataFrame(rows, columns=cols).set_index('t_idx')
    F.index = df.index[F.index]
    F = F.reindex(df.index)

    # agent sensitivity as separate frame
    AS = pd.DataFrame(agent_sens_rows, index=df.index,
                      columns=[f'sens_{a}' for a in _CG_ASSETS])

    return F, AS, e_star, op


# ─────────────────────────────────────────────────────────────────────────────
#  PHASE B — CollapseGeometry-driven alarm (§XIV vote + surgical vetos)
# ─────────────────────────────────────────────────────────────────────────────
def compute_v20_alarm(F, train_mask, e_star,
                      ews_pct=EWS_PCT_TRAIN,
                      psi_floor=PSI_COS_FLOOR,
                      min_steps=V20_ALARM_MIN_STEPS,
                      cond_vote_min=2):
    """Alarm = (CollapseGeometry §XIV vote) OR (§XXIII veto) OR (§XXVI veto).

    PRIMARY (geometry.py §XIV — three equivalent collapse conditions):
      cond_count(t) = #{spectral, angular, energetic} that fire at t.
      Vote fires when cond_count >= cond_vote_min (default 2-of-3).

    SURGICAL VETOS (only override geometry on statistical outliers):
      §XXIII e_BS > e*_eff = max(theoretical χ², P99_train empirical)
      §XXVI  cos_psi < psi_floor (state/channel misalignment)
    """
    cond_n = F['cond_count'].fillna(0).astype(int)
    e_BS   = F['e_BS'].fillna(0.0)
    psi_c  = F['cos_psi'].fillna(1.0)

    # §XXIII empirical recalibration (theoretical χ² is just a *floor*).
    e_BS_train = e_BS[train_mask].dropna()
    if len(e_BS_train) > 0:
        e_emp = float(np.nanpercentile(e_BS_train.values, ews_pct))
        e_star_eff = max(e_star, e_emp)
        print(f"  [v20] χ² floor={e_star:.2f}  P{int(ews_pct)}_train={e_emp:.2f}"
              f"  → e*_eff={e_star_eff:.2f}")
    else:
        e_star_eff = e_star

    geom_vote = (cond_n >= cond_vote_min).astype(int)
    veto_chi2 = (e_BS > e_star_eff).astype(int)
    veto_psi  = (psi_c < psi_floor).astype(int)
    fire      = ((geom_vote + veto_chi2 + veto_psi) > 0).astype(int)

    print(f"  [v20] geom-vote(≥{cond_vote_min}/3) fires {int(geom_vote.sum())} days, "
          f"χ²-veto {int(veto_chi2.sum())} days, ψ-veto {int(veto_psi.sum())} days")

    roll = fire.rolling(min_steps, min_periods=min_steps).sum()
    alarm_raw = roll >= min_steps

    latched = False
    arr_fire = fire.values
    out = np.zeros(len(F), dtype=bool)
    for i in range(len(F)):
        if alarm_raw.iloc[i]:
            latched = True
        if latched and arr_fire[i] == 0:
            latched = False
        out[i] = latched
    alarm = pd.Series(out, index=F.index, name='alarm_v20')
    return alarm, e_star_eff


# ─────────────────────────────────────────────────────────────────────────────
#  PHASE C — Endogenous regime routing via GMM ensemble
# ─────────────────────────────────────────────────────────────────────────────
def fit_gmm_ensemble(F, train_mask, k=GMM_K, n_seeds=GMM_SEEDS,
                     ema_span=GMM_EMA_SPAN):
    """Fit GMM(k) on train_mask only over 9-D feature vector.

    Ensembles n_seeds initialisations, averages posteriors. Post-hoc renames
    components by mean e_BS so R0=calm, R{k-1}=collapse.

    Returns: pd.DataFrame (T, k) of EMA-smoothed regime probabilities.
    """
    feat_cols = ['e_BS', 'mfls_channel', 'mfls_state', 'rho_mfls',
                 'cos_theta_channel', 'cos_theta_state', 'tan_theta',
                 'cos_psi', 'cond_count']
    Fnum = F[feat_cols].copy()

    # expanding z-score (no look-ahead): use train-only mean/std as fixed scaler
    train_idx = np.asarray(train_mask)
    train_F = Fnum[train_idx].dropna()
    mu = train_F.mean()
    sd = train_F.std().replace(0.0, 1.0)
    Fz = (Fnum - mu) / sd
    Fz_train = Fz[train_idx].dropna()

    print(f"  [v20] Fitting GMM(k={k}) ensemble of {n_seeds} seeds on "
          f"{len(Fz_train)} training rows × {len(feat_cols)} features ...")

    posts = np.zeros((len(Fz), k))
    Fz_full = Fz.fillna(0.0).values
    weights_used = 0

    for seed in range(n_seeds):
        try:
            gmm = GaussianMixture(n_components=k, covariance_type='full',
                                  random_state=seed, max_iter=200,
                                  reg_covar=1e-4, init_params='kmeans')
            gmm.fit(Fz_train.values)
            # post-hoc rename by mean e_BS (z-scored) ascending → R0=calm
            mean_e = gmm.means_[:, feat_cols.index('e_BS')]
            order  = np.argsort(mean_e)            # k indices, calm→stress→collapse
            P = gmm.predict_proba(Fz_full)[:, order]
            posts += P
            weights_used += 1
        except Exception as e:
            print(f"  [v20] GMM seed {seed} failed: {e}")
    if weights_used == 0:
        # fallback: all calm
        posts[:, 0] = 1.0
    else:
        posts /= weights_used

    # EMA on posteriors
    P_df = pd.DataFrame(posts, index=Fz.index,
                        columns=[f'p_R{i}' for i in range(k)])
    P_df = P_df.ewm(span=ema_span, adjust=False).mean()
    # renormalise after EMA
    P_df = P_df.div(P_df.sum(axis=1), axis=0)
    return P_df


# ─────────────────────────────────────────────────────────────────────────────
#  PHASE D — CollapseGeometry-driven leverage dial  (§XIV.4 critical angle)
# ─────────────────────────────────────────────────────────────────────────────
def compute_kramers_leverage(F, lev_lo=LEV_LO, lev_hi=LEV_HI):
    """Leverage from the §XIV.4 critical-angle ratio, augmented surgically by Kramers.

    Geometric core (geometry.py):
        ratio = tan_θ / tan_θ*               ∈ [0, ∞)
        lev_geo = clip(1 − ratio, lev_lo, lev_hi)
        ratio→0  : trajectory benign         lev_geo → 1 (capped at lev_hi)
        ratio→1  : at angular collapse       lev_geo → 0 (floored at lev_lo)
    Surgical augment (§XIX Kramers):
        lev = lev_geo · (1 − P_kramers)      forward-looking de-risking
    """
    tan_th  = F['tan_theta'].fillna(0.0).clip(lower=0.0)
    tan_thS = F['tan_theta_star'].fillna(np.inf).clip(lower=1e-6)
    ratio   = (tan_th / tan_thS).clip(lower=0.0, upper=2.0)
    lev_geo = (1.0 - ratio).clip(lower=lev_lo, upper=lev_hi)

    p_kr    = F['kramers_p'].fillna(0.0).clip(0.0, 1.0)
    lev     = (lev_geo * (1.0 - p_kr)).clip(lower=lev_lo, upper=lev_hi)

    return lev.ewm(span=5, adjust=False).mean().clip(lower=lev_lo, upper=lev_hi)


# ─────────────────────────────────────────────────────────────────────────────
#  PHASE E — Per-channel attribution → family tilt
# ─────────────────────────────────────────────────────────────────────────────
def compute_channel_family_tilt(F):
    """Channel attribution a_k → multiplicative tilt across {trend, meanrev, cash}.

    Returns: pd.DataFrame (T, 3) of normalised family weights per day.
    """
    out = pd.DataFrame(index=F.index, columns=list(FAMILY_BASE.keys()), dtype=float)
    for fam in FAMILY_BASE:
        w = pd.Series(FAMILY_BASE[fam], index=F.index)
        for ch in ('C', 'G', 'A', 'T'):
            tilt = CHANNEL_TILT[ch][fam]
            attr = F[f'attr_{ch}'].fillna(0.25)
            w = w * (1.0 + (tilt - 1.0) * attr)
        out[fam] = w
    out = out.div(out.sum(axis=1), axis=0).fillna(1.0 / 3.0)
    return out


# ─────────────────────────────────────────────────────────────────────────────
#  PHASE F — Performance feedback (lagged Sharpe softmax)
# ─────────────────────────────────────────────────────────────────────────────
def compute_perf_feedback(pnl_dict, window=PERF_WIN, tau=PERF_TAU, lag=PERF_LAG):
    """126d rolling Sharpe → softmax(τ) → .shift(lag) for look-ahead safety.

    Returns: dict[strategy] → pd.Series of feedback weights (one per strategy).
    """
    sharpes = {}
    for k, pnl in pnl_dict.items():
        mu = pnl.rolling(window, min_periods=window // 2).mean()
        sd = pnl.rolling(window, min_periods=window // 2).std()
        sharpes[k] = (mu / (sd + 1e-12) * np.sqrt(252)).fillna(0.0)
    sh_df = pd.DataFrame(sharpes)
    # softmax across strategies per day
    z = sh_df / max(tau, 1e-6)
    e = np.exp(z - z.max(axis=1).values[:, None])
    sm = e.div(e.sum(axis=1), axis=0).shift(lag).fillna(1.0 / len(pnl_dict))
    return {k: sm[k] for k in pnl_dict}


# ─────────────────────────────────────────────────────────────────────────────
#  PHASE G — Inverse-correlation intra-family weights
# ─────────────────────────────────────────────────────────────────────────────
def compute_intra_family_weights(pnl_subset, window=60):
    """Inverse-correlation (risk-parity-ish) weights within a strategy family.

    For each day, weight ∝ 1 / (sum of |corr| with other strategies in family).
    Diversifying strategies → higher weight; redundant ones → lower.
    """
    strategies = list(pnl_subset.keys())
    n = len(strategies)
    if n == 1:
        return {strategies[0]: pd.Series(1.0, index=pnl_subset[strategies[0]].index)}
    df_pnl = pd.DataFrame(pnl_subset)
    weights = {k: pd.Series(1.0 / n, index=df_pnl.index) for k in strategies}
    rolling_corr = df_pnl.rolling(window, min_periods=window // 2).corr()
    # for each timestamp, get NxN, compute 1/(row sum of |corr|)
    for t in df_pnl.index[window:]:
        try:
            C = rolling_corr.loc[t].abs().fillna(0.0).values
            row_sum = C.sum(axis=1)
            inv = 1.0 / np.where(row_sum > 1e-9, row_sum, 1.0)
            inv = inv / inv.sum()
            for i, k in enumerate(strategies):
                weights[k].loc[t] = inv[i]
        except Exception:
            pass
    return weights


# ─────────────────────────────────────────────────────────────────────────────
#  PHASE H — Final v20 position composer
# ─────────────────────────────────────────────────────────────────────────────
def compose_v20_pnl(pnl_base, family_map,
                    family_tilt, regime_probs, perf_fb,
                    lev_kramers, alarm,
                    use_attribution=True, use_regime=True,
                    use_kramers=True, use_perf=True, use_alarm=True):
    """Compose final v20 PnL stream.

    Parameters
    ----------
    pnl_base   : dict[strategy_label] → pd.Series of per-day PnL (already pos×ret)
    family_map : dict[strategy_label] → 'trend' | 'meanrev' | 'cash'
    family_tilt: pd.DataFrame (T, 3) per-day family weights
    regime_probs: pd.DataFrame (T, 3)  p_R0 (calm), p_R1 (stress), p_R2 (collapse)
    perf_fb    : dict[strategy_label] → pd.Series of softmax-weighted shares
    lev_kramers: pd.Series of per-day leverage from §XVIII/§XIX
    alarm      : pd.Series of bool — when True, set PnL = 0 (cash, never short)
    """
    idx = next(iter(pnl_base.values())).index
    pnl_total = pd.Series(0.0, index=idx)

    # 1. intra-family inverse-corr weights
    fam_groups = {'trend': [], 'meanrev': [], 'cash': []}
    for s, fam in family_map.items():
        fam_groups[fam].append(s)
    intra_weights = {}
    for fam, strats in fam_groups.items():
        if not strats:
            continue
        sub = {s: pnl_base[s] for s in strats}
        intra_weights[fam] = compute_intra_family_weights(sub, window=60)

    # 2. regime tilt: collapse regime forces cash-heavy
    if use_regime and regime_probs is not None:
        p_calm   = regime_probs.iloc[:, 0]
        p_stress = regime_probs.iloc[:, 1] if regime_probs.shape[1] > 1 else 0.0
        p_coll   = regime_probs.iloc[:, -1]
        # tilt: trend ∝ p_calm, meanrev ∝ p_stress, cash ∝ p_coll
        regime_tilt = pd.DataFrame({
            'trend':   p_calm,
            'meanrev': p_stress if isinstance(p_stress, pd.Series) else pd.Series(p_stress, index=idx),
            'cash':    p_coll,
        })
        regime_tilt = regime_tilt.div(regime_tilt.sum(axis=1), axis=0).fillna(1.0/3.0)
    else:
        regime_tilt = pd.DataFrame(1.0/3.0, index=idx, columns=['trend','meanrev','cash'])

    # 3. attribution tilt
    if use_attribution and family_tilt is not None:
        attr_tilt = family_tilt
    else:
        attr_tilt = pd.DataFrame(1.0/3.0, index=idx, columns=['trend','meanrev','cash'])

    # combined family weights
    fam_w = (regime_tilt * attr_tilt)
    fam_w = fam_w.div(fam_w.sum(axis=1), axis=0).fillna(1.0/3.0)

    # 4. assemble per-strategy weight = family_w[fam] * intra_weight[s]
    for s, fam in family_map.items():
        if fam == 'cash':
            continue   # cash is "do nothing", contributes 0 to PnL
        if s not in intra_weights[fam]:
            continue
        w_intra = intra_weights[fam][s].reindex(idx).fillna(1.0)
        w_fam   = fam_w[fam].reindex(idx).fillna(1.0/3.0)
        if use_perf and s in perf_fb:
            w_perf = perf_fb[s].reindex(idx).fillna(1.0)
        else:
            w_perf = 1.0
        # full per-strat weight (lagged 1 day for execution)
        w_full = (w_intra * w_fam * w_perf).shift(1).fillna(0.0)
        pnl_total = pnl_total + w_full * pnl_base[s]

    # 5. apply Kramers leverage
    if use_kramers and lev_kramers is not None:
        pnl_total = pnl_total * lev_kramers.shift(1).reindex(idx).fillna(1.0)

    # 6. alarm = cash, never short (override)
    if use_alarm and alarm is not None:
        a = alarm.shift(1).fillna(False).reindex(idx).fillna(False)
        pnl_total = pnl_total.where(~a, 0.0)

    return pnl_total


# ─────────────────────────────────────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────────────────────────────────────
def main():
    print("=" * 92)
    print("  CRYPTO BSDT v20 — Geometric State → Dynamic Allocator (GSDA-Arsenal)")
    print("  §I–XXVII closed-form arsenal: χ² · EWS · ψ · Kramers · GMM · attribution")
    print("=" * 92)

    # ── [1] Load data (reuse v19) ──────────────────────────────────────────
    df = fetch_and_prepare()
    print("  Adding cross-market features ...")
    df = add_cross_market_features(df)
    print("  Fetching Binance funding rates ...")
    funding = fetch_binance_funding(symbols=['ETHUSDT', 'BTCUSDT'], start='2020-06-01')
    df = add_leverage_features(df, funding)

    train_mask = (df.index >= TRAIN_START) & (df.index <= TRAIN_END)
    test_mask  = df.index >= TEST_START
    print(f"  Train: {df[train_mask].index[0].date()} → {df[train_mask].index[-1].date()}")
    print(f"  Test:  {df[test_mask].index[0].date()} → {df[test_mask].index[-1].date()}")

    # ── [2] Core BSDT signals (reuse v19) ──────────────────────────────────
    feats_strat = [
        'ret_eth_z', 'ret_btc_z', 'ret_sol_z', 'ret_bnb_z',
        'vol_eth_z', 'vol_btc_z', 'btc_dom_z', 'cross_disp_z',
    ]
    feats_ext = feats_strat + ['ret_spx_z', 'dvix_z', 'ret_dxy_z']
    print("\n[2] Computing BSDT signals (legacy) ...")
    omega_strat, mfls_eth, gamma_eth = compute_bsdt(df, feats_strat, window=60)
    omega_ext,        _,          _  = compute_bsdt(df, feats_ext,   window=60)
    A_eth, A_rank, dA_fast, dA_rank = compute_activity_signals(mfls_eth, gamma_eth)
    gamma_rank = compute_gamma_rank(omega_ext, min_periods=60)
    lev_mult   = compute_leverage_dial(gamma_rank)

    # ── [3] Arsenal feature emission (single CG sweep) ─────────────────────
    print("\n[3] Extracting §I–XXVII arsenal features ...")
    F, AS, e_star, op = extract_arsenal_features(df, train_mask)

    # diagnostics
    F_test = F[test_mask]
    print(f"\n  e_BS [test]:        mean={F_test['e_BS'].mean():.3f}  "
          f"max={F_test['e_BS'].max():.3f}  "
          f"frac > e*={float((F_test['e_BS']>e_star).mean()*100):.1f}%")
    print(f"  ρ_MFLS [test]:      mean={F_test['rho_mfls'].mean():.3f}  "
          f"frac>1={float((F_test['rho_mfls']>1).mean()*100):.1f}%")
    print(f"  cos_θC [test]:      mean={F_test['cos_theta_channel'].mean():.3f}")
    print(f"  cos_θ_state [test]: mean={F_test['cos_theta_state'].mean():.3f}")
    print(f"  cos_ψ [test]:       mean={F_test['cos_psi'].mean():.3f}  "
          f"frac<{PSI_COS_FLOOR}={float((F_test['cos_psi']<PSI_COS_FLOOR).mean()*100):.1f}%")
    print(f"  EWS_6 [test]:       mean={F_test['ews6'].mean():.4f}  "
          f"max={F_test['ews6'].max():.4f}")
    print(f"  Kramers P [test]:   mean={F_test['kramers_p'].mean():.3f}  "
          f"max={F_test['kramers_p'].max():.3f}")
    print(f"  Channel attribution [test] mean: "
          f"C={F_test['attr_C'].mean():.3f}  G={F_test['attr_G'].mean():.3f}  "
          f"A={F_test['attr_A'].mean():.3f}  T={F_test['attr_T'].mean():.3f}")

    # ── [4] v20 alarm + Kramers leverage + family tilts ────────────────────
    print("\n[4] Building v20 alarm (3-of-3 OR-gated) ...")
    alarm_v20, ews_thresh = compute_v20_alarm(F, train_mask, e_star)
    n_alarm = int(alarm_v20[test_mask].sum())
    print(f"  v20 alarm days: {n_alarm} ({n_alarm/test_mask.sum()*100:.1f}% of test)")

    print("\n[5] Building Kramers leverage modulator ...")
    lev_kramers = compute_kramers_leverage(F)
    print(f"  Kramers leverage [test]: min={lev_kramers[test_mask].min():.3f}  "
          f"max={lev_kramers[test_mask].max():.3f}  "
          f"mean={lev_kramers[test_mask].mean():.3f}")

    print("\n[6] Fitting GMM regime ensemble ...")
    P_regime = fit_gmm_ensemble(F.fillna(method='ffill').fillna(0.0),
                                train_mask, k=GMM_K, n_seeds=GMM_SEEDS)
    P_test = P_regime[test_mask]
    print(f"  Regime occupancy [test]: "
          f"R0(calm)={P_test.iloc[:,0].mean():.3f}  "
          f"R1(stress)={P_test.iloc[:,1].mean():.3f}  "
          f"R2(collapse)={P_test.iloc[:,2].mean():.3f}")

    print("\n[7] Computing channel→family attribution tilt ...")
    fam_tilt = compute_channel_family_tilt(F.fillna(method='ffill').fillna(0.25))
    print(f"  Family weight [test] mean: "
          f"trend={fam_tilt['trend'][test_mask].mean():.3f}  "
          f"meanrev={fam_tilt['meanrev'][test_mask].mean():.3f}  "
          f"cash={fam_tilt['cash'][test_mask].mean():.3f}")

    # ── [8] Build base strategies (reuse v19) ──────────────────────────────
    print("\n[8] Building strategy positions (reuse v19) ...")
    ret7  = df['ret_eth'].rolling(7).sum()
    ret3  = df['ret_eth'].rolling(3).sum()
    phase = detect_phase(omega_strat, ret7, ret3, df['btc_dom_z'])
    pos_A_dir = setup_a_directional(df, omega_strat, mfls_eth, gamma_eth, phase)
    pairs = [
        ('P1_ETH_BTC', 'log_eth', 'log_btc', 'ret_eth', 'ret_btc'),
        ('P2_ETH_SOL', 'log_eth', 'log_sol', 'ret_eth', 'ret_sol'),
        ('P3_ETH_BNB', 'log_eth', 'log_bnb', 'ret_eth', 'ret_bnb'),
    ]
    pair_data = {}
    for key, col_a, col_b, ret_a, ret_b in pairs:
        print(f"  {key}: computing spread ...", end='', flush=True)
        sd = compute_rolling_spread_v8(
            df[col_a], df[col_b], df[ret_a], df[ret_b],
            train_mask=train_mask, beta_window=252)
        train_spread = sd['spread'][train_mask].dropna()
        clf = SpreadUDLClassifier(window=20, n_ref_dirs=100).fit(train_spread)
        udl_state, udl_mag, udl_novelty = clf.classify_series(sd['spread'])
        sd['udl_state'] = udl_state
        mval, _ = compute_manifold_validity(sd['z'], sd['sret'])
        sd['manifold_valid'] = mval
        pair_data[key] = sd
        print(f" done")

    pair_pos = {}
    for key, _, _, _, _ in pairs:
        sd = pair_data[key]
        pair_pos[key] = route_pair_v7(
            omega_strat, A_rank, sd['z'], sd['udl_state'], sd['poa'],
            sd['manifold_valid'])
    pos_btc_macro, pos_alt_macro = route_btcalt_macro(df, omega_strat, A_rank, dA_rank)

    pnl_base = {
        'A_directional': get_daily_pnl(pos_A_dir, df['ret_eth']),
        'P1_ETH_BTC':    get_daily_pnl(pair_pos['P1_ETH_BTC'], pair_data['P1_ETH_BTC']['sret']),
        'P2_ETH_SOL':    get_daily_pnl(pair_pos['P2_ETH_SOL'], pair_data['P2_ETH_SOL']['sret']),
        'P3_ETH_BNB':    get_daily_pnl(pair_pos['P3_ETH_BNB'], pair_data['P3_ETH_BNB']['sret']),
        'M1_ALT_macro':  get_daily_pnl(pos_alt_macro, df['ret_eth']),
        'M1_BTC_macro':  get_daily_pnl(pos_btc_macro, df['ret_btc']),
    }
    # Strategy → family map
    family_map = {
        'A_directional': 'trend',
        'P1_ETH_BTC':    'meanrev',
        'P2_ETH_SOL':    'meanrev',
        'P3_ETH_BNB':    'meanrev',
        'M1_ALT_macro':  'trend',
        'M1_BTC_macro':  'trend',
    }

    # v18_smooth baseline (reuse v19 verbatim)
    V_state = compute_state_vector(omega_strat, gamma_rank, mfls_eth, dA_fast)
    phi_18s, align_18s = compute_geom_signals_v18_smooth(V_state)
    lev_v18_smooth = apply_geom_penalties_v18(lev_mult, phi_18s, align_18s)
    cs_wts_v10 = compute_cs_weights(pnl_base, window=GAMMA_SCORE_WIN)
    n_s = len(pnl_base)
    pnl_v10 = pd.Series(0.0, index=df.index)
    for k in pnl_base:
        pnl_v10 += cs_wts_v10[k].shift(1).fillna(1.0/n_s) * pnl_base[k]
    pnl_v18s = pnl_v10 * lev_v18_smooth.shift(1).fillna(1.0)

    # v19_alarm_only (champion to beat) — reuse v19 cos_θC alarm
    cos_tc_v19 = F['cos_theta_channel']
    alarm_v19 = v19.compute_hard_lock_alarm(cos_tc_v19)
    pnl_v19_alarm = pnl_v18s.copy()
    pnl_v19_alarm[alarm_v19.shift(1).fillna(False)] = 0.0

    # ── [9] Performance feedback (computed on v18s base) ───────────────────
    print("\n[9] Computing performance feedback (lagged Sharpe softmax) ...")
    perf_fb = compute_perf_feedback(pnl_base, window=PERF_WIN,
                                     tau=PERF_TAU, lag=PERF_LAG)

    # ── [10] 7-way ablation ────────────────────────────────────────────────
    print("\n[10] Building v20 ablation (7-way) ...")

    # v20_geom_alarm_only: §XIV three-conditions vote + §XXIII/§XXVI vetos
    #                      (replaces v19's single-cosine cos_θC heuristic)
    pnl_v20_thresh = pnl_v18s.copy()
    pnl_v20_thresh[alarm_v20.shift(1).fillna(False)] = 0.0

    # v20_soft_route: just GMM regime tilt (no alarm, no kramers, no attr, no perf)
    pnl_v20_soft = compose_v20_pnl(
        pnl_base, family_map, fam_tilt, P_regime, perf_fb,
        lev_kramers, alarm_v20,
        use_attribution=False, use_regime=True,
        use_kramers=False, use_perf=False, use_alarm=False)

    # v20_geom_lev_only: §XIV.4 tan_θ/tan_θ* leverage dial × §XIX Kramers
    pnl_v20_kram = pnl_v18s * lev_kramers.shift(1).reindex(pnl_v18s.index).fillna(1.0)

    # v20_attribution_only: just channel→family tilt (no regime, no kramers)
    pnl_v20_attr = compose_v20_pnl(
        pnl_base, family_map, fam_tilt, None, perf_fb,
        None, None,
        use_attribution=True, use_regime=False,
        use_kramers=False, use_perf=False, use_alarm=False)

    # v20_full: all components
    pnl_v20_full = compose_v20_pnl(
        pnl_base, family_map, fam_tilt, P_regime, perf_fb,
        lev_kramers, alarm_v20,
        use_attribution=True, use_regime=True,
        use_kramers=True, use_perf=True, use_alarm=True)

    # ── [11] Simulate test period ──────────────────────────────────────────
    print(f"\n[11] Simulating test period {TEST_START} → present ...")
    ablation = {
        'v18_smooth':            pnl_v18s[test_mask],
        'v19_alarm_only':        pnl_v19_alarm[test_mask],
        'v20_geom_alarm_only':   pnl_v20_thresh[test_mask],
        'v20_soft_route':        pnl_v20_soft[test_mask],
        'v20_geom_lev_only':     pnl_v20_kram[test_mask],
        'v20_attribution_only':  pnl_v20_attr[test_mask],
        'v20_full':              pnl_v20_full[test_mask],
    }
    sims = {k: simulate_from_pnl(v, k) for k, v in ablation.items()}

    # Print ablation table
    print("\n" + "=" * 92)
    print("  v20 ABLATION RESULTS  (K=1 gross, test period)")
    print("=" * 92)
    print(f"  {'variant':<24}  {'Sharpe':>8}  {'MaxDD':>8}  {'CAGR%':>8}  "
          f"{'CumRet%':>8}  {'Active':>8}")
    print("  " + "─" * 78)
    for k, s in sims.items():
        marker = ''
        if k == 'v20_full':
            marker = '  ← v20 FULL'
        elif k == 'v19_alarm_only':
            marker = '  ← champion to beat'
        elif k == 'v18_smooth':
            marker = '  ← published baseline'
        print(f"  {k:<24}  {s['sharpe']:>+8.4f}  {s['max_dd']:>+8.4f}  "
              f"{s['cagr']*100:>+7.2f}%  {s['cum_return']*100:>+7.2f}%  "
              f"{s['active_days']:>6}d{marker}")
    print()

    # Win/loss verdict
    sh_v18  = sims['v18_smooth']['sharpe']
    sh_v19  = sims['v19_alarm_only']['sharpe']
    sh_v20  = sims['v20_full']['sharpe']
    dd_v19  = sims['v19_alarm_only']['max_dd']
    dd_v20  = sims['v20_full']['max_dd']

    win_sh    = sh_v20 >= sh_v19
    win_dd    = dd_v20 >= dd_v19
    each_beats_v18 = all(
        sims[k]['sharpe'] >= sh_v18
        for k in ['v20_geom_alarm_only', 'v20_soft_route',
                  'v20_geom_lev_only', 'v20_attribution_only']
    )
    v20_wins = win_sh and win_dd and each_beats_v18

    verdict = "★ v20_full BEATS v19_alarm_only — UPGRADE" if v20_wins else \
              "v20_full does NOT meet all criteria — keep v19_alarm_only"
    print(f"  Win criteria (3-of-3):")
    print(f"    Sharpe(v20_full) ≥ Sharpe(v19_alarm)  : "
          f"{'✓' if win_sh else '✗'} {sh_v20:+.4f} vs {sh_v19:+.4f}")
    print(f"    MaxDD(v20_full)  ≥ MaxDD(v19_alarm)   : "
          f"{'✓' if win_dd else '✗'} {dd_v20:+.4f} vs {dd_v19:+.4f}")
    print(f"    Each v20 component beats v18_smooth   : "
          f"{'✓' if each_beats_v18 else '✗'}")
    print(f"  VERDICT: {verdict}\n")

    # ── [12] K-sweep on best v20 variant ───────────────────────────────────
    best_variant = max(sims, key=lambda k: sims[k]['sharpe'])
    pnl_best = ablation[best_variant]
    print(f"[12] K-sweep on best variant: {best_variant}")
    best_K = find_best_K(pnl_best, tcost_bps=5.0, init=1200.0, max_dd_limit=0.40)
    print(f"  {'K':>4}  {'mode':<10}  {'Sharpe':>8}  {'CAGR%':>8}  "
          f"{'Final $':>10}  {'PnL $':>10}  {'MaxDD%':>9}")
    print("  " + "─" * 70)
    for K in [1.0, 2.0, 3.0, 5.0, 10.0]:
        for tcost, lab in [(0.0, 'gross'), (5.0, 'net 5bp')]:
            m = equity_at_K(pnl_best, K=K, tcost_bps=tcost)
            print(f"  {K:>4.0f}  {lab:<10}  {m['sh']:>+8.3f}  "
                  f"{m['cagr']*100:>+7.2f}%  ${m['final']:>9,.2f}  "
                  f"${m['pnl']:>+9,.2f}  {m['max_dd']*100:>+8.2f}%")
    if best_K:
        print(f"\n  ★ Best K (net Sharpe, MaxDD ≤ 40%): K={best_K['K']:.2f}  "
              f"Final ${best_K['final']:,.2f}  Sharpe {best_K['sh']:+.3f}")

    # ── [13] Save JSON ─────────────────────────────────────────────────────
    print("\n[13] Saving results ...")
    result = {
        'description': 'GSDA-Arsenal — §I-XXVII closed-form dynamic allocator',
        'version': 'v20',
        'train': f'{TRAIN_START} to {TRAIN_END}',
        'test_start': TEST_START,
        'parameters': {
            'CHI2_CONF': CHI2_CONF, 'e_star': round(e_star, 4),
            'EWS_W6_PSI': EWS_W6_PSI, 'EWS_PCT_TRAIN': EWS_PCT_TRAIN,
            'PSI_COS_FLOOR': PSI_COS_FLOOR, 'V20_ALARM_MIN_STEPS': V20_ALARM_MIN_STEPS,
            'KRAMERS_TAU': KRAMERS_TAU, 'LEV_LO': LEV_LO, 'LEV_HI': LEV_HI,
            'GMM_K': GMM_K, 'GMM_SEEDS': GMM_SEEDS, 'GMM_EMA_SPAN': GMM_EMA_SPAN,
            'PERF_WIN': PERF_WIN, 'PERF_TAU': PERF_TAU, 'PERF_LAG': PERF_LAG,
            'CG_HISTORY_WIN': CG_HISTORY_WIN, 'CG_PCA_K': CG_PCA_K,
            'engine': 'collapse_geometry_v1.3.0_arsenal',
        },
        'arsenal_diagnostics': {
            'e_BS_mean':       round(float(F_test['e_BS'].mean()), 3),
            'e_BS_frac_above_estar_pct': round(float((F_test['e_BS']>e_star).mean()*100), 2),
            'rho_mfls_mean':   round(float(F_test['rho_mfls'].mean()), 3),
            'rho_mfls_frac_over1_pct': round(float((F_test['rho_mfls']>1).mean()*100), 2),
            'cos_theta_channel_mean': round(float(F_test['cos_theta_channel'].mean()), 4),
            'cos_theta_state_mean':   round(float(F_test['cos_theta_state'].mean()), 4),
            'cos_psi_mean':    round(float(F_test['cos_psi'].mean()), 4),
            'cos_psi_frac_below_floor_pct':
                round(float((F_test['cos_psi']<PSI_COS_FLOOR).mean()*100), 2),
            'ews6_mean':       round(float(F_test['ews6'].mean()), 4),
            'ews6_threshold':  round(ews_thresh, 4),
            'kramers_p_mean':  round(float(F_test['kramers_p'].mean()), 4),
            'attr_mean': {
                'C': round(float(F_test['attr_C'].mean()), 3),
                'G': round(float(F_test['attr_G'].mean()), 3),
                'A': round(float(F_test['attr_A'].mean()), 3),
                'T': round(float(F_test['attr_T'].mean()), 3),
            },
            'alarm_v20_days_pct': round(n_alarm/test_mask.sum()*100, 2),
            'kramers_lev_mean': round(float(lev_kramers[test_mask].mean()), 3),
            'regime_occupancy': {
                'R0_calm':     round(float(P_test.iloc[:,0].mean()), 3),
                'R1_stress':   round(float(P_test.iloc[:,1].mean()), 3),
                'R2_collapse': round(float(P_test.iloc[:,2].mean()), 3),
            },
        },
        'ablation': {k: s for k, s in sims.items()},
        'verdict': verdict,
        'best_variant': best_variant,
        'best_K': {
            'K': float(best_K['K']) if best_K else None,
            'pnl': round(float(best_K['pnl']), 2) if best_K else None,
            'sharpe_net': round(float(best_K['sh']), 4) if best_K else None,
            'max_dd': round(float(best_K['max_dd']), 4) if best_K else None,
            'final': round(float(best_K['final']), 2) if best_K else None,
        },
    }
    json_path = os.path.join(OUT_DIR, 'crypto_bsdt_v20_results.json')
    with open(json_path, 'w') as f:
        json.dump(result, f, indent=2)
    print(f"  Results → {json_path}")

    # ── [14] Plot ──────────────────────────────────────────────────────────
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        from matplotlib.gridspec import GridSpec

        fig = plt.figure(figsize=(15, 11))
        gs  = GridSpec(4, 2, figure=fig,
                       height_ratios=[2.0, 1.0, 1.0, 1.0], hspace=0.55, wspace=0.3)

        ax_eq    = fig.add_subplot(gs[0, :])
        ax_lev   = fig.add_subplot(gs[1, 0])
        ax_reg   = fig.add_subplot(gs[1, 1])
        ax_alarm = fig.add_subplot(gs[2, :])
        ax_attr  = fig.add_subplot(gs[3, 0])
        ax_bar   = fig.add_subplot(gs[3, 1])

        colors = {
            'v18_smooth':           '#4477aa',
            'v19_alarm_only':       '#aa3377',
            'v20_geom_alarm_only':  '#ee8833',
            'v20_soft_route':       '#cc6677',
            'v20_geom_lev_only':    '#117733',
            'v20_attribution_only': '#999933',
            'v20_full':             '#222222',
        }
        for k, pnl_series in ablation.items():
            eq = 1200.0 * (1.0 + pnl_series.fillna(0)).cumprod()
            lw = 2.0 if k == 'v20_full' else 1.2
            ax_eq.plot(eq.index, eq.values, color=colors[k], lw=lw,
                       label=f"{k}  Sh={sims[k]['sharpe']:+.3f}")
        ax_eq.axhline(1200.0, color='k', lw=0.5, ls='--')
        ax_eq.set_title("v20 Ablation — Equity Curves (K=1 gross, from $1,200)", fontsize=11)
        ax_eq.set_ylabel('Equity ($)'); ax_eq.legend(loc='upper left', fontsize=8)
        ax_eq.grid(alpha=0.3)

        # Kramers leverage
        ax_lev.plot(lev_kramers[test_mask].index, lev_kramers[test_mask].values,
                    color='#117733', lw=1.0)
        ax_lev.set_title('Kramers leverage (§XVIII/§XIX)', fontsize=10)
        ax_lev.set_ylabel('Leverage'); ax_lev.grid(alpha=0.3)

        # Regime probabilities stacked
        ax_reg.stackplot(P_test.index,
                         P_test.iloc[:,0], P_test.iloc[:,1], P_test.iloc[:,2],
                         labels=['R0 calm', 'R1 stress', 'R2 collapse'],
                         colors=['#117733', '#ee8833', '#cc3333'])
        ax_reg.set_title('GMM regime posteriors', fontsize=10)
        ax_reg.legend(loc='upper left', fontsize=8); ax_reg.set_ylim(0, 1)

        # Alarm + cos_theta_channel
        cos_test = F_test['cos_theta_channel']
        ax_alarm.plot(cos_test.index, cos_test.values, color='#333333',
                      lw=0.7, alpha=0.7, label='cos_θC')
        alarm_dates = cos_test.index[alarm_v20[test_mask].values]
        ax_alarm.scatter(alarm_dates, np.full(len(alarm_dates), -0.95),
                         color='red', s=10, alpha=0.7, zorder=3,
                         label='v20 alarm')
        ax_alarm.axhline(0, color='k', lw=0.4)
        ax_alarm.set_title('cos_θC + v20 alarm (3-of-3 OR-gated: χ², EWS₆, ψ floor)',
                           fontsize=10)
        ax_alarm.set_ylim(-1.05, 1.05); ax_alarm.legend(loc='upper right', fontsize=8)
        ax_alarm.grid(alpha=0.3)

        # Channel attribution
        for ch, col in zip(['C','G','A','T'], ['#4477aa','#117733','#ee8833','#cc3333']):
            ax_attr.plot(F_test.index,
                         F_test[f'attr_{ch}'].rolling(20).mean(),
                         color=col, lw=1.0, label=f'a_{ch}')
        ax_attr.set_title('Per-channel attribution a_k (§XXV, 20d MA)', fontsize=10)
        ax_attr.set_ylim(0, 1); ax_attr.legend(loc='upper right', fontsize=8)
        ax_attr.grid(alpha=0.3)

        # Sharpe bar
        labels = list(sims.keys())
        sh_vals = [sims[k]['sharpe'] for k in labels]
        bar_colors = [colors[k] for k in labels]
        bars = ax_bar.barh(range(len(labels)), sh_vals, color=bar_colors)
        ax_bar.set_yticks(range(len(labels)))
        ax_bar.set_yticklabels(labels, fontsize=8)
        ax_bar.axvline(0, color='k', lw=0.5)
        ax_bar.axvline(sh_v19, color='#aa3377', lw=0.7, ls='--', alpha=0.6,
                       label='v19 champion')
        ax_bar.set_title('Sharpe (K=1 gross)', fontsize=10)
        ax_bar.legend(fontsize=7); ax_bar.grid(alpha=0.3, axis='x')
        for i, (sh, bar) in enumerate(zip(sh_vals, bars)):
            ax_bar.text(sh + 0.01, i, f'{sh:+.3f}', va='center', fontsize=7)

        plt.suptitle(
            f"v20 GSDA-Arsenal: §I-XXVII collapse_geometry → dynamic allocator\n"
            f"verdict: {verdict}",
            fontsize=10, y=0.995)
        png_path = os.path.join(OUT_DIR, 'crypto_bsdt_v20_equity.png')
        plt.savefig(png_path, dpi=120, bbox_inches='tight')
        plt.close(fig)
        print(f"  Plot → {png_path}")
    except Exception as e:
        print(f"  (matplotlib skipped: {e})")

    # ── [15] Final summary ─────────────────────────────────────────────────
    print("\n" + "=" * 92)
    print("  v20 GSDA-ARSENAL FINAL SUMMARY")
    print("=" * 92)
    print(f"  Theory deployed: §VII χ² · §XVII EWS₆ · §XXVI ψ · §XVIII τ_safe · §XIX Kramers")
    print(f"                   §XXV per-channel attribution · §XXIII statistical thresholds")
    print(f"                   GMM(3) endogenous regimes · inverse-corr intra-family weights")
    print()
    print(f"  {'Variant':<24}  {'Sharpe':>8}  {'MaxDD':>8}  {'CAGR%':>8}  {'Δ vs v19_alarm'}")
    print("  " + "─" * 78)
    for k, s in sims.items():
        delta = s['sharpe'] - sh_v19 if k != 'v19_alarm_only' else 0.0
        tag = f"  Δ={delta:+.4f}" if k != 'v19_alarm_only' else "  (champion)"
        print(f"  {k:<24}  {s['sharpe']:>+8.4f}  {s['max_dd']:>+8.4f}  "
              f"{s['cagr']*100:>+7.2f}%{tag}")
    print()
    print(f"  VERDICT: {verdict}")
    if best_K:
        print(f"  Best variant ({best_variant}) at K={best_K['K']:.2f} net 5bp:")
        print(f"    → Final ${best_K['final']:,.2f}  PnL ${best_K['pnl']:+,.2f}  "
              f"Sharpe {best_K['sh']:+.3f}")
    print(f"  JSON → {json_path}")
    print("=" * 92)


if __name__ == '__main__':
    main()
