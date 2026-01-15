"""
AMTTP ML Pipeline - Graph Feature Extractor

Extract graph-based features from Memgraph for fraud detection.
These features complement the tabular features for enhanced predictions.
"""
import logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
import numpy as np

from .service import MemgraphService, get_memgraph_service

logger = logging.getLogger(__name__)


@dataclass
class GraphFeatures:
    """Container for graph-based features."""
    address: str
    # Sanctions proximity
    sanctions_distance: int = 999  # Shortest path to sanctioned address (999 = no path)
    sanctions_neighbor_count: int = 0  # Direct neighbors tagged as sanctioned
    
    # Network centrality
    in_degree: int = 0  # Number of incoming transactions
    out_degree: int = 0  # Number of outgoing transactions
    total_degree: int = 0  # Total connections
    
    # Transaction patterns
    unique_counterparties: int = 0  # Number of unique addresses interacted with
    transaction_count: int = 0  # Total transactions
    total_value_sent: float = 0.0  # Total ETH sent
    total_value_received: float = 0.0  # Total ETH received
    
    # Community/clustering
    community_id: int = -1  # Community/cluster ID
    community_risk_score: float = 0.0  # Aggregate risk of community
    
    # Temporal
    first_seen_ts: int = 0  # First transaction timestamp
    last_seen_ts: int = 0  # Most recent transaction timestamp
    activity_span_days: float = 0.0  # Days between first and last activity
    
    # Suspicious patterns
    is_mixer_connected: bool = False  # Connected to known mixer
    is_exchange_connected: bool = False  # Connected to exchange
    loop_count: int = 0  # Number of transaction loops (A→B→A)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "address": self.address,
            "sanctions_distance": self.sanctions_distance,
            "sanctions_neighbor_count": self.sanctions_neighbor_count,
            "in_degree": self.in_degree,
            "out_degree": self.out_degree,
            "total_degree": self.total_degree,
            "unique_counterparties": self.unique_counterparties,
            "transaction_count": self.transaction_count,
            "total_value_sent": self.total_value_sent,
            "total_value_received": self.total_value_received,
            "community_id": self.community_id,
            "community_risk_score": self.community_risk_score,
            "first_seen_ts": self.first_seen_ts,
            "last_seen_ts": self.last_seen_ts,
            "activity_span_days": self.activity_span_days,
            "is_mixer_connected": self.is_mixer_connected,
            "is_exchange_connected": self.is_exchange_connected,
            "loop_count": self.loop_count,
        }
    
    def to_feature_array(self) -> np.ndarray:
        """Convert to numpy array for ML model input."""
        return np.array([
            self.sanctions_distance,
            self.sanctions_neighbor_count,
            self.in_degree,
            self.out_degree,
            self.total_degree,
            self.unique_counterparties,
            self.transaction_count,
            self.total_value_sent,
            self.total_value_received,
            self.community_id,
            self.community_risk_score,
            self.activity_span_days,
            int(self.is_mixer_connected),
            int(self.is_exchange_connected),
            self.loop_count,
        ], dtype=np.float32)


class GraphFeatureExtractor:
    """
    Extract graph-based features from Memgraph for addresses.
    
    Uses efficient batch queries to minimize round trips.
    """
    
    # Feature names for ML integration
    FEATURE_NAMES = [
        "graph_sanctions_distance",
        "graph_sanctions_neighbor_count", 
        "graph_in_degree",
        "graph_out_degree",
        "graph_total_degree",
        "graph_unique_counterparties",
        "graph_transaction_count",
        "graph_total_value_sent",
        "graph_total_value_received",
        "graph_community_id",
        "graph_community_risk_score",
        "graph_activity_span_days",
        "graph_is_mixer_connected",
        "graph_is_exchange_connected",
        "graph_loop_count",
    ]
    
    def __init__(self, service: Optional[MemgraphService] = None):
        """
        Initialize feature extractor.
        
        Args:
            service: Memgraph service instance. If None, uses singleton.
        """
        self.service = service or get_memgraph_service()
    
    def extract_features(self, address: str) -> GraphFeatures:
        """
        Extract all graph features for a single address.
        
        Args:
            address: Ethereum address (lowercase)
            
        Returns:
            GraphFeatures dataclass with all extracted features
        """
        address = address.lower()
        features = GraphFeatures(address=address)
        
        try:
            # Get basic degree and transaction info
            self._extract_degree_features(features)
            
            # Get sanctions proximity
            self._extract_sanctions_features(features)
            
            # Get community/clustering info
            self._extract_community_features(features)
            
            # Get temporal features
            self._extract_temporal_features(features)
            
            # Get suspicious pattern features
            self._extract_pattern_features(features)
            
        except Exception as e:
            logger.warning(f"Failed to extract some features for {address}: {e}")
        
        return features
    
    def extract_features_batch(self, addresses: List[str]) -> Dict[str, GraphFeatures]:
        """
        Extract features for multiple addresses efficiently.
        
        Args:
            addresses: List of Ethereum addresses
            
        Returns:
            Dict mapping address to GraphFeatures
        """
        if not addresses:
            return {}
        
        addresses = [a.lower() for a in addresses]
        results = {a: GraphFeatures(address=a) for a in addresses}
        
        try:
            # Batch query for degree features
            self._batch_extract_degrees(results)
            
            # Batch query for sanctions
            self._batch_extract_sanctions(results)
            
            # Batch query for communities
            self._batch_extract_communities(results)
            
        except Exception as e:
            logger.warning(f"Batch feature extraction error: {e}")
        
        return results
    
    def _extract_degree_features(self, features: GraphFeatures):
        """Extract degree and transaction count features."""
        query = """
        MATCH (a:Address {id: $addr})
        OPTIONAL MATCH (a)-[out:TRANSFER]->()
        OPTIONAL MATCH ()-[in:TRANSFER]->(a)
        WITH a, 
             count(DISTINCT out) AS out_deg,
             count(DISTINCT in) AS in_deg,
             collect(DISTINCT out) AS out_txs,
             collect(DISTINCT in) AS in_txs
        RETURN 
            out_deg,
            in_deg,
            out_deg + in_deg AS total_deg,
            size([x IN out_txs | endNode(x).id]) AS unique_sent_to,
            size([x IN in_txs | startNode(x).id]) AS unique_received_from,
            reduce(s = 0.0, t IN out_txs | s + coalesce(t.value, 0)) AS total_sent,
            reduce(s = 0.0, t IN in_txs | s + coalesce(t.value, 0)) AS total_received
        """
        
        try:
            result = self.service.execute(query, {"addr": features.address})
            if result:
                row = result[0]
                features.out_degree = int(row[0] or 0)
                features.in_degree = int(row[1] or 0)
                features.total_degree = int(row[2] or 0)
                features.unique_counterparties = int(row[3] or 0) + int(row[4] or 0)
                features.transaction_count = features.out_degree + features.in_degree
                features.total_value_sent = float(row[5] or 0)
                features.total_value_received = float(row[6] or 0)
        except Exception as e:
            logger.debug(f"Degree extraction failed: {e}")
    
    def _extract_sanctions_features(self, features: GraphFeatures):
        """Extract sanctions-related features."""
        query = """
        MATCH (a:Address {id: $addr})
        OPTIONAL MATCH (s:Address)-[:TAGGED_AS]->(:Tag {name: 'sanctioned'})
        OPTIONAL MATCH path = shortestPath((a)-[*..6]-(s))
        WHERE s IS NOT NULL
        WITH a, 
             CASE WHEN path IS NULL THEN 999 ELSE length(path) END AS dist,
             s
        RETURN min(dist) AS min_dist, count(DISTINCT s) AS sanctioned_neighbors
        """
        
        try:
            result = self.service.execute(query, {"addr": features.address})
            if result:
                row = result[0]
                features.sanctions_distance = int(row[0]) if row[0] is not None else 999
                # Count direct neighbors (distance 1)
                if features.sanctions_distance == 1:
                    features.sanctions_neighbor_count = int(row[1] or 0)
        except Exception as e:
            logger.debug(f"Sanctions extraction failed: {e}")
    
    def _extract_community_features(self, features: GraphFeatures):
        """Extract community/cluster features."""
        query = """
        MATCH (a:Address {id: $addr})
        OPTIONAL MATCH (a)-[:IN_CLUSTER]->(c:Cluster)
        RETURN coalesce(c.id, -1) AS community_id, coalesce(c.score, 0.0) AS risk_score
        """
        
        try:
            result = self.service.execute(query, {"addr": features.address})
            if result:
                row = result[0]
                features.community_id = int(row[0]) if row[0] is not None else -1
                features.community_risk_score = float(row[1] or 0)
        except Exception as e:
            logger.debug(f"Community extraction failed: {e}")
    
    def _extract_temporal_features(self, features: GraphFeatures):
        """Extract temporal features."""
        query = """
        MATCH (a:Address {id: $addr})
        OPTIONAL MATCH (a)-[t:TRANSFER]-()
        WITH min(coalesce(t.ts, 0)) AS first_ts, max(coalesce(t.ts, 0)) AS last_ts
        RETURN first_ts, last_ts
        """
        
        try:
            result = self.service.execute(query, {"addr": features.address})
            if result:
                row = result[0]
                features.first_seen_ts = int(row[0] or 0)
                features.last_seen_ts = int(row[1] or 0)
                if features.first_seen_ts > 0 and features.last_seen_ts > 0:
                    features.activity_span_days = (features.last_seen_ts - features.first_seen_ts) / 86400
        except Exception as e:
            logger.debug(f"Temporal extraction failed: {e}")
    
    def _extract_pattern_features(self, features: GraphFeatures):
        """Extract suspicious pattern features."""
        # Check for loops (A→B→A patterns)
        loop_query = """
        MATCH (a:Address {id: $addr})-[:TRANSFER]->(b)-[:TRANSFER]->(a)
        WHERE a <> b
        RETURN count(DISTINCT b) AS loop_count
        """
        
        try:
            result = self.service.execute(loop_query, {"addr": features.address})
            if result:
                features.loop_count = int(result[0][0] or 0)
        except Exception as e:
            logger.debug(f"Pattern extraction failed: {e}")
        
        # Check for mixer/exchange connections
        tag_query = """
        MATCH (a:Address {id: $addr})-[:TRANSFER*1..2]-(b:Address)-[:TAGGED_AS]->(t:Tag)
        WHERE t.name IN ['mixer', 'exchange']
        RETURN collect(DISTINCT t.name) AS tags
        """
        
        try:
            result = self.service.execute(tag_query, {"addr": features.address})
            if result and result[0][0]:
                tags = result[0][0]
                features.is_mixer_connected = 'mixer' in tags
                features.is_exchange_connected = 'exchange' in tags
        except Exception as e:
            logger.debug(f"Tag extraction failed: {e}")
    
    def _batch_extract_degrees(self, results: Dict[str, GraphFeatures]):
        """Batch extract degree features."""
        addresses = list(results.keys())
        query = """
        UNWIND $addrs AS addr
        MATCH (a:Address {id: addr})
        OPTIONAL MATCH (a)-[out:TRANSFER]->()
        OPTIONAL MATCH ()-[in:TRANSFER]->(a)
        RETURN addr, count(DISTINCT out) AS out_deg, count(DISTINCT in) AS in_deg
        """
        
        try:
            rows = self.service.execute(query, {"addrs": addresses})
            for row in rows:
                addr = row[0]
                if addr in results:
                    results[addr].out_degree = int(row[1] or 0)
                    results[addr].in_degree = int(row[2] or 0)
                    results[addr].total_degree = results[addr].out_degree + results[addr].in_degree
        except Exception as e:
            logger.warning(f"Batch degree extraction failed: {e}")
    
    def _batch_extract_sanctions(self, results: Dict[str, GraphFeatures]):
        """Batch extract sanctions proximity."""
        addresses = list(results.keys())
        query = """
        UNWIND $addrs AS addr
        MATCH (a:Address {id: addr})
        OPTIONAL MATCH (s:Address)-[:TAGGED_AS]->(:Tag {name: 'sanctioned'})
        OPTIONAL MATCH path = shortestPath((a)-[*..6]-(s))
        RETURN addr, CASE WHEN path IS NULL THEN 999 ELSE min(length(path)) END AS min_dist
        """
        
        try:
            rows = self.service.execute(query, {"addrs": addresses})
            for row in rows:
                addr = row[0]
                if addr in results:
                    results[addr].sanctions_distance = int(row[1]) if row[1] is not None else 999
        except Exception as e:
            logger.warning(f"Batch sanctions extraction failed: {e}")
    
    def _batch_extract_communities(self, results: Dict[str, GraphFeatures]):
        """Batch extract community features."""
        addresses = list(results.keys())
        query = """
        UNWIND $addrs AS addr
        MATCH (a:Address {id: addr})
        OPTIONAL MATCH (a)-[:IN_CLUSTER]->(c:Cluster)
        RETURN addr, coalesce(c.id, -1), coalesce(c.score, 0.0)
        """
        
        try:
            rows = self.service.execute(query, {"addrs": addresses})
            for row in rows:
                addr = row[0]
                if addr in results:
                    results[addr].community_id = int(row[1]) if row[1] is not None else -1
                    results[addr].community_risk_score = float(row[2] or 0)
        except Exception as e:
            logger.warning(f"Batch community extraction failed: {e}")
    
    def get_risk_score_from_graph(self, address: str) -> float:
        """
        Calculate a graph-based risk score for an address.
        
        Score is 0-1 where 1 is highest risk.
        """
        features = self.extract_features(address)
        
        # Weighted scoring
        score = 0.0
        
        # Sanctions proximity (most important)
        if features.sanctions_distance <= 1:
            score += 0.5  # Direct connection to sanctioned
        elif features.sanctions_distance <= 3:
            score += 0.3  # Close proximity
        elif features.sanctions_distance <= 6:
            score += 0.1  # Distant connection
        
        # Mixer connection
        if features.is_mixer_connected:
            score += 0.25
        
        # Loop patterns (potential layering)
        if features.loop_count > 5:
            score += 0.15
        elif features.loop_count > 0:
            score += 0.05
        
        # Community risk
        score += min(0.1, features.community_risk_score * 0.1)
        
        # Normalize
        return min(1.0, score)
