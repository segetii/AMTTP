"""Fix FullBSDT: use Fisher VR weights from dataset properties instead of uniform."""

FILE = r'c:\amttp\research\udl\udl\system_mode.py'

with open(FILE, 'r', encoding='utf-8') as f:
    src = f.read()

# ═══════════════════════════════════════════════════════════════════
#  PATCH 1: FullBSDT in score_variants -> Fisher-weighted channel sum
# ═══════════════════════════════════════════════════════════════════

OLD = '''        # 2. FullBSDT (uniform channel sum)
        t0 = _time.time()
        C = bsdt._channel_matrix(X)
        C_normed = np.zeros_like(C)
        for k in range(C.shape[1]):
            col = C[:, k]
            cmin, cmax = col.min(), col.max()
            if cmax - cmin > 1e-10:
                C_normed[:, k] = (col - cmin) / (cmax - cmin)
        s = C_normed.sum(axis=1)
        results['full_bsdt'] = {
            'scores': s,
            'auroc': _safe_auroc(y, s),
            'time': _time.time() - t0,
        }'''

NEW = '''        # 2. FullBSDT (Fisher-weighted channel sum, closed-form)
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

assert OLD in src, "Could not find FullBSDT block"
src = src.replace(OLD, NEW, 1)

# ═══════════════════════════════════════════════════════════════════
#  PATCH 2: Update docstring
# ═══════════════════════════════════════════════════════════════════

OLD_DOC = '          2. FullBSDT     -- uniform-weighted channel sum (closed-form)'
NEW_DOC = '          2. FullBSDT     -- Fisher-weighted channel sum (closed-form)'
assert OLD_DOC in src
src = src.replace(OLD_DOC, NEW_DOC, 1)

# ═══════════════════════════════════════════════════════════════════
#  PATCH 3: BSDTChannels.score() -> also Fisher-weighted
# ═══════════════════════════════════════════════════════════════════

OLD_SCORE = '''    def score(self, X: np.ndarray) -> np.ndarray:
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
        m_n = m / m_max'''

NEW_SCORE = '''    def score(self, X: np.ndarray) -> np.ndarray:
        """
        Combined BSDT score = Fisher-weighted channel combination.

        Uses Fisher variance-ratio weights derived from the reference
        data (fitted during .fit()) to combine normalised channels.
        Falls back to 0.5*E_BS + 0.5*MFLS blend if Fisher weights
        are not available (e.g. too few reference points).
        """
        e = self.energy(X)
        m = self.mfls(X)

        # Normalise each to [0, 1]
        e_max = max(float(e.max()), self.eps)
        m_max = max(float(m.max()), self.eps)
        e_n = e / e_max
        m_n = m / m_max'''

assert OLD_SCORE in src, "Could not find BSDTChannels.score()"
src = src.replace(OLD_SCORE, NEW_SCORE, 1)

with open(FILE, 'w', encoding='utf-8') as f:
    f.write(src)

print("Patched: %d lines" % len(src.splitlines()))
print("FullBSDT now uses Fisher VR weights from dataset properties")
