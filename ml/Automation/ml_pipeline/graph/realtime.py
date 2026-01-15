"""
AMTTP ML Pipeline - Real-time Graph Scoring

Provides real-time fraud scoring by:
1. Ingesting live transactions into Memgraph
2. Computing graph features on-the-fly
3. Combining ML + graph features for hybrid scoring
4. Streaming updates via WebSocket
"""
import asyncio
import logging
import time
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime
import json

from .service import MemgraphService, get_memgraph_service
from .features import GraphFeatureExtractor, GraphFeatures

logger = logging.getLogger(__name__)


@dataclass
class Transaction:
    """Incoming transaction to be scored."""
    tx_hash: str
    from_address: str
    to_address: str
    value: float  # in ETH
    timestamp: int  # Unix timestamp
    block_number: int = 0
    gas_price: float = 0.0
    gas_used: int = 0
    input_data: str = ""
    # Optional metadata
    token_address: Optional[str] = None
    token_value: Optional[float] = None
    method_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tx_hash": self.tx_hash,
            "from_address": self.from_address,
            "to_address": self.to_address,
            "value": self.value,
            "timestamp": self.timestamp,
            "block_number": self.block_number,
            "gas_price": self.gas_price,
            "gas_used": self.gas_used,
        }


@dataclass
class RealtimeScore:
    """Real-time scoring result."""
    tx_hash: str
    from_address: str
    to_address: str
    # Risk scores
    sender_risk_score: float
    receiver_risk_score: float
    transaction_risk_score: float
    # Graph-derived insights
    sender_graph_features: Dict[str, Any]
    receiver_graph_features: Dict[str, Any]
    # Relationship insights
    is_first_interaction: bool
    shared_neighbors: int
    path_to_sanctions: int  # Shortest path length (999 = no path)
    mixer_exposure: bool
    # Action recommendation
    action: str
    confidence: float
    processing_time_ms: float
    timestamp: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tx_hash": self.tx_hash,
            "from_address": self.from_address,
            "to_address": self.to_address,
            "risk_scores": {
                "sender": self.sender_risk_score,
                "receiver": self.receiver_risk_score,
                "transaction": self.transaction_risk_score,
            },
            "graph_insights": {
                "sender": self.sender_graph_features,
                "receiver": self.receiver_graph_features,
                "is_first_interaction": self.is_first_interaction,
                "shared_neighbors": self.shared_neighbors,
                "path_to_sanctions": self.path_to_sanctions,
                "mixer_exposure": self.mixer_exposure,
            },
            "action": self.action,
            "confidence": self.confidence,
            "processing_time_ms": self.processing_time_ms,
            "timestamp": self.timestamp,
        }


class RealtimeScorer:
    """
    Real-time transaction scoring using Memgraph.
    
    Workflow:
    1. Receive transaction → Ingest into graph
    2. Extract sender/receiver graph features
    3. Compute relationship features
    4. Generate combined risk score
    5. Optionally notify via WebSocket
    """
    
    # Risk thresholds for actions
    THRESHOLDS = {
        "BLOCK": 0.90,
        "ESCROW": 0.75,
        "REVIEW": 0.50,
        "MONITOR": 0.25,
        "APPROVE": 0.0,
    }
    
    # Risk weights
    SENDER_WEIGHT = 0.4
    RECEIVER_WEIGHT = 0.3
    RELATIONSHIP_WEIGHT = 0.3
    
    def __init__(
        self,
        service: Optional[MemgraphService] = None,
        auto_ingest: bool = True,
    ):
        """
        Initialize real-time scorer.
        
        Args:
            service: Memgraph service instance
            auto_ingest: Whether to automatically add transactions to graph
        """
        self.service = service or get_memgraph_service()
        self.feature_extractor = GraphFeatureExtractor(self.service)
        self.auto_ingest = auto_ingest
        
        # WebSocket subscribers for real-time updates
        self._subscribers: List[Callable] = []
        
        # Stats
        self._total_scored = 0
        self._total_blocked = 0
        self._avg_latency_ms = 0.0
        
        logger.info("RealtimeScorer initialized")
    
    def ingest_transaction(self, tx: Transaction) -> bool:
        """
        Add transaction to the graph.
        
        Creates/updates Address nodes and creates TRANSFER relationship.
        
        Args:
            tx: Transaction to ingest
            
        Returns:
            True if successfully ingested
        """
        query = """
        MERGE (from:Address {id: $from_addr})
        ON CREATE SET from.first_seen = $ts, from.tx_count = 1
        ON MATCH SET from.last_seen = $ts, from.tx_count = coalesce(from.tx_count, 0) + 1
        
        MERGE (to:Address {id: $to_addr})
        ON CREATE SET to.first_seen = $ts, to.tx_count = 1
        ON MATCH SET to.last_seen = $ts, to.tx_count = coalesce(to.tx_count, 0) + 1
        
        CREATE (from)-[t:TRANSFER {
            tx_hash: $tx_hash,
            value: $value,
            ts: $ts,
            block: $block,
            gas_price: $gas_price,
            gas_used: $gas_used
        }]->(to)
        
        RETURN from.id, to.id
        """
        
        try:
            self.service.execute(query, {
                "from_addr": tx.from_address.lower(),
                "to_addr": tx.to_address.lower(),
                "tx_hash": tx.tx_hash,
                "value": tx.value,
                "ts": tx.timestamp,
                "block": tx.block_number,
                "gas_price": tx.gas_price,
                "gas_used": tx.gas_used,
            })
            logger.debug(f"Ingested transaction {tx.tx_hash}")
            return True
        except Exception as e:
            logger.error(f"Failed to ingest transaction {tx.tx_hash}: {e}")
            return False
    
    def score_transaction(self, tx: Transaction) -> RealtimeScore:
        """
        Score a transaction in real-time.
        
        Args:
            tx: Transaction to score
            
        Returns:
            RealtimeScore with risk assessment
        """
        start_time = time.time()
        
        # Optionally ingest first
        if self.auto_ingest:
            self.ingest_transaction(tx)
        
        from_addr = tx.from_address.lower()
        to_addr = tx.to_address.lower()
        
        # Extract graph features for sender and receiver
        sender_features = self.feature_extractor.extract_features(from_addr)
        receiver_features = self.feature_extractor.extract_features(to_addr)
        
        # Compute relationship-specific features
        relationship = self._compute_relationship_features(from_addr, to_addr)
        
        # Calculate risk scores
        sender_risk = self._compute_address_risk(sender_features)
        receiver_risk = self._compute_address_risk(receiver_features)
        relationship_risk = self._compute_relationship_risk(relationship, tx.value)
        
        # Combined transaction risk
        tx_risk = (
            self.SENDER_WEIGHT * sender_risk +
            self.RECEIVER_WEIGHT * receiver_risk +
            self.RELATIONSHIP_WEIGHT * relationship_risk
        )
        
        # Determine action
        action = self._determine_action(tx_risk)
        confidence = self._compute_confidence(sender_features, receiver_features)
        
        processing_time = (time.time() - start_time) * 1000
        
        # Update stats
        self._total_scored += 1
        if action == "BLOCK":
            self._total_blocked += 1
        self._avg_latency_ms = (
            (self._avg_latency_ms * (self._total_scored - 1) + processing_time) 
            / self._total_scored
        )
        
        score = RealtimeScore(
            tx_hash=tx.tx_hash,
            from_address=from_addr,
            to_address=to_addr,
            sender_risk_score=sender_risk,
            receiver_risk_score=receiver_risk,
            transaction_risk_score=tx_risk,
            sender_graph_features=sender_features.to_dict(),
            receiver_graph_features=receiver_features.to_dict(),
            is_first_interaction=relationship["is_first_interaction"],
            shared_neighbors=relationship["shared_neighbors"],
            path_to_sanctions=min(
                sender_features.sanctions_distance,
                receiver_features.sanctions_distance
            ),
            mixer_exposure=sender_features.is_mixer_connected or receiver_features.is_mixer_connected,
            action=action,
            confidence=confidence,
            processing_time_ms=processing_time,
            timestamp=datetime.utcnow().isoformat(),
        )
        
        # Notify subscribers
        self._notify_subscribers(score)
        
        return score
    
    def _compute_relationship_features(
        self, from_addr: str, to_addr: str
    ) -> Dict[str, Any]:
        """Compute features about the relationship between two addresses."""
        
        # Check if this is a first-time interaction
        first_interaction_query = """
        MATCH (a:Address {id: $from})-[t:TRANSFER]->(b:Address {id: $to})
        RETURN count(t) AS tx_count
        """
        
        # Count shared neighbors (common counterparties)
        shared_neighbors_query = """
        MATCH (a:Address {id: $from})-[:TRANSFER]-(common)-[:TRANSFER]-(b:Address {id: $to})
        WHERE a <> b AND common <> a AND common <> b
        RETURN count(DISTINCT common) AS shared
        """
        
        # Previous transaction volume between parties
        volume_query = """
        MATCH (a:Address {id: $from})-[t:TRANSFER]->(b:Address {id: $to})
        RETURN sum(t.value) AS total_volume, count(t) AS tx_count
        """
        
        result = {
            "is_first_interaction": True,
            "shared_neighbors": 0,
            "previous_volume": 0.0,
            "previous_tx_count": 0,
        }
        
        params = {"from": from_addr, "to": to_addr}
        
        try:
            # First interaction check
            r = self.service.execute(first_interaction_query, params)
            if r and r[0][0] > 1:  # More than 1 means we just added one
                result["is_first_interaction"] = False
            
            # Shared neighbors
            r = self.service.execute(shared_neighbors_query, params)
            if r:
                result["shared_neighbors"] = int(r[0][0] or 0)
            
            # Previous volume
            r = self.service.execute(volume_query, params)
            if r:
                result["previous_volume"] = float(r[0][0] or 0)
                result["previous_tx_count"] = int(r[0][1] or 0)
                
        except Exception as e:
            logger.debug(f"Relationship feature extraction error: {e}")
        
        return result
    
    def _compute_address_risk(self, features: GraphFeatures) -> float:
        """
        Compute risk score for an address based on graph features.
        
        Returns:
            Risk score between 0.0 (safe) and 1.0 (high risk)
        """
        risk = 0.0
        
        # Sanctions proximity (high weight)
        if features.sanctions_distance <= 1:
            risk += 0.5  # Direct connection to sanctioned
        elif features.sanctions_distance <= 2:
            risk += 0.3
        elif features.sanctions_distance <= 3:
            risk += 0.15
        elif features.sanctions_distance <= 5:
            risk += 0.05
        
        # Mixer connection (high weight)
        if features.is_mixer_connected:
            risk += 0.25
        
        # Loop patterns (suspicious)
        if features.loop_count > 0:
            risk += min(0.1 * features.loop_count, 0.2)
        
        # Low activity (potentially fresh addresses for fraud)
        if features.transaction_count < 5:
            risk += 0.1
        
        # High in/out ratio (potential drain)
        if features.out_degree > 0:
            ratio = features.in_degree / features.out_degree
            if ratio > 10:  # Many ins, few outs (accumulating)
                risk += 0.1
            elif ratio < 0.1:  # Few ins, many outs (draining)
                risk += 0.15
        
        return min(risk, 1.0)
    
    def _compute_relationship_risk(
        self, relationship: Dict[str, Any], value: float
    ) -> float:
        """
        Compute risk based on the relationship between sender and receiver.
        
        Args:
            relationship: Relationship features dict
            value: Transaction value in ETH
        """
        risk = 0.0
        
        # First-time interaction with high value
        if relationship["is_first_interaction"]:
            risk += 0.1
            if value > 10.0:  # Large first-time transfer
                risk += 0.2
            elif value > 1.0:
                risk += 0.1
        
        # No shared neighbors (isolated transaction)
        if relationship["shared_neighbors"] == 0:
            risk += 0.1
        elif relationship["shared_neighbors"] > 5:
            # Many shared neighbors suggests legitimate activity
            risk -= 0.1
        
        return max(0.0, min(risk, 1.0))
    
    def _determine_action(self, risk_score: float) -> str:
        """Determine recommended action based on risk score."""
        for action, threshold in sorted(
            self.THRESHOLDS.items(), 
            key=lambda x: x[1], 
            reverse=True
        ):
            if risk_score >= threshold:
                return action
        return "APPROVE"
    
    def _compute_confidence(
        self, sender: GraphFeatures, receiver: GraphFeatures
    ) -> float:
        """
        Compute confidence in the risk assessment.
        
        Higher confidence when we have more data about the addresses.
        """
        # More transactions = more confidence
        sender_confidence = min(sender.transaction_count / 50, 1.0)
        receiver_confidence = min(receiver.transaction_count / 50, 1.0)
        
        # Average with slight weight toward sender
        confidence = 0.6 * sender_confidence + 0.4 * receiver_confidence
        
        # Minimum confidence of 0.3 even for new addresses
        return max(0.3, confidence)
    
    def subscribe(self, callback: Callable[[RealtimeScore], None]):
        """Add a subscriber for real-time score updates."""
        self._subscribers.append(callback)
    
    def unsubscribe(self, callback: Callable[[RealtimeScore], None]):
        """Remove a subscriber."""
        if callback in self._subscribers:
            self._subscribers.remove(callback)
    
    def _notify_subscribers(self, score: RealtimeScore):
        """Notify all subscribers of a new score."""
        for callback in self._subscribers:
            try:
                callback(score)
            except Exception as e:
                logger.error(f"Subscriber notification failed: {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get scoring statistics."""
        return {
            "total_scored": self._total_scored,
            "total_blocked": self._total_blocked,
            "block_rate": self._total_blocked / max(1, self._total_scored),
            "avg_latency_ms": self._avg_latency_ms,
        }
    
    def batch_score(self, transactions: List[Transaction]) -> List[RealtimeScore]:
        """Score multiple transactions."""
        return [self.score_transaction(tx) for tx in transactions]


# Memgraph trigger setup for automatic scoring
TRIGGER_SETUP_QUERY = """
// This trigger fires after a new TRANSFER is created
// Note: Memgraph triggers require MAGE module for complex operations
CREATE TRIGGER score_new_transfer
ON () CREATE AFTER COMMIT EXECUTE
CALL score_transfer(createdEdges);
"""


def setup_memgraph_triggers(service: MemgraphService):
    """
    Set up Memgraph triggers for automatic scoring.
    
    Note: This requires Memgraph MAGE module and a custom procedure.
    For simpler setups, use the API-based approach instead.
    """
    logger.info("Trigger setup requires Memgraph MAGE module. Skipping for now.")
    # In production, you would:
    # 1. Install MAGE module
    # 2. Create a custom procedure that calls our scoring logic
    # 3. Set up the trigger to call that procedure
    pass


# Singleton instance
_scorer: Optional[RealtimeScorer] = None


def get_realtime_scorer() -> RealtimeScorer:
    """Get or create singleton scorer instance."""
    global _scorer
    if _scorer is None:
        _scorer = RealtimeScorer()
    return _scorer
