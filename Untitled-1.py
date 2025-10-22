# ==== GPU / Scaler Persistence Utilities ====
import json, os, math, hashlib, datetime
from pathlib import Path

GPU_BACKEND_AVAILABLE = False
try:
    import cudf
    try:
        from cuml.preprocessing import StandardScaler as cuStandardScaler
        GPU_BACKEND_AVAILABLE = True
    except Exception:
        GPU_BACKEND_AVAILABLE = False
except ImportError:
    pass

class GPUNormalizer:
    """
    Lightweight GPU-aware standardizer (fit/transform) with JSON persistence.
    Works with cudf.DataFrame. Falls back to pandas if cudf absent.
    """
    def __init__(self):
        self.feature_names = []
        self.mean_ = None
        self.scale_ = None
        self.fitted_ = False
        self.backend = 'cudf' if GPU_BACKEND_AVAILABLE else 'pandas'

    def fit(self, df, columns=None):
        if columns is None:
            columns = [c for c in df.columns if df[c].dtype.kind in ('i','u','f')]
        self.feature_names = columns
        if GPU_BACKEND_AVAILABLE and isinstance(df, cudf.DataFrame):
            stats = df[self.feature_names].agg(['mean','std'])
            self.mean_ = stats.loc['mean'].to_pandas().values
            std_vals = stats.loc['std'].to_pandas().values
        else:
            stats = df[self.feature_names].agg(['mean','std'])
            self.mean_ = stats.loc['mean'].values
            std_vals = stats.loc['std'].values
        # Avoid div zero
        self.scale_ = [s if s and s > 1e-12 else 1.0 for s in std_vals]
        self.fitted_ = True
        return self

    def transform(self, df):
        if not self.fitted_:
            raise RuntimeError("GPUNormalizer not fitted.")
        backend_cudf = GPU_BACKEND_AVAILABLE and isinstance(df, cudf.DataFrame)
        for i, col in enumerate(self.feature_names):
            if col not in df.columns:
                continue
            if backend_cudf:
                df[col] = (df[col] - self.mean_[i]) / self.scale_[i]
            else:
                df[col] = (df[col].astype('float32') - self.mean_[i]) / self.scale_[i]
        return df

    def fit_transform(self, df, columns=None):
        return self.fit(df, columns=columns).transform(df)

    def to_json(self, path):
        payload = {
            'feature_names': self.feature_names,
            'mean': list(map(float, self.mean_)),
            'scale': list(map(float, self.scale_)),
            'backend': self.backend,
            'timestamp_utc': datetime.datetime.utcnow().isoformat() + 'Z'
        }
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w') as f:
            json.dump(payload, f, indent=2)
        return path

    @classmethod
    def from_json(cls, path):
        with open(path,'r') as f:
            data = json.load(f)
        inst = cls()
        inst.feature_names = data['feature_names']
        inst.mean_ = data['mean']
        inst.scale_ = data['scale']
        inst.backend = data.get('backend','pandas')
        inst.fitted_ = True
        return inst


def persist_cuml_scaler(cuml_scaler, feature_names, path):
    """
    For an existing cuStandardScaler (if you already used it) export attributes.
    """
    payload = {
        'feature_names': feature_names,
        'mean': list(map(float, cuml_scaler.mean_)),
        'scale': list(map(float, cuml_scaler.scale_)),
        'variant': 'cuml.StandardScaler',
        'timestamp_utc': datetime.datetime.utcnow().isoformat() + 'Z'
    }
    with open(path, 'w') as f:
        json.dump(payload, f, indent=2)
    return path


def load_cuml_scaler(path):
    """
    Create a dummy object with transform() mimicking cuStandardScaler using stored stats.
    """
    with open(path,'r') as f:
        payload = json.load(f)
    class _Wrapper:
        def __init__(self, p):
            self.feature_names = p['feature_names']
            self.mean_ = p['mean']
            self.scale_ = p['scale']
        def transform(self, df):
            # cudf or pandas
            backend_cudf = GPU_BACKEND_AVAILABLE and isinstance(df, cudf.DataFrame)
            for i,col in enumerate(self.feature_names):
                if col in df.columns:
                    if backend_cudf:
                        df[col] = (df[col] - self.mean_[i]) / self.scale_[i]
                    else:
                        df[col] = (df[col].astype('float32') - self.mean_[i]) / self.scale_[i]
            return df
    return _Wrapper(payload)