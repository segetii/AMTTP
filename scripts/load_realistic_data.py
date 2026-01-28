#!/usr/bin/env python3
"""
Load Realistic Transaction Data for AMTTP Platform
===================================================

This script:
1. Samples transactions from the ML training data (40% of original 20k = 8k)
2. Loads wallet addresses and relationships into Memgraph
3. Loads risk scores into the Risk Engine
4. Creates JSON mock data for frontend visualization

Set DATA_FRACTION to control how much data to load (0.4 = 40%)
"""

import pandas as pd
import numpy as np
import json
import requests
from datetime import datetime, timedelta
import random
import hashlib
from pathlib import Path

# Configuration
MEMGRAPH_HOST = "localhost"
MEMGRAPH_PORT = 7687
RISK_ENGINE_URL = "http://localhost:8002"
MONGO_HOST = "localhost"
MONGO_PORT = 27017

# Data reduction: 0.4 = 40% of original data
DATA_FRACTION = 0.4
SAMPLE_SIZE = int(20000 * DATA_FRACTION)  # 8000 transactions
GRAPH_NODE_LIMIT = int(500 * DATA_FRACTION)  # 200 nodes
GRAPH_EDGE_LIMIT = int(2000 * DATA_FRACTION)  # 800 edges

OUTPUT_DIR = Path("c:/amttp/frontend/frontend/src/data")
FLUTTER_OUTPUT_DIR = Path("c:/amttp/frontend/amttp_app/assets/data")

def load_transaction_data():
    """Load and sample transaction data from parquet files."""
    print(f"Loading transaction data ({DATA_FRACTION*100:.0f}% sample)...")
    
    # Load transactions
    tx_df = pd.read_parquet('c:/amttp/processed/eth_transactions_full_labeled.parquet')
    print(f"Total transactions: {len(tx_df):,}")
    
    # Sample with stratified selection (ensure mix of risk levels)
    # Get distribution of risk classes
    risk_counts = tx_df['risk_class'].value_counts()
    print(f"Risk class distribution:\n{risk_counts}")
    
    # Stratified sample
    sampled_dfs = []
    for risk_class in tx_df['risk_class'].unique():
        class_df = tx_df[tx_df['risk_class'] == risk_class]
        # Sample proportionally but ensure at least some high-risk
        if risk_class in ['high', 'critical']:
            n_sample = min(len(class_df), max(200, int(SAMPLE_SIZE * 0.15)))
        else:
            n_sample = min(len(class_df), int(SAMPLE_SIZE * len(class_df) / len(tx_df)))
        
        sampled_dfs.append(class_df.sample(n=n_sample, random_state=42))
    
    sampled_tx = pd.concat(sampled_dfs).sample(n=min(SAMPLE_SIZE, sum(len(df) for df in sampled_dfs)), random_state=42)
    print(f"Sampled {len(sampled_tx):,} transactions ({DATA_FRACTION*100:.0f}% of full dataset)")
    
    return sampled_tx

def load_address_data():
    """Load address/wallet data with risk scores."""
    print("Loading address data...")
    
    addr_df = pd.read_parquet('c:/amttp/processed/eth_addresses_labeled.parquet')
    print(f"Total addresses: {len(addr_df):,}")
    
    return addr_df

def prepare_memgraph_data(tx_df, addr_df):
    """Prepare data for Memgraph graph database."""
    print("Preparing Memgraph data...")
    
    # Get unique addresses from transactions
    from_addresses = set(tx_df['from_address'].unique())
    to_addresses = set(tx_df['to_address'].unique())
    all_addresses = from_addresses | to_addresses
    
    print(f"Unique addresses in sample: {len(all_addresses):,}")
    
    # Filter address data for our sample
    sample_addresses = addr_df[addr_df['address'].isin(all_addresses)].copy()
    print(f"Addresses with full data: {len(sample_addresses):,}")
    
    return sample_addresses, tx_df

def load_to_memgraph(addresses_df, tx_df):
    """Load data into Memgraph via Cypher queries."""
    print("Loading data to Memgraph...")
    
    try:
        from neo4j import GraphDatabase
        
        driver = GraphDatabase.driver(
            f"bolt://{MEMGRAPH_HOST}:{MEMGRAPH_PORT}",
            auth=("", "")  # Memgraph default no auth
        )
        
        with driver.session() as session:
            # Clear existing data
            print("Clearing existing graph data...")
            session.run("MATCH (n) DETACH DELETE n")
            
            # Create indexes
            print("Creating indexes...")
            session.run("CREATE INDEX ON :Wallet(address)")
            session.run("CREATE INDEX ON :Transaction(hash)")
            
            # Load wallets in batches
            print("Loading wallet nodes...")
            wallets = addresses_df.to_dict('records')
            batch_size = 500
            
            for i in range(0, len(wallets), batch_size):
                batch = wallets[i:i+batch_size]
                session.run("""
                    UNWIND $wallets AS w
                    CREATE (wallet:Wallet {
                        address: w.address,
                        balance: COALESCE(w.balance, 0),
                        total_sent: COALESCE(w.total_sent, 0),
                        total_received: COALESCE(w.total_received, 0),
                        total_transactions: COALESCE(w.total_transactions, 0),
                        hybrid_score: COALESCE(w.hybrid_score, 0),
                        risk_level: COALESCE(w.risk_level, 'low'),
                        risk_class: COALESCE(w.risk_class, 'low'),
                        fraud: COALESCE(w.fraud, false),
                        sophisticated_score: COALESCE(w.sophisticated_score, 0),
                        pattern_count: COALESCE(w.pattern_count, 0),
                        unique_counterparties: COALESCE(w.unique_counterparties, 0)
                    })
                """, wallets=batch)
                
                if (i + batch_size) % 2000 == 0:
                    print(f"  Loaded {min(i + batch_size, len(wallets)):,} wallets...")
            
            print(f"Loaded {len(wallets):,} wallet nodes")
            
            # Load transactions as edges
            print("Loading transaction edges...")
            transactions = tx_df.to_dict('records')
            
            for i in range(0, len(transactions), batch_size):
                batch = transactions[i:i+batch_size]
                # Convert timestamps and clean data
                for tx in batch:
                    if pd.isna(tx.get('block_timestamp')):
                        tx['block_timestamp'] = datetime.now().isoformat()
                    elif isinstance(tx.get('block_timestamp'), pd.Timestamp):
                        tx['block_timestamp'] = tx['block_timestamp'].isoformat()
                    
                    # Handle NaN values
                    for key in tx:
                        if pd.isna(tx[key]):
                            tx[key] = 0 if isinstance(tx[key], (int, float)) else ""
                
                session.run("""
                    UNWIND $transactions AS tx
                    MATCH (from:Wallet {address: tx.from_address})
                    MATCH (to:Wallet {address: tx.to_address})
                    CREATE (from)-[:SENT {
                        hash: tx.tx_hash,
                        value_eth: tx.value_eth,
                        gas_used: tx.gas_used,
                        block_number: tx.block_number,
                        timestamp: tx.block_timestamp,
                        risk_class: tx.risk_class,
                        max_hybrid_score: tx.max_hybrid_score
                    }]->(to)
                """, transactions=batch)
                
                if (i + batch_size) % 5000 == 0:
                    print(f"  Loaded {min(i + batch_size, len(transactions)):,} transactions...")
            
            print(f"Loaded {len(transactions):,} transaction edges")
            
            # Create summary statistics
            result = session.run("""
                MATCH (w:Wallet)
                RETURN count(w) as wallets,
                       sum(CASE WHEN w.fraud = true THEN 1 ELSE 0 END) as fraud_wallets,
                       avg(w.hybrid_score) as avg_risk_score
            """)
            stats = result.single()
            print(f"Memgraph stats: {stats['wallets']} wallets, {stats['fraud_wallets']} fraud, avg risk: {stats['avg_risk_score']:.3f}")
            
        driver.close()
        print("✅ Memgraph data loaded successfully")
        return True
        
    except ImportError:
        print("⚠️ neo4j driver not installed, skipping Memgraph load")
        return False
    except Exception as e:
        print(f"❌ Memgraph error: {e}")
        return False

def load_to_risk_engine(addresses_df, tx_df):
    """Load risk scores to the Risk Engine API."""
    print("Loading data to Risk Engine...")
    
    try:
        # Check if risk engine is running
        health = requests.get(f"{RISK_ENGINE_URL}/health", timeout=5)
        if health.status_code != 200:
            print("⚠️ Risk Engine not healthy, skipping")
            return False
        
        # Prepare risk data
        risk_data = []
        for _, row in addresses_df.iterrows():
            risk_data.append({
                "address": row['address'],
                "risk_score": float(row.get('hybrid_score', 0)) if not pd.isna(row.get('hybrid_score')) else 0,
                "risk_level": row.get('risk_level', 'low') if not pd.isna(row.get('risk_level')) else 'low',
                "risk_class": row.get('risk_class', 'low') if not pd.isna(row.get('risk_class')) else 'low',
                "is_fraud": bool(row.get('fraud', False)),
                "pattern_count": int(row.get('pattern_count', 0)) if not pd.isna(row.get('pattern_count')) else 0,
                "sophisticated_score": float(row.get('sophisticated_score', 0)) if not pd.isna(row.get('sophisticated_score')) else 0,
                "total_transactions": int(row.get('total_transactions', 0)) if not pd.isna(row.get('total_transactions')) else 0,
                "unique_counterparties": int(row.get('unique_counterparties', 0)) if not pd.isna(row.get('unique_counterparties')) else 0
            })
        
        # Try multiple API endpoints
        batch_endpoints = [
            "/api/risk/batch",
            "/api/v1/risk/batch", 
            "/risk/batch",
            "/batch",
            "/api/addresses/batch",
        ]
        
        batch_size = 1000
        success_count = 0
        working_endpoint = None
        
        for i in range(0, len(risk_data), batch_size):
            batch = risk_data[i:i+batch_size]
            
            if working_endpoint:
                # Use the endpoint that worked before
                try:
                    response = requests.post(
                        f"{RISK_ENGINE_URL}{working_endpoint}",
                        json={"addresses": batch},
                        timeout=30
                    )
                    if response.status_code in [200, 201]:
                        success_count += 1
                except Exception:
                    pass
            else:
                # Try each endpoint until one works
                for endpoint in batch_endpoints:
                    try:
                        response = requests.post(
                            f"{RISK_ENGINE_URL}{endpoint}",
                            json={"addresses": batch},
                            timeout=30
                        )
                        if response.status_code in [200, 201]:
                            working_endpoint = endpoint
                            success_count += 1
                            print(f"  Found working endpoint: {endpoint}")
                            break
                    except Exception:
                        continue
        
        if success_count > 0:
            print(f"✅ Loaded {len(risk_data):,} address risk scores to Risk Engine ({success_count} batches)")
        else:
            print(f"⚠️ Risk Engine API endpoints not available, data prepared but not uploaded")
            print(f"   Tried endpoints: {batch_endpoints}")
        
        return success_count > 0
        
    except requests.exceptions.ConnectionError:
        print("⚠️ Risk Engine not available, skipping")
        return False
    except Exception as e:
        print(f"❌ Risk Engine error: {e}")
        return False
    except Exception as e:
        print(f"❌ Risk Engine error: {e}")
        return False

def generate_frontend_mock_data(addresses_df, tx_df):
    """Generate JSON mock data for frontend visualizations."""
    print("Generating frontend mock data...")
    
    # Create output directories
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    FLUTTER_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    # 1. Graph Explorer Data (wallet relationships)
    print(f"  Creating graph explorer data (limit: {GRAPH_NODE_LIMIT} nodes, {GRAPH_EDGE_LIMIT} edges)...")
    
    # Get top N most connected wallets for graph visualization
    from_counts = tx_df['from_address'].value_counts()
    to_counts = tx_df['to_address'].value_counts()
    all_counts = from_counts.add(to_counts, fill_value=0).sort_values(ascending=False)
    top_wallets = set(all_counts.head(GRAPH_NODE_LIMIT).index)
    
    # Filter transactions to top wallets
    graph_tx = tx_df[
        (tx_df['from_address'].isin(top_wallets)) & 
        (tx_df['to_address'].isin(top_wallets))
    ].head(GRAPH_EDGE_LIMIT)
    
    # Create nodes
    graph_wallets = set(graph_tx['from_address']) | set(graph_tx['to_address'])
    wallet_lookup = addresses_df.set_index('address')
    
    def infer_node_type(row):
        """Infer node type based on transaction patterns and risk."""
        tx_count = int(row.get('total_transactions', 0)) if not pd.isna(row.get('total_transactions')) else 0
        counterparties = int(row.get('unique_counterparties', 0)) if not pd.isna(row.get('unique_counterparties')) else 0
        is_flagged = bool(row.get('fraud', False))
        risk_score = float(row.get('hybrid_score', 0)) if not pd.isna(row.get('hybrid_score')) else 0
        risk_level = str(row.get('risk_level', 'low')).upper() if not pd.isna(row.get('risk_level')) else 'LOW'
        
        # Flagged takes priority
        if is_flagged or risk_level in ['HIGH', 'CRITICAL'] or risk_score > 70:
            return 'flagged'
        # Exchange: very high tx count + many counterparties
        if tx_count >= 5000 and counterparties >= 1000:
            return 'exchange'
        # Contract: high tx count but few counterparties (automated)
        if tx_count >= 500 and counterparties <= 20:
            return 'contract'
        # Default to wallet
        return 'wallet'
    
    nodes = []
    for addr in graph_wallets:
        if addr in wallet_lookup.index:
            row = wallet_lookup.loc[addr]
            risk_score = float(row.get('hybrid_score', 0)) if not pd.isna(row.get('hybrid_score')) else 0
            risk_level = row.get('risk_level', 'low') if not pd.isna(row.get('risk_level')) else 'low'
            node_type = infer_node_type(row)
            
            nodes.append({
                "id": addr,
                "address": addr,
                "label": f"{addr[:8]}...{addr[-6:]}",
                "nodeType": node_type,
                "riskScore": risk_score,
                "riskLevel": risk_level.upper() if isinstance(risk_level, str) else 'LOW',
                "isFlagged": bool(row.get('fraud', False)),
                "transactionCount": int(row.get('total_transactions', 0)) if not pd.isna(row.get('total_transactions')) else 0,
                "balance": float(row.get('balance', 0)) if not pd.isna(row.get('balance')) else 0,
                "uniqueCounterparties": int(row.get('unique_counterparties', 0)) if not pd.isna(row.get('unique_counterparties')) else 0
            })
        else:
            nodes.append({
                "id": addr,
                "address": addr,
                "label": f"{addr[:8]}...{addr[-6:]}",
                "nodeType": "wallet",
                "riskScore": 0,
                "riskLevel": "UNKNOWN",
                "isFlagged": False,
                "transactionCount": 0,
                "balance": 0,
                "uniqueCounterparties": 0
            })
    
    # Create edges
    edges = []
    for _, tx in graph_tx.iterrows():
        edges.append({
            "id": tx['tx_hash'],
            "source": tx['from_address'],
            "target": tx['to_address'],
            "value": float(tx['value_eth']) if not pd.isna(tx['value_eth']) else 0,
            "riskScore": float(tx['max_hybrid_score']) if not pd.isna(tx['max_hybrid_score']) else 0,
            "riskClass": tx['risk_class'] if not pd.isna(tx['risk_class']) else 'low'
        })
    
    graph_data = {"nodes": nodes, "edges": edges}
    
    with open(OUTPUT_DIR / "graphExplorerData.json", 'w') as f:
        json.dump(graph_data, f, indent=2)
    with open(FLUTTER_OUTPUT_DIR / "graph_explorer_data.json", 'w') as f:
        json.dump(graph_data, f, indent=2)
    
    print(f"    Graph: {len(nodes)} nodes, {len(edges)} edges")
    
    # 2. Risk Distribution Data
    print("  Creating risk distribution data...")
    
    # Histogram of risk scores
    risk_scores = addresses_df['hybrid_score'].dropna()
    hist, bin_edges = np.histogram(risk_scores, bins=50, range=(0, 1))
    
    risk_distribution = {
        "histogram": [
            {"bin": f"{bin_edges[i]:.2f}-{bin_edges[i+1]:.2f}", "count": int(hist[i]), "binStart": float(bin_edges[i]), "binEnd": float(bin_edges[i+1])}
            for i in range(len(hist))
        ],
        "stats": {
            "mean": float(risk_scores.mean()),
            "median": float(risk_scores.median()),
            "std": float(risk_scores.std()),
            "min": float(risk_scores.min()),
            "max": float(risk_scores.max()),
            "total": len(risk_scores)
        },
        "riskLevelCounts": addresses_df['risk_level'].value_counts().to_dict()
    }
    
    with open(OUTPUT_DIR / "riskDistributionData.json", 'w') as f:
        json.dump(risk_distribution, f, indent=2)
    with open(FLUTTER_OUTPUT_DIR / "risk_distribution_data.json", 'w') as f:
        json.dump(risk_distribution, f, indent=2)
    
    # 3. Time Series Data (transaction volume over time)
    print("  Creating time series data...")
    
    # Generate realistic time series based on transaction patterns
    # Use block numbers as proxy for time
    tx_df_sorted = tx_df.sort_values('block_number')
    
    # Group by time intervals (simulate hourly data for last 30 days)
    base_time = datetime.now() - timedelta(days=30)
    time_series = []
    
    hours = 24 * 30  # 30 days of hourly data
    tx_per_hour = len(tx_df) // hours
    
    for h in range(hours):
        hour_time = base_time + timedelta(hours=h)
        start_idx = h * tx_per_hour
        end_idx = min((h + 1) * tx_per_hour, len(tx_df_sorted))
        
        hour_txs = tx_df_sorted.iloc[start_idx:end_idx]
        
        if len(hour_txs) > 0:
            time_series.append({
                "timestamp": hour_time.isoformat(),
                "hour": hour_time.strftime("%Y-%m-%d %H:00"),
                "transactionCount": len(hour_txs),
                "totalVolume": float(hour_txs['value_eth'].sum()),
                "avgRiskScore": float(hour_txs['max_hybrid_score'].mean()) if not hour_txs['max_hybrid_score'].isna().all() else 0,
                "highRiskCount": len(hour_txs[hour_txs['risk_class'].isin(['high', 'critical'])]),
                "flaggedCount": len(hour_txs[hour_txs['fraud'] == True])
            })
    
    with open(OUTPUT_DIR / "timeSeriesData.json", 'w') as f:
        json.dump(time_series, f, indent=2)
    with open(FLUTTER_OUTPUT_DIR / "time_series_data.json", 'w') as f:
        json.dump(time_series, f, indent=2)
    
    # 4. Velocity Heatmap Data (hour x day patterns)
    print("  Creating velocity heatmap data...")
    
    # Generate realistic velocity patterns (higher activity during business hours)
    velocity_data = []
    days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
    
    for day_idx, day in enumerate(days):
        for hour in range(24):
            # Base activity with business hour boost
            if 9 <= hour <= 17 and day_idx < 5:  # Business hours, weekdays
                base_activity = random.uniform(0.6, 1.0)
            elif 6 <= hour <= 22:  # Daytime
                base_activity = random.uniform(0.3, 0.7)
            else:  # Night
                base_activity = random.uniform(0.05, 0.3)
            
            # Add some randomness
            activity = base_activity * random.uniform(0.8, 1.2)
            activity = min(1.0, max(0, activity))
            
            velocity_data.append({
                "day": day,
                "dayIndex": day_idx,
                "hour": hour,
                "velocity": activity,
                "transactionCount": int(activity * 1000),
                "avgValue": activity * 5.5
            })
    
    with open(OUTPUT_DIR / "velocityHeatmapData.json", 'w') as f:
        json.dump(velocity_data, f, indent=2)
    with open(FLUTTER_OUTPUT_DIR / "velocity_heatmap_data.json", 'w') as f:
        json.dump(velocity_data, f, indent=2)
    
    # 5. Flagged Queue Data
    print("  Creating flagged queue data...")
    
    flagged_limit = int(100 * DATA_FRACTION)  # 40 flagged items
    flagged_wallets = addresses_df[addresses_df['fraud'] == True].head(flagged_limit)
    flagged_queue = []
    
    for idx, (_, wallet) in enumerate(flagged_wallets.iterrows()):
        flagged_queue.append({
            "id": f"FLAG-{idx+1:04d}",
            "address": wallet['address'],
            "riskScore": float(wallet.get('hybrid_score', 0)) if not pd.isna(wallet.get('hybrid_score')) else 0,
            "riskLevel": wallet.get('risk_level', 'high') if not pd.isna(wallet.get('risk_level')) else 'high',
            "reason": random.choice([
                "Multiple rapid transactions",
                "Unusual transaction pattern",
                "Connection to flagged wallet",
                "High-value anomaly detected",
                "Velocity threshold exceeded",
                "Suspicious counterparty network"
            ]),
            "timestamp": (datetime.now() - timedelta(hours=random.randint(1, 72))).isoformat(),
            "status": random.choice(["pending", "under_review", "escalated"]),
            "patternCount": int(wallet.get('pattern_count', 0)) if not pd.isna(wallet.get('pattern_count')) else 0,
            "totalTransactions": int(wallet.get('total_transactions', 0)) if not pd.isna(wallet.get('total_transactions')) else 0,
            "uniqueCounterparties": int(wallet.get('unique_counterparties', 0)) if not pd.isna(wallet.get('unique_counterparties')) else 0
        })
    
    with open(OUTPUT_DIR / "flaggedQueueData.json", 'w') as f:
        json.dump(flagged_queue, f, indent=2)
    with open(FLUTTER_OUTPUT_DIR / "flagged_queue_data.json", 'w') as f:
        json.dump(flagged_queue, f, indent=2)
    
    # 6. Sankey Flow Data (money flow visualization)
    print("  Creating sankey flow data...")
    
    # Map risk class numbers to categories
    risk_class_map = {0: 'low', 1: 'low', 2: 'medium', 3: 'high', 4: 'critical'}
    
    # Get sender and receiver risk from addresses
    tx_with_risk = tx_df.copy()
    
    # Create risk categories based on available columns
    if 'sender_risk_class' in tx_with_risk.columns:
        tx_with_risk['sender_risk_cat'] = tx_with_risk['sender_risk_class'].map(
            lambda x: risk_class_map.get(x, 'unknown') if pd.notna(x) else 'unknown'
        )
    else:
        tx_with_risk['sender_risk_cat'] = 'unknown'
        
    if 'receiver_risk_class' in tx_with_risk.columns:
        tx_with_risk['receiver_risk_cat'] = tx_with_risk['receiver_risk_class'].map(
            lambda x: risk_class_map.get(x, 'unknown') if pd.notna(x) else 'unknown'
        )
    else:
        tx_with_risk['receiver_risk_cat'] = 'unknown'
    
    flow_agg = tx_with_risk.groupby(['sender_risk_cat', 'receiver_risk_cat']).agg({
        'value_eth': 'sum',
        'tx_hash': 'count'
    }).reset_index()
    
    flow_agg.columns = ['source', 'target', 'value', 'count']
    
    # Create sankey nodes and links
    risk_categories = ['low', 'medium', 'high', 'critical', 'unknown']
    sankey_nodes = [
        {"id": "low", "label": "Low Risk", "type": "source", "riskLevel": "low"},
        {"id": "medium", "label": "Medium Risk", "type": "intermediate", "riskLevel": "medium"},
        {"id": "high", "label": "High Risk", "type": "intermediate", "riskLevel": "high"},
        {"id": "critical", "label": "Critical Risk", "type": "sink", "riskLevel": "critical"},
        {"id": "unknown", "label": "Unknown", "type": "intermediate", "riskLevel": "medium"},
    ]
    
    sankey_links = []
    for _, row in flow_agg.iterrows():
        if row['source'] in risk_categories and row['target'] in risk_categories and row['value'] > 0:
            sankey_links.append({
                "source": row['source'],
                "target": row['target'],
                "value": round(float(row['value']), 2),
                "count": int(row['count']),
                "isAnomaly": row['source'] == 'critical' or row['target'] == 'critical'
            })
    
    # If no links, create sample based on transaction data
    if not sankey_links:
        print("    No risk class data, creating sample links...")
        total_value = float(tx_df['value_eth'].sum())
        tx_count = len(tx_df)
        sankey_links = [
            {"source": "low", "target": "low", "value": round(total_value * 0.4, 2), "count": int(tx_count * 0.4)},
            {"source": "low", "target": "medium", "value": round(total_value * 0.2, 2), "count": int(tx_count * 0.2)},
            {"source": "medium", "target": "medium", "value": round(total_value * 0.15, 2), "count": int(tx_count * 0.15)},
            {"source": "medium", "target": "high", "value": round(total_value * 0.1, 2), "count": int(tx_count * 0.1)},
            {"source": "high", "target": "high", "value": round(total_value * 0.08, 2), "count": int(tx_count * 0.08)},
            {"source": "high", "target": "critical", "value": round(total_value * 0.05, 2), "count": int(tx_count * 0.05), "isAnomaly": True},
            {"source": "critical", "target": "unknown", "value": round(total_value * 0.02, 2), "count": int(tx_count * 0.02), "isAnomaly": True},
        ]
    
    sankey_data = {"nodes": sankey_nodes, "links": sankey_links}
    print(f"    Sankey: {len(sankey_nodes)} nodes, {len(sankey_links)} links")
    
    with open(OUTPUT_DIR / "sankeyFlowData.json", 'w') as f:
        json.dump(sankey_data, f, indent=2)
    with open(FLUTTER_OUTPUT_DIR / "sankey_flow_data.json", 'w') as f:
        json.dump(sankey_data, f, indent=2)
    
    # 7. Dashboard Stats
    print("  Creating dashboard stats...")
    
    stats = {
        "totalWallets": len(addresses_df),
        "totalTransactions": len(tx_df),
        "flaggedWallets": int(addresses_df['fraud'].sum()),
        "highRiskWallets": len(addresses_df[addresses_df['risk_class'].isin(['high', 'critical'])]),
        "totalVolume": float(tx_df['value_eth'].sum()),
        "avgRiskScore": float(addresses_df['hybrid_score'].mean()),
        "riskDistribution": addresses_df['risk_class'].value_counts().to_dict(),
        "last24hTransactions": len(tx_df) // 30,  # Approximate
        "last24hVolume": float(tx_df['value_eth'].sum()) / 30,
        "last24hFlagged": int(addresses_df['fraud'].sum()) // 30
    }
    
    with open(OUTPUT_DIR / "dashboardStats.json", 'w') as f:
        json.dump(stats, f, indent=2)
    with open(FLUTTER_OUTPUT_DIR / "dashboard_stats.json", 'w') as f:
        json.dump(stats, f, indent=2)
    
    print(f"✅ Generated mock data files in:")
    print(f"   - {OUTPUT_DIR}")
    print(f"   - {FLUTTER_OUTPUT_DIR}")
    
    return True

def load_to_mongodb(addresses_df, tx_df):
    """Load data to MongoDB for the backend APIs."""
    print("Loading data to MongoDB...")
    
    try:
        from pymongo import MongoClient
        
        # Try connection without auth first (default), then with auth
        connection_strings = [
            f"mongodb://{MONGO_HOST}:{MONGO_PORT}",  # No auth (default)
            f"mongodb://admin:admin@{MONGO_HOST}:{MONGO_PORT}",  # Common default
            f"mongodb://root:root@{MONGO_HOST}:{MONGO_PORT}",  # Another common default
        ]
        
        client = None
        for conn_str in connection_strings:
            try:
                client = MongoClient(conn_str, serverSelectionTimeoutMS=3000)
                # Test connection
                client.admin.command('ping')
                print(f"  Connected to MongoDB")
                break
            except Exception:
                continue
        
        if client is None:
            print("⚠️ Could not connect to MongoDB with any credentials, skipping")
            return False
        
        db = client['amttp']
        
        # Clear existing collections (handle auth errors gracefully)
        try:
            db.wallets.drop()
            db.transactions.drop()
            db.risk_scores.drop()
        except Exception as e:
            print(f"  ⚠️ Could not drop collections (may not exist): {e}")
        
        # Load wallets
        print("  Loading wallets...")
        wallets = addresses_df.to_dict('records')
        
        # Clean NaN values
        for wallet in wallets:
            for key in list(wallet.keys()):
                if pd.isna(wallet[key]):
                    wallet[key] = None
        
        if wallets:
            db.wallets.insert_many(wallets)
            try:
                db.wallets.create_index("address", unique=True)
            except Exception:
                pass  # Index may already exist
        
        # Load transactions (sample for performance)
        print("  Loading transactions...")
        tx_sample = tx_df.sample(n=min(int(10000 * DATA_FRACTION), len(tx_df)), random_state=42)
        transactions = tx_sample.to_dict('records')
        
        # Clean NaN values and convert timestamps
        for tx in transactions:
            for key in list(tx.keys()):
                if pd.isna(tx[key]):
                    tx[key] = None
                elif isinstance(tx[key], pd.Timestamp):
                    tx[key] = tx[key].isoformat()
        
        if transactions:
            db.transactions.insert_many(transactions)
            try:
                db.transactions.create_index("tx_hash", unique=True)
                db.transactions.create_index("from_address")
                db.transactions.create_index("to_address")
            except Exception:
                pass
        
        # Create risk_scores collection for quick lookups
        print("  Creating risk scores collection...")
        risk_scores = []
        for _, row in addresses_df.iterrows():
            risk_scores.append({
                "address": row['address'],
                "hybrid_score": float(row['hybrid_score']) if not pd.isna(row.get('hybrid_score')) else 0,
                "risk_level": row.get('risk_level', 'low') if not pd.isna(row.get('risk_level')) else 'low',
                "risk_class": row.get('risk_class', 'low') if not pd.isna(row.get('risk_class')) else 'low',
                "fraud": bool(row.get('fraud', False)),
                "updated_at": datetime.now().isoformat()
            })
        
        if risk_scores:
            db.risk_scores.insert_many(risk_scores)
            try:
                db.risk_scores.create_index("address", unique=True)
            except Exception:
                pass
        
        print(f"✅ MongoDB loaded: {len(wallets)} wallets, {len(transactions)} transactions")
        
        client.close()
        return True
        
    except ImportError:
        print("⚠️ pymongo not installed, skipping MongoDB load")
        return False
    except Exception as e:
        print(f"❌ MongoDB error: {e}")
        return False

def main():
    """Main execution function."""
    print("=" * 60)
    print("AMTTP Data Loading Script")
    print("=" * 60)
    print()
    
    # Load source data
    tx_df = load_transaction_data()
    addr_df = load_address_data()
    
    # Prepare data
    sample_addresses, sample_tx = prepare_memgraph_data(tx_df, addr_df)
    
    print()
    print("Loading to services...")
    print("-" * 40)
    
    # Load to each service
    memgraph_ok = load_to_memgraph(sample_addresses, sample_tx)
    mongodb_ok = load_to_mongodb(sample_addresses, sample_tx)
    risk_engine_ok = load_to_risk_engine(sample_addresses, sample_tx)
    frontend_ok = generate_frontend_mock_data(sample_addresses, sample_tx)
    
    print()
    print("=" * 60)
    print("Summary")
    print("=" * 60)
    print(f"  Memgraph:    {'✅ Loaded' if memgraph_ok else '⚠️ Skipped'}")
    print(f"  MongoDB:     {'✅ Loaded' if mongodb_ok else '⚠️ Skipped'}")
    print(f"  Risk Engine: {'✅ Loaded' if risk_engine_ok else '⚠️ Skipped'}")
    print(f"  Frontend:    {'✅ Generated' if frontend_ok else '❌ Failed'}")
    print()
    print("Data sample statistics:")
    print(f"  Transactions: {len(sample_tx):,}")
    print(f"  Wallets:      {len(sample_addresses):,}")
    print(f"  Flagged:      {sample_addresses['fraud'].sum():,}")
    print(f"  High Risk:    {len(sample_addresses[sample_addresses['risk_class'].isin(['high', 'critical'])]):,}")
    print()

if __name__ == "__main__":
    main()
