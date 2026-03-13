"""
UDL Multi-Class Classifier
============================
Extends the Universal Deviation Law framework from anomaly detection to
multi-class supervised classification.

Core idea
---------
In anomaly detection, UDL asks: "how anomalous is x relative to the
normal reference, across K operator perspectives?"
For classification, the natural extension asks: "how anomalous is x
relative to *each class*, across K operator perspectives?"

The Magnitude-Direction-Novelty (MDN) decomposition (Section IV-C of
the paper) provides the key:  for each class c, the AnomalyTensor
decomposes a sample's deviation from class c's centroid into:
  - magnitude  r_c  (how far from class c)       → 1 scalar
  - per-law magnitudes  m_{c,k}  (which operators see it) → K scalars
  - novelty  θ_c  (how unprecedented the direction)  → 1 scalar

For C classes and K operators this yields a compact C × (K+2) feature
matrix — far smaller than concatenating raw operator outputs (C × D),
yet theoretically grounded: Theorem 1 guarantees that if the stacked
operator map Φ has full-rank Jacobian, the MDN features of distinct
classes map to distinct regions, ensuring separability.

Architecture
------------
  For each class c ∈ {1, …, C}:
    RepresentationStack_c.fit(X[y==c])  →  operators calibrated to class c
    R_c = Stack_c.transform(X)          →  per-class deviation profile
    AnomalyTensor_c.fit(R_c[y==c])      →  centroid μ_c, ref directions
    AnomalyTensor_c.build(R_c)          →  [r_c, m_{c,1..K}, θ_c]

  Concatenate:  F(x) = [MDN_1(x) | MDN_2(x) | … | MDN_C(x)] ∈ ℝ^{C(K+2)}
  Classifier head (LDA / QDA / Logistic / RF):  ŷ = head(F(x))

The per-class stack calibration is critical: each class's operators are
fitted on that class's distribution, so the MDN decomposition captures
how a sample deviates from *that specific class's* learned patterns.

The classifier follows the sklearn estimator interface:
  fit(X, y)  →  self
  predict(X) →  labels
  predict_proba(X)  →  class probabilities
  score(X, y)       →  accuracy

Author: Odeyemi Olusegun Israel
"""

from __future__ import annotations

import numpy as np
import copy
from typing import Optional, List, Tuple, Union, Dict
from sklearn.base import BaseEstimator, ClassifierMixin
from sklearn.preprocessing import LabelEncoder, StandardScaler
from sklearn.decomposition import PCA

from .stack import RepresentationStack
from .tensor import AnomalyTensor
from .spectra import (
    StatisticalSpectrum,
    ChaosSpectrum,
    SpectralSpectrum,
    GeometricSpectrum,
    ExponentialSpectrum,
    ReconstructionSpectrum,
    RankOrderSpectrum,
)


# ───────────────────────────────────────────────────────────────
#  Default operator set
# ───────────────────────────────────────────────────────────────

def _build_default_operators(extended: bool = False):
    """Build the default operator list.

    Parameters
    ----------
    extended : bool
        If True, also import new_spectra and experimental_spectra
        operators (up to 14 total).  If False, use the 6 core operators.
    """
    ops = [
        ("stat", StatisticalSpectrum()),
        ("chaos", ChaosSpectrum()),
        ("freq", SpectralSpectrum()),
        ("geom", GeometricSpectrum()),
        ("recon", ReconstructionSpectrum()),
        ("rank", RankOrderSpectrum()),
    ]

    if extended:
        try:
            from .new_spectra import (
                GraphNeighborhoodSpectrum,
                DensityRatioSpectrum,
                TopologicalSpectrum,
                DependencyCopulaSpectrum,
                CompressibilitySpectrum,
                KernelRKHSSpectrum,
            )
            ops += [
                ("graph", GraphNeighborhoodSpectrum()),
                ("density", DensityRatioSpectrum()),
                ("topo", TopologicalSpectrum()),
                ("copula", DependencyCopulaSpectrum()),
                ("compress", CompressibilitySpectrum()),
                ("kernel", KernelRKHSSpectrum()),
            ]
        except ImportError:
            pass
        try:
            from .experimental_spectra import (
                PhaseCurveSpectrum,
                GramEigenSpectrum,
            )
            ops += [
                ("phase", PhaseCurveSpectrum()),
                ("gram", GramEigenSpectrum()),
            ]
        except ImportError:
            pass
    return ops


def _clone_operators(ops):
    """Deep-clone operator list so each class gets independent instances."""
    import copy
    return [(name, copy.deepcopy(op)) for name, op in ops]


# ───────────────────────────────────────────────────────────────
#  UDLClassifier — Per-Class Deviation Profile
# ───────────────────────────────────────────────────────────────

class UDLClassifier(BaseEstimator, ClassifierMixin):
    """
    Multi-class classifier using per-class UDL MDN features.

    For each class c, a dedicated RepresentationStack is calibrated on
    class c's training data, then an AnomalyTensor decomposes every
    sample's deviation from class c through the MDN lens: magnitude,
    per-law magnitudes, and novelty.  This yields a compact C × (K+2)
    feature matrix that is passed to a lightweight classifier head.

    Parameters
    ----------
    head : str
        Classifier head.  One of 'lda', 'qda', 'logistic', 'rf'.
    extended_operators : bool
        If True, use all available operators (up to 14).
    operators : list of (name, operator) or None
        Custom operator list.  Overrides extended_operators.
    pca_variance : float or None
        If set, apply PCA retaining this fraction of variance on
        the MDN features before the head.  Default None (no PCA —
        C×(K+2) is already compact).
    standardize : bool
        Whether to Z-standardize raw input before operator projection.
    """

    def __init__(
        self,
        head: str = "qda",
        extended_operators: bool = False,
        operators=None,
        pca_variance: Optional[float] = None,
        standardize: bool = True,
    ):
        self.head = head
        self.extended_operators = extended_operators
        self.operators = operators
        self.pca_variance = pca_variance
        self.standardize = standardize

    # internal state
        self._stacks: Dict[int, RepresentationStack] = {}
        self._tensors: Dict[int, AnomalyTensor] = {}
        self._scaler: Optional[StandardScaler] = None
        self._pca: Optional[PCA] = None
        self._pca_keep: int = 0
        self._clf = None
        self._le = LabelEncoder()
        self._fitted = False

    # ── fit ────────────────────────────────────────────────────

    def fit(self, X: np.ndarray, y: np.ndarray) -> "UDLClassifier":
        """
        Fit per-class operator stacks, MDN tensors, and classifier head.

        Pipeline:
          1. Per-class RepresentationStack: for each class c, fit operators
             on class c's data → R_c(x) ∈ ℝ^D
          2. Per-class AnomalyTensor (MDN): fit on class c's representations
             → captures centroid μ_c and reference directions
          3. MDN features: magnitude, per-law magnitudes, novelty per class
             → F(x) ∈ ℝ^{C(K+2)}
          4. Optional PCA (usually unnecessary — features already compact)
          5. Classifier head

        Parameters
        ----------
        X : (N, m) array — training features
        y : (N,) array — class labels
        """
        X = np.asarray(X, dtype=np.float64)
        y_enc = self._le.fit_transform(np.asarray(y))
        self.classes_ = self._le.classes_
        n_classes = len(self.classes_)

        # 1. Standardize raw inputs
        if self.standardize:
            self._scaler = StandardScaler()
            X = self._scaler.fit_transform(X)
        else:
            self._scaler = None

        # 2. Per-class operator stacks
        base_ops = (self.operators if self.operators is not None
                    else _build_default_operators(self.extended_operators))

        self._stacks = {}
        for c in range(n_classes):
            ops_c = _clone_operators(base_ops)
            stack_c = RepresentationStack(
                operators=ops_c, standardize=False
            )
            X_class = X[y_enc == c]
            if len(X_class) < 3:
                stack_c.fit(X)
            else:
                stack_c.fit(X_class)
            self._stacks[c] = stack_c

        # 3. Per-class MDN tensors — fit on each class's representation
        self._tensors = {}
        for c in range(n_classes):
            R_c_train = self._stacks[c].transform(X[y_enc == c])
            tensor_c = AnomalyTensor()
            tensor_c.fit(R_c_train)
            ref_result = tensor_c.build(R_c_train, self._stacks[c].law_dims_)
            tensor_c.store_ref_law_stats(ref_result)
            self._tensors[c] = tensor_c

        # 4. Build MDN feature matrix: C × (K+2)
        F = self._build_mdn_features(X)

        # 5. Optional PCA
        if self.pca_variance is not None:
            D_total = F.shape[1]
            N = F.shape[0]
            n_comp = min(D_total, N - 1)
            self._pca = PCA(n_components=n_comp)
            F_pca = self._pca.fit_transform(F)
            cum_var = np.cumsum(self._pca.explained_variance_ratio_)
            k = int(np.searchsorted(cum_var, self.pca_variance) + 1)
            k = max(k, n_classes)
            k = min(k, F_pca.shape[1])
            F = F_pca[:, :k]
            self._pca_keep = k
        else:
            self._pca = None

        # 6. Train classifier head
        self._clf = self._build_head(self.head, n_classes, F.shape[1])
        self._clf.fit(F, y_enc)
        self._fitted = True
        return self

    # ── predict / predict_proba / score ───────────────────────

    def predict(self, X: np.ndarray) -> np.ndarray:
        """Predict class labels."""
        F = self._transform(X)
        y_enc = self._clf.predict(F)
        return self._le.inverse_transform(y_enc)

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """Predict class probabilities."""
        F = self._transform(X)
        return self._clf.predict_proba(F)

    def score(self, X: np.ndarray, y: np.ndarray) -> float:
        """Classification accuracy."""
        return np.mean(self.predict(X) == np.asarray(y))

    def decision_function(self, X: np.ndarray) -> np.ndarray:
        """Decision values (if head supports it)."""
        F = self._transform(X)
        if hasattr(self._clf, 'decision_function'):
            return self._clf.decision_function(F)
        return self._clf.predict_proba(F)

    # ── interpretability ──────────────────────────────────────

    def get_class_mdn_profiles(
        self, X: np.ndarray
    ) -> Dict[str, Dict[str, np.ndarray]]:
        """
        Per-class MDN decomposition for interpretability.

        Returns dict mapping class_label → {
            'magnitude': (N,),
            'law_magnitudes': (N, K),
            'novelty': (N,),
            'raw_deviation': (N, D),
        }
        """
        if not self._fitted:
            raise RuntimeError("Call fit() first")
        X = np.asarray(X, dtype=np.float64)
        if self._scaler is not None:
            X = self._scaler.transform(X)

        result = {}
        for c in sorted(self._stacks.keys()):
            R_c = self._stacks[c].transform(X)
            law_dims = self._stacks[c].law_dims_
            tr = self._tensors[c].build(R_c, law_dims)
            label = str(self._le.classes_[c])
            result[label] = {
                'magnitude': tr.magnitude,
                'law_magnitudes': tr.law_magnitudes,
                'novelty': tr.novelty,
                'raw_deviation': R_c,
            }
        return result

    # ── internals ─────────────────────────────────────────────

    def _build_mdn_features(self, X: np.ndarray) -> np.ndarray:
        """
        Build MDN-only feature matrix from per-class stacks and tensors.

        For each class c:
          - Transform x through class c's stack → R_c(x)
          - AnomalyTensor MDN decomposition → magnitude (1),
            per-law magnitudes (K), novelty (1) = K+2 features
        Total: C × (K+2) features.

        Returns (N, C*(K+2)) feature matrix.
        """
        blocks = []
        for c in sorted(self._stacks.keys()):
            R_c = self._stacks[c].transform(X)
            law_dims = self._stacks[c].law_dims_
            tr = self._tensors[c].build(R_c, law_dims)
            block = np.column_stack([
                tr.magnitude[:, None],    # (N, 1) — overall deviation
                tr.law_magnitudes,        # (N, K) — per-operator deviation
                tr.novelty[:, None],      # (N, 1) — directional novelty
            ])
            blocks.append(block)
        return np.hstack(blocks)

    def _transform(self, X: np.ndarray) -> np.ndarray:
        """Full pipeline: raw → standardize → per-class MDN → [PCA]."""
        if not self._fitted:
            raise RuntimeError("Call fit() first")
        X = np.asarray(X, dtype=np.float64)
        if self._scaler is not None:
            X = self._scaler.transform(X)
        F = self._build_mdn_features(X)
        if self._pca is not None:
            F = self._pca.transform(F)[:, :self._pca_keep]
        return F

    @staticmethod
    def _build_head(head: str, n_classes: int, n_features: int):
        """Instantiate the classifier head."""
        head = head.lower()
        if head == "lda":
            from sklearn.discriminant_analysis import (
                LinearDiscriminantAnalysis,
            )
            return LinearDiscriminantAnalysis(
                solver="svd",
                n_components=min(n_classes - 1, n_features),
            )
        elif head == "qda":
            from sklearn.discriminant_analysis import (
                QuadraticDiscriminantAnalysis,
            )
            return QuadraticDiscriminantAnalysis(reg_param=1e-2)
        elif head == "logistic":
            from sklearn.linear_model import LogisticRegression
            return LogisticRegression(
                max_iter=2000, C=1.0, solver="lbfgs",
                multi_class="multinomial",
            )
        elif head == "rf":
            from sklearn.ensemble import RandomForestClassifier
            return RandomForestClassifier(
                n_estimators=200, max_depth=None,
                random_state=42, n_jobs=-1,
            )
        else:
            raise ValueError(
                f"Unknown head '{head}'. Use 'lda', 'qda', "
                f"'logistic', or 'rf'."
            )

    def __repr__(self):
        n_ops = "?"
        if self._stacks:
            first = next(iter(self._stacks.values()))
            n_ops = len(first.operators)
        n_cls = len(self._stacks) if self._stacks else "?"
        return (
            f"UDLClassifier(head={self.head!r}, "
            f"operators={n_ops}, classes={n_cls}, "
            f"features=C×(K+2) MDN)"
        )
