"""
Try to fetch newer cybersecurity benchmark datasets (2018-2024).
Approach: search Zenodo, OpenML, and try direct URLs.
"""
import requests, json, sys, os, time

DATA_DIR = r"c:\amttp\data\external_validation\cyber"
os.makedirs(DATA_DIR, exist_ok=True)

def search_zenodo(query, max_results=10):
    """Search Zenodo for datasets."""
    url = "https://zenodo.org/api/records"
    params = {"q": query, "size": max_results, "sort": "mostrecent", "type": "dataset"}
    r = requests.get(url, params=params, timeout=30)
    if r.status_code == 200:
        hits = r.json().get("hits", {}).get("hits", [])
        results = []
        for h in hits:
            files = h.get("files", [])
            total_size = sum(f.get("size", 0) for f in files)
            results.append({
                "id": h["id"],
                "title": h["metadata"]["title"],
                "year": h["metadata"].get("publication_date", "?")[:4],
                "size_mb": total_size / 1e6,
                "n_files": len(files),
                "doi": h.get("doi", ""),
                "files": [(f["key"], f["size"]/1e6) for f in files[:5]]
            })
        return results
    return []

def search_openml(query):
    """Search OpenML for datasets."""
    url = f"https://www.openml.org/api/v1/json/data/list/data_name/{query}/limit/10"
    r = requests.get(url, timeout=30)
    if r.status_code == 200:
        data = r.json().get("data", {}).get("dataset", [])
        return [(d["did"], d["name"], d.get("NumberOfInstances", "?"), d.get("NumberOfFeatures", "?")) for d in data]
    return []

print("=" * 70)
print("  SEARCHING FOR NEWER CYBERSECURITY DATASETS (2018-2024)")
print("=" * 70)

# 1. Search Zenodo for various newer datasets
queries = [
    "CIC-IDS-2018",
    "CSE-CIC-IDS2018",
    "CIC-IoT-2023",
    "LITNET-2020",
    "Bot-IoT",
    "TON_IoT",
    "CTU-13",
    "HIKARI-2021",
    "NF-UNSW-NB15",    # NetFlow version
    "NF-CSE-CIC-IDS2018",
    "Edge-IIDat",
    "CIC-DDoS2019",
    "cyber intrusion detection 2021",
    "network intrusion detection 2022",
    "network intrusion detection 2023",
]

all_zenodo = {}
for q in queries:
    print(f"\n  Zenodo: '{q}' ... ", end="", flush=True)
    try:
        results = search_zenodo(q)
        if results:
            print(f"{len(results)} hits")
            for r in results[:3]:
                key = r["id"]
                if key not in all_zenodo:
                    all_zenodo[key] = r
                    print(f"    [{r['id']}] {r['title'][:80]}")
                    print(f"        Year: {r['year']}  Size: {r['size_mb']:.1f} MB  Files: {r['n_files']}")
                    for fname, fsize in r["files"][:3]:
                        print(f"          - {fname} ({fsize:.1f} MB)")
        else:
            print("no results")
    except Exception as e:
        print(f"error: {e}")

# 2. Search OpenML
print("\n" + "=" * 70)
print("  OpenML searches:")
for q in ["CIC", "IoT", "UNSW", "Bot", "intrusion"]:
    print(f"\n  OpenML: '{q}' ... ", end="", flush=True)
    try:
        results = search_openml(q)
        if results:
            print(f"{len(results)} hits")
            for did, name, n, nf in results[:5]:
                print(f"    [did={did}] {name}  ({n} samples, {nf} features)")
        else:
            print("no results")
    except Exception as e:
        print(f"error: {e}")

# 3. Try direct URLs for well-known datasets
print("\n" + "=" * 70)
print("  Direct URL probes:")
direct_urls = {
    "CIC-IDS-2018 (UNB)": "https://www.unb.ca/cic/datasets/ids-2018.html",
    "CIC-DDoS-2019": "https://www.unb.ca/cic/datasets/ddos-2019.html",
    "CIC-IoT-2023": "https://www.unb.ca/cic/datasets/iotdataset-2023.html",
    "CTU-13": "https://mcfp.felk.cvut.cz/publicDatasets/CTU-13-Dataset/",
    "HIKARI-2021": "https://zenodo.org/record/5199540",
    "NF-UQ-NIDS (NetFlow)": "https://staff.itee.uq.edu.au/marius/NIDS_datasets/",
}
for name, url in direct_urls.items():
    try:
        r = requests.head(url, timeout=10, allow_redirects=True)
        print(f"  {name}: {r.status_code} ({url})")
    except Exception as e:
        print(f"  {name}: FAILED ({e})")

print("\nSearch complete.")
