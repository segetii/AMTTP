"""Patch: Fix _reference_score calls in conformal methods to pass X_ref."""
import os, sys

FP = os.path.join(os.path.dirname(__file__), 'udl', 'system_mode.py')
with open(FP, encoding='utf-8') as f:
    content = f.read()

# Fix 1: In fit_reference — store X_fit and pass it as X_ref
content = content.replace(
    '''        # Fit descriptor on the fit set
        self.fit(X_fit)

        # Store calibration data
        self._cal_X = X_cal
        self._cal_N = n_cal

        # Compute descriptor features on calibration set
        D_cal = self.transform(X_cal)
        self._cal_features = D_cal

        # ── Multi-view nonconformity scores on calibration set ──
        # Use the proven _reference_score pipeline:
        #   40% raw-kNN + 30% desc-kNN + 30% topology
        self._cal_nonconf = self._reference_score(X_cal)''',
    '''        # Fit descriptor on the fit set
        self.fit(X_fit)

        # Store calibration and fit data
        self._cal_X = X_cal
        self._fit_X = X_fit      # reference distribution for scoring
        self._cal_N = n_cal

        # Compute descriptor features on calibration set
        D_cal = self.transform(X_cal)
        self._cal_features = D_cal

        # ── Multi-view nonconformity scores on calibration set ──
        # Use the proven _reference_score pipeline:
        #   40% raw-kNN + 30% desc-kNN + 30% topology
        self._cal_nonconf = self._reference_score(X_cal, self._fit_X)'''
)

# Fix 2: In score_conformal — pass _fit_X as X_ref
content = content.replace(
    '''        # ── View 1: Multi-view geometric scoring (proven pipeline) ──
        view1 = self._reference_score(X)''',
    '''        # ── View 1: Multi-view geometric scoring (proven pipeline) ──
        view1 = self._reference_score(X, self._fit_X)'''
)

# Fix 3: In predict_pvalue — pass _fit_X as X_ref
content = content.replace(
    '''        # Nonconformity score via multi-view geometric pipeline
        A_test = self._reference_score(X)''',
    '''        # Nonconformity score via multi-view geometric pipeline
        A_test = self._reference_score(X, self._fit_X)'''
)

# Fix 4: In score_conformal_panel — pass fit ref data
content = content.replace(
    '''        # ── Multi-view geometric scores for all points ──
        ref_scores = self._reference_score(X_flat)   # (T*N,)''',
    '''        # ── Multi-view geometric scores for all points ──
        ref_scores = self._reference_score(X_flat, self._fit_X)   # (T*N,)'''
)

with open(FP, 'w', encoding='utf-8') as f:
    f.write(content)

# Verify all references now pass two args
import re
calls = re.findall(r'self\._reference_score\([^)]+\)', content)
for c in calls:
    print(f'  {c}')
bad = [c for c in calls if c.count(',') < 1 and 'X_ref' not in c]
if bad:
    print(f'WARNING: {len(bad)} calls still missing X_ref: {bad}')
else:
    print('All _reference_score calls now pass X_ref. OK.')
