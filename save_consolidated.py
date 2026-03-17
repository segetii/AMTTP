"""Save consolidated results JSON from all 3 benchmark simulations."""
import json
from datetime import datetime

regions = ['Full G-SIB Panel', 'USA (FDIC)', 'Europe + UK', 'Asia (JP + CN)', 'Nigeria (WB-GFDD)']

def extract_operational(rdata):
    """Extract operational configs from a region's data (Sim1/Sim2 format)."""
    ops = []
    for cfg_name, cfg_data in rdata.items():
        if not isinstance(cfg_data, dict):
            continue
        all_ch = cfg_data.get('all_channels', {})
        for ch_name, ch_data in all_ch.items():
            if not isinstance(ch_data, dict):
                continue
            f1 = ch_data.get('f1', 0)
            rec = ch_data.get('recall', 0)
            prec = ch_data.get('prec', 0)
            far = ch_data.get('far', 100)
            gfc = ch_data.get('auroc_gfc', 0)
            auroc = ch_data.get('auroc', 0)
            lead = ch_data.get('gfc_lead', '?')
            first_a = ch_data.get('first_alarm', '?')
            op = (f1 >= 40 and rec >= 50 and prec >= 30 and far < 25
                  and auroc >= 0.65 and gfc >= 0.80
                  and first_a is not None and str(first_a) <= '2007-09-30')
            ops.append({
                'config': cfg_name, 'channel': ch_name,
                'f1': round(f1, 1), 'recall': round(rec, 1),
                'precision': round(prec, 1), 'far': round(far, 1),
                'auroc': round(auroc, 3), 'auroc_gfc': round(gfc, 3),
                'gfc_lead': lead, 'first_alarm': first_a,
                'operational': op,
            })
    return ops

# Load all source data
sim1 = json.load(open('operational_model_search.json'))
sim2_orig = json.load(open('international_bank_benchmark.json'))
sim2_ext = json.load(open('international_bank_benchmark_extended.json'))
sim3_ops = json.load(open('model_artifacts/betti_morse_foundation/operational_configs.json'))
sim3_full = json.load(open('operational_betti_morse_search.json'))

consolidated = {
    'generated': datetime.now().isoformat(),
    'simulations': {
        'sim1_operational_sweep': {
            'script': 'bench_operational.py',
            'description': 'Comprehensive operational sweep: ReducedTensor, BSDT, FusedSystem, MDN variants',
            'total_configs': 41,
            'total_runs': 205,
            'regions': {}
        },
        'sim2_international_banks': {
            'script': 'bench_international_banks.py',
            'description': 'Standalone physics engines: Molecular, Gravity, Hybrid, ReducedTensor, MDN_Tensor, QuadSurf',
            'total_configs': 6,
            'total_runs': 30,
            'note': 'All engines returned F1=0 as standalone implementations; component methods were later successfully integrated into Sim1 and Sim3',
            'regions': {}
        },
        'sim3_betti_morse_foundation': {
            'script': 'bench_betti_morse_foundation.py',
            'description': 'Betti+Morse topological foundation with enrichment layers',
            'total_configs': 25,
            'total_runs': 125,
            'regions': {}
        }
    },
    'cross_simulation_best': {},
    'method_families': {}
}

# Sim1
for reg in regions:
    all_results = extract_operational(sim1.get(reg, {}))
    ops = [r for r in all_results if r['operational']]
    ops.sort(key=lambda x: -x['f1'])
    consolidated['simulations']['sim1_operational_sweep']['regions'][reg] = {
        'total_tested': len(sim1.get(reg, {})),
        'operational_count': len(ops),
        'operational_configs': ops,
        'best': ops[0] if ops else None,
    }

# Sim2
for reg in regions:
    orig_results = extract_operational(sim2_orig.get(reg, {}))
    ext_results = extract_operational(sim2_ext.get(reg, {}))
    all_results = orig_results + ext_results
    ops = [r for r in all_results if r['operational']]
    consolidated['simulations']['sim2_international_banks']['regions'][reg] = {
        'total_tested': len(sim2_orig.get(reg, {})) + len(sim2_ext.get(reg, {})),
        'operational_count': len(ops),
        'operational_configs': ops,
        'best': ops[0] if ops else None,
        'note': 'All zeros — standalone engine implementations failed to produce valid anomaly scores'
    }

# Sim3
for reg in regions:
    reg_ops = sorted([o for o in sim3_ops if o['region'] == reg], key=lambda x: -x['f1'])
    consolidated['simulations']['sim3_betti_morse_foundation']['regions'][reg] = {
        'total_tested': len(sim3_full.get(reg, {})),
        'operational_count': len(reg_ops),
        'operational_configs': reg_ops,
        'best': reg_ops[0] if reg_ops else None,
    }

# Cross-simulation best
for reg in regions:
    best_list = []
    for sim_key, sim_data in consolidated['simulations'].items():
        b = sim_data['regions'][reg].get('best')
        if b:
            entry = dict(b)
            entry['simulation'] = sim_key
            best_list.append(entry)
    best_list.sort(key=lambda x: -x.get('f1', 0))
    consolidated['cross_simulation_best'][reg] = {
        'overall_best': best_list[0] if best_list else None,
        'by_simulation': best_list,
    }

# Save
with open('benchmark_results_consolidated.json', 'w') as f:
    json.dump(consolidated, f, indent=2, default=str)

print('Saved benchmark_results_consolidated.json')
total_ops = sum(
    sim_data['regions'][reg]['operational_count']
    for sim_data in consolidated['simulations'].values()
    for reg in regions
)
print(f'Total operational configs across all sims: {total_ops}')
