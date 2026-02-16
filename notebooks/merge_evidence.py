import json

# Load existing evidence and merge cross-domain results
ev = json.loads(open(r'c:\amttp\papers\bsdt_evidence.json').read())
cd = json.loads(open(r'c:\amttp\papers\bsdt_cross_domain_results.json').read())

# Add cross-domain results
ev['cross_domain'] = cd

# Update abstract numbers
ev['abstract_numbers']['n_datasets'] = 6
ev['abstract_numbers']['n_domains'] = 5
ev['abstract_numbers']['total_samples_all'] = (
    ev['abstract_numbers']['elliptic_n'] + 
    ev['abstract_numbers']['xblock_n'] + 
    sum(v['total_samples'] for v in cd['datasets'].values())
)
ev['abstract_numbers']['mean_mfls_auc_all_datasets'] = cd['summary']['mean_combined_auc']
ev['abstract_numbers']['cross_domain_datasets'] = list(cd['datasets'].keys())

with open(r'c:\amttp\papers\bsdt_evidence.json', 'w') as f:
    json.dump(ev, f, indent=2)

total = ev['abstract_numbers']['total_samples_all']
print(f'Evidence JSON updated with cross-domain results')
print(f'Total samples across all datasets: {total}')
print(f'Mean MFLS AUC: {cd["summary"]["mean_combined_auc"]:.3f}')
