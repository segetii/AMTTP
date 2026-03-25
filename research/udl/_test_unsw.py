import pandas as pd

urls = [
    'https://raw.githubusercontent.com/Luckygyana/UNSW-NB15-Dataset/main/UNSW_NB15_training-set.csv',
    'https://raw.githubusercontent.com/aseempatni/NIDS/master/dataset/UNSW_NB15_training-set.csv',
    'https://raw.githubusercontent.com/shaokun11/UNSW_NB15/main/a%20realistic%20data%20set/UNSW_NB15_training-set.csv',
    'https://raw.githubusercontent.com/pushkardps/UNSWNB15/master/UNSW_NB15_training-set.csv',
]
for url in urls:
    try:
        short = url.split("github.com/")[-1][:70]
        print(f"Trying: {short}...")
        df = pd.read_csv(url, nrows=5)
        print(f"  SUCCESS: {df.shape}, cols={df.columns.tolist()[:8]}")
        
        # Now also test matching test URL
        test_url = url.replace('training-set', 'testing-set')
        df2 = pd.read_csv(test_url, nrows=5)
        print(f"  Test set also works: {test_url}")
        break
    except Exception as e:
        print(f"  Failed: {e}")
