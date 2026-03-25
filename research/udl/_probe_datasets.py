"""
Probe availability of modern, real-world cybersecurity benchmark datasets.
Tests download URLs without fetching full files.
"""
import urllib.request, json

targets = {
    # CICIDS2017 - THE standard modern IDS benchmark (2017, ~2.8M flows, 78 features)
    "CICIDS2017 (Kaggle mirror)": "https://www.kaggle.com/api/v1/datasets/download/cicdataset/cicids2017",
    "CICIDS2017 (UNB official)": "https://iscxdownloads.cs.unb.ca/iscxdownloads/CIC-IDS-2017/MachineLearningCVE/Friday-WorkingHours-Afternoon-DDos.pcap_ISCX.csv",
    
    # CIC-IDS2018 (updated, larger, AWS-hosted)
    "CIC-IDS2018 (AWS)": "https://cic-ids2018.s3.ca-central-1.amazonaws.com/Processed%20Traffic%20Data%20for%20ML%20Algorithms/Friday-02-03-2018_TrafficForML_CICFlowMeter.csv",
    
    # TON_IoT (2020, IoT-specific, UNSW)
    "TON_IoT": "https://cloudstor.aarnet.edu.au/plus/s/ds5zW91vdgjEj9i/download",
    
    # IoT-23 (2020, Stratosphere Lab, CTU)
    "IoT-23 (Stratosphere)": "https://mcfp.felk.cvut.cz/publicDatasets/IoT-23-Dataset/IndividualScenarios/CTU-IoT-Malware-Capture-1-1/bro/conn.log.labeled",
    
    # LITNET-2020 (Lithuanian academic network, 2020)
    "LITNET-2020": "https://dataset.litnet.lt/download/LITNET-2020-1.csv",
    
    # Bot-IoT (2018, UNSW)
    "Bot-IoT (UNSW)": "https://cloudstor.aarnet.edu.au/plus/s/umT99TnxvbpkkoE/download",
}

# Also check OpenML for modern IDS datasets
openml_ids = {
    "OpenML CICIDS2017 (43789)": 43789,
    "OpenML CICIDS2017 (45058)": 45058,
    "OpenML CIC-IDS2018": 43790,
}

print("=== Checking direct download URLs ===\n")
for name, url in targets.items():
    try:
        req = urllib.request.Request(url, method='HEAD')
        req.add_header('User-Agent', 'Mozilla/5.0')
        resp = urllib.request.urlopen(req, timeout=10)
        size = resp.headers.get('Content-Length', '?')
        ctype = resp.headers.get('Content-Type', '?')
        if size != '?':
            size_mb = int(size) / 1024 / 1024
            print(f"  OK  {name:<35} {size_mb:>8.1f} MB  ({ctype})")
        else:
            print(f"  OK  {name:<35} {'?':>8} MB  ({ctype})")
    except Exception as e:
        err = str(e)[:60]
        print(f"  ERR {name:<35} {err}")

print("\n=== Checking OpenML dataset IDs ===\n")
for name, did in openml_ids.items():
    try:
        url = f"https://www.openml.org/api/v1/json/data/{did}"
        req = urllib.request.Request(url)
        req.add_header('User-Agent', 'Mozilla/5.0')
        resp = urllib.request.urlopen(req, timeout=10)
        data = json.loads(resp.read())
        ds = data.get('data_set_description', {})
        dname = ds.get('name', '?')
        nfeat = ds.get('number_of_features', '?')
        ninst = ds.get('number_of_instances', '?')
        print(f"  OK  {name:<35} name='{dname}'  features={nfeat}  instances={ninst}")
    except Exception as e:
        err = str(e)[:60]
        print(f"  ERR {name:<35} {err}")

# Check sklearn openml search
print("\n=== OpenML search for 'IDS' / 'intrusion' datasets ===\n")
try:
    from sklearn.datasets import fetch_openml
    import openml
    dsets = openml.datasets.list_datasets(output_format='dataframe')
    # Filter for IDS/intrusion/cyber keywords
    mask = dsets['name'].str.contains('IDS|intrusion|CICIDS|CIC-IDS|network.traffic|cyber', case=False, na=False)
    hits = dsets[mask][['name', 'NumberOfInstances', 'NumberOfFeatures', 'did']].sort_values('NumberOfInstances', ascending=False)
    print(hits.head(20).to_string())
except Exception as e:
    print(f"  openml search failed: {e}")
    # Fallback: just list known dataset names
    try:
        for dname in ['CICIDS2017', 'CIC-IDS-2017', 'cicids', 'NIDS']:
            try:
                r = fetch_openml(dname, as_frame=True, parser='auto', version=1)
                print(f"  Found '{dname}': {r.frame.shape} cols={r.frame.columns.tolist()[:5]}")
            except:
                print(f"  Not found: '{dname}'")
    except:
        pass
