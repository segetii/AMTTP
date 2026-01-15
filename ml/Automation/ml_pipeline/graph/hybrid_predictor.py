"""
AMTTP ML Pipeline - Hybrid Predictor

Combines tabular ML features with graph-based features from Memgraph
for enhanced fraud detection.
"""
import logging
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional, Union
from dataclasses import dataclass
import numpy as np
import pandas as pd

# Handle imports based on how module is loaded
try:
    from ..inference.cpu_predictor import CPUPredictor
except ImportError:
    # Add parent to path for standalone imports
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from inference.cpu_predictor import CPUPredictor

from .features import GraphFeatureExtractor, GraphFeatures
from .service import MemgraphService, get_memgraph_service

logger = logging.getLogger(__name__)


@dataclass
class HybridPrediction:
    """Combined prediction from tabular and graph models."""
    transaction_id: str
    # Tabular model output
    tabular_risk_score: float
    tabular_prediction: int
    tabular_action: str
    # Graph model output
    graph_risk_score: float
    graph_features: Dict[str, Any]
    # Combined output
    combined_risk_score: float
    combined_action: str
    confidence: float
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "transaction_id": self.transaction_id,
            "tabular": {
                "risk_score": self.tabular_risk_score,
                "prediction": self.tabular_prediction,
                "action": self.tabular_action,
            },
            "graph": {
                "risk_score": self.graph_risk_score,
                "features": self.graph_features,
            },
            "combined": {
                "risk_score": self.combined_risk_score,
                "action": self.combined_action,
                "confidence": self.confidence,
            },
        }


class HybridPredictor:
    """
    Hybrid fraud predictor combining tabular ML and graph analysis.
    
    Features:
    - XGBoost/LightGBM tabular predictions
    - Graph-based risk scoring from Memgraph
    - Weighted combination for final score
    - Action recommendations
    """
    
    # Weights for combining scores
    TABULAR_WEIGHT = 0.7
    GRAPH_WEIGHT = 0.3
    
    # Action thresholds
    ACTION_THRESHOLDS = {
        "BLOCK": 0.90,
        "ESCROW": 0.75,
        "REVIEW": 0.50,
        "MONITOR": 0.25,
        "APPROVE": 0.0,
    }
    
    def __init__(
        self,
        tabular_predictor: Optional[CPUPredictor] = None,
        graph_service: Optional[MemgraphService] = None,
        models_dir: str = "models/trained",
        tabular_weight: float = 0.7,
        graph_weight: float = 0.3,
    ):
        """
        Initialize hybrid predictor.
        
        Args:
            tabular_predictor: CPUPredictor instance. Creates new if None.
            graph_service: MemgraphService instance. Uses singleton if None.
            models_dir: Path to trained models
            tabular_weight: Weight for tabular model (0-1)
            graph_weight: Weight for graph features (0-1)
        """
        # Initialize tabular predictor
        if tabular_predictor is None:
            self.tabular = CPUPredictor(models_dir=models_dir)
        else:
            self.tabular = tabular_predictor
        
        # Initialize graph components
        try:
            self.graph_service = graph_service or get_memgraph_service()
            self.graph_extractor = GraphFeatureExtractor(self.graph_service)
            self._graph_available = True
        except Exception as e:
            logger.warning(f"Graph service unavailable: {e}. Running in tabular-only mode.")
            self.graph_service = None
            self.graph_extractor = None
            self._graph_available = False
        
        # Set weights (normalize to sum to 1)
        total = tabular_weight + graph_weight
        self.tabular_weight = tabular_weight / total
        self.graph_weight = graph_weight / total if self._graph_available else 0
        
        # Adjust if graph unavailable
        if not self._graph_available:
            self.tabular_weight = 1.0
    
    def predict(
        self,
        transaction_id: str,
        tabular_features: Union[Dict[str, float], pd.DataFrame],
        from_address: Optional[str] = None,
        to_address: Optional[str] = None,
    ) -> HybridPrediction:
        """
        Make a hybrid prediction for a transaction.
        
        Args:
            transaction_id: Transaction identifier
            tabular_features: Features for tabular model (dict or DataFrame)
            from_address: Sender address for graph lookup
            to_address: Receiver address for graph lookup
            
        Returns:
            HybridPrediction with combined results
        """
        # Get tabular prediction
        if isinstance(tabular_features, dict):
            df = pd.DataFrame([tabular_features])
        else:
            df = tabular_features
        
        tabular_results = self.tabular.predict_with_action(df)[0]
        tabular_score = tabular_results["risk_score"]
        tabular_pred = tabular_results["prediction"]
        tabular_action = tabular_results["action"]
        
        # Get graph features and score
        graph_score = 0.0
        graph_features_dict = {}
        
        if self._graph_available and (from_address or to_address):
            try:
                # Get features for both addresses
                addresses_to_check = []
                if from_address:
                    addresses_to_check.append(from_address.lower())
                if to_address:
                    addresses_to_check.append(to_address.lower())
                
                # Extract features
                features_map = self.graph_extractor.extract_features_batch(addresses_to_check)
                
                # Use max risk from involved addresses
                max_graph_risk = 0.0
                combined_features = {}
                
                for addr, features in features_map.items():
                    addr_risk = self.graph_extractor.get_risk_score_from_graph(addr)
                    if addr_risk > max_graph_risk:
                        max_graph_risk = addr_risk
                    
                    # Store features
                    prefix = "from_" if addr == (from_address or "").lower() else "to_"
                    for key, val in features.to_dict().items():
                        if key != "address":
                            combined_features[f"{prefix}{key}"] = val
                
                graph_score = max_graph_risk
                graph_features_dict = combined_features
                
            except Exception as e:
                logger.warning(f"Graph feature extraction failed: {e}")
        
        # Combine scores
        combined_score = (
            self.tabular_weight * tabular_score +
            self.graph_weight * graph_score
        )
        
        # Determine action from combined score
        combined_action = "APPROVE"
        for action, threshold in sorted(
            self.ACTION_THRESHOLDS.items(),
            key=lambda x: x[1],
            reverse=True
        ):
            if combined_score >= threshold:
                combined_action = action
                break
        
        # Calculate confidence
        # Higher when tabular and graph agree
        if self._graph_available and graph_score > 0:
            score_diff = abs(tabular_score - graph_score)
            confidence = 1.0 - (score_diff * 0.5)  # Lower confidence if disagreement
        else:
            confidence = 0.85  # Default confidence for tabular-only
        
        return HybridPrediction(
            transaction_id=transaction_id,
            tabular_risk_score=tabular_score,
            tabular_prediction=tabular_pred,
            tabular_action=tabular_action,
            graph_risk_score=graph_score,
            graph_features=graph_features_dict,
            combined_risk_score=combined_score,
            combined_action=combined_action,
            confidence=confidence,
        )
    
    def predict_batch(
        self,
        transactions: List[Dict[str, Any]],
    ) -> List[HybridPrediction]:
        """
        Make predictions for multiple transactions.
        
        Args:
            transactions: List of dicts with keys:
                - transaction_id: str
                - features: Dict[str, float]
                - from_address: Optional[str]
                - to_address: Optional[str]
                
        Returns:
            List of HybridPrediction
        """
        results = []
        
        # Collect all addresses for batch graph extraction
        all_addresses = set()
        for txn in transactions:
            if txn.get("from_address"):
                all_addresses.add(txn["from_address"].lower())
            if txn.get("to_address"):
                all_addresses.add(txn["to_address"].lower())
        
        # Batch extract graph features
        graph_features_cache = {}
        if self._graph_available and all_addresses:
            try:
                graph_features_cache = self.graph_extractor.extract_features_batch(
                    list(all_addresses)
                )
            except Exception as e:
                logger.warning(f"Batch graph extraction failed: {e}")
        
        # Process each transaction
        for txn in transactions:
            # Get tabular prediction
            df = pd.DataFrame([txn["features"]])
            tabular_results = self.tabular.predict_with_action(df)[0]
            
            # Get graph score
            graph_score = 0.0
            graph_features_dict = {}
            
            from_addr = (txn.get("from_address") or "").lower()
            to_addr = (txn.get("to_address") or "").lower()
            
            if from_addr and from_addr in graph_features_cache:
                from_features = graph_features_cache[from_addr]
                from_risk = self._calculate_graph_risk(from_features)
                graph_score = max(graph_score, from_risk)
                for k, v in from_features.to_dict().items():
                    if k != "address":
                        graph_features_dict[f"from_{k}"] = v
            
            if to_addr and to_addr in graph_features_cache:
                to_features = graph_features_cache[to_addr]
                to_risk = self._calculate_graph_risk(to_features)
                graph_score = max(graph_score, to_risk)
                for k, v in to_features.to_dict().items():
                    if k != "address":
                        graph_features_dict[f"to_{k}"] = v
            
            # Combine scores
            combined_score = (
                self.tabular_weight * tabular_results["risk_score"] +
                self.graph_weight * graph_score
            )
            
            # Determine action
            combined_action = "APPROVE"
            for action, threshold in sorted(
                self.ACTION_THRESHOLDS.items(),
                key=lambda x: x[1],
                reverse=True
            ):
                if combined_score >= threshold:
                    combined_action = action
                    break
            
            results.append(HybridPrediction(
                transaction_id=txn["transaction_id"],
                tabular_risk_score=tabular_results["risk_score"],
                tabular_prediction=tabular_results["prediction"],
                tabular_action=tabular_results["action"],
                graph_risk_score=graph_score,
                graph_features=graph_features_dict,
                combined_risk_score=combined_score,
                combined_action=combined_action,
                confidence=0.85,
            ))
        
        return results
    
    def _calculate_graph_risk(self, features: GraphFeatures) -> float:
        """Calculate risk score from graph features."""
        score = 0.0
        
        if features.sanctions_distance <= 1:
            score += 0.5
        elif features.sanctions_distance <= 3:
            score += 0.3
        elif features.sanctions_distance <= 6:
            score += 0.1
        
        if features.is_mixer_connected:
            score += 0.25
        
        if features.loop_count > 5:
            score += 0.15
        elif features.loop_count > 0:
            score += 0.05
        
        score += min(0.1, features.community_risk_score * 0.1)
        
        return min(1.0, score)
    
    def is_graph_available(self) -> bool:
        """Check if graph features are available."""
        return self._graph_available
    
    def get_model_info(self) -> Dict[str, Any]:
        """Get information about the hybrid model."""
        info = {
            "tabular_model": self.tabular.primary_model,
            "tabular_weight": self.tabular_weight,
            "graph_weight": self.graph_weight,
            "graph_available": self._graph_available,
            "mode": "hybrid" if self._graph_available else "tabular-only",
        }
        
        if self._graph_available:
            info["graph_status"] = self.graph_service.health_check()
        
        return info


def create_hybrid_predictor(
    models_dir: str = "models/trained",
    tabular_weight: float = 0.7,
    graph_weight: float = 0.3,
) -> HybridPredictor:
    """Factory function to create hybrid predictor."""
    return HybridPredictor(
        models_dir=models_dir,
        tabular_weight=tabular_weight,
        graph_weight=graph_weight,
    )
