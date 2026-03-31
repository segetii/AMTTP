"""Add _MFLSFisherBSDT class and wire posthoc='fisher' into Mode6."""
import os

FILE = os.path.join('research', 'udl', 'udl', 'system_mode.py')

with open(FILE, encoding='utf-8') as f:
    content = f.read()

# ── 1. Insert _MFLSFisherBSDT class before the Mode6 banner ──

FISHER_CLASS = '''
class _MFLSFisherBSDT:
    """BSDT baseline with Fisher VR dynamic channel weighting.

    Unsupervised correction layer: determines channel weights from
    data regime splits (80th / 50th percentile of total channel
    magnitude).  No polynomial features, no labels.

    Score = Σ_k  w_k · c̃_k

    where  c̃_k  is min-max normalised channel k, and
    w_k = Fisher variance-ratio of channel k between high-regime
    and low-regime samples (data-driven, zero heuristics).

    Reference: Odeyemi O.I., "Blind Spot Decomposition Theory", 2025.
    """

    def __init__(self, eps: float = 1e-10):
        self.eps = eps
        self.w_ = None
        self.lo_ = None
        self.hi_ = None

    def fit(self, channels, y=None):
        """Compute Fisher VR weights from channel regime splits.

        Parameters
        ----------
        channels : (T, K) array — raw BSDT channel scores.
        y : ignored (unsupervised).  Accepts for API compat.
        """
        T, K = channels.shape

        # Min-max normalise each channel
        self.lo_ = channels.min(axis=0)
        self.hi_ = channels.max(axis=0)
        span = self.hi_ - self.lo_
        span = np.where(span < self.eps, 1.0, span)
        C_n = (channels - self.lo_) / span

        # Regime split on total normalised magnitude
        total = C_n.sum(axis=1)
        p80 = np.percentile(total, 80)
        p50 = np.percentile(total, 50)
        hi_mask = total >= p80
        lo_mask = total <= p50

        if hi_mask.sum() >= 2 and lo_mask.sum() >= 2:
            fr = np.zeros(K)
            for k in range(K):
                mu_h = C_n[hi_mask, k].mean()
                mu_l = C_n[lo_mask, k].mean()
                var_h = C_n[hi_mask, k].var()
                var_l = C_n[lo_mask, k].var()
                fr[k] = (mu_h - mu_l) ** 2 / max(var_h + var_l, self.eps)
            total_fr = fr.sum()
            self.w_ = fr / total_fr if total_fr > self.eps else np.ones(K) / K
        else:
            self.w_ = np.ones(K) / K

        return self

    def score(self, channels):
        """Fisher-weighted normalised channel sum."""
        span = self.hi_ - self.lo_
        span = np.where(span < self.eps, 1.0, span)
        C_n = np.clip((channels - self.lo_) / span, 0.0, 1.0)
        return (C_n * self.w_).sum(axis=1)

'''

# Find the Mode6 banner
mode6_banner = '# ═══════════════════════════════════════════════'
# Find the one just before 'MODE-6 GRAVITY ENGINE'
idx = content.find('MODE-6 GRAVITY ENGINE')
if idx < 0:
    raise ValueError("MODE-6 GRAVITY ENGINE banner not found!")
banner_start = content.rfind('\n# ═══', 0, idx)
if banner_start < 0:
    raise ValueError("Banner not found before MODE-6!")

content = content[:banner_start] + '\n' + FISHER_CLASS + content[banner_start:]

# ── 2. Update Mode6 docstring ──
old_doc = '''    """BSDT-damped gravity with MFLS stacked post-hoc scorer.

    Architecture (3-layer stack):
        Layer 1 — BSDT adaptive damping in the gravity iteration loop.
                  Uses gradient descent + Lyapunov ISS for iterating.
                  BSDT is for iteration, NOT for scoring.
        Layer 2 — BSDT channel extraction on final positions.
                  Produces (N, 4) channel matrix:
                  [delta_C, delta_G, delta_A, delta_T]
        Layer 3 — MFLSQuadSurf or MFLSExpoGate stacked on channels.
                  Supervised polynomial ridge regression (labels = y).
                  This IS the final score — no blending.

    QuadSurf: degree-2 polynomial features + ridge regression
        score = max(0, Phi @ beta)
        where Phi = [1, c1..c4, c1^2, c1*c2, ..., c4^2]
        and beta = (Phi^T Phi + alpha I)^-1 Phi^T y

    ExpoGate: QuadSurf output -> tanh saturation -> sigmoid gating
        score = sigmoid(scale * tanh(QuadSurf / sigma))

    Parameters
    ----------
    posthoc : str
        Stacked layer type: ``'quadsurf'`` or ``'expogate'``.'''

new_doc = '''    """BSDT-damped gravity with stacked post-hoc correction layer.

    Architecture (3-layer stack):
        Layer 1 — BSDT adaptive damping in the gravity iteration loop.
                  Uses gradient descent + Lyapunov ISS for iterating.
                  BSDT is for iteration, NOT for scoring.
        Layer 2 — BSDT channel extraction on final positions.
                  Produces (N, 4) channel matrix:
                  [delta_C, delta_G, delta_A, delta_T]
        Layer 3 — Stacked correction layer on channels.
                  This IS the final score — no blending.

    Correction layers (``posthoc`` parameter):

    ``'fisher'`` — BSDT baseline with Fisher VR dynamic weights.
        Unsupervised.  score = Σ w_k · c̃_k  where weights come
        from Fisher variance-ratio regime splits on the channels.

    ``'quadsurf'`` — degree-2 polynomial features + ridge regression.
        Supervised (needs crisis labels).
        score = max(0, Φ·β)  where β = (ΦᵀΦ + αI)⁻¹Φᵀy

    ``'expogate'`` — QuadSurf → tanh saturation → sigmoid gating.
        Supervised (needs crisis labels).
        score = sigmoid(scale · tanh(QuadSurf / σ))

    Parameters
    ----------
    posthoc : str
        Stacked layer: ``'fisher'``, ``'quadsurf'``, or ``'expogate'``.'''

assert old_doc in content, f"Old docstring not found! Searching near Mode6..."
content = content.replace(old_doc, new_doc)

# ── 3. Update Phase 3 to handle posthoc='fisher' ──
old_phase3 = '''        has_labels = y is not None and y.sum() > 0

        if has_labels:
            # ── Supervised stacking: MFLSQuadSurf / ExpoGate ──
            # Crisis labels → ridge regression on polynomial channel features
            y_scored = y.astype(float)
            if self.posthoc == 'expogate':
                layer = _MFLSExpoGate(
                    ridge_alpha=self.ridge_alpha,
                    smooth_sigma=self.smooth_sigma,
                    gate_scale=self.gate_scale,
                )
            else:
                layer = _MFLSQuadSurf(ridge_alpha=self.ridge_alpha)

            layer.fit(C, y_scored)
            scores = layer.score(C)
        else:
            # ── Unsupervised stacking: Fisher VR on channels ──
            # Same polynomial structure, weights from data regime splits
            if self.posthoc == 'expogate':
                bsdt_scorer.fit_expogate(X_ref_final)
                scores = bsdt_scorer.score_expogate(X_scored)
            else:
                bsdt_scorer.fit_quadsurf(X_ref_final)
                scores = bsdt_scorer.score_quadsurf(X_scored)'''

new_phase3 = '''        has_labels = y is not None and y.sum() > 0

        if self.posthoc == 'fisher':
            # ── BSDT baseline: Fisher VR dynamic weights (unsupervised) ──
            layer = _MFLSFisherBSDT()
            layer.fit(C)   # no labels needed
            scores = layer.score(C)

        elif has_labels:
            # ── Supervised stacking: MFLSQuadSurf / ExpoGate ──
            # Crisis labels → ridge regression on polynomial channel features
            y_scored = y.astype(float)
            if self.posthoc == 'expogate':
                layer = _MFLSExpoGate(
                    ridge_alpha=self.ridge_alpha,
                    smooth_sigma=self.smooth_sigma,
                    gate_scale=self.gate_scale,
                )
            else:
                layer = _MFLSQuadSurf(ridge_alpha=self.ridge_alpha)

            layer.fit(C, y_scored)
            scores = layer.score(C)
        else:
            # ── Unsupervised stacking: Fisher VR on channels ──
            # Same polynomial structure, weights from data regime splits
            if self.posthoc == 'expogate':
                bsdt_scorer.fit_expogate(X_ref_final)
                scores = bsdt_scorer.score_expogate(X_scored)
            else:
                bsdt_scorer.fit_quadsurf(X_ref_final)
                scores = bsdt_scorer.score_quadsurf(X_scored)'''

assert old_phase3 in content, "Phase 3 block not found!"
content = content.replace(old_phase3, new_phase3)

# ── Write ──
with open(FILE, 'w', encoding='utf-8') as f:
    f.write(content)

# ── Verify ──
with open(FILE, encoding='utf-8') as f:
    v = f.read()
assert 'class _MFLSFisherBSDT:' in v, "_MFLSFisherBSDT missing!"
assert "posthoc == 'fisher'" in v, "fisher branch missing!"
assert 'class Mode6GravityEngine:' in v
assert 'class HybridGravityEngine:' in v
assert 'class Mode5GravityEngine:' in v
assert 'class Mode4GravityEngine:' in v
print("Done. _MFLSFisherBSDT added, Mode6 now supports posthoc='fisher'.")
print(f"Total lines: {v.count(chr(10)) + 1}")
