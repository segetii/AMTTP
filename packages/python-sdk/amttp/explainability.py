"""
AMTTP Explainability Module
Converts raw ML scores into human-readable explanations for risk decisions.

Usage:
    from amttp.explainability import ExplainabilityService

    explainer = ExplainabilityService()
    explanation = explainer.explain(
        risk_score=0.73,
        features={'amount_eth': 50, 'tx_count_24h': 15}
    )
    
    print(explanation.summary)
    print(explanation.top_reasons)
"""

from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Literal
from enum import Enum
import httpx


# ═══════════════════════════════════════════════════════════════════════════════
# ENUMS & TYPES
# ═══════════════════════════════════════════════════════════════════════════════

class ImpactLevel(str, Enum):
    """Impact level for explanation factors"""
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    NEUTRAL = "NEUTRAL"


class TypologyType(str, Enum):
    """Known fraud/AML typologies"""
    STRUCTURING = "structuring"
    LAYERING = "layering"
    ROUND_TRIP = "round_trip"
    SMURFING = "smurfing"
    FAN_OUT = "fan_out"
    FAN_IN = "fan_in"
    DORMANT_ACTIVATION = "dormant_activation"
    MIXER_INTERACTION = "mixer_interaction"
    SANCTIONS_PROXIMITY = "sanctions_proximity"
    HIGH_RISK_GEOGRAPHY = "high_risk_geography"
    UNUSUAL_TIMING = "unusual_timing"
    RAPID_MOVEMENT = "rapid_movement"
    PEELING = "peeling"


ActionType = Literal["ALLOW", "REVIEW", "ESCROW", "BLOCK"]


# ═══════════════════════════════════════════════════════════════════════════════
# DATA CLASSES
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class ExplanationFactor:
    """A single contributing factor to the risk score"""
    factor_id: str
    impact: ImpactLevel
    reason: str
    detail: str
    value: Any
    threshold: Optional[Any] = None
    contribution: float = 0.0


@dataclass
class TypologyMatch:
    """A matched fraud typology pattern"""
    typology: TypologyType
    confidence: float
    description: str
    indicators: List[str]
    evidence: Dict[str, Any]


@dataclass
class GraphExplanation:
    """Graph-based explanation"""
    summary: str
    hops_to_risk: Optional[int] = None
    pagerank: Optional[float] = None
    community: Optional[str] = None
    flagged_connections: Optional[List[str]] = None


@dataclass
class RiskExplanation:
    """Complete explanation for a risk decision"""
    risk_score: float
    action: ActionType
    summary: str
    top_reasons: List[str]
    factors: List[ExplanationFactor]
    typology_matches: List[TypologyMatch]
    graph_explanation: Optional[GraphExplanation]
    recommendations: List[str]
    confidence: float
    degraded_mode: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "risk_score": self.risk_score,
            "action": self.action,
            "summary": self.summary,
            "top_reasons": self.top_reasons,
            "factors": [
                {
                    "factor_id": f.factor_id,
                    "impact": f.impact.value,
                    "reason": f.reason,
                    "detail": f.detail,
                    "value": f.value,
                    "threshold": f.threshold,
                    "contribution": f.contribution
                }
                for f in self.factors
            ],
            "typology_matches": [
                {
                    "typology": t.typology.value,
                    "confidence": t.confidence,
                    "description": t.description,
                    "indicators": t.indicators,
                    "evidence": t.evidence
                }
                for t in self.typology_matches
            ],
            "graph_explanation": self.graph_explanation.summary if self.graph_explanation else None,
            "recommendations": self.recommendations,
            "confidence": self.confidence,
            "degraded_mode": self.degraded_mode
        }


@dataclass
class TypologyInfo:
    """Information about a fraud typology"""
    id: str
    name: str
    description: str


# ═══════════════════════════════════════════════════════════════════════════════
# TYPOLOGY DEFINITIONS
# ═══════════════════════════════════════════════════════════════════════════════

TYPOLOGIES: List[TypologyInfo] = [
    TypologyInfo("structuring", "Structuring", "Breaking large transactions into smaller ones to avoid reporting thresholds"),
    TypologyInfo("layering", "Layering", "Complex chains of transactions to obscure the source of funds"),
    TypologyInfo("round_trip", "Round Trip", "Funds returning to origin through intermediaries"),
    TypologyInfo("smurfing", "Smurfing", "Using multiple accounts/people to move funds"),
    TypologyInfo("fan_out", "Fan Out", "Single source distributing to many destinations"),
    TypologyInfo("fan_in", "Fan In", "Many sources consolidating to single destination"),
    TypologyInfo("dormant_activation", "Dormant Account Activation", "Previously inactive account suddenly active with large amounts"),
    TypologyInfo("mixer_interaction", "Mixer Interaction", "Funds passing through known mixing services"),
    TypologyInfo("sanctions_proximity", "Sanctions Proximity", "Close network connection to sanctioned entities"),
    TypologyInfo("high_risk_geography", "High Risk Geography", "Transaction involving FATF high-risk jurisdictions"),
    TypologyInfo("unusual_timing", "Unusual Timing", "Transactions at atypical hours or rapid succession"),
    TypologyInfo("rapid_movement", "Rapid Movement", "Funds moved through multiple hops in short time"),
    TypologyInfo("peeling", "Peeling Chain", "Sequential transactions that progressively reduce amounts"),
]


# ═══════════════════════════════════════════════════════════════════════════════
# EXPLAINABILITY SERVICE
# ═══════════════════════════════════════════════════════════════════════════════

class ExplainabilityService:
    """
    Service for generating human-readable explanations for ML risk scores.
    
    Example:
        >>> explainer = ExplainabilityService()
        >>> explanation = explainer.explain(
        ...     risk_score=0.73,
        ...     features={'amount_eth': 50, 'tx_count_24h': 15}
        ... )
        >>> print(explanation.summary)
        'High-risk transaction due to large amount and elevated activity'
    """
    
    def __init__(self, base_url: str = "http://localhost:8009", timeout: float = 5.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client = httpx.Client(timeout=timeout)
    
    def explain(
        self,
        risk_score: float,
        features: Dict[str, Any],
        graph_context: Optional[Dict[str, Any]] = None,
        rule_results: Optional[List[Dict[str, Any]]] = None,
        model_contributions: Optional[Dict[str, float]] = None
    ) -> RiskExplanation:
        """
        Generate human-readable explanation for a risk score.
        
        Args:
            risk_score: Risk score (0-1)
            features: Feature values used in scoring
            graph_context: Optional graph analysis context
            rule_results: Optional rule check results
            model_contributions: Optional model contribution breakdown
            
        Returns:
            RiskExplanation with human-readable factors and recommendations
        """
        try:
            response = self._client.post(
                f"{self.base_url}/explain",
                json={
                    "risk_score": risk_score,
                    "features": features,
                    "graph_context": graph_context,
                    "rule_results": rule_results,
                    "model_contributions": model_contributions
                }
            )
            response.raise_for_status()
            return self._parse_response(response.json())
        except (httpx.RequestError, httpx.HTTPStatusError):
            # Fallback to local explanation
            return self._generate_local_explanation(risk_score, features)
    
    def explain_transaction(
        self,
        transaction_hash: str,
        risk_score: float,
        sender: str,
        receiver: str,
        amount: float,
        features: Dict[str, Any],
        graph_context: Optional[Dict[str, Any]] = None
    ) -> RiskExplanation:
        """
        Generate explanation for a specific transaction.
        
        Args:
            transaction_hash: Transaction hash
            risk_score: Risk score (0-1)
            sender: Sender address
            receiver: Receiver address
            amount: Amount in ETH
            features: Additional features
            graph_context: Optional graph context
            
        Returns:
            RiskExplanation with transaction context
        """
        try:
            response = self._client.post(
                f"{self.base_url}/explain/transaction",
                json={
                    "transaction_hash": transaction_hash,
                    "risk_score": risk_score,
                    "sender": sender,
                    "receiver": receiver,
                    "amount": amount,
                    "features": features,
                    "graph_context": graph_context
                }
            )
            response.raise_for_status()
            return self._parse_response(response.json())
        except (httpx.RequestError, httpx.HTTPStatusError):
            enriched_features = {**features, "amount_eth": amount}
            return self._generate_local_explanation(risk_score, enriched_features)
    
    def get_typologies(self) -> List[TypologyInfo]:
        """List all known fraud typologies."""
        try:
            response = self._client.get(f"{self.base_url}/typologies")
            response.raise_for_status()
            data = response.json()
            return [
                TypologyInfo(t["id"], t["name"], t["description"])
                for t in data.get("typologies", [])
            ]
        except:
            return TYPOLOGIES
    
    def health_check(self) -> bool:
        """Check if the explainability service is healthy."""
        try:
            response = self._client.get(f"{self.base_url}/health")
            return response.status_code == 200
        except:
            return False
    
    def _parse_response(self, data: Dict[str, Any]) -> RiskExplanation:
        """Parse API response into RiskExplanation."""
        factors = [
            ExplanationFactor(
                factor_id=f.get("factor_id", ""),
                impact=ImpactLevel(f.get("impact", "NEUTRAL")),
                reason=f.get("reason", ""),
                detail=f.get("detail", ""),
                value=f.get("value"),
                threshold=f.get("threshold"),
                contribution=f.get("contribution", 0.0)
            )
            for f in data.get("factors", [])
        ]
        
        typologies = [
            TypologyMatch(
                typology=TypologyType(t.get("typology", "structuring")),
                confidence=t.get("confidence", 0.0),
                description=t.get("description", ""),
                indicators=t.get("indicators", []),
                evidence=t.get("evidence", {})
            )
            for t in data.get("typology_matches", [])
        ]
        
        graph_exp = None
        if data.get("graph_explanation"):
            graph_exp = GraphExplanation(summary=data["graph_explanation"])
        
        return RiskExplanation(
            risk_score=data.get("risk_score", 0.0),
            action=data.get("action", "REVIEW"),
            summary=data.get("summary", ""),
            top_reasons=data.get("top_reasons", []),
            factors=factors,
            typology_matches=typologies,
            graph_explanation=graph_exp,
            recommendations=data.get("recommendations", []),
            confidence=data.get("confidence", 0.0),
            degraded_mode=data.get("degraded_mode", False)
        )
    
    def _generate_local_explanation(
        self,
        risk_score: float,
        features: Dict[str, Any]
    ) -> RiskExplanation:
        """Generate explanation locally when service unavailable."""
        factors: List[ExplanationFactor] = []
        top_reasons: List[str] = []
        typology_matches: List[TypologyMatch] = []
        
        # Determine action
        if risk_score >= 0.85:
            action: ActionType = "BLOCK"
        elif risk_score >= 0.70:
            action = "ESCROW"
        elif risk_score >= 0.40:
            action = "REVIEW"
        else:
            action = "ALLOW"
        
        # Amount analysis
        amount_eth = features.get("amount_eth") or features.get("value_eth", 0)
        if amount_eth >= 100:
            factors.append(ExplanationFactor(
                factor_id="large_amount",
                impact=ImpactLevel.HIGH,
                reason=f"Large transaction amount ({amount_eth} ETH)",
                detail="Transaction amount exceeds typical threshold",
                value=amount_eth,
                threshold=100,
                contribution=0.25
            ))
            top_reasons.append(f"Large transaction ({amount_eth} ETH)")
        
        # Velocity analysis
        tx_count = features.get("tx_count_24h") or features.get("velocity_24h", 0)
        if tx_count >= 20:
            factors.append(ExplanationFactor(
                factor_id="high_velocity",
                impact=ImpactLevel.HIGH,
                reason=f"High transaction velocity ({tx_count} in 24h)",
                detail="Unusually high number of transactions",
                value=tx_count,
                threshold=20,
                contribution=0.20
            ))
            top_reasons.append(f"{tx_count} transactions in 24 hours")
            
            if amount_eth and amount_eth < 10:
                typology_matches.append(TypologyMatch(
                    typology=TypologyType.STRUCTURING,
                    confidence=0.6,
                    description="Multiple small transactions may indicate structuring",
                    indicators=["High transaction count", "Below-threshold amounts"],
                    evidence={"tx_count_24h": tx_count, "average_amount": amount_eth}
                ))
        
        # Sanctions proximity
        hops = features.get("hops_to_sanctioned")
        if hops is not None and hops <= 2:
            impact = ImpactLevel.CRITICAL if hops == 0 else ImpactLevel.HIGH if hops == 1 else ImpactLevel.MEDIUM
            factors.append(ExplanationFactor(
                factor_id="sanctions_proximity",
                impact=impact,
                reason="Direct sanctioned address match" if hops == 0 else f"{hops} hop(s) from sanctioned address",
                detail="Network proximity to known sanctioned entities",
                value=hops,
                threshold=2,
                contribution=0.5 if hops == 0 else 0.3
            ))
            top_reasons.append("Sanctioned address" if hops == 0 else f"{hops} hop(s) from sanctioned address")
            
            typology_matches.append(TypologyMatch(
                typology=TypologyType.SANCTIONS_PROXIMITY,
                confidence=1.0 if hops == 0 else 0.8,
                description="Connection to sanctioned entities detected",
                indicators=["Network analysis", "Graph traversal"],
                evidence={"hops": hops}
            ))
        
        # Generate summary
        if action == "BLOCK":
            summary = "Transaction blocked due to critical risk factors"
        elif action == "ESCROW":
            summary = f"High-risk transaction (score: {risk_score*100:.0f}%) - requires escrow or approval"
        elif action == "REVIEW":
            summary = "Moderate risk detected - manual review recommended"
        else:
            summary = "Low risk transaction - approved"
        
        # Recommendations
        recommendations = []
        if action == "BLOCK":
            recommendations = ["Do not proceed", "Report to compliance team"]
        elif action == "ESCROW":
            recommendations = ["Request additional KYC", "Use escrow mechanism", "Verify source of funds"]
        elif action == "REVIEW":
            recommendations = ["Verify counterparty identity", "Document business purpose"]
        
        if not top_reasons:
            top_reasons = ["ML model detected elevated risk patterns" if risk_score >= 0.5 else "Transaction within normal parameters"]
        
        return RiskExplanation(
            risk_score=risk_score,
            action=action,
            summary=summary,
            top_reasons=top_reasons[:5],
            factors=factors,
            typology_matches=typology_matches,
            graph_explanation=None,
            recommendations=recommendations,
            confidence=0.7,
            degraded_mode=True
        )
    
    def __enter__(self):
        return self
    
    def __exit__(self, *args):
        self._client.close()


# ═══════════════════════════════════════════════════════════════════════════════
# CONVENIENCE FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════

def format_explanation(explanation: RiskExplanation) -> str:
    """Format an explanation for display."""
    lines = [
        f"Risk Score: {explanation.risk_score*100:.1f}%",
        f"Action: {explanation.action}",
        "",
        explanation.summary,
        "",
        "Key Factors:"
    ]
    
    for i, reason in enumerate(explanation.top_reasons, 1):
        lines.append(f"  {i}. {reason}")
    
    if explanation.typology_matches:
        lines.append("")
        lines.append("Detected Patterns:")
        for t in explanation.typology_matches:
            lines.append(f"  • {t.description} ({t.confidence*100:.0f}% confidence)")
    
    if explanation.recommendations:
        lines.append("")
        lines.append("Recommendations:")
        for rec in explanation.recommendations:
            lines.append(f"  • {rec}")
    
    return "\n".join(lines)
