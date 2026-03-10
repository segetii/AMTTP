"""
Patch script: Add BSDTChannels to system_mode.py on disk.

Performs 4 patches:
  1. Insert BSDTChannels class before FusedSystemScorer
  2. Update FusedSystemScorer (docstring, __init__, fit, _enrich_score)
  3. Update module docstring (Fused Scoring section)
  4. Update MolecularEngine.fit_score docstring
"""
import re

FILE = r'c:\amttp\research\udl\udl\system_mode.py'

with open(FILE, 'r', encoding='utf-8') as f:
    src = f.read()

# ═══════════════════════════════════════════════════════════════════
#  PATCH 1: Insert BSDTChannels class before FusedSystemScorer
# ═══════════════════════════════════════════════════════════════════

BSDT_CLASS = r'''

# ═══════════════════════════════════════════════════════════════════
#  BSDT CHANNELS (Blind-Spot Detection Tensor)
# ═══════════════════════════════════════════════════════════════════

class BSDTChannels:
    r"""
    Blind-Spot Detection Tensor — four complementary anomaly channels.

    Implements the BSDT framework (SIAM paper, Section 2.2) in a
    domain-agnostic form suitable for post-simulation scoring:

    Channels
    --------
    δ_C : Camouflage
        How well a point blends with the normal cluster.
        ``δ_C = 1 − clip(‖x − μ_ref‖ / d_max, 0, 1)``
        High → point looks normal (potential blind spot).

    δ_G : Feature Gap
        Structural sparsity / incompleteness in features.
        ``δ_G = fraction of near-zero features (|x_j/σ_j| < 0.1)``
        High → abnormally sparse feature representation.

    δ_A : Activity Anomaly
        Mahalanobis deviation from normal reference centroid.
        ``δ_A = sigmoid((mahal − median_ref) / median_ref)``
        High → activity level deviates from normal.

    δ_T : Temporal Novelty
        kNN novelty relative to reference distribution.
        ``δ_T = sigmoid(0.5 · (d_kNN / median_kNN_ref − 2))``
        High → point is far from anything seen in reference.

    Composite Scores
    ----------------
    E_BS = Σ δ_i²           (blind-spot energy)
    MFLS = ‖∇E_BS‖_F        (multi-factor latent score)
    """

    def __init__(self, k: int = 15, eps: float = 1e-8):
        self.k = k
        self.eps = eps
        self._fitted = False

    def fit(self, X_ref: np.ndarray) -> 'BSDTChannels':
        """
        Calibrate BSDT channels on normal reference data.

        Parameters
        ----------
        X_ref : array (n_ref, d)
            Normal-class post-simulation positions.
        """
        self.mu_ = X_ref.mean(axis=0)
        self.n_ref_, self.d_ = X_ref.shape

        # δ_C calibration: max distance from centroid in reference
        dists_ref = np.linalg.norm(X_ref - self.mu_, axis=1)
        self.d_max_ = max(float(dists_ref.max()), self.eps)

        # δ_A calibration: regularised inverse covariance
        cov = np.cov(X_ref, rowvar=False)
        if cov.ndim < 2:
            cov = np.atleast_2d(cov)
        reg = self.eps * np.eye(self.d_)
        self.cov_inv_ = np.linalg.inv(cov + reg)
        self.mahal_ref_median_ = float(np.median(self._mahalanobis(X_ref)))

        # δ_T calibration: kNN distances in reference
        from sklearn.neighbors import NearestNeighbors
        k_use = min(self.k, self.n_ref_ - 1)
        nn = NearestNeighbors(n_neighbors=k_use + 1, algorithm='auto')
        nn.fit(X_ref.astype(np.float32))
        ref_dists, _ = nn.kneighbors(X_ref.astype(np.float32))
        self.ref_knn_median_ = float(np.median(ref_dists[:, -1]))
        self.nn_ = nn

        # Feature-level stats for δ_G
        self.feat_std_ = np.std(X_ref, axis=0) + self.eps

        self._fitted = True
        return self

    def _mahalanobis(self, X: np.ndarray) -> np.ndarray:
        """Per-point Mahalanobis distance from reference centroid."""
        diff = X - self.mu_
        return np.sqrt(np.maximum(
            np.sum(diff @ self.cov_inv_ * diff, axis=1), 0.0
        ))

    def channels(self, X: np.ndarray) -> dict:
        """
        Compute all four BSDT channels.

        Returns dict with keys 'delta_C', 'delta_G', 'delta_A', 'delta_T'.
        """
        # δ_C: Camouflage — proximity to normal centroid
        dist_from_mu = np.linalg.norm(X - self.mu_, axis=1)
        delta_C = 1.0 - np.clip(dist_from_mu / self.d_max_, 0.0, 1.0)

        # δ_G: Feature Gap — fraction of near-zero features
        X_normed = np.abs(X) / self.feat_std_
        delta_G = np.mean(X_normed < 0.1, axis=1).astype(np.float64)

        # δ_A: Activity Anomaly — sigmoid of Mahalanobis deviation
        mahal = self._mahalanobis(X)
        z_a = (mahal - self.mahal_ref_median_) / max(
            self.mahal_ref_median_, self.eps)
        delta_A = 1.0 / (1.0 + np.exp(-np.clip(z_a, -30, 30)))

        # δ_T: Temporal Novelty — kNN distance ratio (sigmoid)
        k_use = min(self.k, self.n_ref_ - 1)
        dists, _ = self.nn_.kneighbors(X.astype(np.float32))
        knn_col = min(k_use, dists.shape[1] - 1)
        knn_dist = dists[:, knn_col].astype(np.float64)
        ratio = knn_dist / max(self.ref_knn_median_, self.eps)
        delta_T = 1.0 / (1.0 + np.exp(-np.clip(
            0.5 * (ratio - 2.0), -30, 30)))

        return {'delta_C': delta_C, 'delta_G': delta_G,
                'delta_A': delta_A, 'delta_T': delta_T}

    def energy(self, X: np.ndarray) -> np.ndarray:
        r"""E_BS = Σ_i δ_i(x)² — blind-spot energy per point."""
        ch = self.channels(X)
        return (ch['delta_C'] ** 2 + ch['delta_G'] ** 2 +
                ch['delta_A'] ** 2 + ch['delta_T'] ** 2)

    def mfls(self, X: np.ndarray) -> np.ndarray:
        r"""
        MFLS = ‖∇E_BS‖_F — gradient norm of blind-spot energy.

        Uses analytical gradients through δ_C (Euclidean) and
        δ_A (Mahalanobis), which dominate the gradient landscape.
        δ_G and δ_T have discontinuous / kNN-based gradients and
        contribute negligibly to ∇E_BS.
        """
        ch = self.channels(X)
        diff = X - self.mu_

        # ── Gradient through δ_A (Mahalanobis, dominant) ──
        mahal = self._mahalanobis(X)
        mahal_safe = np.maximum(mahal, self.eps)
        grad_mahal = (diff @ self.cov_inv_) / mahal_safe[:, None]

        sig_deriv = ch['delta_A'] * (1.0 - ch['delta_A'])
        scale_A = (2.0 * ch['delta_A'] * sig_deriv /
                   max(self.mahal_ref_median_, self.eps))
        grad_E_A = scale_A[:, None] * grad_mahal

        # ── Gradient through δ_C (Euclidean distance) ──
        dist = np.linalg.norm(diff, axis=1, keepdims=True)
        dist_safe = np.maximum(dist, self.eps)
        unit = diff / dist_safe
        active = (dist.squeeze() < self.d_max_).astype(np.float64)
        scale_C = -2.0 * ch['delta_C'] * active / self.d_max_
        grad_E_C = scale_C[:, None] * unit

        # Total gradient
        grad_E = grad_E_A + grad_E_C
        return np.linalg.norm(grad_E, axis=1)

    def score(self, X: np.ndarray) -> np.ndarray:
        """
        Combined BSDT score = blend(E_BS, MFLS).

        Returns per-point score in [0, 1] via min-max normalisation
        of both components, then equal-weight average.
        """
        e = self.energy(X)
        m = self.mfls(X)

        # Normalise each to [0, 1]
        e_max = max(float(e.max()), self.eps)
        m_max = max(float(m.max()), self.eps)
        e_n = e / e_max
        m_n = m / m_max

        return 0.5 * e_n + 0.5 * m_n

'''

# Anchor: insert before "# ═══...FUSED SYSTEM SCORER..."
anchor = '# ═══════════════════════════════════════════════════════════════════\n#  FUSED SYSTEM SCORER\n# ═══════════════════════════════════════════════════════════════════'
assert anchor in src, "Could not find FUSED SYSTEM SCORER anchor"
src = src.replace(anchor, BSDT_CLASS.rstrip('\n') + '\n\n' + anchor, 1)

# ═══════════════════════════════════════════════════════════════════
#  PATCH 2: Update FusedSystemScorer docstring
# ═══════════════════════════════════════════════════════════════════

OLD_DOCSTRING = '''    """
    Combines Morse topology alarm + Betti barcode suite + UDL
    operator ensemble into a single anomaly scorer.

    Architecture
    ------------
    1. **MorseTopologyAlarm** — kNN distance features (4D):
       Mean kNN, d₁, persistence proxy, density ratio.
       Scales to any N via kNN search.

    2. **BettiBarcodeSuite** — multi-scale topology (3 + 2·ns D):
       β₀/β₁/χ curves, Conley stability.
       Scales to any N via kNN search.

    3. **UDLPostSimScorer** — best-4 UDL operators (~27D):
       Phase + Topological + KernelRKHS + Rank.
       Applied to simulation subset, kNN-interpolated for full data.

    Fusion: min-max normalise each component, equal-weight average.
    For simulation-size inputs, all three score directly.
    For larger inputs, Morse + Betti score directly (fast kNN),
    while UDL scores are kNN-interpolated from the simulation subset.
    """'''

NEW_DOCSTRING = '''    """
    Combines four complementary signal families into a single scorer.

    Architecture
    ------------
    1. **MorseTopologyAlarm** — kNN distance features (4D):
       Mean kNN, d₁, persistence proxy, density ratio.
       Scales to any N via kNN search.

    2. **BettiBarcodeSuite** — multi-scale topology (3 + 2·ns D):
       β₀/β₁/χ curves, Conley stability.
       Scales to any N via kNN search.

    3. **UDLPostSimScorer** — best-4 UDL operators (~27D):
       Phase + Topological + KernelRKHS + Rank.
       Applied to simulation subset, kNN-interpolated for full data.

    4. **BSDTChannels** — Blind-Spot Detection Tensor (4 channels):
       δ_C (camouflage) + δ_G (feature gap) + δ_A (activity anomaly)
       + δ_T (temporal novelty) → E_BS + MFLS composite.
       Implements the BSDT framework from Section 2.2 of the paper.

    Fusion: min-max normalise each component, equal-weight average.
    For simulation-size inputs, all four score directly.
    For larger inputs, Morse + Betti + BSDT score directly (fast kNN),
    while UDL scores are kNN-interpolated from the simulation subset.
    """'''

assert OLD_DOCSTRING in src, "Could not find FusedSystemScorer old docstring"
src = src.replace(OLD_DOCSTRING, NEW_DOCSTRING, 1)

# ═══════════════════════════════════════════════════════════════════
#  PATCH 3: Update FusedSystemScorer.__init__ to add BSDT
# ═══════════════════════════════════════════════════════════════════

OLD_INIT = '''    def __init__(self, k: int = 15, use_betti: bool = True,
                 use_udl: bool = True):
        self.k = k
        self.morse = MorseTopologyAlarm(k=k)
        self.betti = BettiBarcodeSuite(k=min(k + 5, 25)) if use_betti else None
        self.udl = UDLPostSimScorer(k=k) if use_udl else None
        self._X_sim = None
        self._sim_enriched = None'''

NEW_INIT = '''    def __init__(self, k: int = 15, use_betti: bool = True,
                 use_udl: bool = True, use_bsdt: bool = True):
        self.k = k
        self.morse = MorseTopologyAlarm(k=k)
        self.betti = BettiBarcodeSuite(k=min(k + 5, 25)) if use_betti else None
        self.udl = UDLPostSimScorer(k=k) if use_udl else None
        self.bsdt = BSDTChannels(k=k) if use_bsdt else None
        self._X_sim = None
        self._sim_enriched = None'''

assert OLD_INIT in src, "Could not find FusedSystemScorer.__init__"
src = src.replace(OLD_INIT, NEW_INIT, 1)

# ═══════════════════════════════════════════════════════════════════
#  PATCH 4: Update FusedSystemScorer.fit to fit BSDT
# ═══════════════════════════════════════════════════════════════════

OLD_FIT_TAIL = '''        if self.udl is not None:
            try:
                self.udl.fit(X_ref)
            except Exception:
                self.udl = None

        # Pre-compute enriched scores on simulation subset'''

NEW_FIT_TAIL = '''        if self.udl is not None:
            try:
                self.udl.fit(X_ref)
            except Exception:
                self.udl = None

        if self.bsdt is not None:
            try:
                self.bsdt.fit(X_ref)
            except Exception:
                self.bsdt = None

        # Pre-compute enriched scores on simulation subset'''

assert OLD_FIT_TAIL in src, "Could not find FusedSystemScorer.fit tail"
src = src.replace(OLD_FIT_TAIL, NEW_FIT_TAIL, 1)

# ═══════════════════════════════════════════════════════════════════
#  PATCH 5: Update _enrich_score to include BSDT
# ═══════════════════════════════════════════════════════════════════

OLD_ENRICH = '''    def _enrich_score(self, X: np.ndarray) -> np.ndarray:
        """Full multi-view scoring (≤ simulation-size inputs)."""
        components = [self.morse.score(X)]

        if self.betti is not None:
            try:
                components.append(self.betti.score(X))
            except Exception:
                pass
        if self.udl is not None and self.udl._fitted:
            try:
                components.append(self.udl.score(X))
            except Exception:
                pass

        normed = [self._minmax(s) for s in components]
        return np.mean(normed, axis=0)'''

NEW_ENRICH = '''    def _enrich_score(self, X: np.ndarray) -> np.ndarray:
        """Full multi-view scoring (≤ simulation-size inputs).

        Fuses four signal families:
          Morse (topology) + Betti (persistence) + UDL (operators)
          + BSDT (blind-spot channels: δ_C, δ_G, δ_A, δ_T, E_BS, MFLS).
        """
        components = [self.morse.score(X)]

        if self.betti is not None:
            try:
                components.append(self.betti.score(X))
            except Exception:
                pass
        if self.udl is not None and self.udl._fitted:
            try:
                components.append(self.udl.score(X))
            except Exception:
                pass
        if self.bsdt is not None and self.bsdt._fitted:
            try:
                components.append(self.bsdt.score(X))
            except Exception:
                pass

        normed = [self._minmax(s) for s in components]
        return np.mean(normed, axis=0)'''

assert OLD_ENRICH in src, "Could not find _enrich_score"
src = src.replace(OLD_ENRICH, NEW_ENRICH, 1)

# ═══════════════════════════════════════════════════════════════════
#  PATCH 6: Update module docstring
# ═══════════════════════════════════════════════════════════════════

OLD_MODDOC = '''Fused Scoring (v2)
------------------
  Post-simulation positions are scored by three complementary signal
  families, then fused via min-max normalisation + equal-weight average:

  1. **MorseTopologyAlarm** — kNN distance features (4D)
  2. **BettiBarcodeSuite** — multi-scale β₀/β₁/χ/Conley (19D)
  3. **UDLPostSimScorer**  — best-4 UDL operators: Phase + Topological
     + KernelRKHS + Rank (≈27D), mAUC 0.972 on paper benchmarks'''

NEW_MODDOC = '''Fused Scoring (v2)
------------------
  Post-simulation positions are scored by four complementary signal
  families, then fused via min-max normalisation + equal-weight average:

  1. **MorseTopologyAlarm** — kNN distance features (4D)
  2. **BettiBarcodeSuite** — multi-scale β₀/β₁/χ/Conley (19D)
  3. **UDLPostSimScorer**  — best-4 UDL operators: Phase + Topological
     + KernelRKHS + Rank (≈27D), mAUC 0.972 on paper benchmarks
  4. **BSDTChannels**      — Blind-Spot Detection Tensor (4 channels):
     δ_C (camouflage) + δ_G (feature gap) + δ_A (activity anomaly)
     + δ_T (temporal novelty) → E_BS + MFLS composite score.
     Implements the BSDT framework (SIAM paper, Section 2.2).'''

assert OLD_MODDOC in src, "Could not find module docstring fused scoring section"
src = src.replace(OLD_MODDOC, NEW_MODDOC, 1)

# ═══════════════════════════════════════════════════════════════════
#  PATCH 7: Update MolecularEngine.fit_score docstring
# ═══════════════════════════════════════════════════════════════════

OLD_MOLDOC = 'Scores are produced by the FusedSystemScorer (Morse + Betti +\n        UDL operators)'
NEW_MOLDOC = 'Scores are produced by the FusedSystemScorer (Morse + Betti +\n        UDL + BSDT operators)'

if OLD_MOLDOC in src:
    src = src.replace(OLD_MOLDOC, NEW_MOLDOC, 1)

# ═══════════════════════════════════════════════════════════════════
#  WRITE BACK
# ═══════════════════════════════════════════════════════════════════

with open(FILE, 'w', encoding='utf-8') as f:
    f.write(src)

# Verify
with open(FILE, 'r', encoding='utf-8') as f:
    final = f.read()

assert 'class BSDTChannels' in final, "BSDTChannels class not found!"
assert 'use_bsdt: bool = True' in final, "use_bsdt param not found!"
assert 'self.bsdt = BSDTChannels' in final, "bsdt instance not found!"
assert 'self.bsdt.fit(X_ref)' in final, "bsdt.fit not found!"
assert 'self.bsdt.score(X)' in final, "bsdt.score not found!"

import re
classes = [m.group(1) for m in re.finditer(r'^class (\w+)', final, re.MULTILINE)]
print(f"✓ Patch applied successfully. {len(final.splitlines())} lines.")
print(f"  Classes: {classes}")
print(f"  BSDTChannels at line ~{final[:final.index('class BSDTChannels')].count(chr(10))+1}")
