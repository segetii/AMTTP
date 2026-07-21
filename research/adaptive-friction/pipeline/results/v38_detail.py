import json
with open('v38_ito_tightcb/crypto_godmode_v38_ito_tightcb.json') as f:
    data = json.load(f)
results = data['results']

targets = [
    'd0p25_q0p5_eta3e-04_lm1000_kmnone',
    'd0p3_q0p65_eta2e-04_lm1000_km10',
    'd0p25_q0p5_eta0e+00_lm0_kmnone',
    'd0p3_q0p5_eta2e-04_lm1000_km10',
    'd0p3_q0p65_eta5e-04_lm1000_kmnone',
    'd0p3_q0p5_eta3e-04_lm1000_kmnone',
]
for name in targets:
    r = next((x for x in results if x['name'] == name), None)
    if r:
        n = r['name']
        cal = r['calmar']
        fin = r['final']
        dd = r['maxdd'] * 100
        cagr = r['cagr'] * 100
        sh = r['sharpe']
        r23 = r['r2023'] * 100
        r24 = r['r2024'] * 100
        r25 = r['r2025'] * 100
        r26 = r['r2026'] * 100
        halt = r['pct_halted'] * 100
        rst = r['ito_resets']
        lam = r.get('lambda_g7', 0.0)
        print(f'{n}')
        print(f'  Calmar={cal:.2f}, Final={fin:,.0f}, MaxDD={dd:.1f}%, CAGR={cagr:.1f}%, Sharpe={sh:.2f}')
        print(f'  r2023={r23:+.1f}%, r2024={r24:+.1f}%, r2025={r25:+.1f}%, r2026={r26:+.1f}%')
        print(f'  pct_halted={halt:.1f}%, ito_resets={rst}, lambda_g7={lam:.4f}')
        print()
