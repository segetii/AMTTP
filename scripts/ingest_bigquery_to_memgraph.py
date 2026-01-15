"""
Ingest BigQuery Ethereum transactions into local Memgraph.
"""
import pandas as pd
import mgclient
from datetime import datetime

# Configuration
PARQUET_PATH = r"C:\Users\Administrator\Downloads\eth_last_7_days.parquet"
MEMGRAPH_HOST = "localhost"
MEMGRAPH_PORT = 7687

# Known addresses for categorization
SANCTIONED_ADDRESSES = {
    '0x8589427373d6d84e98730d7795d8f6f8731fda16',  # Tornado Cash
    '0x722122df12d4e14e13ac3b6895a86e84145b6967',  # Tornado Cash Router
    '0xd90e2f925da726b50c4ed8d0fb90ad053324f31b',  # Tornado Cash 100 ETH
    '0x910cbd523d972eb0a6f4cae4618ad62622b39dbf',  # Tornado Cash 10 ETH
    '0xa160cdab225685da1d56aa342ad8841c3b53f291',  # Tornado Cash 1 ETH
    '0x12d66f87a04a9e220743712ce6d9bb1b5616b8fc',  # Tornado Cash 0.1 ETH
    '0x47ce0c6ed5b0ce3d3a51fdb1c52dc66a7c3c2936',  # Tornado Cash 10000 ETH
    '0x169ad27a470d064dede56a2d3ff727986b15d52b',  # Tornado Cash WstETH
    '0x0836222f2b2b24a3f36f98668ed8f0b38d1a872f',  # Tornado Cash cDAI
    '0x178169b423a011fff22b9e3f3abea13414ddd0f1',  # Tornado Cash
}

MIXER_ADDRESSES = {
    '0x0d0707963952f2fba59dd06f2b425ace40b492fe',  # ChipMixer
    '0x4bb96091ee9d802ed039c4d1a5f6216f90f81b01',  # Blender.io
    '0xba214c1c1928a32bffe790263e38b4af9bfcd659',  # Wasabi
    '0x1da5821544e25c636c1417ba96ade4cf6d2f9b5a',  # JoinMarket
}

EXCHANGE_ADDRESSES = {
    '0x28c6c06298d514db089934071355e5743bf21d60',  # Binance Hot Wallet
    '0xdfd5293d8e347dfe59e90efd55b2956a1343963d',  # Binance 2
    '0x21a31ee1afc51d94c2efccaa2092ad1028285549',  # Binance 3
    '0x47ac0fb4f2d84898e4d9e7b4dab3c24507a6d503',  # Binance 4
    '0x56eddb7aa87536c09ccc2793473599fd21a8b17f',  # Binance 5
    '0xf977814e90da44bfa03b6295a0616a897441acec',  # Binance 8
    '0x3f5ce5fbfe3e9af3971dd833d26ba9b5c936f0be',  # Binance Old
    '0xd551234ae421e3bcba99a0da6d736074f22192ff',  # Binance 4
    '0x71660c4005ba85c37ccec55d0c4493e66fe775d3',  # Coinbase 1
    '0xa9d1e08c7793af67e9d92fe308d5697fb81d3e43',  # Coinbase 2
    '0x503828976d22510aad0201ac7ec88293211d23da',  # Coinbase 3
    '0xddfabcdc4d8ffc6d5beaf154f18b778f892a0740',  # Coinbase 4
    '0x3cd751e6b0078be393132286c442345e5dc49699',  # Coinbase 5
    '0xb5d85cbf7cb3ee0d56b3bb207d5fc4b82f43f511',  # Coinbase 6
    '0x02466e547bfdab679fc49e96bbfc62b9747d997c',  # Coinbase 8
    '0x6cc5f688a315f3dc28a7781717a9a798a59fda7b',  # OKX 1
    '0x236f9f97e0e62388479bf9e5ba4889e46b0273c3',  # OKX 2
    '0xa7efae728d2936e78bda97dc267687568dd593f3',  # OKX 3
    '0x98ec059dc3adfbdd63429454aeb0c990fba4a128',  # Kraken
    '0x2910543af39aba0cd09dbb2d50200b3e800a63d2',  # Kraken 2
    '0x0a869d79a7052c7f1b55a8ebabbea3420f0d1e13',  # Kraken 3
    '0xe853c56864a2ebe4576a807d26fdc4a0ada51919',  # Kraken 4
    '0x267be1c1d684f78cb4f6a176c4911b741e4ffdc0',  # Kraken 6
}

DEFI_ADDRESSES = {
    '0x7a250d5630b4cf539739df2c5dacb4c659f2488d',  # Uniswap V2 Router
    '0x68b3465833fb72a70ecdf485e0e4c7bd8665fc45',  # Uniswap V3 Router
    '0xe592427a0aece92de3edee1f18e0157c05861564',  # Uniswap V3 Router 2
    '0xef1c6e67703c7bd7107eed8303fbe6ec2554bf6b',  # Uniswap Universal Router
    '0xd9e1ce17f2641f24ae83637ab66a2cca9c378b9f',  # SushiSwap Router
    '0x1111111254fb6c44bac0bed2854e76f90643097d',  # 1inch v4
    '0x1111111254eeb25477b68fb85ed929f73a960582',  # 1inch v5
    '0xdef1c0ded9bec7f1a1670819833240f027b25eff',  # 0x Exchange Proxy
    '0x881d40237659c251811cec9c364ef91dc08d300c',  # MetaMask Swap Router
    '0x3fc91a3afd70395cd496c647d5a6cc9d4b2b7fad',  # Uniswap Universal Router 2
    '0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2',  # WETH
    '0x7d1afa7b718fb893db30a3abc0cfc608aacfebb0',  # MATIC
    '0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48',  # USDC
    '0xdac17f958d2ee523a2206206994597c13d831ec7',  # USDT
}


def get_category(address):
    """Determine the category of an address."""
    if not address:
        return "unknown"
    addr_lower = address.lower()
    if addr_lower in SANCTIONED_ADDRESSES:
        return "sanctioned"
    if addr_lower in MIXER_ADDRESSES:
        return "mixer"
    if addr_lower in EXCHANGE_ADDRESSES:
        return "exchange"
    if addr_lower in DEFI_ADDRESSES:
        return "defi"
    return "unknown"


def main():
    print(f"Loading data from {PARQUET_PATH}...")
    df = pd.read_parquet(PARQUET_PATH)
    print(f"Loaded {len(df):,} transactions")
    print(f"Columns: {list(df.columns)}")
    
    # Connect to Memgraph
    print(f"\nConnecting to Memgraph at {MEMGRAPH_HOST}:{MEMGRAPH_PORT}...")
    conn = mgclient.connect(host=MEMGRAPH_HOST, port=MEMGRAPH_PORT)
    cursor = conn.cursor()
    print("Connected!")
    
    # Clear existing data
    print("\nClearing existing graph data...")
    cursor.execute("MATCH (n) DETACH DELETE n")
    conn.commit()
    
    # Create indexes
    print("Creating indexes...")
    try:
        cursor.execute("CREATE INDEX ON :Address(address)")
        conn.commit()
    except Exception as e:
        print(f"Index may already exist: {e}")
    
    # Ingest in batches
    print("\nIngesting transactions...")
    batch_size = 500
    total = len(df)
    ingested = 0
    category_counts = {"sanctioned": 0, "mixer": 0, "exchange": 0, "defi": 0, "unknown": 0}
    
    for i in range(0, total, batch_size):
        batch = df.iloc[i:i+batch_size]
        
        for _, row in batch.iterrows():
            from_addr = str(row['from_address']) if pd.notna(row['from_address']) else ""
            to_addr = str(row['to_address']) if pd.notna(row['to_address']) else ""
            
            if not from_addr or not to_addr:
                continue
                
            from_cat = get_category(from_addr)
            to_cat = get_category(to_addr)
            
            # Count categories
            if from_cat != "unknown":
                category_counts[from_cat] += 1
            if to_cat != "unknown":
                category_counts[to_cat] += 1
            
            query = """
            MERGE (from:Address {address: $from_addr})
            SET from.category = $from_cat
            MERGE (to:Address {address: $to_addr})
            SET to.category = $to_cat
            CREATE (from)-[:TRANSACTION {
                tx_hash: $tx_hash,
                value_eth: $value_eth,
                gas_used: $gas_used,
                block_number: $block_number
            }]->(to)
            """
            
            try:
                cursor.execute(query, {
                    'from_addr': from_addr,
                    'to_addr': to_addr,
                    'from_cat': from_cat,
                    'to_cat': to_cat,
                    'tx_hash': str(row['tx_hash']),
                    'value_eth': float(row['value_eth']) if pd.notna(row['value_eth']) else 0.0,
                    'gas_used': int(row['gas_used']) if pd.notna(row['gas_used']) else 0,
                    'block_number': int(row['block_number']) if pd.notna(row['block_number']) else 0
                })
            except Exception as e:
                print(f"Error ingesting row: {e}")
                continue
        
        conn.commit()
        ingested += len(batch)
        
        if (i + batch_size) % 1000 == 0 or i + batch_size >= total:
            print(f"  Ingested {ingested:,}/{total:,} transactions ({100*ingested/total:.1f}%)")
    
    # Final statistics
    print("\n" + "="*50)
    print("INGESTION COMPLETE")
    print("="*50)
    
    cursor.execute("MATCH (n:Address) RETURN count(n)")
    node_count = cursor.fetchone()[0]
    
    cursor.execute("MATCH ()-[r:TRANSACTION]->() RETURN count(r)")
    edge_count = cursor.fetchone()[0]
    
    print(f"\nGraph Statistics:")
    print(f"  Total Addresses: {node_count:,}")
    print(f"  Total Transactions: {edge_count:,}")
    
    print(f"\nCategory Interaction Counts:")
    for cat, count in category_counts.items():
        if count > 0:
            print(f"  {cat}: {count}")
    
    # Check for labeled addresses
    cursor.execute("""
        MATCH (n:Address) 
        WHERE n.category <> 'unknown' 
        RETURN n.category as category, count(n) as cnt 
        ORDER BY cnt DESC
    """)
    results = cursor.fetchall()
    
    if results:
        print(f"\nLabeled Address Nodes:")
        for row in results:
            print(f"  {row[0]}: {row[1]}")
    else:
        print("\nNo addresses matched known sanctioned/mixer/exchange patterns")
    
    conn.close()
    print("\nDone!")


if __name__ == "__main__":
    main()
