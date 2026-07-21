import json,os
base=r'C:\amttp\research\adaptive-friction\pipeline\results'

# v18
d18=json.load(open(os.path.join(base,'crypto_bsdt_v18_results.json'),encoding='utf-8'))
pr=d18.get('pnl_results',{})
if pr:
    best_k=max(pr.items(),key=lambda kv:kv[1].get('calmar',0))
    cr=best_k[1].get('cum_return',0)
    print(f"v18: final={10000*(1+cr):.0f} calmar={best_k[1].get('calmar',0):.4f} variant={best_k[0]}")
else:
    print(f"v18 no pnl_results, keys={list(d18.keys())[:10]}")

# v19
d19=json.load(open(os.path.join(base,'crypto_bsdt_v19_results.json'),encoding='utf-8'))
bk=d19.get('best_K',{})
print(f"v19: best_variant={d19.get('best_variant','?')} final={bk.get('final','?')} calmar={bk.get('calmar','N/A')} cagr={bk.get('cagr','?')}")

# v20
d20=json.load(open(os.path.join(base,'crypto_bsdt_v20_results.json'),encoding='utf-8'))
ab20=d20['ablation']
best_v20=None; best_sh=None
for vname,vd in ab20.items():
    if isinstance(vd,list) and vd:
        row=max(vd,key=lambda r:r.get('sharpe_net',0) if isinstance(r,dict) else 0)
        sh=row.get('sharpe_net',0)
        if best_sh is None or sh>best_sh:
            best_sh=sh; best_v20=(vname,row)
    elif isinstance(vd,dict):
        sh=vd.get('sharpe_net',0)
        if best_sh is None or sh>best_sh:
            best_sh=sh; best_v20=(vname,vd)
if best_v20:
    vname,row=best_v20
    print(f"v20: best={vname} final={row.get('final','?')} sharpe_net={row.get('sharpe_net','?')}")

# v21
d21=json.load(open(os.path.join(base,'crypto_bsdt_v21_results.json'),encoding='utf-8'))
bk21=d21.get('best_K_net5bp',{})
print(f"v21: best_K={bk21.get('K','?')} final={bk21.get('final','?'):.2f} sharpe={bk21.get('sh','?')}")

# v22
d22=json.load(open(os.path.join(base,'crypto_bsdt_v22_results.json'),encoding='utf-8'))
bk22=d22.get('best_K_net5bp',{})
print(f"v22: best_K={bk22.get('K','?')} final={bk22.get('final','?'):.2f} sharpe={bk22.get('sh','?')}")

# v23
d23=json.load(open(os.path.join(base,'crypto_bsdt_v23_results.json'),encoding='utf-8'))
# look for 'final' anywhere inside variants
vars23=d23.get('variants',{})
best_v23=None; best_sh23=None
for vname,vd in vars23.items():
    if isinstance(vd,dict):
        sh=vd.get('sharpe',vd.get('sharpe_net',None))
        fin=vd.get('final',None)
        print(f"  v23.{vname}: final={fin} sharpe={sh}")
        if sh and (best_sh23 is None or (sh and sh>best_sh23)):
            best_sh23=sh; best_v23=(vname,vd)
baseline=d23.get('baseline',{})
print(f"v23 baseline: {baseline.get('sharpe','?')} | best_repr={d23.get('best_repr','?')} best_sharpe={d23.get('best_sharpe','?')}")

# v24
d24=json.load(open(os.path.join(base,'crypto_bsdt_v24_results.json'),encoding='utf-8'))
vars24=d24.get('variants',{})
for vname,vd in vars24.items():
    if isinstance(vd,dict):
        sh=vd.get('sharpe',vd.get('sharpe_net',None))
        fin=vd.get('final',None)
        print(f"  v24.{vname}: final={fin} sharpe={sh}")
print(f"v24 best_variant={d24.get('best_variant','?')} best_sharpe={d24.get('best_sharpe','?')}")
