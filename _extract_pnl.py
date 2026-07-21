import json, os

def best_from(d):
    if 'performance' in d:
        p = d['performance']
        if isinstance(p, dict):
            vals = list(p.values())
            cands = [r for r in vals if isinstance(r, dict) and 'final' in r]
            if cands: return max(cands, key=lambda r: r['final'])
    for key in ['execution_results', 'rows']:
        if key in d:
            rows = d[key]
            if isinstance(rows, list):
                cands = [r for r in rows if isinstance(r, dict) and 'final' in r]
                if cands: return max(cands, key=lambda r: r['final'])
    if 'champions' in d:
        champs = d['champions']
        if isinstance(champs, list) and champs and isinstance(champs[0], dict) and 'final' in champs[0]:
            return max(champs, key=lambda r: r['final'])
    if 'metrics' in d and isinstance(d['metrics'], dict) and 'final' in d['metrics']:
        return d['metrics']
    if 'summary' in d and isinstance(d['summary'], dict) and 'final' in d['summary']:
        return d['summary']
    if 'equity' in d and isinstance(d['equity'], dict):
        cands = [r for r in d['equity'].values() if isinstance(r, dict) and 'final' in r]
        if cands: return max(cands, key=lambda r: r.get('final', 0))
    if 'best_by_oos_calmar' in d and isinstance(d['best_by_oos_calmar'], dict) and 'final' in d['best_by_oos_calmar']:
        return d['best_by_oos_calmar']
    return None

base = r"C:\amttp\research\adaptive-friction\pipeline\results"

files = [
  ("v1",   "crypto_godmode_v1.json"),
  ("v2",   "crypto_godmode_v2.json"),
  ("v3",   "crypto_godmode_v3_alarm_safe.json"),
  ("v4",   "crypto_godmode_v4_bsignal.json"),
  ("v5",   "crypto_godmode_v5_regime_bsignal.json"),
  ("v6",   "crypto_godmode_v6_angular.json"),
  ("v7",   "crypto_godmode_v7_exec_shell.json"),
  ("v8",   "crypto_godmode_v8_multiasset_shell.json"),
  ("v9",   "crypto_godmode_v9_multiasset_tune.json"),
  ("v10",  "crypto_godmode_v10_cluster.json"),
  ("v10b", "crypto_godmode_v10b_trade_mining.json"),
  ("v11",  "crypto_godmode_v11_lossfix.json"),
  ("v12",  "crypto_godmode_v12_filter_innovate.json"),
  ("v13",  "crypto_godmode_v13_k_sweep.json"),
  ("v14",  "crypto_godmode_v14_k15_sweep.json"),
  ("v15",  "crypto_godmode_v15_cost_backtest.json"),
  ("v16",  "crypto_godmode_v16_plots.json"),
  ("v17",  "crypto_godmode_v17_period_report.json"),
  ("v18",  "crypto_godmode_v18_cb_fix.json"),
  ("v19",  "crypto_godmode_v19_cb_reset.json"),
  ("v20",  "crypto_godmode_v20_cb_window.json"),
  ("v21",  "crypto_godmode_v21_cb_decay.json"),
  ("v22",  "crypto_godmode_v22_directional_cb.json"),
  ("v23",  "crypto_godmode_v23_regime_cb.json"),
  ("v24",  "crypto_godmode_v24_perdirection_cb.json"),
  ("v25",  r"v25_microstructure\crypto_godmode_v25_microstructure.json"),
  ("v26",  r"v26_extended\crypto_godmode_v26_extended.json"),
  ("v27",  r"v27_all_microstructure\crypto_godmode_v27_all_microstructure.json"),
  ("v28",  r"v28_canonical_stability\crypto_godmode_v28_canonical_stability.json"),
  ("v29",  r"v29_regularized_validation\crypto_godmode_v29_regularized_validation.json"),
  ("v30",  r"v30_fractional_ricci\crypto_godmode_v30_fractional_ricci.json"),
  ("v31",  r"v31_disturbance_budget\crypto_godmode_v31_disturbance_budget.json"),
  ("v32",  r"v32_true_fractional\crypto_godmode_v32_true_fractional.json"),
  ("v33",  r"v33_cb_fix\crypto_godmode_v33_cb_fix.json"),
  ("v34",  r"v34_cb_resume_fix\crypto_godmode_v34_cb_resume_fix.json"),
  ("v35",  r"v35_top5_cb_transition\crypto_godmode_v35_top5_cb_transition.json"),
]

for tag, fname in files:
    path = os.path.join(base, fname)
    if not os.path.exists(path):
        print(f"{tag}: MISSING {fname}")
        continue
    d = json.load(open(path, encoding="utf-8"))
    # v25+ use 'results' key directly
    if 'results' in d and isinstance(d['results'], list) and d['results']:
        cands = [r for r in d['results'] if isinstance(r, dict) and r.get('final')]
        if cands:
            r = max(cands, key=lambda r: r['final'])
            calmar = r.get('calmar', 0)
            name = r.get('name', r.get('variant', '?'))
            print(f"{tag}: final=${r['final']:>10,.0f}  calmar={calmar:6.2f}  name={name}")
            continue
    r = best_from(d)
    if r:
        calmar = r.get('calmar', r.get('oos_calmar', 0))
        name = r.get('name', r.get('variant', '?'))
        print(f"{tag}: final=${r.get('final', 0):>10,.0f}  calmar={calmar:6.2f}  name={name}")
    else:
        print(f"{tag}: UNHANDLED keys={list(d.keys())[:8]}")
