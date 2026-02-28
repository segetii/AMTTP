"""
MFLSEngine — the primary commercial entry point.

One object that does everything:
  engine = MFLSEngine()
  panel  = engine.load_gsib_panel()
  result = engine.fit_and_score(panel)
  audit  = engine.bsdt_audit(panel, t=-1)
  ccyb   = engine.ccyb(panel)
  herd   = engine.herding_score(panel)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd

from mfls.core.bsdt import BSDTOperator, BSDTOperators, BSDTAudit, BSDTChannels
from mfls.core.scoring import (
    MFLSBaseline, MFLSFullBSDT, MFLSSignedLR, ALL_VARIANTS,
)
from mfls.core.network import lw_correlation_network, NetworkInfo
from mfls.core.energy import (
    calibrate_ccyb, total_energy, total_force,
    TrajectoryAnalysis, analyse_trajectory,
)
from mfls.signals.pipeline import (
    PanelData, MFLSResult, HerdingResult, standardise_panel,
)


# ---------------------------------------------------------------------------
# Crisis windows for evaluation
# ---------------------------------------------------------------------------

CRISIS_WINDOWS = [
    ("GFC", "2007-10-01", "2009-12-31"),
    ("COVID", "2020-01-01", "2021-06-30"),
    ("RateShock", "2022-01-01", "2023-12-31"),
]


def _build_crisis_labels(dates: pd.DatetimeIndex, windows=None) -> np.ndarray:
    """Binary crisis labels from date windows."""
    if windows is None:
        windows = CRISIS_WINDOWS
    labels = np.zeros(len(dates), dtype=int)
    for _, onset, end in windows:
        mask = (dates >= pd.Timestamp(onset)) & (dates <= pd.Timestamp(end))
        labels[mask] = 1
    return labels


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class MFLSEngine:
    """
    Multi-Factor Lyapunov Systemic-risk engine.

    Parameters
    ----------
    normal_start : str
        Start of calibration (normal) period.  Default "1994-01-01".
    normal_end : str
        End of calibration period.  Default "2003-12-31".
    n_boot : int
        Number of block-bootstrap replicates.
    boot_block_len : int
        Block length for bootstrap.
    threshold_pctl : float
        Percentile of normal-period signal for alarm threshold.
    """

    def __init__(
        self,
        normal_start: str = "1994-01-01",
        normal_end: str = "2003-12-31",
        n_boot: int = 500,
        boot_block_len: int = 8,
        threshold_pctl: float = 75.0,
    ):
        self.normal_start = normal_start
        self.normal_end = normal_end
        self.n_boot = n_boot
        self.boot_block_len = boot_block_len
        self.threshold_pctl = threshold_pctl

        # Fitted internal state
        self._bsdt_op: Optional[BSDTOperator] = None
        self._bsdt_full: Optional[BSDTOperators] = None
        self._panel: Optional[PanelData] = None
        self._network: Optional[NetworkInfo] = None
        self._channels: Optional[BSDTChannels] = None

    # ----- Data loading -----

    def load_gsib_panel(
        self,
        start: str = "2005-01-01",
        end: str = "2023-12-31",
        force_refresh: bool = False,
        verbose: bool = True,
    ) -> PanelData:
        """
        Load real G-SIB panel from FDIC + World Bank + ECB.

        Returns
        -------
        PanelData — standardised panel ready for scoring
        """
        from mfls.data.loaders import build_gsib_panel

        raw = build_gsib_panel(start, end, force_refresh, verbose=verbose)
        names = [m["name"] for m in raw["meta"]]

        # Adjust normal period for G-SIB (shorter history)
        ns = max(self.normal_start, start)
        ne = min(self.normal_end, "2006-12-31")

        panel = standardise_panel(
            raw["X"], raw["dates"], ns, ne, names, raw["feature_names"]
        )
        self._panel = panel
        return panel

    def load_fdic_panel(
        self,
        certs: Dict[str, int],
        start: str = "19900101",
        end: str = "20241231",
        force_refresh: bool = False,
        verbose: bool = True,
    ) -> PanelData:
        """
        Load individual bank panel from FDIC.

        Parameters
        ----------
        certs : dict mapping bank_name → FDIC CERT number

        Returns
        -------
        PanelData
        """
        from mfls.data.fdic import build_bank_panel

        raw = build_bank_panel(certs, start, end, force_refresh, verbose=verbose)

        panel = standardise_panel(
            raw["X"], raw["dates"],
            self.normal_start, self.normal_end,
            raw["names"], raw["feature_names"],
        )
        self._panel = panel
        return panel

    def load_custom_panel(
        self,
        X: np.ndarray,
        dates: pd.DatetimeIndex,
        names: list[str],
        feature_names: list[str],
        normal_start: Optional[str] = None,
        normal_end: Optional[str] = None,
    ) -> PanelData:
        """
        Load a custom (T, N, d) panel — bring your own data.

        Parameters
        ----------
        X : ndarray (T, N, d)
        dates : DatetimeIndex of length T
        names : list of N institution names
        feature_names : list of d feature names
        normal_start, normal_end : calibration period (defaults to engine config)

        Returns
        -------
        PanelData
        """
        ns = normal_start or self.normal_start
        ne = normal_end or self.normal_end
        panel = standardise_panel(X, dates, ns, ne, names, feature_names)
        self._panel = panel
        return panel

    # ----- Core pipeline -----

    def fit_and_score(
        self,
        panel: Optional[PanelData] = None,
        crisis_windows: Optional[list] = None,
        verbose: bool = True,
    ) -> MFLSResult:
        """
        Full MFLS pipeline: fit on normal period, score entire panel,
        evaluate, compute bootstrap CI.

        Parameters
        ----------
        panel : PanelData (or uses last loaded panel)
        crisis_windows : list of (name, onset, end) tuples
        verbose : bool

        Returns
        -------
        MFLSResult
        """
        panel = panel or self._panel
        if panel is None:
            raise ValueError("No panel loaded. Call load_*_panel() first.")

        X = panel.X_std
        X_normal = X[panel.normal_mask]

        # 1. Fit baseline BSDT operator
        if verbose:
            print("Fitting BSDT operator on normal period...")
        bsdt = BSDTOperator()
        bsdt.fit(X_normal)
        self._bsdt_op = bsdt

        # 2. Build network
        if verbose:
            print("Building correlation network...")
        net = lw_correlation_network(X)
        self._network = net

        # 3. Compute MFLS signal
        if verbose:
            print("Computing MFLS signal...")
        signal = bsdt.score_series(X)

        # 4. Compute full BSDT channels
        if verbose:
            print("Computing BSDT 4-channel decomposition...")
        bsdt_full = BSDTOperators()
        bsdt_full.fit(X_normal)
        channels = bsdt_full.compute_channels(X, verbose=verbose)
        self._bsdt_full = bsdt_full
        self._channels = channels

        # 5. Threshold
        normal_signal = signal[panel.normal_mask]
        threshold = float(np.percentile(normal_signal, self.threshold_pctl))

        # 6. Crisis evaluation
        cw = crisis_windows or CRISIS_WINDOWS
        labels = _build_crisis_labels(panel.dates, cw)

        auroc = self._compute_auroc(signal, labels)
        gfc_lead = self._gfc_lead(signal, panel.dates, threshold, cw)
        hr, far = self._hr_far(signal, labels, threshold)

        # 7. Bootstrap CI
        auroc_ci = None
        try:
            from mfls.evaluation.bootstrap import block_bootstrap_ci
            ci = block_bootstrap_ci(
                signal, labels, threshold,
                n_boot=self.n_boot, block_len=self.boot_block_len,
            )
            auroc_ci = (ci["auroc_lo"], ci["auroc_hi"])
        except ImportError:
            pass

        # 8. CCyB
        leverage_std = np.std(X[:, :, 0], axis=1)  # (T,)
        gamma_star = np.array([
            bsdt.energy_score(X[t]) / (bsdt.energy_score(X[t]) + 1.0)
            for t in range(X.shape[0])
        ])
        ccyb = calibrate_ccyb(signal, gamma_star, leverage_std)

        # 9. Causality (optional)
        causality = None
        try:
            from mfls.evaluation.causality import run_all_causality_tests
            causality = run_all_causality_tests(signal, labels, panel.dates, verbose=verbose)
        except ImportError:
            pass

        result = MFLSResult(
            signal=signal,
            dates=panel.dates,
            auroc=auroc,
            auroc_ci=auroc_ci,
            gfc_lead_quarters=gfc_lead,
            hit_rate=hr,
            false_alarm_rate=far,
            threshold=threshold,
            ccyb_bps=ccyb,
            peak_ccyb=float(ccyb.max()),
            spectral_radius=net.spectral_radius,
            pct_supercritical=None,
            causality_results=causality,
            bsdt_channels=channels,
        )

        if verbose:
            print(f"\n{'='*50}")
            print(f"MFLS Pipeline Complete")
            print(f"  AUROC:           {auroc:.4f}" if auroc else "  AUROC:           N/A")
            if auroc_ci:
                print(f"  95% CI:          [{auroc_ci[0]:.4f}, {auroc_ci[1]:.4f}]")
            print(f"  GFC Lead:        {gfc_lead}Q" if gfc_lead else "  GFC Lead:        N/A")
            print(f"  Hit Rate:        {hr:.1%}" if hr is not None else "  Hit Rate:        N/A")
            print(f"  False Alarm:     {far:.1%}" if far is not None else "  False Alarm:     N/A")
            print(f"  Spectral Radius: {net.spectral_radius:.3f}")
            print(f"  Peak CCyB:       {ccyb.max():.0f} bps")
            print(f"{'='*50}")

        return result

    # ----- Products -----

    def bsdt_audit(
        self,
        panel: Optional[PanelData] = None,
        t: int = -1,
    ) -> BSDTAudit:
        """
        Per-institution blind-spot audit at time step t.

        Parameters
        ----------
        panel : PanelData (or last loaded)
        t : int — time index (-1 = latest)

        Returns
        -------
        BSDTAudit — per-institution scores + dominant channel
        """
        panel = panel or self._panel
        if panel is None:
            raise ValueError("No panel loaded.")
        if self._bsdt_full is None:
            raise ValueError("Call fit_and_score() first.")

        X = panel.X_std
        T_len = X.shape[0]
        if t < 0:
            t = T_len + t

        X_curr = X[t]
        X_prev = X[max(0, t - 1)]
        history = [X[s] for s in range(max(0, t - 20), t)]

        return self._bsdt_full.audit(X_curr, X_prev, history, panel.names)

    def ccyb(
        self,
        panel: Optional[PanelData] = None,
    ) -> np.ndarray:
        """
        CCyB recommendation in basis points.

        Returns
        -------
        ndarray (T,) — CCyB in bps at each quarter
        """
        panel = panel or self._panel
        if panel is None:
            raise ValueError("No panel loaded.")
        if self._bsdt_op is None:
            raise ValueError("Call fit_and_score() first.")

        X = panel.X_std
        signal = self._bsdt_op.score_series(X)
        leverage_std = np.std(X[:, :, 0], axis=1)
        gamma_star = np.array([
            self._bsdt_op.energy_score(X[t]) / (self._bsdt_op.energy_score(X[t]) + 1.0)
            for t in range(X.shape[0])
        ])
        return calibrate_ccyb(signal, gamma_star, leverage_std)

    def herding_score(
        self,
        panel: Optional[PanelData] = None,
        crisis_labels: Optional[np.ndarray] = None,
    ) -> HerdingResult:
        """
        Herding / convergent behaviour detection via temporal novelty.

        The Signed LR variant learns that pre-crisis periods show
        *decreased* temporal novelty (beta_delta_T < 0), the quantitative
        signature of convergent herding.

        Returns
        -------
        HerdingResult
        """
        panel = panel or self._panel
        if panel is None:
            raise ValueError("No panel loaded.")
        if self._channels is None:
            raise ValueError("Call fit_and_score() first.")

        channels = self._channels

        # Fit SignedLR to get channel weights
        if crisis_labels is None:
            crisis_labels = _build_crisis_labels(panel.dates)

        X_normal = panel.X_std[panel.normal_mask]
        bsdt_full = self._bsdt_full or BSDTOperators()
        if not bsdt_full._fitted:
            bsdt_full.fit(X_normal)

        slr = MFLSSignedLR()
        train_mask = panel.dates <= pd.Timestamp(self.normal_end)
        ch_train = channels.channels[train_mask]
        y_train = crisis_labels[train_mask]
        slr.fit(ch_train, y_train)

        # Herding = inverted temporal novelty (low novelty = high herding)
        delta_T = channels.delta_T
        max_dT = delta_T.max() if delta_T.max() > 0 else 1.0
        herding = 1.0 - (delta_T / max_dT)

        return HerdingResult(
            temporal_novelty=delta_T,
            herding_score=herding,
            dates=panel.dates,
            signed_lr_weights=slr.channel_weights,
            beta_delta_T=slr.channel_weights.get("delta_T"),
        )

    # ----- Internal helpers -----

    @staticmethod
    def _compute_auroc(signal: np.ndarray, labels: np.ndarray) -> Optional[float]:
        """Trapezoidal AUROC (no sklearn dependency)."""
        if labels.sum() == 0 or labels.sum() == len(labels):
            return None
        desc = np.argsort(-signal)
        sorted_labels = labels[desc]
        n_pos = labels.sum()
        n_neg = len(labels) - n_pos
        tp = 0
        fp = 0
        auroc = 0.0
        prev_tp = 0
        prev_fp = 0
        for i in range(len(sorted_labels)):
            if sorted_labels[i] == 1:
                tp += 1
            else:
                fp += 1
            if i == len(sorted_labels) - 1 or signal[desc[i]] != signal[desc[i + 1]]:
                auroc += (fp - prev_fp) * (tp + prev_tp) / 2.0
                prev_tp = tp
                prev_fp = fp
        return float(auroc / (n_pos * n_neg)) if n_pos * n_neg > 0 else None

    @staticmethod
    def _gfc_lead(
        signal: np.ndarray,
        dates: pd.DatetimeIndex,
        threshold: float,
        crisis_windows: list,
    ) -> Optional[int]:
        """Quarters of lead before GFC onset."""
        gfc_onset = None
        for name, onset, _ in crisis_windows:
            if "GFC" in name.upper() or "2007" in onset or "2008" in onset:
                gfc_onset = pd.Timestamp(onset)
                break
        if gfc_onset is None:
            return None

        alarm_dates = dates[signal > threshold]
        pre_gfc = alarm_dates[alarm_dates < gfc_onset]
        if len(pre_gfc) == 0:
            return 0
        first_alarm = pre_gfc[0]
        lead_q = (gfc_onset.year - first_alarm.year) * 4 + (gfc_onset.quarter - first_alarm.quarter)
        return max(0, int(lead_q))

    @staticmethod
    def _hr_far(
        signal: np.ndarray,
        labels: np.ndarray,
        threshold: float,
    ) -> Tuple[Optional[float], Optional[float]]:
        """Hit rate and false alarm rate."""
        alarm = signal > threshold
        crisis = labels == 1
        calm = labels == 0
        hr = float(alarm[crisis].mean()) if crisis.sum() > 0 else None
        far = float(alarm[calm].mean()) if calm.sum() > 0 else None
        return hr, far
