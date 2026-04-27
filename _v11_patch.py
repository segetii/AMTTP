"""
v11 patch: 
  1. Update docstring
  2. Add GAMMA_FAST_WIN constant
  3. Add compute_tilted_weights function
  4. Add v11 block in main()
  5. Update output filename, JSON, summary
"""

path = r'C:\amttp\research\adaptive-friction\pipeline\results\run_crypto_pairs_v11.py'
with open(path, encoding='utf-8') as f:
    src = f.read()

# ══════════════════════════════════════════════════════════════════════════════
# 1. Docstring
# ══════════════════════════════════════════════════════════════════════════════
old_doc_start = '"""\nCrypto BSDT v10'
old_doc_end   = 'Layer 6 [NEW]: \u03b3-modulation \u00d7 cross-sectional Sharpe weights\n"""'

new_doc = '''\"""
Crypto BSDT v11 \u2014 Fast \u03b3 + Weight Tilt (not position scaling)
=================================================================

v10 lesson:
  Rolling Sharpe cross-sectional weights turned COMBINED from -0.020 \u2192 +0.597.
  But \u03b3-modulation (applied as position scaling) had \u03b3 \u2248 0.514\u00b10.003 \u2014 nearly
  constant. Root causes:
    1. \u03b3 = 1/(1 + mean(\u03a9_20d)) averages out spikes \u2192 kills regime signal.
    2. Constant scaling \u21d2 f(\u03b3) collapses to a fixed multiplier \u21d2 no new info.

v11 \u2014 Fast \u03b3 + Weight Tilt:
  Two changes from v10:

  a) Fast (instantaneous) \u03b3:
       \u03b3_fast_t = 1 / (1 + \u03a9_t)
     No rolling mean. Tracks the actual regime state each day.
     Characterised by much higher variance \u2014 reacts to stress peaks/troughs.

  b) \u03b3 as WEIGHT TILT, not position scaling:
     Individual strategy positions are unchanged from v9 (5-layer gates, pure signal).
     \u03b3 Applies ONLY at the portfolio weight level:
       w_directional  \u221d  rolling_Sharpe \u00d7 (1 - \u03b3_fast)
       w_reversion    \u221d  rolling_Sharpe \u00d7  \u03b3_fast
       w_macro        \u221d  rolling_Sharpe \u00d7  1

     Normalised daily to sum to 1. \u03b3_fast clipped to [0.10, 0.90].

  Intuition:
    When \u03a9 spikes (\u03b3_fast low): directional weights rise, reversion weights fall
      \u2192 ride the momentum / crash leg
    When \u03a9 is high and flattens (\u03b3_fast high): reversion weights rise
      \u2192 capture the snap-back
    Macro always proportional to its Sharpe \u2014 less sensitive to \u03b3

v11 architecture:
  Layer 1:  \u03a9 \u2014 timing gate
  Layer 2:  A \u2014 intensity gate
  Layer 3:  UDL MDN \u2014 geometry (EQUIL / DEGEN / STRUCT)
  Layer 4:  Drift gate  |\u0304z_60d| < 1.0  (anchored z)
  Layer 5:  POA-scaled sizing
  Layer 6:  Portfolio weight = rolling_Sharpe \u00d7 \u03b3_fast_tilt(t) [v11 upgrade]
\"""'''

i_start = src.index(old_doc_start)
i_end   = src.index(old_doc_end) + len(old_doc_end)
src = src[:i_start] + new_doc + src[i_end:]
print("1. docstring OK")

# ══════════════════════════════════════════════════════════════════════════════
# 2. Update model name header in main()
# ══════════════════════════════════════════════════════════════════════════════
src = src.replace(
    'CRYPTO BSDT v10 \u2014 \u03b3-Aware Dynamic Allocation',
    'CRYPTO BSDT v11 \u2014 Fast \u03b3 + Weight Tilt'
)
src = src.replace(
    'Anchored z + Layer 6: \u03b3-modulation \u00d7 cross-sectional Sharpe weights',
    'Layer 6: w_tilt = rolling_Sharpe \u00d7 \u03b3_fast_tilt (no position scaling)'
)
src = src.replace(
    'f(directional)=(1-\u03b3)  f(reversion)=\u03b3  f(macro)=1  \u03b3\u2208[0.10,0.90]',
    '\u03b3_fast=1/(1+\u03a9)  w_dir\u221d(1-\u03b3_fast)  w_rev\u221d\u03b3_fast  w_macro\u221d1'
)
print("2. header prints OK")

# ══════════════════════════════════════════════════════════════════════════════
# 3. Update output filename, JSON model name
# ══════════════════════════════════════════════════════════════════════════════
src = src.replace(
    '"crypto_bsdt_v10_results.json"',
    '"crypto_bsdt_v11_results.json"'
)
src = src.replace(
    '"model": "Crypto BSDT v10 \u2014 \u03b3-Aware Dynamic Allocation"',
    '"model": "Crypto BSDT v11 \u2014 Fast \u03b3 + Weight Tilt"'
)
print("3. filename/model OK")

# ══════════════════════════════════════════════════════════════════════════════
# 4. Add compute_tilted_weights() before the γ-AWARE ALLOCATION FUNCTIONS section
# ══════════════════════════════════════════════════════════════════════════════
new_func = r"""
def compute_tilted_weights(pnl_dict, gamma_series, tilt_modes, window=126):
    """
new_func = """
def compute_tilted_weights(pnl_dict, gamma_series, tilt_modes, window=126):
    \"\"\"
    Cross-sectional portfolio weights = rolling_Sharpe x gamma_tilt, normalised.

    Parameters
    ----------
    pnl_dict    : dict  label -> pd.Series daily PnL (full history)
    gamma_series: pd.Series  instantaneous gamma (gamma_fast = 1/(1+omega))
    tilt_modes  : dict  label -> 'directional' | 'reversion' | 'macro'
    window      : rolling Sharpe window (days)

    Returns
    -------
    dict  label -> pd.Series daily portfolio weights (sum to 1 per day)

    Tilt rules:
      directional  :  w = Sh+ x (1 - gamma_clipped)
      reversion    :  w = Sh+ x  gamma_clipped
      macro        :  w = Sh+                        (no tilt)
      Sh+ = max(rolling_Sharpe, 0)  -- broken strategies get zero weight
    \"\"\"
    gc = gamma_series.clip(GAMMA_CLIP_LOW, GAMMA_CLIP_HIGH)

    sharpes = {}
    for label, pnl in pnl_dict.items():
        mu = pnl.rolling(window, min_periods=window // 2).mean()
        sd = pnl.rolling(window, min_periods=window // 2).std()
        sharpes[label] = (mu / (sd + 1e-12) * np.sqrt(252)).clip(lower=0.0)

    raw_w = {}
    for label, mode in tilt_modes.items():
        sh = sharpes[label].reindex(pnl_dict[label].index)
        if mode == 'directional':
            tilt = (1.0 - gc).reindex(sh.index).fillna(0.5)
        elif mode == 'reversion':
            tilt = gc.reindex(sh.index).fillna(0.5)
        else:
            tilt = pd.Series(1.0, index=sh.index)
        raw_w[label] = sh * tilt

    raw_df = pd.DataFrame(raw_w)
    total  = raw_df.sum(axis=1).replace(0, float('nan'))
    n      = len(pnl_dict)
    weights = {}
    for label in pnl_dict:
        weights[label] = (raw_df[label] / total).fillna(1.0 / n)
    return weights

"""

marker_func = "# \u2500" * 6 + "\n#  \u03b3-AWARE ALLOCATION FUNCTIONS"
if marker_func in src:
    idx_f = src.index(marker_func)
    src = src[:idx_f] + new_func + src[idx_f:]
    print("4. compute_tilted_weights inserted OK")
else:
    # fallback: insert before apply_gamma_mod
    marker_fb = "def apply_gamma_mod("
    idx_f = src.index(marker_fb)
    src = src[:idx_f] + new_func + src[idx_f:]
    print("4. compute_tilted_weights inserted (fallback) OK")

# ══════════════════════════════════════════════════════════════════════════════
# 5. Replace the v10 block in main() with v11 block
# ══════════════════════════════════════════════════════════════════════════════
# Find the [6] header
old_block_start = "    # \u2501" * 10
# find lines [6] and [7] --- use a precise search
block_hdr = "    # [6]  v10: \u03b3-AWARE POSITIONS + CROSS-SECTIONAL DYNAMIC WEIGHTS"
if block_hdr not in src:
    # look for the box drawing version
    block_hdr = "[6]  v10"
    idx_b6 = src.find(block_hdr)
    print(f"  block [6] approx at char {idx_b6}")

# Find where the v10 block ends (after the mean cross-sectional weights print)
end_marker = "    # ── Results table"
idx_end = src.index(end_marker)
# Find start of v10 block - look for the ━━━ line before [6]
v10_box = "\u2501" * 10   # ━━━━━━━━━━
idx_v10_box = src.rfind(v10_box, 0, idx_end)
# go back to start of that line
line_start = src.rfind('\n', 0, idx_v10_box) + 1
print(f"  v10 block start line char: {line_start}")
print(f"  v10 block end marker at:   {idx_end}")

v11_block = """    # \u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501
    #  [6]  v11: FAST \u03b3 + WEIGHT TILT (no position scaling)
    # \u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501
    print(f"\\n[6]  Computing fast \u03b3 and building v11 tilted-weight portfolio ...")

    # ── a) Fast (instantaneous) gamma ─────────────────────────────────────
    gamma_fast = 1.0 / (1.0 + omega)   # no smoothing; same index as omega
    gf_test    = gamma_fast.clip(GAMMA_CLIP_LOW, GAMMA_CLIP_HIGH)[test_mask]
    gf_slow    = gamma_eth.clip(GAMMA_CLIP_LOW, GAMMA_CLIP_HIGH)[test_mask]
    print(f"  \u03b3_fast [test]: mean={gf_test.mean():.3f}  std={gf_test.std():.3f}  "
          f"p10={gf_test.quantile(0.10):.3f}  p90={gf_test.quantile(0.90):.3f}")
    print(f"  \u03b3_slow [test]: mean={gf_slow.mean():.3f}  std={gf_slow.std():.4f}  "
          f"(v10 reference)")
    pct_hi_f = (gf_test > 0.6).mean() * 100
    pct_lo_f = (gf_test < 0.4).mean() * 100
    print(f"  \u03b3_fast>0.6 (reversion-favour): {pct_hi_f:.1f}%  "
          f"\u03b3_fast<0.4 (directional-favour): {pct_lo_f:.1f}%")

    # ── b) Base PnL streams using v9 positions (no gamma scaling) ─────────
    pos_base = {{
        'A_directional': pos_A_dir,
        'P1_ETH_BTC':    pair_positions['P1_ETH_BTC'],
        'P2_ETH_SOL':    pair_positions['P2_ETH_SOL'],
        'P3_ETH_BNB':    pair_positions['P3_ETH_BNB'],
        'M1_ALT_macro':  pos_alt_macro,
        'M1_BTC_macro':  pos_btc_macro,
    }}
    strat_rets_all = {{
        'A_directional': df['ret_eth'],
        'P1_ETH_BTC':    pair_data['P1_ETH_BTC']['sret'],
        'P2_ETH_SOL':    pair_data['P2_ETH_SOL']['sret'],
        'P3_ETH_BNB':    pair_data['P3_ETH_BNB']['sret'],
        'M1_ALT_macro':  df['ret_eth'],
        'M1_BTC_macro':  df['ret_btc'],
    }}
    pnl_base = {{k: get_daily_pnl(pos_base[k], strat_rets_all[k]) for k in pos_base}}

    # ── c) v10 combined (slow \u03b3 position scaling + Sharpe weights) ──────────
    pnl_v10_dict = {{
        'A_directional': get_daily_pnl(apply_gamma_mod(pos_A_dir, gamma_eth, 'directional'), df['ret_eth']),
        'P1_ETH_BTC':    get_daily_pnl(apply_gamma_mod(pair_positions['P1_ETH_BTC'], gamma_eth, 'reversion'), pair_data['P1_ETH_BTC']['sret']),
        'P2_ETH_SOL':    get_daily_pnl(apply_gamma_mod(pair_positions['P2_ETH_SOL'], gamma_eth, 'reversion'), pair_data['P2_ETH_SOL']['sret']),
        'P3_ETH_BNB':    get_daily_pnl(apply_gamma_mod(pair_positions['P3_ETH_BNB'], gamma_eth, 'reversion'), pair_data['P3_ETH_BNB']['sret']),
        'M1_ALT_macro':  get_daily_pnl(pos_alt_macro, df['ret_eth']),
        'M1_BTC_macro':  get_daily_pnl(pos_btc_macro, df['ret_btc']),
    }}
    cs_wts_v10 = compute_cs_weights(pnl_v10_dict, window=GAMMA_SCORE_WIN)
    pnl_dyn_v10 = pd.Series(0.0, index=df.index)
    n_s = len(pnl_v10_dict)
    for k in pnl_v10_dict:
        pnl_dyn_v10 += cs_wts_v10[k].shift(1).fillna(1.0/n_s) * pnl_v10_dict[k]
    sims_v10_comb = simulate_from_pnl(pnl_dyn_v10[test_mask], 'DYNAMIC_v10')

    # ── d) v11 combined (fast \u03b3 weight tilt + Sharpe weights) ──────────────
    tilt_modes = {{
        'A_directional': 'directional',
        'P1_ETH_BTC':    'reversion',
        'P2_ETH_SOL':    'reversion',
        'P3_ETH_BNB':    'reversion',
        'M1_ALT_macro':  'macro',
        'M1_BTC_macro':  'macro',
    }}
    cs_wts_v11 = compute_tilted_weights(pnl_base, gamma_fast, tilt_modes, window=GAMMA_SCORE_WIN)
    pnl_dyn_v11 = pd.Series(0.0, index=df.index)
    for k in pnl_base:
        pnl_dyn_v11 += cs_wts_v11[k].shift(1).fillna(1.0/n_s) * pnl_base[k]
    sims_v11_comb = simulate_from_pnl(pnl_dyn_v11[test_mask], 'DYNAMIC_v11')

    # ── e) Comparison table ───────────────────────────────────────────────
    print("\\n" + "\u2500" * 85)
    print(f"\u2500\u2500 v10 vs v11: fast \u03b3 weight tilt vs slow \u03b3 position scaling [test] \u2500\u2500")
    print("\u2500" * 85)
    print(f"  {{'Strategy':<22}}  {{'v9 Sh':>7}}  {{'v10 Sh':>8}}  {{'v11 Sh':>8}}  "
          f"{{'v10\u2192v11':>8}}  {{'MaxDD_v11':>10}}")
    print("\u2500" * 85)

    v9_sharpes = {{
        'A_directional': sims.get('A_directional', {{}}).get('sharpe'),
        'P1_ETH_BTC':    sims.get('P1_ETH_BTC',    {{}}).get('sharpe'),
        'P2_ETH_SOL':    sims.get('P2_ETH_SOL',    {{}}).get('sharpe'),
        'P3_ETH_BNB':    sims.get('P3_ETH_BNB',    {{}}).get('sharpe'),
        'M1_ALT_macro':  sims.get('M1_ALT_macro',  {{}}).get('sharpe'),
        'M1_BTC_macro':  sims.get('M1_BTC_macro',  {{}}).get('sharpe'),
    }}
    # Individual v11 strategy Sharpes = v9 base (positions unchanged)
    indiv_labels = ['A_directional','P1_ETH_BTC','P2_ETH_SOL','P3_ETH_BNB',
                    'M1_ALT_macro','M1_BTC_macro']
    for name in indiv_labels + ['DYNAMIC_COMBINED']:
        v9s = v9_sharpes.get(name)
        if name == 'DYNAMIC_COMBINED':
            v10s = sims_v10_comb.get('sharpe')
            v11s = sims_v11_comb.get('sharpe')
            dd   = sims_v11_comb.get('max_dd')
            act  = sims_v11_comb.get('active_days', 0)
            tot  = sims_v11_comb.get('total_days', 1)
        else:
            v10s = sims_v10.get(name, {{}}).get('sharpe') if name in sims_v10 else None
            v11s = v9s   # individual positions unchanged in v11
            dd   = sims.get(name, {{}}).get('max_dd')
            act  = sims.get(name, {{}}).get('active_days', 0)
            tot  = sims.get(name, {{}}).get('total_days', 1)
        pct = act / tot * 100 if tot > 0 else 0.0
        v9ss  = f"{{v9s:>+7.3f}}"  if v9s  is not None else "       "
        v10ss = f"{{v10s:>+8.3f}}" if v10s is not None else "        "
        v11ss = f"{{v11s:>+8.3f}}" if v11s is not None else "        "
        dlt   = f"{{v11s - v10s:>+8.3f}}" if (v10s is not None and v11s is not None) else "        "
        dds   = f"{{dd:>10.3f}}"   if dd   is not None else "          "
        label = name if name != 'DYNAMIC_COMBINED' else '\u2500'*4 + ' DYNAMIC_COMBINED'
        print(f"  {{label:<26}}  {{v9ss}}  {{v10ss}}  {{v11ss}}  {{dlt}}  {{dds}}")

    # ── f) Mean v11 weights [test] ────────────────────────────────────────
    print(f"\\n\u2500\u2500 Mean v11 tilted weights vs v10 weights [test] \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500")
    print(f"  {{'Strategy':<22}}  {{'v11 wt':>8}}  {{'v10 wt':>8}}  {{'tilt':>8}}  {{\u03b3 mode':>12}}")
    print("\u2500" * 68)
    for k, mode in tilt_modes.items():
        wt11 = cs_wts_v11[k][test_mask].mean()
        wt10 = cs_wts_v10[k][test_mask].mean()
        print(f"  {{k:<22}}  {{wt11:>+8.3f}}  {{wt10:>+8.3f}}  {{wt11-wt10:>+8.3f}}  {{mode:>12}}")

    # Store v11 combined results for JSON
    sims_v11 = dict(sims_v10)   # individual strategies same as v9
    sims_v11['DYNAMIC_v10'] = sims_v10_comb
    sims_v11['DYNAMIC_v11'] = sims_v11_comb

"""

src = src[:line_start] + v11_block + src[idx_end:]
print(f"5. v11 block inserted (replaced {idx_end - line_start} chars)")

with open(path, 'w', encoding='utf-8') as f:
    f.write(src)
print(f"saved. total lines: {src.count(chr(10))}")
