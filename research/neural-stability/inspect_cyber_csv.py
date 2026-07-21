import pandas as pd, os
paths=[r'c:\amttp\data\external_validation\cyber\ton_iot_network.csv', r'c:\amttp\data\external_validation\cyber\cic_iot_2023.csv']
for path in paths:
    print('\n===', path, os.path.getsize(path))
    df=pd.read_csv(path,nrows=5)
    print(df.columns.tolist())
    print(df.head().to_string())
