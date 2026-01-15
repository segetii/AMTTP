#!/usr/bin/env python3
"""
Initialize Memgraph with sample fraud detection data.
Creates addresses, transactions, and sanctions list nodes.
"""

from neo4j import GraphDatabase
import random
import hashlib


def generate_eth_address():
    """Generate a fake Ethereum address."""
    return "0x" + hashlib.sha256(str(random.random()).encode()).hexdigest()[:40]


def init_memgraph(bolt_uri: str = "bolt://localhost:7687"):
    """Initialize Memgraph with sample data for fraud detection."""
    
    driver = GraphDatabase.driver(bolt_uri)
    
    with driver.session() as session:
        # Clear existing data
        print("Clearing existing data...")
        session.run("MATCH (n) DETACH DELETE n")
        
        # Create indexes for better performance
        print("Creating indexes...")
        try:
            session.run("CREATE INDEX ON :Address(address)")
        except:
            pass  # Index may already exist
        
        try:
            session.run("CREATE INDEX ON :Sanctions(address)")
        except:
            pass
        
        # Generate addresses
        print("Creating addresses...")
        addresses = []
        
        # Create 100 normal addresses
        for i in range(100):
            addr = generate_eth_address()
            addresses.append(addr)
            session.run(
                """
                CREATE (a:Address {
                    address: $address,
                    type: 'normal',
                    created_at: datetime()
                })
                """,
                address=addr
            )
        
        # Create 10 known mixer addresses
        mixer_addresses = []
        for i in range(10):
            addr = generate_eth_address()
            mixer_addresses.append(addr)
            session.run(
                """
                CREATE (a:Address:Mixer {
                    address: $address,
                    type: 'mixer',
                    name: $name,
                    created_at: datetime()
                })
                """,
                address=addr,
                name=f"TornadoCash-{i}"
            )
        addresses.extend(mixer_addresses)
        
        # Create 5 sanctioned addresses (OFAC style)
        print("Creating sanctions list...")
        sanctions_addresses = []
        for i in range(5):
            addr = generate_eth_address()
            sanctions_addresses.append(addr)
            session.run(
                """
                CREATE (s:Sanctions:Address {
                    address: $address,
                    type: 'sanctioned',
                    list_source: 'OFAC',
                    date_added: date(),
                    reason: $reason
                })
                """,
                address=addr,
                reason=f"Sanctions evasion case #{i+1}"
            )
        addresses.extend(sanctions_addresses)
        
        # Create 5 known fraud addresses
        fraud_addresses = []
        for i in range(5):
            addr = generate_eth_address()
            fraud_addresses.append(addr)
            session.run(
                """
                CREATE (a:Address:Fraud {
                    address: $address,
                    type: 'fraud',
                    fraud_type: $fraud_type,
                    created_at: datetime()
                })
                """,
                address=addr,
                fraud_type=random.choice(['phishing', 'rug_pull', 'exploit', 'scam'])
            )
        addresses.extend(fraud_addresses)
        
        # Create transactions between addresses
        print("Creating transactions...")
        tx_count = 0
        
        # Normal transactions (between normal addresses)
        for _ in range(200):
            from_addr = random.choice(addresses[:100])
            to_addr = random.choice(addresses[:100])
            if from_addr != to_addr:
                amount = random.uniform(0.01, 10.0)
                hours_ago = random.randint(1, 720)
                session.run(
                    """
                    MATCH (from:Address {address: $from_addr})
                    MATCH (to:Address {address: $to_addr})
                    CREATE (from)-[:SENT {
                        amount: $amount,
                        hours_ago: $hours_ago,
                        tx_hash: $tx_hash
                    }]->(to)
                    """,
                    from_addr=from_addr,
                    to_addr=to_addr,
                    amount=amount,
                    hours_ago=hours_ago,
                    tx_hash="0x" + hashlib.sha256(str(random.random()).encode()).hexdigest()
                )
                tx_count += 1
        
        # Transactions involving mixers (suspicious pattern)
        for _ in range(30):
            from_addr = random.choice(addresses[:100])
            mixer_addr = random.choice(mixer_addresses)
            to_addr = random.choice(addresses[:100])
            amount = random.uniform(1.0, 50.0)
            hours_ago = random.randint(1, 168)
            
            # Send to mixer
            session.run(
                """
                MATCH (from:Address {address: $from_addr})
                MATCH (mixer:Mixer {address: $mixer_addr})
                CREATE (from)-[:SENT {
                    amount: $amount,
                    hours_ago: $hours_ago,
                    tx_hash: $tx_hash
                }]->(mixer)
                """,
                from_addr=from_addr,
                mixer_addr=mixer_addr,
                amount=amount,
                hours_ago=hours_ago,
                tx_hash="0x" + hashlib.sha256(str(random.random()).encode()).hexdigest()
            )
            
            # Receive from mixer (usually smaller amounts)
            session.run(
                """
                MATCH (mixer:Mixer {address: $mixer_addr})
                MATCH (to:Address {address: $to_addr})
                CREATE (mixer)-[:SENT {
                    amount: $amount,
                    hours_ago: $hours_ago,
                    tx_hash: $tx_hash
                }]->(to)
                """,
                mixer_addr=mixer_addr,
                to_addr=to_addr,
                amount=amount * 0.99,  # Mixer fee
                hours_ago=hours_ago,
                tx_hash="0x" + hashlib.sha256(str(random.random()).encode()).hexdigest()
            )
            tx_count += 2
        
        # Transactions involving sanctioned addresses (high risk)
        for _ in range(15):
            from_addr = random.choice(addresses[:100])
            sanctioned = random.choice(sanctions_addresses)
            amount = random.uniform(0.5, 20.0)
            hours_ago = random.randint(1, 720)
            
            session.run(
                """
                MATCH (from:Address {address: $from_addr})
                MATCH (sanctioned:Sanctions {address: $sanctioned_addr})
                CREATE (from)-[:SENT {
                    amount: $amount,
                    hours_ago: $hours_ago,
                    tx_hash: $tx_hash
                }]->(sanctioned)
                """,
                from_addr=from_addr,
                sanctioned_addr=sanctioned,
                amount=amount,
                hours_ago=hours_ago,
                tx_hash="0x" + hashlib.sha256(str(random.random()).encode()).hexdigest()
            )
            tx_count += 1
        
        # Transactions involving fraud addresses
        for _ in range(20):
            fraud_addr = random.choice(fraud_addresses)
            victim = random.choice(addresses[:100])
            amount = random.uniform(0.1, 5.0)
            hours_ago = random.randint(1, 360)
            
            session.run(
                """
                MATCH (victim:Address {address: $victim_addr})
                MATCH (fraud:Fraud {address: $fraud_addr})
                CREATE (victim)-[:SENT {
                    amount: $amount,
                    hours_ago: $hours_ago,
                    tx_hash: $tx_hash
                }]->(fraud)
                """,
                victim_addr=victim,
                fraud_addr=fraud_addr,
                amount=amount,
                hours_ago=hours_ago,
                tx_hash="0x" + hashlib.sha256(str(random.random()).encode()).hexdigest()
            )
            tx_count += 1
        
        # Create some circular transaction patterns (potential money laundering)
        print("Creating circular patterns...")
        for _ in range(5):
            cycle_addrs = random.sample(addresses[:100], k=random.randint(3, 5))
            amount = random.uniform(1.0, 10.0)
            hours_ago = random.randint(1, 48)
            
            for i in range(len(cycle_addrs)):
                from_addr = cycle_addrs[i]
                to_addr = cycle_addrs[(i + 1) % len(cycle_addrs)]
                
                session.run(
                    """
                    MATCH (from:Address {address: $from_addr})
                    MATCH (to:Address {address: $to_addr})
                    CREATE (from)-[:SENT {
                        amount: $amount,
                        hours_ago: $hours_ago,
                        tx_hash: $tx_hash
                    }]->(to)
                    """,
                    from_addr=from_addr,
                    to_addr=to_addr,
                    amount=amount * (0.98 ** i),  # Slight decrease each hop
                    hours_ago=hours_ago,
                    tx_hash="0x" + hashlib.sha256(str(random.random()).encode()).hexdigest()
                )
                tx_count += 1
        
        # Print summary
        print("\n" + "="*50)
        print("Graph Initialization Complete!")
        print("="*50)
        
        # Get counts
        result = session.run("MATCH (a:Address) RETURN count(a) as count")
        addr_count = result.single()['count']
        
        result = session.run("MATCH (m:Mixer) RETURN count(m) as count")
        mixer_count = result.single()['count']
        
        result = session.run("MATCH (s:Sanctions) RETURN count(s) as count")
        sanction_count = result.single()['count']
        
        result = session.run("MATCH (f:Fraud) RETURN count(f) as count")
        fraud_count = result.single()['count']
        
        result = session.run("MATCH ()-[r:SENT]->() RETURN count(r) as count")
        tx_count_db = result.single()['count']
        
        print(f"Addresses: {addr_count}")
        print(f"  - Normal: {addr_count - mixer_count - sanction_count - fraud_count}")
        print(f"  - Mixers: {mixer_count}")
        print(f"  - Sanctioned: {sanction_count}")
        print(f"  - Fraud: {fraud_count}")
        print(f"Transactions: {tx_count_db}")
        print("="*50)
        
        # Return some sample addresses for testing
        return {
            'normal': addresses[:5],
            'mixers': mixer_addresses[:2],
            'sanctioned': sanctions_addresses[:2],
            'fraud': fraud_addresses[:2]
        }
    
    driver.close()


if __name__ == "__main__":
    sample_addrs = init_memgraph()
    print("\nSample addresses for testing:")
    print(f"Normal: {sample_addrs['normal'][0]}")
    print(f"Mixer: {sample_addrs['mixers'][0]}")
    print(f"Sanctioned: {sample_addrs['sanctioned'][0]}")
    print(f"Fraud: {sample_addrs['fraud'][0]}")
