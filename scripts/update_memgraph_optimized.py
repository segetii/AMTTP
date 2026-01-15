"""
Update Memgraph with optimized ML results for visualization
Labels addresses based on recalibrated multi-signal detection
"""
import mgclient
import pandas as pd

print("=" * 70)
print("UPDATING MEMGRAPH WITH OPTIMIZED DETECTION RESULTS")
print("=" * 70)

# Connect to Memgraph
conn = mgclient.connect(host='localhost', port=7687)
cursor = conn.cursor()

# Load data
cv = pd.read_csv('c:/amttp/processed/cross_validated_results.csv')
hybrid = pd.read_csv('c:/amttp/processed/hybrid_risk_scores.csv')
soph = pd.read_csv('c:/amttp/processed/sophisticated_fraud_patterns.csv')

pattern_addrs = set(soph['address'].str.lower())
pattern_details = dict(zip(soph['address'].str.lower(), soph['patterns']))

# Optimized thresholds
THRESHOLDS = {
    "review": 0.55,
    "escrow": 0.75,
}

print(f"\nLoaded {len(cv)} addresses from cross-validated results")

# Clear existing risk labels (keep structural labels)
print("\nClearing old risk labels...")
cursor.execute("MATCH (a:Address) REMOVE a:FlaggedML, a:EscrowML, a:MultiSignal, a:MLOnly")
conn.commit()

# Apply multi-signal detection
flagged = []
escrow = []
multi_signal = []
ml_only = []

for _, row in cv.iterrows():
    addr = row['address'].lower()
    ml_score = row['ml_max_score']
    graph_score = row['risk_score']
    
    # Check signals
    ml_signal = ml_score >= THRESHOLDS['review']
    graph_signal = graph_score > 0
    pattern_signal = addr in pattern_addrs
    
    signal_count = sum([ml_signal, graph_signal, pattern_signal])
    
    if ml_score >= THRESHOLDS['review'] and signal_count >= 2:
        if ml_score >= THRESHOLDS['escrow']:
            escrow.append({
                'address': row['address'],
                'ml_score': ml_score,
                'graph_score': graph_score,
                'signals': signal_count,
                'patterns': pattern_details.get(addr, '')
            })
        else:
            flagged.append({
                'address': row['address'],
                'ml_score': ml_score,
                'graph_score': graph_score,
                'signals': signal_count,
                'patterns': pattern_details.get(addr, '')
            })
        multi_signal.append(row['address'])
    elif ml_score >= THRESHOLDS['review']:
        ml_only.append({
            'address': row['address'],
            'ml_score': ml_score,
            'graph_score': graph_score
        })

print(f"\n📊 Detection Results:")
print(f"   ESCROW (hold funds): {len(escrow)}")
print(f"   FLAG (review): {len(flagged)}")
print(f"   ML Only (no action): {len(ml_only)}")
print(f"   Multi-signal total: {len(multi_signal)}")

# Update Memgraph with labels and properties
print("\nUpdating Memgraph labels...")

# Add ESCROW labels
for item in escrow:
    query = """
    MATCH (a:Address {address: $addr})
    SET a:EscrowML, a:MultiSignal,
        a.ml_score = $ml_score,
        a.graph_score = $graph_score,
        a.signal_count = $signals,
        a.patterns = $patterns,
        a.action = 'ESCROW'
    """
    cursor.execute(query, {
        'addr': item['address'],
        'ml_score': item['ml_score'],
        'graph_score': item['graph_score'],
        'signals': item['signals'],
        'patterns': item['patterns']
    })

# Add FLAG labels  
for item in flagged:
    query = """
    MATCH (a:Address {address: $addr})
    SET a:FlaggedML, a:MultiSignal,
        a.ml_score = $ml_score,
        a.graph_score = $graph_score,
        a.signal_count = $signals,
        a.patterns = $patterns,
        a.action = 'FLAG'
    """
    cursor.execute(query, {
        'addr': item['address'],
        'ml_score': item['ml_score'],
        'graph_score': item['graph_score'],
        'signals': item['signals'],
        'patterns': item['patterns']
    })

# Add ML_ONLY labels (flagged by ML but no corroborating evidence)
for item in ml_only:
    query = """
    MATCH (a:Address {address: $addr})
    SET a:MLOnly,
        a.ml_score = $ml_score,
        a.graph_score = $graph_score,
        a.action = 'REVIEW'
    """
    cursor.execute(query, {
        'addr': item['address'],
        'ml_score': item['ml_score'],
        'graph_score': item['graph_score']
    })

conn.commit()

# Add pattern labels from sophisticated detection
print("\nAdding behavioral pattern labels...")
for _, row in soph.iterrows():
    patterns = row['patterns']
    addr = row['address']
    
    # Add specific pattern labels
    labels = []
    if 'SMURFING' in patterns:
        labels.append('Smurfing')
    if 'LAYERING' in patterns:
        labels.append('Layering')
    if 'FAN_OUT' in patterns:
        labels.append('FanOut')
    if 'FAN_IN' in patterns:
        labels.append('FanIn')
    if 'PEELING' in patterns:
        labels.append('Peeling')
    if 'STRUCTURING' in patterns:
        labels.append('Structuring')
    
    if labels:
        label_str = ', a:'.join(labels)
        query = f"""
        MATCH (a:Address {{address: $addr}})
        SET a:{label_str}, a.patterns = $patterns
        """
        cursor.execute(query, {'addr': addr, 'patterns': patterns})

conn.commit()

# Verify counts
print("\n" + "=" * 70)
print("VERIFICATION - Labels in Memgraph")
print("=" * 70)

queries = [
    ("Total Addresses", "MATCH (a:Address) RETURN count(a)"),
    ("ESCROW (hold funds)", "MATCH (a:EscrowML) RETURN count(a)"),
    ("FLAGGED (review)", "MATCH (a:FlaggedML) RETURN count(a)"),
    ("Multi-Signal", "MATCH (a:MultiSignal) RETURN count(a)"),
    ("ML Only (no action)", "MATCH (a:MLOnly) RETURN count(a)"),
    ("Smurfing", "MATCH (a:Smurfing) RETURN count(a)"),
    ("Layering", "MATCH (a:Layering) RETURN count(a)"),
    ("FanOut", "MATCH (a:FanOut) RETURN count(a)"),
    ("FanIn", "MATCH (a:FanIn) RETURN count(a)"),
    ("Peeling", "MATCH (a:Peeling) RETURN count(a)"),
    ("Sanctioned", "MATCH (a:Sanctioned) RETURN count(a)"),
    ("Mixer", "MATCH (a:Mixer) RETURN count(a)"),
]

for name, query in queries:
    cursor.execute(query)
    count = cursor.fetchone()[0]
    print(f"   {name}: {count}")

conn.close()

print("\n" + "=" * 70)
print("MEMGRAPH LAB QUERIES")
print("=" * 70)
print("""
Open Memgraph Lab at http://localhost:3000 and run:

1. VIEW ALL FLAGGED (Multi-Signal):
   MATCH (a:MultiSignal)-[t:SENT_TO]->(b)
   RETURN a, t, b LIMIT 100

2. VIEW ESCROW ADDRESSES (Highest Risk):
   MATCH (a:EscrowML)-[t:SENT_TO]->(b)
   RETURN a, t, b LIMIT 50

3. VIEW TRANSACTION FLOW FROM FLAGGED:
   MATCH path = (flagged:FlaggedML)-[:SENT_TO*1..3]->(dest)
   RETURN path LIMIT 100

4. VIEW SMURFING PATTERNS:
   MATCH (a:Smurfing)-[t:SENT_TO]->(b)
   RETURN a, t, b

5. VIEW LAYERING PATTERNS:
   MATCH path = (a:Layering)-[:SENT_TO*1..4]->(dest)
   RETURN path LIMIT 50

6. COMPARE: ML ALONE vs MULTI-SIGNAL:
   MATCH (ml:MLOnly) 
   RETURN 'ML Only (no action)' as type, count(ml) as count
   UNION
   MATCH (ms:MultiSignal)
   RETURN 'Multi-Signal (action taken)' as type, count(ms) as count

7. TOP THREATS BY SIGNAL COUNT:
   MATCH (a:MultiSignal)
   RETURN a.address, a.ml_score, a.graph_score, a.signal_count, a.patterns
   ORDER BY a.signal_count DESC, a.ml_score DESC
   LIMIT 20
""")
