"""
Patch Mode4GravityEngine to use bb43ff5-era scoring classes:
1. Insert _Mode4FusedScorer (bb43ff5 FusedSystemScorer logic)
2. Update Mode4GravityEngine.__init__ to use bb43ff5 weights & scorer
"""
import re

FILE = r'C:\amttp\research\udl\udl\system_mode.py'
with open(FILE, 'r', encoding='utf-8') as f:
    content = f.read()

# ── 1. Insert _Mode4FusedScorer class before Mode4GravityEngine ──

MODE4_FUSED = '''
class _Mode4FusedScorer:
    """bb43ff5-era FusedSystemScorer: Morse + Betti + UDL, hardcoded blend.

    Key differences from current FusedSystemScorer:
    - 3 sub-scorers (no BSDT)
    - score(): 0.4 * morse + 0.6 * kNN-interpolated enriched
    - _enrich_score(): equal-weight average of minmax-normalised components
    - _minmax normalisation (not _robust_norm)
    """

    def __init__(self, k: int = 15, use_betti: bool = True,
                 use_udl: bool = True):
        self.k = k
        self.morse = MorseTopologyAlarm(
            k=k, weights=np.array([0.35, 0.30, 0.20, 0.15]))
        self.betti = BettiBarcodeSuite(k=min(k + 5, 25)) if use_betti else None
        self.udl = UDLPostSimScorer(k=k) if use_udl else None
        self._X_sim = None
        self._sim_enriched = None

    def fit(self, X_ref: np.ndarray,
            X_sim: np.ndarray = None) -> '_Mode4FusedScorer':
        self.morse.fit(X_ref)
        if self.betti is not None:
            try:
                self.betti.fit(X_ref)
            except Exception:
                self.betti = None
        if self.udl is not None:
            try:
                self.udl.fit(X_ref)
            except Exception:
                self.udl = None
        if X_sim is not None:
            self._X_sim = X_sim.copy()
            self._sim_enriched = self._enrich_score(X_sim)
        return self

    def score(self, X: np.ndarray) -> np.ndarray:
        N = len(X)
        if (self._X_sim is not None and N == len(self._X_sim)
                and np.array_equal(X, self._X_sim)):
            return self._sim_enriched
        morse_s = self._minmax(self.morse.score(X))
        if self._X_sim is not None and self._sim_enriched is not None:
            from sklearn.neighbors import KNeighborsRegressor
            k_interp = min(5, len(self._X_sim))
            knn = KNeighborsRegressor(n_neighbors=k_interp,
                                      weights='distance')
            knn.fit(self._X_sim, self._sim_enriched)
            enriched_s = self._minmax(knn.predict(X))
            return 0.4 * morse_s + 0.6 * enriched_s
        else:
            return self._enrich_score(X)

    def _enrich_score(self, X: np.ndarray) -> np.ndarray:
        components = [self.morse.score(X)]
        if self.betti is not None:
            try:
                components.append(self.betti.score(X))
            except Exception:
                pass
        if self.udl is not None and self.udl._fitted:
            try:
                components.append(self.udl.score(X))
            except Exception:
                pass
        normed = [self._minmax(s) for s in components]
        return np.mean(normed, axis=0)

    @staticmethod
    def _minmax(s: np.ndarray) -> np.ndarray:
        s_min, s_max = s.min(), s.max()
        if s_max - s_min > 1e-15:
            return (s - s_min) / (s_max - s_min)
        return np.zeros_like(s)

'''

# Insert _Mode4FusedScorer just before "class Mode4GravityEngine:"
marker = 'class Mode4GravityEngine:'
if '_Mode4FusedScorer' in content:
    print("_Mode4FusedScorer already exists, skipping insertion")
else:
    idx = content.index(marker)
    content = content[:idx] + MODE4_FUSED + '\n' + content[idx:]
    print("Inserted _Mode4FusedScorer class")

# ── 2. Patch Mode4GravityEngine.__init__ ──
# Fix MorseTopologyAlarm weights and FusedSystemScorer

# 2a: Replace alarm init to use bb43ff5 weights
old_alarm = "self.alarm = MorseTopologyAlarm(k=k_neighbors)"
new_alarm = "self.alarm = MorseTopologyAlarm(k=k_neighbors, weights=np.array([0.35, 0.30, 0.20, 0.15]))"

# Find it within Mode4GravityEngine (not the other engines)
m4_start = content.index('class Mode4GravityEngine:')
m4_region = content[m4_start:]
if old_alarm in m4_region:
    # Replace ONLY the first occurrence after Mode4GravityEngine
    m4_patched = m4_region.replace(old_alarm, new_alarm, 1)
    content = content[:m4_start] + m4_patched
    print("Patched MorseTopologyAlarm weights in Mode4")
elif new_alarm.split("=", 2)[2] in m4_region:
    print("MorseTopologyAlarm weights already patched")
else:
    print("WARNING: Could not find MorseTopologyAlarm init in Mode4")

# 2b: Replace FusedSystemScorer with _Mode4FusedScorer
old_fused = "self.fused_scorer = FusedSystemScorer(k=k_neighbors) if use_fused else None"
new_fused = "self.fused_scorer = _Mode4FusedScorer(k=k_neighbors) if use_fused else None"

m4_start = content.index('class Mode4GravityEngine:')
m4_region = content[m4_start:]
if old_fused in m4_region:
    m4_patched = m4_region.replace(old_fused, new_fused, 1)
    content = content[:m4_start] + m4_patched
    print("Patched FusedSystemScorer -> _Mode4FusedScorer in Mode4")
elif new_fused in m4_region:
    print("FusedSystemScorer already patched")
else:
    print("WARNING: Could not find FusedSystemScorer init in Mode4")

# ── Write ──
with open(FILE, 'w', encoding='utf-8') as f:
    f.write(content)

line_count = content.count('\n') + 1
print(f"\nFile written: {line_count} lines")

# Verify
assert '_Mode4FusedScorer' in content
assert '_Mode4FusedScorer(k=k_neighbors)' in content
assert 'weights=np.array([0.35, 0.30, 0.20, 0.15])' in content
print("All assertions passed.")
