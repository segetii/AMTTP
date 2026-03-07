import json, numpy as np

with open('results/full_benchmark_checkpoint.json') as f:
    data = json.load(f)

datasets = ['mammography','pendigits','annthyroid','arrhythmia','satellite','glass','cardio']
ds_short  = ['mammo','pendig','annthy','arrhyt','satell','glass','cardio']

groups = [
    ('Lean 5-op',  ['Fisher-lean','Fuse-lean','QuadSurf-lean','MetaFusion','MetaFusion+','Hybrid-lean']),
    ('QDA',        ['QDA-lean','QDA-Mag-lean']),
    ('BSDT',       ['BSDT-Fisher','BSDT-Fuse','BSDT-Hybrid']),
    ('CombA',      ['CombA-Fisher','CombA-Fuse','CombA-Hybrid','CombA-QDA-Mag']),
    ('Old 4-op',   ['Fisher-4op','Fuse-4op','Hybrid-4op']),
]

hdr = '  {:<18s}'.format('Method')
for s in ds_short:
    hdr += '  {:>7s}'.format(s)
hdr += '  {:>7s}'.format('mAUC')
print(hdr)
print('  ' + '-'*(len(hdr)-2))

for gname, methods in groups:
    print('  -- {} --'.format(gname))
    for m in methods:
        row = '  {:<18s}'.format(m)
        aucs = []
        for d in datasets:
            auc = (data.get(d,{}).get(m,{}).get('auc') or 0.0)
            row += '  {:>7.4f}'.format(auc)
            aucs.append(auc)
        row += '  {:>7.4f}'.format(np.mean(aucs))
        print(row)
