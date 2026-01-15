"""
Label high-risk addresses in Memgraph for visualization.
"""
import mgclient
import pandas as pd

# Connect
conn = mgclient.connect(host='localhost', port=7687)
cursor = conn.cursor()

# Load consensus high-risk addresses
df = pd.read_csv(r'c:\amttp\processed\consensus_high_risk.csv')
print(f'Labeling {len(df)} consensus high-risk addresses...')

# Add HighRisk label
for addr in df['address'].values:
    query = "MATCH (a:Address {address: $addr}) SET a:HighRisk, a.consensus_risk = true"
    cursor.execute(query, {'addr': addr})
conn.commit()

# Load critical risk addresses  
critical_df = pd.read_csv(r'c:\amttp\processed\critical_risk_addresses.csv')
print(f'Labeling {len(critical_df)} critical risk addresses...')

for _, row in critical_df.iterrows():
    query = "MATCH (a:Address {address: $addr}) SET a:CriticalRisk, a.graph_score = $score"
    cursor.execute(query, {'addr': row['address'], 'score': float(row['risk_score'])})
conn.commit()

# Check labels
cursor.execute('MATCH (n:HighRisk) RETURN count(n)')
hr = cursor.fetchone()[0]
cursor.execute('MATCH (n:CriticalRisk) RETURN count(n)')
cr = cursor.fetchone()[0]
print(f'Labels applied: HighRisk={hr}, CriticalRisk={cr}')

conn.close()
print('Done!')
