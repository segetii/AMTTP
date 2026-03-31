import json

regions = ['Full G-SIB Panel', 'USA (FDIC)', 'Europe + UK', 'Asia (JP + CN)', 'Nigeria (WB-GFDD)']

for fname, label in [('operational_model_search.json', 'Sim1-OpSweep'),
                     ('international_bank_benchmark.json', 'Sim2-OrigEng'),
                     ('international_bank_benchmark_extended.json', 'Sim2-ExtEng')]:
    d = json.load(open(fname))
    total_ops = 0
    for reg in regions:
        rdata = d.get(reg, {})
        for cfg_name, cfg_data in rdata.items():
            if isinstance(cfg_data, dict) and cfg_data.get('operational', False):
                total_ops += 1
                best = cfg_data.get('best', {})
                f1 = best.get('f1', 0)
                gfc = best.get('auroc_gfc', 0)
                rec = best.get('recall', 0)
                prec = best.get('prec', 0)
                far = best.get('far', 100)
                ch = cfg_data.get('best_channel', '?')
                lead = best.get('gfc_lead', '?')
                print(f'  [{label}] {reg}: {cfg_name} ({ch}) '
                      f'F1={f1:.1f} R={rec:.1f}% P={prec:.1f}% '
                      f'FAR={far:.1f}% GFC={gfc:.3f} Lead={lead}')
    print(f'{label}: {total_ops} operational total\n')

# Also check all_channels for operational ones
print("=== Checking per-channel operational (Sim1) ===")
d = json.load(open('operational_model_search.json'))
for reg in regions:
    rdata = d.get(reg, {})
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
            # Check operational criteria
            op = (f1 >= 40 and rec >= 50 and prec >= 30 and far < 25
                  and auroc >= 0.65 and gfc >= 0.80
                  and first_a is not None and str(first_a) <= '2007-09-30')
            if op:
                ops.append({
                    'config': cfg_name, 'channel': ch_name,
                    'f1': f1, 'recall': rec, 'prec': prec,
                    'far': far, 'auroc_gfc': gfc, 'gfc_lead': lead,
                })
    ops.sort(key=lambda x: -x['f1'])
    print(f'\n  {reg}: {len(ops)} operationally viable')
    for o in ops[:10]:
        print(f"    {o['config']:30s} ({o['channel']:12s}) "
              f"F1={o['f1']:5.1f}  R={o['recall']:5.1f}%  P={o['prec']:5.1f}%  "
              f"FAR={o['far']:5.1f}%  GFC={o['auroc_gfc']:.3f}  Lead={o['gfc_lead']}")

# Same for Sim2 files
for fname, label in [('international_bank_benchmark.json', 'Sim2-OrigEng'),
                     ('international_bank_benchmark_extended.json', 'Sim2-ExtEng')]:
    print(f"\n=== Checking per-channel operational ({label}) ===")
    d = json.load(open(fname))
    for reg in regions:
        rdata = d.get(reg, {})
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
                if op:
                    ops.append({
                        'config': cfg_name, 'channel': ch_name,
                        'f1': f1, 'recall': rec, 'prec': prec,
                        'far': far, 'auroc_gfc': gfc, 'gfc_lead': lead,
                    })
        ops.sort(key=lambda x: -x['f1'])
        print(f'\n  {reg}: {len(ops)} operationally viable')
        for o in ops[:5]:
            print(f"    {o['config']:30s} ({o['channel']:12s}) "
                  f"F1={o['f1']:5.1f}  R={o['recall']:5.1f}%  P={o['prec']:5.1f}%  "
                  f"FAR={o['far']:5.1f}%  GFC={o['auroc_gfc']:.3f}  Lead={o['gfc_lead']}")

# Sim 3: already have the operational_configs.json
print("\n=== SIMULATION 3 (Betti+Morse) — from operational_configs.json ===")
with open('model_artifacts/betti_morse_foundation/operational_configs.json') as f:
    sim3_ops = json.load(f)
for reg in regions:
    reg_ops = sorted([o for o in sim3_ops if o['region'] == reg], key=lambda x: -x['f1'])
    print(f'\n  {reg}: {len(reg_ops)} operationally viable')
    for o in reg_ops[:5]:
        print(f"    {o['config']:30s} ({o['channel']:12s}) "
              f"F1={o['f1']:5.1f}  R={o['recall']:5.1f}%  P={o['prec']:5.1f}%  "
              f"FAR={o['far']:5.1f}%  GFC={o['auroc_gfc']:.3f}  Lead={o['gfc_lead']}")
