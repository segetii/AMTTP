import json, numpy as np

c = json.load(open('udl/combo_search_final.json'))
print("=== COMBO SEARCH (Fisher AUC, sorted by mean) ===")
ranked = sorted(c.items(), key=lambda x: x[1]['mean'], reverse=True)
for name, v in ranked[:15]:
    pd = v['per_ds']
    ops = v['n_ops']
    m = pd['mammography']
    s = pd['shuttle']
    p = pd['pendigits']
    mn = v['mean']
    print(f"  {name:40s} mamm={m:.4f} shut={s:.4f} pen={p:.4f} mean={mn:.4f} ops={ops}")

# Also check hybrid_rl_results for coverage
print("\n=== HYBRID/RL RESULTS (Coverage) ===")
h = json.load(open('udl/hybrid_rl_results.json'))
for ds_name, methods in h.items():
    print(f"\n  {ds_name}:")
    for method, vals in methods.items():
        print(f"    {method:18s} AUC={vals['auc']:.4f} Cov={vals['cov']*100:.0f}%")

# validation_5seed
print("\n=== 5-SEED VALIDATION (Coverage) ===")  
v = json.load(open('udl/validation_5seed.json'))
for ds_name, data in v.items():
    fisher_cov = np.mean(data['fisher_cov'])
    fuse_cov = np.mean(data['fuse_cov'])
    print(f"  {ds_name:15s} Fisher={fisher_cov*100:.0f}% Fuse={fuse_cov*100:.0f}%")
