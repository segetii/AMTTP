"""Build daily supply Omega from supply_hourly (5 coupled energy source agents)."""
import numpy as np
import pandas as pd
import warnings
warnings.filterwarnings('ignore')

DATA_DIR = r'C:\amttp\data\ercot'

def compute_omega(X_2d, window=30):
    T, N = X_2d.shape
    omega = np.zeros(T)
    for t in range(T):
        lo = max(0, t - window)
        wd = X_2d[lo:t+1]
        if wd.shape[0] < 4:
            continue
        corr = np.corrcoef(wd.T)
        if not np.all(np.isfinite(corr)):
            corr = np.where(np.isfinite(corr), corr, 0.0)
            np.fill_diagonal(corr, 1.0)
        upper = corr[np.triu_indices(N, k=1)]
        rho = float(np.mean(np.abs(upper)))
        ell = float(np.mean(np.abs(X_2d[t])))
        W = np.abs(corr)
        W = W / (W.sum(1, keepdims=True) + 1e-12)
        omega[t] = rho * ell * float(np.linalg.eigvalsh(W)[-1])
    return omega


print("=" * 70)
print("ERCOT DAILY SUPPLY — Omega from supply_hourly daily aggregates")
print("Energy sources (wind/solar/gas/coal/nuclear) as coupled agents")
print("=" * 70)

# Load hourly supply
data = np.load(f'{DATA_DIR}/ercot_supply_hourly.npz', allow_pickle=True)
X_raw  = data['X']
dates  = pd.to_datetime(data['dates'])
y_hr   = data['y']
feat   = list(data['feature_names'])
print(f"\nHourly supply: {X_raw.shape}  features: {feat}")

# Aggregate to daily mean capacity factors
df = pd.DataFrame(X_raw, index=dates, columns=feat)
df['y'] = y_hr
daily_cf   = df.groupby(df.index.date)[feat].mean()
daily_y    = df.groupby(df.index.date)['y'].max()
daily_dates = pd.to_datetime(daily_cf.index)

print(f"Daily supply: {daily_cf.shape}  dates: {daily_dates[0].date()} -> {daily_dates[-1].date()}")
print(f"Crisis days (y=1): {int(daily_y.sum())}")

# Also keep daily std (volatility of each source) as extra feature set
daily_std = df.groupby(df.index.date)[feat].std()

# z-score on 2019 (normal period)
X_cf  = daily_cf.values
normal_mask = np.array(daily_dates.year == 2019)
mu = X_cf[normal_mask].mean(0)
sd = X_cf[normal_mask].std(0) + 1e-8
X_std = (X_cf - mu) / sd

print(f"\nNormal period (2019): {normal_mask.sum()} days")
print(f"Normal mean capacity factors: {dict(zip(feat, mu.round(3)))}")

# Compute Omega (daily, window=30d)
print("\nComputing Omega (window=30d, N=5 coupled sources)...")
omega = compute_omega(X_std, window=30)
print(f"Done. Omega range: [{omega.min():.4f}, {omega.max():.4f}]")

print(f"\nOmega global: min={omega.min():.4f}  mean={omega.mean():.4f}  "
      f"median={np.median(omega):.4f}  p90={np.percentile(omega,90):.4f}  max={omega.max():.4f}")
print(f"Pct above C_man (Omega>1): {(omega>1.0).mean()*100:.3f}%  ({(omega>1.0).sum()} days)")

# By year/period
print(f"\nOmega by year/period:")
print(f"  {'Period':>30}  {'Mean':>8}  {'Max':>8}  {'%>0.5':>7}  {'%>1.0':>7}")
periods = [
    ("Normal 2019",       daily_dates.year == 2019),
    ("2020 full",         daily_dates.year == 2020),
    ("COVID Mar-Apr 2020",(daily_dates.year==2020) & (daily_dates.month.isin([3,4]))),
    ("Pre-Uri Jan 2021",  (daily_dates.year==2021) & (daily_dates.month==1)),
    ("Uri Feb 2021",      (daily_dates.year==2021) & (daily_dates.month==2)),
    ("Post-Uri 2021 H2",  (daily_dates.year==2021) & (daily_dates.month>=3)),
    ("2022 full",         daily_dates.year == 2022),
    ("Summer Peak Jul-Aug 2022", (daily_dates.year==2022) & (daily_dates.month.isin([7,8]))),
    ("Elliott Dec 2022",  (daily_dates.year==2022) & (daily_dates.month==12)),
]
for p_name, pmask in periods:
    pmask = np.array(pmask)
    if not pmask.any():
        continue
    ow = omega[pmask]
    print(f"  {p_name:>30}  {ow.mean():>8.4f}  {ow.max():>8.4f}  "
          f"{(ow>0.5).mean()*100:>7.1f}%  {(ow>1.0).mean()*100:>7.1f}%")

# Lead-time analysis
print(f"\nEarly-warning lead-time (daily supply Omega):")
events = {
    "COVID_Collapse 2020-03-23":     pd.Timestamp("2020-03-23"),
    "WinterStormUri 2021-02-10":     pd.Timestamp("2021-02-10"),
    "WinterStormElliott 2022-12-22": pd.Timestamp("2022-12-22"),
}
print(f"  {'Event':>32}  {'Thr':>4}  {'FirstAlarm':>12}  {'Lead(d)':>8}  {'HR':>6}  {'FAR':>6}")
for ev_name, onset_dt in events.items():
    onset_idx = int(np.searchsorted(daily_dates, onset_dt))
    crisis_end = min(len(omega), onset_idx + 14)
    crisis_mask = np.zeros(len(omega), dtype=bool)
    crisis_mask[onset_idx:crisis_end] = True
    for thr in [0.3, 0.5, 0.7, 0.9, 1.0]:
        alarm = omega > thr
        pre = np.where(alarm[:onset_idx])[0]
        ev_display = ev_name if thr == 0.3 else ""
        if len(pre) == 0:
            print(f"  {ev_display:>32}  {thr:>4.1f}  {'never':>12}")
            continue
        first = int(pre[0])
        lead = onset_idx - first
        hr   = float(alarm[crisis_mask].mean())
        far  = float(alarm[normal_mask].mean())
        alarm_date = str(daily_dates[first].date())
        print(f"  {ev_display:>32}  {thr:>4.1f}  {alarm_date:>12}  {lead:>8}  {hr:>6.3f}  {far:>6.3f}")
    lo = max(0, onset_idx - 30)
    hi = min(len(omega), onset_idx + 14)
    print(f"  {'':>32}       peak_Omega_[-30d,+14d]={omega[lo:hi].max():.4f}")

# Uri detailed day-by-day
print(f"\nUri Feb 2021 — daily Omega day-by-day:")
print(f"  {'Date':>12}  {'Omega':>8}  {'AboveCman':>10}  {'y':>4}")
jan_feb21 = np.array((daily_dates.year==2021) & (daily_dates.month.isin([1,2])))
for i in np.where(jan_feb21)[0]:
    marker = " ***CMAN" if omega[i] > 1.0 else ""
    crisis_flag = " <<CRISIS" if int(daily_y.iloc[i]) == 1 else ""
    print(f"  {str(daily_dates[i].date()):>12}  {omega[i]:>8.4f}  "
          f"{'YES' if omega[i]>1.0 else '':>10}  {int(daily_y.iloc[i]):>4}{marker}{crisis_flag}")

# Elliott detailed
print(f"\nElliott Dec 2022 — daily Omega:")
print(f"  {'Date':>12}  {'Omega':>8}  {'y':>4}")
dec22 = np.array((daily_dates.year==2022) & (daily_dates.month.isin([11,12])))
for i in np.where(dec22)[0]:
    crisis_flag = " <<CRISIS" if int(daily_y.iloc[i]) == 1 else ""
    print(f"  {str(daily_dates[i].date()):>12}  {omega[i]:>8.4f}  "
          f"{'***' if omega[i]>1.0 else '':>5}  {int(daily_y.iloc[i]):>4}{crisis_flag}")

print("\nDone.")
