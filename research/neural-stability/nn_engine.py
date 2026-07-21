"""
nn_engine.py — Domain IV: Neural Network Gradient Stability Engine
====================================================================
Implements a deliberately pathological "BlowUpNet" (20-layer MLP, no
BatchNorm, high-variance init, d=512) and a suite of optimisers:

  Standard (5):  SGD, SGD+GradClip, Adam, AdamW, RMSProp
  BSDT     (8):  CoreBSDT, MFLS, Molecular, Gravity, Hybrid,
                  QuadSurf, QuadExpo, SignedLR

The BSDT optimisers use two-level adaptive friction:
  Level 1 — Spectral:   γ_spec(t) = α / λ_max(∇²L)
  Level 2 — Structural: γ_struct(t) = E_BS / (E_BS + θ)

This is the neural-network analogue of the adaptive friction law
γ*(X) = α / λ_max(D²Φ) from the grand unification paper.

The critical manifold C* in this domain is the boundary in
weight space where gradient norms transition from bounded to
exponentially growing — i.e. the onset of gradient explosion.

Author: Odeyemi Olusegun Israel
"""

from __future__ import annotations
import numpy as np
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


# ═════════════════════════════════════════════════════════════
#  DATA GENERATION
# ═════════════════════════════════════════════════════════════

def make_spiral_data(n_samples: int = 2000, noise: float = 0.3,
                     seed: int = 42) -> Tuple[np.ndarray, np.ndarray]:
    """Generate a 2-class spiral dataset.  Separable only by a
    highly nonlinear boundary — forces the network to develop
    deep representations.
    """
    rng = np.random.default_rng(seed)
    n = n_samples // 2

    theta0 = np.linspace(0, 3 * np.pi, n)
    r0 = theta0 / (3 * np.pi)
    x0 = np.column_stack([r0 * np.cos(theta0), r0 * np.sin(theta0)])
    x0 += rng.normal(0, noise * 0.1, x0.shape)

    theta1 = np.linspace(0, 3 * np.pi, n)
    r1 = theta1 / (3 * np.pi)
    x1 = np.column_stack([r1 * np.cos(theta1 + np.pi), r1 * np.sin(theta1 + np.pi)])
    x1 += rng.normal(0, noise * 0.1, x1.shape)

    X = np.vstack([x0, x1]).astype(np.float64)
    y = np.hstack([np.zeros(n), np.ones(n)]).astype(np.float64)

    # Shuffle
    idx = rng.permutation(n_samples)
    return X[idx], y[idx]


# ═════════════════════════════════════════════════════════════
#  BLOWUPNET: 20-LAYER PATHOLOGICAL MLP
# ═════════════════════════════════════════════════════════════

def relu(x: np.ndarray) -> np.ndarray:
    return np.maximum(0, x)

def relu_grad(x: np.ndarray) -> np.ndarray:
    return (x > 0).astype(np.float64)

def sigmoid(x: np.ndarray) -> np.ndarray:
    x_clip = np.clip(x, -500, 500)
    return 1.0 / (1.0 + np.exp(-x_clip))

def binary_cross_entropy(y_pred: np.ndarray, y_true: np.ndarray,
                         eps: float = 1e-7) -> float:
    yp = np.clip(y_pred, eps, 1 - eps)
    return -float(np.mean(y_true * np.log(yp) + (1 - y_true) * np.log(1 - yp)))


@dataclass
class BlowUpNet:
    """20-layer MLP with deliberately pathological initialisation.

    Architecture:  Input(2) → [512]×18 → [512] → 1
    Activation:    ReLU (no BatchNorm)
    Init:          He-normal with 2× variance inflation (causes explosion)
    """
    n_layers: int = 20
    hidden_dim: int = 512
    input_dim: int = 2
    init_scale: float = 2.0   # >1 causes gradient explosion

    # Weights and biases
    W: List[np.ndarray] = field(default_factory=list)
    b: List[np.ndarray] = field(default_factory=list)

    def init_weights(self, seed: int = 42):
        """Kaiming/He init with inflated scale → guaranteed explosion."""
        rng = np.random.default_rng(seed)
        self.W = []
        self.b = []

        dims = [self.input_dim] + [self.hidden_dim] * (self.n_layers - 1) + [1]

        for i in range(self.n_layers):
            fan_in = dims[i]
            fan_out = dims[i + 1]
            # He init: std = sqrt(2/fan_in), inflated by init_scale
            std = self.init_scale * np.sqrt(2.0 / fan_in)
            self.W.append(rng.normal(0, std, (fan_in, fan_out)))
            self.b.append(np.zeros(fan_out))

    def forward(self, X: np.ndarray) -> Tuple[np.ndarray, List[np.ndarray]]:
        """Forward pass. Returns (output, list of pre-activations for backprop)."""
        activations = [X]  # a[0] = input
        h = X

        for i in range(self.n_layers - 1):
            z = h @ self.W[i] + self.b[i]
            h = relu(z)
            activations.append(h)

        # Output layer (sigmoid for binary classification)
        z_out = h @ self.W[-1] + self.b[-1]
        y_pred = sigmoid(z_out).flatten()
        activations.append(z_out)

        return y_pred, activations

    def backward(self, X: np.ndarray, y: np.ndarray,
                 y_pred: np.ndarray, activations: List[np.ndarray]
                 ) -> Tuple[List[np.ndarray], List[np.ndarray]]:
        """Backpropagation. Returns (dW_list, db_list)."""
        N = X.shape[0]
        dW_list = []
        db_list = []

        # Output layer gradient
        y_pred_clip = np.clip(y_pred, 1e-7, 1 - 1e-7)
        dz = (y_pred_clip - y).reshape(-1, 1)  # (N, 1)

        # Last layer
        h_prev = activations[-2]   # activation before output
        dW = h_prev.T @ dz / N
        db = np.mean(dz, axis=0)
        dW_list.insert(0, dW)
        db_list.insert(0, db)

        # Propagate through hidden layers (back to front)
        delta = dz
        for i in range(self.n_layers - 2, -1, -1):
            delta = delta @ self.W[i + 1].T
            # ReLU gradient
            z_pre = activations[i + 1]  # this is post-relu, we need pre
            # Since activations[i+1] is post-ReLU, mask = (activations[i+1] > 0)
            delta = delta * (activations[i + 1] > 0).astype(np.float64)

            h_prev = activations[i]
            dW = h_prev.T @ delta / N
            db = np.mean(delta, axis=0)
            dW_list.insert(0, dW)
            db_list.insert(0, db)

        return dW_list, db_list

    def get_flat_params(self) -> np.ndarray:
        """Flatten all parameters into a single vector."""
        parts = []
        for i in range(self.n_layers):
            parts.append(self.W[i].flatten())
            parts.append(self.b[i].flatten())
        return np.concatenate(parts)

    def set_flat_params(self, p: np.ndarray):
        """Set parameters from a flat vector."""
        offset = 0
        dims = [self.input_dim] + [self.hidden_dim] * (self.n_layers - 1) + [1]
        for i in range(self.n_layers):
            n_w = dims[i] * dims[i + 1]
            n_b = dims[i + 1]
            self.W[i] = p[offset:offset + n_w].reshape(dims[i], dims[i + 1])
            offset += n_w
            self.b[i] = p[offset:offset + n_b].copy()
            offset += n_b

    def total_params(self) -> int:
        return sum(w.size + b.size for w, b in zip(self.W, self.b))

    def copy_params(self) -> Tuple[List[np.ndarray], List[np.ndarray]]:
        """Deep copy of current parameters."""
        return [w.copy() for w in self.W], [b.copy() for b in self.b]

    def set_params(self, W: List[np.ndarray], b: List[np.ndarray]):
        self.W = [w.copy() for w in W]
        self.b = [bb.copy() for bb in b]


# ═════════════════════════════════════════════════════════════
#  GRADIENT DIAGNOSTICS
# ═════════════════════════════════════════════════════════════

def grad_norm(dW_list: List[np.ndarray], db_list: List[np.ndarray]) -> float:
    """Total Frobenius norm across all gradient matrices."""
    total = 0.0
    for dW, db in zip(dW_list, db_list):
        total += np.sum(dW ** 2) + np.sum(db ** 2)
    return float(np.sqrt(total))


def per_layer_grad_norms(dW_list: List[np.ndarray]) -> np.ndarray:
    """Per-layer gradient norms (for diagnosing where explosion starts)."""
    return np.array([float(np.linalg.norm(dW)) for dW in dW_list])


def spectral_radius_approx(W_list: List[np.ndarray],
                            n_iter: int = 10, seed: int = 0) -> float:
    """Depth-normalised spectral norm — geometric mean of layer spectral norms.

    The standard Jacobian bound gives:
        σ_max(J) ≤ Π_l σ_max(W_l)

    But the full product is exponentially loose for deep networks:
    for a 20-layer 512-dim net at init (init_scale=2), each
    σ_max(W_l) ≈ 5.6, so Π σ ≈ 5.6^20 ≈ 10^15 — making the friction
    γ_spec = lr · Π σ / α so large the network cannot move at all.

    Fix: use the GEOMETRIC MEAN (depth-normalised product):
        λ_eff = exp( (1/L) Σ_l log σ_max(W_l) )  ≈ 5.6

    This is the "effective per-layer spectral norm" — the curvature
    contribution of a *typical* layer, independent of depth.
    γ_spec = lr · λ_eff / α then stays in a sensible [0, 10] range
    at init and rises proportionally as weights grow, providing
    calibrated adaptive braking without freezing the network.
    """
    rng = np.random.default_rng(seed)
    log_spectral_sum = 0.0
    n_valid = 0

    for W in W_list:
        if W.ndim < 2 or W.shape[0] < 1 or W.shape[1] < 1:
            continue
        # Power iteration for σ_max(W)
        v = rng.normal(0, 1, W.shape[1])
        v /= np.linalg.norm(v) + 1e-12
        for _ in range(n_iter):
            u = W @ v
            u_norm = np.linalg.norm(u)
            if u_norm < 1e-12:
                break
            u /= u_norm
            v = W.T @ u
            v_norm = np.linalg.norm(v)
            if v_norm < 1e-12:
                break
            v /= v_norm
        sigma = float(np.linalg.norm(W @ v))
        log_spectral_sum += np.log(max(sigma, 1e-12))
        n_valid += 1

    if n_valid == 0:
        return 1.0
    # Geometric mean: exp((1/L) Σ log σ_l) — depth-normalised, no overflow.
    # Full product Π σ_l grows as σ^L ≈ 5.6^20 ≈ 10^15 for a 20-layer init,
    # making γ_spec astronomically large and freezing the network.
    # Geometric mean gives the typical per-layer spectral norm ≈ 5.6,
    # keeping γ_spec = lr · λ_eff / α in a sensible [0, 10] range.
    return float(np.exp(log_spectral_sum / n_valid))


# ═════════════════════════════════════════════════════════════
#  BSDT CHANNELS IN GRADIENT SPACE
# ═════════════════════════════════════════════════════════════

@dataclass
class GradientBSDT:
    """BSDT four-channel operator in gradient/weight space.

    Channels:
      δ_C (Camouflage):      gradient herding — layers with small grad norm
                              but large parameter norm (hiding instability)
      δ_G (Feature Gap):     per-layer gradient imbalance vs. reference
      δ_A (Activity Anomaly): sudden gradient magnitude changes between epochs
      δ_T (Temporal Novelty): gradient direction novelty (cosine divergence
                              from running average)

    E_BS = Σ w_k ψ_k(δ_k)
    """
    theta: float = 1.0
    # Running statistics
    prev_grad_norms: Optional[np.ndarray] = None
    running_grad_dir: Optional[np.ndarray] = None
    ema_alpha: float = 0.1
    ref_grad_norms: Optional[np.ndarray] = None

    def calibrate(self, grad_norms: np.ndarray):
        """Set reference gradient norms from early (stable) training."""
        self.ref_grad_norms = grad_norms.copy()
        self.prev_grad_norms = grad_norms.copy()

    def compute_channels(self, W_list: List[np.ndarray],
                         dW_list: List[np.ndarray]) -> Dict[str, float]:
        """Compute BSDT channels from current weights and gradients."""
        g_norms = per_layer_grad_norms(dW_list)
        w_norms = np.array([float(np.linalg.norm(W)) for W in W_list])

        # δ_C: Camouflage — layers where grad is small but weights are large
        # (instability hiding behind small gradients)
        ratios = w_norms / (g_norms + 1e-10)
        delta_C = float(np.max(ratios) / (np.mean(ratios) + 1e-10))

        # δ_G: Feature Gap — gradient imbalance relative to reference
        if self.ref_grad_norms is not None:
            gap = np.abs(g_norms - self.ref_grad_norms)
            delta_G = float(np.mean(gap) / (np.mean(self.ref_grad_norms) + 1e-10))
        else:
            delta_G = 0.0

        # δ_A: Activity — sudden gradient magnitude change
        if self.prev_grad_norms is not None:
            change = np.abs(g_norms - self.prev_grad_norms)
            delta_A = float(np.mean(change) / (np.mean(self.prev_grad_norms) + 1e-10))
        else:
            delta_A = 0.0
        self.prev_grad_norms = g_norms.copy()

        # δ_T: Temporal novelty — gradient direction change
        flat_grad = np.concatenate([dW.flatten() for dW in dW_list])
        flat_norm = np.linalg.norm(flat_grad) + 1e-12
        flat_dir = flat_grad / flat_norm

        if self.running_grad_dir is not None:
            cos_sim = float(np.dot(flat_dir, self.running_grad_dir))
            delta_T = max(0.0, 1.0 - cos_sim)  # 0 = same direction, 2 = opposite
            self.running_grad_dir = (self.ema_alpha * flat_dir +
                                     (1 - self.ema_alpha) * self.running_grad_dir)
            rn = np.linalg.norm(self.running_grad_dir) + 1e-12
            self.running_grad_dir /= rn
        else:
            delta_T = 0.0
            self.running_grad_dir = flat_dir.copy()

        return {
            "camouflage": delta_C,
            "feature_gap": delta_G,
            "activity": delta_A,
            "temporal_novelty": delta_T,
        }

    def energy(self, channels: Dict[str, float]) -> float:
        """E_BS = Σ w_k ψ_k(δ_k), with ψ_k = δ_k² (quadratic wells)."""
        w = {"camouflage": 0.35, "feature_gap": 0.25,
             "activity": 0.25, "temporal_novelty": 0.15}
        return sum(w[k] * channels[k] ** 2 for k in w)

    def adaptive_friction(self, E_bs: float, alpha: float = 0.1,
                          lambda_max: float = 1.0,
                          lr: float = 0.01) -> float:
        """Two-level adaptive friction:

        Level 1 — Spectral stability (γ_spec):
            Derived from the descent condition  lr / (1 + γ) ≤ α / λ_max,
            which keeps the effective step inside the curvature radius.
            Solving for γ:  γ_spec = lr · λ_max / α.
            Larger curvature (λ_max ↑) → more friction (γ_spec ↑).
            This is the correct sign: the old formula α/λ_max gave LESS
            friction as curvature grew — exactly backwards.

        Level 2 — Structural energy (γ_struct):
            γ_struct = E_BS / (E_BS + θ)  ∈ [0, 1).
            Captures BSDT-channel stress independent of spectral geometry.

        Combined: γ* = max(γ_spec, γ_struct)
        """
        gamma_spec   = lr * lambda_max / alpha          # ∝ curvature
        gamma_struct = E_bs / (E_bs + self.theta)       # BSDT structural
        return max(gamma_spec, gamma_struct)

    def reset(self):
        self.prev_grad_norms = None
        self.running_grad_dir = None
        self.ref_grad_norms = None


# ═════════════════════════════════════════════════════════════
#  OPTIMISERS
# ═════════════════════════════════════════════════════════════

class Optimiser:
    """Base optimiser interface."""
    name: str = "base"

    def step(self, net: BlowUpNet, dW_list, db_list, epoch: int,
             lr: float) -> Dict:
        raise NotImplementedError

    def reset(self):
        pass


class SGDOptimiser(Optimiser):
    """Vanilla SGD — expected to blow up."""
    name = "SGD"

    def step(self, net, dW_list, db_list, epoch, lr):
        for i in range(net.n_layers):
            net.W[i] -= lr * dW_list[i]
            net.b[i] -= lr * db_list[i]
        return {"friction": 1.0}


class SGDClipOptimiser(Optimiser):
    """SGD with gradient clipping — the 'constant friction' analogue."""
    name = "SGD+Clip"

    def __init__(self, max_norm: float = 1.0):
        self.max_norm = max_norm

    def step(self, net, dW_list, db_list, epoch, lr):
        gnorm = grad_norm(dW_list, db_list)
        scale = min(1.0, self.max_norm / (gnorm + 1e-12))
        for i in range(net.n_layers):
            net.W[i] -= lr * scale * dW_list[i]
            net.b[i] -= lr * scale * db_list[i]
        return {"friction": 1.0 / (scale + 1e-12), "clip_scale": scale}


class AdamOptimiser(Optimiser):
    """Adam optimiser."""
    name = "Adam"

    def __init__(self, beta1=0.9, beta2=0.999, eps=1e-8):
        self.beta1 = beta1
        self.beta2 = beta2
        self.eps = eps
        self.m_W = None
        self.v_W = None
        self.m_b = None
        self.v_b = None
        self.t = 0

    def reset(self):
        self.m_W = None
        self.v_W = None
        self.m_b = None
        self.v_b = None
        self.t = 0

    def step(self, net, dW_list, db_list, epoch, lr):
        if self.m_W is None:
            self.m_W = [np.zeros_like(w) for w in dW_list]
            self.v_W = [np.zeros_like(w) for w in dW_list]
            self.m_b = [np.zeros_like(b) for b in db_list]
            self.v_b = [np.zeros_like(b) for b in db_list]

        self.t += 1
        for i in range(net.n_layers):
            self.m_W[i] = self.beta1 * self.m_W[i] + (1 - self.beta1) * dW_list[i]
            self.v_W[i] = self.beta2 * self.v_W[i] + (1 - self.beta2) * dW_list[i]**2
            self.m_b[i] = self.beta1 * self.m_b[i] + (1 - self.beta1) * db_list[i]
            self.v_b[i] = self.beta2 * self.v_b[i] + (1 - self.beta2) * db_list[i]**2

            m_hat_W = self.m_W[i] / (1 - self.beta1**self.t)
            v_hat_W = self.v_W[i] / (1 - self.beta2**self.t)
            m_hat_b = self.m_b[i] / (1 - self.beta1**self.t)
            v_hat_b = self.v_b[i] / (1 - self.beta2**self.t)

            net.W[i] -= lr * m_hat_W / (np.sqrt(v_hat_W) + self.eps)
            net.b[i] -= lr * m_hat_b / (np.sqrt(v_hat_b) + self.eps)

        return {"friction": 1.0}


class AdamWOptimiser(AdamOptimiser):
    """AdamW (decoupled weight decay)."""
    name = "AdamW"

    def __init__(self, beta1=0.9, beta2=0.999, eps=1e-8, weight_decay=0.01):
        super().__init__(beta1, beta2, eps)
        self.weight_decay = weight_decay

    def step(self, net, dW_list, db_list, epoch, lr):
        result = super().step(net, dW_list, db_list, epoch, lr)
        # Decoupled weight decay
        for i in range(net.n_layers):
            net.W[i] *= (1 - lr * self.weight_decay)
        return result


class RMSPropOptimiser(Optimiser):
    """RMSProp — expected to blow up on pathological nets."""
    name = "RMSProp"

    def __init__(self, alpha_rms=0.99, eps=1e-8):
        self.alpha_rms = alpha_rms
        self.eps = eps
        self.v_W = None
        self.v_b = None

    def reset(self):
        self.v_W = None
        self.v_b = None

    def step(self, net, dW_list, db_list, epoch, lr):
        if self.v_W is None:
            self.v_W = [np.zeros_like(w) for w in dW_list]
            self.v_b = [np.zeros_like(b) for b in db_list]

        for i in range(net.n_layers):
            self.v_W[i] = self.alpha_rms * self.v_W[i] + (1 - self.alpha_rms) * dW_list[i]**2
            self.v_b[i] = self.alpha_rms * self.v_b[i] + (1 - self.alpha_rms) * db_list[i]**2

            net.W[i] -= lr * dW_list[i] / (np.sqrt(self.v_W[i]) + self.eps)
            net.b[i] -= lr * db_list[i] / (np.sqrt(self.v_b[i]) + self.eps)

        return {"friction": 1.0}


# ─── BSDT OPTIMISER FAMILY ───────────────────────────────────

class BSDTOptimiser(Optimiser):
    """Core BSDT optimiser with two-level adaptive friction.

    The friction multiplier γ* scales the effective learning rate:
      effective_lr = lr / (1 + γ*)
    When γ* → 0: behaves like vanilla SGD (low stress)
    When γ* → ∞: step → 0 (emergency braking during explosion)
    """
    name = "BSDT"

    def __init__(self, alpha: float = 0.1, theta: float = 1.0):
        self.bsdt = GradientBSDT(theta=theta)
        self.alpha = alpha
        self.calibrated = False
        self._cached_epoch = -1
        self._cached_lam   = 1.0

    def reset(self):
        self.bsdt.reset()
        self.calibrated    = False
        self._cached_epoch = -1
        self._cached_lam   = 1.0

    def _compute_friction(self, net, dW_list, db_list, epoch, lr):
        """Compute BSDT friction and channel diagnostics.
        Spectral radius is cached per epoch to avoid redundant power
        iterations inside the mini-batch loop.
        """
        channels = self.bsdt.compute_channels(net.W, dW_list)
        E_bs = self.bsdt.energy(channels)
        # Cache lam_max: recompute only at the first batch of each epoch
        if epoch != self._cached_epoch:
            self._cached_lam   = spectral_radius_approx(net.W, seed=epoch)
            self._cached_epoch = epoch
        lam_max    = self._cached_lam
        gamma_star = self.bsdt.adaptive_friction(E_bs, self.alpha, lam_max, lr)

        # Calibrate on first stable epoch
        if not self.calibrated and epoch == 0:
            g_norms = per_layer_grad_norms(dW_list)
            if np.all(np.isfinite(g_norms)):
                self.bsdt.calibrate(g_norms)
                self.calibrated = True

        return gamma_star, E_bs, channels, lam_max

    def step(self, net, dW_list, db_list, epoch, lr):
        gamma_star, E_bs, channels, lam_max = \
            self._compute_friction(net, dW_list, db_list, epoch, lr)

        effective_lr = lr / (1.0 + gamma_star)

        for i in range(net.n_layers):
            net.W[i] -= effective_lr * dW_list[i]
            net.b[i] -= effective_lr * db_list[i]

        return {
            "friction": 1.0 + gamma_star,
            "gamma_star": gamma_star,
            "E_bs": E_bs,
            "channels": channels,
            "lambda_max": lam_max,
        }


class MFLSOptimiser(BSDTOptimiser):
    """MFLS-weighted variant: uses MFLS composite score for friction."""
    name = "MFLS"

    def step(self, net, dW_list, db_list, epoch, lr):
        gamma_star, E_bs, channels, lam_max = \
            self._compute_friction(net, dW_list, db_list, epoch, lr)

        # MFLS score emphasises temporal_novelty + activity
        mfls_score = (0.4 * channels["temporal_novelty"] +
                      0.3 * channels["activity"] +
                      0.2 * channels["camouflage"] +
                      0.1 * channels["feature_gap"])
        gamma_mfls = mfls_score / (mfls_score + self.bsdt.theta)
        gamma_combined = max(gamma_star, gamma_mfls)

        effective_lr = lr / (1.0 + gamma_combined)
        for i in range(net.n_layers):
            net.W[i] -= effective_lr * dW_list[i]
            net.b[i] -= effective_lr * db_list[i]

        return {
            "friction": 1.0 + gamma_combined,
            "gamma_star": gamma_combined,
            "E_bs": E_bs,
            "channels": channels,
            "lambda_max": lam_max,
        }


class MolecularOptimiser(BSDTOptimiser):
    """Molecular: per-layer LJ-inspired friction — softer damping curve."""
    name = "Molecular"

    def step(self, net, dW_list, db_list, epoch, lr):
        gamma_star, E_bs, channels, lam_max = \
            self._compute_friction(net, dW_list, db_list, epoch, lr)

        g_norms = per_layer_grad_norms(dW_list)

        for i in range(net.n_layers):
            # Per-layer Lennard-Jones friction: stronger near blow-up
            gnorm_i = g_norms[i]
            sigma_i = 1.0  # equilibrium gradient norm
            r = gnorm_i / (sigma_i + 1e-10)
            # Repulsive when r > 1 (gradient too large), attractive when r < 1
            lj_friction = max(0.0, (r ** 6 - 1.0))
            layer_gamma = gamma_star + 0.5 * lj_friction

            effective_lr = lr / (1.0 + layer_gamma)
            net.W[i] -= effective_lr * dW_list[i]
            net.b[i] -= effective_lr * db_list[i]

        return {
            "friction": 1.0 + gamma_star,
            "gamma_star": gamma_star,
            "E_bs": E_bs,
            "channels": channels,
            "lambda_max": lam_max,
        }


class GravityOptimiser(BSDTOptimiser):
    """Gravity: uses spectral radius directly (α/λ_max dominant)."""
    name = "Gravity"

    def step(self, net, dW_list, db_list, epoch, lr):
        gamma_star, E_bs, channels, lam_max = \
            self._compute_friction(net, dW_list, db_list, epoch, lr)

        # Gravity mode: pure spectral control — γ_grav = lr·λ/α
        # (proportional to curvature; the old α/λ was inverted)
        gamma_grav = lr * lam_max / self.alpha
        gamma_combined = max(gamma_grav, gamma_star * 0.5)

        effective_lr = lr / (1.0 + gamma_combined)
        for i in range(net.n_layers):
            net.W[i] -= effective_lr * dW_list[i]
            net.b[i] -= effective_lr * db_list[i]

        return {
            "friction": 1.0 + gamma_combined,
            "gamma_star": gamma_combined,
            "E_bs": E_bs,
            "channels": channels,
            "lambda_max": lam_max,
        }


class HybridOptimiser(BSDTOptimiser):
    """Hybrid: blends Molecular + Gravity with adaptive weighting."""
    name = "Hybrid"

    def step(self, net, dW_list, db_list, epoch, lr):
        gamma_star, E_bs, channels, lam_max = \
            self._compute_friction(net, dW_list, db_list, epoch, lr)

        # Blend: use E_BS to choose between molecular (structural)
        # and gravity (spectral)
        blend = E_bs / (E_bs + 1.0)   # →1 when stressed, →0 when calm
        gamma_grav = lr * lam_max / self.alpha   # corrected: ∝ curvature
        gamma_combined = blend * gamma_star + (1 - blend) * gamma_grav

        g_norms = per_layer_grad_norms(dW_list)
        for i in range(net.n_layers):
            gnorm_i = g_norms[i]
            lj = max(0.0, (gnorm_i ** 2 - 1.0)) * 0.1
            layer_gamma = gamma_combined + blend * lj

            effective_lr = lr / (1.0 + layer_gamma)
            net.W[i] -= effective_lr * dW_list[i]
            net.b[i] -= effective_lr * db_list[i]

        return {
            "friction": 1.0 + gamma_combined,
            "gamma_star": gamma_combined,
            "E_bs": E_bs,
            "channels": channels,
            "lambda_max": lam_max,
        }


class QuadSurfOptimiser(BSDTOptimiser):
    """QuadSurf: quadratic surface ψ_k(δ) = δ² with heavier camouflage weight."""
    name = "QuadSurf"

    def step(self, net, dW_list, db_list, epoch, lr):
        gamma_star, E_bs, channels, lam_max = \
            self._compute_friction(net, dW_list, db_list, epoch, lr)

        # QuadSurf: emphasise camouflage (gradient herding detection)
        E_qs = (0.50 * channels["camouflage"] ** 2 +
                0.20 * channels["feature_gap"] ** 2 +
                0.20 * channels["activity"] ** 2 +
                0.10 * channels["temporal_novelty"] ** 2)
        gamma_qs = E_qs / (E_qs + self.bsdt.theta)
        gamma_combined = max(gamma_star, gamma_qs)

        effective_lr = lr / (1.0 + gamma_combined)
        for i in range(net.n_layers):
            net.W[i] -= effective_lr * dW_list[i]
            net.b[i] -= effective_lr * db_list[i]

        return {
            "friction": 1.0 + gamma_combined,
            "gamma_star": gamma_combined,
            "E_bs": E_qs,
            "channels": channels,
            "lambda_max": lam_max,
        }


class QuadExpoOptimiser(BSDTOptimiser):
    """QuadExpo: exponential damping ψ_k(δ) = exp(δ) - 1 → sharper response."""
    name = "QuadExpo"

    def step(self, net, dW_list, db_list, epoch, lr):
        gamma_star, E_bs, channels, lam_max = \
            self._compute_friction(net, dW_list, db_list, epoch, lr)

        # Exponential channel response (sharper reaction to stress)
        E_qe = sum(0.25 * (np.exp(min(v, 10.0)) - 1.0)
                    for v in channels.values())
        gamma_qe = E_qe / (E_qe + self.bsdt.theta)
        gamma_combined = max(gamma_star, gamma_qe)

        effective_lr = lr / (1.0 + gamma_combined)
        for i in range(net.n_layers):
            net.W[i] -= effective_lr * dW_list[i]
            net.b[i] -= effective_lr * db_list[i]

        return {
            "friction": 1.0 + gamma_combined,
            "gamma_star": gamma_combined,
            "E_bs": E_qe,
            "channels": channels,
            "lambda_max": lam_max,
        }


class SignedLROptimiser(BSDTOptimiser):
    """SignedLR: sign-aware learning rate — reduces lr when gradient
    direction reverses (oscillation detection via δ_T)."""
    name = "SignedLR"

    def __init__(self, alpha=0.1, theta=1.0):
        super().__init__(alpha, theta)
        self.prev_sign = None

    def reset(self):
        super().reset()
        self.prev_sign = None

    def step(self, net, dW_list, db_list, epoch, lr):
        gamma_star, E_bs, channels, lam_max = \
            self._compute_friction(net, dW_list, db_list, epoch, lr)

        # Sign consistency across layers
        flat_grad = np.concatenate([dW.flatten() for dW in dW_list])
        curr_sign = np.sign(flat_grad)

        if self.prev_sign is not None:
            # Fraction of parameters that changed sign (oscillation)
            sign_change_frac = float(np.mean(curr_sign != self.prev_sign))
            # More sign changes → more friction
            gamma_sign = sign_change_frac * 2.0
        else:
            gamma_sign = 0.0
        self.prev_sign = curr_sign

        gamma_combined = max(gamma_star, gamma_sign)
        effective_lr = lr / (1.0 + gamma_combined)

        for i in range(net.n_layers):
            net.W[i] -= effective_lr * dW_list[i]
            net.b[i] -= effective_lr * db_list[i]

        return {
            "friction": 1.0 + gamma_combined,
            "gamma_star": gamma_combined,
            "E_bs": E_bs,
            "channels": channels,
            "lambda_max": lam_max,
        }


# ═════════════════════════════════════════════════════════════
#  OPTIMISER REGISTRY
# ═════════════════════════════════════════════════════════════

def get_all_optimisers() -> Dict[str, Optimiser]:
    """Return all 13 optimisers: 5 standard + 8 BSDT."""
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
    }


# ═════════════════════════════════════════════════════════════
#  TRAINING LOOP
# ═════════════════════════════════════════════════════════════

@dataclass
class EpochLog:
    epoch: int
    train_loss: float
    test_loss: float
    train_acc: float
    test_acc: float
    grad_norm: float
    friction: float
    blew_up: bool = False
    channels: Optional[Dict[str, float]] = None
    lambda_max: float = 0.0
    E_bs: float = 0.0


def train(net: BlowUpNet, opt: Optimiser,
          X_train: np.ndarray, y_train: np.ndarray,
          X_test: np.ndarray, y_test: np.ndarray,
          lr: float = 0.01, n_epochs: int = 300,
          batch_size: int = 256, seed: int = 42,
          verbose: bool = False) -> List[EpochLog]:
    """Train the BlowUpNet with the given optimiser.

    Returns a list of per-epoch logs. If gradient explosion is detected
    (grad_norm > 1e10 or NaN), training is halted and remaining epochs
    are marked as blown up.
    """
    rng = np.random.default_rng(seed)
    logs = []
    blown = False

    for epoch in range(n_epochs):
        if blown:
            logs.append(EpochLog(
                epoch=epoch, train_loss=float('inf'), test_loss=float('inf'),
                train_acc=0.5, test_acc=0.5, grad_norm=float('inf'),
                friction=0.0, blew_up=True,
            ))
            continue

        # Mini-batch SGD
        indices = rng.permutation(len(X_train))
        epoch_loss = 0.0
        epoch_correct = 0
        n_batches = 0

        for start in range(0, len(X_train), batch_size):
            batch_idx = indices[start:start + batch_size]
            Xb = X_train[batch_idx]
            yb = y_train[batch_idx]

            # Forward
            y_pred, activations = net.forward(Xb)
            loss = binary_cross_entropy(y_pred, yb)

            # Backward
            dW_list, db_list = net.backward(Xb, yb, y_pred, activations)

            # Check for explosion
            gnorm = grad_norm(dW_list, db_list)
            if not np.isfinite(gnorm) or gnorm > 1e10:
                blown = True
                if verbose:
                    print(f"    [BLOW-UP] epoch {epoch}, grad_norm = {gnorm:.2e}")
                break

            # Optimiser step
            step_info = opt.step(net, dW_list, db_list, epoch, lr)

            epoch_loss += loss * len(batch_idx)
            epoch_correct += int(np.sum((y_pred > 0.5) == yb))
            n_batches += 1

        if blown:
            logs.append(EpochLog(
                epoch=epoch, train_loss=float('inf'), test_loss=float('inf'),
                train_acc=0.5, test_acc=0.5, grad_norm=gnorm,
                friction=0.0, blew_up=True,
            ))
            continue

        # Epoch metrics
        avg_train_loss = epoch_loss / len(X_train)
        train_acc = epoch_correct / len(X_train)

        # Test metrics — forward only (no backward needed)
        y_pred_test, _ = net.forward(X_test)
        test_loss = binary_cross_entropy(y_pred_test, y_test)
        test_acc = float(np.mean((y_pred_test > 0.5) == y_test))

        # Gradient norm: reuse the last mini-batch's gnorm and step_info.
        # The previous code did a full forward+backward over all training
        # data here (O(N·L·d²) every epoch) purely for logging — 6× more
        # expensive than all the mini-batches combined.  The last-batch
        # gnorm is a faithful proxy and avoids the redundant pass.
        final_gnorm = gnorm

        log = EpochLog(
            epoch=epoch,
            train_loss=avg_train_loss,
            test_loss=test_loss,
            train_acc=train_acc,
            test_acc=test_acc,
            grad_norm=final_gnorm,
            friction=step_info.get("friction", 1.0),
            channels=step_info.get("channels"),
            lambda_max=step_info.get("lambda_max", 0.0),
            E_bs=step_info.get("E_bs", 0.0),
        )
        logs.append(log)

        if verbose and epoch % 50 == 0:
            print(f"    ep {epoch:3d}  loss={avg_train_loss:.4f}  "
                  f"acc={train_acc:.3f}  gnorm={final_gnorm:.2e}  "
                  f"γ={step_info.get('friction', 1.0):.2f}")

    return logs
