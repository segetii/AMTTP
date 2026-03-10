"""
Fix: Make QuadSurf and ExpoGate post-hoc analytical formulas (no labels).
Only SignedLR is truly supervised.

QuadSurf: Q(c) = sum of degree-2 polynomial features (standardised channels, unit weights)
ExpoGate: tanh(Q/sigma) -> sigmoid(scale * sat) with fixed hyperparameters
SignedLR: logistic regression on channels (supervised, learns weights from labels)
"""

FILE = r'c:\amttp\research\udl\udl\system_mode.py'

with open(FILE, 'r', encoding='utf-8') as f:
    src = f.read()

original_len = len(src.splitlines())
print(f"Original: {original_len} lines")

# ═══════════════════════════════════════════════════════════════════
#  PATCH 1: Fix the section header and QuadSurf + ExpoGate methods
# ═══════════════════════════════════════════════════════════════════

OLD_VARIANTS = '''    # -- Supervised MFLS scoring variants ---------------------------

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
        return np.maximum(Phi @ self._qs_beta, 0.0)'''

NEW_VARIANTS = '''    # -- MFLS scoring variants ----------------------------------------
    #   QuadSurf & ExpoGate are post-hoc analytical formulas.
    #   SignedLR is the only supervised variant (needs labels).

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

    def fit_quadsurf(self, X_ref: np.ndarray) -> 'BSDTChannels':
        """Calibrate QuadSurf: post-hoc degree-2 polynomial of BSDT channels.

        QuadSurf is an analytical formula -- no labels required.
        The score is the sum of all degree-2 polynomial features
        (linear + squared + cross-terms) of the standardised channels:

          Q(c) = sum_k c_k' + sum_k c_k'^2 + sum_{k<j} c_k' c_j'

        where c_k' = (c_k - mu_k) / sigma_k are standardised against
        reference-period channel statistics.

        Parameters
        ----------
        X_ref : (N, d) array -- reference (normal-period) features
        """
        C = self._channel_matrix(X_ref)
        self._qs_mu = C.mean(axis=0)
        self._qs_std = C.std(axis=0) + self.eps
        self._qs_fitted = True
        return self

    def score_quadsurf(self, X: np.ndarray) -> np.ndarray:
        """QuadSurf score: post-hoc polynomial surface over channel values.

        Returns sum of all non-bias polynomial features (unit weights),
        clipped to [0, inf).  Higher = more anomalous.
        """
        C = self._channel_matrix(X)
        C_std = (C - self._qs_mu) / self._qs_std
        Phi = self._poly_features(C_std)
        # Sum all features except bias (column 0); clip negative
        return np.maximum(Phi[:, 1:].sum(axis=1), 0.0)'''

assert OLD_VARIANTS in src, "Could not find OLD_VARIANTS anchor"
src = src.replace(OLD_VARIANTS, NEW_VARIANTS, 1)
print("  Patched QuadSurf -> post-hoc")

# ═══════════════════════════════════════════════════════════════════
#  PATCH 2: Fix ExpoGate to post-hoc (no y, wraps QuadSurf)
# ═══════════════════════════════════════════════════════════════════

OLD_EXPOGATE = '''    def fit_expogate(self, X: np.ndarray, y: np.ndarray,
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
        return self'''

NEW_EXPOGATE = '''    def fit_expogate(self, X_ref: np.ndarray,
                     smooth_sigma: float = 1.0,
                     gate_scale: float = 3.0) -> 'BSDTChannels':
        """Calibrate ExpoGate: post-hoc QuadSurf + tanh + sigmoid gating.

        Analytical formula -- no labels required.
        Prevents false-alarm inflation by capping extreme QuadSurf
        scores with tanh saturation, then gating through sigmoid
        for calibrated [0, 1] output.

        score = sigmoid(gate_scale * tanh(Q(c) / sigma))

        Parameters
        ----------
        X_ref : (N, d) array -- reference (normal-period) features
        smooth_sigma : float -- tanh saturation scale
        gate_scale : float -- sigmoid gate steepness
        """
        self.fit_quadsurf(X_ref)
        self._eg_sigma = smooth_sigma
        self._eg_scale = gate_scale
        self._eg_fitted = True
        return self'''

assert OLD_EXPOGATE in src, "Could not find OLD_EXPOGATE anchor"
src = src.replace(OLD_EXPOGATE, NEW_EXPOGATE, 1)
print("  Patched ExpoGate -> post-hoc")

# ═══════════════════════════════════════════════════════════════════
#  PATCH 3: Fix score_variants() in ReducedTensorDescriptor
#  QuadSurf and ExpoGate no longer take y
# ═══════════════════════════════════════════════════════════════════

OLD_VARIANTS_CALL = '''        # 3. QuadSurf (supervised)
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
        }'''

NEW_VARIANTS_CALL = '''        # 3. QuadSurf (post-hoc analytical)
        t0 = _time.time()
        bsdt.fit_quadsurf(X_ref)
        s = bsdt.score_quadsurf(X)
        results['quadsurf'] = {
            'scores': s,
            'auroc': _safe_auroc(y, s),
            'time': _time.time() - t0,
        }

        # 4. SignedLR (supervised -- the only variant needing labels)
        t0 = _time.time()
        bsdt.fit_signed_lr(X, y)
        s = bsdt.score_signed_lr(X)
        results['signed_lr'] = {
            'scores': s,
            'auroc': _safe_auroc(y, s),
            'time': _time.time() - t0,
            'weights': bsdt._lr_beta.tolist(),
        }

        # 5. ExpoGate (post-hoc analytical)
        t0 = _time.time()
        bsdt.fit_expogate(X_ref)
        s = bsdt.score_expogate(X)
        results['expo_gate'] = {
            'scores': s,
            'auroc': _safe_auroc(y, s),
            'time': _time.time() - t0,
        }'''

assert OLD_VARIANTS_CALL in src, "Could not find score_variants call anchor"
src = src.replace(OLD_VARIANTS_CALL, NEW_VARIANTS_CALL, 1)
print("  Patched score_variants() calls")

# ═══════════════════════════════════════════════════════════════════
#  PATCH 4: Fix the docstring in score_variants
# ═══════════════════════════════════════════════════════════════════

OLD_DOC = '''          1. Baseline  -- E_BS + MFLS composite (unsupervised)
          2. FullBSDT  -- uniform-weighted channel sum (unsupervised)
          3. QuadSurf  -- degree-2 polynomial ridge (supervised)
          4. SignedLR  -- logistic regression (supervised)
          5. ExpoGate  -- QuadSurf + tanh + sigmoid (supervised)'''

NEW_DOC = '''          1. Baseline  -- E_BS + MFLS composite (unsupervised)
          2. FullBSDT  -- uniform-weighted channel sum (unsupervised)
          3. QuadSurf  -- degree-2 polynomial surface (post-hoc)
          4. SignedLR  -- logistic regression (supervised)
          5. ExpoGate  -- QuadSurf + tanh + sigmoid (post-hoc)'''

assert OLD_DOC in src, "Could not find docstring anchor"
src = src.replace(OLD_DOC, NEW_DOC, 1)
print("  Patched score_variants() docstring")

# ═══════════════════════════════════════════════════════════════════
#  WRITE & VERIFY
# ═══════════════════════════════════════════════════════════════════

with open(FILE, 'w', encoding='utf-8') as f:
    f.write(src)

final_len = len(src.splitlines())
print(f"\nPatched: {final_len} lines")

# Verify
assert 'def fit_quadsurf(self, X_ref: np.ndarray)' in src
assert 'y: np.ndarray' not in src.split('def fit_quadsurf')[1].split('def ')[0], \
    "QuadSurf still takes y!"
assert 'def fit_expogate(self, X_ref: np.ndarray' in src
assert 'post-hoc' in src.split('def fit_quadsurf')[1][:200]
assert 'post-hoc' in src.split('def fit_expogate')[1][:200]
assert "# 3. QuadSurf (post-hoc analytical)" in src
assert "# 5. ExpoGate (post-hoc analytical)" in src

print("All verifications passed.")
