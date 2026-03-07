import json
import sys

with open('c:/amttp/research/udl/results/full_benchmark_checkpoint.json') as f:
    prev = json.load(f)

# Structure: {dataset: {method: {auc: ..., ...}}}
datasets = ['mammography','pendigits','annthyroid','arrhythmia','satellite','glass','cardio']

# Collect all methods
all_methods = set()
for ds in datasets:
    if ds in prev:
        all_methods.update(prev[ds].keys())

method_aucs = {}
for method in all_methods:
    aucs = []
    for d in datasets:
        if d in prev and method in prev[d]:
            aucs.append(prev[d][method]['auc'])
    if len(aucs) == 7:
        method_aucs[method] = sum(aucs)/7

print("TOP 10 PREVIOUS METHODS:")
print(f"{'Method':35s}  {'mammo':>8s}  {'pendig':>8s}  {'annthy':>8s}  {'arrhyt':>8s}  {'satell':>8s}  {'glass':>8s}  {'cardio':>8s}  {'mAUC':>8s}")
print("-"*120)
for method, mauc in sorted(method_aucs.items(), key=lambda x: -x[1])[:10]:
    vals = [prev[d][method]['auc'] if d in prev and method in prev[d] else 0 for d in datasets]
    print(f'{method:35s}  ' + '  '.join(f'{v:8.4f}' for v in vals) + f'  {mauc:8.4f}')

print()
print("NEW SUBSPACE SCAN METHODS:")
with open('c:/amttp/research/udl/src/results/subspace_scan_results.json') as f:
    new = json.load(f)

new_methods = set()
for ds_name, methods in new.items():
    for m in methods:
        new_methods.add(m)

print(f"{'Method':35s}  {'mammo':>8s}  {'pendig':>8s}  {'annthy':>8s}  {'arrhyt':>8s}  {'satell':>8s}  {'glass':>8s}  {'cardio':>8s}  {'mAUC':>8s}")
print("-"*120)
for method in sorted(new_methods):
    vals = [new[d].get(method, 0) for d in datasets]
    mauc = sum(vals)/7
    print(f'{method:35s}  ' + '  '.join(f'{v:8.4f}' for v in vals) + f'  {mauc:8.4f}')
