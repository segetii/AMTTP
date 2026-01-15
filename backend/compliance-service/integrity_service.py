"""
AMTTP UI Integrity Verification Service

Server-side verification to prevent Bybit-style UI manipulation attacks.

This service:
1. Stores known-good UI component hashes
2. Verifies integrity reports from clients
3. Validates transaction intents against displayed data
4. Logs integrity violations for security review
"""

import os
import json
import hashlib
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, List, Any
from pathlib import Path
from dataclasses import dataclass, asdict

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# ═══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════

DATA_DIR = Path(__file__).parent / "data" / "integrity"
HASHES_FILE = DATA_DIR / "trusted_hashes.json"
VIOLATIONS_FILE = DATA_DIR / "violations.jsonl"

INTEGRITY_VERSION = "1.0.0"

logging.basicConfig(
    level=logging.INFO,
    format='{"timestamp":"%(asctime)s","level":"%(levelname)s","service":"integrity","message":"%(message)s"}'
)
logger = logging.getLogger("integrity")

# ═══════════════════════════════════════════════════════════════════════════════
# MODELS
# ═══════════════════════════════════════════════════════════════════════════════

class PageIntegrity(BaseModel):
    pageHash: str
    scriptsHash: str
    stylesHash: str
    formsHash: str
    buttonsHash: str
    combinedHash: str
    timestamp: int
    warnings: List[str]

class ComponentIntegrity(BaseModel):
    componentId: str
    sourceHash: str
    domHash: str
    eventHandlersHash: str
    combinedHash: str
    verified: bool
    timestamp: int

class MutationAlert(BaseModel):
    type: str
    severity: str
    element: str
    details: str
    timestamp: int

class IntegrityReport(BaseModel):
    version: str
    pageIntegrity: PageIntegrity
    componentIntegrity: List[ComponentIntegrity]
    mutationAlerts: List[MutationAlert]
    isCompromised: bool
    riskLevel: str
    timestamp: int

class TransactionIntent(BaseModel):
    type: str
    fromAddress: str
    toAddress: str
    valueWei: str
    valueEth: str
    chainId: int
    networkName: str
    tokenAddress: Optional[str] = None
    tokenSymbol: Optional[str] = None
    tokenDecimals: Optional[int] = None
    contractMethod: Optional[str] = None
    contractArgs: Optional[List[Any]] = None
    timestamp: int
    nonce: int
    userAgent: str
    uiComponentHash: str
    displayedDataHash: str

class PaymentSubmission(BaseModel):
    intent: TransactionIntent
    intentHash: str
    signature: str
    integrityReport: IntegrityReport

class VerifyIntegrityRequest(BaseModel):
    report: IntegrityReport

class VerifyIntegrityResponse(BaseModel):
    valid: bool
    serverHash: str
    message: str
    riskLevel: str = "unknown"

# ═══════════════════════════════════════════════════════════════════════════════
# TRUSTED HASH STORE
# ═══════════════════════════════════════════════════════════════════════════════

class TrustedHashStore:
    """Store and manage trusted UI component hashes"""
    
    def __init__(self):
        self.hashes: Dict[str, Dict[str, Any]] = {}
        self.load()
    
    def load(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        if HASHES_FILE.exists():
            try:
                with open(HASHES_FILE, 'r', encoding='utf-8') as f:
                    self.hashes = json.load(f)
                logger.info("Loaded %d trusted hashes", len(self.hashes))
            except Exception as e:
                logger.error("Failed to load trusted hashes: %s", e)
    
    def save(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(HASHES_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.hashes, f, indent=2)
    
    def register_hash(self, component_id: str, hash_value: str, 
                      version: str, deployed_at: str):
        """Register a new trusted hash for a component"""
        self.hashes[component_id] = {
            "hash": hash_value,
            "version": version,
            "deployed_at": deployed_at,
            "registered_at": datetime.now(timezone.utc).isoformat()
        }
        self.save()
        logger.info("Registered hash for %s: %s", component_id, hash_value[:16])
    
    def verify_hash(self, component_id: str, hash_value: str) -> bool:
        """Verify if a hash matches the trusted hash for a component"""
        if component_id not in self.hashes:
            # Unknown component - suspicious but not necessarily compromised
            logger.warning("Unknown component: %s", component_id)
            return True  # Allow for new components, but flag for review
        
        trusted = self.hashes[component_id]["hash"]
        return trusted == hash_value
    
    def get_trusted_hash(self, component_id: str) -> Optional[str]:
        if component_id in self.hashes:
            return self.hashes[component_id]["hash"]
        return None

hash_store = TrustedHashStore()

# ═══════════════════════════════════════════════════════════════════════════════
# VIOLATION LOGGER
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class IntegrityViolation:
    timestamp: str
    client_ip: str
    user_agent: str
    violation_type: str
    severity: str
    details: Dict[str, Any]
    report_hash: str

def log_violation(request: Request, violation_type: str, severity: str, 
                  details: Dict[str, Any], report: IntegrityReport):
    """Log an integrity violation for security review"""
    violation = IntegrityViolation(
        timestamp=datetime.now(timezone.utc).isoformat(),
        client_ip=request.client.host if request.client else "unknown",
        user_agent=request.headers.get("user-agent", "unknown"),
        violation_type=violation_type,
        severity=severity,
        details=details,
        report_hash=hashlib.sha256(
            json.dumps(report.model_dump(), sort_keys=True).encode()
        ).hexdigest()
    )
    
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(VIOLATIONS_FILE, 'a', encoding='utf-8') as f:
        f.write(json.dumps(asdict(violation)) + "\n")
    
    logger.warning("Integrity violation: %s - %s", violation_type, severity)

# ═══════════════════════════════════════════════════════════════════════════════
# VERIFICATION LOGIC
# ═══════════════════════════════════════════════════════════════════════════════

def compute_intent_hash(intent: TransactionIntent) -> str:
    """Compute the expected intent hash server-side"""
    canonical = {
        "v": INTEGRITY_VERSION,
        "type": intent.type,
        "from": intent.fromAddress.lower(),
        "to": intent.toAddress.lower(),
        "value": intent.valueWei,
        "chain": intent.chainId,
        "token": intent.tokenAddress.lower() if intent.tokenAddress else None,
        "method": intent.contractMethod,
        "ts": intent.timestamp,
        "nonce": intent.nonce,
        "uiHash": intent.uiComponentHash,
        "dataHash": intent.displayedDataHash,
    }
    
    sorted_json = json.dumps(canonical, sort_keys=True)
    return hashlib.sha256(sorted_json.encode()).hexdigest()

def verify_integrity_report(report: IntegrityReport, request: Request) -> VerifyIntegrityResponse:
    """Verify an integrity report from the client"""
    
    # 1. Check version compatibility
    if report.version != INTEGRITY_VERSION:
        log_violation(request, "version_mismatch", "medium", 
                      {"client_version": report.version}, report)
        return VerifyIntegrityResponse(
            valid=False,
            serverHash="",
            message=f"Version mismatch: expected {INTEGRITY_VERSION}",
            riskLevel="suspicious"
        )
    
    # 2. Check for mutation alerts
    critical_alerts = [a for a in report.mutationAlerts if a.severity == "critical"]
    if critical_alerts:
        log_violation(request, "critical_mutation", "critical",
                      {"alerts": [a.model_dump() for a in critical_alerts]}, report)
        return VerifyIntegrityResponse(
            valid=False,
            serverHash="",
            message="Critical mutations detected",
            riskLevel="compromised"
        )
    
    # 3. Check for dangerous patterns in page integrity
    if any("eval" in w.lower() for w in report.pageIntegrity.warnings):
        log_violation(request, "dangerous_script", "critical",
                      {"warnings": report.pageIntegrity.warnings}, report)
        return VerifyIntegrityResponse(
            valid=False,
            serverHash="",
            message="Dangerous script patterns detected",
            riskLevel="compromised"
        )
    
    # 4. Verify component hashes against trusted store
    for component in report.componentIntegrity:
        trusted_hash = hash_store.get_trusted_hash(component.componentId)
        if trusted_hash and trusted_hash != component.combinedHash:
            log_violation(request, "hash_mismatch", "high", {
                "component": component.componentId,
                "expected": trusted_hash[:16],
                "received": component.combinedHash[:16]
            }, report)
            return VerifyIntegrityResponse(
                valid=False,
                serverHash=trusted_hash,
                message=f"Component hash mismatch: {component.componentId}",
                riskLevel="compromised"
            )
    
    # 5. Check timestamp freshness (prevent replay)
    now = datetime.now(timezone.utc).timestamp() * 1000
    age_ms = now - report.timestamp
    if age_ms > 60000:  # More than 1 minute old
        log_violation(request, "stale_report", "low",
                      {"age_ms": age_ms}, report)
        return VerifyIntegrityResponse(
            valid=False,
            serverHash="",
            message="Integrity report is stale",
            riskLevel="suspicious"
        )
    
    # 6. Compute server-side hash for comparison
    server_hash = hashlib.sha256(
        report.pageIntegrity.combinedHash.encode()
    ).hexdigest()
    
    # Determine risk level
    risk_level = "safe"
    if report.pageIntegrity.warnings:
        risk_level = "suspicious"
    if report.isCompromised:
        risk_level = "compromised"
    
    return VerifyIntegrityResponse(
        valid=True,
        serverHash=server_hash,
        message="Integrity verified",
        riskLevel=risk_level
    )

# ═══════════════════════════════════════════════════════════════════════════════
# FASTAPI APPLICATION
# ═══════════════════════════════════════════════════════════════════════════════

app = FastAPI(
    title="AMTTP UI Integrity Service",
    description="Server-side verification for UI integrity and transaction intent",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "service": "integrity",
        "version": INTEGRITY_VERSION,
        "trusted_hashes": len(hash_store.hashes)
    }

@app.post("/verify-integrity", response_model=VerifyIntegrityResponse)
async def verify_integrity(report: IntegrityReport, request: Request):
    """Verify UI integrity report from client"""
    return verify_integrity_report(report, request)

@app.post("/submit-payment")
async def submit_payment(submission: PaymentSubmission, request: Request):
    """Submit a payment with integrity verification"""
    
    # 1. Verify integrity report
    integrity_result = verify_integrity_report(submission.integrityReport, request)
    if not integrity_result.valid:
        raise HTTPException(
            status_code=400,
            detail=f"Integrity check failed: {integrity_result.message}"
        )
    
    # 2. Verify intent hash matches
    computed_hash = compute_intent_hash(submission.intent)
    if computed_hash != submission.intentHash:
        log_violation(request, "intent_hash_mismatch", "critical", {
            "computed": computed_hash[:16],
            "submitted": submission.intentHash[:16]
        }, submission.integrityReport)
        raise HTTPException(
            status_code=400,
            detail="Intent hash mismatch - possible tampering"
        )
    
    # 3. Verify signature (simplified - in production use proper ECDSA)
    if not submission.signature or len(submission.signature) < 100:
        raise HTTPException(
            status_code=400,
            detail="Invalid signature"
        )
    
    # 4. Additional validation
    # - Check sender has permission
    # - Check recipient not sanctioned
    # - Check value within limits
    # (These would call the orchestrator)
    
    # 5. Log the verified transaction
    logger.info("Payment submitted: %s -> %s, %s ETH",
                submission.intent.fromAddress[:10],
                submission.intent.toAddress[:10],
                submission.intent.valueEth)
    
    # 6. Return success (in production, submit to blockchain)
    return {
        "status": "submitted",
        "txHash": f"0x{'0' * 64}",  # Placeholder
        "intentHash": submission.intentHash,
        "verified": True
    }

@app.post("/register-hash")
async def register_hash(
    component_id: str,
    hash_value: str,
    version: str,
    admin_key: str
):
    """Register a new trusted component hash (admin only)"""
    # In production, verify admin_key against secure store
    expected_key = os.getenv("INTEGRITY_ADMIN_KEY", "dev-key")
    if admin_key != expected_key:
        raise HTTPException(status_code=403, detail="Invalid admin key")
    
    hash_store.register_hash(
        component_id,
        hash_value,
        version,
        datetime.now(timezone.utc).isoformat()
    )
    
    return {"status": "registered", "component": component_id}

@app.get("/violations")
async def get_violations(limit: int = 100, admin_key: str = ""):
    """Get recent integrity violations (admin only)"""
    expected_key = os.getenv("INTEGRITY_ADMIN_KEY", "dev-key")
    if admin_key != expected_key:
        raise HTTPException(status_code=403, detail="Invalid admin key")
    
    violations = []
    if VIOLATIONS_FILE.exists():
        with open(VIOLATIONS_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    violations.append(json.loads(line))
    
    # Return most recent first
    return violations[-limit:][::-1]

# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn
    print("=" * 60)
    print("       AMTTP UI Integrity Service")
    print("=" * 60)
    print(f"[CONFIG] Trusted hashes loaded: {len(hash_store.hashes)}")
    print("=" * 60)
    uvicorn.run(app, host="0.0.0.0", port=8008)
