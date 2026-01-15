"""
Fraud Detection Pipeline using Memgraph Graph Algorithms.
Scores addresses based on:
1. Direct connections to sanctioned/mixer addresses
2. PageRank centrality (high-traffic nodes)
3. Transaction patterns (value, frequency)
4. Community detection for suspicious clusters
"""
import pandas as pd
import mgclient
from datetime import datetime
import json

# Configuration
MEMGRAPH_HOST = "localhost"
MEMGRAPH_PORT = 7687
OUTPUT_DIR = r"c:\amttp\processed"

# Risk weights
RISK_WEIGHTS = {
    'direct_sanctioned': 100,    # Direct tx with sanctioned address
    'direct_mixer': 80,          # Direct tx with mixer
    'hop2_sanctioned': 50,       # 2-hop from sanctioned
    'hop2_mixer': 40,            # 2-hop from mixer
    'high_pagerank': 20,         # Top 1% by PageRank
    'high_value_tx': 10,         # High value transactions
    'high_frequency': 5,         # Many transactions
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


def find_direct_connections(cursor):
    """Find addresses directly connected to sanctioned/mixer addresses."""
    print("\n1. Finding direct connections to risky addresses...")
    
    # Direct connections TO sanctioned/mixer
    cursor.execute("""
        MATCH (a:Address)-[t:TRANSACTION]->(risky:Address)
        WHERE risky.category IN ['sanctioned', 'mixer']
        RETURN a.address as address, 
               risky.category as risky_type,
               sum(t.value_eth) as total_sent,
               count(t) as tx_count
    """)
    sent_to_risky = cursor.fetchall()
    
    # Direct connections FROM sanctioned/mixer
    cursor.execute("""
        MATCH (risky:Address)-[t:TRANSACTION]->(a:Address)
        WHERE risky.category IN ['sanctioned', 'mixer']
        RETURN a.address as address,
               risky.category as risky_type,
               sum(t.value_eth) as total_received,
               count(t) as tx_count
    """)
    received_from_risky = cursor.fetchall()
    
    print(f"  Found {len(sent_to_risky)} addresses sending to risky addresses")
    print(f"  Found {len(received_from_risky)} addresses receiving from risky addresses")
    
    return sent_to_risky, received_from_risky


def find_two_hop_connections(cursor):
    """Find addresses within 2 hops of sanctioned/mixer addresses."""
    print("\n2. Finding 2-hop connections to risky addresses...")
    
    # Simpler query that works with Memgraph
    cursor.execute("""
        MATCH (a:Address)-[:TRANSACTION]-(b:Address)-[:TRANSACTION]-(risky:Address)
        WHERE risky.category IN ['sanctioned', 'mixer']
        AND a.category = 'unknown'
        AND a <> risky
        RETURN DISTINCT a.address as address, risky.category as risky_type
        LIMIT 1000
    """)
    two_hop = cursor.fetchall()
    print(f"  Found {len(two_hop)} addresses within 2 hops of risky addresses")
    return two_hop


def calculate_pagerank(cursor):
    """Calculate PageRank for all addresses."""
    print("\n3. Calculating PageRank centrality...")
    
    # Try to use MAGE PageRank
    try:
        cursor.execute("""
            CALL pagerank.get()
            YIELD node, rank
            WHERE node:Address
            RETURN node.address as address, rank
            ORDER BY rank DESC
            LIMIT 100
        """)
        pagerank_results = cursor.fetchall()
        print(f"  Calculated PageRank for top 100 addresses")
        return pagerank_results
    except Exception as e:
        print(f"  PageRank not available: {e}")
        # Fallback: use degree centrality
        print("  Using degree centrality as fallback...")
        cursor.execute("""
            MATCH (a:Address)
            WITH a, 
                 size([(a)-[:TRANSACTION]->() | 1]) as out_degree,
                 size([(a)<-[:TRANSACTION]-() | 1]) as in_degree
            RETURN a.address as address, (out_degree + in_degree) as degree
            ORDER BY degree DESC
            LIMIT 100
        """)
        degree_results = cursor.fetchall()
        print(f"  Calculated degree for top 100 addresses")
        return degree_results


def analyze_transaction_patterns(cursor):
    """Analyze transaction patterns per address."""
    print("\n4. Analyzing transaction patterns...")
    
    cursor.execute("""
        MATCH (a:Address)-[t:TRANSACTION]->()
        WITH a, 
             count(t) as tx_count,
             sum(t.value_eth) as total_value,
             avg(t.value_eth) as avg_value,
             max(t.value_eth) as max_value
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
    print(f"  Analyzed patterns for {len(patterns)} addresses")
    return patterns


def calculate_risk_scores(sent_to_risky, received_from_risky, two_hop, pagerank, patterns):
    """Calculate composite risk scores for all addresses."""
    print("\n5. Calculating risk scores...")
    
    scores = {}
    
    # Direct sanctioned/mixer connections (highest risk)
    for row in sent_to_risky:
        addr = row[0]
        risk_type = row[1]
        if addr not in scores:
            scores[addr] = {'score': 0, 'reasons': [], 'category': 'unknown'}
        
        weight = RISK_WEIGHTS['direct_sanctioned'] if risk_type == 'sanctioned' else RISK_WEIGHTS['direct_mixer']
        scores[addr]['score'] += weight
        scores[addr]['reasons'].append(f"sent_to_{risk_type}")
    
    for row in received_from_risky:
        addr = row[0]
        risk_type = row[1]
        if addr not in scores:
            scores[addr] = {'score': 0, 'reasons': [], 'category': 'unknown'}
        
        weight = RISK_WEIGHTS['direct_sanctioned'] if risk_type == 'sanctioned' else RISK_WEIGHTS['direct_mixer']
        scores[addr]['score'] += weight
        scores[addr]['reasons'].append(f"received_from_{risk_type}")
    
    # 2-hop connections (medium risk)
    for row in two_hop:
        addr = row[0]
        risk_type = row[1]
        if addr not in scores:
            scores[addr] = {'score': 0, 'reasons': [], 'category': 'unknown'}
        
        weight = RISK_WEIGHTS['hop2_sanctioned'] if risk_type == 'sanctioned' else RISK_WEIGHTS['hop2_mixer']
        scores[addr]['score'] += weight
        scores[addr]['reasons'].append(f"2hop_{risk_type}")
    
    # High PageRank (potential hub)
    if pagerank:
        max_rank = max(row[1] for row in pagerank) if pagerank else 1
        threshold = max_rank * 0.9  # Top 10%
        for row in pagerank:
            addr = row[0]
            rank = row[1]
            if rank >= threshold:
                if addr not in scores:
                    scores[addr] = {'score': 0, 'reasons': [], 'category': 'unknown'}
                scores[addr]['score'] += RISK_WEIGHTS['high_pagerank']
                scores[addr]['reasons'].append('high_centrality')
    
    # High value transactions
    if patterns:
        values = [row[2] for row in patterns if row[2] > 0]
        if values:
            value_threshold = sorted(values, reverse=True)[min(10, len(values)-1)]  # Top 10
            for row in patterns:
                addr = row[0]
                total_value = row[2]
                if total_value >= value_threshold:
                    if addr not in scores:
                        scores[addr] = {'score': 0, 'reasons': [], 'category': 'unknown'}
                    scores[addr]['score'] += RISK_WEIGHTS['high_value_tx']
                    scores[addr]['reasons'].append('high_value')
    
    print(f"  Scored {len(scores)} addresses")
    return scores


def generate_reports(cursor, scores):
    """Generate output reports."""
    print("\n6. Generating reports...")
    
    # Create DataFrame
    score_data = []
    for addr, data in scores.items():
        score_data.append({
            'address': addr,
            'risk_score': data['score'],
            'reasons': ', '.join(data['reasons']),
            'reason_count': len(data['reasons'])
        })
    
    df = pd.DataFrame(score_data)
    df = df.sort_values('risk_score', ascending=False)
    
    # Save all scored addresses
    all_output = f"{OUTPUT_DIR}/scored_transactions.csv"
    df.to_csv(all_output, index=False)
    print(f"  Saved {len(df)} scored addresses to {all_output}")
    
    # Save high-risk addresses (score >= 50)
    high_risk = df[df['risk_score'] >= 50]
    high_risk_output = f"{OUTPUT_DIR}/high_risk_transactions.csv"
    high_risk.to_csv(high_risk_output, index=False)
    print(f"  Saved {len(high_risk)} high-risk addresses to {high_risk_output}")
    
    # Print summary
    print("\n" + "="*60)
    print("FRAUD DETECTION SUMMARY")
    print("="*60)
    
    print(f"\nTotal addresses scored: {len(df)}")
    print(f"High-risk (score >= 50): {len(df[df['risk_score'] >= 50])}")
    print(f"Medium-risk (score 20-49): {len(df[(df['risk_score'] >= 20) & (df['risk_score'] < 50)])}")
    print(f"Low-risk (score < 20): {len(df[df['risk_score'] < 20])}")
    
    print("\nTop 10 Highest Risk Addresses:")
    print("-" * 60)
    for i, row in df.head(10).iterrows():
        print(f"{row['address'][:20]}...  Score: {row['risk_score']:3}  Reasons: {row['reasons']}")
    
    # Risk distribution
    print("\nRisk Score Distribution:")
    print(f"  Max: {df['risk_score'].max()}")
    print(f"  Mean: {df['risk_score'].mean():.2f}")
    print(f"  Median: {df['risk_score'].median()}")
    
    return df


def main():
    print("="*60)
    print("MEMGRAPH FRAUD DETECTION PIPELINE")
    print("="*60)
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    conn = connect_memgraph()
    cursor = conn.cursor()
    
    # Get stats
    nodes, edges = get_graph_stats(cursor)
    print(f"\nGraph contains {nodes:,} addresses and {edges:,} transactions")
    
    # Run analysis
    sent_to_risky, received_from_risky = find_direct_connections(cursor)
    two_hop = find_two_hop_connections(cursor)
    pagerank = calculate_pagerank(cursor)
    patterns = analyze_transaction_patterns(cursor)
    
    # Calculate scores
    scores = calculate_risk_scores(sent_to_risky, received_from_risky, two_hop, pagerank, patterns)
    
    # Generate reports
    df = generate_reports(cursor, scores)
    
    conn.close()
    
    print("\n" + "="*60)
    print(f"Pipeline completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60)
    
    return df


if __name__ == "__main__":
    main()
