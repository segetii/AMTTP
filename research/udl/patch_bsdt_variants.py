"""
Patch: Add QuadSurf, SignedLR, ExpoGate scoring variants to BSDTChannels,
and add variant comparison to ReducedTensorDescriptor._reference_score.

Adds three supervised MFLS scoring strategies:
  - QuadSurf:  degree-2 polynomial + ridge regression
  - SignedLR:  logistic regression on channel scores
  - ExpoGate:  QuadSurf + tanh saturation + sigmoid gating

These operate on the 4 BSDT channels (delta_C, delta_G, delta_A, delta_T)
computed by BSDTChannels.channels(X), then produce a scalar score per point.

In the benchmark, we compare all variants against the baseline E_BS+MFLS.
"""

FILE = r'c:\amttp\research\udl\udl\system_mode.py'

with open(FILE, 'r', encoding='utf-8') as f:
    src = f.read()

# ═══════════════════════════════════════════════════════════════════
#  PATCH 1: Add 3 variant methods to BSDTChannels class
#  Insert after score() method, before the closing of the class
# ═══════════════════════════════════════════════════════════════════

# Anchor: the score() method's return statement + the next class separator
OLD_SCORE_END = '        return 0.5 * e_n + 0.5 * m_n\n\n\n# ' + '═' * 65 + '\n#  FUSED SYSTEM SCORER'

NEW_SCORE_END = '''        return 0.5 * e_n + 0.5 * m_n

    # -- Supervised MFLS scoring variants ---------------------------

    def _channel_matrix(self, X: np.ndarray) -> np.ndarray:
        """Return (N, 4) matrix of channel scores."""
        ch = self.channels(X)
        return np.column_stack([
            ch['delta_C'], ch['delta_G'],
            ch['delta_A'], ch['delta_T']
        ])

    def fit_quadsurf(self, X: np.ndarray, y: np.ndarray,
                     ridge_alpha: float = 1.0) -> 'BSDTChannels':
        r"""
        Fit QuadSurf: degree-2 polynomial ridge on BSDT channels.

        Score = beta_0 + sum_k beta_k c_k + sum_{k<=j} beta_{kj} c_k c_j

        Parameters
        ----------
        X : (N, d) array -- training features
        y : (N,) array -- binary labels (0 = normal, 1 = anomaly)
        ridge_alpha : float -- regularisation strength
        """
        C = self._channel_matrix(X)
        self._qs_mu = C.mean(axis=0)
        self._qs_std = C.std(axis=0) + self.eps
        C_std = (C - self._qs_mu) / self._qs_std

        Phi = self._poly_features(C_std)
        n_feat = Phi.shape[1]
        I = np.eye(n_feat)
        I[0, 0] = 0  # don't regularise bias
        self._qs_beta = np.linalg.solve(
            Phi.T @ Phi + ridge_alpha * I,
            Phi.T @ y.astype(float)
        )
        self._qs_fitted = True
        return self

    def score_quadsurf(self, X: np.ndarray) -> np.ndarray:
        r"""QuadSurf score: polynomial surface over channel values."""
        C = self._channel_matrix(X)
        C_std = (C - self._qs_mu) / self._qs_std
        Phi = self._poly_features(C_std)
        return np.maximum(Phi @ self._qs_beta, 0.0)

    def fit_signed_lr(self, X: np.ndarray, y: np.ndarray,
                      lr: float = 0.1, n_iter: int = 500,
                      reg: float = 0.01) -> 'BSDTChannels':
        r"""
        Fit Signed LR: logistic regression on BSDT channels.

        P(anomaly | c_1,...,c_4) = sigma(beta_0 + sum_k beta_k c_k)

        Discovers which channels drive detection; negative weights
        reveal herding effects (e.g. temporal novelty inverts during
        coordinated sell-offs).

        Parameters
        ----------
        X : (N, d) array -- training features
        y : (N,) array -- binary labels
        lr : float -- learning rate
        n_iter : int -- gradient descent iterations
        reg : float -- L2 regularisation
        """
        C = self._channel_matrix(X)
        self._lr_mu = C.mean(axis=0)
        self._lr_std = C.std(axis=0) + self.eps
        C_std = (C - self._lr_mu) / self._lr_std

        T, K = C_std.shape
        Xb = np.hstack([np.ones((T, 1)), C_std])
        beta = np.zeros(K + 1)
        y_f = y.astype(float)

        # Class-imbalance weighting
        n_pos = max(y_f.sum(), 1)
        n_neg = max(len(y_f) - n_pos, 1)
        w = np.where(y_f == 1, n_neg / n_pos, 1.0)

        for _ in range(n_iter):
            p = 1.0 / (1.0 + np.exp(-np.clip(Xb @ beta, -500, 500)))
            grad = Xb.T @ (w * (p - y_f)) / T + reg * beta
            grad[0] -= reg * beta[0]
            beta -= lr * grad

        self._lr_beta = beta
        self._lr_fitted = True
        return self

    def score_signed_lr(self, X: np.ndarray) -> np.ndarray:
        r"""Signed LR score: P(anomaly) via logistic regression."""
        C = self._channel_matrix(X)
        C_std = (C - self._lr_mu) / self._lr_std
        Xb = np.hstack([np.ones((len(C_std), 1)), C_std])
        return 1.0 / (1.0 + np.exp(-np.clip(Xb @ self._lr_beta, -500, 500)))

    def fit_expogate(self, X: np.ndarray, y: np.ndarray,
                     ridge_alpha: float = 1.0,
                     smooth_sigma: float = 1.0,
                     gate_scale: float = 3.0) -> 'BSDTChannels':
        r"""
        Fit ExpoGate: QuadSurf + tanh saturation + sigmoid gating.

        Prevents false-alarm inflation by capping extreme QuadSurf
        scores with tanh, then gating through sigmoid for calibration.

        Parameters
        ----------
        X : (N, d) array -- training features
        y : (N,) array -- binary labels
        ridge_alpha : float -- ridge strength for QuadSurf
        smooth_sigma : float -- tanh saturation scale
        gate_scale : float -- sigmoid gate steepness
        """
        self.fit_quadsurf(X, y, ridge_alpha=ridge_alpha)
        self._eg_sigma = smooth_sigma
        self._eg_scale = gate_scale
        self._eg_fitted = True
        return self

    def score_expogate(self, X: np.ndarray) -> np.ndarray:
        r"""ExpoGate score: saturated + gated QuadSurf output."""
        raw = self.score_quadsurf(X)
        sat = np.tanh(raw / (self._eg_sigma + self.eps))
        return 1.0 / (1.0 + np.exp(-self._eg_scale * sat))

    @staticmethod
    def _poly_features(C: np.ndarray) -> np.ndarray:
        """Expand (N, K) -> (N, 1 + K + K*(K+1)/2) with bias + linear + quadratic."""
        N, K = C.shape
        features = [np.ones((N, 1)), C]
        for k in range(K):
            for j in range(k, K):
                features.append((C[:, k] * C[:, j]).reshape(-1, 1))
        return np.hstack(features)

''' + '\n# ' + '=' * 65 + '\\n#  FUSED SYSTEM SCORER'

assert OLD_SCORE_END in src, "Could not find score() end anchor"
src = src.replace(OLD_SCORE_END, NEW_SCORE_END, 1)

# ═══════════════════════════════════════════════════════════════════
#  PATCH 2: Add variant-aware scoring to ReducedTensorDescriptor
#  Modify _reference_score to use best variant when labels available
# ═══════════════════════════════════════════════════════════════════

# We add a new method score_variants() for explicit comparison,
# and update fit_score to optionally use variants.

# Find the end of _reference_score method (after the return scores line)
OLD_REFSCORE_RETURN = '''        # Fuse: 35% raw + 25% descriptor-kNN + 25% topology + 15% BSDT
        scores = (0.35 * v_raw + 0.25 * v_knn +
                  0.25 * v_desc + 0.15 * v_bsdt)
        return scores

    def score_panel'''

NEW_REFSCORE_RETURN = '''        # Fuse: 35% raw + 25% descriptor-kNN + 25% topology + 15% BSDT
        scores = (0.35 * v_raw + 0.25 * v_knn +
                  0.25 * v_desc + 0.15 * v_bsdt)
        return scores

    def score_variants(self, X: np.ndarray, y: np.ndarray,
                       X_ref: np.ndarray = None) -> dict:
        """Compare all BSDT scoring variants on a labelled dataset.

        Runs 5 scoring strategies on the BSDT channels:
          1. Baseline  — E_BS + MFLS composite (unsupervised)
          2. FullBSDT  — uniform-weighted channel sum (unsupervised)
          3. QuadSurf  — degree-2 polynomial ridge (supervised)
          4. SignedLR  — logistic regression (supervised)
          5. ExpoGate  — QuadSurf + tanh + sigmoid (supervised)

        Parameters
        ----------
        X : (N, d) — feature matrix
        y : (N,) — binary labels (0 = normal, 1 = anomaly)
        X_ref : (N_ref, d) or None — reference data (if None, uses y==0)

        Returns
        -------
        dict with keys: 'baseline', 'full_bsdt', 'quadsurf',
                        'signed_lr', 'expo_gate'.
        Each value is a dict with 'scores' (N,), 'auroc', 'time'.
        """
        import time as _time
        from sklearn.metrics import roc_auc_score

        X = np.asarray(X, dtype=np.float64)
        y = np.asarray(y)
        if X_ref is None:
            X_ref = X[y == 0]

        # Fit BSDT on reference
        bsdt = BSDTChannels(k=min(10, max(2, len(X_ref) - 1)))
        bsdt.fit(X_ref)

        results = {}

        # 1. Baseline (E_BS + MFLS)
        t0 = _time.time()
        s = bsdt.score(X)
        results['baseline'] = {
            'scores': s,
            'auroc': float(roc_auc_score(y, s)),
            'time': _time.time() - t0,
        }

        # 2. FullBSDT (uniform channel sum)
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
            'auroc': float(roc_auc_score(y, s)),
            'time': _time.time() - t0,
        }

        # 3. QuadSurf (supervised)
        t0 = _time.time()
        bsdt.fit_quadsurf(X, y)
        s = bsdt.score_quadsurf(X)
        results['quadsurf'] = {
            'scores': s,
            'auroc': float(roc_auc_score(y, s)),
            'time': _time.time() - t0,
        }

        # 4. SignedLR (supervised)
        t0 = _time.time()
        bsdt.fit_signed_lr(X, y)
        s = bsdt.score_signed_lr(X)
        results['signed_lr'] = {
            'scores': s,
            'auroc': float(roc_auc_score(y, s)),
            'time': _time.time() - t0,
            'weights': bsdt._lr_beta.tolist() if hasattr(bsdt, '_lr_beta') else None,
        }

        # 5. ExpoGate (supervised)
        t0 = _time.time()
        bsdt.fit_expogate(X, y)
        s = bsdt.score_expogate(X)
        results['expo_gate'] = {
            'scores': s,
            'auroc': float(roc_auc_score(y, s)),
            'time': _time.time() - t0,
        }

        return results

    def score_panel'''

assert OLD_REFSCORE_RETURN in src, "Could not find _reference_score return anchor"
src = src.replace(OLD_REFSCORE_RETURN, NEW_REFSCORE_RETURN, 1)

# ═══════════════════════════════════════════════════════════════════
#  WRITE BACK
# ═══════════════════════════════════════════════════════════════════

with open(FILE, 'w', encoding='utf-8') as f:
    f.write(src)

# Verify
with open(FILE, 'r', encoding='utf-8') as f:
    final = f.read()

assert 'def fit_quadsurf' in final, "QuadSurf not found!"
assert 'def score_quadsurf' in final, "score_quadsurf not found!"
assert 'def fit_signed_lr' in final, "SignedLR not found!"
assert 'def score_signed_lr' in final, "score_signed_lr not found!"
assert 'def fit_expogate' in final, "ExpoGate not found!"
assert 'def score_expogate' in final, "score_expogate not found!"
assert 'def score_variants' in final, "score_variants not found!"
assert '_poly_features' in final, "poly_features not found!"

print(f"OK Patch applied. {len(final.splitlines())} lines.")
