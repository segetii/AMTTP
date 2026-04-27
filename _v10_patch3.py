path = r'C:\amttp\research\adaptive-friction\pipeline\results\run_crypto_pairs_v10.py'
with open(path, encoding='utf-8') as f:
    src = f.read()

# ── 5. Update model name in JSON ───────────────────────────────────────────
src = src.replace(
    '"model": "Crypto BSDT v9 \u2014 Drift-Only Validity Gate + Anchored Z-Score"',
    '"model": "Crypto BSDT v10 \u2014 \u03b3-Aware Dynamic Allocation"'
)
print("model name updated")

# ── 6. Update version_history dict to add v9 entry ─────────────────────────
old_vh = '''            "v8":  {"P1_ETH_BTC": -5.664, "P2_ETH_SOL": 0.546, "P3_ETH_BNB": -16.946,
                    "M1_ALT_macro": 1.387},
        },'''
new_vh = '''            "v8":  {"P1_ETH_BTC": -5.664, "P2_ETH_SOL": 0.546, "P3_ETH_BNB": -16.946,
                    "M1_ALT_macro": 1.387},
            "v9":  {"P1_ETH_BTC": -1.248, "P2_ETH_SOL": 1.357, "P3_ETH_BNB": -0.463,
                    "M1_ALT_macro": 1.387},
        },'''
if old_vh in src:
    src = src.replace(old_vh, new_vh)
    print("version_history updated")
else:
    print("WARNING: version_history marker not found")

# ── 7. Add sims_v10 to JSON results ─────────────────────────────────────────
old_results_close = '''        "crisis_sharpe": _clean(crisis_sharpe),
        "version_history": {'''
new_results_close = '''        "crisis_sharpe": _clean(crisis_sharpe),
        "v10_gamma_results": _clean(sims_v10),
        "v10_gamma_stats": {
            "gamma_clip_low":  GAMMA_CLIP_LOW,
            "gamma_clip_high": GAMMA_CLIP_HIGH,
            "gamma_score_win": GAMMA_SCORE_WIN,
            "gamma_mean_test": float(round(gamma_eth.clip(GAMMA_CLIP_LOW, GAMMA_CLIP_HIGH)[test_mask].mean(), 4)),
            "pct_hi_gamma_test": float(round((gamma_eth.clip(GAMMA_CLIP_LOW, GAMMA_CLIP_HIGH)[test_mask] > 0.6).mean() * 100, 1)),
        },
        "version_history": {'''
if old_results_close in src:
    src = src.replace(old_results_close, new_results_close)
    print("v10_gamma_results inserted in JSON")
else:
    print("WARNING: JSON results marker not found")

# ── 8. Update output file name ───────────────────────────────────────────────
src = src.replace(
    '"crypto_bsdt_v9_results.json"',
    '"crypto_bsdt_v10_results.json"'
)
print("output filename updated")

# ── 9. Update main() header print ────────────────────────────────────────────
src = src.replace(
    '  CRYPTO BSDT v9 \u2014 Drift-Only Validity Gate (rev_eff gate removed)',
    '  CRYPTO BSDT v10 \u2014 \u03b3-Aware Dynamic Allocation'
)
src = src.replace(
    '  Anchored z: z = (S \u2212 \u03bc_train) / \u03c3_train',
    '  Anchored z + Layer 6: \u03b3-modulation \u00d7 cross-sectional Sharpe weights'
)
src = src.replace(
    '  Layer 4: Drift gate only  |\u0304z_60d| < 1.0  (rev_eff removed)',
    '  f(directional)=(1-\u03b3)  f(reversion)=\u03b3  f(macro)=1  \u03b3\u2208[0.10,0.90]'
)
print("header prints updated")

# ── 10. Update summary section ───────────────────────────────────────────────
old_sum_header = '  SUMMARY: v4 \u2192 v6 \u2192 v7 \u2192 v8 \u2192 v9 (drift-only validity gate)'
new_sum_header = '  SUMMARY: v4 \u2192 v6 \u2192 v7 \u2192 v8 \u2192 v9 \u2192 v10 (\u03b3-aware dynamic allocation)'
if old_sum_header in src:
    src = src.replace(old_sum_header, new_sum_header)
    print("summary header updated")
else:
    print("WARNING: summary header not found")

old_sum_loop = '''    v8_ref = {'A_directional': 0.535, 'P1_ETH_BTC': -5.664,
              'P2_ETH_SOL': 0.546, 'P3_ETH_BNB': -16.946,
              'M1_ALT_macro': 1.387}
    for name in ['A_directional', 'P1_ETH_BTC', 'P2_ETH_SOL', 'P3_ETH_BNB',
                 'M1_ALT_macro']:
        v4 = v4_ref.get(name, None)
        v8 = v8_ref.get(name, None)
        v9 = sims[name]['sharpe'] if name in sims else None
        v4s = f"{v4:>+7.3f}" if v4 is not None else "       "
        v7s = f"{v7:>+7.3f}" if v7 is not None else "       "
        v8s = f"{v8:>+7.3f}" if v8 is not None else "       "
        if name in sims:
            dd = (f"  MaxDD {sims[name]['max_dd']:>7.3f}  "
                  f"active {sims[name]['active_days']/sims[name]['total_days']*100:.1f}%")
        else:
            dd = ""
        print(f"  {name:<22}  v4:{v4s}  v8:{v8s}  v9:{v8s}{dd}")'''

new_sum_loop = '''    v9_ref = {'A_directional': 0.535, 'P1_ETH_BTC': -1.248,
              'P2_ETH_SOL': 1.357, 'P3_ETH_BNB': -0.463,
              'M1_ALT_macro': 1.387, 'M1_BTC_macro': 0.156}
    for name in ['A_directional', 'P1_ETH_BTC', 'P2_ETH_SOL', 'P3_ETH_BNB',
                 'M1_ALT_macro', 'DYNAMIC_COMBINED']:
        v4 = v4_ref.get(name, None)
        v9 = v9_ref.get(name, None)
        v10 = sims_v10[name]['sharpe'] if name in sims_v10 else None
        v4s  = f"{v4:>+7.3f}"  if v4  is not None else "       "
        v9s  = f"{v9:>+7.3f}"  if v9  is not None else "       "
        v10s = f"{v10:>+7.3f}" if v10 is not None else "       "
        src_sims = sims_v10 if name in sims_v10 else sims
        if name in sims_v10:
            r = sims_v10[name]
            dd = (f"  MaxDD {r['max_dd']:>7.3f}  "
                  f"active {r['active_days']/r['total_days']*100:.1f}%")
        elif name in sims:
            r = sims[name]
            dd = (f"  MaxDD {r['max_dd']:>7.3f}  "
                  f"active {r['active_days']/r['total_days']*100:.1f}%")
        else:
            dd = ""
        print(f"  {name:<22}  v4:{v4s}  v9:{v9s}  v10:{v10s}{dd}")'''

if old_sum_loop in src:
    src = src.replace(old_sum_loop, new_sum_loop)
    print("summary loop updated")
else:
    print("WARNING: summary loop not found - will need manual fix")

with open(path, 'w', encoding='utf-8') as f:
    f.write(src)
print(f"saved. total lines: {src.count(chr(10))}")
