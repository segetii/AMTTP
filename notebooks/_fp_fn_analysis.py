"""Deep FP/FN analysis of MFLS V2 results with fraud accounting."""
import json, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from pathlib import Path

RESULTS_PATH = Path(r'C:\Users\Administrator\Downloads\_results_analysis\results\mfls_variants_v2_results.json')
with open(RESULTS_PATH) as f:
    ALL = json.load(f)

# Top variants to analyze in detail
TOP_VARIANTS = ['F2_QuadSurf', 'B2_KDE_Sig', 'A9_kNNCorr', 'I7_StackedLR',
                'B6_GMM_Tanh', 'D3_IsoCorr', 'J6_LOF_Pow_Corr', 'F5_QuadGrid']

print("=" * 140)
print("  DETAILED FP / FN / TP ANALYSIS — MFLS VARIANTS V2")
print("=" * 140)

# ── 1. Per-combo fraud accounting for base vs top variants ──
print("\n1. FRAUD ACCOUNTING: Total Fraud / Caught / Missed / FP / Accuracy / Misclassification Rate\n")

for r in ALL:
    ds, model, n, nf = r['dataset'], r['model'], r['n'], r['n_fraud']
    nl = n - nf  # legit count
    b = r['B0_Base']
    b_fn = nf - b['tp']
    b_tn = nl - b['fp']
    b_acc = (b['tp'] + b_tn) / n * 100
    b_mcr = (b['fp'] + b_fn) / n * 100
    b_fpr = b['fp'] / max(nl, 1) * 100
    b_fnr = b_fn / max(nf, 1) * 100

    print(f"\n{'─' * 140}")
    print(f"  {ds} | {model} | N={n:,} | Legit={nl:,} | Fraud={nf:,}")
    print(f"{'─' * 140}")
    print(f"  {'Method':<22} │ {'TotalFr':>7} {'Caught':>7} {'Missed':>7} │ {'TP':>6} {'FP':>6} {'TN':>6} {'FN':>6} │ {'Acc%':>7} {'MCR%':>7} {'FPR%':>7} {'FNR%':>7} {'F1':>7} │ {'ΔFP':>6} {'ΔFN':>6} {'ΔAcc':>7}")
    print(f"  {'─'*22}─┼─{'─'*7}─{'─'*7}─{'─'*7}─┼─{'─'*6}─{'─'*6}─{'─'*6}─{'─'*6}─┼─{'─'*7}─{'─'*7}─{'─'*7}─{'─'*7}─{'─'*7}─┼─{'─'*6}─{'─'*6}─{'─'*7}")

    # Base row
    print(f"  {'BASE MODEL':<22} │ {nf:>7,} {b['tp']:>7,} {b_fn:>7,} │ {b['tp']:>6,} {b['fp']:>6,} {b_tn:>6,} {b_fn:>6,} │ {b_acc:>7.2f} {b_mcr:>7.2f} {b_fpr:>7.2f} {b_fnr:>7.2f} {b['f1']:>7.4f} │ {'---':>6} {'---':>6} {'---':>7}")

    # Variant rows
    for vk in TOP_VARIANTS:
        v = r.get(vk)
        if not v or 'error' in v:
            continue
        v_fn = nf - v['tp']
        v_tn = nl - v['fp']
        v_acc = (v['tp'] + v_tn) / n * 100
        v_mcr = (v['fp'] + v_fn) / n * 100
        v_fpr = v['fp'] / max(nl, 1) * 100
        v_fnr = v_fn / max(nf, 1) * 100
        d_fp = v['fp'] - b['fp']
        d_fn = v_fn - b_fn
        d_acc = v_acc - b_acc
        fp_sign = '+' if d_fp > 0 else ''
        fn_sign = '+' if d_fn > 0 else ''
        acc_sign = '+' if d_acc > 0 else ''
        print(f"  {vk:<22} │ {nf:>7,} {v['tp']:>7,} {v_fn:>7,} │ {v['tp']:>6,} {v['fp']:>6,} {v_tn:>6,} {v_fn:>6,} │ {v_acc:>7.2f} {v_mcr:>7.2f} {v_fpr:>7.2f} {v_fnr:>7.2f} {v['f1']:>7.4f} │ {fp_sign}{d_fp:>5,} {fn_sign}{d_fn:>5,} {acc_sign}{d_acc:>6.2f}")

# ── 2. Aggregated FP/FN reduction across all 12 combos ──
print(f"\n\n{'=' * 140}")
print("2. AGGREGATE FP / FN REDUCTION (summed across all 12 combos)\n")

print(f"  {'Variant':<22} │ {'TotFraud':>8} {'TotCaught':>9} {'TotMissed':>9} │ {'SumTP':>7} {'SumFP':>7} {'SumFN':>7} │ {'ΔFP':>7} {'ΔFP%':>6} {'ΔFN':>7} {'ΔFN%':>6} │ {'MeanF1':>7} {'MeanAcc':>8} {'MeanMCR':>8}")
print(f"  {'─'*22}─┼─{'─'*8}─{'─'*9}─{'─'*9}─┼─{'─'*7}─{'─'*7}─{'─'*7}─┼─{'─'*7}─{'─'*6}─{'─'*7}─{'─'*6}─┼─{'─'*7}─{'─'*8}─{'─'*8}")

# Base aggregates
b_tp_total = sum(r['B0_Base']['tp'] for r in ALL)
b_fp_total = sum(r['B0_Base']['fp'] for r in ALL)
b_fn_total = sum(r['n_fraud'] - r['B0_Base']['tp'] for r in ALL)
b_nf_total = sum(r['n_fraud'] for r in ALL)
b_nl_total = sum(r['n'] - r['n_fraud'] for r in ALL)
b_f1_mean = sum(r['B0_Base']['f1'] for r in ALL) / len(ALL)
b_acc_mean = sum((r['B0_Base']['tp'] + (r['n'] - r['n_fraud']) - r['B0_Base']['fp']) / r['n'] * 100 for r in ALL) / len(ALL)
b_mcr_mean = 100 - b_acc_mean

print(f"  {'BASE MODEL':<22} │ {b_nf_total:>8,} {b_tp_total:>9,} {b_fn_total:>9,} │ {b_tp_total:>7,} {b_fp_total:>7,} {b_fn_total:>7,} │ {'---':>7} {'---':>6} {'---':>7} {'---':>6} │ {b_f1_mean:>7.4f} {b_acc_mean:>7.2f}% {b_mcr_mean:>7.2f}%")

for vk in TOP_VARIANTS:
    v_tp = v_fp = v_fn = 0
    f1s = []
    accs = []
    valid = 0
    for r in ALL:
        v = r.get(vk)
        if not v or 'error' in v:
            continue
        valid += 1
        nf = r['n_fraud']
        nl = r['n'] - nf
        v_tp += v['tp']
        v_fp += v['fp']
        fn = nf - v['tp']
        v_fn += fn
        f1s.append(v['f1'])
        acc = (v['tp'] + nl - v['fp']) / r['n'] * 100
        accs.append(acc)

    if valid == 0:
        continue
    d_fp = v_fp - b_fp_total
    d_fn = v_fn - b_fn_total
    d_fp_pct = d_fp / max(b_fp_total, 1) * 100
    d_fn_pct = d_fn / max(b_fn_total, 1) * 100
    mf1 = sum(f1s) / len(f1s)
    macc = sum(accs) / len(accs)
    mmcr = 100 - macc
    fp_s = '+' if d_fp > 0 else ''
    fn_s = '+' if d_fn > 0 else ''
    caught = b_nf_total - v_fn

    print(f"  {vk:<22} │ {b_nf_total:>8,} {caught:>9,} {v_fn:>9,} │ {v_tp:>7,} {v_fp:>7,} {v_fn:>7,} │ {fp_s}{d_fp:>6,} {d_fp_pct:>5.1f}% {fn_s}{d_fn:>6,} {d_fn_pct:>5.1f}% │ {mf1:>7.4f} {macc:>7.2f}% {mmcr:>7.2f}%")

# ── 3. FP vs FN trade-off analysis ──
print(f"\n\n{'=' * 140}")
print("3. FP vs FN TRADE-OFF: Did variants reduce BOTH?\n")

print(f"  {'Variant':<22} │ FP Change │ FN Change │ Both Reduced? │ Net Verdict")
print(f"  {'─'*22}─┼───────────┼───────────┼───────────────┼────────────────────")

for vk in TOP_VARIANTS:
    # Count combos where FP reduced, FN reduced, both reduced
    fp_down = fp_up = fn_down = fn_up = both_down = 0
    for r in ALL:
        v = r.get(vk)
        if not v or 'error' in v:
            continue
        b = r['B0_Base']
        nf = r['n_fraud']
        b_fn = nf - b['tp']
        v_fn = nf - v['tp']
        d_fp = v['fp'] - b['fp']
        d_fn = v_fn - b_fn
        if d_fp < 0: fp_down += 1
        elif d_fp > 0: fp_up += 1
        if d_fn < 0: fn_down += 1
        elif d_fn > 0: fn_up += 1
        if d_fp <= 0 and d_fn <= 0 and (d_fp < 0 or d_fn < 0):
            both_down += 1

    verdict = '*** BOTH REDUCED' if both_down >= 6 else ('FN focus' if fn_down > fp_down else ('FP focus' if fp_down > fn_down else 'Mixed'))
    print(f"  {vk:<22} │ ↓{fp_down:>2} ↑{fp_up:>2}    │ ↓{fn_down:>2} ↑{fn_up:>2}    │    {both_down:>2}/12       │ {verdict}")

# ── 4. Best variant per dataset for missed fraud reduction ──
print(f"\n\n{'=' * 140}")
print("4. BEST VARIANT FOR REDUCING MISSED FRAUD (per dataset×model)\n")

all_vkeys = sorted([k for k in ALL[0].keys() if k[0] in 'ABCDEFGHIJ' and k != 'B0_Base' and '_' in k and k[1].isdigit()])

print(f"  {'Dataset':<15} {'Model':<14} │ {'BaseMissed':>10} │ {'BestVariant':<22} {'NewMissed':>9} {'ΔMissed':>8} {'ΔMissed%':>9} │ {'BaseF1':>7} {'NewF1':>7} {'ΔF1':>7}")
print(f"  {'─'*15} {'─'*14} │ {'─'*10} │ {'─'*22} {'─'*9} {'─'*8} {'─'*9} │ {'─'*7} {'─'*7} {'─'*7}")

for r in ALL:
    nf = r['n_fraud']
    b = r['B0_Base']
    b_fn = nf - b['tp']
    best_vk = None
    best_fn = b_fn
    best_v = None
    for vk in all_vkeys:
        v = r.get(vk)
        if not v or 'error' in v:
            continue
        v_fn = nf - v['tp']
        if v_fn < best_fn:
            best_fn = v_fn
            best_vk = vk
            best_v = v
    if best_vk:
        d_fn = best_fn - b_fn
        d_fn_pct = d_fn / max(b_fn, 1) * 100
        d_f1 = best_v['f1'] - b['f1']
        print(f"  {r['dataset']:<15} {r['model']:<14} │ {b_fn:>10,} │ {best_vk:<22} {best_fn:>9,} {d_fn:>+8,} {d_fn_pct:>+8.1f}% │ {b['f1']:>7.4f} {best_v['f1']:>7.4f} {d_f1:>+7.4f}")
    else:
        print(f"  {r['dataset']:<15} {r['model']:<14} │ {b_fn:>10,} │ {'(none better)':<22}")
