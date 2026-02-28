"""
RL Fusion Agent — Reinforcement-Learning Operator Selection & Weighting
========================================================================
Uses contextual Thompson Sampling to learn which operators to include
and how to weight them, optimising for COVERAGE (not AUC).

Architecture:
  ┌─────────────┐     ┌──────────────┐     ┌──────────────┐
  │  CONTEXT     │────▶│  RL AGENT     │────▶│  ACTION       │
  │  (dataset    │     │  (Thompson    │     │  (operator    │
  │   features)  │     │   Sampling)   │     │   weights)    │
  └─────────────┘     └──────────────┘     └──────────────┘
         │                    │                      │
         │                    ▼                      ▼
         │            ┌──────────────┐     ┌──────────────┐
         └───────────▶│  REWARD       │◀────│  EVALUATE     │
                      │  (coverage)   │     │  (detect &    │
                      └──────────────┘     │   count)      │
                                           └──────────────┘

Three RL strategies:
  1. Thompson Sampling (Bayesian bandits) — default, no hyperparams
  2. UCB1 — Upper Confidence Bound exploration
  3. LinUCB — contextual linear bandit with dataset features

The agent learns ACROSS datasets: meta-learning which operator
combinations work for which data characteristics.

Usage:
    from udl.rl_fusion import RLFusionAgent

    agent = RLFusionAgent(operators=[...])
    agent.fit(X_train, y_train)      # single dataset
    scores = agent.score(X_test)

    # Meta-learning across multiple datasets:
    agent.meta_learn(datasets_dict)  # {name: (X, y), ...}
    agent.fit(X_new, y_new)          # uses learned priors
    scores = agent.score(X_new_test)
"""

import copy
import json
import warnings
import numpy as np
from pathlib import Path
from scipy.stats import spearmanr

from .pipeline import UDLPipeline
from .rank_fusion import RankFusionPipeline


# ─── Arms: operator subsets × fusion strategies ─────────────────────

def _generate_arms(n_operators):
    """
    Generate candidate arms (operator subsets + fusion mode).
    Each arm is (operator_mask, fusion_mode).

    We don't enumerate all 2^n subsets. Instead we use
    structurally motivated candidates:
    - All operators (full stack)
    - Each single operator solo
    - All pairs
    - Leave-one-out combos
    - Top-k by prior performance (added dynamically)
    """
    arms = []

    # Full stack with different fusion modes
    full = tuple([True] * n_operators)
    arms.append((full, 'fisher'))
    arms.append((full, 'fusion'))

    # Each solo operator + fisher
    for i in range(n_operators):
        mask = tuple(j == i for j in range(n_operators))
        arms.append((mask, 'fisher'))

    # All pairs + fusion
    if n_operators <= 8:
        for i in range(n_operators):
            for j in range(i + 1, n_operators):
                mask = tuple(k == i or k == j for k in range(n_operators))
                arms.append((mask, 'fusion'))

    # Leave-one-out + fusion
    for i in range(n_operators):
        mask = tuple(j != i for j in range(n_operators))
        arms.append((mask, 'fusion'))
        arms.append((mask, 'fisher'))

    # Triplets if n <= 6
    if n_operators <= 6:
        from itertools import combinations
        for combo in combinations(range(n_operators), 3):
            mask = tuple(k in combo for k in range(n_operators))
            arms.append((mask, 'fusion'))

    # Deduplicate
    seen = set()
    unique_arms = []
    for arm in arms:
        key = (arm[0], arm[1])
        if key not in seen:
            seen.add(key)
            unique_arms.append(arm)

    return unique_arms


# ─── Context features ───────────────────────────────────────────────

def _extract_context(X, y=None):
    """
    Extract dataset context features for contextual bandits.

    Returns
    -------
    ctx : ndarray (d,) — context feature vector
    """
    n, m = X.shape
    features = [
        np.log10(max(n, 1)),         # log sample size
        np.log10(max(m, 1)),         # log dimensionality
        m / max(n, 1),               # feature ratio
    ]

    if y is not None:
        anom_rate = y.mean()
        features.append(anom_rate)
        features.append(np.log10(max(y.sum(), 1)))  # log n_anomalies
    else:
        features.append(0.01)  # default anomaly rate
        features.append(0.0)

    # Data statistics
    col_stds = np.std(X, axis=0)
    features.append(np.mean(col_stds))           # mean feature std
    features.append(np.std(col_stds))             # std of stds (heterogeneity)
    features.append(np.median(np.abs(X).ravel())) # median abs value

    # Correlation structure
    if m > 1 and m <= 100:
        try:
            corr = np.abs(np.corrcoef(X.T))
            np.fill_diagonal(corr, 0)
            features.append(np.mean(corr))    # mean inter-feature correlation
        except Exception:
            features.append(0.0)
    else:
        features.append(0.0)

    return np.array(features, dtype=np.float64)


# ─── Coverage metric ────────────────────────────────────────────────

def _coverage(scores, y, top_k_pct):
    """Fraction of true anomalies with score in top-k%."""
    anom_idx = np.where(y == 1)[0]
    if len(anom_idx) == 0:
        return 0.0
    threshold = np.percentile(scores, 100 * (1 - top_k_pct))
    return np.sum(scores[anom_idx] >= threshold) / len(anom_idx)


# ─── Thompson Sampling Bandit ───────────────────────────────────────

class ThompsonBandit:
    """
    Beta-Bernoulli Thompson Sampling for arm selection.

    Each arm maintains Beta(α, β) posterior.
    Coverage reward ∈ [0, 1] is treated as Bernoulli-like.
    """

    def __init__(self, n_arms):
        self.n_arms = n_arms
        self.alpha = np.ones(n_arms)  # successes + 1
        self.beta = np.ones(n_arms)   # failures + 1
        self.counts = np.zeros(n_arms, dtype=int)
        self.rewards = np.zeros(n_arms)

    def select(self, rng=None):
        """Sample from posteriors, pick the arm with highest sample."""
        if rng is None:
            rng = np.random.default_rng()
        samples = rng.beta(self.alpha, self.beta)
        return int(np.argmax(samples))

    def update(self, arm, reward):
        """Update posterior with observed coverage reward."""
        # Scale reward to [0, 1] range (coverage is already [0, 1])
        r = np.clip(reward, 0, 1)
        self.alpha[arm] += r
        self.beta[arm] += (1 - r)
        self.counts[arm] += 1
        self.rewards[arm] += reward

    def best_arm(self):
        """Return arm with highest posterior mean."""
        means = self.alpha / (self.alpha + self.beta)
        return int(np.argmax(means))

    def posterior_means(self):
        return self.alpha / (self.alpha + self.beta)

    def to_dict(self):
        return {
            'alpha': self.alpha.tolist(),
            'beta': self.beta.tolist(),
            'counts': self.counts.tolist(),
            'rewards': self.rewards.tolist(),
        }

    @classmethod
    def from_dict(cls, d):
        n = len(d['alpha'])
        b = cls(n)
        b.alpha = np.array(d['alpha'])
        b.beta = np.array(d['beta'])
        b.counts = np.array(d['counts'], dtype=int)
        b.rewards = np.array(d['rewards'])
        return b


# ─── LinUCB Contextual Bandit ───────────────────────────────────────

class LinUCBBandit:
    """
    Linear Upper Confidence Bound contextual bandit.

    Models reward as linear function of context:
      E[r | x, a] = θ_a^T · x

    Uses ridge regression for θ_a estimation with UCB exploration.
    """

    def __init__(self, n_arms, d_context, alpha=1.0):
        self.n_arms = n_arms
        self.d = d_context
        self.ucb_alpha = alpha

        # Per-arm: A_a = d×d matrix, b_a = d vector
        self.A = [np.eye(d_context) for _ in range(n_arms)]
        self.b = [np.zeros(d_context) for _ in range(n_arms)]
        self.counts = np.zeros(n_arms, dtype=int)

    def select(self, context):
        """Select arm with highest UCB given context."""
        x = context.reshape(-1, 1)
        ucbs = np.zeros(self.n_arms)

        for a in range(self.n_arms):
            A_inv = np.linalg.solve(self.A[a], np.eye(self.d))
            theta = A_inv @ self.b[a]
            ucbs[a] = (theta @ context +
                       self.ucb_alpha * np.sqrt(context @ A_inv @ context))

        return int(np.argmax(ucbs))

    def update(self, arm, context, reward):
        """Update arm's model with (context, reward) observation."""
        x = context.reshape(-1, 1)
        self.A[arm] += x @ x.T
        self.b[arm] += reward * context
        self.counts[arm] += 1

    def best_arm(self, context):
        """Return arm with highest expected reward for context."""
        expected = np.zeros(self.n_arms)
        for a in range(self.n_arms):
            A_inv = np.linalg.solve(self.A[a], np.eye(self.d))
            theta = A_inv @ self.b[a]
            expected[a] = theta @ context
        return int(np.argmax(expected))


# ─── Main RL Agent ──────────────────────────────────────────────────

class RLFusionAgent:
    """
    Reinforcement-Learning agent for operator selection and fusion.

    The agent treats each (operator_subset, fusion_mode) combination
    as a bandit arm. It uses Thompson Sampling or LinUCB to learn
    which arm maximises detection COVERAGE, not AUC.

    Parameters
    ----------
    operators : list of (name, operator)
        All available spectrum operators.
    strategy : str
        'thompson' — Beta-Bernoulli Thompson Sampling (default)
        'linucb'   — Contextual Linear UCB
    exploration_rounds : int
        How many arms to try during fit() before committing.
        More rounds = better arm selection, slower fit.
    centroid_method : str
        Centroid method for sub-pipelines.
    score_method : str
        Scoring method for sub-pipelines.
    verbose : bool
        Print diagnostics.
    """

    def __init__(
        self,
        operators,
        strategy='thompson',
        exploration_rounds=5,
        centroid_method='auto',
        score_method='v1',
        verbose=True,
    ):
        self.operator_specs = operators
        self.strategy = strategy
        self.exploration_rounds = exploration_rounds
        self.centroid_method = centroid_method
        self.score_method = score_method
        self.verbose = verbose

        # Generate arms
        self._arms = _generate_arms(len(operators))
        self._n_arms = len(self._arms)

        # Initialize bandit
        if strategy == 'thompson':
            self._bandit = ThompsonBandit(self._n_arms)
        elif strategy == 'linucb':
            d_ctx = 9  # context feature dimension
            self._bandit = LinUCBBandit(self._n_arms, d_ctx, alpha=1.0)
        else:
            raise ValueError(f"Unknown strategy: {strategy}")

        # State
        self._best_arm_idx = None
        self._best_pipe = None
        self._context = None
        self._fitted = False
        self._exploration_log = []
        self._rng = np.random.default_rng(42)

    def _build_pipeline(self, arm_idx):
        """Build a pipeline from an arm specification."""
        mask, fusion_mode = self._arms[arm_idx]
        selected_ops = [
            (name, copy.deepcopy(op))
            for (name, op), include in zip(self.operator_specs, mask)
            if include
        ]

        if not selected_ops:
            return None

        if fusion_mode == 'fisher':
            return UDLPipeline(
                operators=selected_ops,
                centroid_method=self.centroid_method,
                projection_method='fisher',
                score_method=self.score_method,
            )
        else:  # fusion
            return RankFusionPipeline(
                operators=selected_ops,
                centroid_method=self.centroid_method,
                score_method=self.score_method,
                fusion='mean',
            )

    def _arm_description(self, arm_idx):
        """Human-readable description of an arm."""
        mask, fusion_mode = self._arms[arm_idx]
        ops = [name for (name, _), inc in zip(self.operator_specs, mask) if inc]
        return f"{fusion_mode}({'+'.join(ops)})"

    def fit(self, X, y=None):
        """
        Fit the RL agent on a single dataset.

        Process:
        1. Extract context features
        2. Explore: try exploration_rounds arms on validation folds
        3. Exploit: pick the best arm and fit on full training data
        """
        if y is None:
            warnings.warn("[RL] No labels — using RankFusion with all operators")
            self._best_pipe = RankFusionPipeline(
                operators=copy.deepcopy(self.operator_specs),
                fusion='mean',
            )
            self._best_pipe.fit(X, y)
            self._fitted = True
            return self

        self._context = _extract_context(X, y)

        # ── EXPLORATION PHASE ──
        # Use stratified split for evaluation
        from sklearn.model_selection import StratifiedShuffleSplit
        n_anom = int(y.sum())
        if n_anom < 3 or len(X) < 20:
            # Too small — just use all operators with fusion
            if self.verbose:
                print("[RL] Too few samples for exploration — defaulting to full fusion")
            self._best_arm_idx = 1  # full stack + fusion
            self._best_pipe = self._build_pipeline(1)
            if self._best_pipe is not None:
                self._best_pipe.fit(X, y)
            self._fitted = True
            return self

        sss = StratifiedShuffleSplit(n_splits=1, test_size=0.3, random_state=42)
        train_idx, val_idx = next(sss.split(X, y))
        X_tr, X_val = X[train_idx], X[val_idx]
        y_tr, y_val = y[train_idx], y[val_idx]

        anom_rate = y_val.mean()
        top_k = min(max(anom_rate * 2, 0.05), 0.30)

        n_explore = min(self.exploration_rounds, self._n_arms)
        explored = set()

        if self.verbose:
            print(f"[RL] Exploring {n_explore}/{self._n_arms} arms "
                  f"(n={len(X)}, d={X.shape[1]}, anom_rate={anom_rate:.3f})")

        for round_i in range(n_explore):
            # Select arm
            if self.strategy == 'thompson':
                arm = self._bandit.select(self._rng)
                # Force diversity: don't re-explore same arm
                attempts = 0
                while arm in explored and attempts < 20:
                    arm = self._bandit.select(self._rng)
                    attempts += 1
            else:
                arm = self._bandit.select(self._context)

            explored.add(arm)

            # Evaluate arm
            pipe = self._build_pipeline(arm)
            if pipe is None:
                reward = 0.0
            else:
                try:
                    pipe.fit(X_tr, y_tr)
                    scores = pipe.score(X_val)
                    reward = _coverage(scores, y_val, top_k)
                except Exception as e:
                    reward = 0.0
                    if self.verbose:
                        print(f"  [RL] Arm {arm} ({self._arm_description(arm)}) failed: {e}")

            # Update bandit
            if self.strategy == 'thompson':
                self._bandit.update(arm, reward)
            else:
                self._bandit.update(arm, self._context, reward)

            self._exploration_log.append({
                'round': round_i,
                'arm': arm,
                'description': self._arm_description(arm),
                'reward': reward,
            })

            if self.verbose:
                print(f"  Round {round_i}: {self._arm_description(arm):40s} "
                      f"coverage={reward:.3f}")

        # ── EXPLOITATION PHASE ──
        # Pick best arm
        if self.strategy == 'thompson':
            self._best_arm_idx = self._bandit.best_arm()
        else:
            self._best_arm_idx = self._bandit.best_arm(self._context)

        if self.verbose:
            print(f"[RL] Selected: {self._arm_description(self._best_arm_idx)} "
                  f"(posterior mean={self._bandit.posterior_means()[self._best_arm_idx]:.3f})"
                  if self.strategy == 'thompson' else
                  f"[RL] Selected: {self._arm_description(self._best_arm_idx)}")

        # Fit best arm on full training data
        self._best_pipe = self._build_pipeline(self._best_arm_idx)
        if self._best_pipe is not None:
            self._best_pipe.fit(X, y)
        self._fitted = True
        return self

    def score(self, X):
        """Score test data using the selected arm's pipeline."""
        assert self._fitted, "Must call fit() first"
        if self._best_pipe is None:
            return np.zeros(len(X))
        return self._best_pipe.score(X)

    def predict(self, X, threshold=0.5):
        scores = self.score(X)
        t = np.percentile(scores, 100 * (1 - threshold))
        return (scores >= t).astype(int)

    # ── META-LEARNING ────────────────────────────────────────────────

    def meta_learn(self, datasets, n_rounds_per_dataset=10):
        """
        Learn operator preferences across multiple datasets.

        This gives the bandit strong priors for new datasets
        by exploring arms on many different data distributions.

        Parameters
        ----------
        datasets : dict[str, (X, y)]
            Named datasets to learn from.
        n_rounds_per_dataset : int
            Exploration budget per dataset.
        """
        if self.verbose:
            print(f"[RL] Meta-learning across {len(datasets)} datasets, "
                  f"{n_rounds_per_dataset} rounds each")

        for ds_name, (X, y) in datasets.items():
            if self.verbose:
                print(f"\n  === {ds_name} ===")

            ctx = _extract_context(X, y)
            n_anom = int(y.sum())
            if n_anom < 3:
                continue

            from sklearn.model_selection import StratifiedShuffleSplit
            sss = StratifiedShuffleSplit(n_splits=1, test_size=0.3, random_state=42)
            train_idx, val_idx = next(sss.split(X, y))
            X_tr, X_val = X[train_idx], X[val_idx]
            y_tr, y_val = y[train_idx], y[val_idx]

            anom_rate = y_val.mean()
            top_k = min(max(anom_rate * 2, 0.05), 0.30)

            explored = set()
            for r in range(min(n_rounds_per_dataset, self._n_arms)):
                if self.strategy == 'thompson':
                    arm = self._bandit.select(self._rng)
                    attempts = 0
                    while arm in explored and attempts < 20:
                        arm = self._bandit.select(self._rng)
                        attempts += 1
                else:
                    arm = self._bandit.select(ctx)

                explored.add(arm)

                pipe = self._build_pipeline(arm)
                if pipe is None:
                    reward = 0.0
                else:
                    try:
                        pipe.fit(X_tr, y_tr)
                        scores = pipe.score(X_val)
                        reward = _coverage(scores, y_val, top_k)
                    except Exception:
                        reward = 0.0

                if self.strategy == 'thompson':
                    self._bandit.update(arm, reward)
                else:
                    self._bandit.update(arm, ctx, reward)

                if self.verbose:
                    print(f"    {self._arm_description(arm):40s} cov={reward:.3f}")

        if self.verbose:
            print(f"\n[RL] Meta-learning complete. Posterior means:")
            means = self._bandit.posterior_means()
            ranked = np.argsort(means)[::-1]
            for i, arm_idx in enumerate(ranked[:10]):
                print(f"    #{i+1}: {self._arm_description(arm_idx):40s} "
                      f"mean={means[arm_idx]:.3f} (n={self._bandit.counts[arm_idx]})")

    # ── PERSISTENCE ──────────────────────────────────────────────────

    def save_priors(self, path):
        """Save learned bandit parameters to disk."""
        data = {
            'strategy': self.strategy,
            'n_arms': self._n_arms,
            'arms': [(list(m), f) for m, f in self._arms],
            'bandit': self._bandit.to_dict(),
            'exploration_log': self._exploration_log,
        }
        with open(path, 'w') as f:
            json.dump(data, f, indent=2)

    def load_priors(self, path):
        """Load previously learned bandit parameters."""
        with open(path) as f:
            data = json.load(f)
        if data['n_arms'] != self._n_arms:
            warnings.warn(f"Arm count mismatch: saved {data['n_arms']} vs current {self._n_arms}")
            return
        self._bandit = ThompsonBandit.from_dict(data['bandit'])
        self._exploration_log = data.get('exploration_log', [])

    # ── DIAGNOSTICS ──────────────────────────────────────────────────

    @property
    def selected_arm(self):
        if self._best_arm_idx is None:
            return None
        return self._arm_description(self._best_arm_idx)

    @property
    def arm_rankings(self):
        """Return arms sorted by posterior mean (best first)."""
        means = self._bandit.posterior_means()
        ranked = np.argsort(means)[::-1]
        return [
            (self._arm_description(i), means[i], int(self._bandit.counts[i]))
            for i in ranked
        ]

    def __repr__(self):
        if not self._fitted:
            return f"RLFusionAgent(strategy='{self.strategy}', n_arms={self._n_arms}, not fitted)"
        return (f"RLFusionAgent(strategy='{self.strategy}', "
                f"selected={self.selected_arm})")
