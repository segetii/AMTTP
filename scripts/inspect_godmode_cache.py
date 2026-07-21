import pickle
from pathlib import Path
import pandas as pd

DATA_DIR = Path(r"C:\amttp\data")
patterns = ["klines_*", "binance_futures_*", "geometric_extractor_engine_arrays*.npz", "cross_market_df.pkl", "daily_crypto_pairs.pkl"]

print('Inspecting Godmode cache in', DATA_DIR)
for p in DATA_DIR.iterdir():
    name = p.name
    if any(pd.Series([name]).str.contains(pat.replace('*',''))[0] for pat in patterns if '*' in pat) or name in ['cross_market_df.pkl','daily_crypto_pairs.pkl']:
        try:
            if p.suffix in ['.pkl']:
                obj = pd.read_pickle(p)
                tmin = tmax = None
                if isinstance(obj, (pd.Series, pd.DataFrame)):
                    idx = obj.index
                    if len(idx) > 0 and hasattr(idx, 'min'):
                        tmin = idx.min()
                        tmax = idx.max()
                print(f"{name}: type={type(obj).__name__}, rows={len(obj) if hasattr(obj,'__len__') else 'N/A'}, tmin={tmin}, tmax={tmax}")
            elif p.suffix in ['.npz']:
                import numpy as np
                arr = np.load(p)
                print(f"{name}: npz keys={list(arr.keys())}")
            else:
                print(f"{name}: (skipped, unknown suffix)")
        except Exception as e:
            print(f"{name}: ERROR reading ({e})")

# Also check the zip we created
zip_path = DATA_DIR / 'godmode_cached_2021_2026.zip'
if zip_path.exists():
    import zipfile
    with zipfile.ZipFile(zip_path) as z:
        print('\nArchive contents:')
        for info in z.infolist():
            print(' ', info.filename, info.file_size)
else:
    print('\nArchive not found')
