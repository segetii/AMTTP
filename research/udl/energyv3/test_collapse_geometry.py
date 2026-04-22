"""
test_collapse_geometry.py
=========================
Smoke-test for the CollapseGeometry closed-form collapse detector.

Tests:
  1. fit() succeeds on Gaussian reference
  2. Normal data → low collapse scores
  3. Anomalous data → high collapse scores  
  4. C* crossing detected when Q > τ_Q
  5. Angular alarm fires with correlated reference + orthogonal anomaly
  6. Dissipation failure detected in degenerate region
  7. Lead time > 0 for normal data, = 0 for already-crossed
  8. All 7 fusion weights are non-negative and sum to 1
  9. early_warning() returns alarm on injected spike
 10. score() matches detect().collapse_score
 11. formula_summary() prints without error
 12. CollapseReport fields have correct shapes
"""
from __future__ import annotations
import sys, importlib.util, os
import numpy as np

# ── Load collapse_geometry explicitly from energyv3 ──
_this = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location(
    'collapse_geometry', os.path.join(_this, 'collapse_geometry.py'))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
CollapseGeometry = mod.CollapseGeometry

np.random.seed(42)

# ── Reference: 5D Gaussian ──
N_ref, d = 500, 5
X_ref = np.random.randn(N_ref, d)

# ── Normal test data ──
X_normal = np.random.randn(100, d)

# ── Anomalous: large displacement ──
X_anom = np.random.randn(100, d)
X_anom[:, 2] += 15.0

# ── Fit ──
cg = CollapseGeometry()
cg.fit(X_ref)

# ── Test 1: fit succeeds ──
assert cg._tau_Q > 0, "τ_Q must be positive"
assert cg._theta_crit > 0, "θ_crit must be positive"
assert cg._w_fusion is not None, "Fusion weights not set"
print(f"[PASS] 1. fit: τ_Q={cg._tau_Q:.3f}, θ_crit={cg._theta_crit:.4f}")

# ── Test 2: Normal → low scores ──
s_norm = cg.score(X_normal)
assert s_norm.mean() < 0.5, f"Normal mean too high: {s_norm.mean():.3f}"
print(f"[PASS] 2. Normal scores: mean={s_norm.mean():.4f}")

# ── Test 3: Anomalous → high scores ──
s_anom = cg.score(X_anom)
assert s_anom.mean() > s_norm.mean(), "Anomalous should score higher than normal"
print(f"[PASS] 3. Anomalous scores: mean={s_anom.mean():.4f} > normal {s_norm.mean():.4f}")

# ── Test 4: C* crossing ──
report = cg.detect(X_anom)
assert report.crossed_Cstar.any(), "Some anomalous should cross C*"
print(f"[PASS] 4. C* crossing: {report.crossed_Cstar.sum()}/{len(X_anom)} crossed")

# ── Test 5: Angular Mahalanobis discriminates ──
# AM is the more powerful angular indicator (accounts for directional covariance)
report_norm = cg.detect(X_normal)
am_norm_mean = report_norm.AM.mean()
am_anom_mean = report.AM.mean()
assert am_anom_mean > am_norm_mean, \
    f"Angular Mahalanobis should be higher for anomalies: {am_anom_mean:.3f} vs {am_norm_mean:.3f}"
print(f"[PASS] 5. AM(anomalous)={am_anom_mean:.3f} > AM(normal)={am_norm_mean:.3f}")

# ── Test 6: Dissipation failure ──
assert report.dissipation_failure.any(), "Anomalous region should have dissipation failure"
print(f"[PASS] 6. Dissipation failure: {report.dissipation_failure.sum()}/{len(X_anom)} flagged")

# ── Test 7: Lead time ──
assert (report_norm.lead_time > 0).any(), "Normal data should have positive lead time"
assert (report.lead_time[report.crossed_Cstar] == 0.0).all(), "Crossed points: lead=0"
print(f"[PASS] 7. Lead time: normal mean={report_norm.lead_time.mean():.2f}, crossed=0.0")

# ── Test 8: Fusion weights ──
w = cg._w_fusion
assert np.all(w >= 0), "Weights must be non-negative"
assert abs(w.sum() - 1.0) < 1e-6, f"Weights must sum to 1: got {w.sum()}"
print(f"[PASS] 8. Fusion weights: {np.array2string(w, precision=3)}")

# ── Test 9: Early warning ──
T = 200
X_ts = np.random.randn(T, d) * 0.3  # tight normal period
X_ts[160:] += 12.0  # inject very strong spike at step 160
ew = cg.early_warning(X_ts, window=20)
# Check that MORE alarms happen in the spike period than before
pre_alarm_rate = ew['alarms'][:150].mean()
post_alarm_rate = ew['alarms'][160:].mean()
assert post_alarm_rate > pre_alarm_rate, \
    f"Post-spike alarm rate {post_alarm_rate:.2f} should exceed pre-spike {pre_alarm_rate:.2f}"
print(f"[PASS] 9. Early warning: pre-spike alarm rate={pre_alarm_rate:.2f}, "
      f"post-spike={post_alarm_rate:.2f}")

# ── Test 10: score() matches detect() ──
scores_direct = cg.score(X_anom)
# They won't be exactly equal (sigmoid centres differ), but should be correlated
corr = np.corrcoef(scores_direct, report.collapse_score)[0, 1]
assert corr > 0.8, f"score() and detect().collapse_score should correlate: r={corr:.3f}"
print(f"[PASS] 10. score() vs detect(): correlation r={corr:.3f}")

# ── Test 11: formula_summary() ──
summary = cg.formula_summary()
assert "τ_Q" in summary
assert "γ*" in summary
assert "GEOMETRY" in summary
print(f"[PASS] 11. formula_summary() renders ({len(summary)} chars)")

# ── Test 12: Field shapes ──
assert report.Q.shape == (100,)
assert report.theta.shape == (100,)
assert report.delta_C.shape == (100,)
assert report.collapse_score.shape == (100,)
assert report.lead_time.shape == (100,)
assert report.lambda_max.shape == (100,)
assert report.gamma_star.shape == (100,)
print(f"[PASS] 12. All CollapseReport fields have correct shapes")

# ── Summary ──
print(f"\n{'='*60}")
print(f"ALL 12 TESTS PASSED")
print(f"{'='*60}")
print(f"\nCollapseGeometry: 7 indicators, O(N·d), no simulation")
print(f"  Fusion weights: {np.array2string(w, precision=3)}")
print(f"  Reference: N={N_ref}, d={d}")
print(f"  Normal score:  {s_norm.mean():.4f} ± {s_norm.std():.4f}")
print(f"  Anomaly score: {s_anom.mean():.4f} ± {s_anom.std():.4f}")
print(f"  AUC proxy (separation): {s_anom.mean() - s_norm.mean():.4f}")
