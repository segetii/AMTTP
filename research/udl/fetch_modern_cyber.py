"""
Download and prepare REAL modern cybersecurity benchmark datasets.

1. CIC-IDS-2017 V2 (Zenodo) - THE standard modern IDS benchmark, normalized
   ~2.8M flows, 78+ features, 15 attack types across 5 days
   
2. Full KDDCup99 (OpenML, 494K) - larger than current 108K subsample

3. UNSW-NB15 (already have, 54K)
4. NSL-KDD (already have, 148K)
"""
import numpy as np
import pandas as pd
from pathlib import Path
from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.decomposition import PCA
from collections import Counter
import warnings, time, io, zipfile
warnings.filterwarnings('ignore')

ROOT = Path(r'c:\amttp')
OUT  = ROOT / 'data' / 'external_validation' / 'cyber'
OUT.mkdir(parents=True, exist_ok=True)


def prep_and_save(name, X_raw, y, attack_types, outdir):
    """Standardize, PCA reduce, save as .npz."""
    X = np.nan_to_num(X_raw.astype(np.float64), nan=0.0, posinf=10, neginf=-10)
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
    print(f"  Samples: {len(y):,}  Attacks: {y.sum():,} ({100*y.mean():.1f}%)")
    for atype, cnt in sorted(cat_counts.items(), key=lambda x: -x[1])[:12]:
        print(f"    {str(atype):<25} {cnt:>8}")
    print(f"  Features: {X.shape[1]}D -> PCA{n10} (var explained: {pca10.explained_variance_ratio_.sum():.3f})")

    np.savez_compressed(outdir / f'{name}.npz',
                        X_full=Xs, X10=X10, X5=X5,
                        y=y, attack_types=attack_types)
    print(f"  -> Saved {outdir / name}.npz ({(outdir / f'{name}.npz').stat().st_size / 1e6:.1f} MB)")
    return True


# ======================================================================
#  1. CIC-IDS-2017 V2  (Zenodo, 369 MB zip)
#     THE gold standard modern network intrusion benchmark
#     Realistic traffic from Canadian Institute for Cybersecurity
# ======================================================================
print("=" * 75)
print("  1. CIC-IDS-2017 V2 (real-world, 2017, modern attacks)")
print("=" * 75)

import requests

CICIDS_URL = "https://zenodo.org/api/records/10141593/files/CIC-IDS-2017-V2.zip/content"
cicids_zip = OUT / 'cicids2017_v2.zip'

if not cicids_zip.exists():
    print("  Downloading CIC-IDS-2017-V2 from Zenodo (~369 MB)...")
    t0 = time.time()
    try:
        r = requests.get(CICIDS_URL, stream=True, timeout=30)
        r.raise_for_status()
        total = int(r.headers.get('Content-Length', 0))
        downloaded = 0
        with open(cicids_zip, 'wb') as f:
            for chunk in r.iter_content(chunk_size=1024*1024):
                f.write(chunk)
                downloaded += len(chunk)
                pct = 100 * downloaded / total if total > 0 else 0
                mb = downloaded / 1e6
                elapsed = time.time() - t0
                speed = mb / elapsed if elapsed > 0 else 0
                print(f"\r  {mb:.0f}/{total/1e6:.0f} MB ({pct:.0f}%) @ {speed:.1f} MB/s", end="", flush=True)
        print(f"\n  Downloaded in {time.time()-t0:.0f}s")
    except Exception as e:
        print(f"\n  Download failed: {e}")
        if cicids_zip.exists():
            cicids_zip.unlink()
else:
    print(f"  Using cached {cicids_zip} ({cicids_zip.stat().st_size/1e6:.1f} MB)")

if cicids_zip.exists() and cicids_zip.stat().st_size > 1e6:
    print("  Extracting and processing...")
    try:
        with zipfile.ZipFile(cicids_zip, 'r') as zf:
            csv_files = [f for f in zf.namelist() if f.endswith('.csv')]
            print(f"  Found {len(csv_files)} CSV files in archive:")
            for cf in csv_files:
                info = zf.getinfo(cf)
                print(f"    {cf:50} {info.file_size/1e6:>8.1f} MB")

            # Read all CSVs and concatenate
            dfs = []
            for cf in csv_files:
                print(f"  Reading {cf}...", end="", flush=True)
                with zf.open(cf) as fh:
                    df = pd.read_csv(fh, low_memory=False)
                print(f" {df.shape}")
                dfs.append(df)

            df_all = pd.concat(dfs, ignore_index=True)
            print(f"  Combined shape: {df_all.shape}")
            print(f"  Columns: {df_all.columns.tolist()[:10]}...")

            # Find label column
            label_col = None
            for cand in ['Label', 'label', ' Label', 'class', 'Class']:
                if cand in df_all.columns:
                    label_col = cand
                    break
            
            if label_col is None:
                # Check if any column has BENIGN/attack values
                for c in df_all.columns:
                    vals = df_all[c].astype(str).str.strip().unique()
                    if 'BENIGN' in vals or 'Benign' in vals or 'benign' in vals:
                        label_col = c
                        break

            if label_col:
                labels = df_all[label_col].astype(str).str.strip()
                print(f"  Label column: '{label_col}'")
                print(f"  Label distribution:")
                for val, cnt in labels.value_counts().head(20).items():
                    print(f"    {val:<30} {cnt:>10,}")

                y_cic = (~labels.isin(['BENIGN', 'Benign', 'benign', 'Normal', 'normal'])).astype(np.int32).values
                attack_types = labels.values

                # Get numeric features
                df_feat = df_all.drop(columns=[label_col])
                # Remove non-numeric columns
                numeric_cols = df_feat.select_dtypes(include=[np.number]).columns
                df_feat = df_feat[numeric_cols]
                # Remove inf/nan-heavy columns
                df_feat = df_feat.replace([np.inf, -np.inf], np.nan)
                nan_frac = df_feat.isna().mean()
                good_cols = nan_frac[nan_frac < 0.3].index
                df_feat = df_feat[good_cols].fillna(0)

                X_cic = df_feat.values.astype(np.float64)
                print(f"  Numeric features: {X_cic.shape[1]}")

                prep_and_save('cicids2017_v2', X_cic, y_cic, attack_types, OUT)
            else:
                print(f"  ERROR: No label column found. Columns: {df_all.columns.tolist()}")
    except zipfile.BadZipFile:
        print("  ERROR: Downloaded file is not a valid zip. Removing.")
        cicids_zip.unlink()
    except Exception as e:
        print(f"  ERROR processing: {e}")
        import traceback
        traceback.print_exc()
else:
    print("  [SKIPPED] CIC-IDS-2017-V2 download failed or empty")


# ======================================================================
#  2. Full KDDCup99 (OpenML, 494K samples -- 4.6x our current subset)
# ======================================================================
print("\n" + "=" * 75)
print("  2. Full KDDCup99 (494K, complete -- 4.6x current subset)")
print("=" * 75)

kdd_full = OUT / 'kddcup99_full.npz'
if not kdd_full.exists():
    try:
        from sklearn.datasets import fetch_openml
        print("  Fetching from OpenML (494K samples)...")
        r = fetch_openml('KDDCup99', as_frame=True, parser='auto', version=1)
        df = r.frame
        print(f"  Shape: {df.shape}")

        # Last column is target
        target_col = df.columns[-1]
        labels = df[target_col].astype(str).str.strip().str.rstrip('.')
        y_kdd = (labels != 'normal').astype(np.int32).values

        # Map to 5-class 
        dos = {'back','land','neptune','pod','smurf','teardrop','apache2','udpstorm',
               'processtable','mailbomb'}
        probe = {'satan','ipsweep','nmap','portsweep','mscan','saint'}
        r2l = {'guess_passwd','ftp_write','imap','phf','multihop','warezmaster',
               'warezclient','spy','xlock','xsnoop','snmpguess','snmpgetattack',
               'httptunnel','sendmail','named'}
        u2r = {'buffer_overflow','loadmodule','rootkit','perl','sqlattack','xterm','ps'}
        
        attack_cats = []
        for lab in labels:
            ll = lab.lower()
            if ll == 'normal':
                attack_cats.append('normal')
            elif ll in dos:
                attack_cats.append('DoS')
            elif ll in probe:
                attack_cats.append('Probe')
            elif ll in r2l:
                attack_cats.append('R2L')
            elif ll in u2r:
                attack_cats.append('U2R')
            else:
                attack_cats.append(lab)
        attack_cats = np.array(attack_cats)

        df_feat = df.drop(columns=[target_col])
        for c in df_feat.select_dtypes(include=['object', 'category']).columns:
            le = LabelEncoder()
            df_feat[c] = le.fit_transform(df_feat[c].astype(str))
        
        X_kdd = df_feat.values.astype(np.float64)
        prep_and_save('kddcup99_full', X_kdd, y_kdd, attack_cats, OUT)
    except Exception as e:
        print(f"  ERROR: {e}")
        import traceback
        traceback.print_exc()
else:
    print(f"  Using cached {kdd_full} ({kdd_full.stat().st_size/1e6:.1f} MB)")


# ======================================================================
#  SUMMARY
# ======================================================================
print("\n" + "=" * 75)
print("  COMPLETE CYBERSECURITY DATASET INVENTORY")
print("=" * 75)
for f in sorted(OUT.glob('*.npz')):
    d = np.load(f, allow_pickle=True)
    y = d['y']
    X = d.get('X10', d.get('X_full'))
    at = d.get('attack_types', None)
    n_types = len(set(at)) - 1 if at is not None else '?'
    size_mb = f.stat().st_size / 1e6
    print(f"  {f.stem:<25}  {len(y):>8,} samples  {int(y.sum()):>7,} attacks "
          f"({100*y.mean():5.1f}%)  {X.shape[1]:>3}D  {n_types:>2} types  {size_mb:>6.1f} MB")

# Legacy
legacy = ROOT / 'data' / 'external_validation' / 'kddcup99_cyber.npz'
if legacy.exists():
    d = np.load(legacy, allow_pickle=True)
    y = d['y']
    print(f"  {'kddcup99_108k (legacy)':<25}  {len(y):>8,} samples  {int(y.sum()):>7,} attacks "
          f"({100*y.mean():5.1f}%)  {d['X10'].shape[1]:>3}D")

print("\n  Done.")
