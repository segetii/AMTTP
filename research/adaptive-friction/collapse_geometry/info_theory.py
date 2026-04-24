"""§XXIII Information-theoretic interpretation.

E_BSDT (Mahalanobis) = -2 log p_0(x) (up to constant) — KL divergence component.
Statistical threshold: e* = χ²_{Nd, 1-α_conf}
MFLS² = trace of sample Fisher information (×4 factor).
"""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np
from scipy.stats import chi2  # type: ignore
from .control import MasterOperator
from .state import Snapshot


@dataclass
class InformationGeometry:
    op: MasterOperator

    def kl_to_normal(self, snap: Snapshot) -> float:
        """D_KL(p̂_t || p_0) ≈ e_t / N + const; we return e_t / N."""
        e = self.op.damp.e_BSDT(snap)
        return e / snap.N

    def chi2_threshold(self, N: int, d: int, alpha_conf: float = 0.01) -> float:
        return float(chi2.ppf(1.0 - alpha_conf, df=N * d))

    def fisher_trace(self, snap: Snapshot) -> float:
        """trace(Fisher) = MFLS²/4  in pure δ_C regime."""
        m = self.op.mfls.state_mfls(snap)
        return m * m / 4.0

    def confidence_breach(self, snap: Snapshot, alpha_conf: float = 0.01) -> bool:
        e = self.op.damp.e_BSDT(snap)
        e_star = self.chi2_threshold(snap.N, snap.d, alpha_conf)
        return e > e_star
