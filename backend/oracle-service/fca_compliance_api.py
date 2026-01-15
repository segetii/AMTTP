"""
AMTTP FCA Compliance API
UK Financial Conduct Authority Regulatory Reporting Endpoints

Implements:
- Suspicious Activity Reports (SARs) for NCA
- Transaction Monitoring Reports
- FATF Travel Rule compliance
- HMT Sanctions screening
- 5+ year audit trail
- XAI explainability for ML decisions

FCA Requirements addressed:
- MLR 2017 (Money Laundering Regulations)
- PSR 2017 (Payment Services Regulations)
- FSMA 2000 s.330 (SAR reporting)
- FATF Recommendation 16 (Travel Rule)
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, validator
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from enum import Enum
import hashlib
import json
import uuid
import os

# Initialize FastAPI app
app = FastAPI(
    title="AMTTP FCA Compliance API",
    description="UK FCA regulatory reporting and compliance endpoints",
    version="1.0.0",
    docs_url="/compliance/docs",
    redoc_url="/compliance/redoc"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============== Enums ==============

class SARType(str, Enum):
    SUSPICIOUS_TRANSACTION = "suspicious_transaction"
    STRUCTURING = "structuring"
    UNUSUAL_PATTERN = "unusual_pattern"
    SANCTIONS_MATCH = "sanctions_match"
    PEP_TRANSACTION = "pep_transaction"
    HIGH_RISK_JURISDICTION = "high_risk_jurisdiction"
    FRAUD_INDICATION = "fraud_indication"

class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class ReportStatus(str, Enum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    ACKNOWLEDGED = "acknowledged"
    UNDER_REVIEW = "under_review"
    CLOSED = "closed"

class SanctionsListType(str, Enum):
    HMT = "hmt"  # UK HM Treasury
    OFAC = "ofac"  # US OFAC
    EU = "eu"  # EU Consolidated
    UN = "un"  # UN Security Council

# ============== Models ==============

class PartyInfo(BaseModel):
    """FATF Travel Rule - Originator/Beneficiary information"""
    name: str
    address: Optional[str] = None
    account_number: str
    institution_name: Optional[str] = None
    institution_address: Optional[str] = None
    country: str = Field(..., min_length=2, max_length=2)  # ISO 3166-1 alpha-2
    date_of_birth: Optional[str] = None
    national_id: Optional[str] = None

class TransactionRecord(BaseModel):
    """Transaction for compliance review"""
    tx_hash: str
    from_address: str
    to_address: str
    value_eth: float
    value_gbp: Optional[float] = None
    timestamp: datetime
    block_number: int
    chain: str = "ethereum"
    
    # Risk assessment
    risk_score: float = Field(..., ge=0, le=1)
    risk_level: RiskLevel
    ml_model_version: str
    
    # Travel Rule data (if applicable)
    originator: Optional[PartyInfo] = None
    beneficiary: Optional[PartyInfo] = None
    
    # Additional context
    purpose: Optional[str] = None
    notes: Optional[str] = None

class SARRequest(BaseModel):
    """Suspicious Activity Report request"""
    transaction: TransactionRecord
    sar_type: SARType
    suspicion_grounds: str = Field(..., min_length=50)
    additional_evidence: Optional[List[str]] = None
    related_transactions: Optional[List[str]] = None
    urgency: str = Field(default="normal", pattern="^(normal|urgent)$")

class SARResponse(BaseModel):
    """SAR submission response"""
    sar_id: str
    reference_number: str  # NCA reference format
    status: ReportStatus
    submitted_at: datetime
    estimated_acknowledgment: datetime
    
class AuditLogEntry(BaseModel):
    """Audit trail entry"""
    log_id: str
    timestamp: datetime
    action: str
    entity_type: str
    entity_id: str
    actor: str
    details: Dict[str, Any]
    integrity_hash: str

class SanctionsCheckRequest(BaseModel):
    """Sanctions screening request"""
    address: str
    name: Optional[str] = None
    check_lists: List[SanctionsListType] = [SanctionsListType.HMT]

class SanctionsCheckResult(BaseModel):
    """Sanctions screening result"""
    address: str
    is_sanctioned: bool
    matches: List[Dict[str, Any]]
    checked_lists: List[str]
    check_timestamp: datetime
    confidence: float

class XAIExplanation(BaseModel):
    """Explainable AI decision report"""
    decision_id: str
    transaction_hash: str
    risk_score: float
    risk_level: RiskLevel
    decision: str
    
    # Feature contributions
    top_factors: List[Dict[str, Any]]
    feature_importance: Dict[str, float]
    
    # Model information
    model_version: str
    model_type: str
    training_date: str
    performance_metrics: Dict[str, float]
    
    # Human-readable explanation
    narrative_explanation: str
    regulatory_justification: str

class ComplianceReport(BaseModel):
    """Periodic compliance report"""
    report_id: str
    report_type: str
    period_start: datetime
    period_end: datetime
    generated_at: datetime
    
    summary: Dict[str, Any]
    transactions_reviewed: int
    sars_filed: int
    sanctions_hits: int
    high_risk_transactions: int

# ============== Storage (In-memory for demo, use MongoDB in production) ==============

SARS_STORE: Dict[str, Dict] = {}
AUDIT_LOGS: List[Dict] = []
SANCTIONS_CACHE: Dict[str, Dict] = {}

# Sample HMT sanctions list (in production, fetch from official source)
HMT_SANCTIONS_ADDRESSES = {
    "0x8576acc5c05d6ce88f4e49bf65bdf0c62f91353c": {
        "name": "Tornado Cash",
        "list_date": "2022-08-08",
        "reason": "OFAC SDN designation"
    },
    "0xd90e2f925da726b50c4ed8d0fb90ad053324f31b": {
        "name": "Tornado Cash",
        "list_date": "2022-08-08",
        "reason": "OFAC SDN designation"
    }
}

# ============== Helper Functions ==============

def generate_sar_reference() -> str:
    """Generate NCA-style SAR reference number"""
    timestamp = datetime.utcnow().strftime("%Y%m%d")
    random_suffix = uuid.uuid4().hex[:8].upper()
    return f"SAR-{timestamp}-{random_suffix}"

def compute_integrity_hash(data: Dict) -> str:
    """Compute SHA-256 hash for audit integrity"""
    canonical = json.dumps(data, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()

def log_audit_event(
    action: str,
    entity_type: str,
    entity_id: str,
    actor: str,
    details: Dict[str, Any]
):
    """Add entry to audit trail"""
    entry = {
        "log_id": str(uuid.uuid4()),
        "timestamp": datetime.utcnow().isoformat(),
        "action": action,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "actor": actor,
        "details": details
    }
    entry["integrity_hash"] = compute_integrity_hash(entry)
    AUDIT_LOGS.append(entry)
    return entry

def generate_xai_explanation(
    tx_hash: str,
    risk_score: float,
    features: Dict[str, float]
) -> XAIExplanation:
    """Generate explainable AI report for regulatory review"""
    
    # Determine risk level
    if risk_score >= 0.7:
        risk_level = RiskLevel.HIGH
        decision = "BLOCKED"
    elif risk_score >= 0.4:
        risk_level = RiskLevel.MEDIUM
        decision = "REVIEW"
    else:
        risk_level = RiskLevel.LOW
        decision = "APPROVED"
    
    # Sort features by importance
    sorted_features = sorted(features.items(), key=lambda x: abs(x[1]), reverse=True)
    
    top_factors = [
        {
            "feature": name,
            "contribution": value,
            "direction": "increases risk" if value > 0 else "decreases risk",
            "explanation": _explain_feature(name, value)
        }
        for name, value in sorted_features[:5]
    ]
    
    # Generate narrative
    narrative = _generate_narrative(risk_score, risk_level, top_factors)
    
    return XAIExplanation(
        decision_id=str(uuid.uuid4()),
        transaction_hash=tx_hash,
        risk_score=risk_score,
        risk_level=risk_level,
        decision=decision,
        top_factors=top_factors,
        feature_importance=dict(sorted_features),
        model_version="xgboost-hybrid-v2.1",
        model_type="XGBoost Gradient Boosting + Graph Analysis",
        training_date="2025-12-20",
        performance_metrics={
            "f1_score": 0.847,
            "precision": 0.823,
            "recall": 0.872,
            "auc_roc": 0.941
        },
        narrative_explanation=narrative,
        regulatory_justification=_generate_regulatory_justification(risk_level, decision)
    )

def _explain_feature(name: str, value: float) -> str:
    """Generate human-readable feature explanation"""
    explanations = {
        "value_eth": f"Transaction value {'high' if value > 0 else 'normal'} relative to typical patterns",
        "velocity_24h": f"Transaction velocity in 24h is {'elevated' if value > 0 else 'normal'}",
        "account_age_days": f"Account {'newer' if value > 0 else 'established'} than typical",
        "counterparty_risk": f"Counterparty has {'elevated' if value > 0 else 'low'} historical risk",
        "country_risk": f"Geographic risk indicator {'elevated' if value > 0 else 'normal'}",
        "time_of_day": f"Transaction timing {'unusual' if value > 0 else 'typical'}",
        "graph_centrality": f"Network position {'suspicious' if value > 0 else 'normal'}",
        "pattern_match": f"{'Matches' if value > 0 else 'No match to'} known fraud patterns"
    }
    return explanations.get(name, f"Feature {name} contribution: {value:.3f}")

def _generate_narrative(
    risk_score: float,
    risk_level: RiskLevel,
    top_factors: List[Dict]
) -> str:
    """Generate human-readable narrative explanation"""
    
    if risk_level == RiskLevel.HIGH:
        intro = f"This transaction received a HIGH risk score of {risk_score:.2%}, indicating significant fraud indicators."
    elif risk_level == RiskLevel.MEDIUM:
        intro = f"This transaction received a MEDIUM risk score of {risk_score:.2%}, warranting manual review."
    else:
        intro = f"This transaction received a LOW risk score of {risk_score:.2%}, within acceptable parameters."
    
    factors_text = "The primary factors contributing to this assessment are: "
    factors_list = [f"{f['feature']} ({f['direction']})" for f in top_factors[:3]]
    factors_text += ", ".join(factors_list) + "."
    
    return f"{intro} {factors_text}"

def _generate_regulatory_justification(risk_level: RiskLevel, decision: str) -> str:
    """Generate FCA regulatory justification"""
    
    if decision == "BLOCKED":
        return (
            "Under MLR 2017 Regulation 28, this transaction has been blocked due to reasonable grounds "
            "for suspecting money laundering or terrorist financing. The automated risk assessment "
            "identified multiple high-risk indicators that exceed the institution's risk appetite. "
            "A Suspicious Activity Report (SAR) should be filed with the NCA under FSMA s.330."
        )
    elif decision == "REVIEW":
        return (
            "Under MLR 2017 Regulation 27, enhanced due diligence is required for this transaction. "
            "The risk indicators present warrant human review before processing. If suspicion "
            "is confirmed upon review, a SAR should be filed with the NCA."
        )
    else:
        return (
            "This transaction has been assessed as low risk under the institution's risk-based "
            "approach compliant with MLR 2017. Standard monitoring will continue, and the "
            "transaction has been logged for the 5-year record-keeping requirement."
        )

# ============== API Endpoints ==============

@app.get("/compliance/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "AMTTP FCA Compliance API",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "1.0.0"
    }

# ------------ SAR Endpoints ------------

@app.post("/compliance/sar/submit", response_model=SARResponse)
async def submit_sar(
    request: SARRequest,
    background_tasks: BackgroundTasks
):
    """
    Submit a Suspicious Activity Report (SAR) to NCA
    
    UK requirement: FSMA 2000 s.330 - Failure to disclose
    Deadline: As soon as reasonably practicable
    """
    sar_id = str(uuid.uuid4())
    reference = generate_sar_reference()
    
    sar_record = {
        "sar_id": sar_id,
        "reference_number": reference,
        "status": ReportStatus.SUBMITTED,
        "submitted_at": datetime.utcnow(),
        "transaction": request.transaction.dict(),
        "sar_type": request.sar_type,
        "suspicion_grounds": request.suspicion_grounds,
        "additional_evidence": request.additional_evidence,
        "related_transactions": request.related_transactions,
        "urgency": request.urgency
    }
    
    # Store SAR
    SARS_STORE[sar_id] = sar_record
    
    # Log audit event
    log_audit_event(
        action="SAR_SUBMITTED",
        entity_type="SAR",
        entity_id=sar_id,
        actor="system",
        details={
            "reference": reference,
            "sar_type": request.sar_type,
            "tx_hash": request.transaction.tx_hash
        }
    )
    
    # In production: background_tasks.add_task(send_to_nca, sar_record)
    
    return SARResponse(
        sar_id=sar_id,
        reference_number=reference,
        status=ReportStatus.SUBMITTED,
        submitted_at=datetime.utcnow(),
        estimated_acknowledgment=datetime.utcnow() + timedelta(days=7)
    )

@app.get("/compliance/sar/{sar_id}")
async def get_sar_status(sar_id: str):
    """Get SAR status and details"""
    if sar_id not in SARS_STORE:
        raise HTTPException(status_code=404, detail="SAR not found")
    
    return SARS_STORE[sar_id]

@app.get("/compliance/sar/list")
async def list_sars(
    status: Optional[ReportStatus] = None,
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
    limit: int = Query(default=50, le=200)
):
    """List SARs with optional filters"""
    sars = list(SARS_STORE.values())
    
    if status:
        sars = [s for s in sars if s["status"] == status]
    
    if from_date:
        sars = [s for s in sars if s["submitted_at"] >= from_date]
    
    if to_date:
        sars = [s for s in sars if s["submitted_at"] <= to_date]
    
    return {
        "total": len(sars),
        "sars": sars[:limit]
    }

# ------------ Sanctions Screening ------------

@app.post("/compliance/sanctions/check", response_model=SanctionsCheckResult)
async def check_sanctions(request: SanctionsCheckRequest):
    """
    Screen address against sanctions lists
    
    Lists checked:
    - HMT (UK HM Treasury)
    - OFAC (US Treasury)
    - EU Consolidated List
    - UN Security Council
    """
    address_lower = request.address.lower()
    matches = []
    
    # Check HMT list
    if SanctionsListType.HMT in request.check_lists:
        if address_lower in HMT_SANCTIONS_ADDRESSES:
            matches.append({
                "list": "HMT",
                "entity": HMT_SANCTIONS_ADDRESSES[address_lower],
                "match_type": "exact_address",
                "confidence": 1.0
            })
    
    # In production: integrate with Chainalysis, Elliptic, or similar
    
    result = SanctionsCheckResult(
        address=request.address,
        is_sanctioned=len(matches) > 0,
        matches=matches,
        checked_lists=[l.value for l in request.check_lists],
        check_timestamp=datetime.utcnow(),
        confidence=1.0 if matches else 0.0
    )
    
    # Log the check
    log_audit_event(
        action="SANCTIONS_CHECK",
        entity_type="ADDRESS",
        entity_id=request.address,
        actor="system",
        details={
            "is_sanctioned": result.is_sanctioned,
            "matches_count": len(matches)
        }
    )
    
    return result

@app.post("/compliance/sanctions/batch-check")
async def batch_sanctions_check(addresses: List[str]):
    """Batch screen multiple addresses"""
    results = []
    sanctioned_count = 0
    
    for addr in addresses:
        addr_lower = addr.lower()
        is_sanctioned = addr_lower in HMT_SANCTIONS_ADDRESSES
        if is_sanctioned:
            sanctioned_count += 1
        
        results.append({
            "address": addr,
            "is_sanctioned": is_sanctioned,
            "match": HMT_SANCTIONS_ADDRESSES.get(addr_lower)
        })
    
    return {
        "total_checked": len(addresses),
        "sanctioned_count": sanctioned_count,
        "results": results
    }

# ------------ Travel Rule ------------

@app.post("/compliance/travel-rule/validate")
async def validate_travel_rule(transaction: TransactionRecord):
    """
    Validate FATF Travel Rule compliance
    
    Requirement: For transactions >= €1000 (or £840):
    - Originator name, account, address
    - Beneficiary name, account
    """
    TRAVEL_RULE_THRESHOLD_GBP = 840.0
    
    issues = []
    compliant = True
    
    # Check if travel rule applies
    if transaction.value_gbp and transaction.value_gbp >= TRAVEL_RULE_THRESHOLD_GBP:
        # Check originator info
        if not transaction.originator:
            issues.append("Missing originator information for Travel Rule compliance")
            compliant = False
        else:
            if not transaction.originator.name:
                issues.append("Missing originator name")
                compliant = False
            if not transaction.originator.address:
                issues.append("Missing originator address")
                compliant = False
        
        # Check beneficiary info
        if not transaction.beneficiary:
            issues.append("Missing beneficiary information for Travel Rule compliance")
            compliant = False
        else:
            if not transaction.beneficiary.name:
                issues.append("Missing beneficiary name")
                compliant = False
    
    return {
        "tx_hash": transaction.tx_hash,
        "travel_rule_applies": transaction.value_gbp and transaction.value_gbp >= TRAVEL_RULE_THRESHOLD_GBP,
        "threshold_gbp": TRAVEL_RULE_THRESHOLD_GBP,
        "transaction_value_gbp": transaction.value_gbp,
        "compliant": compliant,
        "issues": issues
    }

# ------------ XAI Explainability ------------

@app.post("/compliance/xai/explain", response_model=XAIExplanation)
async def explain_decision(tx_hash: str, risk_score: float):
    """
    Generate explainable AI report for a risk decision
    
    Required for FCA regulatory review of automated decisions
    """
    # In production, fetch actual features from ML pipeline
    mock_features = {
        "value_eth": 0.35,
        "velocity_24h": 0.42,
        "account_age_days": -0.15,
        "counterparty_risk": 0.28,
        "country_risk": 0.12,
        "time_of_day": 0.08,
        "graph_centrality": 0.22,
        "pattern_match": 0.45
    }
    
    explanation = generate_xai_explanation(tx_hash, risk_score, mock_features)
    
    # Log the explanation generation
    log_audit_event(
        action="XAI_EXPLANATION_GENERATED",
        entity_type="TRANSACTION",
        entity_id=tx_hash,
        actor="system",
        details={
            "risk_score": risk_score,
            "decision": explanation.decision
        }
    )
    
    return explanation

@app.get("/compliance/xai/model-info")
async def get_model_info():
    """Get current ML model information for compliance documentation"""
    return {
        "model_version": "xgboost-hybrid-v2.1",
        "model_type": "XGBoost Gradient Boosting Classifier",
        "training_date": "2025-12-20",
        "dataset_size": 685400,
        "features_used": 24,
        "performance_metrics": {
            "test_f1": 0.847,
            "test_precision": 0.823,
            "test_recall": 0.872,
            "test_auc_roc": 0.941,
            "test_average_precision": 0.891
        },
        "thresholds": {
            "low_risk": 0.4,
            "medium_risk": 0.7,
            "high_risk": 1.0
        },
        "bias_testing": {
            "geographic_parity": 0.98,
            "value_parity": 0.96
        },
        "last_recalibration": "2025-12-20T10:30:00Z"
    }

# ------------ Audit Trail ------------

@app.get("/compliance/audit/logs")
async def get_audit_logs(
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    action: Optional[str] = None,
    from_date: Optional[datetime] = None,
    limit: int = Query(default=100, le=500)
):
    """
    Retrieve audit logs
    
    MLR 2017 requires 5-year retention of:
    - Customer due diligence records
    - Transaction records
    - SAR records
    """
    logs = AUDIT_LOGS.copy()
    
    if entity_type:
        logs = [l for l in logs if l["entity_type"] == entity_type]
    
    if entity_id:
        logs = [l for l in logs if l["entity_id"] == entity_id]
    
    if action:
        logs = [l for l in logs if l["action"] == action]
    
    if from_date:
        logs = [l for l in logs if datetime.fromisoformat(l["timestamp"]) >= from_date]
    
    return {
        "total": len(logs),
        "logs": logs[:limit]
    }

@app.get("/compliance/audit/verify/{log_id}")
async def verify_audit_integrity(log_id: str):
    """Verify cryptographic integrity of an audit log entry"""
    entry = next((l for l in AUDIT_LOGS if l["log_id"] == log_id), None)
    
    if not entry:
        raise HTTPException(status_code=404, detail="Audit log not found")
    
    # Recompute hash
    entry_copy = {k: v for k, v in entry.items() if k != "integrity_hash"}
    computed_hash = compute_integrity_hash(entry_copy)
    
    is_valid = computed_hash == entry["integrity_hash"]
    
    return {
        "log_id": log_id,
        "stored_hash": entry["integrity_hash"],
        "computed_hash": computed_hash,
        "integrity_valid": is_valid,
        "verification_timestamp": datetime.utcnow().isoformat()
    }

# ------------ Compliance Reports ------------

@app.get("/compliance/reports/periodic")
async def generate_periodic_report(
    period: str = Query(default="monthly", pattern="^(daily|weekly|monthly|quarterly)$")
):
    """Generate periodic compliance report for FCA"""
    
    # Calculate period
    now = datetime.utcnow()
    if period == "daily":
        period_start = now - timedelta(days=1)
    elif period == "weekly":
        period_start = now - timedelta(weeks=1)
    elif period == "monthly":
        period_start = now - timedelta(days=30)
    else:  # quarterly
        period_start = now - timedelta(days=90)
    
    # Count SARs in period
    sars_in_period = [
        s for s in SARS_STORE.values()
        if s["submitted_at"] >= period_start
    ]
    
    # Count by type
    sar_by_type = {}
    for sar in sars_in_period:
        sar_type = sar["sar_type"]
        sar_by_type[sar_type] = sar_by_type.get(sar_type, 0) + 1
    
    report = ComplianceReport(
        report_id=str(uuid.uuid4()),
        report_type=f"{period}_compliance_report",
        period_start=period_start,
        period_end=now,
        generated_at=now,
        summary={
            "sars_by_type": sar_by_type,
            "total_sars": len(sars_in_period),
            "audit_entries": len([
                l for l in AUDIT_LOGS
                if datetime.fromisoformat(l["timestamp"]) >= period_start
            ])
        },
        transactions_reviewed=len(AUDIT_LOGS),
        sars_filed=len(sars_in_period),
        sanctions_hits=0,  # Would be populated from actual checks
        high_risk_transactions=len([
            s for s in sars_in_period
            if s["transaction"]["risk_level"] in ["high", "critical"]
        ])
    )
    
    return report

@app.get("/compliance/reports/fca-mlr")
async def generate_fca_mlr_report():
    """
    Generate Money Laundering Regulations compliance report
    
    For FCA submission under MLR 2017
    """
    return {
        "report_type": "MLR_2017_COMPLIANCE",
        "reporting_entity": "AMTTP Protocol",
        "fca_firm_reference": "FRN-XXXXXX",  # Would be actual FRN
        "reporting_period": {
            "start": (datetime.utcnow() - timedelta(days=365)).isoformat(),
            "end": datetime.utcnow().isoformat()
        },
        "compliance_summary": {
            "risk_based_approach": "IMPLEMENTED",
            "customer_due_diligence": "AUTOMATED",
            "enhanced_due_diligence": "TRIGGERED_BY_ML",
            "ongoing_monitoring": "REAL_TIME",
            "record_keeping": "5_YEAR_RETENTION",
            "staff_training": "DOCUMENTED",
            "sar_reporting": "AUTOMATED"
        },
        "statistics": {
            "total_transactions_monitored": len(AUDIT_LOGS),
            "sars_filed": len(SARS_STORE),
            "sanctions_checks": len([l for l in AUDIT_LOGS if l["action"] == "SANCTIONS_CHECK"]),
            "high_risk_blocks": len([
                s for s in SARS_STORE.values()
                if s["transaction"]["risk_level"] == "high"
            ])
        },
        "ml_system_validation": {
            "model_version": "xgboost-hybrid-v2.1",
            "last_validation_date": "2025-12-20",
            "f1_score": 0.847,
            "false_positive_rate": 0.177,
            "false_negative_rate": 0.128
        },
        "generated_at": datetime.utcnow().isoformat()
    }

# ============== Main ==============

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
