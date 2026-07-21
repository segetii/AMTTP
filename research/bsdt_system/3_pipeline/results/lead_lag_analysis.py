"""
Lead-lag correlation analysis: corr(MFLS_t, DD_{t+tau}) for tau in [-60, +60]
Also: cross-correlogram for E_BS, delta_T, delta_C, Omega (spectral_order)
And: multi-horizon outcome probabilities (21, 63, 126 days)
"""
import pandas as pd
import numpy as np

ts = pd.read_csv(
    r'C:\amttp\research\adaptive-friction\pipeline\results\market_mfls_timeseries.csv',
    index_col=0, parse_dates=True
)

# ── Build rolling max-drawdown for multiple horizons ──────────────────────────
price = ts['sp500']

def rolling_drawdown(price, h):
    """Max percentage drawdown over next h days."""
    fwd_max = price.rolling(h, min_periods=1).max().shift(-h)
    rolling_min = price[::-1].rolling(h, min_periods=1).min()[::-1].shift(-(h-1))
    # simpler: max loss from t over [t, t+h]
    dd = pd.Series(index=price.index, dtype=float)
    for i in range(len(price) - h):
        window = price.iloc[i:i+h]
        dd.iloc[i] = (window.min() - price.iloc[i]) / price.iloc[i]
    return dd

print("Computing drawdown horizons...")
for h in [21, 63, 126]:
    col = "dd_fwd_%d" % h
    dd = pd.Series(index=price.index, dtype=float)
    arr = price.values
    for i in range(len(arr) - h):
        window = arr[i:i+h]
        dd.iloc[i] = (window.min() - arr[i]) / arr[i]
    ts[col] = dd
    print("  dd_fwd_%d computed" % h)

# ── Lead-lag cross-correlation ─────────────────────────────────────────────────
signals = {
    'MFLS':        ts['MFLS'],
    'E_BS':        ts['E_BS'],
    'delta_T':     ts['delta_T'],
    'delta_C':     ts['delta_C'],
    'spectral_Omega': ts['spectral_order'],
}

taus = range(-60, 61)
dd_col = 'dd_fwd_21'
dd = ts[dd_col].dropna()

print()
print("=" * 70)
print("LEAD-LAG CORRELATION: signal vs DD_{t+tau}  (tau -60 to +60)")
print("Negative tau = signal is AHEAD of drawdown (signal leads)")
print("=" * 70)

for sig_name, sig_raw in signals.items():
    corrs = []
    for tau in taus:
        shifted_dd = dd.shift(-tau)  # shift DD backward = check signal vs future DD
        both = pd.concat([sig_raw, shifted_dd], axis=1).dropna()
        if len(both) < 100:
            corrs.append(float('nan'))
            continue
        c = both.iloc[:,0].corr(both.iloc[:,1])
        corrs.append(c)
    corrs = np.array(corrs)
    peak_idx = np.nanargmin(corrs)   # most negative = strongest negative correlation
    peak_tau = list(taus)[peak_idx]
    peak_val = corrs[peak_idx]
    max_pos_idx = np.nanargmax(corrs)
    max_pos_tau = list(taus)[max_pos_idx]
    max_pos_val = corrs[max_pos_idx]

    print()
    print("Signal: %s" % sig_name)
    # Print correlation at key lags
    key_taus = [-60,-40,-21,-10,-5,0,5,10,21,40,60]
    for t in key_taus:
        idx = t + 60
        bar_len = int(abs(corrs[idx]) * 40)
        direction = "+" if corrs[idx] > 0 else "-"
        bar = direction * bar_len
        print("  tau=%+4d  corr=%+6.3f  |%s" % (t, corrs[idx], bar))
    print("  >> Peak NEGATIVE corr: tau=%+d  corr=%.4f  (%s)" % (
        peak_tau, peak_val,
        "SIGNAL LEADS by %d days" % abs(peak_tau) if peak_tau < 0 else
        "COINCIDENT" if peak_tau == 0 else
        "SIGNAL LAGS by %d days" % peak_tau
    ))

# ── Multi-horizon outcome probabilities ──────────────────────────────────────
print()
print("=" * 70)
print("OUTCOME PROBABILITIES BY REGIME x HORIZON")
print("=" * 70)
regimes = ['Critical Instability', 'Elevated Risk', 'Normal']
thresholds = [-0.03, -0.05, -0.10]
horizons = [21, 63, 126]

for h in horizons:
    col = "dd_fwd_%d" % h
    print()
    print("Horizon: %d days" % h)
    print("  %-22s   %8s   %8s   %8s    n" % ("Regime","P(<-3%)","P(<-5%)","P(<-10%)"))
    for r in regimes:
        mask = ts['regime'] == r
        sub = ts.loc[mask, col].dropna()
        p3 = (sub < -0.03).mean()
        p5 = (sub < -0.05).mean()
        p10 = (sub < -0.10).mean()
        print("  %-22s   %8.3f   %8.3f   %8.3f    %d" % (r, p3, p5, p10, len(sub)))
    # Lift: critical vs normal at -5%
    crit_sub = ts.loc[ts['regime']=='Critical Instability', col].dropna()
    norm_sub = ts.loc[ts['regime']=='Normal', col].dropna()
    p5_crit = (crit_sub < -0.05).mean()
    p5_norm = (norm_sub < -0.05).mean()
    lift = p5_crit / p5_norm if p5_norm > 0 else float('nan')
    print("  >> Lift(Critical/Normal at -5%%): %.4f %s" % (
        lift, "<< INVERTED" if lift < 1.0 else "<< SIGNAL PREDICTS ✓"))

# ── Crisis alignment: MFLS vs drawdown around key events ─────────────────────
print()
print("=" * 70)
print("CRISIS ALIGNMENT: MFLS rank vs SP500 drawdown rank (normalized)")
print("=" * 70)
events = {
    'Pre-GFC lead-up (2007-Jan to 2007-Dec)':    ('2007-01-01','2007-12-31'),
    'GFC peak (2008-Jun to 2009-Mar)':            ('2008-06-01','2009-03-31'),
    'Eurozone crisis (2010-Jan to 2012-Dec)':     ('2010-01-01','2012-12-31'),
    'COVID crash (2020-Jan to 2020-Jun)':         ('2020-01-01','2020-06-30'),
    'COVID recovery (2020-Jul to 2021-Dec)':      ('2020-07-01','2021-12-31'),
}
for label, (start, end) in events.items():
    sub = ts[start:end].copy()
    if len(sub) < 20:
        continue
    mfls_peak_date = sub['MFLS'].idxmax()
    dd_col21 = 'dd_fwd_21'
    dd_trough_date  = sub['dd_fwd_21'].idxmin() if dd_col21 in sub else None
    delta_days = (dd_trough_date - mfls_peak_date).days if dd_trough_date else None
    print("  %-42s  MFLS_peak=%s  DD_worst=%s  delta=%s days" % (
        label,
        str(mfls_peak_date.date()),
        str(dd_trough_date.date()) if dd_trough_date else 'N/A',
        str(delta_days) if delta_days is not None else 'N/A'
    ))

print()
print("Done.")
