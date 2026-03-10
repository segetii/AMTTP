"""
Patch: Add BSDTChannels to ReducedTensorDescriptor._reference_score.

Adds BSDT as a 4th view in the multi-view scoring fusion:
  View A: Raw-space (kNN + Mahalanobis)          35%
  View B: Descriptor-space kNN                   25%
  View C: Descriptor-native (Z-scored topology)  25%
  View D: BSDT channels (E_BS + MFLS)            15%  [NEW]
"""

FILE = r'c:\amttp\research\udl\udl\system_mode.py'

with open(FILE, 'r', encoding='utf-8') as f:
    src = f.read()

# ═══════════════════════════════════════════════════════════════════
#  PATCH 1: Add BSDT view to _reference_score fusion
# ═══════════════════════════════════════════════════════════════════

OLD_FUSION = '''        # View A: Raw-space scoring (captures simple separability)
        v_raw = (0.50 * robust_norm(z_raw_knn) +
                 0.50 * robust_norm(raw_knn_mean))

        # View B: Descriptor-space kNN (captures topology-transformed distances)
        v_knn = (0.35 * robust_norm(z_knn) +
                 0.30 * robust_norm(knn_d1) +
                 0.20 * robust_norm(knn_persist) +
                 0.15 * robust_norm(knn_mean))

        # View C: Descriptor-native (Z-scored topology features)
        v_desc = (0.25 * robust_norm(z_grad) +
                  0.30 * robust_norm(z_maha) +
                  0.15 * robust_norm(z_med) +
                  0.10 * robust_norm(z_trace) +
                  0.20 * robust_norm(z_morse))

        # Fuse: 40% raw-space + 30% descriptor-kNN + 30% topology
        scores = 0.40 * v_raw + 0.30 * v_knn + 0.30 * v_desc
        return scores'''

NEW_FUSION = '''        # View A: Raw-space scoring (captures simple separability)
        v_raw = (0.50 * robust_norm(z_raw_knn) +
                 0.50 * robust_norm(raw_knn_mean))

        # View B: Descriptor-space kNN (captures topology-transformed distances)
        v_knn = (0.35 * robust_norm(z_knn) +
                 0.30 * robust_norm(knn_d1) +
                 0.20 * robust_norm(knn_persist) +
                 0.15 * robust_norm(knn_mean))

        # View C: Descriptor-native (Z-scored topology features)
        v_desc = (0.25 * robust_norm(z_grad) +
                  0.30 * robust_norm(z_maha) +
                  0.15 * robust_norm(z_med) +
                  0.10 * robust_norm(z_trace) +
                  0.20 * robust_norm(z_morse))

        # View D: BSDT channels (blind-spot detection, Section 2.2)
        #   Fits BSDTChannels on reference data and scores all points
        #   via E_BS (energy) + MFLS (gradient norm) composite.
        bsdt = BSDTChannels(k=min(10, max(2, len(X_ref) - 1)))
        bsdt.fit(X_ref)
        v_bsdt = robust_norm(bsdt.score(X))

        # Fuse: 35% raw + 25% descriptor-kNN + 25% topology + 15% BSDT
        scores = (0.35 * v_raw + 0.25 * v_knn +
                  0.25 * v_desc + 0.15 * v_bsdt)
        return scores'''

assert OLD_FUSION in src, "Could not find _reference_score fusion block"
src = src.replace(OLD_FUSION, NEW_FUSION, 1)

# ═══════════════════════════════════════════════════════════════════
#  PATCH 2: Update _reference_score docstring to mention BSDT
# ═══════════════════════════════════════════════════════════════════

OLD_REFDOC = '''        """Score X by multi-view deviation from reference distribution.

        Mirrors the architecture of ``FusedSystemScorer``:
          1. Transform both X and X_ref through the descriptor
          2. Compute kNN-based deviation in descriptor space
          3. Z-score against reference statistics (positive-deviation only)
          4. Combine with descriptor-native features'''

NEW_REFDOC = '''        """Score X by multi-view deviation from reference distribution.

        Mirrors the architecture of ``FusedSystemScorer``:
          1. Transform both X and X_ref through the descriptor
          2. Compute kNN-based deviation in descriptor space
          3. Z-score against reference statistics (positive-deviation only)
          4. Combine with descriptor-native features
          5. BSDT channels (\\delta_C, \\delta_G, \\delta_A, \\delta_T)
             for blind-spot detection (Section 2.2)'''

assert OLD_REFDOC in src, "Could not find _reference_score docstring"
src = src.replace(OLD_REFDOC, NEW_REFDOC, 1)

# ═══════════════════════════════════════════════════════════════════
#  WRITE BACK
# ═══════════════════════════════════════════════════════════════════

with open(FILE, 'w', encoding='utf-8') as f:
    f.write(src)

# Verify
with open(FILE, 'r', encoding='utf-8') as f:
    final = f.read()

assert 'v_bsdt = robust_norm(bsdt.score(X))' in final
assert '0.15 * v_bsdt' in final
assert 'View D: BSDT channels' in final
print(f"✓ Patch applied. {len(final.splitlines())} lines.")
