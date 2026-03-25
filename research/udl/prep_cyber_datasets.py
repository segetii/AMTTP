"""
Fetch and prepare modern cybersecurity datasets for anomaly detection benchmark.

Datasets (operational-grade complexity):
  1. NSL-KDD       — improved KDDCup99, no duplicates, harder test set
  2. UNSW-NB15     — 2015, 9 modern attack categories, 49 features
  3. Synthetic CyberOps — realistic multi-campaign cyber traffic (fallback)

All fetched from public GitHub mirrors of research data.
"""
import numpy as np
import pandas as pd
from pathlib import Path
from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.decomposition import PCA
from collections import Counter
import warnings
warnings.filterwarnings('ignore')

ROOT = Path(r'c:\amttp')
OUT  = ROOT / 'data' / 'external_validation' / 'cyber'
OUT.mkdir(parents=True, exist_ok=True)


def prep_and_save(name, X_raw, y, attack_types, outdir):
    """Standardize, PCA, save."""
    X = np.nan_to_num(X_raw.astype(np.float64), nan=0.0, posinf=10, neginf=-10)
    
    # Remove constant columns
    col_std = X.std(axis=0)
    valid = col_std > 1e-10
    X = X[:, valid]
    
    scaler = StandardScaler()
    Xs = scaler.fit_transform(X)
    Xs = np.clip(Xs, -10, 10)
    
    n10 = min(10, Xs.shape[1])
    n5  = min(5, Xs.shape[1])
    pca10 = PCA(n_components=n10, random_state=42)
    X10 = pca10.fit_transform(Xs)
    pca5 = PCA(n_components=n5, random_state=42)
    X5 = pca5.fit_transform(Xs)
    
    cat_counts = Counter(attack_types[y == 1])
    n_types = len(cat_counts)
    print(f"  Samples: {len(y):,}  Attacks: {y.sum():,} ({100*y.mean():.1f}%)")
    for atype, cnt in sorted(cat_counts.items(), key=lambda x: -x[1]):
        print(f"    {str(atype):<20} {cnt:>6}")
    print(f"  Features: {X.shape[1]}D -> PCA{n10} (var explained: {pca10.explained_variance_ratio_.sum():.3f})")
    
    np.savez_compressed(outdir / f'{name}.npz',
                        X_full=Xs, X10=X10, X5=X5,
                        y=y, attack_types=attack_types)
    print(f"  -> Saved {outdir / name}.npz")
    return True


# ======================================================================
#  1. NSL-KDD  (improved KDDCup99 -- no duplicates, harder test split)
#     Full: ~148K records. 41 features, 4 attack categories + normal
# ======================================================================
print("=" * 75)
print("  1. NSL-KDD (improved KDDCup99, no duplicates)")
print("=" * 75)

nsl_ok = False

# Column names for NSL-KDD (41 features + class + difficulty)
nsl_cols = ['duration','protocol_type','service','flag','src_bytes','dst_bytes',
            'land','wrong_fragment','urgent','hot','num_failed_logins','logged_in',
            'num_compromised','root_shell','su_attempted','num_root','num_file_creations',
            'num_shells','num_access_files','num_outbound_cmds','is_host_login',
            'is_guest_login','count','srv_count','serror_rate','srv_serror_rate',
            'rerror_rate','srv_rerror_rate','same_srv_rate','diff_srv_rate',
            'srv_diff_host_rate','dst_host_count','dst_host_srv_count',
            'dst_host_same_srv_rate','dst_host_diff_srv_rate',
            'dst_host_same_src_port_rate','dst_host_srv_diff_host_rate',
            'dst_host_serror_rate','dst_host_srv_serror_rate',
            'dst_host_rerror_rate','dst_host_srv_rerror_rate',
            'class','difficulty']

nsl_urls = [
    ("https://raw.githubusercontent.com/defcom17/NSL_KDD/master/KDDTrain+.txt",
     "https://raw.githubusercontent.com/defcom17/NSL_KDD/master/KDDTest+.txt"),
    ("https://raw.githubusercontent.com/jmnwong/NSL-KDD-Dataset/master/KDDTrain+.txt",
     "https://raw.githubusercontent.com/jmnwong/NSL-KDD-Dataset/master/KDDTest+.txt"),
]

for train_url, test_url in nsl_urls:
    try:
        print(f"  Trying: {train_url.split('github.com/')[-1].split('/KDD')[0]}...")
        df_train = pd.read_csv(train_url, header=None, names=nsl_cols)
        df_test  = pd.read_csv(test_url, header=None, names=nsl_cols)
        df_nsl = pd.concat([df_train, df_test], ignore_index=True)
        print(f"  OK: train={len(df_train):,} test={len(df_test):,} total={len(df_nsl):,}")
        nsl_ok = True
        break
    except Exception as e:
        print(f"  Failed: {e}")

if nsl_ok:
    # Attack category mapping
    dos_attacks = {'back','land','neptune','pod','smurf','teardrop','apache2','udpstorm',
                   'processtable','worm','mailbomb'}
    probe_attacks = {'satan','ipsweep','nmap','portsweep','mscan','saint'}
    r2l_attacks = {'guess_passwd','ftp_write','imap','phf','multihop','warezmaster',
                   'warezclient','spy','xlock','xsnoop','snmpguess','snmpgetattack',
                   'httptunnel','sendmail','named'}
    u2r_attacks = {'buffer_overflow','loadmodule','rootkit','perl','sqlattack','xterm','ps'}
    
    raw_labels = df_nsl['class'].astype(str).str.strip()
    y_nsl = (raw_labels != 'normal').astype(np.int32).values
    
    attack_cats = []
    for a in raw_labels:
        al = a.lower().strip()
        if al == 'normal':
            attack_cats.append('normal')
        elif al in dos_attacks:
            attack_cats.append('DoS')
        elif al in probe_attacks:
            attack_cats.append('Probe')
        elif al in r2l_attacks:
            attack_cats.append('R2L')
        elif al in u2r_attacks:
            attack_cats.append('U2R')
        else:
            attack_cats.append(f'Other({a})')
    attack_cats = np.array(attack_cats)
    
    # Encode categorical features
    df_feat = df_nsl.drop(columns=['class', 'difficulty'])
    for c in ['protocol_type', 'service', 'flag']:
        le = LabelEncoder()
        df_feat[c] = le.fit_transform(df_feat[c].astype(str))
    
    X_nsl = df_feat.values.astype(np.float64)
    prep_and_save('nsl_kdd', X_nsl, y_nsl, attack_cats, OUT)
else:
    print("  [SKIPPED] Could not fetch NSL-KDD")


# ======================================================================
#  2. UNSW-NB15  (2015, ADFA, realistic modern attacks)
#     49 features, 9 attack types, ~250K records
# ======================================================================
print("\n" + "=" * 75)
print("  2. UNSW-NB15 (modern attack categories)")
print("=" * 75)

unsw_ok = False

unsw_urls = [
    ("https://raw.githubusercontent.com/InitRoot/UNSW_NB15/master/UNSW_NB15_training-set.csv",
     "https://raw.githubusercontent.com/InitRoot/UNSW_NB15/master/UNSW_NB15_testing-set.csv"),
]

for train_url, test_url in unsw_urls:
    try:
        print(f"  Trying GitHub mirror...")
        df_train = pd.read_csv(train_url)
        df_test  = pd.read_csv(test_url)
        df_unsw = pd.concat([df_train, df_test], ignore_index=True)
        print(f"  OK: train={len(df_train):,} test={len(df_test):,} total={len(df_unsw):,}")
        print(f"  Columns: {df_unsw.columns.tolist()[:10]}...")
        unsw_ok = True
        break
    except Exception as e:
        print(f"  Failed: {e}")

if unsw_ok:
    # Find columns
    label_col = 'label' if 'label' in df_unsw.columns else 'Label'
    cat_col = 'attack_cat' if 'attack_cat' in df_unsw.columns else None
    
    if label_col in df_unsw.columns:
        y_unsw = df_unsw[label_col].astype(int).values
    else:
        print(f"  Columns available: {df_unsw.columns.tolist()}")
        y_unsw = None
    
    if y_unsw is not None:
        if cat_col and cat_col in df_unsw.columns:
            attack_types = df_unsw[cat_col].astype(str).str.strip().values
        else:
            attack_types = np.where(y_unsw == 1, 'attack', 'normal')
        
        # Drop ID, label, attack_cat
        drop = [c for c in ['id', 'ID', label_col, cat_col] if c and c in df_unsw.columns]
        df_feat = df_unsw.drop(columns=drop, errors='ignore')
        
        for c in df_feat.select_dtypes(include=['object', 'category']).columns:
            le = LabelEncoder()
            df_feat[c] = le.fit_transform(df_feat[c].astype(str))
        
        X_unsw = df_feat.values.astype(np.float64)
        prep_and_save('unsw_nb15', X_unsw, y_unsw, attack_types, OUT)
    else:
        print("  [SKIPPED] Label column not found")
else:
    print("  [SKIPPED] Could not fetch UNSW-NB15")


# ======================================================================
#  3. Synthetic CyberOps  (realistic multi-campaign traffic)
#     ~78K samples, 33 features, 7 distinct attack campaign types
#     Mimics CICFlowMeter / Zeek network flow data
# ======================================================================
print("\n" + "=" * 75)
print("  3. Synthetic CyberOps (realistic multi-campaign traffic)")
print("=" * 75)

rng = np.random.RandomState(2024)

# 33-feature flow vector mimicking CICFlowMeter output
d = 33

def make_normal_http(n, rng):
    return np.abs(np.column_stack([
        rng.exponential(2.0, n), rng.poisson(15, n), rng.poisson(25, n),
        200+rng.randn(n)*80, 600+rng.randn(n)*200, rng.exponential(5e5, n),
        rng.exponential(500, n), rng.exponential(0.05, n), rng.exponential(0.03, n),
        rng.binomial(1,0.8,n), rng.binomial(1,0.9,n), np.zeros(n), np.zeros(n),
        rng.poisson(20,n)*20, rng.poisson(30,n)*20, 400+rng.randn(n)*150,
        200+rng.randn(n)*80, 600+rng.randn(n)*200, rng.poisson(15,n), rng.poisson(25,n),
        8192+rng.randn(n)*2000, 65535*np.ones(n), rng.poisson(10,n), 20*np.ones(n),
        rng.exponential(0.5,n), rng.exponential(0.2,n), rng.exponential(5,n),
        rng.exponential(2,n), np.full(n,80), np.full(n,6),
        rng.poisson(15,n)*(200+rng.randn(n)*80), rng.poisson(25,n)*(600+rng.randn(n)*200),
        rng.exponential(0.1,n)
    ]))

def make_normal_dns(n, rng):
    return np.abs(np.column_stack([
        rng.exponential(0.01,n), 1+rng.poisson(1,n), 1+rng.poisson(1,n),
        50+rng.randn(n)*15, 80+rng.randn(n)*30, rng.exponential(1e4,n),
        rng.exponential(200,n), rng.exponential(0.001,n), rng.exponential(0.001,n),
        np.zeros(n), np.zeros(n), np.zeros(n), np.zeros(n),
        20*(1+rng.poisson(1,n)), 20*(1+rng.poisson(1,n)), 70+rng.randn(n)*20,
        50+rng.randn(n)*15, 80+rng.randn(n)*30, 1+rng.poisson(1,n), 1+rng.poisson(1,n),
        512*np.ones(n), 512*np.ones(n), np.ones(n), 20*np.ones(n),
        rng.exponential(0.001,n), rng.exponential(0.0005,n), rng.exponential(0.1,n),
        rng.exponential(0.05,n), np.full(n,53), np.full(n,17),
        (1+rng.poisson(1,n))*(50+rng.randn(n)*15), (1+rng.poisson(1,n))*(80+rng.randn(n)*30),
        rng.exponential(0.002,n)
    ]))

def make_normal_https(n, rng):
    return np.abs(np.column_stack([
        rng.exponential(3.0,n), rng.poisson(20,n), rng.poisson(40,n),
        300+rng.randn(n)*100, 800+rng.randn(n)*300, rng.exponential(8e5,n),
        rng.exponential(600,n), rng.exponential(0.04,n), rng.exponential(0.02,n),
        rng.binomial(1,0.7,n), rng.binomial(1,0.8,n), np.zeros(n), np.zeros(n),
        rng.poisson(25,n)*20, rng.poisson(45,n)*20, 550+rng.randn(n)*180,
        300+rng.randn(n)*100, 800+rng.randn(n)*300, rng.poisson(20,n), rng.poisson(40,n),
        16384+rng.randn(n)*4000, 65535*np.ones(n), rng.poisson(15,n), 20*np.ones(n),
        rng.exponential(0.8,n), rng.exponential(0.3,n), rng.exponential(3,n),
        rng.exponential(1,n), np.full(n,443), np.full(n,6),
        rng.poisson(20,n)*(300+rng.randn(n)*100), rng.poisson(40,n)*(800+rng.randn(n)*300),
        rng.exponential(0.08,n)
    ]))

def make_normal_ssh(n, rng):
    return np.abs(np.column_stack([
        rng.exponential(30,n), rng.poisson(50,n), rng.poisson(60,n),
        100+rng.randn(n)*50, 150+rng.randn(n)*80, rng.exponential(2e4,n),
        rng.exponential(100,n), rng.exponential(0.5,n), rng.exponential(0.3,n),
        rng.binomial(1,0.6,n), rng.binomial(1,0.7,n), np.zeros(n), np.zeros(n),
        rng.poisson(50,n)*20, rng.poisson(60,n)*20, 130+rng.randn(n)*60,
        100+rng.randn(n)*50, 150+rng.randn(n)*80, rng.poisson(50,n), rng.poisson(60,n),
        32768+rng.randn(n)*5000, 32768+rng.randn(n)*5000, rng.poisson(40,n), 20*np.ones(n),
        rng.exponential(2,n), rng.exponential(1,n), rng.exponential(10,n),
        rng.exponential(5,n), np.full(n,22), np.full(n,6),
        rng.poisson(50,n)*(100+rng.randn(n)*50), rng.poisson(60,n)*(150+rng.randn(n)*80),
        rng.exponential(1,n)
    ]))

def make_normal_smtp(n, rng):
    return np.abs(np.column_stack([
        rng.exponential(1.5,n), rng.poisson(8,n), rng.poisson(5,n),
        400+rng.randn(n)*200, 100+rng.randn(n)*50, rng.exponential(3e5,n),
        rng.exponential(200,n), rng.exponential(0.1,n), rng.exponential(0.08,n),
        rng.binomial(1,0.5,n), rng.binomial(1,0.3,n), np.zeros(n), np.zeros(n),
        rng.poisson(8,n)*20, rng.poisson(5,n)*20, 300+rng.randn(n)*100,
        400+rng.randn(n)*200, 100+rng.randn(n)*50, rng.poisson(8,n), rng.poisson(5,n),
        8192+rng.randn(n)*2000, 16384+rng.randn(n)*4000, rng.poisson(6,n), 20*np.ones(n),
        rng.exponential(0.3,n), rng.exponential(0.1,n), rng.exponential(2,n),
        rng.exponential(0.8,n), np.full(n,25), np.full(n,6),
        rng.poisson(8,n)*(400+rng.randn(n)*200), rng.poisson(5,n)*(100+rng.randn(n)*50),
        rng.exponential(0.2,n)
    ]))

X_normal = np.vstack([
    make_normal_http(25000, rng),
    make_normal_dns(15000, rng),
    make_normal_https(20000, rng),
    make_normal_ssh(5000, rng),
    make_normal_smtp(3000, rng),
])
n_normal = len(X_normal)
print(f"  Normal traffic: {n_normal:,} flows across 5 protocol clusters")

# -- Attack campaigns --
attacks = {}

# 1. DDoS SYN Flood
n = 3500
attacks['DDoS_SYN_Flood'] = np.abs(np.column_stack([
    rng.exponential(0.001,n), rng.poisson(5000,n), rng.poisson(2,n),
    40+rng.randn(n)*5, rng.exponential(5,n), rng.exponential(1e8,n),
    rng.exponential(1e5,n), rng.exponential(0.00001,n), rng.exponential(0.001,n),
    np.zeros(n), np.zeros(n), np.zeros(n), np.zeros(n),
    rng.poisson(5000,n)*20, rng.poisson(2,n)*20, 40+rng.randn(n)*3,
    40+rng.randn(n)*5, rng.exponential(5,n), rng.poisson(5000,n), rng.poisson(2,n),
    1024*np.ones(n), np.zeros(n), np.zeros(n), 20*np.ones(n),
    rng.exponential(0.0001,n), rng.exponential(0.00005,n), np.zeros(n), np.zeros(n),
    np.full(n,80), np.full(n,6),
    rng.poisson(5000,n)*40, rng.poisson(2,n)*5, rng.exponential(0.00002,n)
]))

# 2. DDoS HTTP Flood
n = 2000
attacks['DDoS_HTTP_Flood'] = np.abs(np.column_stack([
    rng.exponential(0.5,n), rng.poisson(100,n), rng.poisson(120,n),
    250+rng.randn(n)*30, 500+rng.randn(n)*50, rng.exponential(2e6,n),
    rng.exponential(5000,n), rng.exponential(0.002,n), rng.exponential(0.001,n),
    np.ones(n), np.ones(n), np.zeros(n), np.zeros(n),
    rng.poisson(100,n)*20, rng.poisson(120,n)*20, 380+rng.randn(n)*30,
    250+rng.randn(n)*30, 500+rng.randn(n)*50, rng.poisson(100,n), rng.poisson(120,n),
    8192+rng.randn(n)*500, 65535*np.ones(n), rng.poisson(80,n), 20*np.ones(n),
    rng.exponential(0.01,n), rng.exponential(0.005,n), rng.exponential(0.1,n),
    rng.exponential(0.05,n), np.full(n,80), np.full(n,6),
    rng.poisson(100,n)*250, rng.poisson(120,n)*500, rng.exponential(0.005,n)
]))

# 3. Brute Force SSH
n = 800
attacks['BruteForce_SSH'] = np.abs(np.column_stack([
    rng.exponential(0.3,n), rng.poisson(5,n)+3, rng.poisson(3,n)+2,
    80+rng.randn(n)*20, 60+rng.randn(n)*15, rng.exponential(5000,n),
    rng.exponential(50,n), 0.05+rng.exponential(0.02,n), 0.03+rng.exponential(0.01,n),
    rng.binomial(1,0.4,n), rng.binomial(1,0.3,n), np.zeros(n), np.zeros(n),
    (rng.poisson(5,n)+3)*20, (rng.poisson(3,n)+2)*20, 70+rng.randn(n)*15,
    80+rng.randn(n)*20, 60+rng.randn(n)*15, rng.poisson(5,n)+3, rng.poisson(3,n)+2,
    32768*np.ones(n), 32768*np.ones(n), rng.poisson(3,n), 20*np.ones(n),
    rng.exponential(0.1,n), rng.exponential(0.05,n), 0.05+rng.exponential(0.02,n),
    rng.exponential(0.005,n), np.full(n,22), np.full(n,6),
    (rng.poisson(5,n)+3)*80, (rng.poisson(3,n)+2)*60, rng.exponential(0.01,n)
]))

# 4. Port Scan (SYN)
n = 2000
attacks['PortScan'] = np.abs(np.column_stack([
    rng.exponential(0.0005,n), 1+rng.binomial(1,0.1,n), rng.binomial(1,0.3,n),
    44+rng.randn(n)*2, 44*rng.binomial(1,0.3,n), rng.exponential(1e5,n),
    rng.exponential(3000,n), rng.exponential(0.0001,n), rng.exponential(0.0001,n),
    np.zeros(n), np.zeros(n), np.zeros(n), np.zeros(n),
    20*(1+rng.binomial(1,0.1,n)), 20*rng.binomial(1,0.3,n), 44+rng.randn(n)*3,
    44+rng.randn(n)*2, 44*rng.binomial(1,0.3,n), np.ones(n), rng.binomial(1,0.3,n),
    1024*np.ones(n), 1024*rng.binomial(1,0.3,n), np.zeros(n), 20*np.ones(n),
    rng.exponential(0.00001,n), rng.exponential(0.000005,n), np.zeros(n), np.zeros(n),
    rng.randint(1,65535,n), np.full(n,6),
    44*(1+rng.binomial(1,0.1,n)), 44*rng.binomial(1,0.3,n), rng.exponential(0.0002,n)
]))

# 5. DNS Exfiltration
n = 300
attacks['DNS_Exfiltration'] = np.abs(np.column_stack([
    rng.exponential(0.1,n), rng.poisson(3,n)+1, rng.poisson(2,n)+1,
    200+rng.randn(n)*50, 150+rng.randn(n)*40, rng.exponential(5e4,n),
    rng.exponential(100,n), rng.exponential(0.005,n), rng.exponential(0.003,n),
    np.zeros(n), np.zeros(n), np.zeros(n), np.zeros(n),
    (rng.poisson(3,n)+1)*20, (rng.poisson(2,n)+1)*20, 180+rng.randn(n)*40,
    200+rng.randn(n)*50, 150+rng.randn(n)*40, rng.poisson(3,n)+1, rng.poisson(2,n)+1,
    512*np.ones(n), 512*np.ones(n), rng.poisson(2,n), 20*np.ones(n),
    rng.exponential(0.01,n), rng.exponential(0.005,n), rng.exponential(0.5,n),
    rng.exponential(0.2,n), np.full(n,53), np.full(n,17),
    (rng.poisson(3,n)+1)*200, (rng.poisson(2,n)+1)*150, rng.exponential(0.01,n)
]))

# 6. Botnet C2 Beaconing (ultra-regular intervals)
n = 600
beacon = 60 + rng.randn(n)*0.5  # 60s +/- 0.5s
attacks['Botnet_C2'] = np.abs(np.column_stack([
    rng.exponential(0.5,n), rng.poisson(3,n)+1, rng.poisson(2,n)+1,
    100+rng.randn(n)*20, 80+rng.randn(n)*15, rng.exponential(1000,n),
    rng.exponential(20,n), beacon, rng.exponential(0.1,n),
    rng.binomial(1,0.5,n), rng.binomial(1,0.5,n), np.zeros(n), np.zeros(n),
    (rng.poisson(3,n)+1)*20, (rng.poisson(2,n)+1)*20, 90+rng.randn(n)*15,
    100+rng.randn(n)*20, 80+rng.randn(n)*15, rng.poisson(3,n)+1, rng.poisson(2,n)+1,
    16384+rng.randn(n)*1000, 16384+rng.randn(n)*1000, rng.poisson(2,n), 20*np.ones(n),
    rng.exponential(0.2,n), rng.exponential(0.05,n), beacon, 0.5+rng.exponential(0.1,n),
    np.full(n,443), np.full(n,6),
    (rng.poisson(3,n)+1)*100, (rng.poisson(2,n)+1)*80, rng.exponential(0.05,n)
]))

# 7. Web Application Attack (SQLi/XSS)
n = 400
attacks['WebApp_Attack'] = np.abs(np.column_stack([
    rng.exponential(1,n), rng.poisson(10,n)+2, rng.poisson(8,n)+1,
    800+rng.randn(n)*200, 300+rng.randn(n)*100, rng.exponential(5e5,n),
    rng.exponential(300,n), rng.exponential(0.05,n), rng.exponential(0.03,n),
    np.ones(n), rng.binomial(1,0.8,n), np.zeros(n), np.zeros(n),
    (rng.poisson(10,n)+2)*20, (rng.poisson(8,n)+1)*20, 550+rng.randn(n)*100,
    800+rng.randn(n)*200, 300+rng.randn(n)*100, rng.poisson(10,n)+2, rng.poisson(8,n)+1,
    8192+rng.randn(n)*2000, 65535*np.ones(n), rng.poisson(8,n), 20*np.ones(n),
    rng.exponential(0.3,n), rng.exponential(0.1,n), rng.exponential(2,n),
    rng.exponential(0.8,n), np.full(n,80), np.full(n,6),
    (rng.poisson(10,n)+2)*800, (rng.poisson(8,n)+1)*300, rng.exponential(0.1,n)
]))

# Assemble
X_attacks = np.vstack(list(attacks.values()))
type_labels = sum([[k]*len(v) for k,v in attacks.items()], [])
y_synth = np.concatenate([np.zeros(n_normal), np.ones(len(X_attacks))]).astype(np.int32)
atypes = np.array(['normal']*n_normal + type_labels)
X_synth = np.vstack([X_normal, X_attacks])

# Shuffle
perm = rng.permutation(len(y_synth))
X_synth, y_synth, atypes = X_synth[perm], y_synth[perm], atypes[perm]

prep_and_save('cyberops_synthetic', X_synth, y_synth, atypes, OUT)


# ======================================================================
#  SUMMARY
# ======================================================================
print("\n" + "=" * 75)
print("  CYBERSECURITY DATASET SUMMARY")
print("=" * 75)
for f in sorted(OUT.glob('*.npz')):
    data = np.load(f, allow_pickle=True)
    y = data['y']
    X = data.get('X10', data.get('X_full'))
    types = data.get('attack_types', None)
    n_types = len(set(types)) - 1 if types is not None else '?'
    print(f"  {f.stem:<25}  {len(y):>8,} samples  {int(y.sum()):>7,} attacks "
          f"({100*y.mean():5.1f}%)  {X.shape[1]:>3}D  {n_types} attack types")

kdd = ROOT / 'data' / 'external_validation' / 'kddcup99_cyber.npz'
if kdd.exists():
    data = np.load(kdd, allow_pickle=True)
    y = data['y']
    types = data.get('attack_types', None)
    n_types = len(set(types)) - 1 if types is not None else '?'
    print(f"  {'kddcup99 (legacy)':<25}  {len(y):>8,} samples  {int(y.sum()):>7,} attacks "
          f"({100*y.mean():5.1f}%)  {data['X10'].shape[1]:>3}D  {n_types} attack types")

print("\n  All datasets saved to:", OUT)
