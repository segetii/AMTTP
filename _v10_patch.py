path = r'C:\amttp\research\adaptive-friction\pipeline\results\run_crypto_pairs_v10.py'
with open(path, encoding='utf-8') as f:
    src = f.read()

# ── 1. Replace docstring ─────────────────────────────────────────────────────
old_doc_start = '"""\nCrypto BSDT v9'
old_doc_end   = 'Layer 5: POA-scaled sizing\n"""'
new_doc = '''\"""
Crypto BSDT v10 \u2014 \u03b3-Aware Dynamic Allocation
===============================================

v9 lesson:
  Drift-only validity gate raised VALID% to 48\u201361% and restored sample
  sizes to n=47\u201398. ETH/SOL Sharpe +1.357. Allocation is still static:
  all strategies contribute equally regardless of system state (\u03b3 level).

v10 \u2014 Strategy-Specific \u03b3 Modulation:
  position_i(t) = base_position_i(t) \u00d7 f_i(\u03b3_clipped(t))

  f(\u03b3) by strategy type:
    Directional (A_dir)   : f(\u03b3) = 1 \u2212 \u03b3   \u2014 reduce when system near saturation
    Mean-reversion (pairs): f(\u03b3) = \u03b3      \u2014 amplify when stress peaks (reversion set-up)
    Macro (ALT/BTC)       : f(\u03b3) = 1       \u2014 \u03a9/A driven, insensitive to \u03b3

  Intuition:
    \u03b3 = 1/(1 + \u0100\u03a9_20d) \u2014 high when system near saturation (\u03a9 high repeatedly)
    High \u03b3 \u2192 late-stage crash risk for directional
    High \u03b3 \u2192 pairs far from anchor \u2192 better reversion set-up

  \u03b3 clipped to [0.10, 0.90] \u2014 prevents full position elimination.

v10 \u2014 Cross-Sectional Dynamic Weighting (combined portfolio):
  Weights \u221d rolling 126d Sharpe per \u03b3-adjusted strategy (causal).
  Negative-Sharpe strategies get zero weight.
  Combined PnL = \u03a3_i w_i(t\u22121) \u00d7 pos_i(t\u22121) \u00d7 ret_i(t)

Full 5-layer architecture unchanged from v9; \u03b3 is Layer 6:
  Layer 1: \u03a9 \u2014 timing gate
  Layer 2: A \u2014 intensity gate
  Layer 3: UDL MDN \u2014 geometry (EQUIL / DEGEN / STRUCT)
  Layer 4: Drift gate only  |\u0304z_60d| < 1.0  (anchored z)
  Layer 5: POA-scaled sizing
  Layer 6 [NEW]: \u03b3-modulation \u00d7 cross-sectional Sharpe weights
\"""'''

i_start = src.index(old_doc_start)
i_end   = src.index(old_doc_end) + len(old_doc_end)
src = src[:i_start] + new_doc + src[i_end:]
print("docstring replaced OK")

# ── 2. Add gamma constants after EFF_THRESH line ────────────────────────────
gamma_consts = """\n# \u2500\u2500\u2500 \u03b3-aware allocation (v10) \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\nGAMMA_CLIP_LOW   = 0.10   # floor \u2014 never fully zero-out directional\nGAMMA_CLIP_HIGH  = 0.90   # cap   \u2014 never fully saturate reversion\nGAMMA_SCORE_WIN  = 126    # ~6-month rolling Sharpe window for cross-sectional scoring\n"""
marker = "EFF_THRESH    = 0.0   # rev_eff_60d below this"
idx = src.index(marker)
eol = src.index('\n', idx) + 1
src = src[:eol] + gamma_consts + src[eol:]
print("constants inserted OK")

# ── 3. Insert 4 new functions before setup_a_directional ───────────────────
new_funcs = """
# \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
#  \u03b3-AWARE ALLOCATION FUNCTIONS (v10)
# \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
def apply_gamma_mod(pos, gamma_series, mode='macro'):
    \"\"\"
    Modulate position by strategy-specific adaptive friction term.

    mode='directional' : pos x (1 - gamma_clipped)
        Directional strategies profit in early/mid regimes.
        Reduce as gamma rises (system near saturation = late-stage crash risk).
    mode='reversion'   : pos x gamma_clipped
        Reversion strategies profit after stress peaks.
        Amplify when gamma high (large displacement from anchor = better set-up).
    mode='macro'       : pos unchanged
        Macro rotation driven by Omega and A; less sensitive to gamma level.

    Clipping (GAMMA_CLIP_LOW, GAMMA_CLIP_HIGH) prevents full zero-out at extremes.
    \"\"\"
    gc = gamma_series.reindex(pos.index).clip(GAMMA_CLIP_LOW, GAMMA_CLIP_HIGH)
    if mode == 'directional':
        return (pos * (1.0 - gc)).clip(-1, 1)
    elif mode == 'reversion':
        return (pos * gc).clip(-1, 1)
    else:
        return pos.clip(-1, 1)


def get_daily_pnl(pos, ret):
    \"\"\"Causal daily PnL: position(t-1) x ret(t). No lookahead.\"\"\"
    return pos.shift(1).fillna(0) * ret.reindex(pos.index).fillna(0)


def compute_cs_weights(pnl_dict, window=126):
    \"\"\"
    Rolling cross-sectional Sharpe weights for dynamic portfolio allocation.

    Backward-looking rolling Sharpe per strategy, normalized to portfolio weights.
    Negative-Sharpe strategies get zero weight (no short-selling of strategies).
    Equal-weight fallback when all Sharpes are non-positive.

    Parameters
    ----------
    pnl_dict : dict label -> pd.Series daily PnL (full history, causal)
    window   : rolling window in days

    Returns
    -------
    dict label -> pd.Series weights (sum to 1 cross-sectionally each day)
    \"\"\"
    sharpes = {}
    for label, pnl in pnl_dict.items():
        mu = pnl.rolling(window, min_periods=window // 2).mean()
        sd = pnl.rolling(window, min_periods=window // 2).std()
        sharpes[label] = mu / (sd + 1e-12) * np.sqrt(252)
    df_sh = pd.DataFrame(sharpes).clip(lower=0.0)
    total = df_sh.sum(axis=1)
    n     = len(pnl_dict)
    weights = {}
    for label in pnl_dict:
        w = df_sh[label] / total.replace(0, float('nan'))
        weights[label] = w.fillna(1.0 / n)
    return weights


def simulate_from_pnl(pnl_series, label=""):
    \"\"\"
    Compute simulation stats directly from daily PnL stream.
    Used for the dynamic combined portfolio (multiple return streams).
    \"\"\"
    import numpy as _np
    pnl      = pnl_series.fillna(0).values
    cum      = _np.cumprod(1.0 + pnl)
    active   = pnl[pnl != 0]
    sharpe   = float(active.mean() / (_np.std(active) + 1e-12) * _np.sqrt(252)) if len(active) > 0 else 0.0
    roll_max = _np.maximum.accumulate(cum)
    max_dd   = float((cum / roll_max - 1).min())
    hit_rate = float((active > 0).mean()) if len(active) > 0 else float('nan')
    return dict(
        label=label,
        sharpe=round(sharpe, 3),
        max_dd=round(max_dd, 3),
        cum_return=round(float(cum[-1] - 1), 3),
        active_days=int((pnl != 0).sum()),
        total_days=int(len(pnl)),
        hit_rate=round(hit_rate, 3) if hit_rate == hit_rate else None,
    )

"""

marker2 = "# ─────────────────────────────────────────────────────────────────────────────\n#  v2 DIRECTIONAL"
idx2 = src.index(marker2)
src = src[:idx2] + new_funcs + src[idx2:]
print("new functions inserted OK")

with open(path, 'w', encoding='utf-8') as f:
    f.write(src)
print("saved after step 3")
print(f"total lines: {src.count(chr(10))}")
