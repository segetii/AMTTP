import json
d = json.loads(open(r'c:\amttp\papers\bsdt_cross_domain_results.json').read())
for key, v in d['datasets'].items():
    ds = v['dataset']
    bl = v['baseline']
    cf = v['correction_fixed']
    cm = v['correction_mi']
    cv = v['correction_vr']
    pp = v['predictive_power']
    orth = v['orthogonality']
    
    print(f'--- {ds} ---')
    print(f'  Samples: {v["total_samples"]}, Fraud: {v["total_fraud"]}, Rate: {v["fraud_rate"]*100:.2f}%')
    print(f'  Baseline: recall={bl["recall"]:.3f}, prec={bl["precision"]:.3f}, f1={bl["f1"]:.3f}')
    print(f'  Fixed:    recall={cf["recall"]:.3f}, prec={cf["precision"]:.3f}, f1={cf["f1"]:.3f}')
    print(f'  MI:       recall={cm["recall"]:.3f}, prec={cm["precision"]:.3f}, f1={cm["f1"]:.3f}')
    print(f'  VR:       recall={cv["recall"]:.3f}, prec={cv["precision"]:.3f}, f1={cv["f1"]:.3f}')
    print(f'  Delta: +{v["recall_improvement_pp"]}pp, MFLS AUC: {pp["combined_auc"]:.3f}')
    print(f'  Active: {orth["active_components"]}, |r|={orth["mean_abs_pearson"]:.3f}, nMI={orth["normalised_MI_mean"]:.3f}')
    print()
