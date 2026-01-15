"""
AMTTP Compliance Database Layer
PostgreSQL-backed storage for profiles, decisions, and audit logs.

Supports:
- Entity profiles with versioning
- Compliance decisions with full audit trail
- API keys management
- Rate limit tracking

Uses asyncpg for async PostgreSQL access.
Falls back to JSON file storage if PostgreSQL is not configured.
"""

import os
import json
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, asdict, field
from enum import Enum
from pathlib import Path
import hashlib
import secrets
import logging

logger = logging.getLogger("database")

# ═══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════

DATABASE_URL = os.getenv("DATABASE_URL", "")  # postgresql://user:pass@host:5432/dbname
USE_POSTGRES = bool(DATABASE_URL)

DATA_DIR = Path(__file__).parent / "data" / "orchestrator"
PROFILES_FILE = DATA_DIR / "entity_profiles.json"
DECISIONS_FILE = DATA_DIR / "decisions.jsonl"
API_KEYS_FILE = DATA_DIR / "api_keys.json"

# Try to import asyncpg if available
try:
    import asyncpg
    HAS_ASYNCPG = True
except ImportError:
    HAS_ASYNCPG = False
    logger.warning("asyncpg not installed - using JSON file storage")

# ═══════════════════════════════════════════════════════════════════════════════
# ENUMS
# ═══════════════════════════════════════════════════════════════════════════════

class EntityType(str, Enum):
    RETAIL = "RETAIL"
    INSTITUTIONAL = "INSTITUTIONAL"
    VASP = "VASP"
    HIGH_NET_WORTH = "HIGH_NET_WORTH"
    UNVERIFIED = "UNVERIFIED"

class KYCLevel(str, Enum):
    NONE = "NONE"
    BASIC = "BASIC"
    STANDARD = "STANDARD"
    ENHANCED = "ENHANCED"
    INSTITUTIONAL = "INSTITUTIONAL"

class RiskTolerance(str, Enum):
    STRICT = "STRICT"
    CONSERVATIVE = "CONSERVATIVE"
    MODERATE = "MODERATE"
    PERMISSIVE = "PERMISSIVE"

class ComplianceAction(str, Enum):
    APPROVE = "APPROVE"
    ESCROW = "ESCROW"
    REVIEW = "REVIEW"
    BLOCK = "BLOCK"
    REQUIRE_INFO = "REQUIRE_INFO"

# ═══════════════════════════════════════════════════════════════════════════════
# DATA CLASSES
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class EntityProfile:
    """Entity profile with compliance settings"""
    address: str
    entity_type: EntityType = EntityType.UNVERIFIED
    kyc_level: KYCLevel = KYCLevel.NONE
    risk_tolerance: RiskTolerance = RiskTolerance.CONSERVATIVE
    jurisdiction: str = "UNKNOWN"
    
    daily_limit_eth: float = 10.0
    monthly_limit_eth: float = 100.0
    single_tx_limit_eth: float = 5.0
    
    sanctions_checked: bool = False
    pep_checked: bool = False
    source_of_funds_verified: bool = False
    
    travel_rule_threshold_eth: float = 0.84
    originator_info: Optional[Dict] = None
    
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    version: int = 1
    
    total_transactions: int = 0
    daily_volume_eth: float = 0.0
    monthly_volume_eth: float = 0.0

@dataclass
class ComplianceDecision:
    """Compliance decision record"""
    decision_id: str
    timestamp: str
    from_address: str
    to_address: str
    value_eth: float
    action: ComplianceAction
    risk_score: float
    reasons: List[str]
    checks: List[Dict]
    requires_travel_rule: bool = False
    requires_sar: bool = False
    requires_escrow: bool = False
    escrow_duration_hours: int = 0
    processing_time_ms: float = 0.0
    originator_profile: Optional[Dict] = None
    beneficiary_profile: Optional[Dict] = None

@dataclass
class ProfileVersion:
    """Historical version of a profile"""
    address: str
    version: int
    profile_data: Dict
    changed_at: str
    changed_by: str
    change_reason: str

# ═══════════════════════════════════════════════════════════════════════════════
# DATABASE INTERFACE
# ═══════════════════════════════════════════════════════════════════════════════

class DatabaseInterface:
    """Abstract interface for database operations"""
    
    async def init(self):
        raise NotImplementedError
    
    async def close(self):
        raise NotImplementedError
    
    # Profiles
    async def get_profile(self, address: str) -> Optional[EntityProfile]:
        raise NotImplementedError
    
    async def save_profile(self, profile: EntityProfile, changed_by: str = "system", reason: str = "") -> EntityProfile:
        raise NotImplementedError
    
    async def list_profiles(self, limit: int = 50, offset: int = 0) -> List[EntityProfile]:
        raise NotImplementedError
    
    async def get_profile_history(self, address: str, limit: int = 10) -> List[ProfileVersion]:
        raise NotImplementedError
    
    # Decisions
    async def save_decision(self, decision: ComplianceDecision):
        raise NotImplementedError
    
    async def get_decision(self, decision_id: str) -> Optional[ComplianceDecision]:
        raise NotImplementedError
    
    async def list_decisions(self, limit: int = 50, address: Optional[str] = None) -> List[ComplianceDecision]:
        raise NotImplementedError
    
    # API Keys
    async def get_api_key(self, key_hash: str) -> Optional[Dict]:
        raise NotImplementedError
    
    async def save_api_key(self, key_data: Dict):
        raise NotImplementedError
    
    async def list_api_keys(self) -> List[Dict]:
        raise NotImplementedError

# ═══════════════════════════════════════════════════════════════════════════════
# JSON FILE STORAGE (Fallback)
# ═══════════════════════════════════════════════════════════════════════════════

class JSONFileDatabase(DatabaseInterface):
    """JSON file-based storage for development/fallback"""
    
    def __init__(self):
        self.profiles: Dict[str, EntityProfile] = {}
        self.api_keys: Dict[str, Dict] = {}
        self.profile_history: Dict[str, List[ProfileVersion]] = {}
    
    async def init(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        await self._load_profiles()
        await self._load_api_keys()
        logger.info("JSON file database initialized")
    
    async def close(self):
        await self._save_profiles()
        await self._save_api_keys()
    
    async def _load_profiles(self):
        if PROFILES_FILE.exists():
            try:
                with open(PROFILES_FILE, 'r', encoding='utf-8') as f:
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
                        version=profile_data.get("version", 1),
                        total_transactions=profile_data.get("total_transactions", 0),
                        daily_volume_eth=profile_data.get("daily_volume_eth", 0.0),
                        monthly_volume_eth=profile_data.get("monthly_volume_eth", 0.0),
                    )
                logger.info("Loaded %d profiles from JSON", len(self.profiles))
            except Exception as e:
                logger.error("Failed to load profiles: %s", e)
    
    async def _save_profiles(self):
        data = {}
        for addr, profile in self.profiles.items():
            profile_dict = asdict(profile)
            # Convert enums to strings
            profile_dict["entity_type"] = profile.entity_type.value if isinstance(profile.entity_type, Enum) else profile.entity_type
            profile_dict["kyc_level"] = profile.kyc_level.value if isinstance(profile.kyc_level, Enum) else profile.kyc_level
            profile_dict["risk_tolerance"] = profile.risk_tolerance.value if isinstance(profile.risk_tolerance, Enum) else profile.risk_tolerance
            data[addr] = profile_dict
        
        with open(PROFILES_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, default=str)
    
    async def _load_api_keys(self):
        if API_KEYS_FILE.exists():
            try:
                with open(API_KEYS_FILE, 'r', encoding='utf-8') as f:
                    self.api_keys = json.load(f)
                logger.info("Loaded %d API keys from JSON", len(self.api_keys))
            except Exception as e:
                logger.error("Failed to load API keys: %s", e)
    
    async def _save_api_keys(self):
        with open(API_KEYS_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.api_keys, f, indent=2)
    
    # Profile operations
    async def get_profile(self, address: str) -> Optional[EntityProfile]:
        return self.profiles.get(address.lower())
    
    async def save_profile(self, profile: EntityProfile, changed_by: str = "system", reason: str = "") -> EntityProfile:
        address = profile.address.lower()
        old_profile = self.profiles.get(address)
        
        # Track version history
        if old_profile:
            profile.version = old_profile.version + 1
            if address not in self.profile_history:
                self.profile_history[address] = []
            self.profile_history[address].append(ProfileVersion(
                address=address,
                version=old_profile.version,
                profile_data=asdict(old_profile),
                changed_at=datetime.now(timezone.utc).isoformat(),
                changed_by=changed_by,
                change_reason=reason
            ))
        
        profile.updated_at = datetime.now(timezone.utc).isoformat()
        self.profiles[address] = profile
        await self._save_profiles()
        return profile
    
    async def list_profiles(self, limit: int = 50, offset: int = 0) -> List[EntityProfile]:
        profiles = list(self.profiles.values())
        return profiles[offset:offset + limit]
    
    async def get_profile_history(self, address: str, limit: int = 10) -> List[ProfileVersion]:
        history = self.profile_history.get(address.lower(), [])
        return history[-limit:]
    
    # Decision operations
    async def save_decision(self, decision: ComplianceDecision):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        decision_dict = asdict(decision)
        decision_dict["action"] = decision.action.value if isinstance(decision.action, Enum) else decision.action
        
        with open(DECISIONS_FILE, 'a', encoding='utf-8') as f:
            f.write(json.dumps(decision_dict, default=str) + "\n")
    
    async def get_decision(self, decision_id: str) -> Optional[ComplianceDecision]:
        if not DECISIONS_FILE.exists():
            return None
        
        with open(DECISIONS_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    data = json.loads(line.strip())
                    if data.get("decision_id") == decision_id:
                        return ComplianceDecision(**data)
                except json.JSONDecodeError:
                    continue
        return None
    
    async def list_decisions(self, limit: int = 50, address: Optional[str] = None) -> List[ComplianceDecision]:
        if not DECISIONS_FILE.exists():
            return []
        
        decisions = []
        with open(DECISIONS_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    data = json.loads(line.strip())
                    if address:
                        if data.get("from_address", "").lower() == address.lower() or \
                           data.get("to_address", "").lower() == address.lower():
                            decisions.append(data)
                    else:
                        decisions.append(data)
                except json.JSONDecodeError:
                    continue
        
        return decisions[-limit:]
    
    # API Key operations
    async def get_api_key(self, key_hash: str) -> Optional[Dict]:
        return self.api_keys.get(key_hash)
    
    async def save_api_key(self, key_data: Dict):
        key_hash = key_data.get("key_hash")
        if key_hash:
            self.api_keys[key_hash] = key_data
            await self._save_api_keys()
    
    async def list_api_keys(self) -> List[Dict]:
        return list(self.api_keys.values())

# ═══════════════════════════════════════════════════════════════════════════════
# POSTGRESQL STORAGE
# ═══════════════════════════════════════════════════════════════════════════════

class PostgresDatabase(DatabaseInterface):
    """PostgreSQL-backed storage for production"""
    
    def __init__(self, database_url: str):
        self.database_url = database_url
        self.pool: Optional[asyncpg.Pool] = None
    
    async def init(self):
        if not HAS_ASYNCPG:
            raise RuntimeError("asyncpg is required for PostgreSQL storage")
        
        self.pool = await asyncpg.create_pool(self.database_url, min_size=2, max_size=10)
        await self._create_tables()
        logger.info("PostgreSQL database initialized")
    
    async def close(self):
        if self.pool:
            await self.pool.close()
    
    async def _create_tables(self):
        async with self.pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS entity_profiles (
                    address TEXT PRIMARY KEY,
                    entity_type TEXT NOT NULL DEFAULT 'UNVERIFIED',
                    kyc_level TEXT NOT NULL DEFAULT 'NONE',
                    risk_tolerance TEXT NOT NULL DEFAULT 'CONSERVATIVE',
                    jurisdiction TEXT DEFAULT 'UNKNOWN',
                    daily_limit_eth DECIMAL(20,8) DEFAULT 10.0,
                    monthly_limit_eth DECIMAL(20,8) DEFAULT 100.0,
                    single_tx_limit_eth DECIMAL(20,8) DEFAULT 5.0,
                    sanctions_checked BOOLEAN DEFAULT FALSE,
                    pep_checked BOOLEAN DEFAULT FALSE,
                    source_of_funds_verified BOOLEAN DEFAULT FALSE,
                    travel_rule_threshold_eth DECIMAL(20,8) DEFAULT 0.84,
                    originator_info JSONB,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW(),
                    version INTEGER DEFAULT 1,
                    total_transactions INTEGER DEFAULT 0,
                    daily_volume_eth DECIMAL(20,8) DEFAULT 0.0,
                    monthly_volume_eth DECIMAL(20,8) DEFAULT 0.0
                );
                
                CREATE TABLE IF NOT EXISTS profile_history (
                    id SERIAL PRIMARY KEY,
                    address TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    profile_data JSONB NOT NULL,
                    changed_at TIMESTAMPTZ DEFAULT NOW(),
                    changed_by TEXT DEFAULT 'system',
                    change_reason TEXT
                );
                
                CREATE INDEX IF NOT EXISTS idx_profile_history_address ON profile_history(address);
                
                CREATE TABLE IF NOT EXISTS compliance_decisions (
                    decision_id TEXT PRIMARY KEY,
                    timestamp TIMESTAMPTZ NOT NULL,
                    from_address TEXT NOT NULL,
                    to_address TEXT NOT NULL,
                    value_eth DECIMAL(20,8) NOT NULL,
                    action TEXT NOT NULL,
                    risk_score DECIMAL(5,2) NOT NULL,
                    reasons JSONB,
                    checks JSONB,
                    requires_travel_rule BOOLEAN DEFAULT FALSE,
                    requires_sar BOOLEAN DEFAULT FALSE,
                    requires_escrow BOOLEAN DEFAULT FALSE,
                    escrow_duration_hours INTEGER DEFAULT 0,
                    processing_time_ms DECIMAL(10,3) DEFAULT 0,
                    originator_profile JSONB,
                    beneficiary_profile JSONB
                );
                
                CREATE INDEX IF NOT EXISTS idx_decisions_from ON compliance_decisions(from_address);
                CREATE INDEX IF NOT EXISTS idx_decisions_to ON compliance_decisions(to_address);
                CREATE INDEX IF NOT EXISTS idx_decisions_timestamp ON compliance_decisions(timestamp DESC);
                
                CREATE TABLE IF NOT EXISTS api_keys (
                    key_hash TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    org_id TEXT,
                    scopes JSONB,
                    rate_limit INTEGER DEFAULT 100,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    expires_at TIMESTAMPTZ,
                    active BOOLEAN DEFAULT TRUE
                );
            """)
    
    async def get_profile(self, address: str) -> Optional[EntityProfile]:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM entity_profiles WHERE address = $1",
                address.lower()
            )
            if row:
                return EntityProfile(
                    address=row['address'],
                    entity_type=EntityType(row['entity_type']),
                    kyc_level=KYCLevel(row['kyc_level']),
                    risk_tolerance=RiskTolerance(row['risk_tolerance']),
                    jurisdiction=row['jurisdiction'],
                    daily_limit_eth=float(row['daily_limit_eth']),
                    monthly_limit_eth=float(row['monthly_limit_eth']),
                    single_tx_limit_eth=float(row['single_tx_limit_eth']),
                    sanctions_checked=row['sanctions_checked'],
                    pep_checked=row['pep_checked'],
                    source_of_funds_verified=row['source_of_funds_verified'],
                    travel_rule_threshold_eth=float(row['travel_rule_threshold_eth']),
                    originator_info=row['originator_info'],
                    created_at=row['created_at'].isoformat(),
                    updated_at=row['updated_at'].isoformat(),
                    version=row['version'],
                    total_transactions=row['total_transactions'],
                    daily_volume_eth=float(row['daily_volume_eth']),
                    monthly_volume_eth=float(row['monthly_volume_eth']),
                )
            return None
    
    async def save_profile(self, profile: EntityProfile, changed_by: str = "system", reason: str = "") -> EntityProfile:
        address = profile.address.lower()
        
        async with self.pool.acquire() as conn:
            # Get existing profile for versioning
            existing = await conn.fetchrow(
                "SELECT version FROM entity_profiles WHERE address = $1",
                address
            )
            
            new_version = (existing['version'] + 1) if existing else 1
            profile.version = new_version
            profile.updated_at = datetime.now(timezone.utc).isoformat()
            
            # Save history if updating
            if existing:
                old_profile = await self.get_profile(address)
                if old_profile:
                    await conn.execute("""
                        INSERT INTO profile_history (address, version, profile_data, changed_by, change_reason)
                        VALUES ($1, $2, $3, $4, $5)
                    """, address, existing['version'], json.dumps(asdict(old_profile), default=str), changed_by, reason)
            
            # Upsert profile
            await conn.execute("""
                INSERT INTO entity_profiles (
                    address, entity_type, kyc_level, risk_tolerance, jurisdiction,
                    daily_limit_eth, monthly_limit_eth, single_tx_limit_eth,
                    sanctions_checked, pep_checked, source_of_funds_verified,
                    travel_rule_threshold_eth, originator_info, created_at, updated_at,
                    version, total_transactions, daily_volume_eth, monthly_volume_eth
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19)
                ON CONFLICT (address) DO UPDATE SET
                    entity_type = EXCLUDED.entity_type,
                    kyc_level = EXCLUDED.kyc_level,
                    risk_tolerance = EXCLUDED.risk_tolerance,
                    jurisdiction = EXCLUDED.jurisdiction,
                    daily_limit_eth = EXCLUDED.daily_limit_eth,
                    monthly_limit_eth = EXCLUDED.monthly_limit_eth,
                    single_tx_limit_eth = EXCLUDED.single_tx_limit_eth,
                    sanctions_checked = EXCLUDED.sanctions_checked,
                    pep_checked = EXCLUDED.pep_checked,
                    source_of_funds_verified = EXCLUDED.source_of_funds_verified,
                    travel_rule_threshold_eth = EXCLUDED.travel_rule_threshold_eth,
                    originator_info = EXCLUDED.originator_info,
                    updated_at = EXCLUDED.updated_at,
                    version = EXCLUDED.version,
                    total_transactions = EXCLUDED.total_transactions,
                    daily_volume_eth = EXCLUDED.daily_volume_eth,
                    monthly_volume_eth = EXCLUDED.monthly_volume_eth
            """,
                address,
                profile.entity_type.value if isinstance(profile.entity_type, Enum) else profile.entity_type,
                profile.kyc_level.value if isinstance(profile.kyc_level, Enum) else profile.kyc_level,
                profile.risk_tolerance.value if isinstance(profile.risk_tolerance, Enum) else profile.risk_tolerance,
                profile.jurisdiction,
                profile.daily_limit_eth,
                profile.monthly_limit_eth,
                profile.single_tx_limit_eth,
                profile.sanctions_checked,
                profile.pep_checked,
                profile.source_of_funds_verified,
                profile.travel_rule_threshold_eth,
                json.dumps(profile.originator_info) if profile.originator_info else None,
                profile.created_at,
                profile.updated_at,
                profile.version,
                profile.total_transactions,
                profile.daily_volume_eth,
                profile.monthly_volume_eth
            )
        
        return profile
    
    async def list_profiles(self, limit: int = 50, offset: int = 0) -> List[EntityProfile]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM entity_profiles ORDER BY updated_at DESC LIMIT $1 OFFSET $2",
                limit, offset
            )
            return [EntityProfile(
                address=row['address'],
                entity_type=EntityType(row['entity_type']),
                kyc_level=KYCLevel(row['kyc_level']),
                risk_tolerance=RiskTolerance(row['risk_tolerance']),
                jurisdiction=row['jurisdiction'],
                daily_limit_eth=float(row['daily_limit_eth']),
                monthly_limit_eth=float(row['monthly_limit_eth']),
                single_tx_limit_eth=float(row['single_tx_limit_eth']),
                version=row['version'],
                total_transactions=row['total_transactions'],
            ) for row in rows]
    
    async def get_profile_history(self, address: str, limit: int = 10) -> List[ProfileVersion]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """SELECT * FROM profile_history 
                   WHERE address = $1 
                   ORDER BY version DESC 
                   LIMIT $2""",
                address.lower(), limit
            )
            return [ProfileVersion(
                address=row['address'],
                version=row['version'],
                profile_data=row['profile_data'],
                changed_at=row['changed_at'].isoformat(),
                changed_by=row['changed_by'],
                change_reason=row['change_reason'] or ""
            ) for row in rows]
    
    async def save_decision(self, decision: ComplianceDecision):
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO compliance_decisions (
                    decision_id, timestamp, from_address, to_address, value_eth,
                    action, risk_score, reasons, checks, requires_travel_rule,
                    requires_sar, requires_escrow, escrow_duration_hours,
                    processing_time_ms, originator_profile, beneficiary_profile
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16)
            """,
                decision.decision_id,
                decision.timestamp,
                decision.from_address,
                decision.to_address,
                decision.value_eth,
                decision.action.value if isinstance(decision.action, Enum) else decision.action,
                decision.risk_score,
                json.dumps(decision.reasons),
                json.dumps(decision.checks),
                decision.requires_travel_rule,
                decision.requires_sar,
                decision.requires_escrow,
                decision.escrow_duration_hours,
                decision.processing_time_ms,
                json.dumps(decision.originator_profile) if decision.originator_profile else None,
                json.dumps(decision.beneficiary_profile) if decision.beneficiary_profile else None
            )
    
    async def get_decision(self, decision_id: str) -> Optional[ComplianceDecision]:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM compliance_decisions WHERE decision_id = $1",
                decision_id
            )
            if row:
                return ComplianceDecision(
                    decision_id=row['decision_id'],
                    timestamp=row['timestamp'].isoformat(),
                    from_address=row['from_address'],
                    to_address=row['to_address'],
                    value_eth=float(row['value_eth']),
                    action=ComplianceAction(row['action']),
                    risk_score=float(row['risk_score']),
                    reasons=row['reasons'],
                    checks=row['checks'],
                    requires_travel_rule=row['requires_travel_rule'],
                    requires_sar=row['requires_sar'],
                    requires_escrow=row['requires_escrow'],
                    escrow_duration_hours=row['escrow_duration_hours'],
                    processing_time_ms=float(row['processing_time_ms']),
                )
            return None
    
    async def list_decisions(self, limit: int = 50, address: Optional[str] = None) -> List[ComplianceDecision]:
        async with self.pool.acquire() as conn:
            if address:
                rows = await conn.fetch(
                    """SELECT * FROM compliance_decisions 
                       WHERE from_address = $1 OR to_address = $1
                       ORDER BY timestamp DESC LIMIT $2""",
                    address.lower(), limit
                )
            else:
                rows = await conn.fetch(
                    "SELECT * FROM compliance_decisions ORDER BY timestamp DESC LIMIT $1",
                    limit
                )
            return [dict(row) for row in rows]
    
    async def get_api_key(self, key_hash: str) -> Optional[Dict]:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM api_keys WHERE key_hash = $1 AND active = TRUE",
                key_hash
            )
            return dict(row) if row else None
    
    async def save_api_key(self, key_data: Dict):
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO api_keys (key_hash, name, org_id, scopes, rate_limit, expires_at)
                VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT (key_hash) DO UPDATE SET
                    name = EXCLUDED.name,
                    scopes = EXCLUDED.scopes,
                    rate_limit = EXCLUDED.rate_limit,
                    active = TRUE
            """,
                key_data['key_hash'],
                key_data.get('name', 'default'),
                key_data.get('org_id'),
                json.dumps(key_data.get('scopes', ['read', 'write'])),
                key_data.get('rate_limit', 100),
                key_data.get('expires_at')
            )
    
    async def list_api_keys(self) -> List[Dict]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM api_keys WHERE active = TRUE")
            return [dict(row) for row in rows]

# ═══════════════════════════════════════════════════════════════════════════════
# DATABASE FACTORY
# ═══════════════════════════════════════════════════════════════════════════════

_db_instance: Optional[DatabaseInterface] = None

async def get_database() -> DatabaseInterface:
    """Get or create database instance"""
    global _db_instance
    
    if _db_instance is None:
        if USE_POSTGRES and HAS_ASYNCPG:
            _db_instance = PostgresDatabase(DATABASE_URL)
            logger.info("Using PostgreSQL database")
        else:
            _db_instance = JSONFileDatabase()
            logger.info("Using JSON file database")
        
        await _db_instance.init()
    
    return _db_instance

async def close_database():
    """Close database connection"""
    global _db_instance
    if _db_instance:
        await _db_instance.close()
        _db_instance = None
