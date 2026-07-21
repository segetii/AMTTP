import pandas as pd
p=r'c:\amttp\data\external_validation\cyber\ton_iot_network.csv'
cols=['ts','label','type']
df=pd.read_csv(p,usecols=cols).sort_values('ts').reset_index(drop=True)
print('rows',len(df),'attacks',int(df.label.sum()),'normal',int((df.label==0).sum()),'prevalence',df.label.mean())
print('ts min/max',df.ts.min(),df.ts.max())
print('types',df.type.value_counts().to_string())
# bins by 1000 rows
for bs in [500,1000,2000,5000]:
    print('\nBatch',bs)
    for i in range(0,min(len(df),20000),bs):
        sub=df.iloc[i:i+bs]
        print(i,i+len(sub)-1,'attack%',round(sub.label.mean()*100,1),'normal',int((sub.label==0).sum()),'types',sub.type.value_counts().head(3).to_dict())
