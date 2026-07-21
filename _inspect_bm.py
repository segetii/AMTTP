import json, os

ROOT = r"C:\amttp"

files = [
    ("benchmark_production_results.json", "production"),
    ("benchmark_full_results.json",       "full"),
    ("benchmark_dynamical_results.json",  "dynamical"),
    ("benchmark_curv_results.json",       "curv"),
    ("benchmark_ricci_results.json",      "ricci"),
    ("benchmark_v2_results.json",         "v2"),
    ("benchmark_v3_results.json",         "v3"),
]

for fname, tag in files:
    path = os.path.join(ROOT, fname)
    with open(path) as fh:
        d = json.load(fh)
    rows = d.get("results", d if isinstance(d, list) else [])
    print("=== %s ===" % tag)
    print("  version=%s  generated=%s  n_rows=%d" % (
        d.get("version","?"), d.get("generated","?"), len(rows)))
    if rows:
        print("  keys: %s" % list(rows[0].keys())[:25])
    print()
