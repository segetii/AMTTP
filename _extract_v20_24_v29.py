import json,os
base=r'C:\amttp\research\adaptive-friction\pipeline\results'

# Find v29
found=[]
for root,dirs,files in os.walk(base):
    for f in files:
        if 'v29' in f and f.endswith('.json'):
            found.append(os.path.join(root,f))
print('v29 files:',found)

# v23 sim fields
d23=json.load(open(os.path.join(base,'crypto_bsdt_v23_results.json'),encoding='utf-8'))
print()
for vname,vd in d23['variants'].items():
    sim=vd.get('sim',{})
    print('v23.'+vname+': sh='+str(round(sim.get('sharpe',0),4))+' cum='+str(round(sim.get('cum_return',0),4)))

# v24
print()
d24=json.load(open(os.path.join(base,'crypto_bsdt_v24_results.json'),encoding='utf-8'))
for vname,vd in d24['variants'].items():
    sim=vd.get('sim',{})
    print('v24.'+vname+': sh='+str(round(sim.get('sharpe',0),4))+' cum='+str(round(sim.get('cum_return',0),4)))

# v20
print()
d20=json.load(open(os.path.join(base,'crypto_bsdt_v20_results.json'),encoding='utf-8'))
ab20=d20['ablation']
best_sh=0; best_nm=''; best_cum=0
for vname,vd in ab20.items():
    if isinstance(vd,dict):
        sh=vd.get('sharpe',0)
        cum=vd.get('cum_return',0)
        print('v20.'+vname+': sh='+str(round(sh,4))+' cum='+str(round(cum,6)))
        if sh>best_sh: best_sh=sh; best_nm=vname; best_cum=cum
print('v20 BEST: '+best_nm+' sh='+str(round(best_sh,4))+' cum='+str(round(best_cum,6)))

# v29 when found
print()
if found:
    for fp in found:
        d=json.load(open(fp,encoding='utf-8'))
        print('v29 file='+os.path.basename(fp))
        print('keys='+str(list(d.keys()))[:200])
        if 'results' in d and isinstance(d['results'],list):
            best=max(d['results'],key=lambda r:r.get('calmar',0))
            print('v29 best: final='+str(best.get('final',0))+' calmar='+str(best.get('calmar',0)))
