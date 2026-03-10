"""Fix: Add _normalise and _auto_blend back to HybridGravityEngine."""
import os, sys

FP = os.path.join(os.path.dirname(__file__), 'udl', 'system_mode.py')
with open(FP, encoding='utf-8') as f:
    content = f.read()

if 'def _normalise' in content:
    print('Already has _normalise'); sys.exit(0)

# The methods should go between "return blended" (end of fit_score)
# and "# ─── Conformal scoring methods" in HybridGravityEngine.

# Find the exact location
marker = '''        return blended
 
    # ─── Conformal scoring methods ───────────────────────────

    def _score_new(self, X: np.ndarray) -> np.ndarray:
        """Score new data points using the fitted engine.

        Requires that fit_score() has been called first.
        """
        X = np.asarray(X, dtype=np.float64)
        # Score via both sub-engines and blend
        scores_mol = self.molecular._score_new(X)
        scores_grav = self.gravity._score_new(X)
        scores_mol = self._normalise(scores_mol)
        scores_grav = self._normalise(scores_grav)'''

# Try different whitespace variants
for ws in ['', '\n', ' ']:
    test = f'        return blended\n{ws}\n    # ─── Conformal scoring methods'
    if test in content:
        replacement = f'''        return blended

    def _normalise(self, s: np.ndarray) -> np.ndarray:
        """Min-max normalise to [0, 1]."""
        s_min, s_max = s.min(), s.max()
        if s_max - s_min < 1e-15:
            return np.zeros_like(s)
        return (s - s_min) / (s_max - s_min)

    def _auto_blend(self, scores_mol: np.ndarray,
                    scores_grav: np.ndarray,
                    y: np.ndarray) -> float:
        """Select blend weight by maximising AUROC on training data."""
        from sklearn.metrics import roc_auc_score

        best_w, best_auc = 0.5, 0.0
        for w in np.linspace(0, 1, 11):
            blended = w * scores_mol + (1 - w) * scores_grav
            try:
                auc = roc_auc_score(y, blended)
                if auc > best_auc:
                    best_auc = auc
                    best_w = w
            except ValueError:
                pass

        self._cv_scores = {{'best_weight': best_w, 'best_auc': best_auc}}
        return best_w

    # ─── Conformal scoring methods'''
        content = content.replace(test, replacement)
        print(f'Found with ws={repr(ws)}, replaced.')
        break
else:
    # Try finding HybridGravityEngine's return blended more directly
    # Find the "return blended" line that's inside HybridGravityEngine
    lines = content.split('\n')
    for i, ln in enumerate(lines):
        if 'class HybridGravityEngine' in ln:
            hybrid_start = i
            break
    
    # Find "return blended" within the class
    for i in range(hybrid_start, len(lines)):
        if lines[i].strip() == 'return blended':
            # Insert after this line
            insert_idx = i + 1
            break
    
    new_methods = '''
    def _normalise(self, s: np.ndarray) -> np.ndarray:
        """Min-max normalise to [0, 1]."""
        s_min, s_max = s.min(), s.max()
        if s_max - s_min < 1e-15:
            return np.zeros_like(s)
        return (s - s_min) / (s_max - s_min)

    def _auto_blend(self, scores_mol: np.ndarray,
                    scores_grav: np.ndarray,
                    y: np.ndarray) -> float:
        """Select blend weight by maximising AUROC on training data."""
        from sklearn.metrics import roc_auc_score

        best_w, best_auc = 0.5, 0.0
        for w in np.linspace(0, 1, 11):
            blended = w * scores_mol + (1 - w) * scores_grav
            try:
                auc = roc_auc_score(y, blended)
                if auc > best_auc:
                    best_auc = auc
                    best_w = w
            except ValueError:
                pass

        self._cv_scores = {'best_weight': best_w, 'best_auc': best_auc}
        return best_w
'''
    
    lines.insert(insert_idx, new_methods)
    content = '\n'.join(lines)
    print(f'Inserted after line {insert_idx+1} (line-based fallback).')

with open(FP, 'w', encoding='utf-8') as f:
    f.write(content)

print(f'File: {len(content)} bytes')

import py_compile
try:
    py_compile.compile(FP, doraise=True)
    print('Syntax OK')
except py_compile.PyCompileError as e:
    print(f'Syntax ERROR: {e}')
