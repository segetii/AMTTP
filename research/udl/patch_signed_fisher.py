"""
Fix 2: SignedFisher must compute Fisher weights on FULL data (transductive),
not just reference data.  This follows the paper's method exactly:
  _variance_ratio_weights(magnitudes, y=None)  <-- uses ALL magnitudes

The percentile split naturally discovers anomaly direction.
Still zero label leakage -- y is never used.
"""

FILE = r'c:\amttp\research\udl\udl\system_mode.py'

with open(FILE, 'r', encoding='utf-8') as f:
    src = f.read()

# ═══════════════════════════════════════════════════════════════════
#  PATCH 1: fit_signed_lr takes X (full data), not X_ref
# ═══════════════════════════════════════════════════════════════════

OLD_SLR = '''    def fit_signed_lr(self, X_ref: np.ndarray) -> 'BSDTChannels':
        """Calibrate Signed Fisher: signed Fisher-weighted linear combination.

        Closed-form from data statistics -- zero labels required.
        Discovers which channels increase vs decrease when overall
        anomaly signal is high (herding detection).

        The sign of each Fisher weight is determined by comparing
        mu_high vs mu_low: if a channel DECREASES in the high-anomaly
        regime, it gets a negative weight.  This is the mechanism
        that discovers herding (e.g. delta_T inverts during
        coordinated sell-offs).

        score = sigmoid(bias + sum_k sign_k * w_k * c_k')

        The bias is set so that the reference median maps to 0.5.

        Parameters
        ----------
        X_ref : (N, d) array -- reference (normal-period) features
        """
        w, signs, mu, std = self._fisher_weights(X_ref)
        self._lr_mu = mu
        self._lr_std = std

        K = len(w)
        # Beta = [bias, sign_1 * w_1, ..., sign_K * w_K]
        # Scale weights to have unit L1 norm for interpretability
        w_sum = w.sum() + self.eps
        self._lr_beta = np.zeros(K + 1)
        for k in range(K):
            self._lr_beta[k + 1] = signs[k] * w[k] / w_sum

        # Set bias so that reference-period median -> sigmoid(0) = 0.5
        C_ref = self._channel_matrix(X_ref) if hasattr(self, '_ref_data_for_bias') else None
        # Use zero bias as default (reference is centred at 0 after standardisation)
        self._lr_beta[0] = 0.0

        self._lr_fitted = True
        return self'''

NEW_SLR = '''    def fit_signed_lr(self, X: np.ndarray) -> 'BSDTChannels':
        """Calibrate Signed Fisher: signed Fisher-weighted linear combination.

        Closed-form from data statistics -- zero labels required.
        Discovers which channels increase vs decrease when overall
        anomaly signal is high (herding detection).

        Uses Fisher variance-ratio with percentile-based regime split
        on the FULL data (transductive, label-free).  The 80th/50th
        percentile of total channel magnitude naturally separates
        high-anomaly from low-anomaly samples.  The sign of each
        weight reflects whether a channel increases or decreases
        in the high-regime → herding discovery.

        score = sigmoid(scale * sum_k sign_k * w_k * c_k')

        Parameters
        ----------
        X : (N, d) array -- full dataset (normal + test, NO labels)
        """
        w, signs, mu, std = self._fisher_weights(X)
        self._lr_mu = mu
        self._lr_std = std

        K = len(w)
        # Beta = [bias, sign_1 * w_1, ..., sign_K * w_K]
        w_sum = w.sum() + self.eps
        self._lr_beta = np.zeros(K + 1)
        for k in range(K):
            self._lr_beta[k + 1] = signs[k] * w[k] / w_sum

        # Scale factor: sigmoid sensitivity.  Set so that std-dev
        # of the raw combination maps to a useful range.
        C = self._channel_matrix(X)
        C_std = (C - mu) / std
        raw = C_std @ self._lr_beta[1:]
        raw_std = raw.std() + self.eps
        # Scale so that 2-sigma spans sigmoid's active region (~[-3,3])
        scale = 3.0 / (2.0 * raw_std)
        self._lr_beta[1:] *= scale
        self._lr_beta[0] = -np.median(raw * scale)

        self._lr_fitted = True
        return self'''

assert OLD_SLR in src, "Could not find fit_signed_lr"
src = src.replace(OLD_SLR, NEW_SLR, 1)
print("  Patched fit_signed_lr -> transductive Fisher VR")

# ═══════════════════════════════════════════════════════════════════
#  PATCH 2: score_variants() passes X (not X_ref) to fit_signed_lr
# ═══════════════════════════════════════════════════════════════════

OLD_CALL = '''        # 4. SignedFisher (signed Fisher combination, closed-form)
        t0 = _time.time()
        bsdt.fit_signed_lr(X_ref)'''

NEW_CALL = '''        # 4. SignedFisher (signed Fisher combination, closed-form)
        t0 = _time.time()
        bsdt.fit_signed_lr(X)'''

assert OLD_CALL in src, "Could not find score_variants signed_lr call"
src = src.replace(OLD_CALL, NEW_CALL, 1)
print("  Patched score_variants -> passes X (full data)")

with open(FILE, 'w', encoding='utf-8') as f:
    f.write(src)
print(f"Written: {len(src.splitlines())} lines")

# Verify
for bad in ['y: np.ndarray', 'y_f', 'n_pos', 'n_neg']:
    block = src.split('def fit_signed_lr')[1].split('def ')[0]
    assert bad not in block, f"LEAKAGE: {bad} still in fit_signed_lr"

print("Zero leakage verified.")
