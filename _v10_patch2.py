path = r'C:\amttp\research\adaptive-friction\pipeline\results\run_crypto_pairs_v10.py'
with open(path, encoding='utf-8') as f:
    src = f.read()

# ── 4. Insert v10 gamma block AFTER the ic_res loop ──────────────────────────
v10_block = """
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  [6]  v10: γ-AWARE POSITIONS + CROSS-SECTIONAL DYNAMIC WEIGHTS
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    print(f"\\n[6]  Building γ-aware positions (v10) ...")
    gc_test = gamma_eth.clip(GAMMA_CLIP_LOW, GAMMA_CLIP_HIGH)[test_mask]
    g_mean  = gc_test.mean()
    print(f"  γ [test]: mean={g_mean:.3f}  std={gc_test.std():.3f}  "
          f"p25={gc_test.quantile(0.25):.3f}  p75={gc_test.quantile(0.75):.3f}")
    print(f"  directional factor (1-γ): mean={(1-g_mean):.3f}")
    print(f"  reversion   factor (γ):   mean={g_mean:.3f}")
    pct_hi = (gc_test > 0.6).mean() * 100
    pct_lo = (gc_test < 0.4).mean() * 100
    print(f"  γ>0.6 (reversion-favourable): {pct_hi:.1f}%  "
          f"γ<0.4 (directional-favourable): {pct_lo:.1f}%")

    pos_v10 = {
        'A_directional': apply_gamma_mod(pos_A_dir,                    gamma_eth, 'directional'),
        'P1_ETH_BTC':    apply_gamma_mod(pair_positions['P1_ETH_BTC'], gamma_eth, 'reversion'),
        'P2_ETH_SOL':    apply_gamma_mod(pair_positions['P2_ETH_SOL'], gamma_eth, 'reversion'),
        'P3_ETH_BNB':    apply_gamma_mod(pair_positions['P3_ETH_BNB'], gamma_eth, 'reversion'),
        'M1_ALT_macro':  apply_gamma_mod(pos_alt_macro,                gamma_eth, 'macro'),
        'M1_BTC_macro':  apply_gamma_mod(pos_btc_macro,                gamma_eth, 'macro'),
    }
    strat_rets = {
        'A_directional': df['ret_eth'],
        'P1_ETH_BTC':    pair_data['P1_ETH_BTC']['sret'],
        'P2_ETH_SOL':    pair_data['P2_ETH_SOL']['sret'],
        'P3_ETH_BNB':    pair_data['P3_ETH_BNB']['sret'],
        'M1_ALT_macro':  df['ret_eth'],
        'M1_BTC_macro':  df['ret_btc'],
    }

    # -- Daily PnL streams (full history) for cross-sectional Sharpe scoring --
    pnl_full = {k: get_daily_pnl(pos_v10[k], strat_rets[k]) for k in pos_v10}

    # -- Rolling cross-sectional Sharpe weights (causal) ----------------------
    cs_wts = compute_cs_weights(pnl_full, window=GAMMA_SCORE_WIN)

    # -- Dynamic combined portfolio PnL: sum_i w_i(t-1) * pnl_i(t) -----------
    pnl_dyn = pd.Series(0.0, index=df.index)
    n_strats = len(pos_v10)
    for k in pos_v10:
        pnl_dyn += cs_wts[k].shift(1).fillna(1.0 / n_strats) * pnl_full[k]

    print(f"\\n[7]  Simulating v10 (test {TEST_START}→2026) ...")
    sims_v10 = {}
    for k in ['A_directional', 'P1_ETH_BTC', 'P2_ETH_SOL', 'P3_ETH_BNB',
              'M1_ALT_macro', 'M1_BTC_macro']:
        sims_v10[k] = simulate(pos_v10[k][test_mask], strat_rets[k][test_mask], k)
    sims_v10['DYNAMIC_COMBINED'] = simulate_from_pnl(pnl_dyn[test_mask], 'DYNAMIC_COMBINED')

    # -- v9 vs v10 comparison table -------------------------------------------
    print()
    print("─" * 88)
    print(f"── v9 vs v10: γ-aware allocation [test {TEST_START}→2026] ────────────────────────────")
    print("─" * 88)
    gamma_modes = {
        'A_directional': '(1-γ)',  'P1_ETH_BTC': 'γ', 'P2_ETH_SOL': 'γ',
        'P3_ETH_BNB':   'γ',       'M1_ALT_macro': '1', 'M1_BTC_macro': '1',
        'DYNAMIC_COMBINED': 'w×γ',
    }
    print(f"  {'Strategy':<22}  {'v9 Sh':>7}  {'v10 Sh':>7}  {'Δ':>7}  "
          f"{'γ-mode':>7}  {'MaxDD':>7}  {'Active%':>7}")
    print("─" * 88)
    for name in ['A_directional', 'P1_ETH_BTC', 'P2_ETH_SOL', 'P3_ETH_BNB',
                 'M1_ALT_macro', 'M1_BTC_macro', 'DYNAMIC_COMBINED']:
        v9s  = sims.get(name, {}).get('sharpe', None)
        v10r = sims_v10.get(name, {})
        v10s = v10r.get('sharpe', None)
        dd   = v10r.get('max_dd', None)
        tot  = v10r.get('total_days', 1)
        act  = v10r.get('active_days', 0)
        pct  = act / tot * 100 if tot > 0 else 0.0
        dlt  = f"{v10s - v9s:>+7.3f}" if (v9s is not None and v10s is not None) else "       "
        v9ss  = f"{v9s:>+7.3f}"  if v9s  is not None else "       "
        v10ss = f"{v10s:>+7.3f}" if v10s is not None else "       "
        dds   = f"{dd:>7.3f}"    if dd   is not None else "       "
        gm    = gamma_modes.get(name, '?')
        print(f"  {name:<22}  {v9ss}  {v10ss}  {dlt}  {gm:>7}  {dds}  {pct:>6.1f}%")

    # -- Mean cross-sectional weights [test] ----------------------------------
    print()
    print("── Mean cross-sectional weights [test period] ──────────────────────")
    for k in pos_v10:
        w_mean = cs_wts[k][test_mask].mean()
        print(f"  {k:<22}: {w_mean:.3f}")
    print()

"""

# Insert after the ic_res loop, before the "Results table" comment
marker = "    ic_res[key] = ic_metric(pair_positions[key][test_mask], fwd21[test_mask], key)\n\n    # ── Results table"
idx = src.index(marker)
insert_at = idx + len("    ic_res[key] = ic_metric(pair_positions[key][test_mask], fwd21[test_mask], key)\n")
src = src[:insert_at] + v10_block + src[insert_at:]
print("v10 block inserted OK")
print(f"search marker found at char {idx}")

with open(path, 'w', encoding='utf-8') as f:
    f.write(src)
print(f"saved. total lines: {src.count(chr(10))}")
