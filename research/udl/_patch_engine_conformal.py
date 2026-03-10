"""Patch: Add conformal scoring methods to MolecularEngine, GravityModeEngine, HybridGravityEngine.

Adds to each engine:
  1. _score_new(X) — score new data using the fitted engine (internal)
  2. fit_reference(X_ref, y_ref, cal_frac) — conformal calibration
  3. score_conformal(X) — anomaly scores for new data
  4. predict_pvalue(X) — distribution-free conformal p-values
  5. score_universal(X, y, T, N) — meta-strategy with conformal calibration
"""
import os, sys, textwrap

FP = os.path.join(os.path.dirname(__file__), 'udl', 'system_mode.py')
with open(FP, encoding='utf-8') as f:
    lines = f.readlines()

content = ''.join(lines)

# Check not already patched
if content.count('def fit_reference') >= 3:
    print('Already has fit_reference on engines.'); sys.exit(0)


# ═══════════════════════════════════════════════════════════════
# Helper: generate the conformal methods for a physics engine
# ═══════════════════════════════════════════════════════════════

def make_engine_conformal_methods(engine_name, score_new_body):
    """Generate conformal method text for a given engine class."""
    return f'''
    # ─── Conformal scoring methods ───────────────────────────
    def _score_new(self, X: np.ndarray) -> np.ndarray:
        """Score new data points using the fitted engine.

        Requires that fit_score() has been called first.
        """
{score_new_body}

    def fit_reference(self, X_ref: np.ndarray,
                      y_ref: np.ndarray = None,
                      cal_frac: float = 0.2,
                      random_state: int = 42) -> '{engine_name}':
        """Fit the engine and calibration set for conformal scoring.

        Splits reference data into:
          - fit set (1 - cal_frac): used to run the physics simulation
          - calibration set (cal_frac): used to build the reference
            distribution of nonconformity scores

        Parameters
        ----------
        X_ref  : (N, d) array — reference data (ideally normal-period)
        y_ref  : (N,) array or None — labels (0=normal). If None, all normal.
        cal_frac : float — fraction reserved for calibration
        random_state : int — reproducibility seed

        Returns
        -------
        self
        """
        X_ref = np.asarray(X_ref, dtype=np.float64)
        N = len(X_ref)
        n_cal = max(10, int(N * cal_frac))

        rng = np.random.default_rng(random_state)
        perm = rng.permutation(N)
        idx_fit = perm[:-n_cal]
        idx_cal = perm[-n_cal:]

        X_fit = X_ref[idx_fit]
        X_cal = X_ref[idx_cal]

        if y_ref is not None:
            y_fit = np.asarray(y_ref)[idx_fit]
            y_cal = np.asarray(y_ref)[idx_cal]
        else:
            y_fit = np.zeros(len(X_fit), dtype=int)
            y_cal = np.zeros(len(X_cal), dtype=int)

        # Run the physics simulation on the fit set
        self.fit_score(X_fit, y_fit)

        # Score the calibration set using the fitted engine
        self._cal_scores = self._score_new(X_cal)
        self._cal_sorted = np.sort(self._cal_scores)
        self._cal_N = len(self._cal_scores)
        self._conformal_fitted = True
        return self

    def score_conformal(self, X: np.ndarray) -> np.ndarray:
        """Score new data using the fitted engine.

        Must call fit_reference() first.

        Parameters
        ----------
        X : (N, d) array — points to score

        Returns
        -------
        scores : (N,) array — higher = more anomalous
        """
        if not getattr(self, '_conformal_fitted', False):
            raise RuntimeError('Call fit_reference() before score_conformal()')
        return self._score_new(X)

    def predict_pvalue(self, X: np.ndarray) -> np.ndarray:
        """Conformal p-values with distribution-free validity.

        For each test point x:
            p(x) = (1 + #{{i : A_cal_i >= A(x)}}) / (n_cal + 1)

        Guarantee (Vovk et al., 2005):
            Under exchangeability, P(p(X) <= alpha) <= alpha

        Must call fit_reference() first.

        Parameters
        ----------
        X : (N, d) array — points to score

        Returns
        -------
        pvalues : (N,) array — conformal p-values in (0, 1]
        """
        if not getattr(self, '_conformal_fitted', False):
            raise RuntimeError('Call fit_reference() before predict_pvalue()')

        scores = self._score_new(X)
        n_cal = self._cal_N
        rank = n_cal - np.searchsorted(self._cal_sorted, scores, side='left')
        return (1 + rank) / (n_cal + 1)

    def score_universal(self, X: np.ndarray, y: np.ndarray,
                        T: int, N: int,
                        window: int = None) -> dict:
        """Universal dataset-agnostic scoring with conformal calibration.

        Runs the physics engine + conformal p-values, plus panel-level
        temporal aggregation. Works on any dataset without tuning.

        Parameters
        ----------
        X : (T*N, d) array — flat panel data
        y : (T*N,) array — labels (0 = normal)
        T : int — number of time periods
        N : int — number of agents per period
        window : int or None — rolling window (auto-detected if None)

        Returns
        -------
        dict with keys:
            'scores'    : (T*N,) — point-level anomaly scores
            'q_scores'  : (T,)   — period-level scores
            'pvalues'   : (T*N,) — conformal p-values (point-level)
            'q_pvalues' : (T,)   — conformal p-values (period-level)
        """
        X = np.asarray(X, dtype=np.float64)
        y = np.asarray(y)
        d = X.shape[1]

        if window is None:
            window = 4 if T < 200 else max(4, T // 10)

        # ── Point-level scoring via fit_score (proven pipeline) ──
        s_point = self.fit_score(X, y)

        # ── Panel-level temporal aggregation ──
        y_time = y.reshape(T, N)[:, 0]
        s_3d = s_point.reshape(T, N)

        # Cross-sectional stats per period
        q_mean = s_3d.mean(axis=1)
        q_p90 = np.percentile(s_3d, 90, axis=1)
        q_max = s_3d.max(axis=1)
        q_std = s_3d.std(axis=1)

        # Temporal dynamics
        q_z = np.zeros(T)
        for t in range(window, T):
            w = q_mean[t-window:t]
            mu_w, std_w = w.mean(), w.std() + 1e-10
            q_z[t] = max((q_mean[t] - mu_w) / std_w, 0.0)

        q_mom = np.zeros(T)
        q_mom[1:] = np.maximum(q_mean[1:] - q_mean[:-1], 0.0)

        # Rank-normalised fusion (no dataset-specific weights)
        def rank_norm(x):
            if x.max() == x.min():
                return np.zeros_like(x)
            order = np.argsort(np.argsort(x)).astype(np.float64)
            return order / (len(x) - 1 + 1e-15)

        components = np.column_stack([
            q_mean, q_p90, q_max, q_std, q_z, q_mom
        ])
        ranked = np.column_stack([rank_norm(c) for c in components.T])
        q_scores = ranked.mean(axis=1)

        # ── Conformal calibration ──
        ref_mask = (y == 0)
        cal_pt = s_point[ref_mask]
        cal_pt_sorted = np.sort(cal_pt)
        n_cal = len(cal_pt_sorted)
        rank_pt = n_cal - np.searchsorted(cal_pt_sorted, s_point, side='left')
        pvalues = (1 + rank_pt) / (n_cal + 1)

        cal_q_mask = (y_time == 0)
        cal_q = q_scores[cal_q_mask]
        cal_q_sorted = np.sort(cal_q)
        n_cal_q = len(cal_q_sorted)
        rank_q = n_cal_q - np.searchsorted(cal_q_sorted, q_scores, side='left')
        q_pvalues = (1 + rank_q) / (n_cal_q + 1)

        return {{
            'scores': s_point,
            'q_scores': q_scores,
            'pvalues': pvalues,
            'q_pvalues': q_pvalues,
        }}

'''
    return result


# ═══════════════════════════════════════════════════════════════
# 1. MolecularEngine: insert before GravityModeEngine class
# ═══════════════════════════════════════════════════════════════

mol_score_new = textwrap.dedent("""\
        X = np.asarray(X, dtype=np.float64)
        if self.scaler_ is not None:
            X_scaled = self.scaler_.transform(X)
        else:
            X_scaled = X.copy()
        if self.fused_scorer is not None:
            return self.fused_scorer.score(X_scaled)
        return self.alarm.score(X_scaled)""")

mol_methods = make_engine_conformal_methods('MolecularEngine', mol_score_new)

# Find the separator line before GravityModeEngine
mol_end_marker = '# ═══════════════════════════════════════════════════════════════════\n#  GRAVITY ENGINE (wrapped for mode system)\n# ═══════════════════════════════════════════════════════════════════'
assert mol_end_marker in content, 'Cannot find GRAVITY ENGINE separator'
content = content.replace(mol_end_marker, mol_methods + '\n\n' + mol_end_marker)


# ═══════════════════════════════════════════════════════════════
# 2. GravityModeEngine: insert before HybridGravityEngine class
# ═══════════════════════════════════════════════════════════════

grav_score_new = textwrap.dedent("""\
        X = np.asarray(X, dtype=np.float64)
        if self.scaler_ is not None:
            X_scaled = self.scaler_.transform(X)
        else:
            X_scaled = X.copy()
        if self.fused_scorer is not None:
            return self.fused_scorer.score(X_scaled)
        return self.alarm.score(X_scaled)""")

grav_methods = make_engine_conformal_methods('GravityModeEngine', grav_score_new)

grav_end_marker = '# ═══════════════════════════════════════════════════════════════════\n#  HYBRID ENGINE (Molecular + Gravity blend)\n# ═══════════════════════════════════════════════════════════════════'
assert grav_end_marker in content, 'Cannot find HYBRID ENGINE separator'
content = content.replace(grav_end_marker, grav_methods + '\n\n' + grav_end_marker)


# ═══════════════════════════════════════════════════════════════
# 3. HybridGravityEngine: insert before SpectraFalseAlarmFilter
# ═══════════════════════════════════════════════════════════════

hybrid_score_new = textwrap.dedent("""\
        X = np.asarray(X, dtype=np.float64)
        # Score via both sub-engines and blend
        scores_mol = self.molecular._score_new(X)
        scores_grav = self.gravity._score_new(X)
        scores_mol = self._normalise(scores_mol)
        scores_grav = self._normalise(scores_grav)
        return self._blend_w * scores_mol + (1 - self._blend_w) * scores_grav""")

hybrid_methods = make_engine_conformal_methods('HybridGravityEngine', hybrid_score_new)

hybrid_end_marker = '# ═══════════════════════════════════════════════════════════════════\n#  SPECTRA FALSE-ALARM FILTER\n# ═══════════════════════════════════════════════════════════════════'
assert hybrid_end_marker in content, 'Cannot find SPECTRA separator'
content = content.replace(hybrid_end_marker, hybrid_methods + '\n\n' + hybrid_end_marker)


with open(FP, 'w', encoding='utf-8') as f:
    f.write(content)

# Verify
for engine in ['MolecularEngine', 'GravityModeEngine', 'HybridGravityEngine']:
    count = content.count(f"-> '{engine}'")
    print(f'  {engine}: fit_reference count = {count}')

total_fit_ref = content.count('def fit_reference')
total_score_conf = content.count('def score_conformal')
total_predict_pv = content.count('def predict_pvalue')
total_universal = content.count('def score_universal')
print(f'Total: fit_reference={total_fit_ref}, score_conformal={total_score_conf}, '
      f'predict_pvalue={total_predict_pv}, score_universal={total_universal}')
print(f'File: {len(content)} bytes, {content.count(chr(10))} lines')
