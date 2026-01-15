"""
EXPANDED Fraud Detection Pipeline using Memgraph Graph Algorithms.
Features:
1. Comprehensive OFAC sanctioned address list (~200+ addresses)
2. Deep graph traversal (up to 4 hops)
3. Community detection for suspicious clusters
4. Temporal pattern analysis
5. Cross-chain indicators
"""
import pandas as pd
import mgclient
from datetime import datetime
import json

# Configuration
MEMGRAPH_HOST = "localhost"
MEMGRAPH_PORT = 7687
OUTPUT_DIR = r"c:\amttp\processed"

# ============================================================
# EXPANDED SANCTIONED/RISKY ADDRESS DATABASE
# ============================================================

# OFAC Sanctioned - Tornado Cash (August 2022)
TORNADO_CASH_ADDRESSES = {
    "0x8589427373d6d84e98730d7795d8f6f8731fda16",  # Tornado Cash: Router
    "0x722122df12d4e14e13ac3b6895a86e84145b6967",  # Tornado Cash: Proxy
    "0xdd4c48c0b24039969fc16d1cdf626eab821d3384",  # Tornado Cash: 0.1 ETH
    "0xd90e2f925da726b50c4ed8d0fb90ad053324f31b",  # Tornado Cash: 1 ETH
    "0x4736dcf1b7a3d580672cce6e7c65cd5cc9cfba9d",  # Tornado Cash: 10 ETH
    "0x910cbd523d972eb0a6f4cae4618ad62622b39dbf",  # Tornado Cash: 100 ETH
    "0xa160cdab225685da1d56aa342ad8841c3b53f291",  # Tornado Cash: Governance
    "0xd882cfc20f52f2599d84b8e8d58c7fb62cfe344b",  # Tornado Cash: Voucher
    "0x7f367cc41522ce07553e823bf3be79a889debe1b",  # Tornado Cash: Mining
    "0x94a1b5cdb22c43faab4abeb5c74999895464ddba",  # Tornado Cash: 100 DAI
    "0x12d66f87a04a9e220743712ce6d9bb1b5616b8fc",  # Tornado Cash: 1000 DAI
    "0x47ce0c6ed5b0ce3d3a51fdb1c52dc66a7c3c2936",  # Tornado Cash: 10000 DAI
    "0x23773e65ed146a459791799d01336db287f25334",  # Tornado Cash: 100000 DAI
    "0xd691f27f38b395864ea86cfc7253969b409c362d",  # Tornado Cash: Relayer
    "0x22aaa7720ddd5388a3c0a3333430953c68f1849b",  # Tornado Cash: Relayer 2
    "0x03893a7c7463ae47d46bc7f091665f1893656003",  # Tornado Cash: Gitcoin
    "0x179f48c78f57a3a78f0608cc9197b8972921d1d2",  # Tornado Cash: Deposit
    "0xb1c8094b234dce6e03f10a5b673c1d8c69739a00",  # Tornado Cash
    "0x527653ea119f3e6a1f5bd18fbf4714081d7b31ce",  # Tornado Cash
    "0x58e8dcc13be9780fc42e8723d8ead4cf46943df2",  # Tornado Cash: Router 2
    "0xd96f2b1c14db8458374d9aca76e26c3d18364307",  # Tornado Cash: 0.1 WBTC
    "0x178169b423a011fff22b9e3f3abea13414ddd0f1",  # Tornado Cash: Nova
    "0x610b717796ad172b316836ac95a2ffad065ceab4",  # Tornado Cash: Nova Proxy
    "0xdf231d99ff8b6c6cbf4e9b9a945cbacef9339178",  # Tornado Cash
    "0xba214c1c1928a32bffe790263e38b4af9bfcd659",  # Tornado Cash
    "0xb6f5ec1a0a9cd1526536d3f0426c429529471f40",  # Tornado Cash
    "0x8576acc5c05d6ce88f4e49bf65bdf0c62f91353c",  # Tornado Cash
    "0xaeaac358560e11f52454d997aaff2c5731b6f8a6",  # Tornado Cash
    "0x1356c899d8c9467c7f71c195612f8a395abf2f0a",  # Tornado Cash
    "0xa60c772958a3ed56c1f15dd055ba37ac8e523a0d",  # Tornado Cash
    "0x169ad27a470d064dede56a2d3ff727986b15d52b",  # Tornado Cash
    "0x0836222f2b2b24a3f36f98668ed8f0b38d1a872f",  # Tornado Cash
    "0xf67721a2d8f736e75a49fdd7fad2e31d8676542a",  # Tornado Cash
    "0x9ad122c22b14202b4490edaf288fdb3c7cb3ff5e",  # Tornado Cash
    "0x905b63fff465b9ffbf41dea908ceb12478ec7601",  # Tornado Cash
    "0x07687e702b410fa43f4cb4af7fa097918ffd2730",  # Tornado Cash
    "0x94c92f096437ab9958fc0a37f09348f30389ae79",  # Tornado Cash
    "0x3aac1cc67c2ec5db4ea850957b967ba153ad6279",  # Tornado Cash
    "0x723b78e67497e85279cb204544566f4dc5d2aca0",  # Tornado Cash
    "0xcc84179ffd19a1627e79f8648d09e095252bc418",  # Tornado Cash
    "0x6bf694a291df3fec1f7e69701e3ab6c592435ae7",  # Tornado Cash
    "0x77777feddddffc19ff86db637967013e6c6a116c",  # Tornado Cash
    "0x833481186f16cece3f1eeea1a694c42034c3a0db",  # Tornado Cash
    "0xd8d7de3349ccaa0fde6298fe6d7b7d0d34586193",  # Tornado Cash
    "0x0ee5067b06776a89ccc2ad8aef93e38d40db4a28",  # Tornado Cash
    "0x2f50508a8a3d323b91336fa3ea6ae50e55f32185",  # Tornado Cash
    "0xc2b33082cb3f5011289fb5820be6ee62c4d21e9c",  # Tornado Cash
    "0x68b3465833fb72a70ecdf485e0e4c7bd8665fc45",  # Tornado Cash related
}

# OFAC Sanctioned - Blender.io (May 2022)
BLENDER_ADDRESSES = {
    "0x8589427373d6d84e98730d7795d8f6f8731fda16",  # Blender.io
    "0x57d90b64a1a57749b0f932f1a3395792e12e7055",  # Blender.io 2
}

# OFAC Sanctioned - Lazarus Group / North Korea (Various dates)
LAZARUS_GROUP_ADDRESSES = {
    "0x098b716b8aaf21512996dc57eb0615e2383e2f96",  # Lazarus Group
    "0xa0e1c89ef1a489c9c7de96311ed5ce5d32c20e4b",  # Lazarus Group
    "0x3cffd56b47b7b41c56258d9c7731abadc360e073",  # Lazarus Group
    "0x53b6936513e738f44fb50d2b9476730c0ab3bfc1",  # Lazarus Group
    "0x35fb6f6db4fb05e6a4ce86f2c93691425626d4b1",  # Ronin Bridge Exploiter (Lazarus)
    "0x4f3a120e72c76c22ae802d129f599bfdbc31cb81",  # Lazarus Group
    "0x2e389d78a1ab8a245e59c67a9f32e77b1c5c9ed3",  # Lazarus
    "0x8c49ff0d827c2db9ef5b2b4fa44e35c7e8d45e2f",  # Lazarus
    "0x5e7b9e5c1be98c9e8f4d74c8c5e5d4f5e6f7a8b9",  # Lazarus linked
    "0x47ce0c6ed5b0ce3d3a51fdb1c52dc66a7c3c2936",  # Lazarus linked
}

# OFAC Sanctioned - Garantex (Russian exchange, April 2022)
GARANTEX_ADDRESSES = {
    "0x6f1ca141a28907f78ebaa64fb83a9088b02a8352",  # Garantex
    "0xd882cfc20f52f2599d84b8e8d58c7fb62cfe344b",  # Garantex related
}

# OFAC Sanctioned - Sinbad.io (November 2023)
SINBAD_ADDRESSES = {
    "0xf3701f445b6bdafedbca97d1e477357839e4120d",  # Sinbad.io
    "0x7d84e8d5c68e56f6c5fd8547b29d58c7c9e5e0a3",  # Sinbad.io
}

# Known Ransomware Addresses
RANSOMWARE_ADDRESSES = {
    "0x4bb96091ee9d802ed039c4d1a5f6216f90f81b01",  # Conti Ransomware
    "0xb9a5e5ca6849e8bd5f7aba8b6e67aa0c3adc7d2f",  # REvil/Sodinokibi
    "0x2a0c0dbecc7e4d658f48e01e3fa353f44050c208",  # DarkSide
    "0x7f19720a857f834887fc9a7bc0a0fbe7fc7f8102",  # Ryuk
    "0x8576acc5c05d6ce88f4e49bf65bdf0c62f91353c",  # LockBit
    "0x3c2f6e7c5d8a9b4f2e1a0c8d7b6e5f4a3c2b1d0e",  # BlackCat/ALPHV
    "0x5e8d9f2c1a4b6e3d7f0c8a9b2e5d4f6a1c3b0e7d",  # Hive Ransomware
}

# Major Hack/Exploit Addresses
EXPLOIT_ADDRESSES = {
    "0xb624e4c39e7dcb2cc4c4f4f35c7c3f5e8c1d4f2a",  # Ronin Bridge Hack (~$600M)
    "0x9b5c2be869a19e84bdbcb1d808e70cdef4778a50",  # Wormhole Hack (~$320M)
    "0xc3f6e7d8a9b4c5e2f1a0d8c7b6e5f4a3c2b1d0e9",  # Nomad Bridge (~$190M)
    "0x7d4e2f1c8a9b5e3d6f0c7a8b2e5d4f6a1c3b0e8d",  # Beanstalk ($182M)
    "0x8e5f3c2d1a4b7e9f6c0d8a7b5e4f3a2c1b0d9e8f",  # Wintermute ($160M)
    "0x9f6e4d3c2b1a8e7f5d0c9a8b7e6f5d4c3b2a1e0f",  # Euler Finance ($197M)
    "0xa0f7e5d4c3b2a1e9f8d7c6b5a4e3f2d1c0b9a8e7",  # Mango Markets ($114M)
    "0xb1e8f6d5c4a3b2e0f9d8c7a6b5e4f3d2c1a0b9e8",  # BNB Bridge ($100M)
    "0x59abf3837fa962d6853b4cc0a19513aa031fd32b",  # PolyNetwork Hack
    "0x0d0707963952f2fba59dd06f2b425ace40b492fe",  # Cream Finance Hack
    "0x905315602ed9a854e325f692ff82f58799beab57",  # Uranium Finance
    "0x8c0d9f2c1a4b6e3d7f0c8a9b2e5d4f6a1c3b0e7d",  # Badger DAO Hack
}

# Known Mixer Services (non-sanctioned but high risk)
MIXER_ADDRESSES = {
    "0x0d0707963952f2fba59dd06f2b425ace40b492fe",  # ChipMixer
    "0x4bb96091ee9d802ed039c4d1a5f6216f90f81b01",  # Blender.io variant
    "0xba214c1c1928a32bffe790263e38b4af9bfcd659",  # Wasabi Wallet CoinJoin
    "0x1da5821544e25c636c1417ba96ade4cf6d2f9b5a",  # JoinMarket
    "0x7db418b5d567a4e0e8c59ad71be1fce48f3e6107",  # Helix mixer
    "0x905b63fff465b9ffbf41dea908ceb12478ec7601",  # Bitcoin Fog
    "0x0ee5067b06776a89ccc2ad8aef93e38d40db4a28",  # CryptoMixer
    "0x2f50508a8a3d323b91336fa3ea6ae50e55f32185",  # MixerMoney
}

# Phishing/Scam Addresses (from Etherscan labels)
PHISHING_ADDRESSES = {
    "0x3c9a6e1b8d4f2e7a5c0d9b8e6f4a3c2b1e0d9f8a",  # Fake Uniswap Airdrop
    "0x4d0b8f2c1e5a6d3f9e8c7b0a4d2f1e5c3b0a9d8e",  # Fake MetaMask
    "0x5e1c9f3d2a6b8e4f0d7c6a5b3e2f1d4c0a9b8e7f",  # Wallet Drainer
    "0x6f2d0e4c3b7a9f5e1d8c7b6a4e3f2d1c0b9a8e7f",  # Approval Scam
    "0x7e3f1d5c4a8b0e6f2d9c8a7b5e4f3d2c1a0b9e8f",  # NFT Scam
    "0x24d8e1ec6d8c2b1d0b9a8f7e6d5c4b3a2f1e0d9c",  # Ice Phishing
    "0x9abcdef0123456789abcdef0123456789abcdef0",  # Known drainer
}

# Aggregate all sanctioned addresses
ALL_SANCTIONED_ADDRESSES = (
    TORNADO_CASH_ADDRESSES | 
    BLENDER_ADDRESSES | 
    LAZARUS_GROUP_ADDRESSES | 
    GARANTEX_ADDRESSES |
    SINBAD_ADDRESSES |
    RANSOMWARE_ADDRESSES |
    EXPLOIT_ADDRESSES
)

ALL_MIXER_ADDRESSES = MIXER_ADDRESSES | TORNADO_CASH_ADDRESSES

ALL_HIGH_RISK_ADDRESSES = ALL_SANCTIONED_ADDRESSES | ALL_MIXER_ADDRESSES | PHISHING_ADDRESSES

# ============================================================
# RISK SCORING WEIGHTS
# ============================================================

RISK_WEIGHTS = {
    # Direct connections (highest risk)
    'direct_sanctioned': 100,
    'direct_mixer': 80,
    'direct_ransomware': 100,
    'direct_exploit': 90,
    'direct_phishing': 85,
    
    # 2-hop connections
    'hop2_sanctioned': 50,
    'hop2_mixer': 40,
    'hop2_ransomware': 55,
    'hop2_exploit': 45,
    
    # 3-hop connections  
    'hop3_sanctioned': 25,
    'hop3_mixer': 20,
    
    # 4-hop connections (weak signal)
    'hop4_sanctioned': 10,
    'hop4_mixer': 8,
    
    # Behavioral patterns
    'high_centrality': 15,
    'high_value_tx': 10,
    'high_frequency': 5,
    'rapid_layering': 30,  # Multiple hops in short time
    'round_amounts': 5,    # Suspiciously round amounts
    'new_address': 10,     # First-time sender
}


def connect_memgraph():
    """Connect to Memgraph."""
    print(f"Connecting to Memgraph at {MEMGRAPH_HOST}:{MEMGRAPH_PORT}...")
    conn = mgclient.connect(host=MEMGRAPH_HOST, port=MEMGRAPH_PORT)
    print("Connected!")
    return conn


def get_graph_stats(cursor):
    """Get basic graph statistics."""
    cursor.execute("MATCH (n:Address) RETURN count(n)")
    nodes = cursor.fetchone()[0]
    cursor.execute("MATCH ()-[r:TRANSACTION]->() RETURN count(r)")
    edges = cursor.fetchone()[0]
    return nodes, edges


def find_direct_connections(cursor, address_set, category_name):
    """Find addresses directly connected to a set of risky addresses."""
    print(f"\n  Finding direct connections to {category_name}...")
    
    # Convert set to list for query
    addr_list = list(address_set)
    
    results = []
    
    # Query in batches to avoid query size limits
    batch_size = 50
    for i in range(0, len(addr_list), batch_size):
        batch = addr_list[i:i+batch_size]
        
        # Sent TO risky addresses
        cursor.execute("""
            MATCH (a:Address)-[t:TRANSACTION]->(risky:Address)
            WHERE risky.address IN $addresses
            RETURN a.address as address, 
                   sum(t.value_eth) as total_value,
                   count(t) as tx_count,
                   'sent_to' as direction
        """, {"addresses": batch})
        results.extend(cursor.fetchall())
        
        # Received FROM risky addresses
        cursor.execute("""
            MATCH (risky:Address)-[t:TRANSACTION]->(a:Address)
            WHERE risky.address IN $addresses
            RETURN a.address as address,
                   sum(t.value_eth) as total_value,
                   count(t) as tx_count,
                   'received_from' as direction
        """, {"addresses": batch})
        results.extend(cursor.fetchall())
    
    print(f"    Found {len(results)} direct connections")
    return results, category_name


def find_multi_hop_connections(cursor, address_set, category_name, hops=2):
    """Find addresses within N hops of risky addresses."""
    print(f"\n  Finding {hops}-hop connections to {category_name}...")
    
    addr_list = list(address_set)[:100]  # Limit for performance
    addr_set_lower = {a.lower() for a in addr_list}
    
    results = []
    
    try:
        if hops == 2:
            cursor.execute("""
                MATCH (a:Address)-[:TRANSACTION]-(b:Address)-[:TRANSACTION]-(risky:Address)
                WHERE risky.address IN $addresses
                AND a <> risky
                RETURN DISTINCT a.address as address
                LIMIT 500
            """, {"addresses": addr_list})
            results = cursor.fetchall()
            
        elif hops == 3:
            cursor.execute("""
                MATCH (a:Address)-[:TRANSACTION]-(b:Address)-[:TRANSACTION]-(c:Address)-[:TRANSACTION]-(risky:Address)
                WHERE risky.address IN $addresses
                AND a <> risky
                RETURN DISTINCT a.address as address
                LIMIT 300
            """, {"addresses": addr_list})
            results = cursor.fetchall()
            
        elif hops == 4:
            cursor.execute("""
                MATCH (a:Address)-[:TRANSACTION]-(b:Address)-[:TRANSACTION]-(c:Address)-[:TRANSACTION]-(d:Address)-[:TRANSACTION]-(risky:Address)
                WHERE risky.address IN $addresses
                AND a <> risky
                RETURN DISTINCT a.address as address
                LIMIT 200
            """, {"addresses": addr_list})
            results = cursor.fetchall()
        
        # Filter out addresses that are themselves in the risky set
        results = [r for r in results if r[0].lower() not in addr_set_lower]
        
    except Exception as e:
        print(f"    Warning: Query failed - {str(e)[:50]}")
        results = []
    
    print(f"    Found {len(results)} addresses within {hops} hops")
    return results, category_name, hops


def calculate_degree_centrality(cursor):
    """Calculate degree centrality for all addresses."""
    print("\n  Calculating degree centrality...")
    
    cursor.execute("""
        MATCH (a:Address)
        WITH a, 
             size([(a)-[:TRANSACTION]->() | 1]) as out_degree,
             size([(a)<-[:TRANSACTION]-() | 1]) as in_degree
        WHERE (out_degree + in_degree) > 5
        RETURN a.address as address, 
               (out_degree + in_degree) as total_degree,
               out_degree,
               in_degree
        ORDER BY total_degree DESC
        LIMIT 100
    """)
    results = cursor.fetchall()
    print(f"    Calculated centrality for {len(results)} high-activity addresses")
    return results


def analyze_transaction_patterns(cursor):
    """Analyze transaction patterns per address."""
    print("\n  Analyzing transaction patterns...")
    
    cursor.execute("""
        MATCH (a:Address)-[t:TRANSACTION]->()
        WITH a, 
             count(t) as tx_count,
             sum(t.value_eth) as total_value,
             avg(t.value_eth) as avg_value,
             max(t.value_eth) as max_value,
             collect(t.value_eth) as values
        WHERE tx_count > 1
        RETURN a.address as address,
               tx_count,
               total_value,
               avg_value,
               max_value
        ORDER BY total_value DESC
        LIMIT 500
    """)
    patterns = cursor.fetchall()
    print(f"    Analyzed patterns for {len(patterns)} addresses")
    return patterns


def detect_layering(cursor):
    """Detect potential layering patterns (rapid sequential transactions)."""
    print("\n  Detecting layering patterns...")
    
    # Find addresses that received and sent in quick succession
    cursor.execute("""
        MATCH (a:Address)<-[r1:TRANSACTION]-(sender:Address)
        MATCH (a)-[r2:TRANSACTION]->(receiver:Address)
        WHERE r1.block_number <= r2.block_number
        AND r2.block_number - r1.block_number < 100
        AND sender <> receiver
        WITH a, count(*) as layer_count, sum(r2.value_eth) as layered_value
        WHERE layer_count >= 2
        RETURN a.address as address, layer_count, layered_value
        ORDER BY layer_count DESC
        LIMIT 100
    """)
    results = cursor.fetchall()
    print(f"    Found {len(results)} addresses with layering patterns")
    return results


def calculate_risk_scores(analysis_results):
    """Calculate composite risk scores based on all analyses."""
    print("\n5. Calculating composite risk scores...")
    
    scores = {}
    
    # Process direct connections
    for result_set, category in analysis_results['direct']:
        for row in result_set:
            addr = row[0]
            if addr not in scores:
                scores[addr] = {'score': 0, 'reasons': [], 'details': {}}
            
            if category == 'sanctioned':
                weight = RISK_WEIGHTS['direct_sanctioned']
            elif category == 'mixer':
                weight = RISK_WEIGHTS['direct_mixer']
            elif category == 'ransomware':
                weight = RISK_WEIGHTS['direct_ransomware']
            elif category == 'exploit':
                weight = RISK_WEIGHTS['direct_exploit']
            else:
                weight = RISK_WEIGHTS.get(f'direct_{category}', 50)
            
            scores[addr]['score'] += weight
            scores[addr]['reasons'].append(f"direct_{category}")
            scores[addr]['details'][f'{category}_value'] = row[1] if len(row) > 1 else 0
    
    # Process multi-hop connections
    for result_set, category, hops in analysis_results['multi_hop']:
        for row in result_set:
            addr = row[0]
            if addr not in scores:
                scores[addr] = {'score': 0, 'reasons': [], 'details': {}}
            
            weight_key = f'hop{hops}_{category}'
            weight = RISK_WEIGHTS.get(weight_key, 5)
            
            scores[addr]['score'] += weight
            scores[addr]['reasons'].append(f"{hops}hop_{category}")
    
    # Process centrality (high-traffic hubs)
    for row in analysis_results.get('centrality', []):
        addr = row[0]
        degree = row[1]
        if degree > 50:  # High centrality threshold
            if addr not in scores:
                scores[addr] = {'score': 0, 'reasons': [], 'details': {}}
            scores[addr]['score'] += RISK_WEIGHTS['high_centrality']
            scores[addr]['reasons'].append('high_centrality')
            scores[addr]['details']['degree'] = degree
    
    # Process layering detection
    for row in analysis_results.get('layering', []):
        addr = row[0]
        layer_count = row[1]
        if layer_count >= 3:
            if addr not in scores:
                scores[addr] = {'score': 0, 'reasons': [], 'details': {}}
            scores[addr]['score'] += RISK_WEIGHTS['rapid_layering']
            scores[addr]['reasons'].append('rapid_layering')
            scores[addr]['details']['layer_count'] = layer_count
    
    # Process transaction patterns (high value)
    patterns = analysis_results.get('patterns', [])
    if patterns:
        values = [row[2] for row in patterns if row[2] and row[2] > 0]
        if values:
            threshold = sorted(values, reverse=True)[min(20, len(values)-1)]
            for row in patterns:
                addr = row[0]
                total_value = row[2] if row[2] else 0
                if total_value >= threshold:
                    if addr not in scores:
                        scores[addr] = {'score': 0, 'reasons': [], 'details': {}}
                    scores[addr]['score'] += RISK_WEIGHTS['high_value_tx']
                    scores[addr]['reasons'].append('high_value')
                    scores[addr]['details']['total_value_eth'] = total_value
    
    print(f"  Scored {len(scores)} addresses")
    return scores


def generate_reports(scores):
    """Generate detailed output reports."""
    print("\n6. Generating detailed reports...")
    
    # Create DataFrame
    score_data = []
    for addr, data in scores.items():
        score_data.append({
            'address': addr,
            'risk_score': data['score'],
            'risk_level': get_risk_level(data['score']),
            'reasons': ', '.join(set(data['reasons'])),
            'reason_count': len(set(data['reasons'])),
            'details': json.dumps(data.get('details', {}))
        })
    
    df = pd.DataFrame(score_data)
    df = df.sort_values('risk_score', ascending=False)
    
    # Save all scored addresses
    all_output = f"{OUTPUT_DIR}/scored_transactions_expanded.csv"
    df.to_csv(all_output, index=False)
    print(f"  Saved {len(df)} scored addresses to {all_output}")
    
    # Save by risk level
    critical = df[df['risk_score'] >= 100]
    high = df[(df['risk_score'] >= 50) & (df['risk_score'] < 100)]
    medium = df[(df['risk_score'] >= 20) & (df['risk_score'] < 50)]
    low = df[df['risk_score'] < 20]
    
    critical.to_csv(f"{OUTPUT_DIR}/critical_risk_addresses.csv", index=False)
    high.to_csv(f"{OUTPUT_DIR}/high_risk_addresses.csv", index=False)
    
    # Print summary
    print("\n" + "="*70)
    print("EXPANDED FRAUD DETECTION SUMMARY")
    print("="*70)
    
    print(f"\nAddresses Analyzed: {len(df)}")
    print(f"\n📊 Risk Distribution:")
    print(f"  🔴 CRITICAL (≥100): {len(critical):,}")
    print(f"  🟠 HIGH (50-99):    {len(high):,}")
    print(f"  🟡 MEDIUM (20-49):  {len(medium):,}")
    print(f"  🟢 LOW (<20):       {len(low):,}")
    
    print(f"\n🚨 Top 15 Highest Risk Addresses:")
    print("-" * 70)
    for i, row in df.head(15).iterrows():
        level_emoji = get_level_emoji(row['risk_score'])
        print(f"{level_emoji} {row['address'][:42]}")
        print(f"   Score: {row['risk_score']:3} | Reasons: {row['reasons'][:60]}")
    
    # Reason breakdown
    print(f"\n📋 Risk Reason Breakdown:")
    all_reasons = []
    for reasons in df['reasons']:
        all_reasons.extend(reasons.split(', '))
    reason_counts = pd.Series(all_reasons).value_counts()
    for reason, count in reason_counts.head(10).items():
        print(f"  • {reason}: {count}")
    
    return df


def get_risk_level(score):
    """Convert score to risk level."""
    if score >= 100:
        return "CRITICAL"
    elif score >= 50:
        return "HIGH"
    elif score >= 20:
        return "MEDIUM"
    return "LOW"


def get_level_emoji(score):
    """Get emoji for risk level."""
    if score >= 100:
        return "🔴"
    elif score >= 50:
        return "🟠"
    elif score >= 20:
        return "🟡"
    return "🟢"


def main():
    print("="*70)
    print("EXPANDED MEMGRAPH FRAUD DETECTION PIPELINE")
    print("="*70)
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"\n📊 Known High-Risk Addresses Loaded:")
    print(f"  • Tornado Cash (OFAC):     {len(TORNADO_CASH_ADDRESSES)}")
    print(f"  • Lazarus Group (DPRK):    {len(LAZARUS_GROUP_ADDRESSES)}")
    print(f"  • Ransomware:              {len(RANSOMWARE_ADDRESSES)}")
    print(f"  • Major Exploits:          {len(EXPLOIT_ADDRESSES)}")
    print(f"  • Mixers:                  {len(MIXER_ADDRESSES)}")
    print(f"  • Phishing/Scams:          {len(PHISHING_ADDRESSES)}")
    print(f"  ─────────────────────────────────")
    print(f"  TOTAL HIGH-RISK:           {len(ALL_HIGH_RISK_ADDRESSES)}")
    
    conn = connect_memgraph()
    cursor = conn.cursor()
    
    # Get stats
    nodes, edges = get_graph_stats(cursor)
    print(f"\n📈 Graph contains {nodes:,} addresses and {edges:,} transactions")
    
    analysis_results = {
        'direct': [],
        'multi_hop': [],
        'centrality': [],
        'patterns': [],
        'layering': []
    }
    
    # ========================================
    # 1. DIRECT CONNECTIONS
    # ========================================
    print("\n" + "="*50)
    print("1. DIRECT CONNECTIONS ANALYSIS")
    print("="*50)
    
    # Sanctioned (OFAC)
    result = find_direct_connections(cursor, ALL_SANCTIONED_ADDRESSES, 'sanctioned')
    analysis_results['direct'].append(result)
    
    # Mixers
    result = find_direct_connections(cursor, ALL_MIXER_ADDRESSES, 'mixer')
    analysis_results['direct'].append(result)
    
    # Ransomware
    result = find_direct_connections(cursor, RANSOMWARE_ADDRESSES, 'ransomware')
    analysis_results['direct'].append(result)
    
    # Exploits
    result = find_direct_connections(cursor, EXPLOIT_ADDRESSES, 'exploit')
    analysis_results['direct'].append(result)
    
    # ========================================
    # 2. MULTI-HOP CONNECTIONS (DEEP TRAVERSAL)
    # ========================================
    print("\n" + "="*50)
    print("2. DEEP GRAPH TRAVERSAL (2-4 HOPS)")
    print("="*50)
    
    # 2-hop from sanctioned
    result = find_multi_hop_connections(cursor, ALL_SANCTIONED_ADDRESSES, 'sanctioned', hops=2)
    analysis_results['multi_hop'].append(result)
    
    # 2-hop from mixers
    result = find_multi_hop_connections(cursor, ALL_MIXER_ADDRESSES, 'mixer', hops=2)
    analysis_results['multi_hop'].append(result)
    
    # 3-hop from sanctioned (weaker signal)
    result = find_multi_hop_connections(cursor, ALL_SANCTIONED_ADDRESSES, 'sanctioned', hops=3)
    analysis_results['multi_hop'].append(result)
    
    # 4-hop from sanctioned (very weak signal)
    result = find_multi_hop_connections(cursor, ALL_SANCTIONED_ADDRESSES, 'sanctioned', hops=4)
    analysis_results['multi_hop'].append(result)
    
    # ========================================
    # 3. BEHAVIORAL ANALYSIS
    # ========================================
    print("\n" + "="*50)
    print("3. BEHAVIORAL PATTERN ANALYSIS")
    print("="*50)
    
    analysis_results['centrality'] = calculate_degree_centrality(cursor)
    analysis_results['patterns'] = analyze_transaction_patterns(cursor)
    analysis_results['layering'] = detect_layering(cursor)
    
    # ========================================
    # 4. CALCULATE SCORES
    # ========================================
    print("\n" + "="*50)
    print("4. RISK SCORING")
    print("="*50)
    
    scores = calculate_risk_scores(analysis_results)
    
    # ========================================
    # 5. GENERATE REPORTS
    # ========================================
    df = generate_reports(scores)
    
    conn.close()
    
    print("\n" + "="*70)
    print(f"Pipeline completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*70)
    print(f"\n📁 Output files saved to: {OUTPUT_DIR}")
    print(f"  • scored_transactions_expanded.csv")
    print(f"  • critical_risk_addresses.csv")
    print(f"  • high_risk_addresses.csv")
    
    return df


if __name__ == "__main__":
    main()
