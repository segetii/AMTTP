"""Patch: Improve _reference_score with raw-space kNN + adaptive weighting."""
import os, sys

FP = os.path.join(os.path.dirname(__file__), 'udl', 'system_mode.py')
with open(FP, encoding='utf-8') as f:
    lines = f.readlines()

print(f'Original lines: {len(lines)}')
joined = ''.join(lines)

if 'v_raw' in joined:
    print('Already patched (v_raw found).'); sys.exit(0)

# Find the _reference_score method: look for the fusion section
# Replace lines from "# 4. Fused score" to "return scores\n" in _reference_score
# Find "# 4. Fused score" line
fuse_start = None
for i, line in enumerate(lines):
    if '# 4. Fused score' in line and i > 1900:
        fuse_start = i
        break

assert fuse_start is not None, 'Cannot find "# 4. Fused score"'

# Find "return scores" that ends _reference_score (before score_panel)
fuse_end = None
for i in range(fuse_start, min(fuse_start+30, len(lines))):
    if lines[i].strip() == 'return scores':
        fuse_end = i + 1  # include this line
        break

assert fuse_end is not None, 'Cannot find "return scores" after fuse section'
print(f'Replacing lines {fuse_start+1}-{fuse_end} (fuse section)')

new_fuse = [
    '        # 4. Raw-space features (what makes simple Mahalanobis so strong)\n',
    '        # kNN in raw feature space against reference\n',
    '        k_raw = min(10, len(X_ref) - 1)\n',
    '        nn_raw = NearestNeighbors(n_neighbors=k_raw, algorithm="auto")\n',
    '        nn_raw.fit(X_ref.astype(np.float32))\n',
    '        dists_raw, _ = nn_raw.kneighbors(X.astype(np.float32))\n',
    '        raw_knn_mean = dists_raw.mean(axis=1)\n',
    '\n',
    '        # Mahalanobis in raw space (proven AUC ~0.998 on ERCOT)\n',
    '        raw_maha = mahalanobis  # already computed from descriptor\n',
    '\n',
    '        # Reference kNN stats for raw space\n',
    '        ref_dists_raw, _ = nn_raw.kneighbors(X_ref.astype(np.float32))\n',
    '        ref_raw_mean_d = ref_dists_raw.mean(axis=1)\n',
    '        z_raw_knn = np.maximum(\n',
    '            (raw_knn_mean - ref_raw_mean_d.mean()) /\n',
    '            (ref_raw_mean_d.std() + 1e-10), 0.0)\n',
    '\n',
    '        # 5. Adaptive fusion — multi-view weighted combination\n',
    '        def robust_norm(x):\n',
    '            q1, q99 = np.percentile(x, [1, 99])\n',
    '            xn = (x - q1) / (q99 - q1 + 1e-15)\n',
    '            return np.clip(xn, 0.0, 1.0)\n',
    '\n',
    '        # View A: Raw-space scoring (captures simple separability)\n',
    '        v_raw = (0.50 * robust_norm(z_raw_knn) +\n',
    '                 0.50 * robust_norm(raw_knn_mean))\n',
    '\n',
    '        # View B: Descriptor-space kNN (captures topology-transformed distances)\n',
    '        v_knn = (0.35 * robust_norm(z_knn) +\n',
    '                 0.30 * robust_norm(knn_d1) +\n',
    '                 0.20 * robust_norm(knn_persist) +\n',
    '                 0.15 * robust_norm(knn_mean))\n',
    '\n',
    '        # View C: Descriptor-native (Z-scored topology features)\n',
    '        v_desc = (0.25 * robust_norm(z_grad) +\n',
    '                  0.30 * robust_norm(z_maha) +\n',
    '                  0.15 * robust_norm(z_med) +\n',
    '                  0.10 * robust_norm(z_trace) +\n',
    '                  0.20 * robust_norm(z_morse))\n',
    '\n',
    '        # Fuse: 40% raw-space + 30% descriptor-kNN + 30% topology\n',
    '        scores = 0.40 * v_raw + 0.30 * v_knn + 0.30 * v_desc\n',
    '        return scores\n',
]

lines[fuse_start:fuse_end] = new_fuse
print(f'Replaced {fuse_end - fuse_start} lines with {len(new_fuse)} lines')

with open(FP, 'w', encoding='utf-8') as f:
    f.writelines(lines)

total = len(lines)
print(f'Total lines: {total}')
print(f'v_raw: {"v_raw" in "".join(lines)}')
