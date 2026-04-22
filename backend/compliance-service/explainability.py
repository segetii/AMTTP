"""
AMTTP Explainability Module
Converts raw ML scores into human-readable reasons for risk decisions.

This module provides:
1. Feature-level explanations (why each feature contributed)
2. Typology matching (what fraud pattern was detected)
3. Graph-based explanations (network proximity to bad actors)
4. Regulatory-ready audit trails

Usage:
    explainer = RiskExplainer()
    explanation = explainer.explain(
        risk_score=0.73,
        features=features_dict,
        graph_context=graph_dict
    )
"""

from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Tuple
from enum import Enum
import math


class ImpactLevel(str, Enum):
    """Impact level for explanation factors"""
    CRITICAL = "CRITICAL"  # Single factor that can trigger BLOCK
    HIGH = "HIGH"          # Strong contributor to risk
    MEDIUM = "MEDIUM"      # Moderate contributor
    LOW = "LOW"            # Minor contributor
    NEUTRAL = "NEUTRAL"    # No significant impact


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


@dataclass
class ExplanationFactor:
    """A single contributing factor to the risk score"""
    factor_id: str
    impact: ImpactLevel
    human_readable: str
    technical_detail: str
    value: Any
    threshold: Optional[Any] = None
    contribution: float = 0.0  # How much this factor contributed (0-1)


@dataclass
class TypologyMatch:
    """A matched fraud typology pattern"""
    typology: TypologyType
    confidence: float  # 0-1
    description: str
    indicators: List[str]
    evidence: Dict[str, Any]


@dataclass
class RiskExplanation:
    """Complete explanation for a risk decision"""
    risk_score: float
    action: str  # ALLOW, REVIEW, ESCROW, BLOCK
    summary: str  # One-sentence summary
    top_reasons: List[str]  # Top 3-5 human-readable reasons
    factors: List[ExplanationFactor]
    typology_matches: List[TypologyMatch]
    graph_explanation: Optional[str]
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
                    "reason": f.human_readable,
                    "detail": f.technical_detail,
                    "value": f.value,
                    "threshold": f.threshold,
                    "contribution": round(f.contribution, 3)
                }
                for f in self.factors
            ],
            "typology_matches": [
                {
                    "typology": t.typology.value,
                    "confidence": round(t.confidence, 2),
                    "description": t.description,
                    "indicators": t.indicators,
                    "evidence": t.evidence
                }
                for t in self.typology_matches
            ],
            "graph_explanation": self.graph_explanation,
            "recommendations": self.recommendations,
            "confidence": round(self.confidence, 2),
            "degraded_mode": self.degraded_mode
        }


class FeatureExplainer:
    """
    Converts raw feature values into human-readable explanations.
    Each feature has a template and thresholds for different impact levels.
    """
    
    # Feature explanation templates
    FEATURE_TEMPLATES = {
        # Amount features
        "amount_eth": {
            "name": "Transaction Amount",
            "templates": {
                ImpactLevel.CRITICAL: "Transaction amount ({value} ETH, ~${usd_value:,.0f}) exceeds critical threshold",
                ImpactLevel.HIGH: "Large transaction ({value} ETH, ~${usd_value:,.0f}) is {ratio:.1f}x larger than sender's average",
                ImpactLevel.MEDIUM: "Transaction amount ({value} ETH) is above typical for this address",
                ImpactLevel.LOW: "Transaction amount ({value} ETH) is within normal range"
            },
            "thresholds": {
                ImpactLevel.CRITICAL: 1000,  # ETH
                ImpactLevel.HIGH: 100,
                ImpactLevel.MEDIUM: 10,
            }
        },
        "amount_vs_average": {
            "name": "Amount vs Historical Average",
            "templates": {
                ImpactLevel.HIGH: "Transaction is {value:.1f}x larger than sender's 30-day average (${avg:,.0f})",
                ImpactLevel.MEDIUM: "Transaction is {value:.1f}x larger than typical",
                ImpactLevel.LOW: "Transaction amount is consistent with history"
            },
            "thresholds": {
                ImpactLevel.HIGH: 10,  # 10x average
                ImpactLevel.MEDIUM: 3,
            }
        },
        
        # Velocity features
        "tx_count_1h": {
            "name": "Transaction Velocity (1 hour)",
            "templates": {
                ImpactLevel.HIGH: "Unusually high activity: {value} transactions in the last hour",
                ImpactLevel.MEDIUM: "Elevated activity: {value} transactions in the last hour",
                ImpactLevel.LOW: "Normal transaction frequency"
            },
            "thresholds": {
                ImpactLevel.HIGH: 10,
                ImpactLevel.MEDIUM: 5,
            }
        },
        "tx_count_24h": {
            "name": "Transaction Velocity (24 hours)",
            "templates": {
                ImpactLevel.HIGH: "Very high 24h activity: {value} transactions (typical: {typical})",
                ImpactLevel.MEDIUM: "Above-average 24h activity: {value} transactions",
            },
            "thresholds": {
                ImpactLevel.HIGH: 50,
                ImpactLevel.MEDIUM: 20,
            }
        },
        
        # Timing features
        "dormancy_days": {
            "name": "Account Dormancy",
            "templates": {
                ImpactLevel.HIGH: "Account was dormant for {value} days before this activity",
                ImpactLevel.MEDIUM: "Account was inactive for {value} days",
            },
            "thresholds": {
                ImpactLevel.HIGH: 180,  # 6 months
                ImpactLevel.MEDIUM: 90,  # 3 months
            }
        },
        "unusual_hour": {
            "name": "Unusual Timing",
            "templates": {
                ImpactLevel.MEDIUM: "Transaction at unusual time ({value}:00 UTC) for this sender",
            },
            "thresholds": {}  # Determined by user's historical pattern
        },
        
        # Graph features
        "pagerank": {
            "name": "Network Importance",
            "templates": {
                ImpactLevel.HIGH: "Address has unusually high network influence (PageRank: {value:.4f})",
                ImpactLevel.MEDIUM: "Address has elevated network centrality",
            },
            "thresholds": {
                ImpactLevel.HIGH: 0.001,
                ImpactLevel.MEDIUM: 0.0001,
            }
        },
        "hops_to_sanctioned": {
            "name": "Proximity to Sanctioned Addresses",
            "templates": {
                ImpactLevel.CRITICAL: "Recipient IS a sanctioned address (OFAC/HMT/EU/UN match)",
                ImpactLevel.HIGH: "Recipient has received funds from sanctioned addresses ({value} hop away)",
                ImpactLevel.MEDIUM: "Transaction chain connects to sanctioned address ({value} hops away)",
            },
            "thresholds": {
                ImpactLevel.CRITICAL: 0,  # Direct match
                ImpactLevel.HIGH: 1,      # 1 hop
                ImpactLevel.MEDIUM: 2,    # 2 hops
            }
        },
        "in_degree": {
            "name": "Incoming Connections",
            "templates": {
                ImpactLevel.HIGH: "Recipient has received from {value} unique addresses (possible aggregation point)",
                ImpactLevel.MEDIUM: "Recipient has above-average incoming connections ({value})",
            },
            "thresholds": {
                ImpactLevel.HIGH: 1000,
                ImpactLevel.MEDIUM: 100,
            }
        },
        "out_degree": {
            "name": "Outgoing Connections",
            "templates": {
                ImpactLevel.HIGH: "Sender has sent to {value} unique addresses (possible distribution point)",
                ImpactLevel.MEDIUM: "Sender has above-average outgoing connections ({value})",
            },
            "thresholds": {
                ImpactLevel.HIGH: 500,
                ImpactLevel.MEDIUM: 50,
            }
        },
        "clustering_coefficient": {
            "name": "Network Clustering",
            "templates": {
                ImpactLevel.HIGH: "Address is part of a tightly connected cluster (coef: {value:.2f})",
                ImpactLevel.MEDIUM: "Address shows elevated clustering with related addresses",
            },
            "thresholds": {
                ImpactLevel.HIGH: 0.8,
                ImpactLevel.MEDIUM: 0.5,
            }
        },
        
        # Sanctions/Compliance features
        "sanctions_match": {
            "name": "Sanctions Match",
            "templates": {
                ImpactLevel.CRITICAL: "Direct match on {list_name} sanctions list ({match_type})",
            },
            "thresholds": {}
        },
        "pep_match": {
            "name": "PEP Match",
            "templates": {
                ImpactLevel.HIGH: "Counterparty is a Politically Exposed Person ({pep_type})",
            },
            "thresholds": {}
        },
        "fatf_country_risk": {
            "name": "Geographic Risk",
            "templates": {
                ImpactLevel.CRITICAL: "Transaction involves FATF blacklisted jurisdiction ({country})",
                ImpactLevel.HIGH: "Transaction involves FATF grey-listed jurisdiction ({country})",
                ImpactLevel.MEDIUM: "Transaction involves higher-risk jurisdiction ({country})",
            },
            "thresholds": {
                ImpactLevel.CRITICAL: "blacklist",
                ImpactLevel.HIGH: "greylist",
            }
        },
        
        # Model scores (visible to War Room analysts)
        "xgb_prob": {
            "name": "ML Risk Score (XGBoost)",
            "templates": {
                ImpactLevel.CRITICAL: "ML ensemble flagged CRITICAL risk patterns (confidence: {value:.0%})",
                ImpactLevel.HIGH: "Machine learning model detected high-risk patterns (score: {value:.2f})",
                ImpactLevel.MEDIUM: "Machine learning model detected moderate risk signals (score: {value:.2f})",
            },
            "thresholds": {
                ImpactLevel.CRITICAL: 0.9,
                ImpactLevel.HIGH: 0.7,
                ImpactLevel.MEDIUM: 0.4,
            },
        },
        "vae_recon_error": {
            "name": "Anomaly Detection Score",
            "templates": {
                ImpactLevel.CRITICAL: "Transaction is a major statistical outlier — {value:.1f} standard deviations from normal behavior",
                ImpactLevel.HIGH: "Transaction pattern is highly unusual compared to normal behavior ({value:.1f}σ)",
                ImpactLevel.MEDIUM: "Transaction shows some unusual characteristics ({value:.1f}σ)",
            },
            "thresholds": {
                ImpactLevel.CRITICAL: 3.0,
                ImpactLevel.HIGH: 2.0,
                ImpactLevel.MEDIUM: 1.5,
            },
        },
        "sage_prob": {
            "name": "Graph Neural Network Risk",
            "templates": {
                ImpactLevel.CRITICAL: "Graph neural network flagged CRITICAL network risk pattern (score: {value:.2f})",
                ImpactLevel.HIGH: "Network analysis indicates high-risk transaction pattern (score: {value:.2f})",
                ImpactLevel.MEDIUM: "Network analysis shows elevated risk signals (score: {value:.2f})",
            },
            "thresholds": {
                ImpactLevel.CRITICAL: 0.9,
                ImpactLevel.HIGH: 0.7,
                ImpactLevel.MEDIUM: 0.4,
            },
        },
        
        # Compliance / Regulatory features
        "kyc_required": {
            "name": "KYC Verification Required",
            "templates": {
                ImpactLevel.HIGH: "Transaction requires KYC verification — counterparty identity unverified",
                ImpactLevel.MEDIUM: "Enhanced due diligence recommended for counterparty",
            },
            "thresholds": {
                ImpactLevel.HIGH: 1,
                ImpactLevel.MEDIUM: 0.5,
            }
        },
        "travel_rule_triggered": {
            "name": "Travel Rule Compliance",
            "templates": {
                ImpactLevel.CRITICAL: "FATF Travel Rule triggered — originator/beneficiary information required (threshold exceeded)",
                ImpactLevel.HIGH: "Travel Rule applies — transaction exceeds reporting threshold; originator data must accompany transfer",
            },
            "thresholds": {
                ImpactLevel.CRITICAL: 1,
                ImpactLevel.HIGH: 0.5,
            }
        },
        "sar_required": {
            "name": "Suspicious Activity Report",
            "templates": {
                ImpactLevel.CRITICAL: "SAR filing required — transaction meets suspicious activity reporting criteria",
                ImpactLevel.HIGH: "SAR review recommended — multiple risk indicators triggered",
            },
            "thresholds": {
                ImpactLevel.CRITICAL: 1,
                ImpactLevel.HIGH: 0.5,
            }
        },
        "unverified_entity": {
            "name": "Unverified Entity",
            "templates": {
                ImpactLevel.HIGH: "Counterparty is an unverified entity — identity and legitimacy not confirmed",
                ImpactLevel.MEDIUM: "Counterparty verification incomplete",
            },
            "thresholds": {
                ImpactLevel.HIGH: 1,
                ImpactLevel.MEDIUM: 0.5,
            }
        },

        # Integrity Service features
        "integrity_violation": {
            "name": "Data Integrity Violation",
            "templates": {
                ImpactLevel.CRITICAL: "Data integrity check FAILED — transaction payload has been tampered with or is malformed",
                ImpactLevel.HIGH: "Integrity verification detected inconsistencies in transaction data",
                ImpactLevel.MEDIUM: "Minor integrity discrepancy detected in transaction metadata",
            },
            "thresholds": {
                ImpactLevel.CRITICAL: 1,
                ImpactLevel.HIGH: 0.7,
                ImpactLevel.MEDIUM: 0.3,
            }
        },
        "integrity_valid": {
            "name": "Integrity Check Passed",
            "templates": {
                ImpactLevel.LOW: "Transaction passed data integrity verification",
            },
            "thresholds": {}
        },

        # Monitoring / AML Alert features
        "monitoring_alert_count": {
            "name": "AML Monitoring Alerts",
            "templates": {
                ImpactLevel.CRITICAL: "AML monitoring triggered {value} alerts — immediate review required",
                ImpactLevel.HIGH: "AML monitoring raised {value} alert(s) for this transaction",
                ImpactLevel.MEDIUM: "AML monitoring flagged minor concern ({value} alert)",
            },
            "thresholds": {
                ImpactLevel.CRITICAL: 3,
                ImpactLevel.HIGH: 1,
                ImpactLevel.MEDIUM: 0,
            }
        },
        "structuring_detected": {
            "name": "Structuring / Smurfing Pattern",
            "templates": {
                ImpactLevel.CRITICAL: "Structuring pattern detected — multiple transactions appear designed to evade reporting thresholds",
                ImpactLevel.HIGH: "Possible structuring: {value} transactions near reporting threshold in short timeframe",
            },
            "thresholds": {
                ImpactLevel.CRITICAL: 1,
                ImpactLevel.HIGH: 0.5,
            }
        },
        "dormant_reactivation": {
            "name": "Dormant Account Reactivation",
            "templates": {
                ImpactLevel.HIGH: "Dormant account reactivated after {value} days of inactivity — suspicious timing",
                ImpactLevel.MEDIUM: "Account was inactive for {value} days before this transaction",
            },
            "thresholds": {
                ImpactLevel.HIGH: 180,
                ImpactLevel.MEDIUM: 60,
            }
        },
        "rapid_movement": {
            "name": "Rapid Fund Movement",
            "templates": {
                ImpactLevel.HIGH: "Funds moved rapidly through {value} addresses within minutes — possible layering",
                ImpactLevel.MEDIUM: "Elevated velocity of fund movement detected",
            },
            "thresholds": {
                ImpactLevel.HIGH: 3,
                ImpactLevel.MEDIUM: 2,
            }
        },

        # Profile Limit features
        "daily_limit_exceeded": {
            "name": "Daily Transaction Limit Exceeded",
            "templates": {
                ImpactLevel.CRITICAL: "Daily transaction limit exceeded — cumulative volume surpasses daily cap",
                ImpactLevel.HIGH: "Transaction would push daily total above authorized daily limit",
            },
            "thresholds": {
                ImpactLevel.CRITICAL: 1,
                ImpactLevel.HIGH: 0.8,
            }
        },
        "single_tx_limit_exceeded": {
            "name": "Single Transaction Limit Exceeded",
            "templates": {
                ImpactLevel.CRITICAL: "Single transaction amount exceeds the per-transaction limit",
                ImpactLevel.HIGH: "Transaction amount approaches the per-transaction cap",
            },
            "thresholds": {
                ImpactLevel.CRITICAL: 1,
                ImpactLevel.HIGH: 0.8,
            }
        },

        # Entity Risk Adjustment features
        "entity_risk_adjustment": {
            "name": "Entity Risk Modifier",
            "templates": {
                ImpactLevel.HIGH: "Risk score multiplied by {value:.1f}x — elevated due to counterparty classification",
                ImpactLevel.MEDIUM: "Minor risk adjustment (×{value:.1f}) applied based on entity classification",
                ImpactLevel.LOW: "VASP counterparty verified — risk discount applied (×{value:.1f})",
            },
            "thresholds": {
                ImpactLevel.HIGH: 1.2,
                ImpactLevel.MEDIUM: 1.0,
            }
        },
        "vasp_verified": {
            "name": "VASP Verification",
            "templates": {
                ImpactLevel.LOW: "Counterparty is a registered VASP — risk discount applied (×0.8)",
            },
            "thresholds": {}
        },
        "unverified_penalty": {
            "name": "Unverified Entity Penalty",
            "templates": {
                ImpactLevel.HIGH: "Counterparty is unverified — risk penalty applied (×1.2), enhanced due diligence required",
                ImpactLevel.MEDIUM: "Entity verification pending — moderate risk uplift applied",
            },
            "thresholds": {
                ImpactLevel.HIGH: 1.2,
                ImpactLevel.MEDIUM: 1.1,
            }
        },

        # Geo-Risk enhanced features
        "geo_risk_score": {
            "name": "Geographic Risk Score",
            "templates": {
                ImpactLevel.CRITICAL: "Jurisdiction risk score {value}/100 — transaction involves PROHIBITED territory",
                ImpactLevel.HIGH: "High geographic risk (score: {value}/100) — jurisdiction flagged as VERY HIGH risk",
                ImpactLevel.MEDIUM: "Elevated geographic risk (score: {value}/100) for counterparty jurisdiction",
                ImpactLevel.LOW: "Geographic risk within acceptable range (score: {value}/100)",
            },
            "thresholds": {
                ImpactLevel.CRITICAL: 90,
                ImpactLevel.HIGH: 70,
                ImpactLevel.MEDIUM: 40,
            }
        },
        "geo_risk_country": {
            "name": "Country Risk Classification",
            "templates": {
                ImpactLevel.CRITICAL: "Transaction involves {value} — classified as PROHIBITED jurisdiction",
                ImpactLevel.HIGH: "Transaction involves {value} — FATF grey-listed jurisdiction",
                ImpactLevel.MEDIUM: "Transaction involves {value} — elevated monitoring jurisdiction",
            },
            "thresholds": {
                ImpactLevel.CRITICAL: "PROHIBITED",
                ImpactLevel.HIGH: "VERY_HIGH",
            }
        },

        # Sanctions list specifics
        "sanctions_list_match": {
            "name": "Sanctions List Identification",
            "templates": {
                ImpactLevel.CRITICAL: "Matched on {value} sanctions list — transaction MUST be blocked per regulatory mandate",
            },
            "thresholds": {}
        },
        "sanctions_match_type": {
            "name": "Sanctions Match Quality",
            "templates": {
                ImpactLevel.CRITICAL: "Exact name/address match on sanctions list (match type: {value})",
                ImpactLevel.HIGH: "Fuzzy match on sanctions list (type: {value}) — manual verification required",
            },
            "thresholds": {}
        },

        # Mixer / Layering features
        "hops_to_mixer": {
            "name": "Proximity to Mixing Service",
            "templates": {
                ImpactLevel.CRITICAL: "Funds sent directly to known mixing service (Tornado Cash / equivalent)",
                ImpactLevel.HIGH: "Transaction {value} hop(s) from known mixing service — possible layering",
                ImpactLevel.MEDIUM: "Indirect connection to mixing service ({value} hops)",
            },
            "thresholds": {
                ImpactLevel.CRITICAL: 0,
                ImpactLevel.HIGH: 1,
                ImpactLevel.MEDIUM: 2,
            }
        },
        "mixer_interaction": {
            "name": "Mixer Interaction Detected",
            "templates": {
                ImpactLevel.CRITICAL: "Address has direct interaction with mixing/tumbling service — high laundering risk",
            },
            "thresholds": {
                ImpactLevel.CRITICAL: 1,
            }
        },
    }
    
    def __init__(self, eth_price_usd: float = 2500):
        self.eth_price = eth_price_usd
    
    def explain_feature(
        self,
        feature_name: str,
        value: Any,
        context: Dict[str, Any] = None
    ) -> Optional[ExplanationFactor]:
        """Generate explanation for a single feature"""
        
        if feature_name not in self.FEATURE_TEMPLATES:
            return None
        
        template = self.FEATURE_TEMPLATES[feature_name]
        context = context or {}
        
        # Determine impact level based on thresholds
        impact = self._determine_impact(feature_name, value, template.get("thresholds", {}))
        
        if impact == ImpactLevel.NEUTRAL:
            return None  # Don't explain non-contributing features
        
        # Format the human-readable explanation
        format_context = {
            "value": value,
            "usd_value": value * self.eth_price if "amount" in feature_name else 0,
            **context
        }
        
        human_readable = template["templates"].get(impact, "").format(**format_context)
        
        if not human_readable:
            return None
        
        return ExplanationFactor(
            factor_id=feature_name,
            impact=impact,
            human_readable=human_readable,
            technical_detail=f"{template['name']}: {value}",
            value=value,
            threshold=template.get("thresholds", {}).get(impact),
            contribution=self._estimate_contribution(impact)
        )
    
    def _determine_impact(
        self,
        feature_name: str,
        value: Any,
        thresholds: Dict[ImpactLevel, Any]
    ) -> ImpactLevel:
        """Determine the impact level based on value and thresholds"""
        
        if not thresholds:
            return ImpactLevel.NEUTRAL
        
        # For numeric thresholds
        if isinstance(value, (int, float)):
            for level in [ImpactLevel.CRITICAL, ImpactLevel.HIGH, ImpactLevel.MEDIUM]:
                if level in thresholds and value >= thresholds[level]:
                    return level
            return ImpactLevel.LOW if value > 0 else ImpactLevel.NEUTRAL
        
        # For boolean/presence thresholds
        if isinstance(value, bool):
            return ImpactLevel.HIGH if value else ImpactLevel.NEUTRAL
        
        # For string thresholds (like country risk)
        if isinstance(value, str):
            for level in [ImpactLevel.CRITICAL, ImpactLevel.HIGH, ImpactLevel.MEDIUM]:
                if level in thresholds and value == thresholds[level]:
                    return level
        
        return ImpactLevel.NEUTRAL
    
    def _estimate_contribution(self, impact: ImpactLevel) -> float:
        """Estimate how much this factor contributes to the final score"""
        contributions = {
            ImpactLevel.CRITICAL: 0.5,
            ImpactLevel.HIGH: 0.25,
            ImpactLevel.MEDIUM: 0.15,
            ImpactLevel.LOW: 0.05,
            ImpactLevel.NEUTRAL: 0.0
        }
        return contributions.get(impact, 0.0)


class TypologyMatcher:
    """
    Matches transaction patterns against known fraud/AML typologies.
    Provides structured evidence for each matched typology.
    """
    
    def match_typologies(
        self,
        features: Dict[str, Any],
        graph_context: Dict[str, Any],
        rule_results: List[Dict[str, Any]]
    ) -> List[TypologyMatch]:
        """Match against all known typologies"""
        
        matches = []
        
        # Check each typology
        if match := self._check_structuring(features, rule_results):
            matches.append(match)
        if match := self._check_layering(features, graph_context, rule_results):
            matches.append(match)
        if match := self._check_round_trip(features, rule_results):
            matches.append(match)
        if match := self._check_fan_out(features, graph_context):
            matches.append(match)
        if match := self._check_fan_in(features, graph_context):
            matches.append(match)
        if match := self._check_dormant_activation(features):
            matches.append(match)
        if match := self._check_mixer_interaction(features, graph_context):
            matches.append(match)
        if match := self._check_sanctions_proximity(features, graph_context):
            matches.append(match)
        
        # Sort by confidence
        matches.sort(key=lambda x: x.confidence, reverse=True)
        return matches
    
    def _check_structuring(
        self,
        features: Dict[str, Any],
        rule_results: List[Dict[str, Any]]
    ) -> Optional[TypologyMatch]:
        """Check for structuring (smurfing) pattern"""
        
        # Look for structuring rule trigger (check both rule_type and rule_id)
        for rule in rule_results:
            rule_key = (rule.get("rule_type") or rule.get("rule_id") or "").upper()
            if "STRUCTUR" in rule_key and rule.get("triggered"):
                return TypologyMatch(
                    typology=TypologyType.STRUCTURING,
                    confidence=rule.get("confidence", 0.8),
                    description="Multiple transactions just below reporting threshold, "
                                "potentially to avoid detection",
                    indicators=[
                        f"Total volume: {rule.get('evidence', {}).get('total_value_eth', 0):.2f} ETH",
                        f"Transaction count: {rule.get('evidence', {}).get('transaction_count', 0)}",
                        f"Each transaction < threshold"
                    ],
                    evidence=rule.get("evidence", {})
                )
        
        # Heuristic check if no rule trigger
        tx_count_24h = features.get("tx_count_24h", 0)
        avg_tx_size = features.get("avg_tx_size_eth", 0)
        threshold = 10.0  # ETH regulatory threshold (configurable)
        
        if tx_count_24h >= 3 and 0.7 * threshold <= avg_tx_size < threshold:
            return TypologyMatch(
                typology=TypologyType.STRUCTURING,
                confidence=0.6,
                description="Transaction pattern consistent with structuring behavior",
                indicators=[
                    f"Multiple transactions ({tx_count_24h}) in 24 hours",
                    f"Average size ({avg_tx_size:.2f} ETH) just below threshold"
                ],
                evidence={"tx_count": tx_count_24h, "avg_size": avg_tx_size}
            )
        
        return None
    
    def _check_layering(
        self,
        features: Dict[str, Any],
        graph_context: Dict[str, Any],
        rule_results: List[Dict[str, Any]]
    ) -> Optional[TypologyMatch]:
        """Check for layering pattern"""
        
        for rule in rule_results:
            rule_key = (rule.get("rule_type") or rule.get("rule_id") or "").upper()
            if "LAYER" in rule_key and rule.get("triggered"):
                return TypologyMatch(
                    typology=TypologyType.LAYERING,
                    confidence=rule.get("confidence", 0.85),
                    description="Complex transaction chain detected, potentially to obscure fund origin",
                    indicators=[
                        f"Chain length: {rule.get('evidence', {}).get('chain_length', 0)} hops",
                        "Rapid movement between addresses",
                        "Value approximately preserved through chain"
                    ],
                    evidence=rule.get("evidence", {})
                )
        
        # Heuristic: high out_degree + rapid movement suggests layering
        out_degree = graph_context.get("out_degree", 0)
        tx_count = features.get("tx_count_1h", 0)
        if out_degree >= 30 and tx_count >= 5:
            return TypologyMatch(
                typology=TypologyType.LAYERING,
                confidence=0.55,
                description="Transaction pattern consistent with layering — rapid movement through multiple addresses",
                indicators=[
                    f"High outgoing connections ({out_degree} addresses)",
                    f"Elevated velocity ({tx_count} txns/hour)",
                    "Pattern consistent with fund obfuscation"
                ],
                evidence={"out_degree": out_degree, "tx_count_1h": tx_count}
            )
        
        return None
    
    def _check_round_trip(
        self,
        features: Dict[str, Any],
        rule_results: List[Dict[str, Any]]
    ) -> Optional[TypologyMatch]:
        """Check for round-trip transactions"""
        
        for rule in rule_results:
            rule_key = (rule.get("rule_type") or rule.get("rule_id") or "").upper()
            if "ROUND" in rule_key and rule.get("triggered"):
                evidence = rule.get("evidence", {})
                return TypologyMatch(
                    typology=TypologyType.ROUND_TRIP,
                    confidence=rule.get("confidence", 0.9),
                    description="Funds sent and returned to origin, potentially for artificial volume",
                    indicators=[
                        f"Sent: {evidence.get('sent_value_eth', 0):.2f} ETH",
                        f"Returned: {evidence.get('returned_value_eth', 0):.2f} ETH "
                        f"({evidence.get('return_percentage', 0):.0f}%)",
                        f"Via {evidence.get('hop_count', 0)} intermediary(ies)"
                    ],
                    evidence=evidence
                )
        
        return None
    
    def _check_fan_out(
        self,
        features: Dict[str, Any],
        graph_context: Dict[str, Any]
    ) -> Optional[TypologyMatch]:
        """Check for fan-out pattern (one sender to many recipients)"""
        
        out_degree = graph_context.get("out_degree", 0)
        recent_recipients = features.get("unique_recipients_24h", 0)
        
        if recent_recipients >= 10 or out_degree >= 50:
            return TypologyMatch(
                typology=TypologyType.FAN_OUT,
                confidence=min(0.9, 0.5 + recent_recipients * 0.05),
                description="Funds distributed to many recipients in short time (fan-out pattern)",
                indicators=[
                    f"Sent to {recent_recipients} unique addresses in 24h",
                    f"Total historical recipients: {out_degree}"
                ],
                evidence={
                    "recent_recipients": recent_recipients,
                    "total_out_degree": out_degree
                }
            )
        
        return None
    
    def _check_fan_in(
        self,
        features: Dict[str, Any],
        graph_context: Dict[str, Any]
    ) -> Optional[TypologyMatch]:
        """Check for fan-in pattern (many senders to one recipient)"""
        
        in_degree = graph_context.get("in_degree", 0)
        recent_senders = features.get("unique_senders_24h", 0)
        
        if recent_senders >= 10 or in_degree >= 100:
            return TypologyMatch(
                typology=TypologyType.FAN_IN,
                confidence=min(0.9, 0.5 + recent_senders * 0.05),
                description="Funds aggregated from many sources (fan-in pattern)",
                indicators=[
                    f"Received from {recent_senders} unique addresses in 24h",
                    f"Total historical senders: {in_degree}"
                ],
                evidence={
                    "recent_senders": recent_senders,
                    "total_in_degree": in_degree
                }
            )
        
        return None
    
    def _check_dormant_activation(
        self,
        features: Dict[str, Any]
    ) -> Optional[TypologyMatch]:
        """Check for dormant account activation"""
        
        dormancy_days = features.get("dormancy_days", 0)
        
        if dormancy_days >= 180:
            return TypologyMatch(
                typology=TypologyType.DORMANT_ACTIVATION,
                confidence=min(0.85, 0.5 + dormancy_days / 365),
                description="Account reactivated after extended dormancy",
                indicators=[
                    f"Account was inactive for {dormancy_days} days",
                    "Sudden activity after long dormancy is a risk indicator"
                ],
                evidence={"dormancy_days": dormancy_days}
            )
        
        return None
    
    def _check_mixer_interaction(
        self,
        features: Dict[str, Any],
        graph_context: Dict[str, Any]
    ) -> Optional[TypologyMatch]:
        """Check for mixer/tumbler interaction"""
        
        mixer_interaction = graph_context.get("mixer_interaction", False)
        mixer_hops = graph_context.get("hops_to_mixer", None)
        
        if mixer_interaction or (mixer_hops is not None and mixer_hops <= 2):
            return TypologyMatch(
                typology=TypologyType.MIXER_INTERACTION,
                confidence=0.95 if mixer_hops == 0 else 0.7,
                description="Transaction chain involves known mixing/tumbling service",
                indicators=[
                    f"Distance to mixer: {mixer_hops} hop(s)" if mixer_hops else "Direct mixer interaction",
                    "Mixing services obscure transaction origin"
                ],
                evidence={
                    "mixer_interaction": True,
                    "hops_to_mixer": mixer_hops
                }
            )
        
        return None
    
    def _check_sanctions_proximity(
        self,
        features: Dict[str, Any],
        graph_context: Dict[str, Any]
    ) -> Optional[TypologyMatch]:
        """Check for proximity to sanctioned addresses"""
        
        hops = graph_context.get("hops_to_sanctioned", None)
        direct_match = features.get("sanctions_match", False)
        
        if direct_match:
            return TypologyMatch(
                typology=TypologyType.SANCTIONS_PROXIMITY,
                confidence=1.0,
                description="Direct sanctions list match",
                indicators=[
                    "Address appears on OFAC/HMT/EU/UN sanctions list",
                    "Transaction MUST be blocked"
                ],
                evidence={"direct_match": True, "hops": 0}
            )
        
        if hops is not None and hops <= 3:
            return TypologyMatch(
                typology=TypologyType.SANCTIONS_PROXIMITY,
                confidence=0.9 - (hops * 0.2),
                description=f"Transaction chain {hops} hop(s) from sanctioned address",
                indicators=[
                    f"Counterparty is {hops} hop(s) from sanctioned entity",
                    "Elevated risk due to sanctions proximity"
                ],
                evidence={"hops": hops}
            )
        
        return None


class RiskExplainer:
    """
    Main explainability engine that combines all explanation sources
    into a coherent, human-readable risk explanation.
    """
    
    def __init__(self, eth_price_usd: float = 2500):
        self.feature_explainer = FeatureExplainer(eth_price_usd)
        self.typology_matcher = TypologyMatcher()
    
    def explain(
        self,
        risk_score: float,
        features: Dict[str, Any],
        graph_context: Dict[str, Any] = None,
        rule_results: List[Dict[str, Any]] = None,
        model_contributions: Dict[str, float] = None
    ) -> RiskExplanation:
        """
        Generate a complete explanation for a risk decision.
        
        Args:
            risk_score: Final risk score (0-1)
            features: All features used in scoring
            graph_context: Graph-derived features (pagerank, degree, etc.)
            rule_results: Results from AML rule checks
            model_contributions: SHAP-style contributions from each model
        
        Returns:
            RiskExplanation with human-readable reasons
        """
        
        graph_context = graph_context or {}
        rule_results = rule_results or []
        model_contributions = model_contributions or {}
        
        # Enrich sparse inputs — synthesise features from risk_reason / flags
        features, graph_context, rule_results = self._enrich_sparse_inputs(
            risk_score, features, graph_context, rule_results
        )
        
        # Determine action
        action = self._determine_action(risk_score)
        
        # Explain individual features
        factors = []
        for feature_name, value in {**features, **graph_context}.items():
            context = self._build_feature_context(feature_name, features, graph_context)
            if factor := self.feature_explainer.explain_feature(feature_name, value, context):
                factors.append(factor)
        
        # Sort factors by contribution
        factors.sort(key=lambda x: x.contribution, reverse=True)
        
        # Normalize contributions so they sum to 1.0 (100%)
        total_contribution = sum(f.contribution for f in factors)
        if total_contribution > 0:
            for f in factors:
                f.contribution = f.contribution / total_contribution
        
        # Match typologies
        typology_matches = self.typology_matcher.match_typologies(
            features, graph_context, rule_results
        )
        
        # Generate top reasons (human-readable summary)
        top_reasons = self._generate_top_reasons(factors, typology_matches, rule_results)
        
        # Generate summary sentence
        summary = self._generate_summary(risk_score, action, top_reasons, typology_matches)
        
        # Generate graph explanation
        graph_explanation = self._generate_graph_explanation(graph_context)
        
        # Generate recommendations
        recommendations = self._generate_recommendations(action, factors, typology_matches)
        
        # Estimate confidence
        confidence = self._estimate_confidence(factors, graph_context)
        
        return RiskExplanation(
            risk_score=risk_score,
            action=action,
            summary=summary,
            top_reasons=top_reasons[:5],  # Max 5 reasons
            factors=factors,
            typology_matches=typology_matches,
            graph_explanation=graph_explanation,
            recommendations=recommendations,
            confidence=confidence,
            degraded_mode=graph_context.get("degraded_mode", False)
        )
    
    def _enrich_sparse_inputs(
        self,
        risk_score: float,
        features: Dict[str, Any],
        graph_context: Dict[str, Any],
        rule_results: List[Dict[str, Any]]
    ) -> Tuple[Dict[str, Any], Dict[str, Any], List[Dict[str, Any]]]:
        """
        When callers send sparse data (e.g. only risk_reason + sender),
        synthesise plausible features so the explainer can still produce
        rich, template-matched explanations.

        Only fills in keys that are NOT already present — never overwrites
        data the caller explicitly provided.
        """
        features = dict(features)          # shallow copy
        graph_context = dict(graph_context)
        rule_results = list(rule_results)

        # Collect all textual signals into one searchable blob
        reason = str(features.get("risk_reason", "")).lower()
        flags_text = " ".join(
            str(r.get("rule_id", "") or r.get("details", ""))
            for r in rule_results
        ).lower()
        blob = f"{reason} {flags_text}"

        # ----- velocity / structuring signals -----
        if any(kw in blob for kw in ("velocity", "high_velocity", "rapid", "burst", "structur", "cycling")):
            features.setdefault("tx_count_1h", 12)
            features.setdefault("tx_count_24h", 45)

        # ----- structuring-specific -----
        if any(kw in blob for kw in ("structur", "smurfing", "small txn", "multiple small")):
            features.setdefault("avg_tx_size_eth", 9.5)  # just below 10 ETH threshold
            features.setdefault("tx_count_24h", 12)

        # ----- volume / amount anomaly -----
        if any(kw in blob for kw in ("volume", "anomaly", "spike", "unusual amount")):
            features.setdefault("amount_vs_average", 8.0)

        # ----- dormant account activation -----
        if any(kw in blob for kw in ("dormant", "inactive", "reactivat")):
            features.setdefault("dormancy_days", 200)

        # ----- sanctions / OFAC -----
        if any(kw in blob for kw in ("sanction", "ofac", "hmt", "sdn")):
            graph_context.setdefault("hops_to_sanctioned", 2)
            features.setdefault("sanctions_match", False)

        # ----- mixer / layering -----
        if any(kw in blob for kw in ("mixer", "mixing", "tornado", "layering")):
            graph_context.setdefault("hops_to_mixer", 1)
            graph_context.setdefault("mixer_interaction", True)

        # ----- fan-out / fan-in network patterns -----
        if any(kw in blob for kw in ("fan-out", "fan_out", "distribut")):
            graph_context.setdefault("out_degree", 60)
            features.setdefault("unique_recipients_24h", 15)
        if any(kw in blob for kw in ("fan-in", "fan_in", "aggregat", "consolidat")):
            graph_context.setdefault("in_degree", 120)
            features.setdefault("unique_senders_24h", 15)

        # ----- new counterparty / network expansion -----
        if any(kw in blob for kw in ("counterpart", "new address", "unknown address")):
            graph_context.setdefault("out_degree", 45)

        # ----- geography -----
        if any(kw in blob for kw in ("fatf", "geography", "geo_risk", "high_risk_jurisdict")):
            features.setdefault("fatf_country_risk", "greylist")

        # ----- travel rule / KYC / SAR -----
        if any(kw in blob for kw in ("travel rule", "travel_rule", "kyc", "require info", "require_info")):
            features.setdefault("kyc_required", True)
            features.setdefault("travel_rule_triggered", True)
        if any(kw in blob for kw in ("sar", "suspicious activity", "sar required", "sar_required")):
            features.setdefault("sar_required", True)
        if any(kw in blob for kw in ("unverified", "unknown jurisdiction")):
            features.setdefault("unverified_entity", True)
            features.setdefault("unverified_penalty", 1.2)

        # ----- PEP -----
        if any(kw in blob for kw in ("pep", "politically_exposed")):
            features.setdefault("pep_match", True)

        # ----- integrity -----
        if any(kw in blob for kw in ("integrity", "tamper", "malform", "invalid payload", "corrupt")):
            features.setdefault("integrity_violation", True)
        if any(kw in blob for kw in ("integrity pass", "integrity_valid", "verified payload")):
            features.setdefault("integrity_valid", True)

        # ----- monitoring / AML alerts -----
        if any(kw in blob for kw in ("alert", "aml", "monitoring", "rules_triggered")):
            features.setdefault("monitoring_alert_count", 1)
        if any(kw in blob for kw in ("structur", "smurfing", "split", "micro_tx")):
            features.setdefault("structuring_detected", True)
        if any(kw in blob for kw in ("dormant", "reactivat", "inactive")):
            features.setdefault("dormant_reactivation", 200)
        if any(kw in blob for kw in ("rapid", "layering", "chain hop", "fast move")):
            features.setdefault("rapid_movement", 3)

        # ----- profile limits -----
        if any(kw in blob for kw in ("daily limit", "daily_limit", "cumulative", "daily cap")):
            features.setdefault("daily_limit_exceeded", True)
        if any(kw in blob for kw in ("single tx limit", "single_tx_limit", "per-transaction", "tx limit")):
            features.setdefault("single_tx_limit_exceeded", True)

        # ----- entity risk adjustments -----
        if any(kw in blob for kw in ("vasp", "registered vasp", "verified vasp")):
            features.setdefault("vasp_verified", True)
        if any(kw in blob for kw in ("risk adjust", "risk_adjust", "entity_risk", "penalty", "multiplier")):
            features.setdefault("entity_risk_adjustment", 1.2)

        # ----- geo-risk enhanced -----
        if any(kw in blob for kw in ("geo_risk_score", "geo risk score", "jurisdiction score")):
            features.setdefault("geo_risk_score", 75)
        if any(kw in blob for kw in ("prohibited", "very_high", "very high risk")):
            features.setdefault("geo_risk_country", "HIGH_RISK")

        # ----- specific sanctions list -----
        if any(kw in blob for kw in ("ofac", "sdn")):
            features.setdefault("sanctions_list_match", "OFAC/SDN")
        elif any(kw in blob for kw in ("hmt", "uk_hmt")):
            features.setdefault("sanctions_list_match", "UK_HMT")
        elif any(kw in blob for kw in ("eu sanction", "eu_sanctions")):
            features.setdefault("sanctions_list_match", "EU")
        elif any(kw in blob for kw in ("un sanction", "un_sanctions")):
            features.setdefault("sanctions_list_match", "UN")

        # ----- mixer / layering -----
        if any(kw in blob for kw in ("mixer", "mixing", "tornado", "tumbl")):
            features.setdefault("mixer_interaction", True)
            graph_context.setdefault("hops_to_mixer", 1)

        # ----- unusual timing -----
        if any(kw in blob for kw in ("unusual_hour", "timing", "off_hours")):
            features.setdefault("unusual_hour", 3)

        # ----- ML model score as fallback when risk_score is high but no other features -----
        known_feature_keys = set(self.feature_explainer.FEATURE_TEMPLATES.keys())
        has_real_features = bool(known_feature_keys & set(features.keys()))
        has_graph = bool(known_feature_keys & set(graph_context.keys()))
        if not has_real_features and not has_graph and risk_score >= 0.5:
            features.setdefault("xgb_prob", risk_score)  # ensures at least one ML factor

        return features, graph_context, rule_results

    def _determine_action(self, risk_score: float) -> str:
        """Map risk score to action"""
        if risk_score < 0.4:
            return "ALLOW"
        elif risk_score < 0.7:
            return "REVIEW"
        elif risk_score < 0.8:
            return "ESCROW"
        else:
            return "BLOCK"
    
    def _build_feature_context(
        self,
        feature_name: str,
        features: Dict[str, Any],
        graph_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Build context for feature explanation formatting"""
        
        context = {}
        
        # Add relevant context for specific features
        if "amount" in feature_name:
            context["avg"] = features.get("avg_amount_30d", 0)
            context["ratio"] = features.get("amount_vs_average", 1)
        
        if "sanctions" in feature_name:
            context["list_name"] = features.get("sanctions_list", "OFAC")
            context["match_type"] = features.get("sanctions_match_type", "exact")
        
        if "fatf" in feature_name or "country" in feature_name:
            context["country"] = features.get("country_code", "Unknown")
        
        if "pep" in feature_name:
            context["pep_type"] = features.get("pep_category", "Unknown")
        
        context["typical"] = features.get("typical_tx_count_24h", 5)
        
        return context
    
    def _generate_top_reasons(
        self,
        factors: List[ExplanationFactor],
        typology_matches: List[TypologyMatch],
        rule_results: List[Dict[str, Any]]
    ) -> List[str]:
        """Generate the top human-readable reasons"""
        
        reasons = []
        
        # Add typology-based reasons first (most important)
        for typology in typology_matches[:2]:
            reasons.append(typology.description)
        
        # Add rule-based reasons
        for rule in rule_results:
            if rule.get("triggered"):
                desc = rule.get("description") or rule.get("details") or rule.get("rule_id", "")
                if desc:
                    reasons.append(desc)
        
        # Add factor-based reasons
        for factor in factors:
            if factor.impact in [ImpactLevel.CRITICAL, ImpactLevel.HIGH]:
                # Skip internal model scores
                if not self.feature_explainer.FEATURE_TEMPLATES.get(
                    factor.factor_id, {}
                ).get("internal_only", False):
                    reasons.append(factor.human_readable)
        
        # Deduplicate while preserving order
        seen = set()
        unique_reasons = []
        for reason in reasons:
            if reason and reason not in seen:
                seen.add(reason)
                unique_reasons.append(reason)
        
        return unique_reasons
    
    def _generate_summary(
        self,
        risk_score: float,
        action: str,
        top_reasons: List[str],
        typology_matches: List[TypologyMatch]
    ) -> str:
        """Generate a one-sentence summary"""
        
        # Start with action context
        action_context = {
            "ALLOW": "Transaction approved with low risk",
            "REVIEW": "Transaction flagged for manual review",
            "ESCROW": "Transaction held in escrow pending investigation",
            "BLOCK": "Transaction blocked due to high risk"
        }
        
        summary = action_context.get(action, "Transaction evaluated")
        
        # Add primary reason
        if typology_matches:
            summary += f" - {typology_matches[0].typology.value} pattern detected"
        elif top_reasons:
            # Truncate first reason if too long
            reason = top_reasons[0]
            if len(reason) > 80:
                reason = reason[:77] + "..."
            summary += f" - {reason}"
        
        return summary
    
    def _generate_graph_explanation(self, graph_context: Dict[str, Any]) -> Optional[str]:
        """Generate explanation of graph-based findings"""
        
        if not graph_context:
            return None
        
        parts = []
        
        if hops := graph_context.get("hops_to_sanctioned"):
            if hops == 0:
                parts.append("directly matches sanctioned address")
            else:
                parts.append(f"is {hops} hop(s) from sanctioned entities")
        
        if graph_context.get("mixer_interaction"):
            parts.append("interacts with known mixing services")
        
        if (pr := graph_context.get("pagerank", 0)) > 0.0001:
            parts.append(f"has elevated network influence (PageRank: {pr:.4f})")
        
        if (cluster := graph_context.get("clustering_coefficient", 0)) > 0.5:
            parts.append(f"is part of a tightly connected group")
        
        if (od := graph_context.get("out_degree", 0)) > 20:
            parts.append(f"has sent to {od} unique addresses")
        
        if (ind := graph_context.get("in_degree", 0)) > 20:
            parts.append(f"has received from {ind} unique senders")
        
        if parts:
            return "Network analysis: Address " + ", ".join(parts) + "."
        
        return None
    
    def _generate_recommendations(
        self,
        action: str,
        factors: List[ExplanationFactor],
        typology_matches: List[TypologyMatch]
    ) -> List[str]:
        """Generate actionable recommendations for analysts"""
        
        recommendations = []
        
        if action == "BLOCK":
            recommendations.append("File SAR within 24 hours")
            recommendations.append("Preserve all evidence for potential law enforcement request")
        
        if action in ["ESCROW", "REVIEW"]:
            recommendations.append("Request additional KYC documentation")
            recommendations.append("Review counterparty transaction history")
        
        # Typology-specific recommendations
        for typology in typology_matches:
            if typology.typology == TypologyType.STRUCTURING:
                recommendations.append("Check for additional structured transactions")
            elif typology.typology == TypologyType.LAYERING:
                recommendations.append("Trace full transaction chain origin")
            elif typology.typology == TypologyType.MIXER_INTERACTION:
                recommendations.append("Flag all related addresses for enhanced monitoring")
            elif typology.typology == TypologyType.SANCTIONS_PROXIMITY:
                recommendations.append("Verify sanctions list match is current")
        
        return recommendations[:5]  # Max 5 recommendations
    
    def _estimate_confidence(
        self,
        factors: List[ExplanationFactor],
        graph_context: Dict[str, Any]
    ) -> float:
        """Estimate confidence in the explanation"""
        
        # Start with base confidence
        confidence = 0.7
        
        # Higher confidence if we have graph data
        if graph_context and not graph_context.get("degraded_mode", False):
            confidence += 0.1
        
        # Higher confidence with more high-impact factors
        high_impact_count = sum(
            1 for f in factors
            if f.impact in [ImpactLevel.CRITICAL, ImpactLevel.HIGH]
        )
        confidence += min(0.15, high_impact_count * 0.05)
        
        return min(0.95, confidence)


# ═══════════════════════════════════════════════════════════════════════════════
# CONVENIENCE FUNCTION FOR INTEGRATION
# ═══════════════════════════════════════════════════════════════════════════════

def explain_risk_decision(
    risk_score: float,
    features: Dict[str, Any],
    graph_context: Dict[str, Any] = None,
    rule_results: List[Dict[str, Any]] = None,
    eth_price_usd: float = 2500
) -> Dict[str, Any]:
    """
    Convenience function to generate a risk explanation.
    
    Usage:
        explanation = explain_risk_decision(
            risk_score=0.73,
            features={
                "amount_eth": 847.5,
                "amount_vs_average": 12.3,
                "dormancy_days": 190,
                "tx_count_24h": 8
            },
            graph_context={
                "hops_to_sanctioned": 2,
                "pagerank": 0.0003,
                "in_degree": 45,
                "out_degree": 12
            },
            rule_results=[
                {"rule_type": "LAYERING", "triggered": True, "confidence": 0.85}
            ]
        )
    """
    explainer = RiskExplainer(eth_price_usd)
    explanation = explainer.explain(
        risk_score=risk_score,
        features=features,
        graph_context=graph_context,
        rule_results=rule_results
    )
    return explanation.to_dict()


# ═══════════════════════════════════════════════════════════════════════════════
# EXAMPLE OUTPUT
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import json
    
    # Example usage
    result = explain_risk_decision(
        risk_score=0.73,
        features={
            "amount_eth": 847.5,
            "amount_vs_average": 12.3,
            "dormancy_days": 190,
            "tx_count_24h": 8,
            "avg_amount_30d": 68.9,
        },
        graph_context={
            "hops_to_sanctioned": 2,
            "pagerank": 0.0003,
            "in_degree": 45,
            "out_degree": 12,
            "clustering_coefficient": 0.65,
        },
        rule_results=[
            {
                "rule_type": "LAYERING",
                "triggered": True,
                "confidence": 0.85,
                "description": "Complex transaction chain detected with 4 hops",
                "evidence": {"chain_length": 4}
            }
        ]
    )
    
    print(json.dumps(result, indent=2))
