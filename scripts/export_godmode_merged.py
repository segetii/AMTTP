from pathlib import Path
import pandas as pd
import numpy as np

DATA_DIR = Path(r"C:\amttp\data")
OUT_PKL = DATA_DIR / "godmode_1h_2021_2026.pkl"
OUT_CSV = DATA_DIR / "godmode_1h_2021_2026.csv"

# load klines (price series)
kl_btc = pd.read_pickle(DATA_DIR / 'klines_BTCUSDT_1h.pkl') if (DATA_DIR / 'klines_BTCUSDT_1h.pkl').exists() else pd.Series(dtype=float)
kl_eth = pd.read_pickle(DATA_DIR / 'klines_ETHUSDT_1h.pkl') if (DATA_DIR / 'klines_ETHUSDT_1h.pkl').exists() else pd.Series(dtype=float)
kl_sol = pd.read_pickle(DATA_DIR / 'klines_SOLUSDT_1h.pkl') if (DATA_DIR / 'klines_SOLUSDT_1h.pkl').exists() else pd.Series(dtype=float)

# Normalize indices to naive timestamps
def _tz_to_naive(s: pd.Series) -> pd.Series:
    if s.empty:
        return s
    if hasattr(s.index, 'tz') and s.index.tz is not None:
        s = s.tz_convert(None)
    return s

kl_btc = _tz_to_naive(kl_btc)
kl_eth = _tz_to_naive(kl_eth)
kl_sol = _tz_to_naive(kl_sol)

# Build base_df similar to run_crypto_pairs_v34_full_combined.build_1h_df
base_df = pd.DataFrame({'eth': kl_eth, 'btc': kl_btc}).dropna()
has_sol = False
if not kl_sol.empty and kl_sol.index[0] <= pd.Timestamp('2021-06-01'):
    base_df = pd.concat([base_df, kl_sol.rename('sol')], axis=1).dropna()
    has_sol = True
else:
    # include sol as placeholder column with same index (will be filled later if needed)
    base_df['sol'] = kl_sol.reindex(base_df.index).fillna(method='ffill') if not kl_sol.empty else np.nan

# Compute derived columns
for a in ['eth','btc','sol']:
    base_df[f'ret_{a}'] = np.log(base_df[a] / base_df[a].shift(1))
    base_df[f'log_{a}'] = np.log(base_df[a])
base_df['btc_dom'] = base_df['ret_btc'] - base_df['ret_eth']
base_df['spread_eb'] = base_df['log_eth'] - base_df['log_btc']
base_df['spread_ret_eb'] = base_df['ret_eth'] - base_df['ret_btc']
base_df = base_df.dropna()

# Load microstructure caches and align
def load_and_align(name, default=pd.Series(dtype=float)):
    p = DATA_DIR / name
    if not p.exists():
        return pd.Series(dtype=float)
    s = pd.read_pickle(p)
    if isinstance(s, pd.DataFrame):
        # return first column if DataFrame
        if s.shape[1] == 1:
            s = s.iloc[:,0]
        else:
            # leave as dataframe
            return s.reindex(base_df.index).ffill()
    # tz handling
    if hasattr(s.index, 'tz') and s.index.tz is not None:
        s = s.tz_convert(None)
    s = s.reindex(base_df.index, method='ffill')
    return s

# tbr and funding and dv metrics
btc_tbr = load_and_align('binance_futures_BTCUSDT_1h_tbr.pkl')
eth_tbr = load_and_align('binance_futures_ETHUSDT_1h_tbr.pkl')
sol_tbr = load_and_align('binance_futures_SOLUSDT_1h_tbr.pkl')

btc_fr = load_and_align('binance_futures_BTCUSDT_1h_fr.pkl')
eth_fr = load_and_align('binance_futures_ETHUSDT_1h_fr.pkl')
sol_fr = load_and_align('binance_futures_SOLUSDT_1h_fr.pkl')

btc_dv = load_and_align('binance_futures_BTCUSDT_1h_dv_metrics.pkl')
eth_dv = load_and_align('binance_futures_ETHUSDT_1h_dv_metrics.pkl')
sol_dv = load_and_align('binance_futures_SOLUSDT_1h_dv_metrics.pkl')

# Merge microstructure fields into a single frame
ms = pd.DataFrame(index=base_df.index)
ms['btc_tbr'] = btc_tbr
ms['eth_tbr'] = eth_tbr
ms['sol_tbr'] = sol_tbr
ms['btc_funding'] = btc_fr
ms['eth_funding'] = eth_fr
ms['sol_funding'] = sol_fr

# dv metrics may be DataFrames
if isinstance(btc_dv, pd.DataFrame):
    for col in btc_dv.columns:
        ms[f'btc_{col}'] = btc_dv[col].reindex(base_df.index).ffill()
if isinstance(eth_dv, pd.DataFrame):
    for col in eth_dv.columns:
        ms[f'eth_{col}'] = eth_dv[col].reindex(base_df.index).ffill()
if isinstance(sol_dv, pd.DataFrame):
    for col in sol_dv.columns:
        ms[f'sol_{col}'] = sol_dv[col].reindex(base_df.index).ffill()

# Combine
merged = pd.concat([base_df, ms], axis=1)

# Save outputs
merged.to_pickle(OUT_PKL)
merged.to_csv(OUT_CSV)
print('Saved:', OUT_PKL, OUT_CSV)
