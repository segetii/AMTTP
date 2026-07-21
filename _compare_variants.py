import json
v63 = json.load(open(r'c:\amttp\research\adaptive-friction\pipeline\results\simulation_v63_quadrant.json'))
prev = {'layered_daily_no_crash_ze7': 3.236}
rows = []
for k, d in v63.items():
    oos = d['oos']
    cal_now = round(oos['calmar'], 3)
    maxdd = round(oos['maxdd']*100, 2)
    final = round(oos['final'])
    sharpe = round(oos['sharpe'], 3)
    prior = prev.get(k)
    rows.append((k, prior, cal_now, maxdd, sharpe, final))

print(f"{'Strategy':<40} {'Prior':>7} {'Calmar':>7} {'Delta':>7} {'MaxDD':>8} {'Sharpe':>7} {'$1k->':>9}")
print('-'*97)
for k, prior, cal, maxdd, sh, fin in rows:
    pr = f'+{prior:.3f}' if prior else '  n/a '
    delta = (f'+{(cal-prior):.3f}' if cal >= prior else f'{(cal-prior):.3f}') if prior else '  n/a'
    cal_s = f'+{cal:.3f}' if cal >= 0 else f'{cal:.3f}'
    print(f'{k:<40} {pr:>7} {cal_s:>7} {delta:>7} {maxdd:>7.2f}% {sh:>7.3f} {fin:>9,}')
