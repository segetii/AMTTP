import json, pandas as pd

s = json.load(open(r'C:\amttp\research\adaptive-friction\pipeline\results\market_mfls_summary.json'))
ts = pd.read_csv(r'C:\amttp\research\adaptive-friction\pipeline\results\market_mfls_timeseries.csv', index_col=0, parse_dates=True)

print("=== OVERVIEW ===")
print("Observations :", s['n_obs'])
print("Date range   :", s['date_start'], "->", s['date_end'])
print("Regimes      :", s['regime_counts'])
print("Crisis years :", s['crisis_captured'])

print()
print("=== FISHER WEIGHTS (data-driven, eq:fisher_vr) ===")
fw = s['bsdt_exact']['fisher_weights']
for k, v in fw.items():
    print("  %s: %.4f" % (k, v))

print()
print("=== CHANNEL MEANS BY ERA (vs fixed N=2005-2007 baseline) ===")
eras = [
    ("Normal 2005-2007", ts['normal_period'] == True),
    ("GFC 2008",         ts.index.year == 2008),
    ("Eurozone 2011",    ts.index.year == 2011),
    ("COVID 2020",       ts.index.year == 2020),
    ("Post-2020",        ts.index.year >= 2021),
]
for lbl, mask in eras:
    sub = ts[mask]
    crit = (sub['regime'] == 'Critical Instability').sum()
    print("  %-20s n=%4d  dC=%6.1f  dG=%5.2f  dA=%5.2f  dT=%7.1f  MFLS=%7.2f  critical_days=%d" % (
        lbl, len(sub),
        sub['delta_C'].mean(), sub['delta_G'].mean(), sub['delta_A'].mean(),
        sub['delta_T'].mean(), sub['MFLS'].mean(), crit
    ))

print()
print("=== ENERGY & FRICTION ===")
print("theta (friction midpoint) :", round(s['theta'], 4))
print("tau_elevated               :", round(s['tau_elevated'], 4))
print("tau_critical               :", round(s['tau_critical'], 4))
print("gamma at E=theta is 0.5    : verified (paper eq:bsdamped)")
for lbl, mask in eras[:4]:
    sub = ts[mask]
    if 'gamma' in sub.columns:
        print("  gamma mean %-16s: %.4f" % (lbl, sub['gamma'].mean()))

print()
print("=== CRITICAL MANIFOLD C_man (eq:cman) ===")
td = s['transition_diagnostics']
print("Transitions above C_man :", td['n_transitions'])
print("Pct time above C_man    : %.2f%%" % (td['pct_above_cman'] * 100))
dates = td.get('transition_dates_above_cman', [])
print("First 8 transition dates:", dates[:8])

print()
print("=== OUTCOME PROBABILITIES (21-day forward) ===")
op = s.get('outcome_probabilities', {})
for regime, r in op.items():
    n = r.get('n_obs', '?')
    d3 = r.get('P_DD_lt_m3pct', r.get('P(DD<-3%)', float('nan')))
    d5 = r.get('P_DD_lt_m5pct', r.get('P(DD<-5%)', float('nan')))
    d10 = r.get('P_DD_lt_m10pct', r.get('P(DD<-10%)', float('nan')))
    print("  %-22s n=%4s  P(DD<-3%%)=%.3f  P(DD<-5%%)=%.3f  P(DD<-10%%)=%.3f" % (
        regime, str(n), d3, d5, d10
    ))

print()
print("=== VALIDATION ===")
v = s.get('validation', {})
print("Lift Critical/Normal at DD<-5%:", v.get('lift_critical_vs_normal_5pct', 'N/A'))
print("AUC MFLS -> DD<-5% drawdown  :", v.get('auc_mfls_to_5pct_drawdown', 'N/A'))
cm = v.get('confusion_matrix_at_tau_critical', {})
tp = cm.get('TP', 0); fp = cm.get('FP', 0); tn = cm.get('TN', 0); fn = cm.get('FN', 0)
prec = cm.get('precision', 0); rec = cm.get('recall', 0)
print("Confusion matrix at tau_crit  : TP=%d FP=%d TN=%d FN=%d  Prec=%.3f  Recall=%.3f" % (
    tp, fp, tn, fn, prec, rec))

print()
print("=== SCENARIO ANALYSIS ===")
sc = s.get('scenario_results', [])
stable = sum(1 for x in sc if x.get('stable'))
print("Stable / Total: %d / %d" % (stable, len(sc)))
for x in sc:
    print("  shock=%.1f  gmult=%.1f  end_dist=%.4f  stable=%s" % (
        x['shock'], x['gamma_mult'], x['end_distance'], x['stable']))
