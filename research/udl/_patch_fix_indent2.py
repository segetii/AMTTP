"""Fix: Completely rewrite the engine conformal patches with correct indentation.

Strategy: Remove all misplaced conformal methods, then re-insert with correct
8-space indentation inside the _score_new body.
"""
import os, sys, re

FP = os.path.join(os.path.dirname(__file__), 'udl', 'system_mode.py')
with open(FP, encoding='utf-8') as f:
    content = f.read()

# Step 1: Remove all the misplaced conformal blocks.
# They start with "    # ─── Conformal scoring methods" and end with
# the closing of score_universal (which ends with a return dict with }}). 
# We need to find all three blocks and remove them.

# Strategy: find each block by locating "    # ─── Conformal scoring methods"
# and removing everything from there to the next class separator comment.

# First, let's just strip ALL conformal method text from the engines
# and start fresh. 

# Find all occurrences of the conformal marker
marker = '    # ─── Conformal scoring methods'
occurrences = []
pos = 0
while True:
    idx = content.find(marker, pos)
    if idx == -1:
        break
    occurrences.append(idx)
    pos = idx + 1

print(f'Found {len(occurrences)} conformal marker(s)')

# Also find the _score_new blocks that have wrong indentation
# Pattern: lines 1089-1095 style (no indentation for if/else in _score_new body)
score_new_marker = '    def _score_new(self, X: np.ndarray) -> np.ndarray:'
sn_count = content.count(score_new_marker)
print(f'Found {sn_count} _score_new definitions')

# The safest approach: remove all engine conformal additions and redo.
# Find the three separator comments and remove everything between
# the class's last "return scores" / "return blended" and the separator.

# Approach: Remove all conformal method text, then re-add properly.

# Let's identify the exact boundaries of each engine's conformal additions
# by finding the text between specific anchors.

# For MolecularEngine: everything from after "self._far_calibrator = cal\n\n        return scores\n\n\n"
# before "# ═══...GRAVITY ENGINE"
# The original code had: return scores\n\n\n# ═══...GRAVITY ENGINE

# Let's use a different approach: read the file that we know had correct syntax
# before the engine conformal patch, and regenerate.

# Actually, the simplest fix: find each engine class, find its last method's
# return statement, remove everything after that until the next class separator,
# then insert the conformal methods properly.

# Let me take a line-based approach.

lines = content.split('\n')
total = len(lines)

def find_line(lines, text, start=0):
    for i in range(start, len(lines)):
        if text in lines[i]:
            return i
    return -1

# Find class starts
mol_start = find_line(lines, 'class MolecularEngine:')
grav_start = find_line(lines, 'class GravityModeEngine:')
hybrid_start = find_line(lines, 'class HybridGravityEngine:')
spectra_start = find_line(lines, 'class SpectraFalseAlarmFilter:')

print(f'Mol={mol_start+1}, Grav={grav_start+1}, Hybrid={hybrid_start+1}, Spectra={spectra_start+1}')

# Find the separator comments (they're 3 lines: ═══, text, ═══)
grav_sep = find_line(lines, '#  GRAVITY ENGINE (wrapped for mode system)')
hybrid_sep = find_line(lines, '#  HYBRID ENGINE (Molecular + Gravity blend)')
spectra_sep = find_line(lines, '#  SPECTRA FALSE-ALARM FILTER')

print(f'Grav_sep={grav_sep+1}, Hybrid_sep={hybrid_sep+1}, Spectra_sep={spectra_sep+1}')

# For each engine: find the "return scores"/"return blended" that ends the 
# original class body (before conformal additions), then remove everything
# from there+1 to the separator-1, then insert new methods.

# MolecularEngine ends with "        return scores" before grav_sep
# Find the FIRST "return scores" that belongs to MolecularEngine (in its last method)
# The original fit_score ends with return scores after FAR calibration block

def find_class_end(lines, class_start, separator_line):
    """Find the last 'return scores' or 'return blended' before the separator."""
    # Look for the pattern:
    #         return scores
    # followed by blank lines before the separator
    for i in range(separator_line - 1, class_start, -1):
        stripped = lines[i].strip()
        if stripped in ('return scores', 'return blended'):
            return i
        # Skip blank lines and comments
        if stripped and not stripped.startswith('#') and not stripped.startswith('def _score_new') and stripped != 'return self.alarm.score(X_scaled)':
            # We've hit actual code that isn't a return
            pass
    return -1

# For MolecularEngine: find last "return scores" before grav_sep
mol_end = -1
for i in range(grav_sep - 1, mol_start, -1):
    if lines[i].strip() == 'return scores':
        mol_end = i
        break

# For GravityModeEngine: find last "return scores" before hybrid_sep  
grav_end = -1
for i in range(hybrid_sep - 1, grav_start, -1):
    if lines[i].strip() == 'return scores':
        grav_end = i
        break

# For HybridGravityEngine: find last "return blended" before spectra_sep
hybrid_end = -1
for i in range(spectra_sep - 1, hybrid_start, -1):
    if lines[i].strip() == 'return blended':
        hybrid_end = i
        break

print(f'Mol_end={mol_end+1}, Grav_end={grav_end+1}, Hybrid_end={hybrid_end+1}')

# Verify these are correct by checking context
for name, idx in [('Mol', mol_end), ('Grav', grav_end), ('Hybrid', hybrid_end)]:
    if idx > 0:
        print(f'{name} end context: {lines[idx-1].rstrip()[:60]} | {lines[idx].rstrip()[:60]} | {lines[idx+1].rstrip()[:60]}')

# Now build the conformal methods text with correct 4+4=8 space indentation
# for the _score_new body

CONFORMAL_METHODS_TEMPLATE = '''
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

        Splits reference data into fit + calibration sets.
        Runs physics simulation on fit set, scores calibration set
        to build reference distribution for conformal inference.

        Parameters
        ----------
        X_ref  : (N, d) array — reference data
        y_ref  : (N,) array or None — labels (0=normal)
        cal_frac : float — fraction reserved for calibration
        random_state : int — seed

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
        else:
            y_fit = np.zeros(len(X_fit), dtype=int)

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
        """
        if not getattr(self, '_conformal_fitted', False):
            raise RuntimeError('Call fit_reference() before score_conformal()')
        return self._score_new(X)

    def predict_pvalue(self, X: np.ndarray) -> np.ndarray:
        """Conformal p-values with distribution-free validity.

        p(x) = (1 + #{{i : A_cal_i >= A(x)}}) / (n_cal + 1)

        Guarantee: P(p(X) <= alpha) <= alpha for any distribution.
        Must call fit_reference() first.
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

        Runs physics engine + panel-level temporal aggregation +
        conformal p-values. Works on any dataset without tuning.

        Parameters
        ----------
        X : (T*N, d) — flat panel data
        y : (T*N,) — labels (0 = normal)
        T, N : int — periods, agents
        window : int or None — auto-detected

        Returns
        -------
        dict: scores, q_scores, pvalues, q_pvalues
        """
        X = np.asarray(X, dtype=np.float64)
        y = np.asarray(y)

        if window is None:
            window = 4 if T < 200 else max(4, T // 10)

        # ── Point-level scoring ──
        s_point = self.fit_score(X, y)

        # ── Panel-level temporal aggregation ──
        y_time = y.reshape(T, N)[:, 0]
        s_3d = s_point.reshape(T, N)

        q_mean = s_3d.mean(axis=1)
        q_p90 = np.percentile(s_3d, 90, axis=1)
        q_max = s_3d.max(axis=1)
        q_std = s_3d.std(axis=1)

        q_z = np.zeros(T)
        for t in range(window, T):
            w = q_mean[t-window:t]
            mu_w, std_w = w.mean(), w.std() + 1e-10
            q_z[t] = max((q_mean[t] - mu_w) / std_w, 0.0)

        q_mom = np.zeros(T)
        q_mom[1:] = np.maximum(q_mean[1:] - q_mean[:-1], 0.0)

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

# Build the three engine-specific versions
mol_score_body = '''        X = np.asarray(X, dtype=np.float64)
        if self.scaler_ is not None:
            X_scaled = self.scaler_.transform(X)
        else:
            X_scaled = X.copy()
        if self.fused_scorer is not None:
            return self.fused_scorer.score(X_scaled)
        return self.alarm.score(X_scaled)'''

grav_score_body = '''        X = np.asarray(X, dtype=np.float64)
        if self.scaler_ is not None:
            X_scaled = self.scaler_.transform(X)
        else:
            X_scaled = X.copy()
        if self.fused_scorer is not None:
            return self.fused_scorer.score(X_scaled)
        return self.alarm.score(X_scaled)'''

hybrid_score_body = '''        X = np.asarray(X, dtype=np.float64)
        # Score via both sub-engines and blend
        scores_mol = self.molecular._score_new(X)
        scores_grav = self.gravity._score_new(X)
        scores_mol = self._normalise(scores_mol)
        scores_grav = self._normalise(scores_grav)
        return self._blend_w * scores_mol + (1 - self._blend_w) * scores_grav'''

mol_methods = CONFORMAL_METHODS_TEMPLATE.format(
    score_new_body=mol_score_body, engine_name='MolecularEngine')
grav_methods = CONFORMAL_METHODS_TEMPLATE.format(
    score_new_body=grav_score_body, engine_name='GravityModeEngine')
hybrid_methods = CONFORMAL_METHODS_TEMPLATE.format(
    score_new_body=hybrid_score_body, engine_name='HybridGravityEngine')

# Now rebuild the file: for each engine, keep lines up to the "return scores"/
# "return blended" line, append the conformal methods, then skip any existing
# conformal text until the separator, then continue.

new_lines = []
i = 0
while i < total:
    line = lines[i]
    
    if i == mol_end:
        # Write the return scores line
        new_lines.append(line)
        # Append conformal methods  
        new_lines.append(mol_methods)
        new_lines.append('')
        # Skip everything until the GRAVITY ENGINE separator (line grav_sep-1)
        i += 1
        while i < total and '#  GRAVITY ENGINE' not in lines[i]:
            i += 1
        # Back up to include the separator's ═══ line
        i -= 1
        new_lines.append('')
        continue
    
    elif i == grav_end:
        new_lines.append(line)
        new_lines.append(grav_methods)
        new_lines.append('')
        i += 1
        while i < total and '#  HYBRID ENGINE' not in lines[i]:
            i += 1
        i -= 1
        new_lines.append('')
        continue
    
    elif i == hybrid_end:
        new_lines.append(line)
        new_lines.append(hybrid_methods)
        new_lines.append('')
        i += 1
        while i < total and '#  SPECTRA FALSE-ALARM FILTER' not in lines[i]:
            i += 1
        i -= 1
        new_lines.append('')
        continue
    
    new_lines.append(line)
    i += 1

new_content = '\n'.join(new_lines)

with open(FP, 'w', encoding='utf-8') as f:
    f.write(new_content)

print(f'Rebuilt file: {len(new_content)} bytes')

# Verify syntax
import py_compile
try:
    py_compile.compile(FP, doraise=True)
    print('Syntax OK')
except py_compile.PyCompileError as e:
    print(f'Syntax ERROR: {e}')
