"""
Anomaly Tensor — Multi-Spectrum Deviation Representation
=========================================================
Composes the outputs of all spectrum operators into a structured
tensor object. Provides Magnitude-Direction-Novelty (MDN)
decomposition and cross-law coupling analysis.

Conceptual shape:  T[i, k, t, d]
  i = observation index
  k = law-domain index (stat, chaos, spectral, geom, exp)
  t = temporal index (1 for static snapshots)
  d = dimension within each law's feature space
"""

import numpy as np


class AnomalyTensor:
    """
    Multi-spectrum tensor wrapping the stacked law-domain projections.

    Core decomposition:
      - magnitude:  ||v_i|| across all law domains
      - direction:  v_i / ||v_i|| — normalised deviation direction
      - novelty:    angular deviation from nearest reference direction
    """

    def __init__(self, centroid=None):
        """
        Parameters
        ----------
        centroid : ndarray or None
            Reference centroid in unified representation space.
            If None, set via fit().
        """
        self.centroid = centroid
        self.ref_directions_ = None

    def fit(self, R_ref, centroid=None):
        """
        Fit tensor decomposition from reference representations.

        Parameters
        ----------
        R_ref : ndarray of shape (N_ref, D_total)
            Stacked representation of reference data across all law domains.
        centroid : ndarray of shape (D_total,) or None
            If provided, overrides the stored centroid.
        """
        if centroid is not None:
            self.centroid = centroid
        if self.centroid is None:
            self.centroid = R_ref.mean(axis=0)

        # Reference deviation vectors
        dev_vecs = R_ref - self.centroid
        norms = np.linalg.norm(dev_vecs, axis=1, keepdims=True)
        norms = np.maximum(norms, 1e-10)
        self.ref_directions_ = dev_vecs / norms

        # Store reference magnitude statistics for z-score normalisation
        self.ref_magnitude_mean_ = np.linalg.norm(dev_vecs, axis=1).mean()
        self.ref_magnitude_std_ = max(np.linalg.norm(dev_vecs, axis=1).std(), 1e-10)

        return self

    def store_ref_law_stats(self, tensor_result):
        """
        Store per-law magnitude statistics from reference data.
        Called after build() on the reference set so that subsequent
        build() calls on test data carry z-score normalisation info.
        """
        lm = tensor_result.law_magnitudes  # (N_ref, K)
        self.ref_law_means_ = lm.mean(axis=0)  # (K,)
        self.ref_law_stds_ = np.maximum(lm.std(axis=0), 1e-10)  # (K,)

        # Store sorted per-law magnitudes for quantile scoring (variant C)
        self.ref_law_sorted_ = np.sort(lm, axis=0)  # (N_ref, K)

        # Store total reference magnitudes for variant D hybrid
        total_mag = tensor_result.magnitude
        self.ref_total_sorted_ = np.sort(total_mag)

    def build(self, R, law_dims):
        """
        Construct tensor from stacked representations.

        Parameters
        ----------
        R : ndarray of shape (N, D_total)
            Stacked representation vectors.
        law_dims : list of int
            Dimensionality per law-domain, e.g. [5, 3, 4, 3, m].
            Must sum to D_total.

        Returns
        -------
        TensorResult with .tensor, .magnitude, .direction, .novelty
        """
        N, D = R.shape
        assert sum(law_dims) == D, f"law_dims sum {sum(law_dims)} ≠ D={D}"

        K = len(law_dims)
        max_d = max(law_dims)

        # Build 3D tensor: (N, K, max_d) — padded
        tensor = np.zeros((N, K, max_d), dtype=np.float64)
        offset = 0
        for k, dim in enumerate(law_dims):
            tensor[:, k, :dim] = R[:, offset:offset + dim]
            offset += dim

        # ── Magnitude-Direction-Novelty decomposition ──
        c = self.centroid if self.centroid is not None else np.zeros(D)
        dev_vecs = R - c

        magnitude = np.linalg.norm(dev_vecs, axis=1)

        norms = np.maximum(magnitude, 1e-10)
        direction = dev_vecs / norms[:, None]

        # Per-law magnitudes
        law_magnitudes = np.zeros((N, K))
        offset = 0
        for k, dim in enumerate(law_dims):
            law_magnitudes[:, k] = np.linalg.norm(
                R[:, offset:offset + dim] - c[offset:offset + dim],
                axis=1
            )
            offset += dim

        # Novelty: angular deviation from nearest reference direction
        novelty = self._compute_novelty(direction)

        # Per-law reference statistics (stored during fit)
        ref_law_means = getattr(self, 'ref_law_means_', None)
        ref_law_stds = getattr(self, 'ref_law_stds_', None)

        return TensorResult(
            tensor=tensor,
            raw=R,
            magnitude=magnitude,
            direction=direction,
            novelty=novelty,
            law_magnitudes=law_magnitudes,
            law_dims=law_dims,
            centroid=c,
            ref_law_means=ref_law_means,
            ref_law_stds=ref_law_stds,
            ref_magnitude_mean=getattr(self, 'ref_magnitude_mean_', None),
            ref_magnitude_std=getattr(self, 'ref_magnitude_std_', None),
            ref_law_sorted=getattr(self, 'ref_law_sorted_', None),
            ref_total_sorted=getattr(self, 'ref_total_sorted_', None),
        )

    def _compute_novelty(self, directions):
        """
        Novelty = min angular distance to any reference direction.
        Higher values → more novel (anomalous) direction.
        Uses batched computation for memory efficiency on large datasets.
        """
        N = directions.shape[0]
        novelty = np.zeros(N)

        if self.ref_directions_ is None or len(self.ref_directions_) == 0:
            return novelty

        N_ref = len(self.ref_directions_)

        batch_size = max(1, min(500, 50_000_000 // max(N_ref, 1)))

        for start in range(0, N, batch_size):
            end = min(start + batch_size, N)
            batch = directions[start:end]
            cos_sim = batch @ self.ref_directions_.T
            cos_sim = np.clip(cos_sim, -1, 1)
            max_sim = cos_sim.max(axis=1)
            novelty[start:end] = np.arccos(max_sim) / np.pi

        return novelty

    def cross_law_coupling(self, tensor_result):
        """
        Compute coupling matrix between law domains.

        C[j, k] = correlation of magnitudes between laws j and k
        across the observation set. High off-diagonal values indicate
        that anomalies in one law domain co-occur with anomalies in another.
        """
        lm = tensor_result.law_magnitudes
        K = lm.shape[1]
        coupling = np.corrcoef(lm.T)  # (K, K)
        return coupling


class TensorResult:
    """
    Container for tensor decomposition results.
    """

    def __init__(self, tensor, raw, magnitude, direction, novelty,
                 law_magnitudes, law_dims, centroid,
                 ref_law_means=None, ref_law_stds=None,
                 ref_magnitude_mean=None, ref_magnitude_std=None,
                 ref_law_sorted=None, ref_total_sorted=None):
        self.tensor = tensor              # (N, K, max_d)
        self.raw = raw                    # (N, D_total)
        self.magnitude = magnitude        # (N,)
        self.direction = direction        # (N, D_total)
        self.novelty = novelty            # (N,)
        self.law_magnitudes = law_magnitudes  # (N, K)
        self.law_dims = law_dims          # list of int
        self.centroid = centroid           # (D_total,)
        self.ref_law_means = ref_law_means    # (K,) or None
        self.ref_law_stds = ref_law_stds      # (K,) or None
        self.ref_magnitude_mean = ref_magnitude_mean
        self.ref_magnitude_std = ref_magnitude_std
        self.ref_law_sorted = ref_law_sorted    # (N_ref, K) or None
        self.ref_total_sorted = ref_total_sorted  # (N_ref,) or None

    @property
    def n_observations(self):
        return self.tensor.shape[0]

    @property
    def n_laws(self):
        return self.tensor.shape[1]

    def anomaly_score(self, weights=None):
        """
        Composite anomaly score combining magnitude + novelty.

        score = w_mag * magnitude + w_nov * novelty

        Parameters
        ----------
        weights : tuple of (w_magnitude, w_novelty), default (0.7, 0.3)
        """
        if weights is None:
            weights = (0.7, 0.3)
        w_m, w_n = weights

        # Normalise magnitude to [0, 1]
        mag_max = self.magnitude.max() + 1e-10
        mag_norm = self.magnitude / mag_max

        return w_m * mag_norm + w_n * self.novelty

    def anomaly_score_v2(self, weights=None):
        """
        V2 composite anomaly score — per-law z-score + novelty.

        Each law domain's magnitude is z-scored against the reference
        distribution, so a subtle deviation in ONE law domain is visible
        even if all other laws say "normal". The max z-score across
        laws is used (any single law screaming = anomaly detected).

        score = w_m * sigmoid(max_z) + w_n * novelty

        This fixes the magnitude-crushing problem where one extreme
        outlier makes all subtle anomalies invisible.
        """
        if weights is None:
            weights = (0.7, 0.3)
        w_m, w_n = weights

        if self.ref_law_means is not None and self.ref_law_stds is not None:
            # Per-law z-scores: how many σ from normal mean in each law
            z_scores = (self.law_magnitudes - self.ref_law_means) / self.ref_law_stds

            # Take max across laws — any single law deviating is enough
            max_z = z_scores.max(axis=1)

            # Also compute mean z for multi-law deviations
            mean_z = z_scores.mean(axis=1)

            # Combine: max catches single-law anomalies, mean catches spread
            combined_z = 0.6 * max_z + 0.4 * mean_z

            # Sigmoid maps z-scores to [0, 1] — z=0 → 0.5, z=3 → 0.95
            mag_score = 1.0 / (1.0 + np.exp(-combined_z))
        else:
            # Fallback: z-score total magnitude
            if self.ref_magnitude_mean is not None:
                z = (self.magnitude - self.ref_magnitude_mean) / self.ref_magnitude_std
                mag_score = 1.0 / (1.0 + np.exp(-z))
            else:
                mag_max = self.magnitude.max() + 1e-10
                mag_score = self.magnitude / mag_max

        return w_m * mag_score + w_n * self.novelty

    # ── Variant A: One-sided activation ──────────────────────────

    def anomaly_score_v3a(self, weights=None):
        """
        One-sided exponential activation on per-law z-scores.

        Maps z <= 0 → 0, z > 0 → 1 - exp(-z²/2).
        Normal data (z~0) → ~0. Anomaly (z=3) → 0.989.
        No sigmoid compression problem.
        """
        if weights is None:
            weights = (0.7, 0.3)
        w_m, w_n = weights

        if self.ref_law_means is not None:
            z = (self.law_magnitudes - self.ref_law_means) / self.ref_law_stds
            z_pos = np.maximum(z, 0)
            activated = 1.0 - np.exp(-z_pos ** 2 / 2.0)
            # max across laws + mean
            max_a = activated.max(axis=1)
            mean_a = activated.mean(axis=1)
            mag_score = 0.6 * max_a + 0.4 * mean_a
        else:
            mag_max = self.magnitude.max() + 1e-10
            mag_score = self.magnitude / mag_max

        return w_m * mag_score + w_n * self.novelty

    # ── Variant B: Shifted sigmoid ───────────────────────────────

    def anomaly_score_v3b(self, weights=None):
        """
        Sigmoid shifted by expected normal max-z.

        For K laws, expected max of K independent N(0,1) ≈ √(2 ln K).
        Shift: sigmoid(z - c) so normal → ~0.5, anomalies → >0.8.
        Then rescale to [0,1] via (sig - 0.5) * 2 clipped.
        """
        if weights is None:
            weights = (0.7, 0.3)
        w_m, w_n = weights

        if self.ref_law_means is not None:
            z = (self.law_magnitudes - self.ref_law_means) / self.ref_law_stds
            max_z = z.max(axis=1)
            mean_z = z.mean(axis=1)
            combined_z = 0.6 * max_z + 0.4 * mean_z

            # Shift by expected normal max_z ≈ √(2 ln K)
            K = self.law_magnitudes.shape[1]
            shift = np.sqrt(2 * np.log(max(K, 2)))
            sig = 1.0 / (1.0 + np.exp(-(combined_z - shift)))
            # Rescale: normal maps to ~0, anomalies to ~1
            mag_score = np.clip(sig * 2.0 - 0.5, 0, 1)
        else:
            mag_max = self.magnitude.max() + 1e-10
            mag_score = self.magnitude / mag_max

        return w_m * mag_score + w_n * self.novelty

    # ── Variant C: Quantile transform ────────────────────────────

    def anomaly_score_v3c(self, weights=None):
        """
        Distribution-free quantile scoring.

        For each law, compute what percentile of the reference
        distribution the observed magnitude falls at.
        99.5th percentile → 0.995. No Gaussian assumption,
        no saturation, naturally [0,1].
        """
        if weights is None:
            weights = (0.7, 0.3)
        w_m, w_n = weights

        if self.ref_law_sorted is not None:
            N_ref, K = self.ref_law_sorted.shape
            N = self.law_magnitudes.shape[0]
            quantiles = np.zeros((N, K))

            for k in range(K):
                # searchsorted: how many ref values <= observed
                quantiles[:, k] = np.searchsorted(
                    self.ref_law_sorted[:, k],
                    self.law_magnitudes[:, k]
                ) / N_ref

            # max quantile across laws (any law at 99th pct = anomaly)
            max_q = quantiles.max(axis=1)
            mean_q = quantiles.mean(axis=1)
            mag_score = 0.6 * max_q + 0.4 * mean_q
        else:
            mag_max = self.magnitude.max() + 1e-10
            mag_score = self.magnitude / mag_max

        return w_m * mag_score + w_n * self.novelty

    # ── Variant D: Hybrid 3-channel ──────────────────────────────

    def anomaly_score_v3d(self, weights=None):
        """
        Three independent complementary channels:

        Ch1: total magnitude quantile (catches diffuse multi-law anomalies)
        Ch2: max per-law z-score one-sided (catches single-law spikes)
        Ch3: novelty (catches directional anomalies)

        score = w1*ch1 + w2*ch2 + w3*ch3, w = (0.4, 0.35, 0.25)
        """
        w1, w2, w3 = 0.40, 0.35, 0.25

        # Channel 1: total magnitude quantile
        if self.ref_total_sorted is not None:
            ch1 = np.searchsorted(
                self.ref_total_sorted, self.magnitude
            ) / len(self.ref_total_sorted)
        else:
            mag_max = self.magnitude.max() + 1e-10
            ch1 = self.magnitude / mag_max

        # Channel 2: max per-law z one-sided activation
        if self.ref_law_means is not None:
            z = (self.law_magnitudes - self.ref_law_means) / self.ref_law_stds
            z_pos = np.maximum(z, 0)
            ch2 = (1.0 - np.exp(-z_pos ** 2 / 2.0)).max(axis=1)
        else:
            ch2 = ch1  # fallback

        # Channel 3: novelty
        ch3 = self.novelty

        return w1 * ch1 + w2 * ch2 + w3 * ch3

    def __repr__(self):
        return (f"TensorResult(n={self.n_observations}, K={self.n_laws}, "
                f"dims={self.law_dims})")
