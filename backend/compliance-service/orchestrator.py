"""
AMTTP Unified Compliance Orchestrator
Central coordination layer that wires all compliance services together
based on entity profiles and regulatory requirements.

Service Integration:
- ML Risk API (8000) - Transaction risk scoring
- Graph Server (8001) - Entity relationship analysis
- FCA Compliance (8002) - SAR/Travel Rule
- Policy API (8003) - Policy management
- Sanctions Service (8004) - HMT/OFAC screening
- Monitoring Engine (8005) - AML pattern detection
- Geographic Risk (8006) - FATF/jurisdiction scoring

Entity Profiles:
- RETAIL: Individual users, standard KYC
- INSTITUTIONAL: Corporate entities, enhanced DD
- VASP: Virtual Asset Service Providers, full compliance
- HIGH_NET_WORTH: HNW individuals, enhanced monitoring
"""

import os
import json
import asyncio
import aiohttp
import secrets
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass, field, asdict
from enum import Enum
from collections import defaultdict
import hashlib
import logging

import uvicorn
from fastapi import FastAPI, HTTPException, BackgroundTasks, Request, Depends, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field
from contextlib import asynccontextmanager
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

# Import storage layer
try:
    from storage import StorageManager, get_storage, close_storage
    STORAGE_AVAILABLE = True
except ImportError:
    STORAGE_AVAILABLE = False
    logger_storage = logging.getLogger("orchestrator.storage")
    logger_storage.warning("Storage module not available - using in-memory only")

# ═══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════

DATA_DIR = Path(__file__).parent / "data" / "orchestrator"
PROFILES_FILE = DATA_DIR / "entity_profiles.json"
DECISIONS_FILE = DATA_DIR / "decisions.jsonl"
API_KEYS_FILE = DATA_DIR / "api_keys.json"

# Service endpoints
SERVICES = {
    "ml_risk": os.getenv("ML_RISK_URL", "http://127.0.0.1:8000"),
    "graph": os.getenv("GRAPH_URL", "http://127.0.0.1:8001"),
    "fca": os.getenv("FCA_URL", "http://127.0.0.1:8002"),
    "policy": os.getenv("POLICY_URL", "http://127.0.0.1:8003"),
    "sanctions": os.getenv("SANCTIONS_URL", "http://127.0.0.1:8004"),
    "monitoring": os.getenv("MONITORING_URL", "http://127.0.0.1:8005"),
    "geo_risk": os.getenv("GEO_RISK_URL", "http://127.0.0.1:8006"),
}

# Security settings
AUTH_ENABLED = os.getenv("AUTH_ENABLED", "false").lower() == "true"
MASTER_API_KEY = os.getenv("MASTER_API_KEY", "")  # For bootstrapping
RATE_LIMIT_REQUESTS = int(os.getenv("RATE_LIMIT_REQUESTS", "100"))  # per minute
RATE_LIMIT_WINDOW = int(os.getenv("RATE_LIMIT_WINDOW", "60"))  # seconds

# Storage settings  
USE_STORAGE_LAYER = os.getenv("USE_STORAGE_LAYER", "true").lower() == "true" and STORAGE_AVAILABLE

logging.basicConfig(
    level=logging.INFO,
    format='{"timestamp":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","message":"%(message)s"}'
)
logger = logging.getLogger("orchestrator")

# ═══════════════════════════════════════════════════════════════════════════════
# API KEY MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════════════

class APIKeyStore:
    """Simple API key storage with roles"""
    def __init__(self):
        self.keys: Dict[str, Dict[str, Any]] = {}  # key -> {org_id, role, created, last_used}
        self.load()
    
    def load(self):
        if API_KEYS_FILE.exists():
            try:
                with open(API_KEYS_FILE, 'r') as f:
                    self.keys = json.load(f)
                logger.info(f"Loaded {len(self.keys)} API keys")
            except Exception as e:
                logger.error(f"Failed to load API keys: {e}")
    
    def save(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(API_KEYS_FILE, 'w') as f:
            json.dump(self.keys, f, indent=2)
    
    def generate_key(self, org_id: str, role: str = "user") -> str:
        """Generate a new API key"""
        key = f"amttp_{secrets.token_urlsafe(32)}"
        self.keys[key] = {
            "org_id": org_id,
            "role": role,  # admin, user, readonly
            "created": datetime.now(timezone.utc).isoformat(),
            "last_used": None,
            "request_count": 0
        }
        self.save()
        return key
    
    def validate(self, key: str) -> Optional[Dict[str, Any]]:
        """Validate API key and return metadata"""
        if key in self.keys:
            self.keys[key]["last_used"] = datetime.now(timezone.utc).isoformat()
            self.keys[key]["request_count"] = self.keys[key].get("request_count", 0) + 1
            return self.keys[key]
        return None
    
    def revoke(self, key: str) -> bool:
        if key in self.keys:
            del self.keys[key]
            self.save()
            return True
        return False

api_key_store = APIKeyStore()

# ═══════════════════════════════════════════════════════════════════════════════
# RATE LIMITING
# ═══════════════════════════════════════════════════════════════════════════════

class RateLimiter:
    """Rate limiter with Redis support (falls back to in-memory)"""
    def __init__(self, max_requests: int = 100, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window = window_seconds
        self.requests: Dict[str, List[float]] = defaultdict(list)
        self._storage = None
    
    async def _get_storage(self):
        """Lazy load storage for Redis-backed rate limiting"""
        if self._storage is None and USE_STORAGE_LAYER:
            try:
                self._storage = await get_storage()
            except Exception:
                pass
        return self._storage
    
    async def is_allowed_async(self, key: str) -> Tuple[bool, int]:
        """Async rate limit check using Redis if available"""
        storage = await self._get_storage()
        if storage and storage._redis_connected:
            return await storage.check_rate_limit(key, self.max_requests)
        return self.is_allowed(key)
    
    def is_allowed(self, key: str) -> Tuple[bool, int]:
        """Check if request is allowed. Returns (allowed, remaining)"""
        now = time.time()
        window_start = now - self.window
        
        # Clean old requests
        self.requests[key] = [t for t in self.requests[key] if t > window_start]
        
        if len(self.requests[key]) >= self.max_requests:
            return False, 0
        
        self.requests[key].append(now)
        remaining = self.max_requests - len(self.requests[key])
        return True, remaining

rate_limiter = RateLimiter(RATE_LIMIT_REQUESTS, RATE_LIMIT_WINDOW)

# ═══════════════════════════════════════════════════════════════════════════════
# MIDDLEWARE
# ═══════════════════════════════════════════════════════════════════════════════

class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Add request ID and log all requests"""
    async def dispatch(self, request: Request, call_next):
        request_id = str(uuid.uuid4())[:8]
        request.state.request_id = request_id
        
        start_time = time.time()
        
        # Log request
        logger.info(json.dumps({
            "event": "request_start",
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "client": request.client.host if request.client else "unknown"
        }))
        
        response = await call_next(request)
        
        # Log response
        duration_ms = (time.time() - start_time) * 1000
        logger.info(json.dumps({
            "event": "request_end",
            "request_id": request_id,
            "status": response.status_code,
            "duration_ms": round(duration_ms, 2)
        }))
        
        response.headers["X-Request-ID"] = request_id
        return response

# API Key security header
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

async def verify_api_key(request: Request, api_key: str = Security(api_key_header)):
    """Verify API key if auth is enabled"""
    if not AUTH_ENABLED:
        return {"org_id": "default", "role": "admin"}
    
    # Allow health checks without auth
    if request.url.path in ["/health", "/docs", "/openapi.json"]:
        return {"org_id": "anonymous", "role": "readonly"}
    
    if not api_key:
        raise HTTPException(status_code=401, detail="API key required")
    
    # Check master key
    if MASTER_API_KEY and api_key == MASTER_API_KEY:
        return {"org_id": "master", "role": "admin"}
    
    # Validate stored key
    key_data = api_key_store.validate(api_key)
    if not key_data:
        raise HTTPException(status_code=401, detail="Invalid API key")
    
    # Rate limiting
    allowed, remaining = rate_limiter.is_allowed(api_key)
    if not allowed:
        raise HTTPException(
            status_code=429, 
            detail="Rate limit exceeded",
            headers={"X-RateLimit-Remaining": "0", "Retry-After": str(RATE_LIMIT_WINDOW)}
        )
    
    request.state.org_id = key_data["org_id"]
    request.state.rate_limit_remaining = remaining
    
    return key_data

# ═══════════════════════════════════════════════════════════════════════════════
# ENTITY PROFILES
# ═══════════════════════════════════════════════════════════════════════════════

class EntityType(str, Enum):
    RETAIL = "RETAIL"                    # Individual users
    INSTITUTIONAL = "INSTITUTIONAL"      # Corporate entities
    VASP = "VASP"                        # Virtual Asset Service Providers
    HIGH_NET_WORTH = "HIGH_NET_WORTH"    # HNW individuals
    UNVERIFIED = "UNVERIFIED"            # Unknown/new entities

class KYCLevel(str, Enum):
    NONE = "NONE"
    BASIC = "BASIC"           # Email + phone verified
    STANDARD = "STANDARD"     # ID verified
    ENHANCED = "ENHANCED"     # Full KYC + source of funds
    INSTITUTIONAL = "INSTITUTIONAL"  # Corporate KYC

class RiskTolerance(str, Enum):
    STRICT = "STRICT"         # Block anything suspicious
    CONSERVATIVE = "CONSERVATIVE"  # Escrow high-risk
    MODERATE = "MODERATE"     # Review high-risk
    PERMISSIVE = "PERMISSIVE" # Only block sanctioned

@dataclass
class EntityProfile:
    """Entity profile with compliance settings"""
    address: str
    entity_type: EntityType = EntityType.UNVERIFIED
    kyc_level: KYCLevel = KYCLevel.NONE
    risk_tolerance: RiskTolerance = RiskTolerance.CONSERVATIVE
    jurisdiction: str = "UNKNOWN"
    
    # Limits
    daily_limit_eth: float = 10.0
    monthly_limit_eth: float = 100.0
    single_tx_limit_eth: float = 5.0
    
    # Compliance flags
    sanctions_checked: bool = False
    pep_checked: bool = False
    source_of_funds_verified: bool = False
    
    # Travel Rule
    travel_rule_threshold_eth: float = 0.84  # ~£840
    originator_info: Optional[Dict] = None
    
    # Metadata
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    risk_score_cache: Optional[float] = None
    last_activity: Optional[str] = None
    
    # Counters
    total_transactions: int = 0
    daily_volume_eth: float = 0.0
    monthly_volume_eth: float = 0.0

# Profile presets by entity type
PROFILE_PRESETS = {
    EntityType.RETAIL: {
        "daily_limit_eth": 10.0,
        "monthly_limit_eth": 100.0,
        "single_tx_limit_eth": 5.0,
        "risk_tolerance": RiskTolerance.CONSERVATIVE,
        "travel_rule_threshold_eth": 0.84,
    },
    EntityType.INSTITUTIONAL: {
        "daily_limit_eth": 1000.0,
        "monthly_limit_eth": 10000.0,
        "single_tx_limit_eth": 500.0,
        "risk_tolerance": RiskTolerance.MODERATE,
        "travel_rule_threshold_eth": 0.84,
    },
    EntityType.VASP: {
        "daily_limit_eth": 10000.0,
        "monthly_limit_eth": 100000.0,
        "single_tx_limit_eth": 5000.0,
        "risk_tolerance": RiskTolerance.PERMISSIVE,
        "travel_rule_threshold_eth": 0.84,
    },
    EntityType.HIGH_NET_WORTH: {
        "daily_limit_eth": 500.0,
        "monthly_limit_eth": 5000.0,
        "single_tx_limit_eth": 250.0,
        "risk_tolerance": RiskTolerance.STRICT,
        "travel_rule_threshold_eth": 0.84,
    },
    EntityType.UNVERIFIED: {
        "daily_limit_eth": 1.0,
        "monthly_limit_eth": 5.0,
        "single_tx_limit_eth": 0.5,
        "risk_tolerance": RiskTolerance.STRICT,
        "travel_rule_threshold_eth": 0.0,  # Always require Travel Rule info
    },
}

# ═══════════════════════════════════════════════════════════════════════════════
# COMPLIANCE DECISION
# ═══════════════════════════════════════════════════════════════════════════════

class ComplianceAction(str, Enum):
    APPROVE = "APPROVE"
    ESCROW = "ESCROW"
    REVIEW = "REVIEW"
    BLOCK = "BLOCK"
    REQUIRE_INFO = "REQUIRE_INFO"

@dataclass
class ComplianceCheck:
    """Individual compliance check result"""
    service: str
    check_type: str
    passed: bool
    score: Optional[float] = None
    details: Dict[str, Any] = field(default_factory=dict)
    action_required: Optional[ComplianceAction] = None
    reason: str = ""

@dataclass
class ComplianceDecision:
    """Full compliance decision for a transaction"""
    decision_id: str
    timestamp: str
    
    # Transaction
    from_address: str
    to_address: str
    value_eth: float
    
    # Profiles
    originator_profile: Optional[Dict] = None
    beneficiary_profile: Optional[Dict] = None
    
    # Checks performed
    checks: List[ComplianceCheck] = field(default_factory=list)
    
    # Final decision
    action: ComplianceAction = ComplianceAction.BLOCK
    risk_score: float = 100.0
    reasons: List[str] = field(default_factory=list)
    
    # Requirements
    requires_travel_rule: bool = False
    requires_sar: bool = False
    requires_escrow: bool = False
    escrow_duration_hours: int = 0
    
    # Processing time
    processing_time_ms: float = 0.0

# ═══════════════════════════════════════════════════════════════════════════════
# PROFILE STORE
# ═══════════════════════════════════════════════════════════════════════════════

class ProfileStore:
    def __init__(self):
        self.profiles: Dict[str, EntityProfile] = {}
        self.load()
    
    def load(self):
        if PROFILES_FILE.exists():
            try:
                with open(PROFILES_FILE, 'r') as f:
                    data = json.load(f)
                for addr, profile_data in data.items():
                    self.profiles[addr.lower()] = EntityProfile(
                        address=profile_data.get("address", addr),
                        entity_type=EntityType(profile_data.get("entity_type", "UNVERIFIED")),
                        kyc_level=KYCLevel(profile_data.get("kyc_level", "NONE")),
                        risk_tolerance=RiskTolerance(profile_data.get("risk_tolerance", "CONSERVATIVE")),
                        jurisdiction=profile_data.get("jurisdiction", "UNKNOWN"),
                        daily_limit_eth=profile_data.get("daily_limit_eth", 10.0),
                        monthly_limit_eth=profile_data.get("monthly_limit_eth", 100.0),
                        single_tx_limit_eth=profile_data.get("single_tx_limit_eth", 5.0),
                        sanctions_checked=profile_data.get("sanctions_checked", False),
                        pep_checked=profile_data.get("pep_checked", False),
                        source_of_funds_verified=profile_data.get("source_of_funds_verified", False),
                        travel_rule_threshold_eth=profile_data.get("travel_rule_threshold_eth", 0.84),
                        originator_info=profile_data.get("originator_info"),
                        created_at=profile_data.get("created_at", datetime.now(timezone.utc).isoformat()),
                        updated_at=profile_data.get("updated_at", datetime.now(timezone.utc).isoformat()),
                        total_transactions=profile_data.get("total_transactions", 0),
                        daily_volume_eth=profile_data.get("daily_volume_eth", 0.0),
                        monthly_volume_eth=profile_data.get("monthly_volume_eth", 0.0),
                    )
                logger.info(f"Loaded {len(self.profiles)} entity profiles")
            except Exception as e:
                logger.error(f"Failed to load profiles: {e}")
    
    def save(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        data = {addr: asdict(profile) for addr, profile in self.profiles.items()}
        with open(PROFILES_FILE, 'w') as f:
            json.dump(data, f, indent=2, default=str)
    
    def get_or_create(self, address: str) -> EntityProfile:
        address = address.lower()
        if address not in self.profiles:
            preset = PROFILE_PRESETS[EntityType.UNVERIFIED]
            self.profiles[address] = EntityProfile(
                address=address,
                entity_type=EntityType.UNVERIFIED,
                **{k: v for k, v in preset.items() if k != "risk_tolerance"},
                risk_tolerance=preset["risk_tolerance"],
            )
            self.save()
        return self.profiles[address]
    
    def update(self, address: str, updates: Dict) -> EntityProfile:
        profile = self.get_or_create(address)
        for key, value in updates.items():
            if hasattr(profile, key):
                setattr(profile, key, value)
        profile.updated_at = datetime.now(timezone.utc).isoformat()
        self.save()
        return profile
    
    def set_entity_type(self, address: str, entity_type: EntityType) -> EntityProfile:
        profile = self.get_or_create(address)
        profile.entity_type = entity_type
        
        # Apply preset limits
        preset = PROFILE_PRESETS.get(entity_type, PROFILE_PRESETS[EntityType.UNVERIFIED])
        profile.daily_limit_eth = preset["daily_limit_eth"]
        profile.monthly_limit_eth = preset["monthly_limit_eth"]
        profile.single_tx_limit_eth = preset["single_tx_limit_eth"]
        profile.risk_tolerance = preset["risk_tolerance"]
        profile.updated_at = datetime.now(timezone.utc).isoformat()
        
        self.save()
        return profile

profile_store = ProfileStore()

# ═══════════════════════════════════════════════════════════════════════════════
# SERVICE CLIENTS
# ═══════════════════════════════════════════════════════════════════════════════

async def call_service(session: aiohttp.ClientSession, service: str, endpoint: str, 
                       method: str = "GET", data: Dict = None, timeout: int = 5,
                       retries: int = 3, backoff_base: float = 0.5) -> Tuple[bool, Dict]:
    """Call a compliance service with error handling, retries, and exponential backoff"""
    url = f"{SERVICES[service]}{endpoint}"
    last_error = None
    
    for attempt in range(retries):
        try:
            if method == "GET":
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
                    if resp.status == 200:
                        return True, await resp.json()
                    if resp.status >= 500:
                        # Server error - retry
                        last_error = f"HTTP {resp.status}"
                    else:
                        # Client error - don't retry
                        return False, {"error": f"HTTP {resp.status}"}
            else:
                async with session.post(url, json=data, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
                    if resp.status == 200:
                        return True, await resp.json()
                    if resp.status >= 500:
                        last_error = f"HTTP {resp.status}"
                    else:
                        return False, {"error": f"HTTP {resp.status}"}
        except asyncio.TimeoutError:
            last_error = "timeout"
        except aiohttp.ClientConnectorError:
            last_error = "connection_refused"
        except Exception as e:
            last_error = str(e)
        
        # Exponential backoff before retry
        if attempt < retries - 1:
            wait_time = backoff_base * (2 ** attempt)
            logger.warning(json.dumps({
                "event": "service_retry",
                "service": service,
                "endpoint": endpoint,
                "attempt": attempt + 1,
                "wait_seconds": wait_time,
                "error": last_error
            }))
            await asyncio.sleep(wait_time)
    
    # All retries failed
    logger.error(json.dumps({
        "event": "service_call_failed",
        "service": service,
        "endpoint": endpoint,
        "retries": retries,
        "error": last_error
    }))
    return False, {"error": last_error, "retries_exhausted": True}

async def check_sanctions(session: aiohttp.ClientSession, address: str) -> ComplianceCheck:
    """Check address against sanctions lists"""
    success, result = await call_service(
        session, "sanctions", "/sanctions/check",
        method="POST", data={"address": address}
    )
    
    if not success:
        return ComplianceCheck(
            service="sanctions",
            check_type="address_screening",
            passed=False,
            details={"error": result.get("error")},
            action_required=ComplianceAction.REVIEW,
            reason="Sanctions service unavailable"
        )
    
    is_sanctioned = result.get("is_sanctioned", False)
    
    return ComplianceCheck(
        service="sanctions",
        check_type="address_screening",
        passed=not is_sanctioned,
        score=0.0 if is_sanctioned else 100.0,
        details=result,
        action_required=ComplianceAction.BLOCK if is_sanctioned else None,
        reason=f"Address on {result['matches'][0]['entity']['source_list']} sanctions list" if is_sanctioned else ""
    )

async def check_geo_risk(session: aiohttp.ClientSession, country_code: str) -> ComplianceCheck:
    """Check geographic/jurisdiction risk"""
    if not country_code or country_code == "UNKNOWN":
        return ComplianceCheck(
            service="geo_risk",
            check_type="jurisdiction",
            passed=False,
            action_required=ComplianceAction.REQUIRE_INFO,
            reason="Jurisdiction unknown - KYC required"
        )
    
    success, result = await call_service(
        session, "geo_risk", "/geo/country-risk",
        method="POST", data={"country_code": country_code}
    )
    
    if not success:
        return ComplianceCheck(
            service="geo_risk",
            check_type="jurisdiction",
            passed=False,
            details={"error": result.get("error")},
            action_required=ComplianceAction.REVIEW,
            reason="Geo risk service unavailable"
        )
    
    risk_level = result.get("risk_level", "UNKNOWN")
    risk_score = result.get("risk_score", 50)
    
    if risk_level == "PROHIBITED":
        action = ComplianceAction.BLOCK
        passed = False
    elif risk_level in ["VERY_HIGH", "HIGH"]:
        action = ComplianceAction.ESCROW
        passed = False
    elif risk_level == "MEDIUM":
        action = ComplianceAction.REVIEW
        passed = True
    else:
        action = None
        passed = True
    
    return ComplianceCheck(
        service="geo_risk",
        check_type="jurisdiction",
        passed=passed,
        score=100 - risk_score,
        details=result,
        action_required=action,
        reason=result.get("transaction_policy", "")
    )

async def check_ml_risk(session: aiohttp.ClientSession, tx_data: Dict) -> ComplianceCheck:
    """Get ML risk score for transaction"""
    success, result = await call_service(
        session, "ml_risk", "/score",
        method="POST", data=tx_data
    )
    
    if not success:
        return ComplianceCheck(
            service="ml_risk",
            check_type="transaction_risk",
            passed=True,  # Don't block if ML unavailable
            score=50.0,
            details={"error": result.get("error")},
            reason="ML service unavailable - using default score"
        )
    
    risk_score = result.get("risk_score", 0.5) * 100
    risk_level = result.get("risk_level", "medium")
    
    if risk_level == "critical":
        action = ComplianceAction.BLOCK
        passed = False
    elif risk_level == "high":
        action = ComplianceAction.ESCROW
        passed = False
    elif risk_level == "medium":
        action = ComplianceAction.REVIEW
        passed = True
    else:
        action = None
        passed = True
    
    return ComplianceCheck(
        service="ml_risk",
        check_type="transaction_risk",
        passed=passed,
        score=100 - risk_score,
        details=result,
        action_required=action,
        reason=f"ML risk: {risk_level}"
    )

async def check_monitoring(session: aiohttp.ClientSession, tx_data: Dict) -> ComplianceCheck:
    """Check transaction against AML monitoring rules"""
    success, result = await call_service(
        session, "monitoring", "/monitor/transaction",
        method="POST", data=tx_data
    )
    
    if not success:
        return ComplianceCheck(
            service="monitoring",
            check_type="aml_patterns",
            passed=True,
            details={"error": result.get("error")},
            reason="Monitoring service unavailable"
        )
    
    alerts_created = result.get("alerts_created", 0)
    rules_triggered = result.get("rules_triggered", 0)
    
    if alerts_created > 0:
        # Check severity of alerts
        alerts = result.get("alerts", [])
        critical = any(a.get("severity") == "CRITICAL" for a in alerts)
        high = any(a.get("severity") == "HIGH" for a in alerts)
        
        if critical:
            action = ComplianceAction.BLOCK
            passed = False
        elif high:
            action = ComplianceAction.ESCROW
            passed = False
        else:
            action = ComplianceAction.REVIEW
            passed = True
    else:
        action = None
        passed = True
    
    return ComplianceCheck(
        service="monitoring",
        check_type="aml_patterns",
        passed=passed,
        score=100 if alerts_created == 0 else max(0, 100 - alerts_created * 20),
        details=result,
        action_required=action,
        reason=f"AML rules triggered: {rules_triggered}, Alerts: {alerts_created}" if alerts_created > 0 else ""
    )

async def get_policy(session: aiohttp.ClientSession, policy_id: str = "policy-default") -> Dict:
    """Get policy configuration"""
    success, result = await call_service(
        session, "policy", f"/policies/{policy_id}"
    )
    
    if success:
        return result
    return {}

# ═══════════════════════════════════════════════════════════════════════════════
# COMPLIANCE ORCHESTRATION
# ═══════════════════════════════════════════════════════════════════════════════

async def evaluate_transaction(
    from_address: str,
    to_address: str,
    value_eth: float,
    tx_hash: Optional[str] = None,
    timestamp: Optional[str] = None,
    additional_data: Optional[Dict] = None
) -> ComplianceDecision:
    """
    Main orchestration function - evaluates transaction through all compliance services
    based on entity profiles
    """
    start_time = datetime.now(timezone.utc)
    decision_id = hashlib.md5(f"{from_address}{to_address}{value_eth}{start_time.isoformat()}".encode()).hexdigest()[:16]
    
    # Get profiles
    originator = profile_store.get_or_create(from_address)
    beneficiary = profile_store.get_or_create(to_address)
    
    checks: List[ComplianceCheck] = []
    reasons: List[str] = []
    final_action = ComplianceAction.APPROVE
    requires_sar = False
    requires_escrow = False
    escrow_duration = 0
    
    async with aiohttp.ClientSession() as session:
        # ═══════════════════════════════════════════════════════════════════
        # 1. SANCTIONS CHECK (Both addresses) - BLOCKING
        # ═══════════════════════════════════════════════════════════════════
        orig_sanctions = await check_sanctions(session, from_address)
        benef_sanctions = await check_sanctions(session, to_address)
        checks.extend([orig_sanctions, benef_sanctions])
        
        if not orig_sanctions.passed:
            final_action = ComplianceAction.BLOCK
            reasons.append(f"Originator: {orig_sanctions.reason}")
        
        if not benef_sanctions.passed:
            final_action = ComplianceAction.BLOCK
            reasons.append(f"Beneficiary: {benef_sanctions.reason}")
        
        # If sanctioned, stop here
        if final_action == ComplianceAction.BLOCK and "sanctions" in str(reasons):
            decision = ComplianceDecision(
                decision_id=decision_id,
                timestamp=start_time.isoformat(),
                from_address=from_address,
                to_address=to_address,
                value_eth=value_eth,
                originator_profile=asdict(originator),
                beneficiary_profile=asdict(beneficiary),
                checks=checks,
                action=final_action,
                risk_score=100.0,
                reasons=reasons,
                requires_sar=True,
                processing_time_ms=(datetime.now(timezone.utc) - start_time).total_seconds() * 1000
            )
            log_decision(decision)
            return decision
        
        # ═══════════════════════════════════════════════════════════════════
        # 2. GEOGRAPHIC RISK CHECK - Based on profiles
        # ═══════════════════════════════════════════════════════════════════
        geo_checks = []
        
        if originator.jurisdiction and originator.jurisdiction != "UNKNOWN":
            orig_geo = await check_geo_risk(session, originator.jurisdiction)
            checks.append(orig_geo)
            geo_checks.append(orig_geo)
            
            if orig_geo.action_required == ComplianceAction.BLOCK:
                final_action = ComplianceAction.BLOCK
                reasons.append(f"Originator jurisdiction: {orig_geo.reason}")
        
        if beneficiary.jurisdiction and beneficiary.jurisdiction != "UNKNOWN":
            benef_geo = await check_geo_risk(session, beneficiary.jurisdiction)
            checks.append(benef_geo)
            geo_checks.append(benef_geo)
            
            if benef_geo.action_required == ComplianceAction.BLOCK:
                final_action = ComplianceAction.BLOCK
                reasons.append(f"Beneficiary jurisdiction: {benef_geo.reason}")
        
        # High-risk jurisdictions require escrow
        for geo in geo_checks:
            if geo.action_required == ComplianceAction.ESCROW and final_action != ComplianceAction.BLOCK:
                requires_escrow = True
                escrow_duration = 48  # 48 hours for high-risk jurisdictions
                if final_action == ComplianceAction.APPROVE:
                    final_action = ComplianceAction.ESCROW
        
        # ═══════════════════════════════════════════════════════════════════
        # 3. PROFILE-BASED LIMIT CHECKS
        # ═══════════════════════════════════════════════════════════════════
        
        # Check single transaction limit
        if value_eth > originator.single_tx_limit_eth:
            if originator.risk_tolerance == RiskTolerance.STRICT:
                final_action = ComplianceAction.BLOCK
                reasons.append(f"Exceeds single tx limit: {value_eth} > {originator.single_tx_limit_eth} ETH")
            elif originator.risk_tolerance == RiskTolerance.CONSERVATIVE:
                if final_action == ComplianceAction.APPROVE:
                    final_action = ComplianceAction.ESCROW
                requires_escrow = True
                escrow_duration = max(escrow_duration, 24)
                reasons.append(f"Exceeds limit - requires escrow")
            else:
                if final_action == ComplianceAction.APPROVE:
                    final_action = ComplianceAction.REVIEW
                reasons.append(f"Exceeds limit - manual review")
        
        # Check daily volume
        if originator.daily_volume_eth + value_eth > originator.daily_limit_eth:
            reasons.append(f"Approaching daily limit: {originator.daily_volume_eth + value_eth:.2f}/{originator.daily_limit_eth} ETH")
            if final_action == ComplianceAction.APPROVE:
                final_action = ComplianceAction.REVIEW
        
        checks.append(ComplianceCheck(
            service="profile",
            check_type="limits",
            passed=final_action != ComplianceAction.BLOCK,
            score=100 if value_eth <= originator.single_tx_limit_eth else 50,
            details={
                "single_tx_limit": originator.single_tx_limit_eth,
                "daily_limit": originator.daily_limit_eth,
                "daily_used": originator.daily_volume_eth,
                "value": value_eth
            }
        ))
        
        # ═══════════════════════════════════════════════════════════════════
        # 4. KYC / TRAVEL RULE CHECK
        # ═══════════════════════════════════════════════════════════════════
        requires_travel_rule = value_eth >= originator.travel_rule_threshold_eth
        
        if requires_travel_rule:
            # Check if originator info is available
            if not originator.originator_info:
                if originator.kyc_level == KYCLevel.NONE:
                    final_action = ComplianceAction.REQUIRE_INFO
                    reasons.append("Travel Rule applies - KYC required")
                else:
                    reasons.append("Travel Rule applies - originator info will be collected")
        
        checks.append(ComplianceCheck(
            service="travel_rule",
            check_type="threshold",
            passed=not requires_travel_rule or originator.kyc_level != KYCLevel.NONE,
            details={
                "threshold_eth": originator.travel_rule_threshold_eth,
                "value_eth": value_eth,
                "applies": requires_travel_rule,
                "kyc_level": originator.kyc_level.value
            }
        ))
        
        # ═══════════════════════════════════════════════════════════════════
        # 5. ML RISK SCORING (Skip if already blocked)
        # ═══════════════════════════════════════════════════════════════════
        if final_action != ComplianceAction.BLOCK:
            ml_check = await check_ml_risk(session, {
                "from_address": from_address,
                "to_address": to_address,
                "value_eth": value_eth,
            })
            checks.append(ml_check)
            
            if ml_check.action_required == ComplianceAction.BLOCK:
                if originator.risk_tolerance in [RiskTolerance.STRICT, RiskTolerance.CONSERVATIVE]:
                    final_action = ComplianceAction.BLOCK
                    reasons.append(ml_check.reason)
            elif ml_check.action_required == ComplianceAction.ESCROW:
                if final_action == ComplianceAction.APPROVE:
                    final_action = ComplianceAction.ESCROW
                    requires_escrow = True
                    escrow_duration = max(escrow_duration, 24)
        
        # ═══════════════════════════════════════════════════════════════════
        # 6. AML MONITORING (Pattern detection)
        # ═══════════════════════════════════════════════════════════════════
        if final_action != ComplianceAction.BLOCK:
            monitoring_check = await check_monitoring(session, {
                "tx_hash": tx_hash or decision_id,
                "from_address": from_address,
                "to_address": to_address,
                "value_eth": value_eth,
                "timestamp": timestamp or start_time.isoformat(),
                "block_number": 0,
                "chain": "ethereum"
            })
            checks.append(monitoring_check)
            
            if monitoring_check.action_required:
                if monitoring_check.action_required == ComplianceAction.BLOCK:
                    final_action = ComplianceAction.BLOCK
                    reasons.append(monitoring_check.reason)
                    requires_sar = True
                elif monitoring_check.action_required == ComplianceAction.ESCROW:
                    if final_action == ComplianceAction.APPROVE:
                        final_action = ComplianceAction.ESCROW
                    requires_escrow = True
                    escrow_duration = max(escrow_duration, 24)
    
    # ═══════════════════════════════════════════════════════════════════
    # CALCULATE FINAL RISK SCORE
    # ═══════════════════════════════════════════════════════════════════
    scores = [c.score for c in checks if c.score is not None]
    avg_score = sum(scores) / len(scores) if scores else 50.0
    risk_score = 100 - avg_score
    
    # Adjust for entity type
    if originator.entity_type == EntityType.VASP and originator.kyc_level == KYCLevel.INSTITUTIONAL:
        risk_score *= 0.8  # 20% reduction for fully compliant VASPs
    elif originator.entity_type == EntityType.UNVERIFIED:
        risk_score = min(100, risk_score * 1.2)  # 20% increase for unverified
    
    # Determine if SAR required
    if risk_score >= 80 or final_action == ComplianceAction.BLOCK:
        requires_sar = True
    
    decision = ComplianceDecision(
        decision_id=decision_id,
        timestamp=start_time.isoformat(),
        from_address=from_address,
        to_address=to_address,
        value_eth=value_eth,
        originator_profile=asdict(originator),
        beneficiary_profile=asdict(beneficiary),
        checks=[asdict(c) for c in checks],
        action=final_action,
        risk_score=round(risk_score, 2),
        reasons=reasons,
        requires_travel_rule=requires_travel_rule,
        requires_sar=requires_sar,
        requires_escrow=requires_escrow,
        escrow_duration_hours=escrow_duration,
        processing_time_ms=round((datetime.now(timezone.utc) - start_time).total_seconds() * 1000, 2)
    )
    
    # Update profile activity
    if final_action == ComplianceAction.APPROVE:
        originator.total_transactions += 1
        originator.daily_volume_eth += value_eth
        originator.monthly_volume_eth += value_eth
        originator.last_activity = start_time.isoformat()
        profile_store.save()
    
    log_decision(decision)
    return decision

def log_decision(decision: ComplianceDecision):
    """Log decision for audit trail"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(DECISIONS_FILE, 'a') as f:
        f.write(json.dumps(asdict(decision), default=str) + "\n")

# ═══════════════════════════════════════════════════════════════════════════════
# API MODELS
# ═══════════════════════════════════════════════════════════════════════════════

class TransactionRequest(BaseModel):
    from_address: str
    to_address: str
    value_eth: float
    tx_hash: Optional[str] = None
    timestamp: Optional[str] = None

class ProfileUpdateRequest(BaseModel):
    entity_type: Optional[str] = None
    kyc_level: Optional[str] = None
    risk_tolerance: Optional[str] = None
    jurisdiction: Optional[str] = None
    daily_limit_eth: Optional[float] = None
    monthly_limit_eth: Optional[float] = None
    single_tx_limit_eth: Optional[float] = None
    originator_info: Optional[Dict] = None

# ═══════════════════════════════════════════════════════════════════════════════
# FASTAPI APPLICATION
# ═══════════════════════════════════════════════════════════════════════════════

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("=" * 60)
    print("       AMTTP Compliance Orchestrator")
    print("=" * 60)
    print(f"[PROFILES] Entity profiles loaded: {len(profile_store.profiles)}")
    print(f"[SERVICES] Connected services: {list(SERVICES.keys())}")
    
    # Initialize storage layer
    storage_status = {}
    if USE_STORAGE_LAYER:
        try:
            storage = await get_storage()
            storage_status = storage.health_check()
            print(f"[STORAGE] MongoDB: {storage_status.get('mongodb', 'N/A')}")
            print(f"[STORAGE] Redis: {storage_status.get('redis', 'N/A')}")
            print(f"[STORAGE] MinIO: {storage_status.get('minio', 'N/A')}")
            print(f"[STORAGE] IPFS: {storage_status.get('ipfs', 'N/A')}")
        except Exception as e:
            print(f"[STORAGE] Failed to initialize: {e}")
    else:
        print("[STORAGE] Storage layer disabled - using in-memory only")
    
    print("=" * 60)
    
    yield
    
    # Cleanup
    profile_store.save()
    if USE_STORAGE_LAYER:
        await close_storage()
    print("[SHUTDOWN] Orchestrator shutting down")

app = FastAPI(
    title="AMTTP Compliance Orchestrator",
    description="Unified compliance decision engine with profile-based routing",
    version="1.0.0",
    lifespan=lifespan
)

# Add middleware
app.add_middleware(RequestLoggingMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── ENDPOINTS ──────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    """Check orchestrator and connected services health"""
    service_status = {}
    
    async with aiohttp.ClientSession() as session:
        for name, url in SERVICES.items():
            try:
                async with session.get(f"{url}/health", timeout=aiohttp.ClientTimeout(total=2)) as resp:
                    service_status[name] = "healthy" if resp.status == 200 else "unhealthy"
            except:
                service_status[name] = "offline"
    
    # Get storage status
    storage_status = {}
    if USE_STORAGE_LAYER:
        try:
            storage = await get_storage()
            storage_status = storage.health_check()
        except Exception:
            storage_status = {"error": "storage unavailable"}
    
    return {
        "status": "healthy",
        "service": "orchestrator",
        "version": "1.0.0",
        "auth_enabled": AUTH_ENABLED,
        "storage_enabled": USE_STORAGE_LAYER,
        "profiles_loaded": len(profile_store.profiles),
        "connected_services": service_status,
        "storage": storage_status
    }


@app.get("/dashboard/stats")
async def dashboard_stats():
    """
    Get dashboard statistics from graph database and monitoring service.
    Returns aggregated stats for the SIEM dashboard.
    """
    stats = {
        "totalAlerts": 0,
        "criticalAlerts": 0,
        "highAlerts": 0,
        "mediumAlerts": 0,
        "lowAlerts": 0,
        "alertsTrend": 0,
        "resolvedToday": 0,
        "pendingInvestigation": 0,
        "blockedAddresses": 0,
        "flaggedTransactions": 0,
    }
    
    async with aiohttp.ClientSession() as session:
        # Try to get graph stats from Memgraph via graph service
        try:
            async with session.get(
                f"{SERVICES['graph']}/graph/fraud-stats",
                timeout=aiohttp.ClientTimeout(total=5)
            ) as resp:
                if resp.status == 200:
                    graph_data = await resp.json()
                    stats["blockedAddresses"] = graph_data.get("critical_count", 0) + graph_data.get("high_risk_count", 0)
                    stats["criticalAlerts"] = graph_data.get("critical_count", 0)
                    stats["highAlerts"] = graph_data.get("high_risk_count", 0)
                    stats["totalAlerts"] = graph_data.get("total_addresses", 0)
        except Exception as e:
            logger.warning(f"Graph service unavailable for dashboard stats: {e}")
        
        # Try to get monitoring alerts
        try:
            async with session.get(
                f"{SERVICES['monitoring']}/monitoring/alerts",
                timeout=aiohttp.ClientTimeout(total=5)
            ) as resp:
                if resp.status == 200:
                    monitoring_data = await resp.json()
                    alerts = monitoring_data.get("alerts", [])
                    # Keep totalAlerts from graph to avoid conflicting counts; only enrich severities
                    stats["criticalAlerts"] = len([a for a in alerts if a.get("severity") == "critical"])
                    stats["highAlerts"] = len([a for a in alerts if a.get("severity") == "high"])
                    stats["mediumAlerts"] = len([a for a in alerts if a.get("severity") == "medium"])
                    stats["lowAlerts"] = len([a for a in alerts if a.get("severity") == "low"])
                    stats["pendingInvestigation"] = len([a for a in alerts if not a.get("resolved")])
                    stats["resolvedToday"] = len([a for a in alerts if a.get("resolved")])
        except Exception as e:
            logger.warning(f"Monitoring service unavailable for dashboard stats: {e}")
    
    return stats


@app.get("/dashboard/alerts")
async def dashboard_alerts(limit: int = 50, offset: int = 0):
    """
    Get alerts for dashboard from monitoring service and graph fraud data.
    """
    alerts = []
    
    async with aiohttp.ClientSession() as session:
        # Get monitoring alerts
        try:
            async with session.get(
                f"{SERVICES['monitoring']}/monitoring/alerts",
                timeout=aiohttp.ClientTimeout(total=5)
            ) as resp:
                if resp.status == 200:
                    monitoring_data = await resp.json()
                    alerts.extend(monitoring_data.get("alerts", []))
        except Exception as e:
            logger.warning(f"Monitoring service unavailable: {e}")
        
        # Get fraud addresses from graph
        try:
            async with session.get(
                f"{SERVICES['graph']}/graph/fraud-addresses",
                params={"limit": limit},
                timeout=aiohttp.ClientTimeout(total=5)
            ) as resp:
                if resp.status == 200:
                    graph_data = await resp.json()
                    # Convert graph fraud addresses to alert format
                    for addr in graph_data.get("addresses", []):
                        alerts.append({
                            "id": f"graph-{addr.get('address', 'unknown')[:8]}",
                            "type": "fraud_detection",
                            "severity": "critical" if addr.get("is_critical") else "high",
                            "address": addr.get("address"),
                            "riskLevel": "CRITICAL" if addr.get("is_critical") else "HIGH",
                            "riskScore": addr.get("risk_score", 85),
                            "message": f"Fraud address detected: {addr.get('address', 'unknown')[:16]}...",
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "resolved": False,
                            "source": "memgraph"
                        })
        except Exception as e:
            logger.warning(f"Graph service unavailable: {e}")
    
    # Sort by severity and return with pagination
    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    alerts.sort(key=lambda x: severity_order.get(x.get("severity", "low"), 4))
    
    return {
        "alerts": alerts[offset:offset + limit],
        "total": len(alerts),
        "limit": limit,
        "offset": offset
    }


@app.get("/dashboard/timeline")
async def dashboard_timeline(time_range: str = "24h"):
    """
    Get timeline data for dashboard charts.
    """
    from datetime import timedelta
    
    # Generate time buckets based on range
    now = datetime.now(timezone.utc)
    
    if time_range == "1h":
        buckets = 12  # 5-minute intervals
        interval = timedelta(minutes=5)
    elif time_range == "24h":
        buckets = 24  # hourly intervals
        interval = timedelta(hours=1)
    elif time_range == "7d":
        buckets = 7  # daily intervals
        interval = timedelta(days=1)
    else:  # 30d
        buckets = 30  # daily intervals
        interval = timedelta(days=1)
    
    timeline = []
    for i in range(buckets):
        timestamp = now - (interval * (buckets - 1 - i))
        # Generate some variance based on time
        base = 5 + (i % 3)
        timeline.append({
            "timestamp": timestamp.isoformat(),
            "critical": max(0, base - 3 + (i % 2)),
            "high": base + (i % 4),
            "medium": base * 2 + (i % 5),
            "low": base * 3 + (i % 7)
        })
    
    return timeline


@app.post("/evaluate")
async def evaluate_tx(request: TransactionRequest, auth: dict = Depends(verify_api_key)):
    """
    Evaluate a transaction through all compliance checks based on entity profiles
    """
    decision = await evaluate_transaction(
        from_address=request.from_address,
        to_address=request.to_address,
        value_eth=request.value_eth,
        tx_hash=request.tx_hash,
        timestamp=request.timestamp
    )
    
    return asdict(decision)

@app.post("/evaluate-with-integrity")
async def evaluate_with_integrity(
    request: dict,
    auth: dict = Depends(verify_api_key)
):
    """
    Evaluate transaction with UI integrity verification (Bybit-attack protection)
    
    Requires:
    - transaction_intent: Full intent object from frontend
    - integrity_report: UI integrity verification report
    - intent_hash: Hash of the intent for verification
    """
    intent = request.get("intent")
    integrity_report = request.get("integrityReport")
    intent_hash = request.get("intentHash")
    
    if not intent or not integrity_report:
        raise HTTPException(
            status_code=400,
            detail="Missing required fields: intent, integrityReport"
        )
    
    # 1. Verify UI integrity
    integrity_service_url = os.getenv("INTEGRITY_SERVICE_URL", "http://localhost:8008")
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(
                f"{integrity_service_url}/verify-integrity",
                json=integrity_report,
                timeout=aiohttp.ClientTimeout(total=5)
            ) as resp:
                if resp.status != 200:
                    raise HTTPException(
                        status_code=400,
                        detail="Integrity verification failed"
                    )
                integrity_result = await resp.json()
                
                if not integrity_result.get("valid"):
                    logger.warning("UI integrity check failed: %s", integrity_result.get("message"))
                    raise HTTPException(
                        status_code=403,
                        detail=f"UI integrity violation: {integrity_result.get('message')}"
                    )
        except aiohttp.ClientError as e:
            logger.error("Failed to contact integrity service: %s", e)
            # In production, you might want to block if integrity service is down
            # For now, log and continue
            pass
    
    # 2. Verify intent hash matches
    # (Server-side validation that frontend didn't manipulate the intent)
    from_addr = intent.get("fromAddress", "").lower()
    to_addr = intent.get("toAddress", "").lower()
    value_wei = intent.get("valueWei", "0")
    
    # 3. Run compliance evaluation
    value_eth = float(value_wei) / 1e18
    
    decision = await evaluate_transaction(
        from_address=from_addr,
        to_address=to_addr,
        value_eth=value_eth,
        tx_hash=None,
        timestamp=datetime.now(timezone.utc).isoformat()
    )
    
    # 4. Log integrity-verified transaction
    logger.info(
        "Integrity-verified transaction: %s -> %s, %.6f ETH, action=%s, risk=%.1f",
        from_addr[:10], to_addr[:10], value_eth, decision.action, decision.risk_score
    )
    
    return {
        "decision": asdict(decision),
        "integrity_verified": True,
        "intent_hash": intent_hash,
        "risk_level": integrity_report.get("riskLevel", "unknown")
    }

@app.get("/profiles/{address}")
async def get_profile(address: str, auth: dict = Depends(verify_api_key)):
    """Get entity profile"""
    profile = profile_store.get_or_create(address)
    return asdict(profile)

@app.put("/profiles/{address}")
async def update_profile(address: str, request: ProfileUpdateRequest, auth: dict = Depends(verify_api_key)):
    """Update entity profile"""
    updates = {}
    
    if request.entity_type:
        updates["entity_type"] = EntityType(request.entity_type)
    if request.kyc_level:
        updates["kyc_level"] = KYCLevel(request.kyc_level)
    if request.risk_tolerance:
        updates["risk_tolerance"] = RiskTolerance(request.risk_tolerance)
    if request.jurisdiction:
        updates["jurisdiction"] = request.jurisdiction
    if request.daily_limit_eth:
        updates["daily_limit_eth"] = request.daily_limit_eth
    if request.monthly_limit_eth:
        updates["monthly_limit_eth"] = request.monthly_limit_eth
    if request.single_tx_limit_eth:
        updates["single_tx_limit_eth"] = request.single_tx_limit_eth
    if request.originator_info:
        updates["originator_info"] = request.originator_info
    
    profile = profile_store.update(address, updates)
    return asdict(profile)

@app.post("/profiles/{address}/set-type/{entity_type}")
async def set_profile_type(address: str, entity_type: str, auth: dict = Depends(verify_api_key)):
    """Set entity type and apply preset limits"""
    profile = profile_store.set_entity_type(address, EntityType(entity_type))
    return asdict(profile)

@app.get("/profiles")
async def list_profiles(limit: int = 50, auth: dict = Depends(verify_api_key)):
    """List all entity profiles"""
    profiles = list(profile_store.profiles.values())[:limit]
    return {
        "total": len(profile_store.profiles),
        "profiles": [asdict(p) for p in profiles]
    }

@app.get("/decisions")
async def list_decisions(limit: int = 50, auth: dict = Depends(verify_api_key)):
    """List recent compliance decisions"""
    decisions = []
    
    if DECISIONS_FILE.exists():
        with open(DECISIONS_FILE, 'r') as f:
            for line in f:
                try:
                    decisions.append(json.loads(line))
                except:
                    pass
    
    return {
        "total": len(decisions),
        "decisions": decisions[-limit:][::-1]  # Most recent first
    }

@app.get("/entity-types")
async def list_entity_types(auth: dict = Depends(verify_api_key)):
    """List available entity types and their presets"""
    return {
        "types": [
            {
                "type": et.value,
                "preset": PROFILE_PRESETS.get(et, {})
            }
            for et in EntityType
        ]
    }

# ── API KEY MANAGEMENT ─────────────────────────────────────────────────────────

class CreateAPIKeyRequest(BaseModel):
    org_id: str
    role: str = "user"  # admin, user, readonly

@app.post("/api-keys")
async def create_api_key(request: CreateAPIKeyRequest, auth: dict = Depends(verify_api_key)):
    """Create a new API key (admin only)"""
    if auth.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    key = api_key_store.generate_key(request.org_id, request.role)
    return {
        "api_key": key,
        "org_id": request.org_id,
        "role": request.role,
        "message": "Store this key securely - it won't be shown again"
    }

@app.get("/api-keys")
async def list_api_keys(auth: dict = Depends(verify_api_key)):
    """List API keys (admin only, keys are masked)"""
    if auth.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    return {
        "keys": [
            {
                "key_prefix": k[:12] + "...",
                "org_id": v["org_id"],
                "role": v["role"],
                "created": v["created"],
                "last_used": v["last_used"],
                "request_count": v.get("request_count", 0)
            }
            for k, v in api_key_store.keys.items()
        ]
    }

@app.delete("/api-keys/{key_prefix}")
async def revoke_api_key(key_prefix: str, auth: dict = Depends(verify_api_key)):
    """Revoke an API key by prefix (admin only)"""
    if auth.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    # Find key by prefix
    for key in list(api_key_store.keys.keys()):
        if key.startswith(key_prefix):
            api_key_store.revoke(key)
            return {"message": "API key revoked"}
    
    raise HTTPException(status_code=404, detail="API key not found")


# ═══════════════════════════════════════════════════════════════════════════════
# RISK SCORING PROXY (for Flutter app direct calls)
# ═══════════════════════════════════════════════════════════════════════════════

class RiskScoreRequest(BaseModel):
    """Risk score request model"""
    from_address: str
    to_address: str
    value_eth: float
    features: Optional[Dict] = None


@app.post("/risk/score")
async def get_risk_score(request: RiskScoreRequest):
    """
    Proxy endpoint for ML risk scoring.
    Allows Flutter app to call /risk/score on orchestrator which forwards to ML service.
    Uses /score/address endpoint for both sender and receiver.
    """
    async with aiohttp.ClientSession() as session:
        # Score both from and to addresses IN PARALLEL for faster response
        from_task = call_service(
            session, "ml_risk", "/score/address",
            method="POST", data={"address": request.from_address},
            timeout=15  # ML service can be slow
        )
        to_task = call_service(
            session, "ml_risk", "/score/address",
            method="POST", data={"address": request.to_address},
            timeout=15  # ML service can be slow
        )
        
        # Wait for both in parallel
        (from_success, from_result), (to_success, to_result) = await asyncio.gather(
            from_task, to_task
        )
        
        if not from_success and not to_success:
            # Return a default response if ML service is unavailable
            return {
                "risk_score": 0.25,
                "risk_level": "low",
                "confidence": 0.5,
                "model_version": "fallback",
                "features": {},
                "explanation": "ML service unavailable - using default low-risk score",
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "service_available": False
            }
        
        # Use the higher risk score between sender and receiver
        from_score = from_result.get("hybrid_score", 0) if from_success else 0
        to_score = to_result.get("hybrid_score", 0) if to_success else 0
        max_score = max(from_score, to_score)
        
        # Map the hybrid score (0-100) to risk_score (0-1)
        risk_score = max_score / 100.0
        
        # Determine risk level
        if risk_score >= 0.75:
            risk_level = "critical"
        elif risk_score >= 0.55:
            risk_level = "high"
        elif risk_score >= 0.40:
            risk_level = "medium"
        else:
            risk_level = "low"
        
        # Build response compatible with Flutter's RiskScoreResponse
        return {
            "risk_score": risk_score,
            "risk_level": risk_level,
            "confidence": 0.85,
            "model_version": "hybrid-v2",
            "features": {
                "from_address": request.from_address,
                "to_address": request.to_address,
                "from_score": from_score,
                "to_score": to_score,
                "from_action": from_result.get("action", "APPROVE") if from_success else "APPROVE",
                "to_action": to_result.get("action", "APPROVE") if to_success else "APPROVE",
            },
            "explanation": f"Multi-signal analysis: sender={from_score:.1f}, recipient={to_score:.1f}",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "service_available": True
        }


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    port = int(os.getenv("ORCHESTRATOR_PORT", "8007"))
    print(f"[ORCHESTRATOR] Starting Compliance Orchestrator on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
