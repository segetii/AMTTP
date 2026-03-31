import numpy as np
from sklearn.metrics import roc_auc_score

npz = np.load(r'c:\amttp\data\ercot\ercot_daily_2018_2022.npz', allow_pickle=True)
X, y, dates, labels = npz['X'], npz['y'], npz['dates'], npz['labels']
fnames = ['load_mean_gw','load_std_gw','load_max_gw','ramp_rate','temp_f','load_temp_ixn']

# Test set: 2020+
test  = np.array([str(d)[:10] >= '2020-01-01' for d in dates])
train = ~test
X_test = X[test]
y_test = y[test]

print('RAW FEATURE INDIVIDUAL AUCs (test set 2020+):')
for j, fn in enumerate(fnames):
    col = X_test[:, j]
    col_fill = np.where(np.isnan(col), np.nanmean(col), col)
    auc = roc_auc_score(y_test, col_fill)
    print(f'  [{j}] {fn:<22}: AUC(high=anom)={auc:.4f}   AUC(low=anom)={1-auc:.4f}')

# Check event groups
uri    = np.array([labels[i] == 'WinterStormUri'     for i in range(len(dates))])
covid  = np.array([labels[i] == 'COVID_Collapse'     for i in range(len(dates))])
normal = (y == 0)

print()
print('FEATURE MEANS by GROUP:')
print(f"  {'Feature':<22} {'Normal-train':>12} {'Uri':>10} {'COVID':>10} {'NormDiff(Uri)':>14}")
for j, fn in enumerate(fnames):
    n_mu = float(np.nanmean(X[normal & train, j]))
    n_sd = float(np.nanstd(X[normal & train, j]))
    u_mu = float(np.nanmean(X[uri, j]))
    c_mu = float(np.nanmean(X[covid, j]))
    z_u  = (u_mu - n_mu) / (n_sd + 1e-9)
    print(f'  {fn:<22}: {n_mu:12.3f} {u_mu:10.3f} {c_mu:10.3f} {z_u:+14.2f}σ')

print()
print('Uri dates and raw feature values:')
for i in range(len(dates)):
    if labels[i] == 'WinterStormUri':
        feats = ' | '.join([f'{X[i,j]:.2f}' for j in range(6)])
        print(f'  {dates[i]}: [{feats}]')
