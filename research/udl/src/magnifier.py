"""
Dimension Magnifier — Boundary-Centred Saturating Transform
============================================================
Glides over every dimension of the representation space, measures
class separation, then TRANSFORMS each dimension non-linearly:

  For each dimension d:
    1. Find the decision boundary:  b_d = (μ_normal + μ_anomaly) / 2
    2. Standardise deviation from boundary:  z = (r - b_d) / σ_pooled
    3. Apply saturating non-linearity:  r' = tanh(k_d · z)

  k_d = γ · discriminative_score_d

  For CLEAR dimensions (high disc_score, large k):
    - tanh saturates → normal cluster collapses to ≈ −1,
      anomaly cluster collapses to ≈ +1
    - Within-class variance → near zero
    - Cohen's d explodes (e.g. 1.2 → 10+)

  For BLIND dimensions (low disc_score, tiny k):
    - tanh(small · z) ≈ small · z → dim is scaled to near-zero
    - Effectively silenced without being removed

The result: after magnify(), every informative dimension has a huge
gap between normal and anomaly with tiny variance, and noise dims
are muted.  Fisher then gets a trivially separable geometry.

Transform formula per dimension d:
  b_d = (μ₀ + μ₁) / 2                        (decision boundary)
  z   = (r_d − b_d) / σ_pooled_d              (standardise from boundary)
  k_d = γ · disc_score_d                      (steepness)
  r'_d = tanh(k_d · z)                        (saturating transform → [−1, +1])
"""

import numpy as np
from sklearn.metrics import roc_auc_score


class DimensionMagnifier:
    """
    Boundary-centred saturating transform per dimension.

    For each dimension d:
      1. Compute decision boundary b_d = (μ_normal + μ_anomaly) / 2
      2. Standardise from boundary: z = (r - b_d) / σ_pooled
      3. Apply: r' = tanh(k_d · z)   where k_d = γ · disc_score_d

    Clear dims (large k): both classes saturate to ±1 → huge Cohen's d.
    Blind dims (tiny k): tanh ≈ 0 → dimension silenced.

    Parameters
    ----------
    gamma : float
        Steepness multiplier.  k_d = gamma * disc_score.  Default 5.0.
    blind_threshold : float
        Disc score below which a dim is considered blind (for display).
    verbose : bool
        Print per-dimension scan results during fit.
    """

    def __init__(self, power=2.0, floor=0.01, method="full", verbose=False,
                 gamma=5.0, compress=0.3, blind_threshold=0.3):
        self.power = power
        self.floor = floor
        self.method = method
        self.verbose = verbose
        self.gamma = gamma
        self.compress = compress
        self.blind_threshold = blind_threshold
        self.weights_ = None         # (D,) per-dimension weights (kept for compat)
        self.steepness_ = None       # (D,) per-dimension tanh steepness k_d
        self.boundaries_ = None      # (D,) per-dimension decision boundary
        self.pooled_std_ = None      # (D,) per-dimension pooled std
        self.alphas_ = None          # (D,) alias for steepness_ (compat)
        self.dim_stats_ = None
        self._fitted = False

    def fit(self, R, y, law_names=None, law_dims=None):
        """
        Scan all D dimensions and compute discriminative weights.

        Parameters
        ----------
        R : ndarray (N, D)
            Representation matrix.
        y : ndarray (N,)
            Labels (0=normal, 1=anomaly).
        law_names : list of str or None
            Names of each law block (for logging).
        law_dims : list of int or None
            Number of dimensions per law block (for logging).

        Returns
        -------
        self
        """
        N, D = R.shape
        mask_n = y == 0
        mask_a = y == 1

        # Store normal reference stats for direct scoring
        self._ref_mean = R[mask_n].mean(axis=0) if mask_n.any() else R.mean(axis=0)
        self._ref_std = R[mask_n].std(axis=0) if mask_n.any() else R.std(axis=0)
        # Direction: +1 if anomalies are higher, -1 if lower
        self._anom_direction = np.sign(
            R[mask_a].mean(axis=0) - R[mask_n].mean(axis=0)
        ) if mask_a.any() else np.ones(D)

        if mask_a.sum() < 2 or mask_n.sum() < 2:
            # Not enough of both classes — uniform weights
            self.weights_ = np.ones(D)
            self._fitted = True
            return self

        weights = np.zeros(D)
        stats = []

        for d in range(D):
            vals_n = R[mask_n, d]
            vals_a = R[mask_a, d]

            # ── Cohen's d ──
            mu_n, mu_a = vals_n.mean(), vals_a.mean()
            var_n, var_a = vals_n.var(ddof=1), vals_a.var(ddof=1)
            pooled_std = np.sqrt((var_n + var_a) / 2 + 1e-15)
            cohen_d = abs(mu_a - mu_n) / pooled_std

            # ── Overlap fraction (5th–95th percentile) ──
            n_lo, n_hi = np.percentile(vals_n, [5, 95])
            a_lo, a_hi = np.percentile(vals_a, [5, 95])
            overlap = max(0, min(n_hi, a_hi) - max(n_lo, a_lo))
            span = max(n_hi, a_hi) - min(n_lo, a_lo) + 1e-15
            overlap_frac = overlap / span

            # ── Per-dimension AUC ──
            try:
                all_vals = np.concatenate([vals_n, vals_a])
                all_labels = np.concatenate([np.zeros(len(vals_n)),
                                             np.ones(len(vals_a))])
                dim_auc = roc_auc_score(all_labels, all_vals)
                dim_auc = max(dim_auc, 1 - dim_auc)  # direction-invariant
            except Exception:
                dim_auc = 0.5

            # ── Fisher ratio (between / within variance) ──
            grand_mean = R[:, d].mean()
            sb = mask_n.sum() * (mu_n - grand_mean)**2 + \
                 mask_a.sum() * (mu_a - grand_mean)**2
            sw = (mask_n.sum() - 1) * var_n + (mask_a.sum() - 1) * var_a + 1e-15
            fisher_ratio = sb / sw

            # ── Combine into weight ──
            if self.method == "full":
                auc_bonus = 1.0 + 2.0 * (dim_auc - 0.5)  # 1.0–2.0
                w = (cohen_d ** self.power) * (1 - overlap_frac) * auc_bonus
            elif self.method == "cohen":
                w = cohen_d ** self.power
            elif self.method == "auc":
                w = (dim_auc - 0.5) ** self.power  # 0–0.5 range
            elif self.method == "fisher_ratio":
                w = fisher_ratio ** (self.power / 2)
            else:
                w = cohen_d ** self.power

            weights[d] = max(w, self.floor)

            stats.append({
                "dim": d,
                "cohen_d": cohen_d,
                "overlap_frac": overlap_frac,
                "auc": dim_auc,
                "fisher_ratio": fisher_ratio,
                "raw_weight": w,
                "final_weight": weights[d],
            })

        # Normalise: weights sum to D (preserves representation scale)
        w_sum = weights.sum()
        if w_sum > 0:
            weights = weights / w_sum * D

        self.weights_ = weights

        # ── Compute per-dimension power exponents ──
        # Discriminative score ∈ [0, 1] for each dim
        # Combine Cohen's d (capped at 3) and (1 - overlap)
        disc_scores = np.zeros(D)
        for d in range(D):
            s = stats[d]
            cd_norm = min(s["cohen_d"], 3.0) / 3.0     # 0–1
            sep = 1.0 - s["overlap_frac"]                # 0–1
            auc_norm = 2.0 * (s["auc"] - 0.5)           # 0–1
            disc_scores[d] = 0.4 * cd_norm + 0.3 * sep + 0.3 * auc_norm

        self.disc_scores_ = disc_scores

        # ── Per-dimension tanh steepness ──
        # k_d = gamma * disc_score — clear dims saturate, blind dims flatten
        self.steepness_ = self.gamma * disc_scores

        # Decision boundary per dim: midpoint of class means
        self.boundaries_ = np.zeros(D)
        self.pooled_std_ = np.zeros(D)
        for d in range(D):
            vals_n = R[mask_n, d]
            vals_a = R[mask_a, d]
            mu_n, mu_a = vals_n.mean(), vals_a.mean()
            var_n = vals_n.var(ddof=1)
            var_a = vals_a.var(ddof=1)
            self.boundaries_[d] = (mu_n + mu_a) / 2.0
            self.pooled_std_[d] = np.sqrt((var_n + var_a) / 2.0 + 1e-15)

        # Alias for compatibility
        self.alphas_ = self.steepness_

        self.dim_stats_ = stats
        self._fitted = True

        if self.verbose:
            self._print_scan(law_names, law_dims)

        return self

    def magnify(self, R):
        """
        Boundary-centred saturating transform.

        For each dimension d:
          z = (r - b_d) / σ_pooled_d        # deviation from decision boundary
          r' = tanh(k_d · z)                # saturating non-linearity

        Clear dims (large k_d):
          Normal side → tanh(large_negative) ≈ −1
          Anomaly side → tanh(large_positive) ≈ +1
          Within-class variance collapses, Cohen's d explodes.

        Blind dims (tiny k_d):
          tanh(tiny · z) ≈ tiny · z → dimension is scaled to near-zero.

        Output is in [−1, +1] per dimension.

        Parameters
        ----------
        R : ndarray (N, D)

        Returns
        -------
        R_magnified : ndarray (N, D)
        """
        if not self._fitted:
            raise RuntimeError("Call fit() first")

        N, D = R.shape
        R_out = np.empty_like(R)

        for d in range(D):
            b = self.boundaries_[d]
            sigma = self.pooled_std_[d]
            k = self.steepness_[d]

            # Standardise relative to decision boundary
            z = (R[:, d] - b) / sigma

            # Saturating non-linearity
            R_out[:, d] = np.tanh(k * z)

        return R_out

    def score(self, R):
        """
        Direct per-dimension anomaly scoring — bypasses Fisher entirely.

        For each dimension, computes a z-score relative to the normal
        reference distribution. Then combines across dimensions using
        the discriminative weights, so clear dimensions dominate and
        blind dimensions are silenced.

        This captures non-linear separation that Fisher misses:
        a point can be anomalous on dimension d12 but normal on d06,
        and the magnifier ensures d12 drives the final score.

        Parameters
        ----------
        R : ndarray (N, D)

        Returns
        -------
        scores : ndarray (N,)  — higher = more anomalous
        """
        if not self._fitted:
            raise RuntimeError("Call fit() first")

        D = R.shape[1]
        per_dim_scores = np.zeros_like(R)
        for d in range(D):
            mu = self._ref_mean[d]
            sigma = self._ref_std[d]
            z = (R[:, d] - mu) / (sigma + 1e-15)
            if self._anom_direction[d] < 0:
                z = -z
            # One-sided: only count positive deviations as anomalous
            per_dim_scores[:, d] = np.maximum(z, 0)

        # Weighted combination: clear dims dominate
        w = self.weights_ / (self.weights_.sum() + 1e-15)

        # Three channels combined:
        # 1. Weighted mean — smooth aggregate signal
        ch_mean = per_dim_scores @ w

        # 2. Weighted max — the single clearest dimension's alarm
        weighted_scores = per_dim_scores * w[np.newaxis, :]
        ch_max = weighted_scores.max(axis=1)

        # 3. Top-K consensus — agreement among the best dimensions
        top_k = min(5, D)
        top_dims = np.argsort(self.weights_)[::-1][:top_k]
        ch_topk = per_dim_scores[:, top_dims].mean(axis=1)

        # Combine: 50% weighted mean + 25% max + 25% top-K consensus
        scores = 0.50 * ch_mean + 0.25 * ch_max + 0.25 * ch_topk
        return scores

    def _print_scan(self, law_names=None, law_dims=None):
        """Print per-dimension scan results grouped by law."""
        print("\n┌──────────────────────────────────────────────────────────────────┐")
        print("│      DIMENSION MAGNIFIER — BOUNDARY-CENTRED TANH SCAN           │")
        print("├──────────────────────────────────────────────────────────────────┤")

        if law_names and law_dims:
            offset = 0
            for name, ndim in zip(law_names, law_dims):
                print(f"│  {name} ({ndim} dims)")
                for i in range(ndim):
                    s = self.dim_stats_[offset + i]
                    k = self.steepness_[offset + i]
                    disc = self.disc_scores_[offset + i]
                    if disc >= self.blind_threshold:
                        action = f"SATURATE k={k:.1f}"
                        bar_len = int(min(k, 4) / 4 * 15)
                        bar = "█" * bar_len + "░" * (15 - bar_len)
                        status = "✓ CLEAR"
                    else:
                        action = f"SILENCE k={k:.2f}"
                        bar_len = int(min(k, 1) / 1.0 * 15)
                        bar = "·" * (15 - bar_len) + "░" * bar_len
                        status = "✗ BLIND"
                    print(f"│    d{offset+i:02d}  d={s['cohen_d']:.2f}  "
                          f"ovlp={s['overlap_frac']:.0%}  "
                          f"auc={s['auc']:.3f}  "
                          f"disc={disc:.2f}  "
                          f"{bar}  {action}  {status}")
                offset += ndim
        else:
            for i, s in enumerate(self.dim_stats_):
                k = self.steepness_[i]
                disc = self.disc_scores_[i]
                if disc >= self.blind_threshold:
                    action = f"SATURATE k={k:.1f}"
                    bar_len = int(min(k, 4) / 4 * 15)
                    bar = "█" * bar_len + "░" * (15 - bar_len)
                    status = "✓ CLEAR"
                else:
                    action = f"SILENCE k={k:.2f}"
                    bar_len = int(min(k, 1) / 1.0 * 15)
                    bar = "·" * (15 - bar_len) + "░" * bar_len
                    status = "✗ BLIND"
                print(f"│  d{s['dim']:02d}  d={s['cohen_d']:.2f}  "
                      f"ovlp={s['overlap_frac']:.0%}  "
                      f"auc={s['auc']:.3f}  "
                      f"disc={disc:.2f}  "
                      f"{bar}  {action}  {status}")

        # Summary
        n_clear = (self.disc_scores_ >= self.blind_threshold).sum()
        n_blind = (self.disc_scores_ < self.blind_threshold).sum()
        print(f"├──────────────────────────────────────────────────────────────────┤")
        print(f"│  Saturated: {n_clear:2d} dims  (classes pushed to ±1)")
        print(f"│  Silenced:  {n_blind:2d} dims  (scaled to ~0)")
        print(f"│  Max k: {self.steepness_.max():.2f}   Min k: {self.steepness_.min():.2f}")
        print(f"└──────────────────────────────────────────────────────────────────┘\n")

    def get_top_dims(self, n=5):
        """Return indices of top-n most discriminative dimensions."""
        if not self._fitted:
            raise RuntimeError("Call fit() first")
        return np.argsort(self.weights_)[::-1][:n]

    def get_blind_dims(self, threshold=0.3):
        """Return indices of blind (suppressed) dimensions."""
        if not self._fitted:
            raise RuntimeError("Call fit() first")
        return np.where(self.weights_ < threshold)[0]

    def __repr__(self):
        if self._fitted:
            n_amp = (self.weights_ > 1.0).sum()
            n_sup = (self.weights_ < 0.5).sum()
            return (f"DimensionMagnifier(method='{self.method}', "
                    f"amplified={n_amp}, suppressed={n_sup})")
        return f"DimensionMagnifier(method='{self.method}', unfitted)"
