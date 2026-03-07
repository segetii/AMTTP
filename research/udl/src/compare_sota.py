"""
compare_sota.py — Dataset registry for UDL vs SOTA evaluation
==============================================================
Provides `load_all_datasets()` returning {name: (X, y)} for every
real-world benchmark used in the paper.  Synthetic/mimic generators
are excluded; they are available via datasets.py for unit tests only.
"""

from .datasets import (
    load_mammography,
    load_shuttle,
    load_pendigits,
    load_annthyroid,
    load_arrhythmia,
    load_satellite,
    load_glass,
    load_cardio,
)

# Ordered so the three original paper datasets come first
REAL_DATASETS = [
    "mammography",
    "shuttle",
    "pendigits",
    "annthyroid",
    "arrhythmia",
    "satellite",
    "glass",
    "cardio",
]

_LOADERS = {
    "mammography": load_mammography,
    "shuttle":     load_shuttle,
    "pendigits":   load_pendigits,
    "annthyroid":  load_annthyroid,
    "arrhythmia":  load_arrhythmia,
    "satellite":   load_satellite,
    "glass":       load_glass,
    "cardio":      load_cardio,
}


def load_all_datasets(subset=None):
    """
    Load all real-world benchmark datasets.

    Parameters
    ----------
    subset : list[str] | None
        If provided, only load these datasets (must be names from
        REAL_DATASETS).  If None, load all.

    Returns
    -------
    dict[str, tuple[np.ndarray, np.ndarray]]
        {name: (X, y)} where y ∈ {0, 1} and 1 = anomaly.
    """
    names = subset if subset is not None else REAL_DATASETS
    result = {}
    for name in names:
        if name not in _LOADERS:
            raise ValueError(f"Unknown dataset '{name}'. "
                             f"Available: {list(_LOADERS.keys())}")
        result[name] = _LOADERS[name]()
    return result
