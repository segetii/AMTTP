import json
regions = ['Full G-SIB Panel', 'USA (FDIC)', 'Europe + UK', 'Asia (JP + CN)', 'Nigeria (WB-GFDD)']
for fname, label in [('international_bank_benchmark.json', 'OrigEng'),
                     ('international_bank_benchmark_extended.json', 'ExtEng')]:
    d = json.load(open(fname))
    print(f'=== {label} ===')
    for reg in regions:
        rdata = d.get(reg, {})
        for cfg, cdata in rdata.items():
            if isinstance(cdata, dict):
                best = cdata.get('best', {})
                ch = cdata.get('best_channel', '?')
                f1 = best.get('f1', 0)
                rec = best.get('recall', 0)
                prec = best.get('prec', 0)
                far = best.get('far', 100)
                gfc = best.get('auroc_gfc', 0)
                auroc = best.get('auroc', 0)
                lead = best.get('gfc_lead', '?')
                first_a = best.get('first_alarm', '?')
                op_flag = cdata.get('operational', False)
                print(f'  {reg}: {cfg} ({ch}) F1={f1:.1f} R={rec:.1f}% '
                      f'P={prec:.1f}% FAR={far:.1f}% GFC={gfc:.3f} '
                      f'AUROC={auroc:.3f} Lead={lead} 1stAlarm={first_a} Op={op_flag}')
    print()
