import numpy as np, pandas as pd, warnings
warnings.filterwarnings('ignore')
import yfinance as yf
from numpy.linalg import eigh

raw = {}
for tk in ['ETH-USD','BTC-USD']:
    raw[tk] = yf.download(tk, start='2019-01-01', progress=False, auto_adjust=True)['Close'].squeeze()
df = pd.DataFrame({'eth': raw['ETH-USD'], 'btc': raw['BTC-USD']}).dropna()
df['ret_eth']  = np.log(df['eth']/df['eth'].shift(1))
df['ret_btc']  = np.log(df['btc']/df['btc'].shift(1))
df['vol_eth']  = df['ret_eth'].rolling(20).std()*np.sqrt(252)
df['vol_btc']  = df['ret_btc'].rolling(20).std()*np.sqrt(252)
df['ret21_eth']= df['ret_eth'].rolling(21).sum()
df['ret5_eth'] = df['ret_eth'].rolling(5).sum()
df['mom_sign'] = np.sign(df['ret21_eth'])

def rolling_z(s, w=252):
    mu = s.rolling(w, min_periods=60).mean()
    si = s.rolling(w, min_periods=60).std()
    return (s-mu)/(si+1e-9)
for c in ['ret_eth','vol_eth','ret_btc','vol_btc']:
    df[c+'_z'] = rolling_z(df[c])
df = df.dropna()

print('=== Root Cause Diagnostics ===')
print()
print('1. Omega range:')
feats = ['ret_eth_z','vol_eth_z','ret_btc_z','vol_btc_z']
X = df[feats].values
omegas = []
for t in range(60, min(600, len(X))):
    wd = X[t-60:t+1]
    wd = wd[np.all(np.isfinite(wd),axis=1)]
    if len(wd) < 30: continue
    corr = np.corrcoef(wd.T)
    W = np.abs(corr)
    W = W / (W.sum(1, keepdims=True)+1e-12)
    lam = eigh(W)[0][-1]
    omegas.append(lam)
omegas = np.array(omegas)
print(f'   range = {omegas.min():.4f} to {omegas.max():.4f}  (span={omegas.max()-omegas.min():.4f})')
print(f'   SP500 Omega spanned 0.0 to 2.6 — crypto spans only {omegas.max()-omegas.min():.4f}')
print(f'   Percentile-rank on compressed range → all days look equally stressed')
print()

test = df[df.index >= '2023-01-01'].copy()
rc   = test['ret_eth'].rolling(60).corr(test['ret_btc'])
print('2. ETH/BTC rolling correlation [test 2023+]:')
print(f'   min={rc.min():.3f}  median={rc.median():.3f}  max={rc.max():.3f}')
pct_high = (rc>0.80).mean()*100
print(f'   % days corr>0.80: {pct_high:.1f}% -- pair strategy has barely any divergence to exploit')
print()

test['fwd5']  = test['ret_eth'].rolling(5).sum().shift(-5)
test['fwd21'] = test['ret_eth'].rolling(21).sum().shift(-21)
for H, col in [(5,'fwd5'), (21,'fwd21')]:
    valid = test['mom_sign'].notna() & test[col].notna()
    acc   = (np.sign(test.loc[valid,'mom_sign']) == np.sign(test.loc[valid,col])).mean()
    print(f'3. Momentum signal (21d lookback) -> fwd_{H}d accuracy: {acc:.3f}')
print()

print('4. Annual regime (long bias + trend):')
for yr in [2022, 2023, 2024, 2025]:
    ym  = (df.index.year == yr)
    if ym.sum() < 50: continue
    sub = df[ym]
    long_pct = (np.sign(sub['ret21_eth']) > 0).mean()
    up_pct   = (sub['ret_eth'] > 0).mean()
    cumr     = sub['ret_eth'].sum()
    print(f'   {yr}: mom_long={long_pct*100:.1f}%  daily_up={up_pct*100:.1f}%  cumret={cumr:+.3f}')
print()

print('5. WHY crash phase fires and hurts:')
print('   Crash phase = Omega rising + 21d return < -5%')
print('   But if corr(Omega, next_day) is negative, rising Omega = already peaked')
crash_m = (df['ret21_eth'] < -0.05)
tot = crash_m.sum()
up_next = (df['ret_eth'].shift(-1) > 0)[crash_m].sum()
print(f'   n crash days: {tot}')
print(f'   % next day positive (should short but market bounces): {up_next/max(tot,1)*100:.1f}%')
print()

print('6. Core structural issue:')
print('   In crypto, 21d momentum is MEAN-REVERTING at short horizons')
fwd1_acc  = (np.sign(df.loc[df['ret21_eth']<-0.05, 'mom_sign']) != np.sign(df.loc[df['ret21_eth']<-0.05, 'ret_eth'].shift(-1).fillna(0))).mean()
print(f'   When 21d_ret < -5%, next-day momentum OPPOSITE of prediction: {fwd1_acc*100:.1f}% of time')
print('   -> The features/volatility regime that worked for SP500 do not transfer')
print('      without re-calibrating thresholds to crypto volatility scale')
