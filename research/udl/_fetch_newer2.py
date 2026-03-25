"""
Download and preprocess newer cybersecurity datasets found on Zenodo + direct sources.
"""
import requests, json, sys, os, io, time
import numpy as np

DATA_DIR = r"c:\amttp\data\external_validation\cyber"
os.makedirs(DATA_DIR, exist_ok=True)

def zenodo_files(record_id):
    """Get download URLs for a Zenodo record."""
    url = f"https://zenodo.org/api/records/{record_id}"
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    data = r.json()
    title = data["metadata"]["title"]
    date = data["metadata"].get("publication_date", "?")
    files = [(f["key"], f["links"]["self"], f["size"]) for f in data.get("files", [])]
    return title, date, files

def download_file(url, dest, desc=""):
    """Download with progress."""
    print(f"    Downloading {desc}...", flush=True)
    r = requests.get(url, stream=True, timeout=300)
    r.raise_for_status()
    total = int(r.headers.get("content-length", 0))
    downloaded = 0
    t0 = time.time()
    with open(dest, "wb") as f:
        for chunk in r.iter_content(chunk_size=1024*1024):
            f.write(chunk)
            downloaded += len(chunk)
            if total > 0:
                pct = downloaded / total * 100
                speed = downloaded / (time.time() - t0 + 0.001) / 1e6
                print(f"\r    {pct:.0f}% ({downloaded/1e6:.1f}/{total/1e6:.1f} MB @ {speed:.1f} MB/s)  ", end="", flush=True)
    elapsed = time.time() - t0
    print(f"\n    Done in {elapsed:.1f}s ({downloaded/1e6:.1f} MB)")
    return dest

def preprocess_csv_to_npz(csv_path, out_name, label_col=None, max_pca_dim=10):
    """Load CSV, handle mixed types, PCA to 10D, save as .npz"""
    import pandas as pd
    from sklearn.preprocessing import LabelEncoder, StandardScaler
    from sklearn.decomposition import PCA
    
    print(f"    Loading CSV...", flush=True)
    df = pd.read_csv(csv_path, low_memory=False)
    print(f"    Raw shape: {df.shape}")
    print(f"    Columns: {list(df.columns[:20])}{'...' if len(df.columns)>20 else ''}")
    
    # Try to find label column
    if label_col is None:
        candidates = ['label', 'Label', 'attack_cat', 'Attack', 'class', 'Class', 
                       'attack_type', 'attack', 'category', 'is_attack', 'target']
        for c in candidates:
            if c in df.columns:
                label_col = c
                break
        if label_col is None:
            # Use last column as label
            label_col = df.columns[-1]
    
    print(f"    Label column: '{label_col}'")
    labels = df[label_col].astype(str).str.strip()
    print(f"    Label distribution:\n{labels.value_counts().head(20).to_string()}")
    
    # Determine attack vs normal
    normal_keywords = ['benign', 'normal', '0', 'false', 'legitimate', 'clean']
    is_normal = labels.str.lower().isin(normal_keywords)
    
    # If no normals found, try numeric 0
    if is_normal.sum() == 0:
        try:
            numeric_labels = pd.to_numeric(labels, errors='coerce')
            is_normal = numeric_labels == 0
        except:
            pass
    
    if is_normal.sum() == 0:
        print(f"    WARNING: Could not identify normal class. Using most common as normal.")
        most_common = labels.value_counts().index[0]
        is_normal = labels == most_common
        print(f"    Using '{most_common}' as normal class")
    
    y = (~is_normal).astype(int).values
    attack_types = labels.values
    
    # Feature matrix: drop label column, encode categoricals
    feat_df = df.drop(columns=[label_col])
    
    # Drop columns with too many unique strings (IPs, timestamps, etc.)
    drop_cols = []
    for col in feat_df.columns:
        if feat_df[col].dtype == object:
            nunique = feat_df[col].nunique()
            if nunique > 50:
                drop_cols.append(col)
            else:
                # Encode categorical
                le = LabelEncoder()
                feat_df[col] = le.fit_transform(feat_df[col].astype(str))
    if drop_cols:
        print(f"    Dropping high-cardinality columns: {drop_cols}")
        feat_df = feat_df.drop(columns=drop_cols)
    
    # Convert to numeric
    feat_df = feat_df.apply(pd.to_numeric, errors='coerce')
    feat_df = feat_df.fillna(0)
    
    # Remove constant/inf columns
    feat_df = feat_df.replace([np.inf, -np.inf], np.nan).fillna(0)
    std = feat_df.std()
    feat_df = feat_df.loc[:, std > 1e-10]
    
    print(f"    Features after cleaning: {feat_df.shape[1]}")
    
    X = feat_df.values.astype(np.float64)
    
    # Standardize + PCA
    scaler = StandardScaler()
    X = scaler.fit_transform(X)
    
    n_components = min(max_pca_dim, X.shape[1])
    pca = PCA(n_components=n_components)
    X_pca = pca.fit_transform(X)
    var_explained = pca.explained_variance_ratio_.sum()
    print(f"    PCA: {X.shape[1]}D -> {n_components}D (var={var_explained:.3f})")
    
    # Save
    out_path = os.path.join(DATA_DIR, f"{out_name}.npz")
    np.savez_compressed(out_path, X=X_pca, y=y, attack_types=attack_types)
    sz = os.path.getsize(out_path) / 1e6
    n_attacks = y.sum()
    unique_at = len(set(attack_types[y == 1]))
    print(f"    Saved: {out_path}")
    print(f"    {len(y)} samples, {n_attacks} attacks ({100*n_attacks/len(y):.1f}%), {unique_at} attack types, {sz:.1f} MB")
    return out_path

# ============================================================
# 1. TON_IoT (2025, Zenodo 18074069) — IoT intrusion detection
# ============================================================
print("\n" + "=" * 70)
print("  1. TON_IoT Dataset (Zenodo #18074069)")
print("=" * 70)

try:
    title, date, files = zenodo_files(18074069)
    print(f"  Title: {title}")
    print(f"  Date: {date}")
    for fname, url, size in files:
        print(f"  File: {fname} ({size/1e6:.1f} MB)")
    
    # Download CSV
    csv_name, csv_url, csv_size = files[0]
    csv_path = os.path.join(DATA_DIR, "ton_iot_network.csv")
    if not os.path.exists(csv_path):
        download_file(csv_url, csv_path, f"TON_IoT ({csv_size/1e6:.1f} MB)")
    else:
        print(f"    Already downloaded: {csv_path}")
    
    preprocess_csv_to_npz(csv_path, "ton_iot_2020", label_col=None)
    
except Exception as e:
    print(f"  ERROR: {e}")

# ============================================================
# 2. CIC-IoT 2023 (Zenodo 17418769)
# ============================================================
print("\n" + "=" * 70)
print("  2. CIC-IoT 2023 (Zenodo #17418769)")
print("=" * 70)

try:
    title, date, files = zenodo_files(17418769)
    print(f"  Title: {title}")
    print(f"  Date: {date}")
    for fname, url, size in files:
        print(f"  File: {fname} ({size/1e6:.1f} MB)")
    
    csv_name, csv_url, csv_size = files[0]
    csv_path = os.path.join(DATA_DIR, "cic_iot_2023.csv")
    if not os.path.exists(csv_path):
        download_file(csv_url, csv_path, f"CIC-IoT 2023 ({csv_size/1e6:.1f} MB)")
    else:
        print(f"    Already downloaded: {csv_path}")
    
    preprocess_csv_to_npz(csv_path, "cic_iot_2023", label_col=None)
    
except Exception as e:
    print(f"  ERROR: {e}")

# ============================================================
# 3. HIKARI-2021 (Zenodo #5199540)
# ============================================================
print("\n" + "=" * 70)
print("  3. HIKARI-2021 (Zenodo #5199540)")
print("=" * 70)

try:
    title, date, files = zenodo_files(5199540)
    print(f"  Title: {title}")
    print(f"  Date: {date}")
    for fname, url, size in files:
        print(f"  File: {fname} ({size/1e6:.1f} MB)")
    
    # Download the CSV files (pick the biggest one)
    csv_files = [(f, u, s) for f, u, s in files if f.endswith('.csv')]
    if csv_files:
        csv_files.sort(key=lambda x: -x[2])  # Largest first
        csv_name, csv_url, csv_size = csv_files[0]
        csv_path = os.path.join(DATA_DIR, f"hikari_2021_{csv_name}")
        if not os.path.exists(csv_path):
            download_file(csv_url, csv_path, f"HIKARI-2021 {csv_name} ({csv_size/1e6:.1f} MB)")
        else:
            print(f"    Already downloaded: {csv_path}")
        preprocess_csv_to_npz(csv_path, "hikari_2021", label_col=None)
    else:
        print("  No CSV files found, checking other formats...")
        for fname, url, size in files[:5]:
            print(f"    {fname} ({size/1e6:.1f} MB)")
    
except Exception as e:
    print(f"  ERROR: {e}")

# ============================================================
# 4. CIC-DDoS-2019 SDN traffic (Zenodo #17121740)
# ============================================================
print("\n" + "=" * 70)
print("  4. CIC-DDoS-2019 SDN (Zenodo #17121740)")
print("=" * 70)

try:
    title, date, files = zenodo_files(17121740)
    print(f"  Title: {title}")
    print(f"  Date: {date}")
    for fname, url, size in files:
        print(f"  File: {fname} ({size/1e6:.1f} MB)")
    
    csv_files = [(f, u, s) for f, u, s in files if f.endswith('.csv')]
    if csv_files:
        csv_files.sort(key=lambda x: -x[2])
        csv_name, csv_url, csv_size = csv_files[0]
        csv_path = os.path.join(DATA_DIR, f"ddos2019_{csv_name}")
        if not os.path.exists(csv_path):
            download_file(csv_url, csv_path, f"DDoS-2019 {csv_name} ({csv_size/1e6:.1f} MB)")
        else:
            print(f"    Already downloaded: {csv_path}")
        preprocess_csv_to_npz(csv_path, "cic_ddos_2019", label_col=None)
    
except Exception as e:
    print(f"  ERROR: {e}")

# ============================================================
# 5. Try UQ-NIDS NetFlow datasets (direct URL)
# ============================================================
print("\n" + "=" * 70)
print("  5. NF-UQ-NIDS NetFlow datasets (direct)")
print("=" * 70)

nf_urls = {
    "NF-UNSW-NB15-v2": "https://rdm.uq.edu.au/files/a0afb6e0-a70d-11ec-8668-1be37d5502f5/NF-UNSW-NB15-v2.csv.zip",
    "NF-BoT-IoT-v2": "https://rdm.uq.edu.au/files/a0afb6e0-a70d-11ec-8668-1be37d5502f5/NF-BoT-IoT-v2.csv.zip",
    "NF-CSE-CIC-IDS2018-v2": "https://rdm.uq.edu.au/files/a0afb6e0-a70d-11ec-8668-1be37d5502f5/NF-CSE-CIC-IDS2018-v2.csv.zip",
    "NF-ToN-IoT-v2": "https://rdm.uq.edu.au/files/a0afb6e0-a70d-11ec-8668-1be37d5502f5/NF-ToN-IoT-v2.csv.zip",
}

for name, url in nf_urls.items():
    print(f"\n  Trying {name}...", flush=True)
    try:
        r = requests.head(url, timeout=10, allow_redirects=True)
        size = int(r.headers.get("content-length", 0))
        print(f"    Status: {r.status_code}, Size: {size/1e6:.1f} MB")
        if r.status_code == 200 and size > 1e6:
            print(f"    AVAILABLE! Would download {size/1e6:.1f} MB")
            # Download if reasonable size (<500MB)
            if size < 500e6:
                zip_path = os.path.join(DATA_DIR, f"{name}.csv.zip")
                if not os.path.exists(zip_path):
                    download_file(url, zip_path, f"{name} ({size/1e6:.1f} MB)")
                    # Unzip
                    import zipfile
                    with zipfile.ZipFile(zip_path, 'r') as z:
                        z.extractall(DATA_DIR)
                        csv_name = [f for f in z.namelist() if f.endswith('.csv')][0]
                    csv_path = os.path.join(DATA_DIR, csv_name)
                    preprocess_csv_to_npz(csv_path, name.lower().replace('-','_'), label_col=None)
                else:
                    print(f"    Already downloaded: {zip_path}")
            else:
                print(f"    Too large ({size/1e6:.0f} MB), skipping download")
    except Exception as e:
        print(f"    Failed: {e}")

print("\n" + "=" * 70)
print("  DOWNLOAD COMPLETE")
print("=" * 70)

# List what we have
print("\n  Available datasets:")
for f in sorted(os.listdir(DATA_DIR)):
    if f.endswith('.npz'):
        path = os.path.join(DATA_DIR, f)
        sz = os.path.getsize(path) / 1e6
        d = np.load(path, allow_pickle=True)
        n = len(d['y'])
        na = d['y'].sum()
        print(f"    {f:<35s}  {n:>10,} samples  {na:>10,} attacks ({100*na/n:.1f}%)  {sz:.1f} MB")
