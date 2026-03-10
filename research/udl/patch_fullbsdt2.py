"""Fix FullBSDT: use transductive (full-data) Fisher VR, not reference-only."""

FILE = r'c:\amttp\research\udl\udl\system_mode.py'

with open(FILE, 'r', encoding='utf-8') as f:
    src = f.read()

OLD = '''        # 2. FullBSDT (Fisher-weighted channel sum, closed-form)
        t0 = _time.time()
        C = bsdt._channel_matrix(X)
        fw, _, _, _ = bsdt._fisher_weights(X_ref)
        # Min-max normalise each channel, then Fisher-weight
        C_normed = np.zeros_like(C)
        for k in range(C.shape[1]):
            col = C[:, k]
            cmin, cmax = col.min(), col.max()
            if cmax - cmin > 1e-10:
                C_normed[:, k] = (col - cmin) / (cmax - cmin)
        s = (C_normed * fw).sum(axis=1)
        results['full_bsdt'] = {
            'scores': s,
            'auroc': _safe_auroc(y, s),
            'time': _time.time() - t0,
            'fisher_weights': fw.tolist(),
        }'''

NEW = '''        # 2. FullBSDT (Fisher-weighted channel sum, closed-form)
        #    Uses transductive Fisher VR on full data X so that the
        #    percentile split discovers crash-discriminative channels.
        t0 = _time.time()
        C = bsdt._channel_matrix(X)
        fw, _, _, _ = bsdt._fisher_weights(X)  # transductive
        # Min-max normalise each channel, then Fisher-weight
        C_normed = np.zeros_like(C)
        for k in range(C.shape[1]):
            col = C[:, k]
            cmin, cmax = col.min(), col.max()
            if cmax - cmin > 1e-10:
                C_normed[:, k] = (col - cmin) / (cmax - cmin)
        s = (C_normed * fw).sum(axis=1)
        results['full_bsdt'] = {
            'scores': s,
            'auroc': _safe_auroc(y, s),
            'time': _time.time() - t0,
            'fisher_weights': fw.tolist(),
        }'''

assert OLD in src, "Could not find FullBSDT block"
src = src.replace(OLD, NEW, 1)

with open(FILE, 'w', encoding='utf-8') as f:
    f.write(src)
print("Patched: FullBSDT -> transductive Fisher VR on X")
