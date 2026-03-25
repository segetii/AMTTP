import requests, json

# Check Zenodo for CICIDS2017
r = requests.get('https://zenodo.org/api/records/7913948', timeout=15)
data = r.json()
title = data.get('metadata', {}).get('title', '?')
print(f"Title: {title}")
files = data.get('files', [])
for f in files[:10]:
    key = f.get('key', '?')
    size_mb = f.get('size', 0) / 1e6
    link = f.get('links', {}).get('self', '')
    print(f"  {key:40} {size_mb:>8.1f} MB  {link[:80]}")

# Search Zenodo for IDS/intrusion datasets
print("\n=== Zenodo search: 'network intrusion detection dataset' ===\n")
r2 = requests.get('https://zenodo.org/api/records',
                   params={'q': 'CICIDS network intrusion detection', 'size': 10},
                   timeout=15)
hits = r2.json().get('hits', {}).get('hits', [])
for h in hits[:8]:
    meta = h.get('metadata', {})
    rid = h.get('id', '?')
    title = meta.get('title', '?')[:80]
    print(f"  ID={rid}  {title}")
    for f in h.get('files', [])[:3]:
        key = f.get('key', '?')
        size_mb = f.get('size', 0) / 1e6
        print(f"    {key:40} {size_mb:>8.1f} MB")

# Also search for more modern datasets
print("\n=== Zenodo search: 'IoT intrusion 2020 2021 2022' ===\n")
r3 = requests.get('https://zenodo.org/api/records',
                   params={'q': 'IoT network intrusion detection dataset 2020 2021 2022', 'size': 10},
                   timeout=15)
hits3 = r3.json().get('hits', {}).get('hits', [])
for h in hits3[:8]:
    meta = h.get('metadata', {})
    rid = h.get('id', '?')
    title = meta.get('title', '?')[:80]
    pub = meta.get('publication_date', '?')
    print(f"  ID={rid} ({pub})  {title}")
    files = h.get('files', [])
    total_mb = sum(f.get('size', 0) for f in files) / 1e6
    print(f"    {len(files)} files, {total_mb:.1f} MB total")
