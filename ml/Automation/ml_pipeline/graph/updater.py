"""
AMTTP ML Pipeline - Graph Updater

Real-time updates to Memgraph when transactions are processed.
Maintains the transaction graph for continuous fraud detection.
"""
import logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from datetime import datetime

from .service import MemgraphService, get_memgraph_service

logger = logging.getLogger(__name__)


@dataclass
class Transaction:
    """Transaction data for graph updates."""
    hash: str
    from_address: str
    to_address: str
    value: float  # in ETH or wei
    timestamp: int  # unix timestamp
    block_number: int = 0
    gas_used: int = 0
    # Optional ML-derived fields
    risk_score: Optional[float] = None
    is_fraud: Optional[bool] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "hash": self.hash,
            "from": self.from_address.lower(),
            "to": self.to_address.lower(),
            "value": self.value,
            "ts": self.timestamp,
            "block": self.block_number,
            "gas": self.gas_used,
            "risk": self.risk_score,
            "fraud": self.is_fraud,
        }


class GraphUpdater:
    """
    Updates Memgraph with new transactions and address tags.
    
    Provides methods for:
    - Adding new transactions to the graph
    - Tagging addresses (sanctioned, mixer, exchange, etc.)
    - Updating risk scores
    - Running community detection
    """
    
    def __init__(self, service: Optional[MemgraphService] = None):
        """
        Initialize graph updater.
        
        Args:
            service: Memgraph service instance. If None, uses singleton.
        """
        self.service = service or get_memgraph_service()
    
    def add_transaction(self, txn: Transaction) -> bool:
        """
        Add a single transaction to the graph.
        
        Creates or updates:
        - Source address node
        - Destination address node
        - TRANSFER edge between them
        
        Args:
            txn: Transaction to add
            
        Returns:
            True if successful
        """
        query = """
        MERGE (a:Address {id: $from})
        MERGE (b:Address {id: $to})
        MERGE (a)-[t:TRANSFER {hash: $hash}]->(b)
        ON CREATE SET 
            t.value = $value,
            t.ts = $ts,
            t.block = $block,
            t.gas = $gas,
            t.risk = $risk,
            t.fraud = $fraud,
            t.created_at = timestamp()
        ON MATCH SET
            t.value = $value,
            t.risk = $risk,
            t.fraud = $fraud,
            t.updated_at = timestamp()
        RETURN t.hash
        """
        
        try:
            data = txn.to_dict()
            result = self.service.execute(query, data)
            logger.debug(f"Added transaction {txn.hash}")
            return len(result) > 0
        except Exception as e:
            logger.error(f"Failed to add transaction {txn.hash}: {e}")
            return False
    
    def add_transactions_batch(self, transactions: List[Transaction], batch_size: int = 1000) -> int:
        """
        Add multiple transactions efficiently.
        
        Args:
            transactions: List of transactions
            batch_size: Number of transactions per batch
            
        Returns:
            Number of transactions added
        """
        query = """
        UNWIND $rows AS r
        MERGE (a:Address {id: r.from})
        MERGE (b:Address {id: r.to})
        MERGE (a)-[t:TRANSFER {hash: r.hash}]->(b)
        ON CREATE SET 
            t.value = r.value,
            t.ts = r.ts,
            t.block = r.block,
            t.gas = r.gas,
            t.risk = r.risk,
            t.fraud = r.fraud
        """
        
        total = 0
        for i in range(0, len(transactions), batch_size):
            batch = transactions[i:i + batch_size]
            rows = [t.to_dict() for t in batch]
            
            try:
                self.service.execute(query, {"rows": rows})
                total += len(batch)
                
                if total % (batch_size * 10) == 0:
                    logger.info(f"Ingested {total}/{len(transactions)} transactions")
                    
            except Exception as e:
                logger.error(f"Batch ingestion failed at {i}: {e}")
        
        logger.info(f"Completed ingestion: {total} transactions")
        return total
    
    def tag_address(self, address: str, tag: str) -> bool:
        """
        Tag an address with a label.
        
        Common tags: sanctioned, mixer, exchange, contract, whale
        
        Args:
            address: Ethereum address
            tag: Tag name
            
        Returns:
            True if successful
        """
        query = """
        MERGE (a:Address {id: $addr})
        MERGE (t:Tag {name: $tag})
        MERGE (a)-[:TAGGED_AS]->(t)
        RETURN a.id
        """
        
        try:
            result = self.service.execute(query, {
                "addr": address.lower(),
                "tag": tag.lower(),
            })
            logger.debug(f"Tagged {address} as {tag}")
            return len(result) > 0
        except Exception as e:
            logger.error(f"Failed to tag {address}: {e}")
            return False
    
    def tag_addresses_batch(self, addresses: List[str], tag: str) -> int:
        """
        Tag multiple addresses with the same label.
        
        Args:
            addresses: List of addresses
            tag: Tag name
            
        Returns:
            Number of addresses tagged
        """
        query = """
        UNWIND $addrs AS addr
        MERGE (a:Address {id: addr})
        MERGE (t:Tag {name: $tag})
        MERGE (a)-[:TAGGED_AS]->(t)
        """
        
        try:
            addresses = [a.lower() for a in addresses]
            self.service.execute(query, {"addrs": addresses, "tag": tag.lower()})
            logger.info(f"Tagged {len(addresses)} addresses as {tag}")
            return len(addresses)
        except Exception as e:
            logger.error(f"Batch tagging failed: {e}")
            return 0
    
    def update_address_risk(self, address: str, risk_score: float) -> bool:
        """
        Update the risk score for an address.
        
        Args:
            address: Ethereum address
            risk_score: Risk score 0-1
            
        Returns:
            True if successful
        """
        query = """
        MERGE (a:Address {id: $addr})
        SET a.risk_score = $risk,
            a.risk_updated_at = timestamp()
        RETURN a.id
        """
        
        try:
            result = self.service.execute(query, {
                "addr": address.lower(),
                "risk": float(risk_score),
            })
            return len(result) > 0
        except Exception as e:
            logger.error(f"Failed to update risk for {address}: {e}")
            return False
    
    def mark_transaction_fraud(self, tx_hash: str, is_fraud: bool, confidence: float = 1.0) -> bool:
        """
        Mark a transaction as fraudulent or legitimate.
        
        Used for:
        - Ground truth labeling
        - Model predictions
        - Manual review results
        
        Args:
            tx_hash: Transaction hash
            is_fraud: Whether transaction is fraud
            confidence: Confidence of the label (0-1)
            
        Returns:
            True if successful
        """
        query = """
        MATCH ()-[t:TRANSFER {hash: $hash}]->()
        SET t.fraud = $fraud,
            t.fraud_confidence = $conf,
            t.labeled_at = timestamp()
        RETURN t.hash
        """
        
        try:
            result = self.service.execute(query, {
                "hash": tx_hash.lower(),
                "fraud": is_fraud,
                "conf": confidence,
            })
            return len(result) > 0
        except Exception as e:
            logger.error(f"Failed to mark transaction {tx_hash}: {e}")
            return False
    
    def assign_to_cluster(self, address: str, cluster_id: int, cluster_score: float = 0.0) -> bool:
        """
        Assign an address to a cluster/community.
        
        Args:
            address: Ethereum address
            cluster_id: Cluster identifier
            cluster_score: Risk score for the cluster
            
        Returns:
            True if successful
        """
        query = """
        MERGE (a:Address {id: $addr})
        MERGE (c:Cluster {id: $cluster_id})
        ON CREATE SET c.score = $score
        MERGE (a)-[:IN_CLUSTER]->(c)
        RETURN a.id
        """
        
        try:
            result = self.service.execute(query, {
                "addr": address.lower(),
                "cluster_id": cluster_id,
                "score": cluster_score,
            })
            return len(result) > 0
        except Exception as e:
            logger.error(f"Failed to assign {address} to cluster: {e}")
            return False
    
    def run_community_detection(self, algorithm: str = "louvain") -> Dict[str, Any]:
        """
        Run community detection on the graph.
        
        Note: Requires MAGE (Memgraph Advanced Graph Extensions)
        
        Args:
            algorithm: Algorithm to use (louvain, label_propagation)
            
        Returns:
            Statistics about detected communities
        """
        if algorithm == "louvain":
            # Louvain community detection via MAGE
            query = """
            CALL community_detection.louvain() YIELD node, community_id
            WITH node, community_id
            MERGE (c:Cluster {id: community_id})
            MERGE (node)-[:IN_CLUSTER]->(c)
            RETURN count(DISTINCT community_id) AS num_communities,
                   count(node) AS num_nodes
            """
        else:
            # Label propagation
            query = """
            CALL community_detection.label_propagation() YIELD node, community_id  
            WITH node, community_id
            MERGE (c:Cluster {id: community_id})
            MERGE (node)-[:IN_CLUSTER]->(c)
            RETURN count(DISTINCT community_id) AS num_communities,
                   count(node) AS num_nodes
            """
        
        try:
            result = self.service.execute(query)
            if result:
                return {
                    "communities": result[0][0],
                    "nodes_assigned": result[0][1],
                    "algorithm": algorithm,
                }
            return {"error": "No results"}
        except Exception as e:
            logger.error(f"Community detection failed: {e}")
            return {"error": str(e)}
    
    def create_indexes(self):
        """Create necessary indexes for performance."""
        indexes = [
            "CREATE INDEX ON :Address(id)",
            "CREATE INDEX ON :Tag(name)",
            "CREATE INDEX ON :Cluster(id)",
            "CREATE INDEX ON :TRANSFER(hash)",
            "CREATE INDEX ON :TRANSFER(ts)",
        ]
        
        for idx in indexes:
            try:
                self.service.execute(idx)
                logger.debug(f"Created index: {idx}")
            except Exception as e:
                # Index may already exist
                logger.debug(f"Index creation note: {e}")
    
    def clear_graph(self, confirm: bool = False):
        """
        Clear all data from the graph.
        
        Args:
            confirm: Must be True to actually clear
        """
        if not confirm:
            logger.warning("clear_graph called without confirmation - skipping")
            return
        
        try:
            self.service.execute("MATCH (n) DETACH DELETE n")
            logger.info("Graph cleared")
        except Exception as e:
            logger.error(f"Failed to clear graph: {e}")
