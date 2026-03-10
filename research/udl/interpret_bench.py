"""Detailed diagnostic benchmark: interpret what each variant sees."""
import sys, json
sys.path.insert(0, 'udl')
from system_mode import BSDTChannels, ReducedTensorDescriptor
import numpy as np

rng = np.random.RandomState(42)
CHANNEL_NAMES = ['delta_C (Curvature)', 'delta_G (Gradient)', 
                 'delta_A (Anisotropy)', 'delta_T (Temporal)']

for name, n_ref, n_anom, d, shift in [
    ('ERCOT (Energy Market)', 200, 50, 8, 2.5),
    ('Bank (Financial Crisis)', 150, 30, 6, 2.0),
]:
    print('=' * 70)
    print(name)
    print('=' * 70)
    
    X_ref = rng.randn(n_ref, d) * 0.5
    X_anom = rng.randn(n_anom, d) * 0.5 + shift
    X = np.vstack([X_ref, X_anom])
    y = np.array([0]*n_ref + [1]*n_anom)

    # Fit BSDT and get channel-level insight
    bsdt = BSDTChannels(k=10)
    bsdt.fit(X_ref)
    
    # Channel values for normal vs anomalous
    ch_ref = bsdt.channels(X_ref)
    ch_anom = bsdt.channels(X_anom)
    
    print('\n--- CHANNEL-LEVEL ANALYSIS ---')
    for i, cname in enumerate(CHANNEL_NAMES):
        keys = ['delta_C', 'delta_G', 'delta_A', 'delta_T']
        k = keys[i]
        mu_n = ch_ref[k].mean()
        mu_a = ch_anom[k].mean()
        ratio = mu_a / max(mu_n, 1e-10)
        print('  %s:' % cname)
        print('    Normal mean:  %.4f  |  Crash mean:  %.4f  |  Ratio: %.1fx' % (mu_n, mu_a, ratio))

    # Energy and MFLS
    e_ref = bsdt.energy(X_ref)
    e_anom = bsdt.energy(X_anom)
    m_ref = bsdt.mfls(X_ref)
    m_anom = bsdt.mfls(X_anom)
    print('\n--- ENERGY & MFLS ---')
    print('  E_BS:  Normal=%.4f   Crash=%.4f   (%.1fx)' % (e_ref.mean(), e_anom.mean(), e_anom.mean()/max(e_ref.mean(),1e-10)))
    print('  MFLS:  Normal=%.4f   Crash=%.4f   (%.1fx)' % (m_ref.mean(), m_anom.mean(), m_anom.mean()/max(m_ref.mean(),1e-10)))

    # Fisher weights
    bsdt.fit_quadsurf(X_ref)
    fw = bsdt._qs_weights
    fs = bsdt._qs_signs
    print('\n--- FISHER VARIANCE-RATIO WEIGHTS (from reference data) ---')
    for i, cname in enumerate(CHANNEL_NAMES):
        sign_str = '+' if fs[i] > 0 else '-'
        bar = '#' * int(fw[i] * 40)
        print('  %s%s  w=%.3f  %s' % (sign_str, cname, fw[i], bar))

    # Signed Fisher beta
    bsdt.fit_signed_lr(X)
    beta = bsdt._lr_beta
    print('\n--- SIGNED FISHER WEIGHTS (transductive, from full data) ---')
    print('  Bias: %.3f' % beta[0])
    for i, cname in enumerate(CHANNEL_NAMES):
        sign_str = '+' if beta[i+1] > 0 else '-'
        bar = '#' * int(abs(beta[i+1]) * 20)
        print('  %s%s  beta=%.3f  %s' % (sign_str, cname, beta[i+1], bar))

    # Score distributions
    desc = ReducedTensorDescriptor(k_neighbors=10)
    desc.fit(X_ref)
    r = desc.score_variants(X, y, X_ref=X_ref)
    
    print('\n--- VARIANT SCORES (mean +/- std) ---')
    print('  %-12s  %-20s  %-20s  AUROC' % ('Variant', 'Normal', 'Crash'))
    for vname in ['baseline', 'full_bsdt', 'quadsurf', 'signed_lr', 'expo_gate']:
        s = r[vname]['scores']
        s_n = s[y==0]
        s_a = s[y==1]
        auroc = r[vname]['auroc']
        sep = s_a.min() - s_n.max()
        sep_str = '  [SEPARATED]' if sep > 0 else '  [overlap=%.3f]' % abs(sep)
        print('  %-12s  %.4f +/- %.4f      %.4f +/- %.4f      %.4f%s' % (
            vname, s_n.mean(), s_n.std(), s_a.mean(), s_a.std(), auroc, sep_str))

    # Did it spot the crash?
    print('\n--- CRASH DETECTION VERDICT ---')
    n_normal = (y == 0).sum()
    n_anom_actual = (y == 1).sum()
    for vname in ['baseline', 'full_bsdt', 'quadsurf', 'signed_lr', 'expo_gate']:
        s = r[vname]['scores']
        auroc = r[vname]['auroc']
        # Use 95th percentile of normal scores as threshold
        thresh = np.percentile(s[y==0], 95)
        detected = (s[y==1] > thresh).sum()
        pct = 100.0 * detected / n_anom_actual
        print('  %-12s: %d/%d anomalies detected (%.0f%%) at 5%% FAR, AUROC=%.4f' % (
            vname, detected, n_anom_actual, pct, auroc))
    
    print()
