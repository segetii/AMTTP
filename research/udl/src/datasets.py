"""
Benchmark Dataset Loaders — Cross-Domain Validation
=====================================================
Easy-access loaders for the benchmark datasets used
in the BSDT and UDL papers.

Each loader returns (X, y) where y ∈ {0, 1} with 1 = anomaly.
"""

import numpy as np

try:
    from sklearn.datasets import (
        fetch_openml,
        load_digits,
        make_classification,
    )
    HAS_SKLEARN = True
except ImportError:
    HAS_SKLEARN = False


def _require_sklearn():
    if not HAS_SKLEARN:
        raise ImportError("scikit-learn is required for dataset loaders. "
                          "Install with: pip install scikit-learn")


# ═══════════════════════════════════════════════════════════════════
# SYNTHETIC GENERATORS
# ═══════════════════════════════════════════════════════════════════

def make_synthetic(n_normal=1000, n_anomaly=50, n_features=10,
                   anomaly_offset=3.0, random_state=42):
    """
    Generate a synthetic anomaly detection dataset.

    Normal data ~ N(0, I), anomalies ~ N(offset, I).
    Baseline for sanity-checking pipelines.
    """
    rng = np.random.RandomState(random_state)
    X_normal = rng.randn(n_normal, n_features)
    X_anomaly = rng.randn(n_anomaly, n_features) + anomaly_offset
    X = np.vstack([X_normal, X_anomaly])
    y = np.array([0] * n_normal + [1] * n_anomaly)
    # Shuffle
    idx = rng.permutation(len(y))
    return X[idx], y[idx]


def make_mimic_anomalies(n_normal=1000, n_anomaly=50, n_features=10,
                         mimic_fraction=0.5, random_state=42):
    """
    Generate anomalies that partially mimic normal patterns.
    Tests whether UDL can detect camouflaged mimics.

    mimic_fraction: portion of anomaly features matching normal distribution.
    """
    rng = np.random.RandomState(random_state)
    X_normal = rng.randn(n_normal, n_features)

    n_mimic_features = int(n_features * mimic_fraction)
    n_deviant_features = n_features - n_mimic_features

    X_anomaly = np.zeros((n_anomaly, n_features))
    X_anomaly[:, :n_mimic_features] = rng.randn(n_anomaly, n_mimic_features)
    X_anomaly[:, n_mimic_features:] = (
        rng.randn(n_anomaly, n_deviant_features) * 0.5 + 4.0
    )

    X = np.vstack([X_normal, X_anomaly])
    y = np.array([0] * n_normal + [1] * n_anomaly)
    idx = rng.permutation(len(y))
    return X[idx], y[idx]


# ═══════════════════════════════════════════════════════════════════
# REAL-WORLD LOADERS (via scikit-learn / OpenML)
# ═══════════════════════════════════════════════════════════════════

def load_mammography():
    """
    Mammography dataset (OpenML ID 310).
    ~11,183 samples, 6 features. Anomaly class = minority (~2.3%).
    """
    _require_sklearn()
    data = fetch_openml(data_id=310, as_frame=False)
    X = data.data.astype(np.float64)
    y_raw = data.target
    # Convert to binary
    classes = np.unique(y_raw)
    minority = classes[np.argmin([np.sum(y_raw == c) for c in classes])]
    y = (y_raw == minority).astype(int)
    return X, y


def load_shuttle():
    """
    Shuttle dataset (OpenML). 9 features.
    Class 1 is normal (~80%), rest are anomalies.
    """
    _require_sklearn()
    data = fetch_openml(name="shuttle", version=1, as_frame=False)
    X = data.data.astype(np.float64)
    y = (data.target.astype(int) != 1).astype(int)
    return X, y


def load_pendigits():
    """
    Pen-Based Recognition of Handwritten Digits.
    16 features. We treat digit 4 as the anomaly class
    (following BSDT convention).
    """
    _require_sklearn()
    digits = load_digits()
    X = digits.data.astype(np.float64)
    y = (digits.target == 4).astype(int)
    return X, y


def load_creditcard_sample(n_samples=10000, random_state=42):
    """
    Credit Card Fraud (OpenML). 30 features.
    Returns a balanced subsample for tractable benchmarking.
    """
    _require_sklearn()
    data = fetch_openml(name="creditcard", version=1, as_frame=False)
    X = data.data.astype(np.float64)
    y = data.target.astype(int)

    rng = np.random.RandomState(random_state)
    fraud_idx = np.where(y == 1)[0]
    normal_idx = np.where(y == 0)[0]
    n_fraud = min(len(fraud_idx), n_samples // 10)
    n_normal = n_samples - n_fraud

    sel = np.concatenate([
        rng.choice(fraud_idx, n_fraud, replace=False),
        rng.choice(normal_idx, n_normal, replace=False),
    ])
    rng.shuffle(sel)
    return X[sel], y[sel]


# ═══════════════════════════════════════════════════════════════════
# DATASET REGISTRY
# ═══════════════════════════════════════════════════════════════════

DATASETS = {
    "synthetic": make_synthetic,
    "mimic": make_mimic_anomalies,
    "mammography": load_mammography,
    "shuttle": load_shuttle,
    "pendigits": load_pendigits,
    "creditcard": load_creditcard_sample,
}


def list_datasets():
    """List available benchmark datasets."""
    return list(DATASETS.keys())


def load_dataset(name, **kwargs):
    """Load a benchmark dataset by name."""
    if name not in DATASETS:
        raise ValueError(f"Unknown dataset '{name}'. Available: {list_datasets()}")
    return DATASETS[name](**kwargs)
