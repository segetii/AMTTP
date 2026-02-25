"""
UDL Compute Backend — Hardware-Agnostic Array Dispatch
=======================================================
Detects the best available compute backend at import time:

    JAX   →  XLA JIT compilation, GPU/TPU, automatic cache-blocking
    CuPy  →  CUDA GPU arrays (NVIDIA only)
    NumPy →  CPU fallback (always available)

Usage::

    from udl.backend import xp, jit, vmap, to_numpy, BACKEND

    @jit
    def hot_function(a, b):
        return xp.dot(a, b)

The ``xp`` namespace mirrors numpy's API.  ``jit`` is a no-op when
JAX is unavailable, so decorated functions run identically on NumPy.

Author: Odeyemi Olusegun Israel
"""

from __future__ import annotations

import numpy as np
from typing import Callable, TypeVar

F = TypeVar("F", bound=Callable)

# ═══════════════════════════════════════════════════════════════
# Backend detection — JAX preferred, then CuPy, then NumPy
# ═══════════════════════════════════════════════════════════════
BACKEND: str = "numpy"
xp = np  # array namespace — drop-in numpy replacement

_jax_available = False
_cupy_available = False

try:
    import jax
    import jax.numpy as jnp
    # Suppress JAX's verbose startup warnings
    jax.config.update("jax_platform_name", "cpu")  # safe default; GPU auto-detects
    BACKEND = "jax"
    xp = jnp
    _jax_available = True
except (ImportError, Exception):
    pass

if not _jax_available:
    try:
        import cupy as cp
        BACKEND = "cupy"
        xp = cp
        _cupy_available = True
    except (ImportError, Exception):
        pass


# ═══════════════════════════════════════════════════════════════
# JIT / vmap decorators (no-ops when JAX is absent)
# ═══════════════════════════════════════════════════════════════

def jit(fn: F = None, **kwargs) -> F:
    """JIT-compile a function.  Falls through to plain Python if JAX
    is not installed.

    Supports both ``@jit`` and ``@jit(donate_argnums=...)`` syntax.
    """
    if fn is None:
        # Called as @jit(kw=...)
        def wrapper(f: F) -> F:
            if _jax_available:
                return jax.jit(f, **kwargs)
            return f
        return wrapper

    # Called as @jit (no parens)
    if _jax_available:
        return jax.jit(fn, **kwargs)
    return fn


def vmap(fn: F = None, **kwargs) -> F:
    """Auto-vectorise a function over a batch axis.
    Falls through to the original function when JAX is absent
    (caller is responsible for passing batched arrays that already
    work with numpy broadcasting).
    """
    if fn is None:
        def wrapper(f: F) -> F:
            if _jax_available:
                return jax.vmap(f, **kwargs)
            return f
        return wrapper

    if _jax_available:
        return jax.vmap(fn, **kwargs)
    return fn


# ═══════════════════════════════════════════════════════════════
# Interop helpers
# ═══════════════════════════════════════════════════════════════

def to_numpy(arr) -> np.ndarray:
    """Convert any backend array to a plain NumPy ndarray.

    Safe to call on arrays that are already NumPy — returns a view.
    """
    if _jax_available and hasattr(arr, "device"):
        # JAX DeviceArray → numpy
        return np.asarray(arr)
    if _cupy_available and hasattr(arr, "get"):
        return arr.get()
    return np.asarray(arr)


def from_numpy(arr: np.ndarray):
    """Convert a NumPy array to the active backend's array type."""
    if _jax_available:
        return jnp.asarray(arr)
    if _cupy_available:
        return cp.asarray(arr)
    return arr


def info() -> dict:
    """Return a summary of the active backend configuration."""
    result = {
        "backend": BACKEND,
        "jax_available": _jax_available,
        "cupy_available": _cupy_available,
    }
    if _jax_available:
        result["jax_version"] = jax.__version__
        result["jax_devices"] = [str(d) for d in jax.devices()]
    return result
