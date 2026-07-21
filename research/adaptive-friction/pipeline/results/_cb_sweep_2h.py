"""Quick CB sweep for 2h-filtered signal — find optimal halt threshold."""
import numpy as np, pandas as pd
from collections import deque
from run_crypto_pairs_v34_full_combined import TRAIN_START, TEST_START
from run_crypto_pairs_v36_intraday_bsdt import CALIB_BARS
from test_daily_geometry_stop_tp_ohlc import build_daily_geometry, fetch_futures_ohlcv
from test_psi_adaptive_y import BASE, simulate_unit_with_psi
from test_dynamic_profit_sizing import _percentile_against

INIT = 1000.0; H = 24

df_1h, comp_raw, _ = build_daily_geometry()
ohlc_all = fetch_futures_ohlcv()
ohlc = ohlc_all[ohlc_all.index >= comp_raw.dropna().index.min()].copy()
hours = ohlc.index

idx = df_1h.index; train_1h = (idx >= TRAIN_START) & (idx < TEST_START)
train_idx = np.where(train_1h)[0]
cm = np.zeros(len(df_1h), dtype=bool); cm[train_idx[-CALIB_BARS:]] = True
hourly_cal = comp_raw[cm].abs().dropna()
sig_shifted = comp_raw.shift(1).reindex(hours).fillna(0.0).values.astype(float)
hth = float(hourly_cal.quantile(BASE['q_hourly']))
hpos = np.where(np.abs(sig_shifted) >= hth, np.sign(sig_shifted).astype(int), 0)
hq   = _percentile_against(np.abs(sig_shifted), hourly_cal.values)

comp_2h  = comp_raw.resample('2h').last().dropna()
train_2h = (comp_2h.index >= pd.Timestamp(TRAIN_START)) & (comp_2h.index < pd.Timestamp(TEST_START))
cal_2h   = comp_2h[train_2h].abs().dropna()
tth      = float(cal_2h.quantile(BASE['q_daily']))
t2h_vals = comp_2h.shift(1).reindex(hours, method='ffill').fillna(0.0).values.astype(float)
tpos     = np.sign(t2h_vals).astype(int)
tactive  = np.abs(t2h_vals) >= tth
tq       = _percentile_against(np.abs(t2h_vals), cal_2h.values)
confirm  = (tactive & (tpos == hpos) & (hpos != 0)).astype(float)

all_days   = pd.Index(sorted(ohlc_all.index.normalize().unique()))
calib_days = all_days[(all_days >= pd.Timestamp(TRAIN_START)) & (all_days < pd.Timestamp(TEST_START))]
ret_daily  = ohlc_all['close'].pct_change().fillna(0.0).groupby(ohlc_all.index.normalize()).sum()
daily_vol  = float(ret_daily.reindex(calib_days).std())
sl = BASE['sl_mult'] * daily_vol; tp = BASE['tp_mult'] * daily_vol

ret_h  = ohlc_all['close'].pct_change().fillna(0.0)
rv     = ret_h.rolling(24, min_periods=12).std().shift(1)
rv_cal = rv[(rv.index >= pd.Timestamp(TRAIN_START)) & (rv.index < pd.Timestamp(TEST_START))].dropna()
rv_h   = rv.reindex(hours).ffill().fillna(rv_cal.median())
stress_rank = _percentile_against(rv_h.values, rv_cal.values)
vol_base    = (float(rv_cal.median()) / rv_h.clip(lower=1e-8)).values

unit0_arr, _ = simulate_unit_with_psi(
    ohlc['open'].values.astype(float), ohlc['high'].values.astype(float),
    ohlc['low'].values.astype(float),  ohlc['close'].values.astype(float),
    hpos, tpos, tactive, np.ones(len(hours)), sl, tp)
unit0   = pd.Series(unit0_arr, index=hours)
roll_mu = unit0.rolling(240, min_periods=72).mean().shift(1).fillna(0.0)
roll_sd = unit0.rolling(240, min_periods=72).std().shift(1).replace(0, np.nan).fillna(unit0.std())
q_quality    = 0.25 + 1.25 / (1.0 + np.exp(-np.clip(roll_mu / roll_sd * np.sqrt(24*365.25) * 0.50, -50, 50)))
strength_raw = hq * (1.0 + tq) * (1.0 + confirm) / 4.0
sm_mult      = np.clip(0.25 + 2.5 * strength_raw, 0.25, 2.5)
delta        = 1.2 - stress_rank
gamma        = np.clip(np.sign(delta) * delta**2, 0.4, 1.3)
size_mult    = np.clip(sm_mult * q_quality * np.clip(vol_base, 0.25, 3.0) * gamma, 0.0, 2.0)

unit_arr, _ = simulate_unit_with_psi(
    ohlc['open'].values.astype(float), ohlc['high'].values.astype(float),
    ohlc['low'].values.astype(float),  ohlc['close'].values.astype(float),
    hpos, tpos, tactive, size_mult, sl, tp)
unit_base   = pd.Series(unit_arr, index=hours)
test_ts     = pd.Timestamp(TEST_START)

print(f'  daily_vol={daily_vol:.4f}  2h cal_size={len(cal_2h)}')
print()
hdr = f'  {"win":>6} {"halt":>6} {"resume":>7}  {"OOS $":>10}  {"OOS ret":>8}  {"maxdd":>8}  {"calmar":>8}  {"halted%":>8}  {"trips":>5}'
print(hdr); print('  ' + '-'*95)

for win in [60, 90, 120]:
    for halt in [0.15, 0.18, 0.20, 0.22, 0.25, 0.28]:
        resume = halt - 0.05
        wb = win * H; mono_dq = deque()
        eq = INIT; peak = INIT; halted = False; eq_v = []; cb_v = []
        for i, un in enumerate(unit_base):
            while mono_dq and mono_dq[0][0] <= i - wb: mono_dq.popleft()
            while mono_dq and mono_dq[-1][1] <= eq: mono_dq.pop()
            mono_dq.append((i, eq)); rp = mono_dq[0][1]
            dd_aty = max(0, 1 - eq / max(peak, 1e-12))
            cb_dd  = max(0, 1 - eq / max(rp,   1e-12))
            if not halted and cb_dd >= halt:   halted = True
            elif  halted and cb_dd <= resume:  halted = False
            y = (0.0 if halted else
                 1.0 if dd_aty <= 0.05 else
                 0.25 if dd_aty >= 0.20 else
                 0.25 + (1-0.25)*(0.20-dd_aty)/(0.20-0.05))
            r = max(3.0 * y * float(un), -0.95)
            eq *= (1 + r); peak = max(peak, eq)
            eq_v.append(eq); cb_v.append(int(halted))

        eqs = pd.Series(eq_v, index=hours)
        oos = eqs[eqs.index >= test_ts]
        n_oos = len(oos)
        dd = (oos - oos.cummax()) / oos.cummax(); mdd = float(dd.min())
        yrs = max((oos.index[-1] - oos.index[0]).days / 365.25, 1e-9)
        cagr = (oos.iloc[-1] / INIT) ** (1 / yrs) - 1
        calmar = cagr / max(abs(mdd), 1e-9)
        pct_h  = float(np.mean(cb_v[-n_oos:]))
        trips  = sum(cb_v[i] > cb_v[i-1] for i in range(1, len(cb_v)))
        mark   = '  <-- BEST' if calmar >= 2.0 else ''
        print(f'  {win:>6}d {halt:>5.0%} r={resume:.0%}  '
              f'{oos.iloc[-1]:>10,.2f}  {(oos.iloc[-1]/INIT-1):>+7.1%}  '
              f'{mdd:>+7.2%}  {calmar:>+8.3f}  {pct_h:>7.1%}  {trips:>5}{mark}')
    print()
