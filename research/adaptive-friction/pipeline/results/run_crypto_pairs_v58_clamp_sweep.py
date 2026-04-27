"""Quick sweep: find minimum clamp lower-bound to get rv×1.10 drop < 0.15."""
import os, sys, warnings, json, pickle
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")
warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, r'C:\amttp\research\adaptive-friction')

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from collapse_geometry import MasterOperator
from run_crypto_pairs_v38_lambda_norm import compute_lambda_features
from run_crypto_pairs_v37_price_prediction import compute_price_prediction_signals
from run_crypto_pairs_v36_intraday_bsdt import (
    CALIB_BARS, BPD,
    build_intraday_state_panel, calibrate_intraday_engine,
    compute_intraday_signals, _stats,
)
from run_crypto_pairs_v34_full_combined import (
    OUT_DIR, TEST_START, TRAIN_START, TRAIN_END,
    build_1h_df, fetch_binance_funding, add_leverage_features,
    build_daily_positions, upsample_daily_to_1h_pnl,
    compute_1h_strategies, compute_quality, assemble_combined,
)
from run_crypto_pairs_v39_four_channels import FIRE_PERCENTILE, calibrate_firing_thresholds
from run_crypto_pairs_v39b_k1_scaled import PCA_K_B, calibrate_channel_means, compute_four_channel_signals_v39b
import run_crypto_pairs_v34_full_combined as _v34

_CACHE = Path(r'C:\amttp\data')
_TTL = 72

def _cf(fn):
    def w(sym, s, e, iv='1h'):
        p = _CACHE / f'klines_{sym}_{iv}.pkl'
        if p.exists() and (__import__('time').time() - p.stat().st_mtime) / 3600 < _TTL:
            return pd.read_pickle(str(p))
        r = fn(sym, s, e, iv); r.to_pickle(str(p)); return r
    return w

_v34.fetch_klines = _cf(_v34.fetch_klines)

CLIP=6.0; GH_TH=5.0; GH_TL=GL_TH=GL_TL=-1.0
N=8; TTB=0.41; GTB=0.45; GBT=0.45; CB=0.65; AFT=0.65; KG=0.10
OOS='2025-01-01'

def rv_norm(df_1h, span=3):
    rv = df_1h['ret_eth'].rolling(168, min_periods=24).std()
    rv_m = rv.rolling(1000, min_periods=100).mean()
    r = (rv / rv_m.replace(0, np.nan)).fillna(1.0)
    if span > 1:
        r = r.ewm(span=span, adjust=False).mean()
    return r.shift(1).fillna(1.0)

def build_pnl(base, sv36, lf, s4, rv, lo):
    idx = base.index
    sv36 = sv36.reindex(idx, method='ffill').fillna(0)
    lf   = lf.reindex(idx,   method='ffill').fillna(0.5)
    s4   = s4.reindex(idx,   method='ffill').fillna(0)
    gam  = sv36['gamma_star_adj'].shift(1).fillna(0.24)
    lp   = lf['lambda_pct_100'].shift(1).fillna(0.5)
    size = np.clip(1 - gam, 0, 1) * (0.75 + 0.5 * lp)
    adj  = (KG * (1.0 - rv.reindex(idx, method='ffill').fillna(1.0))).clip(lo, 0.10)
    gth  = (GTB * (1.0 + adj)).clip(0.20, 0.70)
    aG = s4['a_G']; aA = s4['a_A']; aT = s4['a_T']
    Gm = aG.rolling(N, min_periods=1).max().shift(1).fillna(0)
    Tm = aT.rolling(N, min_periods=1).max().shift(1).fillna(0)
    fi = aA.shift(1).fillna(0) > AFT
    q1 = (fi & (Gm > gth)  & (Tm > TTB)).astype(float)
    q2 = (fi & (Gm > gth)  & (Tm <= TTB)).astype(float)
    q3 = (fi & (Gm <= gth) & (Tm > TTB)).astype(float)
    q4 = (fi & (Gm <= gth) & (Tm <= TTB)).astype(float)
    phase = (1 + GH_TH*q1 + GH_TL*q2 + GL_TH*q3 + GL_TL*q4).clip(0.05, CLIP)
    flag  = (aG.shift(1).fillna(0) > GBT).astype(float)
    return base.fillna(0) * size * (1 + CB * flag) * phase

def sh(p): return float(_stats(p)['sharpe'])

print("Loading data (all cached)...")
df_1h, has_sol = build_1h_df(start='2021-01-01', end='2026-05-01')
test_mask   = df_1h.index >= TEST_START
train_1h    = (df_1h.index >= TRAIN_START) & (df_1h.index < TEST_START)
second_half = df_1h.index >= OOS

fund = pickle.load(open(str(_CACHE / 'binance_funding.pkl'), 'rb'))
fe = fund.get('ETHUSDT'); fb = fund.get('BTCUSDT')
X = build_intraday_state_panel(df_1h, fb, fe); X = np.nan_to_num(X)
ti = np.where(train_1h)[0]; cm = np.zeros(len(df_1h), dtype=bool); cm[ti[-CALIB_BARS:]] = True
M, net, geom, lyap, ews, stoch, e_star, theta = calibrate_intraday_engine(X, cm)
sn = getattr(stoch, 'sigma_n', 1.0); M_k1 = MasterOperator.calibrate(X[cm], k=PCA_K_B)
sv36 = compute_intraday_signals(X, df_1h, M, net, ews, stoch, e_star, theta)
sv37, _, _ = compute_price_prediction_signals(X, df_1h, M, sv36, e_star, sn)
lf = compute_lambda_features(sv37, roll_windows=(100, 200, 500))
mu = calibrate_channel_means(X, cm, M_k1)
ft = calibrate_firing_thresholds(X, cm, M_k1, pct=FIRE_PERCENTILE)
s4 = compute_four_channel_signals_v39b(X, df_1h, M_k1, sv36, ft, mu)

df_d = pickle.load(open(str(_CACHE / 'cross_market_df.pkl'), 'rb'))
df_d = add_leverage_features(df_d, fund)
tmask_d = (df_d.index >= TRAIN_START) & (df_d.index <= TRAIN_END)
pos, _, F, gate = build_daily_positions(df_d, tmask_d, np.asarray(tmask_d, dtype=bool))
imap = {
    'D1_trend_eth': df_1h['ret_eth'], 'D2_pairs_eb': df_1h['spread_ret_eb'],
    'D3_pairs_es': df_1h['ret_eth'] - df_1h.get('ret_sol', df_1h['ret_eth']),
    'D4_macro_btc': df_1h['ret_btc'], 'D5_macro_btc': df_1h['ret_btc'],
    'D5_macro_alt': df_1h['ret_eth'],
}
h_s = compute_1h_strategies(df_1h, has_sol)
d1h = {n: upsample_daily_to_1h_pnl(p, imap.get(n, df_1h['ret_eth']), gate) for n, p in pos.items()}
base = assemble_combined({**d1h, **h_s}, compute_quality({**d1h, **h_s}, bpd=BPD))

rv3 = rv_norm(df_1h, span=3)
rng = np.random.default_rng(42)
noise = rng.normal(0, 0.02, size=len(rv3))

print()
print("  rv x1.10 sensitivity vs lower-clamp bound  (EMA span=3, all configs)")
print(f"  {'lo':>6}  {'baseline':>10}  {'rv x0.90':>10}  {'rv x1.10':>10}  {'drop 1.10':>10}  {'noise':>10}  {'OOS H2':>8}  stress?")
print(f"  {'-'*6}  {'-'*10}  {'-'*10}  {'-'*10}  {'-'*10}  {'-'*10}  {'-'*8}  -------")

results = {}
for lo in [-0.05, -0.04, -0.03, -0.02, -0.01, 0.00]:
    p_b   = build_pnl(base, sv36, lf, s4, rv3,        lo)
    p_09  = build_pnl(base, sv36, lf, s4, rv3 * 0.90, lo)
    p_11  = build_pnl(base, sv36, lf, s4, rv3 * 1.10, lo)
    p_n   = build_pnl(base, sv36, lf, s4, (rv3 + noise).clip(0.02), lo)
    sb    = sh(p_b[test_mask])
    s09   = sh(p_09[test_mask])
    s11   = sh(p_11[test_mask])
    sn_   = sh(p_n[test_mask])
    sh2   = sh(p_b[second_half])
    drop  = s11 - sb
    max_d = max(abs(s09 - sb), abs(s11 - sb), abs(sn_ - sb))
    ok    = 'PASS' if max_d < 0.15 else 'FAIL'
    print(f"  {lo:>6.2f}  {sb:>+10.4f}  {s09:>+10.4f}  {s11:>+10.4f}  {drop:>+10.4f}  {sn_:>+10.4f}  {sh2:>+8.4f}  {ok}")
    results[lo] = {'baseline': sb, 'rv09': s09, 'rv11': s11, 'noise': sn_, 'drop110': drop, 'oos_h2': sh2, 'max_drop': max_d, 'pass': ok == 'PASS'}

out = Path(OUT_DIR) / 'crypto_bsdt_v58_clamp_sweep.json'
with open(out, 'w') as f:
    json.dump({str(k): v for k, v in results.items()}, f, indent=2)
print(f"\n  Saved -> {out}")
