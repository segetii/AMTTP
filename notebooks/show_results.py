import json

R = json.loads(open(r'c:\amttp\data\external_validation\cross_validation_v2_results.json').read())['results']

hdr = f'  {"Dataset":<42} {"Fraud":>6} {"Caught":>7} {"Missed":>7} {"Recall":>8} {"FP Rate":>8} {"ROC-AUC":>10}'

print('\nTABLE 1: DETECTION AT PRODUCTION THRESHOLD')
print('-' * 130)
print(hdr)
print('-' * 130)
t1f = t1c = t1m = 0
for r in R:
    nm = r.get('name', '?')
    np_ = r.get('n_pos')
    nn = r.get('n_neg')
    roc = r.get('roc_auc', '')
    cp = r.get('caught_production')
    fp = r.get('fa_production')
    note = r.get('note', r.get('error', ''))
    if isinstance(np_, int) and isinstance(cp, int):
        mp = np_ - cp
        rc = cp / np_ if np_ > 0 else 0
        fpr = fp / nn if isinstance(fp, int) and nn else 0
        print(f'  {nm:<42} {np_:>6,} {cp:>7,} {mp:>7,} {rc:>7.1%} {fpr:>7.1%} {roc:>10.4f}')
        t1f += np_; t1c += cp; t1m += mp
    else:
        ns = str(np_) if np_ is not None else '-'
        rs = f'{roc:.4f}' if isinstance(roc, float) else str(roc)
        print(f'  {nm:<42} {ns:>6} {"-":>7} {"-":>7} {"-":>8} {"-":>8} {rs:>10}  {note}')
print('-' * 130)
print(f'  {"TOTAL":.<42} {t1f:>6,} {t1c:>7,} {t1m:>7,} {t1c/t1f:>7.1%}')

hdr2 = f'  {"Dataset":<42} {"Fraud":>6} {"Caught":>7} {"Missed":>7} {"Recall":>8} {"FP Rate":>8} {"Best F1":>10}'

print(f'\nTABLE 2: DETECTION AT OPTIMAL F1 THRESHOLD')
print('-' * 130)
print(hdr2)
print('-' * 130)
t2f = t2c = t2m = 0
for r in R:
    nm = r.get('name', '?')
    np_ = r.get('n_pos')
    nn = r.get('n_neg')
    f1 = r.get('f1_optimal', '')
    co = r.get('caught_optimal')
    fo = r.get('fa_optimal')
    note = r.get('note', r.get('error', ''))
    if isinstance(np_, int) and isinstance(co, int):
        mo = np_ - co
        rc = co / np_ if np_ > 0 else 0
        fpr = fo / nn if isinstance(fo, int) and nn else 0
        print(f'  {nm:<42} {np_:>6,} {co:>7,} {mo:>7,} {rc:>7.1%} {fpr:>7.1%} {f1:>10.4f}')
        t2f += np_; t2c += co; t2m += mo
    else:
        ns = str(np_) if np_ is not None else '-'
        fs = f'{f1:.4f}' if isinstance(f1, float) else str(f1)
        print(f'  {nm:<42} {ns:>6} {"-":>7} {"-":>7} {"-":>8} {"-":>8} {fs:>10}  {note}')
print('-' * 130)
print(f'  {"TOTAL":.<42} {t2f:>6,} {t2c:>7,} {t2m:>7,} {t2c/t2f:>7.1%}')
