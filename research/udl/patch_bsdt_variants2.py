"""
Patch: Add QuadSurf, SignedLR, ExpoGate scoring variants to BSDTChannels,
and add score_variants() to ReducedTensorDescriptor for comparison.
"""
import re

FILE = r'c:\amttp\research\udl\udl\system_mode.py'

with open(FILE, 'r', encoding='utf-8') as f:
    lines = f.readlines()

print(f"Original: {len(lines)} lines")

# ═══════════════════════════════════════════════════════════════════
#  PATCH 1: Insert supervised variant methods into BSDTChannels
#  After line 900 (the "return 0.5 * e_n + 0.5 * m_n" line)
#  and before line 902 (the "# ═══..." FUSED SYSTEM SCORER line)
# ═══════════════════════════════════════════════════════════════════

# Find the exact insertion point
insert_after = None
for i, line in enumerate(lines):
    if 'return 0.5 * e_n + 0.5 * m_n' in line:
        insert_after = i
        break

assert insert_after is not None, "Could not find score() return line"
print(f"Inserting variant methods after line {insert_after + 1}")

VARIANT_METHODS = '''
    # -- Supervised MFLS scoring variants ---------------------------

    def _channel_matrix(self, X: np.ndarray) -> np.ndarray:
        """Return (N, 4) matrix of channel scores."""
        ch = self.channels(X)
        return np.column_stack([
            ch['delta_C'], ch['delta_G'],
            ch['delta_A'], ch['delta_T']
        ])

    @staticmethod
    def _poly_features(C: np.ndarray) -> np.ndarray:
        """Expand (N, K) -> (N, 1 + K + K*(K+1)/2) with bias + linear + quadratic."""
        N, K = C.shape
        features = [np.ones((N, 1)), C]
        for k in range(K):
            for j in range(k, K):
                features.append((C[:, k] * C[:, j]).reshape(-1, 1))
        return np.hstack(features)

    def fit_quadsurf(self, X: np.ndarray, y: np.ndarray,
                     ridge_alpha: float = 1.0) -> 'BSDTChannels':
        """Fit QuadSurf: degree-2 polynomial ridge on BSDT channels.

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
        I[0, 0] = 0.0  # don't regularise bias
        self._qs_beta = np.linalg.solve(
            Phi.T @ Phi + ridge_alpha * I,
            Phi.T @ y.astype(float)
        )
        self._qs_fitted = True
        return self

    def score_quadsurf(self, X: np.ndarray) -> np.ndarray:
        """QuadSurf score: polynomial surface over channel values."""
        C = self._channel_matrix(X)
        C_std = (C - self._qs_mu) / self._qs_std
        Phi = self._poly_features(C_std)
        return np.maximum(Phi @ self._qs_beta, 0.0)

    def fit_signed_lr(self, X: np.ndarray, y: np.ndarray,
                      lr: float = 0.1, n_iter: int = 500,
                      reg: float = 0.01) -> 'BSDTChannels':
        """Fit Signed LR: logistic regression on BSDT channels.

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
            grad[0] -= reg * beta[0]  # no reg on bias
            beta -= lr * grad

        self._lr_beta = beta
        self._lr_fitted = True
        return self

    def score_signed_lr(self, X: np.ndarray) -> np.ndarray:
        """Signed LR score: P(anomaly) via logistic regression."""
        C = self._channel_matrix(X)
        C_std = (C - self._lr_mu) / self._lr_std
        Xb = np.hstack([np.ones((len(C_std), 1)), C_std])
        return 1.0 / (1.0 + np.exp(-np.clip(Xb @ self._lr_beta, -500, 500)))

    def fit_expogate(self, X: np.ndarray, y: np.ndarray,
                     ridge_alpha: float = 1.0,
                     smooth_sigma: float = 1.0,
                     gate_scale: float = 3.0) -> 'BSDTChannels':
        """Fit ExpoGate: QuadSurf + tanh saturation + sigmoid gating.

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
        """ExpoGate score: saturated + gated QuadSurf output."""
        raw = self.score_quadsurf(X)
        sat = np.tanh(raw / (self._eg_sigma + self.eps))
        return 1.0 / (1.0 + np.exp(-self._eg_scale * sat))

'''

variant_lines = VARIANT_METHODS.split('\n')
# Insert after the 'return' line + 1 blank line
# line insert_after is 0-indexed, we want to insert after it
# There's already a blank line at insert_after+1, so insert after that
insert_pos = insert_after + 1
lines.insert(insert_pos, VARIANT_METHODS)

# ═══════════════════════════════════════════════════════════════════
#  PATCH 2: Add score_variants() to ReducedTensorDescriptor
#  Insert after "return scores" in _reference_score and before
#  "def score_panel"
# ═══════════════════════════════════════════════════════════════════

# Re-join lines and re-split for easier patching
src = ''.join(lines)

# Find the "return scores" at end of _reference_score, right before score_panel
ANCHOR = '''        scores = (0.35 * v_raw + 0.25 * v_knn +
                  0.25 * v_desc + 0.15 * v_bsdt)
        return scores

    def score_panel'''

assert ANCHOR in src, f"Could not find _reference_score anchor! File len: {len(src)}"

REPLACEMENT = '''        scores = (0.35 * v_raw + 0.25 * v_knn +
                  0.25 * v_desc + 0.15 * v_bsdt)
        return scores

    def score_variants(self, X: np.ndarray, y: np.ndarray,
                       X_ref: np.ndarray = None) -> dict:
        """Compare all BSDT scoring variants on a labelled dataset.

        Runs 5 scoring strategies on the BSDT channels:
          1. Baseline  -- E_BS + MFLS composite (unsupervised)
          2. FullBSDT  -- uniform-weighted channel sum (unsupervised)
          3. QuadSurf  -- degree-2 polynomial ridge (supervised)
          4. SignedLR  -- logistic regression (supervised)
          5. ExpoGate  -- QuadSurf + tanh + sigmoid (supervised)

        Parameters
        ----------
        X : (N, d) -- feature matrix
        y : (N,) -- binary labels (0 = normal, 1 = anomaly)
        X_ref : (N_ref, d) or None -- reference data (if None, uses y==0)

        Returns
        -------
        dict mapping variant name to {'scores', 'auroc', 'time'}.
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

        def _safe_auroc(y_true, y_score):
            try:
                return float(roc_auc_score(y_true, y_score))
            except ValueError:
                return float('nan')

        # 1. Baseline (E_BS + MFLS)
        t0 = _time.time()
        s = bsdt.score(X)
        results['baseline'] = {
            'scores': s,
            'auroc': _safe_auroc(y, s),
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
            'auroc': _safe_auroc(y, s),
            'time': _time.time() - t0,
        }

        # 3. QuadSurf (supervised)
        t0 = _time.time()
        bsdt.fit_quadsurf(X, y)
        s = bsdt.score_quadsurf(X)
        results['quadsurf'] = {
            'scores': s,
            'auroc': _safe_auroc(y, s),
            'time': _time.time() - t0,
        }

        # 4. SignedLR (supervised)
        t0 = _time.time()
        bsdt.fit_signed_lr(X, y)
        s = bsdt.score_signed_lr(X)
        results['signed_lr'] = {
            'scores': s,
            'auroc': _safe_auroc(y, s),
            'time': _time.time() - t0,
            'weights': bsdt._lr_beta.tolist(),
        }

        # 5. ExpoGate (supervised)
        t0 = _time.time()
        bsdt.fit_expogate(X, y)
        s = bsdt.score_expogate(X)
        results['expo_gate'] = {
            'scores': s,
            'auroc': _safe_auroc(y, s),
            'time': _time.time() - t0,
        }

        return results

    def score_panel'''

src = src.replace(ANCHOR, REPLACEMENT, 1)

# ═══════════════════════════════════════════════════════════════════
#  WRITE & VERIFY
# ═══════════════════════════════════════════════════════════════════
with open(FILE, 'w', encoding='utf-8') as f:
    f.write(src)

final_lines = src.split('\n')
print(f"Patched: {len(final_lines)} lines")

for name in ['fit_quadsurf', 'score_quadsurf', 'fit_signed_lr',
             'score_signed_lr', 'fit_expogate', 'score_expogate',
             '_poly_features', '_channel_matrix', 'score_variants']:
    assert f'def {name}' in src, f"MISSING: {name}"
    print(f"  OK def {name}")

print("\nAll patches applied successfully.")
