"""
Fix Mode6 to handle both supervised (labels available) and unsupervised (y=0) cases.

When y has crisis labels (sum > 0): use supervised MFLSQuadSurf (ridge regression)
When y is all zeros: use unsupervised BSDTChannels score_quadsurf/expogate (Fisher VR)

Both cases: NO blending with base scorer. Stacked layer IS the final score.
"""
import sys, os

FILE = os.path.join('research', 'udl', 'udl', 'system_mode.py')

with open(FILE, encoding='utf-8') as f:
    content = f.read()

# Find the Phase 3 section in Mode6's fit_score
old_phase3 = '''        # ══════════════════════════════════════════════════════════
        #  Phase 3: MFLS stacked layer (supervised ridge)
        # ══════════════════════════════════════════════════════════
        if y is not None:
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
            # Unsupervised fallback: raw BSDT score
            scores = bsdt_scorer.score(X_scored)'''

new_phase3 = '''        # ══════════════════════════════════════════════════════════
        #  Phase 3: MFLS stacked layer on BSDT channels
        #
        #  Supervised (y has crisis labels) → MFLSQuadSurf / ExpoGate
        #  with polynomial ridge regression on channels.
        #
        #  Unsupervised (y=0 or None) → BSDTChannels score_quadsurf /
        #  score_expogate (Fisher VR weights, no labels needed).
        #
        #  In both cases: the stacked layer IS the final score.
        #  No blending with a separate base scorer.
        # ══════════════════════════════════════════════════════════
        has_labels = y is not None and y.sum() > 0

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

assert old_phase3 in content, "Phase 3 block not found!"
content = content.replace(old_phase3, new_phase3)

with open(FILE, 'w', encoding='utf-8') as f:
    f.write(content)

# Verify
with open(FILE, encoding='utf-8') as f:
    v = f.read()
assert 'has_labels = y is not None and y.sum() > 0' in v
assert 'Supervised stacking' in v
assert 'Unsupervised stacking' in v
print("Done. Mode6 now handles both supervised and unsupervised cases.")
print("  Supervised: MFLSQuadSurf/ExpoGate (ridge regression on channels)")
print("  Unsupervised: BSDTChannels score_quadsurf/expogate (Fisher VR)")
print("  Both: NO blending. Stacked layer IS the final score.")
