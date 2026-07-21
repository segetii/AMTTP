"""
colab_bsdt_gradient_stability.py
=================================
Domain IV — Neural Network Gradient Stability
BSDT Canonical Adaptive Friction  ×  16 Optimisers

I built this experiment end-to-end — the BSDT optimiser family, the
BlowUpNet architecture designed to induce pathological gradient behaviour,
the training harness, and the analysis pipeline — to investigate whether
BSDT's adaptive-friction mechanism stabilises gradient flow in deep networks
where standard optimisers collapse or diverge.

Single-file Google Colab script. Uses PyTorch + GPU automatically.

Architecture : BlowUpNet — 20-layer MLP, d=512, init_scale=2.0 (pathological)
Dataset      : 2-class spiral (2000 samples)
Optimisers   : 5 standard  +  8 BSDT family  +  2 Canonical reference
Epochs       : 300   lr=0.01   batch=256

GPU notes:
  - Weights stay as torch.Tensor on CUDA; all matrix ops are GPU-native.
  - spectral_radius_approx: power iteration runs on GPU via torch.linalg.
  - BSDT channels: grad norms and dot-products via torch.
  - No Python loops over individual weight elements; all ops are batched.

Usage in Colab:
  !pip install -q torch torchvision   # already present in Colab
  !python colab_bsdt_gradient_stability.py

Author: Odeyemi Olusegun Israel
"""

from __future__ import annotations
import os, sys, json, time, math
from collections import deque
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np
import torch
import torch.nn.functional as F

# ─── device ──────────────────────────────────────────────────────────────────
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print(f"[device] Using: {DEVICE}")
if DEVICE.type == "cuda":
    print(f"         {torch.cuda.get_device_name(0)}")


# ══════════════════════════════════════════════════════════════════════════════
#  DATA
# ══════════════════════════════════════════════════════════════════════════════

def make_spiral_data(n_samples: int = 2000, noise: float = 0.3,
                     seed: int = 42) -> Tuple[torch.Tensor, torch.Tensor]:
    rng = np.random.default_rng(seed)
    n   = n_samples // 2

    t0  = np.linspace(0, 3 * np.pi, n)
    r0  = t0 / (3 * np.pi)
    x0  = np.column_stack([r0 * np.cos(t0), r0 * np.sin(t0)])
    x0 += rng.normal(0, noise * 0.1, x0.shape)

    t1  = np.linspace(0, 3 * np.pi, n)
    r1  = t1 / (3 * np.pi)
    x1  = np.column_stack([r1 * np.cos(t1 + np.pi), r1 * np.sin(t1 + np.pi)])
    x1 += rng.normal(0, noise * 0.1, x1.shape)

    X = np.vstack([x0, x1]).astype(np.float32)
    y = np.hstack([np.zeros(n), np.ones(n)]).astype(np.float32)
    idx = rng.permutation(n_samples)

    X = torch.tensor(X[idx], dtype=torch.float64, device=DEVICE)
    y = torch.tensor(y[idx], dtype=torch.float64, device=DEVICE)
    return X, y


# ══════════════════════════════════════════════════════════════════════════════
#  BLOWUPNET — GPU tensor implementation (no torch.nn, manual weights)
# ══════════════════════════════════════════════════════════════════════════════

class BlowUpNet:
    """20-layer MLP stored as plain torch.Tensor lists on DEVICE.

    Architecture:  Input(2) → [hidden_dim]×(n_layers-1) → 1
    Activation:    ReLU (no BatchNorm — pathological by design)
    Init:          He-normal × init_scale  (init_scale=2.0 → explosion)
    """

    def __init__(self, n_layers: int = 20, hidden_dim: int = 512,
                 input_dim: int = 2, init_scale: float = 2.0):
        self.n_layers   = n_layers
        self.hidden_dim = hidden_dim
        self.input_dim  = input_dim
        self.init_scale = init_scale
        self.W: List[torch.Tensor] = []
        self.b: List[torch.Tensor] = []

    def init_weights(self, seed: int = 42):
        torch.manual_seed(seed)
        self.W, self.b = [], []
        dims = [self.input_dim] + [self.hidden_dim] * (self.n_layers - 1) + [1]
        for i in range(self.n_layers):
            fan_in  = dims[i]
            fan_out = dims[i + 1]
            std = self.init_scale * math.sqrt(2.0 / fan_in)
            self.W.append(torch.randn(fan_in, fan_out, device=DEVICE,
                                      dtype=torch.float64) * std)
            self.b.append(torch.zeros(fan_out, device=DEVICE,
                                      dtype=torch.float64))

    def forward(self, X: torch.Tensor) -> Tuple[torch.Tensor, List[torch.Tensor]]:
        acts = [X]
        h    = X
        for i in range(self.n_layers - 1):
            h = F.relu(h @ self.W[i] + self.b[i])
            acts.append(h)
        z_out = h @ self.W[-1] + self.b[-1]
        y_out = torch.sigmoid(z_out).squeeze(-1)
        acts.append(z_out)
        return y_out, acts

    def backward(self, X: torch.Tensor, y: torch.Tensor,
                 y_pred: torch.Tensor,
                 acts: List[torch.Tensor]) -> Tuple[List[torch.Tensor], List[torch.Tensor]]:
        N      = X.shape[0]
        dW_lst, db_lst = [], []

        # Output layer
        dz     = (y_pred - y).unsqueeze(-1)          # (N,1)
        h_prev = acts[-2]
        dW_lst.insert(0, h_prev.T @ dz / N)
        db_lst.insert(0, dz.mean(0))

        delta = dz
        for i in range(self.n_layers - 2, -1, -1):
            delta  = delta @ self.W[i + 1].T
            mask   = (acts[i + 1] > 0).float()       # ReLU gate
            delta  = delta * mask
            h_prev = acts[i]
            dW_lst.insert(0, h_prev.T @ delta / N)
            db_lst.insert(0, delta.mean(0))

        return dW_lst, db_lst

    def total_params(self) -> int:
        return sum(w.numel() + b.numel() for w, b in zip(self.W, self.b))


# ══════════════════════════════════════════════════════════════════════════════
#  GRADIENT DIAGNOSTICS
# ══════════════════════════════════════════════════════════════════════════════

def grad_norm_t(dW_list: List[torch.Tensor],
                db_list: List[torch.Tensor]) -> float:
    total = sum(dW.pow(2).sum() + db.pow(2).sum()
                for dW, db in zip(dW_list, db_list))
    return float(total.sqrt().item())


def per_layer_grad_norms_t(dW_list: List[torch.Tensor]) -> torch.Tensor:
    return torch.tensor([float(dW.norm().item()) for dW in dW_list],
                        device=DEVICE)


def binary_cross_entropy_t(y_pred: torch.Tensor,
                            y_true: torch.Tensor,
                            eps: float = 1e-7) -> float:
    yp  = y_pred.clamp(eps, 1 - eps)
    bce = -(y_true * yp.log() + (1 - y_true) * (1 - yp).log())
    return float(bce.mean().item())


def spectral_radius_approx(W_list: List[torch.Tensor],
                            n_iter: int = 10, seed: int = 0) -> float:
    """Geometric mean (depth-normalised) of layer spectral norms.

    The full product Π σ_max(W_l) is ~5.6^20 ≈ 10^15 for a 20-layer
    init — astronomically large, freezing γ_spec.  The geometric mean
    exp((1/L) Σ log σ_l) gives the *typical per-layer* spectral norm
    (~5.6 at init), keeping γ_spec = lr·λ_eff/α in a sensible range.

    Power iteration runs entirely on GPU.
    """
    torch.manual_seed(seed)
    log_sum, n_valid = 0.0, 0

    for W in W_list:
        if W.ndim < 2 or min(W.shape) < 1:
            continue
        v = torch.randn(W.shape[1], device=DEVICE, dtype=torch.float64)
        v = v / (v.norm() + 1e-12)
        for _ in range(n_iter):
            u = W @ v;      u_n = u.norm(); u = u / (u_n + 1e-12)
            v = W.T @ u;    v_n = v.norm(); v = v / (v_n + 1e-12)
        sigma    = float((W @ v).norm().item())
        log_sum += math.log(max(sigma, 1e-12))
        n_valid += 1

    return math.exp(log_sum / n_valid) if n_valid else 1.0


def trust_region_clip_(W_list: List[torch.Tensor],
                       dW_list: List[torch.Tensor],
                       lr: float,
                       rho: float = 0.5,
                       eps: float = 1e-12) -> float:
    """Per-layer trust-region clip on F_base (canonical Rem 9.5 shaping).

    Mutates dW_list IN-PLACE so that for every layer
        lr · ‖dW_l‖  ≤  ρ · ‖W_l‖.
    Each rogue layer is rescaled independently — healthy layers are
    untouched.  This is the F_base shaping authorised by Rem 9.5 of the
    canonical paper when ‖F_base‖ > Ψ⋆ admissibility threshold.

    Returns the largest clip factor applied (1.0 = no clipping).
    """
    max_clip = 1.0
    for W, dW in zip(W_list, dW_list):
        wn = float(W.norm().item())
        gn = float(dW.norm().item())
        if not (math.isfinite(gn) and math.isfinite(wn)):
            return float('inf')
        bound = rho * wn / max(lr, eps)
        if gn > bound:
            scale = bound / (gn + eps)
            dW.mul_(scale)
            if 1.0/scale > max_clip:
                max_clip = 1.0/scale
    return max_clip


def per_layer_eff_lr(W_list: List[torch.Tensor],
                     dW_list: List[torch.Tensor],
                     lr: float,
                     rho: float = 0.05,
                     eps: float = 1e-12) -> Tuple[List[float], float]:
    """Per-layer effective learning rate (LARS-style boundary).

    For each layer, bounds the step norm to be at most rho * ||W_l||.
    If lr * ||dW_l|| > rho * ||W_l||, the effective lr is scaled down.
    This acts exactly like the old trust_region_clip_ (which enabled
    deep MLPs to train properly by acting like local LARS/LAMB layer
    normalisation) but DOES NOT mutate gradients in-place, preserving
    the exact descent direction within each layer.
    """
    out: List[float] = []
    max_gamma = 0.0
    for W, dW in zip(W_list, dW_list):
        wn = float(W.norm().item())
        gn = float(dW.norm().item())
        if not (math.isfinite(gn) and math.isfinite(wn)) or wn < eps:
            out.append(0.0)
            max_gamma = float('inf')
            continue
            
        r = lr * gn / wn
        # rho is our maximum allowed ratio (e.g. 0.05 = 5% of weight norm)
        # If r > rho, we scale lr down so the update equals rho * wn
        if r <= rho:
            gamma_l = 0.0
            out.append(lr)
        else:
            gamma_l = (r / rho) - 1.0
            out.append(lr / (1.0 + gamma_l))
            
        if gamma_l > max_gamma:
            max_gamma = gamma_l
    return out, max_gamma


def gamma_magnitude_guardian(W_list: List[torch.Tensor],
                             dW_list: List[torch.Tensor],
                             lr: float,
                             threshold: float = 1.0,
                             eps: float = 1e-12) -> float:
    """Magnitude-based guardian friction.

    Deadband: 0 unless the worst-layer relative update lr*||dW_l||/||W_l||
    exceeds `threshold`. Above the threshold it grows UNBOUNDED so the
    effective lr can collapse to ~0 in a genuine emergency (e.g. ratio
    1e6 -> gamma 1e6 -> eff_lr ~ lr*1e-6).

        gamma_mag = max(0, max_l (lr * ||dW_l|| / ||W_l||) - threshold)

    Applied via eff_lr = lr / (1 + gamma_mag) so DIRECTION of dW is
    preserved exactly (no per-layer mutation that would corrupt the
    chain-rule signal across deep nets).

    threshold = 1.0 means: silent until update would shift the worst
    layer by >= 100 percent of its weight norm. Realistic blow-ups
    happen well above this; healthy training stays safely below.
    """
    worst = 0.0
    for W, dW in zip(W_list, dW_list):
        wn = float(W.norm().item())
        gn = float(dW.norm().item())
        if not (math.isfinite(gn) and math.isfinite(wn)):
            return float('inf')
        r = lr * gn / (wn + eps)
        if r > worst:
            worst = r
    excess = worst - threshold
    return max(0.0, excess)


def _guardian_gamma(stress: float, threshold: float, theta: float = 1.0) -> float:
    """Canonical-shaped friction with a deadband.

        gamma = max(0, (stress - threshold) / (stress - threshold + theta))

    When stress <= threshold  -> gamma = 0 (BSDT silent, no interference).
    When stress  > threshold  -> ramps smoothly to 1 as stress -> infinity,
                                  preserving the canonical form gamma in [0,1).

    This realises the design intent: BSDT does NOT participate in normal
    training; it only steps in when the system approaches collapse and
    saves the day in the nick of time.
    """
    excess = stress - threshold
    if excess <= 0.0:
        return 0.0
    return excess / (excess + theta)


def trust_region_clip_full_(W_list: List[torch.Tensor],
                            dW_list: List[torch.Tensor],
                            db_list: List[torch.Tensor],
                            lr: float,
                            rho: float = 0.5,
                            eps: float = 1e-12) -> float:
    """Per-layer trust-region clip on BOTH dW and db (canonical Rem 9.5).

    Mutates dW_list and db_list IN-PLACE so for every layer
        lr * ||dW_l|| <= rho * ||W_l||
        lr * ||db_l|| <= rho * ||W_l||
    Each rogue layer is rescaled independently. This is the F_base
    shaping authorised by the canonical paper when ||F_base|| > Psi*.
    Returns the largest clip factor applied (1.0 = no clipping).

    THIS replaces the old unbounded gamma_step friction. With the clip
    in place, the canonical gamma in [0,1) is sufficient.
    """
    max_clip = 1.0
    for W, dW, db in zip(W_list, dW_list, db_list):
        wn = float(W.norm().item())
        if not math.isfinite(wn):
            return float('inf')
        bound = rho * wn / max(lr, eps)
        gn = float(dW.norm().item())
        if math.isfinite(gn) and gn > bound and bound > 0:
            dW.mul_(bound / (gn + eps))
            if gn / bound > max_clip:
                max_clip = gn / bound
        bn = float(db.norm().item())
        if math.isfinite(bn) and bn > bound and bound > 0:
            db.mul_(bound / (bn + eps))
    return max_clip


def step_safety_friction(W_list: List[torch.Tensor],
                         dW_list: List[torch.Tensor],
                         lr: float,
                         rho: float = 0.05,
                         eps: float = 1e-12) -> float:
    """Trust-region (step-safety) friction γ_step.

    Derivation from the descent stability condition:

        ‖eff_lr · dW_l‖ ≤ ρ · ‖W_l‖    ∀ l
        eff_lr = lr / (1 + γ)
        ⇒  γ_step  =  max(0, (lr/ρ) · max_l ‖dW_l‖/‖W_l‖ − 1)

    This is the missing scale-aware term: γ_spec & γ_struct & MFLS are all
    O(1) regardless of ‖∇‖ magnitude (ratio-invariant); γ_step grows
    linearly with the actual gradient/weight ratio and is the only thing
    that prevents catastrophic updates when ‖∇‖ → ∞ at init.

    ρ = 0.05 means at most 5% relative weight change per step (safe).
    """
    worst = 0.0
    for W, dW in zip(W_list, dW_list):
        wn = float(W.norm().item())
        gn = float(dW.norm().item())
        if not math.isfinite(gn) or not math.isfinite(wn):
            return float('inf')
        r = gn / (wn + eps)
        if r > worst:
            worst = r
    val = (lr / rho) * worst - 1.0
    return max(0.0, val)


# ══════════════════════════════════════════════════════════════════════════════
#  BSDT CHANNELS IN GRADIENT SPACE
# ══════════════════════════════════════════════════════════════════════════════

class GradientBSDT:
    """Four-channel BSDT operator in gradient/weight space.

      δ_C  Camouflage   — large weight norm, small grad norm (hiding instability)
      δ_G  Feature Gap  — per-layer grad imbalance vs. reference distribution
      δ_A  Activity     — sudden grad magnitude change between epochs
      δ_T  Temporal     — gradient direction novelty (cosine drift)

    E_BS = Σ_k w_k · δ_k²
    """

    def __init__(self, theta: float = 1.0, ema_alpha: float = 0.1,
                 fisher_window: int = 10):
        self.theta            = theta
        self.ema_alpha        = ema_alpha
        self.prev_gnorms:  Optional[torch.Tensor] = None
        self.run_grad_dir: Optional[torch.Tensor] = None
        self.ref_gnorms:   Optional[torch.Tensor] = None
        # Fisher channel weights: empirical w_k proportional to E[delta_k^2]
        # over a calibration window of healthy training. Until then,
        # uniform 1/4 weighting (canonical default).
        self.weights = {"camouflage": 0.25, "feature_gap": 0.25,
                        "activity":   0.25, "temporal_novelty": 0.25}
        self.fisher_calibrated = False
        self.fisher_window     = fisher_window
        self._chan_history     = {"camouflage": [], "feature_gap": [],
                                  "activity":   [], "temporal_novelty": []}

    def fisher_calibrate(self) -> Dict[str, float]:
        """Compute Fisher-style channel weights from accumulated history.

            w_k  =  E[delta_k^2]  /  sum_j E[delta_j^2]

        This is the empirical Fisher information of the BSDT energy
        E_BS = sum_k w_k * delta_k^2 with respect to channel parameters,
        evaluated on a calibration window of healthy training. Channels
        that carry consistently larger signal get more weight; silent or
        noisy channels are down-weighted.
        """
        ms = {}
        for k, h in self._chan_history.items():
            if h:
                arr = np.asarray(h, dtype=np.float64)
                ms[k] = float((arr ** 2).mean()) + 1e-12
            else:
                ms[k] = 1e-12
        Z = sum(ms.values())
        self.weights = {k: v / Z for k, v in ms.items()}
        self.fisher_calibrated = True
        return dict(self.weights)

    def calibrate(self, gnorms: torch.Tensor):
        self.ref_gnorms   = gnorms.clone()
        self.prev_gnorms  = gnorms.clone()

    def compute_channels(self, W_list: List[torch.Tensor],
                         dW_list: List[torch.Tensor]) -> Dict[str, float]:
        gnorms = per_layer_grad_norms_t(dW_list)
        wnorms = torch.tensor([float(W.norm().item()) for W in W_list],
                              device=DEVICE)

        # δ_C: Camouflage
        ratios  = wnorms / (gnorms + 1e-10)
        delta_C = float((ratios.max() / (ratios.mean() + 1e-10)).item())

        # δ_G: Feature Gap
        if self.ref_gnorms is not None:
            gap     = (gnorms - self.ref_gnorms).abs()
            delta_G = float((gap.mean() / (self.ref_gnorms.mean() + 1e-10)).item())
        else:
            delta_G = 0.0

        # δ_A: Activity
        if self.prev_gnorms is not None:
            chg     = (gnorms - self.prev_gnorms).abs()
            delta_A = float((chg.mean() / (self.prev_gnorms.mean() + 1e-10)).item())
        else:
            delta_A = 0.0
        self.prev_gnorms = gnorms.clone()

        # δ_T: Temporal novelty
        flat  = torch.cat([dW.flatten() for dW in dW_list])
        fnorm = flat.norm() + 1e-12
        fdir  = flat / fnorm
        if self.run_grad_dir is not None:
            cos_sim = float(torch.dot(fdir, self.run_grad_dir).item())
            delta_T = max(0.0, 1.0 - cos_sim)
            rdir    = self.ema_alpha * fdir + (1 - self.ema_alpha) * self.run_grad_dir
            self.run_grad_dir = rdir / (rdir.norm() + 1e-12)
        else:
            delta_T           = 0.0
            self.run_grad_dir = fdir.clone()

        result = {"camouflage": delta_C, "feature_gap": delta_G,
                  "activity": delta_A, "temporal_novelty": delta_T}

        # Log channel values during pre-Fisher window (healthy training)
        if not self.fisher_calibrated:
            for k, v in result.items():
                if math.isfinite(v):
                    self._chan_history[k].append(v)
        return result

    def energy(self, ch: Dict[str, float]) -> float:
        return sum(self.weights[k] * ch[k] ** 2 for k in self.weights)

    def reset(self):
        self.prev_gnorms  = None
        self.run_grad_dir = None
        self.ref_gnorms   = None
        self.weights = {"camouflage": 0.25, "feature_gap": 0.25,
                        "activity":   0.25, "temporal_novelty": 0.25}
        self.fisher_calibrated = False
        self._chan_history = {"camouflage": [], "feature_gap": [],
                              "activity":   [], "temporal_novelty": []}


# ══════════════════════════════════════════════════════════════════════════════
#  OPTIMISERS  (all operate on torch.Tensor lists on DEVICE)
# ══════════════════════════════════════════════════════════════════════════════

class Optimiser:
    name: str = "base"
    def step(self, net, dW_list, db_list, epoch, lr) -> Dict: raise NotImplementedError
    def reset(self): pass


# ── Standard ─────────────────────────────────────────────────────────────────

class SGDOptimiser(Optimiser):
    name = "SGD"
    def step(self, net, dW_list, db_list, epoch, lr):
        for i in range(net.n_layers):
            net.W[i] -= lr * dW_list[i]
            net.b[i] -= lr * db_list[i]
        return {"friction": 1.0}


class SGDClipOptimiser(Optimiser):
    name = "SGD+Clip"
    def __init__(self, max_norm: float = 1.0): self.max_norm = max_norm
    def step(self, net, dW_list, db_list, epoch, lr):
        gnorm = grad_norm_t(dW_list, db_list)
        scale = min(1.0, self.max_norm / (gnorm + 1e-12))
        for i in range(net.n_layers):
            net.W[i] -= lr * scale * dW_list[i]
            net.b[i] -= lr * scale * db_list[i]
        return {"friction": 1.0 / (scale + 1e-12)}


class AdamOptimiser(Optimiser):
    name = "Adam"
    def __init__(self, beta1=0.9, beta2=0.999, eps=1e-8):
        self.beta1, self.beta2, self.eps = beta1, beta2, eps
        self.m_W = self.v_W = self.m_b = self.v_b = None; self.t = 0
    def reset(self):
        self.m_W = self.v_W = self.m_b = self.v_b = None; self.t = 0
    def step(self, net, dW_list, db_list, epoch, lr):
        if self.m_W is None:
            self.m_W = [torch.zeros_like(w) for w in dW_list]
            self.v_W = [torch.zeros_like(w) for w in dW_list]
            self.m_b = [torch.zeros_like(b) for b in db_list]
            self.v_b = [torch.zeros_like(b) for b in db_list]
        self.t += 1
        bc1 = 1 - self.beta1 ** self.t
        bc2 = 1 - self.beta2 ** self.t
        for i in range(net.n_layers):
            self.m_W[i] = self.beta1*self.m_W[i] + (1-self.beta1)*dW_list[i]
            self.v_W[i] = self.beta2*self.v_W[i] + (1-self.beta2)*dW_list[i]**2
            self.m_b[i] = self.beta1*self.m_b[i] + (1-self.beta1)*db_list[i]
            self.v_b[i] = self.beta2*self.v_b[i] + (1-self.beta2)*db_list[i]**2
            net.W[i] -= lr * (self.m_W[i]/bc1) / ((self.v_W[i]/bc2).sqrt() + self.eps)
            net.b[i] -= lr * (self.m_b[i]/bc1) / ((self.v_b[i]/bc2).sqrt() + self.eps)
        return {"friction": 1.0}


class AdamWOptimiser(AdamOptimiser):
    name = "AdamW"
    def __init__(self, beta1=0.9, beta2=0.999, eps=1e-8, wd=0.01):
        super().__init__(beta1, beta2, eps); self.wd = wd
    def step(self, net, dW_list, db_list, epoch, lr):
        r = super().step(net, dW_list, db_list, epoch, lr)
        for i in range(net.n_layers): net.W[i] *= (1 - lr * self.wd)
        return r


class RMSPropOptimiser(Optimiser):
    name = "RMSProp"
    def __init__(self, alpha=0.99, eps=1e-8): self.alpha, self.eps = alpha, eps; self.v_W=self.v_b=None
    def reset(self): self.v_W = self.v_b = None
    def step(self, net, dW_list, db_list, epoch, lr):
        if self.v_W is None:
            self.v_W = [torch.zeros_like(w) for w in dW_list]
            self.v_b = [torch.zeros_like(b) for b in db_list]
        for i in range(net.n_layers):
            self.v_W[i] = self.alpha*self.v_W[i] + (1-self.alpha)*dW_list[i]**2
            self.v_b[i] = self.alpha*self.v_b[i] + (1-self.alpha)*db_list[i]**2
            net.W[i] -= lr * dW_list[i] / (self.v_W[i].sqrt() + self.eps)
            net.b[i] -= lr * db_list[i] / (self.v_b[i].sqrt() + self.eps)
        return {"friction": 1.0}


# ── MFLS proper gradient ──────────────────────────────────────────────────────

def compute_ebs_grad_W(W_list: List[torch.Tensor],
                       dW_list: List[torch.Tensor],
                       channels: Dict[str, float],
                       weights: Optional[Dict[str, float]] = None
                       ) -> Tuple[List[torch.Tensor], float]:
    """Per-layer canonical state-space gradient ∇_{W_i} E_BS  AND  its norm.

    BSDT dictionary for the canonical g_X = 2 J^T G S:
        S    = (δ_C, δ_G, δ_A, δ_T) restricted to channels with ∂/∂W ≠ 0.
        G    = diag(w_k)  (channel weights from the BSDT energy template).
        E_BS = Σ_k w_k δ_k²,  hence  ∇_W E_BS = Σ_k w_k·2δ_k·∇_W δ_k.

    Only δ_C has ∂/∂W ≠ 0 (others are gradient-space).
    Argmax-aware ratio derivative.

    Returns (grad_W_list, ‖grad_W‖_F).
    """
    CH_W    = {"camouflage": (weights or {}).get("camouflage", 0.25)}
    delta_C = channels["camouflage"]
    grad_W  = [torch.zeros_like(W) for W in W_list]

    if delta_C < 1e-12:
        return grad_W, 0.0

    g_norms = torch.stack([dW.norm().clamp(min=1e-12) for dW in dW_list])
    w_norms = torch.stack([W.norm().clamp(min=1e-12)  for W  in W_list ])
    ratios  = w_norms / g_norms
    r_mean  = ratios.mean().item() + 1e-10
    i_star  = int(ratios.argmax().item())
    r_istar = ratios[i_star].item()
    L       = len(W_list)

    sq_sum = torch.tensor(0.0, dtype=torch.float64, device=W_list[0].device)
    for i, W in enumerate(W_list):
        wi = w_norms[i].item(); gi = g_norms[i].item()
        if i == i_star:
            d_dw = (1.0/gi) * (1.0/r_mean - r_istar/(L * r_mean**2))
        else:
            d_dw = (r_istar / r_mean**2) * (1.0/(L * gi))
        coeff     = CH_W["camouflage"] * 2.0 * delta_C * d_dw / wi
        grad_W[i] = coeff * W
        sq_sum    = sq_sum + grad_W[i].pow(2).sum()

    return grad_W, float(sq_sum.sqrt().item())


def compute_mfls_state(W_list: List[torch.Tensor],
                       dW_list: List[torch.Tensor],
                       channels: Dict[str, float],
                       bsdt: "GradientBSDT") -> float:
    """MFLS_W = ‖∇_W E_BS‖_F — state-space MFLS (norm of canonical g_X)."""
    _, n = compute_ebs_grad_W(W_list, dW_list, channels, weights=bsdt.weights)
    return n


def compute_mfls_grad(channels: Dict[str, float],
                      dW_list: List[torch.Tensor],
                      W_list:  List[torch.Tensor],
                      bsdt: "GradientBSDT") -> float:
    """MFLS_{dW} = ‖grad_{dW} E_BS‖_F — gradient-space MFLS.

    E_BS = Σ_k w_k δ_k²  (quadratic link ψ_k → ψ'_k = 2δ_k)

    grad_{dW} E_BS = Σ_k  w_k · 2δ_k · grad_{dW} δ_k

    Chain rule per channel (all via ∂δ/∂g_i  where g_i = ‖dW_i‖_F):
      δ_A, δ_G  →  grad_{dW_i} δ = [sgn(g_i-prev_i) / (L·ḡ·g_i)] · dW_i
      δ_T       →  grad_{flat} δ_T = −(r − cos·f̂) / ‖f‖   (full vector)
      δ_C       →  grad_{dW_i} δ_C via argmax-aware ratio derivative
    """
    CH_W = dict(bsdt.weights)  # Fisher-calibrated (or uniform if not yet)

    L = len(dW_list)
    g_norms = torch.stack([dW.norm() for dW in dW_list])   # (L,)
    w_norms = torch.stack([W.norm()  for W  in W_list  ])  # (L,)

    grad_ebs = [torch.zeros_like(dW) for dW in dW_list]

    # δ_A ──────────────────────────────────────────────────────────────────────
    delta_A = channels["activity"]
    if bsdt.prev_gnorms is not None and delta_A > 0:
        prev     = bsdt.prev_gnorms.to(g_norms.device)
        mean_p   = prev.mean().clamp(min=1e-10)
        for i, dW in enumerate(dW_list):
            gi    = g_norms[i].clamp(min=1e-12)
            s     = torch.sign(gi - prev[i])
            coeff = CH_W["activity"] * 2.0 * delta_A * s / (L * mean_p * gi)
            grad_ebs[i] = grad_ebs[i] + coeff * dW

    # δ_G ──────────────────────────────────────────────────────────────────────
    delta_G = channels["feature_gap"]
    if bsdt.ref_gnorms is not None and delta_G > 0:
        ref    = bsdt.ref_gnorms.to(g_norms.device)
        mean_r = ref.mean().clamp(min=1e-10)
        for i, dW in enumerate(dW_list):
            gi    = g_norms[i].clamp(min=1e-12)
            s     = torch.sign(gi - ref[i])
            coeff = CH_W["feature_gap"] * 2.0 * delta_G * s / (L * mean_r * gi)
            grad_ebs[i] = grad_ebs[i] + coeff * dW

    # δ_T ──────────────────────────────────────────────────────────────────────
    # grad_{flat} δ_T = −(r − cos·f̂) / ‖f‖   where r = running_dir (unit vec)
    delta_T = channels["temporal_novelty"]
    flat    = torch.cat([dW.flatten() for dW in dW_list])
    f_norm  = flat.norm().clamp(min=1e-12)
    if bsdt.run_grad_dir is not None and delta_T > 0:
        r        = bsdt.run_grad_dir
        cos_sim  = 1.0 - delta_T                       # δ_T = max(0,1−cos)
        flat_dir = flat / f_norm
        g_T_flat = -(r - cos_sim * flat_dir) / f_norm  # (n_params,)
        g_T_flat = (CH_W["temporal_novelty"] * 2.0 * delta_T) * g_T_flat
        offset   = 0
        for i, dW in enumerate(dW_list):
            n = dW.numel()
            grad_ebs[i] = grad_ebs[i] + g_T_flat[offset:offset+n].reshape(dW.shape)
            offset += n

    # δ_C ──────────────────────────────────────────────────────────────────────
    # r_i = w_i/g_i,  δ_C = r_max/r_mean
    # ∂δ_C/∂g_{i*} = −(w_{i*}/g_{i*}²)·(1/r̄ − r_{i*}/(L·r̄²))
    # ∂δ_C/∂g_i    =  (r_{i*}/r̄²)·(w_i/(L·g_i²))   for i≠i*
    # grad_{dW_i} δ_C = (∂δ_C/∂g_i)/g_i · dW_i
    delta_C = channels["camouflage"]
    ratios  = w_norms / (g_norms + 1e-10)
    r_mean  = ratios.mean().item() + 1e-10
    i_star  = int(ratios.argmax().item())
    r_istar = ratios[i_star].item()
    for i, dW in enumerate(dW_list):
        gi = g_norms[i].item()
        wi = w_norms[i].item()
        if gi < 1e-12:
            continue
        if i == i_star:
            d_dg = -(wi / gi**2) * (1.0/r_mean - r_istar/(L * r_mean**2))
        else:
            d_dg = (r_istar / r_mean**2) * (wi / (L * gi**2))
        coeff = CH_W["camouflage"] * 2.0 * delta_C * d_dg / gi
        grad_ebs[i] = grad_ebs[i] + coeff * dW

    return float(sum(g.pow(2).sum() for g in grad_ebs).sqrt().item())


def compute_mfls(channels: Dict[str, float],
                dW_list: List[torch.Tensor],
                W_list:  List[torch.Tensor],
                bsdt: "GradientBSDT") -> float:
    """Two-space MFLS = max(MFLS_W, MFLS_{dW}).

    MFLS_W    (state-space, SLOW)  : structural weight drift, δ_C dominant.
    MFLS_{dW} (gradient-space, FAST): explosion onset, all channels.
    Taking the max gives the tightest early-warning across both timescales.
    """
    mfls_s = compute_mfls_state(W_list, dW_list, channels, bsdt)
    mfls_g = compute_mfls_grad(channels, dW_list, W_list, bsdt)
    return max(mfls_s, mfls_g)


# ── BSDT base ─────────────────────────────────────────────────────────────────

class BSDTOptimiser(Optimiser):
    """Core BSDT optimiser — three-level canonical adaptive friction.

    γ*(t) = max(γ_spec, γ_struct, γ_step)

    Level 1 (spectral, ratio-invariant):
        γ_spec = lr · λ_eff(W) / α
        λ_eff  = exp((1/L) Σ log σ_max(W_l))   (geometric mean)

    Level 2 (structural BSDT energy, ratio-invariant):
        γ_struct = E_BS / (E_BS + θ) ∈ [0,1)
        E_BS = Σ w_k δ_k² over the four BSDT channels

    Level 3 (trust-region step-safety, scale-aware — the missing piece):
        γ_step = max(0, (lr/ρ)·max_l ‖dW_l‖/‖W_l‖ − 1)
        Derived from ‖eff_lr·dW_l‖ ≤ ρ‖W_l‖.
        Without this, all three friction families above are O(1) regardless
        of ‖∇‖, so a 10⁶ gradient at init produces a 10⁶·lr/2 weight update
        → instant blow-up.  γ_step grows linearly with the actual
        gradient/weight ratio and is the only term that responds to
        absolute scale.
    """
    name = "BSDT"

    def __init__(self, alpha: float = 0.1, theta: float = 1.0):
        self.bsdt         = GradientBSDT(theta=theta)
        self.alpha        = alpha
        self.calibrated   = False
        self._cache_epoch = -1
        self._cache_lam   = 1.0

    def reset(self):
        self.bsdt.reset()
        self.calibrated   = False
        self._cache_epoch = -1
        self._cache_lam   = 1.0

    def _compute_friction(self, net, dW_list, db_list, epoch, lr):
        # NO per-layer gradient mutation -- that destroys descent direction
        # in deep nets (it breaks the inter-layer coherence backprop needs).
        # Friction is applied via global eff_lr scaling only.

        # Cache λ_eff per epoch (power iteration is O(L·d·n_iter))
        if epoch != self._cache_epoch:
            self._cache_lam   = spectral_radius_approx(net.W, seed=epoch)
            self._cache_epoch = epoch
        lam  = self._cache_lam

        ch   = self.bsdt.compute_channels(net.W, dW_list)
        E_bs = self.bsdt.energy(ch)

        # Guardian friction (deadbands -- silent during healthy training):
        #   gamma_spec   fires when predicted step lr*lam/alpha > 1
        #   gamma_struct fires when E_BS exceeds calibrated safe band theta
        # Magnitude guardian is applied PER-LAYER in step() via
        # per_layer_eff_lr -- it preserves descent direction within each
        # layer while still freezing genuinely rogue layers.
        s            = lr * lam / self.alpha
        gamma_spec   = _guardian_gamma(s, threshold=1.0, theta=1.0)
        gamma_struct = _guardian_gamma(E_bs, threshold=self.bsdt.theta,
                                       theta=self.bsdt.theta)
        gamma_star   = max(gamma_spec, gamma_struct)

        # Reference-norm calibration on the first stable batch
        if not self.calibrated and epoch == 0:
            gn = per_layer_grad_norms_t(dW_list)
            if torch.isfinite(gn).all():
                self.bsdt.calibrate(gn)
                self.calibrated = True

        # Fisher channel-weight calibration after a healthy window
        if (not self.bsdt.fisher_calibrated and
                len(self.bsdt._chan_history["camouflage"]) >= self.bsdt.fisher_window):
            self.bsdt.fisher_calibrate()

        return gamma_star, E_bs, ch, lam

    def step(self, net, dW_list, db_list, epoch, lr):
        gamma_star, E_bs, ch, lam = self._compute_friction(net, dW_list, db_list, epoch, lr)
        # Per-layer eff_lr (healthy layers learn at full lr; only rogue
        # layers throttle). Then global structural/spectral friction is
        # applied uniformly on top.
        ll_lr, _ = per_layer_eff_lr(net.W, dW_list, lr, rho=getattr(self, 'rho', 0.05))
        for i in range(net.n_layers):
            eff_lr = ll_lr[i] / (1.0 + gamma_star)
            net.W[i] -= eff_lr * dW_list[i]
            net.b[i] -= eff_lr * db_list[i]
        return {"friction": 1.0 + gamma_star, "gamma_star": gamma_star,
                "E_bs": E_bs, "channels": ch, "lambda_max": lam}


class MFLSOptimiser(BSDTOptimiser):
    """MFLS optimiser — friction driven by windowed-peak two-space MFLS.

    MFLS_W    = ‖∇_W E_BS‖_F    (state-space, SLOW  — structural weight drift)
    MFLS_{dW} = ‖∇_{dW} E_BS‖_F (gradient-space, FAST — explosion onset)
    MFLS(t)   = max_{t' ∈ [t-L, t]} max(MFLS_W, MFLS_{dW})  (windowed peak, §XII.1)

    Windowed max is mandatory: the admissibility and safety conditions (§XII)
    require the *peak* intensity over the lead window, not the instantaneous
    value.  Without it, a single quiet step falsely relaxes friction while
    the root cause (structural weight drift) persists.

    γ_mfls = _guardian_gamma(MFLS)   then  γ* = max(γ_spec, γ_mfls)
    """
    name = "MFLS"

    def __init__(self, alpha: float = 0.1, theta: float = 1.0,
                 mfls_window: int = 20):
        super().__init__(alpha=alpha, theta=theta)
        self.mfls_window = mfls_window
        self._mfls_buf: deque = deque(maxlen=mfls_window)

    def reset(self):
        super().reset()
        self._mfls_buf.clear()

    def step(self, net, dW_list, db_list, epoch, lr):
        gamma_star, E_bs, channels, lam_max = \
            self._compute_friction(net, dW_list, db_list, epoch, lr)

        # Instantaneous two-space MFLS: max(‖∇_W E_BS‖_F, ‖∇_{dW} E_BS‖_F)
        mfls_inst = compute_mfls(channels, dW_list, net.W, self.bsdt)
        self._mfls_buf.append(mfls_inst)

        # Windowed peak over lead window L = mfls_window  (Definition §XII.1)
        mfls       = max(self._mfls_buf)
        gamma_mfls = _guardian_gamma(mfls, threshold=self.bsdt.theta,
                                     theta=self.bsdt.theta)
        g          = max(gamma_star, gamma_mfls)

        eff_lr_list, _ = per_layer_eff_lr(net.W, dW_list, lr, rho=getattr(self, 'rho', 0.05))
        for i in range(net.n_layers):
            eff_lr = eff_lr_list[i] / (1.0 + g)
            net.W[i] -= eff_lr * dW_list[i]
            net.b[i] -= eff_lr * db_list[i]
        return {"friction": 1.0 + g, "gamma_star": g, "E_bs": E_bs,
                "channels": channels, "lambda_max": lam_max,
                "mfls": mfls, "mfls_inst": mfls_inst}


class MolecularOptimiser(BSDTOptimiser):
    """Molecular (Lennard-Jones) optimiser — WCA hard-wall per-layer stiffening.

    Each layer i is treated as a "particle" with gradient norm ‖dW_i‖ as its
    "instantaneous velocity".  The WCA (Weeks-Chandler-Andersen) purely repulsive
    potential adds friction when gradient norm exceeds the calibrated reference r_i:

        r_i     = ‖dW_i‖ / r_ref_i                    (dimensionless excess)
        V_WCA_i = max(0, r_i^12 − 2r_i^6 + 1)         (canonical WCA, §IV LJ)

    V_WCA properties:
        V_WCA(1)    = 0   — equilibrium: no extra friction at reference intensity
        dV/dr|_{r=1} = 0  — smooth onset (no discontinuous kick)
        V_WCA → ∞  as r → ∞  with r^12 wall (hard repulsion, gradient explosion blocked)

    r_ref_i is calibrated from the first stable epoch (‖dW_i‖ during normal training);
    falls back to 1.0 before calibration is complete.

    Total per-layer friction:
        g_i = γ_star + ε_LJ · V_WCA_i
        eff_lr_i = eff_lr_i / (1 + g_i)
    """
    name = "Molecular"

    def __init__(self, alpha: float = 0.1, theta: float = 1.0,
                 eps_lj: float = 0.01):
        super().__init__(alpha=alpha, theta=theta)
        # ε_LJ normalises WCA so V_WCA(r=1.5) ≈ 1 extra friction unit:
        #   eps_lj = 1 / V_WCA(1.5) = 1 / (1.5^12 − 2·1.5^6 + 1) ≈ 0.00927
        # Using 0.01 (clean round number, same order) for conference readability.
        self.eps_lj = eps_lj

    def step(self, net, dW_list, db_list, epoch, lr):
        gamma_star, E_bs, ch, lam = self._compute_friction(net, dW_list, db_list, epoch, lr)
        gn = per_layer_grad_norms_t(dW_list)
        eff_lr_list, _ = per_layer_eff_lr(net.W, dW_list, lr, rho=getattr(self, 'rho', 0.05))

        lj_max = 0.0
        for i in range(net.n_layers):
            # Calibrated reference norm (from epoch-0 healthy training); fallback 1.0
            r_ref = float(self.bsdt.ref_gnorms[i].item()) \
                    if self.bsdt.ref_gnorms is not None else 1.0
            r_ref = max(r_ref, 1e-12)

            r  = float(gn[i].item()) / r_ref
            # Canonical WCA (zero at equilibrium r=1; r^12 hard wall for r>1)
            lj = max(0.0, r ** 12 - 2.0 * r ** 6 + 1.0)
            lj_max = max(lj_max, lj)

            g_i    = gamma_star + self.eps_lj * lj
            eff_lr = eff_lr_list[i] / (1.0 + g_i)
            net.W[i] -= eff_lr * dW_list[i]
            net.b[i] -= eff_lr * db_list[i]

        # Report peak applied friction (worst layer)
        g_peak = gamma_star + self.eps_lj * lj_max
        return {"friction": 1.0 + g_peak, "gamma_star": gamma_star,
                "E_bs": E_bs, "channels": ch, "lambda_max": lam,
                "lj_max": lj_max}


class GravityOptimiser(BSDTOptimiser):
    """Gravity optimiser — friction driven by spectral radius (gravitational pull toward collapse).

    Canonical gravity friction (§XIV):
        γ_grav = λ_max / (λ_max + θ)   (guardian form on spectral radius, no dead-band)

    Gravitational pull is always present (threshold = 0): unlike the BSDT guardian which
    has a quiet dead-band below threshold=1, gravity continuously damps in proportion to
    how close λ_max is to instability.  This mirrors Newtonian gravity: always-on, grows
    with "mass" (spectral radius).

    Final friction:
        γ* = max(γ_grav, γ_canonical)   (never under-damp below canonical BSDT level)
    """
    name = "Gravity"

    def step(self, net, dW_list, db_list, epoch, lr):
        gamma_star, E_bs, ch, lam = self._compute_friction(net, dW_list, db_list, epoch, lr)

        # Guardian form on spectral radius: γ_grav = λ/(λ+θ) ∈ [0,1)  (threshold=0, no dead-band)
        gamma_grav = _guardian_gamma(lam, threshold=0.0, theta=self.bsdt.theta)

        # Never under-damp: take the tighter of gravitational and canonical friction
        g = max(gamma_grav, gamma_star)

        eff_lr_list, _ = per_layer_eff_lr(net.W, dW_list, lr, rho=getattr(self, 'rho', 0.05))
        for i in range(net.n_layers):
            eff_lr = eff_lr_list[i] / (1.0 + g)
            net.W[i] -= eff_lr * dW_list[i]
            net.b[i] -= eff_lr * db_list[i]
        return {"friction": 1.0 + g, "gamma_star": g, "E_bs": E_bs,
                "channels": ch, "lambda_max": lam, "gamma_grav": gamma_grav}


class HybridOptimiser(BSDTOptimiser):
    """Hybrid optimiser — energy-weighted blend of gravity and canonical BSDT friction,
    with per-layer Lennard-Jones stiffening in high-gradient layers.

    Blend: b = E_BS / (E_BS + θ) ∈ [0,1)
        b → 0  (normal):  g_base ≈ γ_grav   (gravity dominates — spectral pull)
        b → 1  (crisis):  g_base ≈ γ_star   (BSDT dominates — Lyapunov energy)

    Admissibility floor: g_base ≥ γ_star always  (never under-damp below canonical).
    """
    name = "Hybrid"

    def step(self, net, dW_list, db_list, epoch, lr):
        gamma_star, E_bs, ch, lam = self._compute_friction(net, dW_list, db_list, epoch, lr)

        # Guardian form on spectral radius (same θ as structural friction)
        gamma_grav = _guardian_gamma(lam, threshold=0.0, theta=self.bsdt.theta)

        # Energy-weighted blend, θ-consistent
        blend  = E_bs / (E_bs + self.bsdt.theta)
        g_blend = blend * gamma_star + (1.0 - blend) * gamma_grav

        # Admissibility floor: never under-damp below the canonical BSDT level
        g_base = max(gamma_star, g_blend)

        gn = per_layer_grad_norms_t(dW_list)
        eff_lr_list, _ = per_layer_eff_lr(net.W, dW_list, lr, rho=getattr(self, 'rho', 0.05))
        for i in range(net.n_layers):
            # WCA per-layer stiffening (same form as MolecularOptimiser, calibrated r_ref)
            r_ref = float(self.bsdt.ref_gnorms[i].item()) \
                    if self.bsdt.ref_gnorms is not None else 1.0
            r     = float(gn[i].item()) / max(r_ref, 1e-12)
            lj    = max(0.0, r ** 12 - 2.0 * r ** 6 + 1.0)
            g_l   = g_base + blend * 0.01 * lj
            eff_lr = eff_lr_list[i] / (1.0 + g_l)
            net.W[i] -= eff_lr * dW_list[i]
            net.b[i] -= eff_lr * db_list[i]
        return {"friction": 1.0 + g_base, "gamma_star": g_base,
                "E_bs": E_bs, "channels": ch, "lambda_max": lam,
                "gamma_grav": gamma_grav, "blend": blend}


class QuadSurfOptimiser(BSDTOptimiser):
    name = "QuadSurf"
    def step(self, net, dW_list, db_list, epoch, lr):
        gamma_star, E_bs, ch, lam = self._compute_friction(net, dW_list, db_list, epoch, lr)
        E_qs = (0.50*ch["camouflage"]**2 + 0.20*ch["feature_gap"]**2 +
                0.20*ch["activity"]**2  + 0.10*ch["temporal_novelty"]**2)
        g = max(gamma_star, _guardian_gamma(E_qs, threshold=self.bsdt.theta,
                                            theta=self.bsdt.theta))
        eff_lr_list, _ = per_layer_eff_lr(net.W, dW_list, lr, rho=getattr(self, 'rho', 0.05))
        for i in range(net.n_layers):
            eff_lr = eff_lr_list[i] / (1.0 + g)
            net.W[i] -= eff_lr*dW_list[i]; net.b[i] -= eff_lr*db_list[i]
        return {"friction": 1.0+g, "gamma_star": g, "E_bs": E_qs, "channels": ch, "lambda_max": lam}


class QuadExpoOptimiser(BSDTOptimiser):
    name = "QuadExpo"
    def step(self, net, dW_list, db_list, epoch, lr):
        gamma_star, E_bs, ch, lam = self._compute_friction(net, dW_list, db_list, epoch, lr)
        E_qe = sum(0.25*(math.exp(min(v, 10.0))-1.0) for v in ch.values())
        g = max(gamma_star, _guardian_gamma(E_qe, threshold=self.bsdt.theta,
                                            theta=self.bsdt.theta))
        eff_lr_list, _ = per_layer_eff_lr(net.W, dW_list, lr, rho=getattr(self, 'rho', 0.05))
        for i in range(net.n_layers):
            eff_lr = eff_lr_list[i] / (1.0 + g)
            net.W[i] -= eff_lr*dW_list[i]; net.b[i] -= eff_lr*db_list[i]
        return {"friction": 1.0+g, "gamma_star": g, "E_bs": E_qe, "channels": ch, "lambda_max": lam}


class SignedLROptimiser(BSDTOptimiser):
    name = "SignedLR"
    def __init__(self, alpha=0.1, theta=1.0):
        super().__init__(alpha, theta); self.prev_sign: Optional[torch.Tensor] = None
    def reset(self):
        super().reset(); self.prev_sign = None
    def step(self, net, dW_list, db_list, epoch, lr):
        gamma_star, E_bs, ch, lam = self._compute_friction(net, dW_list, db_list, epoch, lr)
        flat = torch.cat([dW.flatten() for dW in dW_list])
        csign = flat.sign()
        if self.prev_sign is not None:
            scf = float((csign != self.prev_sign).float().mean().item())
            g_sign = scf * 2.0
        else:
            g_sign = 0.0
        self.prev_sign = csign
        g = max(gamma_star, g_sign)
        eff_lr_list, _ = per_layer_eff_lr(net.W, dW_list, lr, rho=getattr(self, 'rho', 0.05))
        for i in range(net.n_layers):
            eff_lr = eff_lr_list[i] / (1.0 + g)
            net.W[i] -= eff_lr*dW_list[i]; net.b[i] -= eff_lr*db_list[i]
        return {"friction": 1.0+g, "gamma_star": g, "E_bs": E_bs, "channels": ch, "lambda_max": lam}


# ── Canonical reference optimisers ────────────────────────────────────────────

class CanonicalSpectralOptimiser(Optimiser):
    """Level-1 only: γ*(t) = lr · λ_eff(W,t) / α (pure spectral control).

    Derivation:
      Stability condition:  lr_eff = lr/(1+γ) ≤ α/λ_eff
      ⟹  γ_spec = lr·λ_eff / α
    When λ_eff ↑ (near blow-up) → γ ↑ → step shrinks → network stabilised.
    """
    name = "CanSpectral"

    def __init__(self, alpha: float = 0.1):
        self.alpha = alpha
        self._cache_epoch = -1
        self._cache_lam   = 1.0

    def reset(self):
        self._cache_epoch = -1
        self._cache_lam   = 1.0

    def step(self, net, dW_list, db_list, epoch, lr):
        # No per-layer mutation -- friction via global eff_lr scaling only.
        if epoch != self._cache_epoch:
            self._cache_lam   = spectral_radius_approx(net.W, seed=epoch)
            self._cache_epoch = epoch
        lam        = self._cache_lam
        s          = lr * lam / self.alpha
        gamma_spec = _guardian_gamma(s, threshold=1.0, theta=1.0)
        gamma_star = gamma_spec
        eff_lr_list, gamma_mag = per_layer_eff_lr(net.W, dW_list, lr, rho=getattr(self, 'rho', 0.05))
        for i in range(net.n_layers):
            eff_lr = eff_lr_list[i] / (1.0 + gamma_star)
            net.W[i] -= eff_lr * dW_list[i]
            net.b[i] -= eff_lr * db_list[i]
        return {"friction": 1.0 + gamma_star + gamma_mag,
                "gamma_star": gamma_star,
                "lambda_max": lam, "E_bs": 0.0, "channels": None}


class CanonicalFullOptimiser(Optimiser):
    """Two-level canonical adaptive friction (spectral + structural).

    γ_spec   = lr · λ_eff(W) / α              (Level 1 — spectral)
    γ_struct = E_BS / (E_BS + θ)              (Level 2 — BSDT energy)
    γ*       = max(γ_spec, γ_struct)           (canonical formula)

    Both levels are derived from first principles here — fully auditable
    without tracing into any helper class.
    """
    name = "CanFull"

    def __init__(self, alpha: float = 0.1, theta: float = 1.0):
        self.alpha        = alpha
        self.bsdt         = GradientBSDT(theta=theta)
        self.calibrated   = False
        self._cache_epoch = -1
        self._cache_lam   = 1.0

    def reset(self):
        self.bsdt.reset()
        self.calibrated   = False
        self._cache_epoch = -1
        self._cache_lam   = 1.0

    def step(self, net, dW_list, db_list, epoch, lr):
        # No per-layer mutation -- friction via global eff_lr scaling only.

        # Level 1 — spectral (cached per epoch)
        if epoch != self._cache_epoch:
            self._cache_lam   = spectral_radius_approx(net.W, seed=epoch)
            self._cache_epoch = epoch
        lam        = self._cache_lam
        s          = lr * lam / self.alpha
        gamma_spec = _guardian_gamma(s, threshold=1.0, theta=1.0)

        # Level 2 — structural BSDT energy
        ch           = self.bsdt.compute_channels(net.W, dW_list)
        E_bs         = self.bsdt.energy(ch)
        gamma_struct = _guardian_gamma(E_bs, threshold=self.bsdt.theta,
                                       theta=self.bsdt.theta)

        if not self.calibrated and epoch == 0:
            gn = per_layer_grad_norms_t(dW_list)
            if torch.isfinite(gn).all():
                self.bsdt.calibrate(gn)
                self.calibrated = True
        if (not self.bsdt.fisher_calibrated and
                len(self.bsdt._chan_history["camouflage"]) >= self.bsdt.fisher_window):
            self.bsdt.fisher_calibrate()

        # Canonical formula -- bounded structural + spectral, plus
        # per-layer magnitude guardian (no global throttle).
        gamma_star = max(gamma_spec, gamma_struct)
        eff_lr_list, gamma_mag = per_layer_eff_lr(net.W, dW_list, lr, rho=getattr(self, 'rho', 0.05))
        for i in range(net.n_layers):
            eff_lr = eff_lr_list[i] / (1.0 + gamma_star)
            net.W[i] -= eff_lr * dW_list[i]
            net.b[i] -= eff_lr * db_list[i]
        return {"friction": 1.0 + gamma_star + gamma_mag,
                "gamma_star": gamma_star,
                "gamma_spec": gamma_spec, "gamma_struct": gamma_struct,
                "lambda_max": lam, "E_bs": E_bs, "channels": ch}


class CanonicalEngineOptimiser(Optimiser):
    """The TRUE canonical engine — projection ODE, not scalar damping.

    Implements the locked canonical ODE of the Canonical Dynamical Geometry
    System v4 (§4):

        Ẋ = F_base − g_X − γ · ⟨F, g_X⟩/‖g_X‖² · g_X
        F = F_base − g_X
        γ = E / (E + θ)              (canonical friction, §5.5)

    BSDT dictionary (§2.2 of the canonical paper):
        X        ← weights W                          (state)
        F_base   ← −dW                                (loss-descent direction)
        S        ← (δ_C, δ_G, δ_A, δ_T)               (BSDT feature map)
        G        ← diag(w_k)                          (channel weights)
        E        ← Σ_k w_k δ_k² = E_BS                (BSDT energy)
        g_X      ← ∇_W E_BS                           (state-space gradient)

    All scalar friction is replaced by Euclidean projection (Rule 2):
    only the component of F aligned with g_X is damped, and only by γ ∈ [0,1).
    The projection is computed once across all layers (single inner product
    on the concatenated state, as required by the locked formula).

    Outer feedback shaping (Rem 9.5, canonical-legitimate): pathological
    init pushes ‖∇‖ outside the admissibility window M < Ψ⋆. We wrap
    F_base with a trust-region step-safety scale so the integrator stays
    inside the operating window; the canonical projection itself is
    untouched.
    """
    name = "Canonical"

    def __init__(self, theta: float = 1.0, rho: float = 0.05):
        self.bsdt = GradientBSDT(theta=theta)
        self.rho  = rho
        self.calibrated = False

    def reset(self):
        self.bsdt.reset()
        self.calibrated = False

    def step(self, net, dW_list, db_list, epoch, lr):
        # Per-layer eff_lr (Rem 9.5 F_base shaping). Preserves descent
        # direction within each layer; healthy layers learn at full lr
        # while only rogue layers are throttled.
        eff_lr_list, gamma_mag = per_layer_eff_lr(
            net.W, dW_list, lr, rho=getattr(self, 'rho', 0.05))

        # BSDT channels & energy
        ch    = self.bsdt.compute_channels(net.W, dW_list)
        E_bs  = self.bsdt.energy(ch)
        gamma = _guardian_gamma(E_bs, threshold=self.bsdt.theta,
                                theta=self.bsdt.theta)  # guardian canonical gamma

        if not self.calibrated and epoch == 0:
            gn = per_layer_grad_norms_t(dW_list)
            if torch.isfinite(gn).all():
                self.bsdt.calibrate(gn)
                self.calibrated = True
        if (not self.bsdt.fisher_calibrated and
                len(self.bsdt._chan_history["camouflage"]) >= self.bsdt.fisher_window):
            self.bsdt.fisher_calibrate()

        # State-space gradient g_X = grad_W E_BS (BSDT dictionary)
        gX_list, gX_norm = compute_ebs_grad_W(net.W, dW_list, ch,
                                              weights=self.bsdt.weights)

        # F_base = -dW;  F = F_base - g_X (modified force)
        F_list = [(-dW) - gX for dW, gX in zip(dW_list, gX_list)]

        # Euclidean projection coefficient alpha = <F,g_X> / ||g_X||^2
        if gX_norm > 1e-12:
            num = sum((F * gX).sum() for F, gX in zip(F_list, gX_list))
            den = sum(gX.pow(2).sum() for gX in gX_list).clamp(min=1e-24)
            alpha_proj = float((num / den).item())
        else:
            alpha_proj = 0.0

        # Locked canonical ODE:  dX/dt = F - gamma * alpha * g_X
        # Integrated with per-layer magnitude-guarded eff_lr.
        for i in range(net.n_layers):
            X_dot = F_list[i] - (gamma * alpha_proj) * gX_list[i]
            net.W[i] += eff_lr_list[i] * X_dot
            net.b[i] -= eff_lr_list[i] * db_list[i]

        return {"friction": 1.0 / (1.0 - gamma + 1e-12),
                "gamma_star": gamma, "clip_factor": 1.0 + gamma_mag,
                "alpha_proj": alpha_proj, "gX_norm": gX_norm,
                "E_bs": E_bs, "channels": ch, "lambda_max": 0.0}


# ── Registry ──────────────────────────────────────────────────────────────────

def get_all_optimisers() -> Dict[str, Optimiser]:
    return {
        # Standard (5)
        "SGD":         SGDOptimiser(),
        "SGD+Clip":    SGDClipOptimiser(max_norm=1.0),
        "Adam":        AdamOptimiser(),
        "AdamW":       AdamWOptimiser(),
        "RMSProp":     RMSPropOptimiser(),
        # BSDT family (8)
        "BSDT":        BSDTOptimiser(),
        "MFLS":        MFLSOptimiser(),
        "Molecular":   MolecularOptimiser(),
        "Gravity":     GravityOptimiser(),
        "Hybrid":      HybridOptimiser(),
        "QuadSurf":    QuadSurfOptimiser(),
        "QuadExpo":    QuadExpoOptimiser(),
        "SignedLR":    SignedLROptimiser(),
        # Canonical reference (3)
        "CanSpectral": CanonicalSpectralOptimiser(alpha=0.1),
        "CanFull":     CanonicalFullOptimiser(alpha=0.1, theta=1.0),
        "Canonical":   CanonicalEngineOptimiser(theta=1.0, rho=0.05),
    }


# ══════════════════════════════════════════════════════════════════════════════
#  EPOCH LOG
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class EpochLog:
    epoch:      int
    train_loss: float
    test_loss:  float
    train_acc:  float
    test_acc:   float
    grad_norm:  float
    friction:   float
    blew_up:    bool = False
    channels:   Optional[Dict[str, float]] = None
    lambda_max: float = 0.0
    E_bs:       float = 0.0


# ══════════════════════════════════════════════════════════════════════════════
#  TRAINING LOOP
# ══════════════════════════════════════════════════════════════════════════════

def train(net: BlowUpNet, opt: Optimiser,
          X_train: torch.Tensor, y_train: torch.Tensor,
          X_test:  torch.Tensor, y_test:  torch.Tensor,
          lr: float = 0.01, n_epochs: int = 300,
          batch_size: int = 256, seed: int = 42) -> List[EpochLog]:

    torch.manual_seed(seed)
    rng   = torch.Generator(device=DEVICE).manual_seed(seed)
    logs  = []
    blown = False
    gnorm = 0.0
    step_info: Dict = {"friction": 1.0}

    for epoch in range(n_epochs):
        if blown:
            logs.append(EpochLog(epoch=epoch, train_loss=float('inf'),
                                 test_loss=float('inf'), train_acc=0.5,
                                 test_acc=0.5, grad_norm=float('inf'),
                                 friction=0.0, blew_up=True))
            continue

        perm  = torch.randperm(len(X_train), generator=rng, device=DEVICE)
        epoch_loss, epoch_correct, n_batches = 0.0, 0, 0

        for start in range(0, len(X_train), batch_size):
            idx  = perm[start:start + batch_size]
            Xb, yb = X_train[idx], y_train[idx]

            y_pred, acts = net.forward(Xb)
            loss  = binary_cross_entropy_t(y_pred, yb)
            dW_list, db_list = net.backward(Xb, yb, y_pred, acts)

            gnorm = grad_norm_t(dW_list, db_list)
            # Only bail on genuine NaN/Inf — clipping optimisers can
            # handle huge-but-finite gradients via per-layer trust region.
            if not math.isfinite(gnorm):
                blown = True
                break

            step_info  = opt.step(net, dW_list, db_list, epoch, lr)
            epoch_loss += loss * len(idx)
            epoch_correct += int(((y_pred > 0.5).float() == yb).sum().item())
            n_batches  += 1

        if blown:
            logs.append(EpochLog(epoch=epoch, train_loss=float('inf'),
                                 test_loss=float('inf'), train_acc=0.5,
                                 test_acc=0.5, grad_norm=gnorm,
                                 friction=0.0, blew_up=True))
            continue

        # Eval
        with torch.no_grad():
            y_pt, _ = net.forward(X_test)
        test_loss = binary_cross_entropy_t(y_pt, y_test)
        test_acc  = float(((y_pt > 0.5).float() == y_test).float().mean().item())

        logs.append(EpochLog(
            epoch=epoch,
            train_loss=epoch_loss / len(X_train),
            test_loss=test_loss,
            train_acc=epoch_correct / len(X_train),
            test_acc=test_acc,
            grad_norm=gnorm,
            friction=step_info.get("friction", 1.0),
            channels=step_info.get("channels"),
            lambda_max=step_info.get("lambda_max", 0.0),
            E_bs=step_info.get("E_bs", 0.0),
        ))

    return logs


# ══════════════════════════════════════════════════════════════════════════════
#  THREE-PHASE CLASSIFIER
# ══════════════════════════════════════════════════════════════════════════════

def classify_phases(fh: List[float]) -> Dict:
    if len(fh) < 20:
        return {}
    f = np.array(fh)
    n = len(f)
    peak = np.max(f[:min(30, n)])
    p1 = 0
    for i in range(min(30, n)):
        if i > 5 and f[i] < 0.5 * peak:
            p1 = i; break
    if p1 == 0: p1 = min(20, n)
    fin = f[-1]
    p3 = n
    for i in range(n-1, max(n//2, 0), -1):
        if abs(f[i] - fin) > 0.2 * max(fin, 1.0):
            p3 = i+1; break
    if p3 >= n: p3 = max(n*2//3, p1+1)
    return {
        "phase1_end": p1, "phase3_start": p3,
        "peak_friction_phase1": float(np.max(f[:p1+1])) if p1 else float(f[0]),
        "mean_friction_phase2": float(np.mean(f[p1:p3])) if p3 > p1 else 0.0,
        "mean_friction_phase3": float(np.mean(f[p3:])) if p3 < n else float(fin),
    }


# ══════════════════════════════════════════════════════════════════════════════
#  EXPERIMENT
# ══════════════════════════════════════════════════════════════════════════════

def run_experiment(n_epochs: int = 300, lr: float = 0.01,
                   seed: int = 42, verbose: bool = True) -> Dict:

    X, y = make_spiral_data(n_samples=2000, noise=0.3, seed=seed)
    split = int(0.8 * len(X))
    X_train, X_test = X[:split], X[split:]
    y_train, y_test = y[:split], y[split:]

    if verbose:
        print(f"Data : {len(X_train)} train / {len(X_test)} test / 2D spiral")
        print(f"Net  : 20 layers, d=512, init_scale=2.0 (pathological)")
        print(f"Train: lr={lr}, epochs={n_epochs}, batch=256, device={DEVICE}")
        print()

    optimisers = get_all_optimisers()
    results    = {}

    for opt_name, opt in optimisers.items():
        net = BlowUpNet()
        net.init_weights(seed=seed)
        opt.reset()

        if verbose:
            print(f"  [{opt_name:12s}] ({net.total_params():,d} params) ",
                  end="", flush=True)

        t0   = time.time()
        logs = train(net, opt, X_train, y_train, X_test, y_test,
                     lr=lr, n_epochs=n_epochs, seed=seed)
        elapsed = time.time() - t0

        blew_up     = any(l.blew_up for l in logs)
        bu_epoch    = next((i for i, l in enumerate(logs) if l.blew_up), -1) if blew_up else -1
        valid       = [l for l in logs if not l.blew_up]
        final_loss  = valid[-1].train_loss if valid else float('inf')
        final_acc   = valid[-1].test_acc   if valid else 0.5
        best_acc    = max((l.test_acc for l in valid), default=0.5)
        peak_fr     = max((l.friction for l in valid), default=0.0)
        final_fr    = valid[-1].friction if valid else 0.0
        peak_gn     = max((l.grad_norm for l in valid if math.isfinite(l.grad_norm)), default=float('inf'))
        fh          = [l.friction for l in valid]
        phases      = classify_phases(fh) if len(fh) > 20 else {}

        results[opt_name] = dict(
            name=opt_name, blew_up=blew_up, blow_up_epoch=bu_epoch,
            epochs_survived=len(valid), final_train_loss=final_loss,
            final_test_acc=final_acc, best_test_acc=best_acc,
            peak_grad_norm=peak_gn, peak_friction=peak_fr,
            final_friction=final_fr, elapsed_s=elapsed,
            phases=phases, logs=logs,
        )

        if verbose:
            if blew_up:
                print(f"BLOW-UP at epoch {bu_epoch:3d}  "
                      f"gnorm={peak_gn:.1e}  ({elapsed:.1f}s)")
            else:
                print(f"loss={final_loss:.4f}  acc={best_acc:.3f}  "
                      f"γ_peak={peak_fr:.1f}×  γ_final={final_fr:.2f}×  ({elapsed:.1f}s)")

    return results


# ══════════════════════════════════════════════════════════════════════════════
#  SUMMARY TABLE
# ══════════════════════════════════════════════════════════════════════════════

def print_summary(results: Dict) -> str:
    W = 110
    lines = ["", "="*W,
             "  NEURAL NETWORK GRADIENT STABILITY — BSDT CANONICAL FRICTION RESULTS",
             "="*W,
             f"  {'Optimiser':<14} {'Type':<9} {'Survived':>8} {'BU Ep':>7} "
             f"{'Loss':>10} {'Acc':>8} {'γ_peak':>10} {'γ_final':>10} {'Peak∥∇∥':>11}",
             "-"*W]

    STD = ["SGD","SGD+Clip","Adam","AdamW","RMSProp"]
    BST = ["BSDT","MFLS","Molecular","Gravity","Hybrid","QuadSurf","QuadExpo","SignedLR"]
    CAN = ["CanSpectral","CanFull","Canonical"]

    def row(name, r):
        t    = "std" if name in STD else ("canon" if name in CAN else "BSDT")
        surv = f"{r['epochs_survived']}/300"
        bu   = str(r['blow_up_epoch']) if r['blew_up'] else "—"
        loss = f"{r['final_train_loss']:.4f}" if math.isfinite(r['final_train_loss']) else "∞"
        acc  = f"{r['best_test_acc']:.3f}"
        pk   = f"{r['peak_friction']:.2f}×"
        fn   = f"{r['final_friction']:.2f}×"
        gn   = f"{r['peak_grad_norm']:.2e}" if math.isfinite(r['peak_grad_norm']) else "∞"
        return f"  {name:<14} {t:<9} {surv:>8} {bu:>7} {loss:>10} {acc:>8} {pk:>10} {fn:>10} {gn:>11}"

    for g, names in [("Standard", STD), ("BSDT", BST), ("Canonical", CAN)]:
        for n in names:
            if n in results: lines.append(row(n, results[n]))
        lines.append("-"*W)

    std_blew  = sum(1 for n in STD if n in results and results[n]["blew_up"])
    bst_ok    = sum(1 for n in BST if n in results and not results[n]["blew_up"])
    can_ok    = sum(1 for n in CAN if n in results and not results[n]["blew_up"])
    lines += ["",
              f"  Standard optimisers that BLEW UP          : {std_blew}/{len(STD)}",
              f"  BSDT variants surviving 300 epochs        : {bst_ok}/{len(BST)}",
              f"  Canonical variants surviving 300 epochs   : {can_ok}/{len(CAN)}",
              ""]

    table = "\n".join(lines)
    print(table)
    return table


# ══════════════════════════════════════════════════════════════════════════════
#  FIGURES
# ══════════════════════════════════════════════════════════════════════════════

def generate_figures(results: Dict, figdir: str = "/content/figures"):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("  [WARN] matplotlib not available — skipping figures")
        return

    os.makedirs(figdir, exist_ok=True)

    COLORS = {
        "SGD": "#e74c3c", "SGD+Clip": "#f39c12", "Adam": "#3498db",
        "AdamW": "#2980b9", "RMSProp": "#e67e22",
        "BSDT": "#2ecc71", "MFLS": "#27ae60", "Molecular": "#1abc9c",
        "Gravity": "#16a085", "Hybrid": "#2ecc71", "QuadSurf": "#1dd1a1",
        "QuadExpo": "#10ac84", "SignedLR": "#0a8f6c",
        "CanSpectral": "#9b59b6", "CanFull": "#6c3483", "Canonical": "#4a235a",
    }
    STD = {"SGD","SGD+Clip","Adam","AdamW","RMSProp"}
    CAN = {"CanSpectral","CanFull","Canonical"}

    # ── Fig 1: Loss + Gradient norm ──────────────────────────────────────────
    fig, axes = plt.subplots(1, 2, figsize=(16, 6))
    for name, r in results.items():
        logs   = r["logs"]
        valid  = [(l.epoch, l.train_loss) for l in logs
                  if not l.blew_up and math.isfinite(l.train_loss) and l.train_loss < 100]
        if valid:
            ep, ls = zip(*valid)
            lw = 2.5 if name in CAN else 1.5
            ls_style = "--" if name in STD and name != "SGD+Clip" else "-"
            axes[0].plot(ep, ls, label=name, color=COLORS.get(name, "#999"),
                         linewidth=lw, linestyle=ls_style, alpha=0.85)

    axes[0].set_yscale("log"); axes[0].set_xlim(0, 300)
    axes[0].set_xlabel("Epoch"); axes[0].set_ylabel("Train Loss (log)")
    axes[0].set_title("(a) Training Loss: Standard vs BSDT vs Canonical",
                      fontweight="bold")
    axes[0].legend(fontsize=7, ncol=2); axes[0].grid(alpha=0.15)

    for name, r in results.items():
        logs  = r["logs"]
        valid = [(l.epoch, l.grad_norm) for l in logs
                 if math.isfinite(l.grad_norm) and l.grad_norm < 1e12]
        if valid:
            ep, gn = zip(*valid)
            lw = 2.5 if name in CAN else 1.5
            axes[1].plot(ep, gn, label=name, color=COLORS.get(name, "#999"),
                         linewidth=lw, alpha=0.85)
    axes[1].set_yscale("log")
    axes[1].axhline(1e10, color="red", ls=":", lw=1, alpha=0.5, label="Blow-up")
    axes[1].set_xlabel("Epoch"); axes[1].set_ylabel("Gradient Norm (log)")
    axes[1].set_title("(b) Gradient Norm: Explosion vs Stabilisation",
                      fontweight="bold")
    axes[1].legend(fontsize=7, ncol=2); axes[1].grid(alpha=0.15)
    plt.tight_layout()
    for ext in ["png","pdf"]:
        plt.savefig(f"{figdir}/nn_loss_gradient.{ext}", dpi=200, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {figdir}/nn_loss_gradient.[png|pdf]")

    # ── Fig 2: Friction dynamics (BSDT + Canonical) ──────────────────────────
    fig, axes = plt.subplots(1, 2, figsize=(16, 6))
    BSDT_CAN = ["BSDT","MFLS","Molecular","Gravity","Hybrid",
                 "QuadSurf","QuadExpo","SignedLR","CanSpectral","CanFull","Canonical"]
    for name in BSDT_CAN:
        r = results.get(name)
        if r and not r["blew_up"]:
            fh = [l.friction for l in r["logs"] if not l.blew_up]
            lw = 2.5 if name in CAN else 1.8
            axes[0].plot(range(len(fh)), fh, label=name,
                         color=COLORS.get(name, "#999"), lw=lw, alpha=0.9)

    axes[0].set_xlabel("Epoch")
    axes[0].set_ylabel("Friction Multiplier  1 + γ*")
    axes[0].set_title("(a) Canonical Adaptive Friction Self-Regulation",
                      fontweight="bold")
    axes[0].legend(fontsize=8); axes[0].grid(alpha=0.15)
    for x0, x1, c, lbl in [(0,20,"red","Phase 1\nBraking"),
                            (20,200,"orange","Phase 2\nDescent"),
                            (200,300,"green","Phase 3\nEquil.")]:
        axes[0].axvspan(x0, x1, alpha=0.04, color=c)

    for name, r in results.items():
        if r["blew_up"]: continue
        ep  = [l.epoch    for l in r["logs"] if not l.blew_up]
        acc = [l.test_acc for l in r["logs"] if not l.blew_up]
        lw  = 2.5 if name in CAN else 1.5
        ls  = "--" if name in STD else "-"
        axes[1].plot(ep, acc, label=name, color=COLORS.get(name, "#999"),
                     lw=lw, ls=ls, alpha=0.85)
    axes[1].set_xlabel("Epoch"); axes[1].set_ylabel("Test Accuracy")
    axes[1].set_title("(b) Test Accuracy Comparison", fontweight="bold")
    axes[1].legend(fontsize=7, ncol=2); axes[1].grid(alpha=0.15)
    axes[1].set_ylim(0.45, 1.0)
    plt.tight_layout()
    for ext in ["png","pdf"]:
        plt.savefig(f"{figdir}/nn_friction_accuracy.{ext}", dpi=200, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {figdir}/nn_friction_accuracy.[png|pdf]")

    # ── Fig 3: BSDT channel decomposition at peak stress ────────────────────
    fig, ax = plt.subplots(figsize=(13, 6))
    ch_keys  = ["camouflage","feature_gap","activity","temporal_novelty"]
    ch_lbls  = [r"$\delta_C$ Camouflage", r"$\delta_G$ Feature Gap",
                r"$\delta_A$ Activity",   r"$\delta_T$ Temporal"]
    bar_data = {}
    for name in BSDT_CAN:
        r = results.get(name)
        if r and not r["blew_up"]:
            valid = [l for l in r["logs"] if l.channels is not None]
            if valid:
                bar_data[name] = max(valid, key=lambda l: l.friction).channels
    if bar_data:
        x = np.arange(len(bar_data))
        w = 0.18
        for j, (k, lbl) in enumerate(zip(ch_keys, ch_lbls)):
            ax.bar(x + j*w, [bar_data[n].get(k, 0) for n in bar_data],
                   w, label=lbl, alpha=0.8)
        ax.set_xticks(x + 1.5*w)
        ax.set_xticklabels(list(bar_data.keys()), rotation=30, ha="right")
        ax.set_ylabel("Channel value at peak friction"); ax.legend(fontsize=9)
        ax.set_title("BSDT Channel Decomposition at Peak Stress", fontweight="bold")
        ax.grid(alpha=0.15, axis="y")
    plt.tight_layout()
    for ext in ["png","pdf"]:
        plt.savefig(f"{figdir}/nn_channels.{ext}", dpi=200, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {figdir}/nn_channels.[png|pdf]")

    # ── Fig 4: Summary bars ──────────────────────────────────────────────────
    names_all = list(results.keys())
    fig, axes = plt.subplots(1, 3, figsize=(16, 5))
    cols  = [COLORS.get(n, "#999") for n in names_all]
    surv  = [results[n]["epochs_survived"] for n in names_all]
    loss  = [min(results[n]["final_train_loss"], 10.0) for n in names_all]
    acc   = [results[n]["best_test_acc"] for n in names_all]

    for ax, vals, title, xlabel in [
        (axes[0], surv, "Epochs Survived",     "Epochs (out of 300)"),
        (axes[1], loss, "Final Training Loss",  "Loss (capped at 10)"),
        (axes[2], acc,  "Best Test Accuracy",   "Accuracy"),
    ]:
        ax.barh(range(len(names_all)), vals, color=cols, alpha=0.85)
        ax.set_yticks(range(len(names_all)))
        ax.set_yticklabels(names_all, fontsize=8)
        ax.set_xlabel(xlabel); ax.set_title(title, fontweight="bold")
        ax.grid(alpha=0.15, axis="x")
    axes[0].axvline(300, color="green", ls=":", lw=1, alpha=0.5)
    axes[1].set_xscale("log")
    axes[2].axvline(0.5, color="red", ls=":", lw=1, alpha=0.5)
    plt.tight_layout()
    for ext in ["png","pdf"]:
        plt.savefig(f"{figdir}/nn_summary.{ext}", dpi=200, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {figdir}/nn_summary.[png|pdf]")


# ══════════════════════════════════════════════════════════════════════════════
#  SAVE JSON
# ══════════════════════════════════════════════════════════════════════════════

def save_results(results: Dict, outdir: str = "/content/results"):
    os.makedirs(outdir, exist_ok=True)
    jr = {}
    for name, r in results.items():
        jr[name] = {k: (v if not isinstance(v, list) else None)
                    for k, v in r.items() if k != "logs"}
        jr[name]["final_train_loss"] = (
            r["final_train_loss"] if math.isfinite(r["final_train_loss"]) else "Inf")
        jr[name]["peak_grad_norm"] = (
            r["peak_grad_norm"] if math.isfinite(r["peak_grad_norm"]) else "Inf")
    path = f"{outdir}/nn_results.json"
    with open(path, "w") as f:
        json.dump(jr, f, indent=2, default=str)
    print(f"  JSON → {path}")


# ══════════════════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 70)
    print("  Domain IV: Neural Network Gradient Stability")
    print("  BlowUpNet (20-layer MLP) × 16 Optimisers  — GPU Colab edition")
    print("=" * 70)
    print()

    results = run_experiment(n_epochs=300, lr=0.01, seed=42, verbose=True)

    print()
    print_summary(results)

    FIGDIR = "/content/figures" if os.path.exists("/content") else "figures"
    RESDIR = "/content/results" if os.path.exists("/content") else "results"

    print("\nGenerating figures ...")
    generate_figures(results, figdir=FIGDIR)

    print("\nSaving results ...")
    save_results(results, outdir=RESDIR)

    print("\nDone.")
    if os.path.exists("/content"):
        print(f"\nDownload from Colab:")
        print(f"  from google.colab import files")
        print(f"  import os, glob")
        print(f"  for f in glob.glob('{FIGDIR}/*') + ['{RESDIR}/nn_results.json']:")
        print(f"      files.download(f)")
