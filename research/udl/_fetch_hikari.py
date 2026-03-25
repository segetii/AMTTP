"""Download and preprocess HIKARI-2021 CSV from Zenodo."""
import requests, os, zipfile, time
import numpy as np
import pandas as pd
from sklearn.preprocessing import LabelEncoder, StandardScaler
from sklearn.decomposition import PCA

DATA_DIR = r"c:\amttp\data\external_validation\cyber"

# HIKARI-2021 CSV zip from Zenodo #5199540
RECORD_ID = 5199540
url = f"https://zenodo.org/api/records/{RECORD_ID}"
r = requests.get(url, timeout=30)
data = r.json()
files = data.get("files", [])

# Find the CSV zip
csv_zip = None
for f in files:
    if "csv.zip" in f["key"].lower():
        csv_zip = f
        break

if csv_zip is None:
    print("No CSV zip found!")
    for f in files[:10]:
        print(f"  {f['key']} ({f['size']/1e6:.1f} MB)")
    exit()

print(f"Downloading: {csv_zip['key']} ({csv_zip['size']/1e6:.1f} MB)")
zip_path = os.path.join(DATA_DIR, "hikari_2021.csv.zip")

if not os.path.exists(zip_path):
    t0 = time.time()
    resp = requests.get(csv_zip["links"]["self"], stream=True, timeout=300)
    resp.raise_for_status()
    total = int(resp.headers.get("content-length", 0))
    downloaded = 0
    with open(zip_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=1024*1024):
            f.write(chunk)
            downloaded += len(chunk)
            if total > 0:
                pct = downloaded / total * 100
                speed = downloaded / (time.time() - t0 + 0.001) / 1e6
                print(f"\r  {pct:.0f}% ({downloaded/1e6:.1f}/{total/1e6:.1f} MB @ {speed:.1f} MB/s)  ", end="", flush=True)
    print(f"\n  Done in {time.time()-t0:.1f}s")
else:
    print(f"  Already downloaded: {zip_path}")

# Extract
print("Extracting...")
with zipfile.ZipFile(zip_path, 'r') as z:
    names = z.namelist()
    print(f"  Contents: {names}")
    csv_name = [n for n in names if n.endswith('.csv')][0]
    z.extract(csv_name, DATA_DIR)

csv_path = os.path.join(DATA_DIR, csv_name)
print(f"Loading {csv_path}...")
df = pd.read_csv(csv_path, low_memory=False)
print(f"  Shape: {df.shape}")
print(f"  Columns: {list(df.columns[:20])}{'...' if len(df.columns)>20 else ''}")

# Find label column
label_col = None
for c in df.columns:
    cl = c.lower()
    if 'label' in cl or 'attack' in cl or 'class' in cl or 'category' in cl:
        label_col = c
        print(f"  Found label candidate: '{c}'")
        print(f"    Values: {df[c].value_counts().head(10).to_string()}")

# Use the last label-like column found, or last column
if label_col is None:
    label_col = df.columns[-1]
    print(f"  Using last column: '{label_col}'")
    print(f"    Values: {df[label_col].value_counts().head(10).to_string()}")

labels = df[label_col].astype(str).str.strip()
print(f"\nLabel column: '{label_col}'")
print(f"Distribution:\n{labels.value_counts().to_string()}")

# Determine normal vs attack
normal_kw = ['benign', 'normal', 'background', '0', 'false', 'legitimate']
is_normal = labels.str.lower().isin(normal_kw)
if is_normal.sum() == 0:
    most_common = labels.value_counts().index[0]
    is_normal = labels == most_common
    print(f"Using '{most_common}' as normal class")

y = (~is_normal).astype(int).values
attack_types = labels.values

# Features
feat_df = df.drop(columns=[label_col])
# Also drop any other label-like columns
for c in list(feat_df.columns):
    cl = c.lower()
    if 'label' in cl or cl in ('attack_cat', 'attack_type', 'class'):
        print(f"  Also dropping: {c}")
        feat_df = feat_df.drop(columns=[c])

# Handle categoricals
drop_cols = []
for col in feat_df.columns:
    if feat_df[col].dtype == object:
        nunique = feat_df[col].nunique()
        if nunique > 50:
            drop_cols.append(col)
        else:
            le = LabelEncoder()
            feat_df[col] = le.fit_transform(feat_df[col].astype(str))
if drop_cols:
    print(f"  Dropping high-cardinality: {drop_cols}")
    feat_df = feat_df.drop(columns=drop_cols)

feat_df = feat_df.apply(pd.to_numeric, errors='coerce')
feat_df = feat_df.replace([np.inf, -np.inf], np.nan).fillna(0)
std = feat_df.std()
feat_df = feat_df.loc[:, std > 1e-10]
print(f"  Features after cleaning: {feat_df.shape[1]}")

X = feat_df.values.astype(np.float64)
scaler = StandardScaler()
X = scaler.fit_transform(X)

n_comp = min(10, X.shape[1])
pca = PCA(n_components=n_comp)
X_pca = pca.fit_transform(X)
var_exp = pca.explained_variance_ratio_.sum()
print(f"  PCA: {X.shape[1]}D -> {n_comp}D (var={var_exp:.3f})")

out_path = os.path.join(DATA_DIR, "hikari_2021.npz")
np.savez_compressed(out_path, X=X_pca, y=y, attack_types=attack_types)
sz = os.path.getsize(out_path) / 1e6
n_att = y.sum()
unique_at = len(set(attack_types[y == 1]))
print(f"\nSaved: {out_path}")
print(f"  {len(y)} samples, {n_att} attacks ({100*n_att/len(y):.1f}%), {unique_at} attack types, {sz:.1f} MB")
