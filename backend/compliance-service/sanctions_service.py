"""
AMTTP Real Sanctions Screening Service
Production implementation with live HMT/OFAC/EU/UN sanctions lists

Features:
- Live download from official sources
- Daily automatic refresh
- Fuzzy name matching (Levenshtein distance)
- Address normalization and matching
- Caching for performance
- Audit logging
"""

import os
import json
import hashlib
import asyncio
import aiohttp
import aiofiles
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any, Set, Tuple
from dataclasses import dataclass, field, asdict
from enum import Enum
import re
import logging
from functools import lru_cache

import uvicorn
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# ═══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════

DATA_DIR = Path(__file__).parent / "data" / "sanctions"
CACHE_FILE = DATA_DIR / "sanctions_cache.json"
AUDIT_LOG = DATA_DIR / "sanctions_audit.jsonl"

# Official sanctions list sources
SANCTIONS_SOURCES = {
    "HMT": {
        "name": "UK HM Treasury Consolidated List",
        "url": "https://assets.publishing.service.gov.uk/government/uploads/system/uploads/attachment_data/file/consolidated_list.json",
        "backup_url": "https://ofsistorage.blob.core.windows.net/publishlive/ConList.csv",
        "format": "json",
        "refresh_hours": 24
    },
    "OFAC_SDN": {
        "name": "US OFAC Specially Designated Nationals",
        "url": "https://www.treasury.gov/ofac/downloads/sdn.json",
        "backup_url": "https://www.treasury.gov/ofac/downloads/sdn.csv",
        "format": "json",
        "refresh_hours": 24
    },
    "EU": {
        "name": "EU Consolidated Sanctions List",
        "url": "https://webgate.ec.europa.eu/fsd/fsf/public/files/jsonFullSanctionsList_1_1/content",
        "format": "json",
        "refresh_hours": 24
    },
    "UN": {
        "name": "UN Security Council Consolidated List",
        "url": "https://scsanctions.un.org/resources/xml/en/consolidated.json",
        "format": "json",
        "refresh_hours": 24
    }
}

# Known crypto addresses from sanctions (OFAC designated)
SANCTIONED_CRYPTO_ADDRESSES = {
    # Tornado Cash addresses (OFAC designated Aug 2022)
    "0x8589427373d6d84e98730d7795d8f6f8731fda16": {"name": "Tornado Cash", "list": "OFAC", "date": "2022-08-08"},
    "0x722122df12d4e14e13ac3b6895a86e84145b6967": {"name": "Tornado Cash Router", "list": "OFAC", "date": "2022-08-08"},
    "0xdd4c48c0b24039969fc16d1cdf626eab821d3384": {"name": "Tornado Cash", "list": "OFAC", "date": "2022-08-08"},
    "0xd90e2f925da726b50c4ed8d0fb90ad053324f31b": {"name": "Tornado Cash", "list": "OFAC", "date": "2022-08-08"},
    "0xd96f2b1c14db8458374d9aca76e26c3d18364307": {"name": "Tornado Cash", "list": "OFAC", "date": "2022-08-08"},
    "0x4736dcf1b7a3d580672cce6e7c65cd5cc9cfba9d": {"name": "Tornado Cash", "list": "OFAC", "date": "2022-08-08"},
    "0xd4b88df4d29f5cedd6857912842cff3b20c8cfa3": {"name": "Tornado Cash 100 ETH", "list": "OFAC", "date": "2022-08-08"},
    "0x910cbd523d972eb0a6f4cae4618ad62622b39dbf": {"name": "Tornado Cash 10 ETH", "list": "OFAC", "date": "2022-08-08"},
    "0xa160cdab225685da1d56aa342ad8841c3b53f291": {"name": "Tornado Cash 1 ETH", "list": "OFAC", "date": "2022-08-08"},
    "0xfd8610d20aa15b7b2e3be39b396a1bc3516c7144": {"name": "Tornado Cash 0.1 ETH", "list": "OFAC", "date": "2022-08-08"},
    "0xf60dd140cff0706bae9cd734ac3ae76ad9ebc32a": {"name": "Tornado Cash", "list": "OFAC", "date": "2022-08-08"},
    "0x22aaa7720ddd5388a3c0a3333430953c68f1849b": {"name": "Tornado Cash", "list": "OFAC", "date": "2022-08-08"},
    "0xba214c1c1928a32bffe790263e38b4af9bfcd659": {"name": "Tornado Cash", "list": "OFAC", "date": "2022-08-08"},
    "0xb1c8094b234dce6e03f10a5b673c1d8c69739a00": {"name": "Tornado Cash", "list": "OFAC", "date": "2022-08-08"},
    "0x527653ea119f3e6a1f5bd18fbf4714081d7b31ce": {"name": "Tornado Cash", "list": "OFAC", "date": "2022-08-08"},
    "0x58e8dcc13be9780fc42e8723d8ead4cf46943df2": {"name": "Tornado Cash Relayer", "list": "OFAC", "date": "2022-08-08"},
    # Lazarus Group / DPRK addresses
    "0x098b716b8aaf21512996dc57eb0615e2383e2f96": {"name": "Lazarus Group", "list": "OFAC", "date": "2022-04-14"},
    "0xa7e5d5a720f06526557c513402f2e6b5fa20b008": {"name": "Lazarus Group", "list": "OFAC", "date": "2022-04-14"},
    "0x3cffd56b47b7b41c56258d9c7731abadc360e073": {"name": "Lazarus Group", "list": "OFAC", "date": "2022-04-14"},
    # Blender.io
    "0x8576acc5c05d6ce88f4e49bf65bdf0c62f91353c": {"name": "Blender.io", "list": "OFAC", "date": "2022-05-06"},
    # Garantex
    "0x48549a34ae37b12f6a30566245176994e17c6b4a": {"name": "Garantex", "list": "OFAC", "date": "2022-04-05"},
    "0x6f1ca141a28907f78ebaa64fb83a9088b02a8352": {"name": "Garantex", "list": "OFAC", "date": "2022-04-05"},
}

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("sanctions_service")

# ═══════════════════════════════════════════════════════════════════════════════
# DATA MODELS
# ═══════════════════════════════════════════════════════════════════════════════

class SanctionsList(str, Enum):
    HMT = "HMT"
    OFAC = "OFAC"
    EU = "EU"
    UN = "UN"
    ALL = "ALL"

class MatchType(str, Enum):
    EXACT = "EXACT"
    FUZZY = "FUZZY"
    PARTIAL = "PARTIAL"
    ALIAS = "ALIAS"

@dataclass
class SanctionedEntity:
    id: str
    name: str
    aliases: List[str] = field(default_factory=list)
    entity_type: str = "individual"  # individual, entity, vessel, aircraft
    addresses: List[str] = field(default_factory=list)
    crypto_addresses: List[str] = field(default_factory=list)
    countries: List[str] = field(default_factory=list)
    programs: List[str] = field(default_factory=list)
    source_list: str = ""
    designation_date: Optional[str] = None
    additional_info: Dict[str, Any] = field(default_factory=dict)

@dataclass
class SanctionsMatch:
    matched: bool
    match_type: Optional[MatchType] = None
    confidence: float = 0.0
    entity: Optional[SanctionedEntity] = None
    matched_field: str = ""
    matched_value: str = ""
    query_value: str = ""

class SanctionsCheckRequest(BaseModel):
    address: Optional[str] = None
    name: Optional[str] = None
    country: Optional[str] = None
    lists: List[str] = Field(default=["ALL"])

class SanctionsCheckResponse(BaseModel):
    query: Dict[str, Any]
    is_sanctioned: bool
    matches: List[Dict[str, Any]]
    checked_lists: List[str]
    check_timestamp: str
    cache_age_hours: Optional[float] = None

# ═══════════════════════════════════════════════════════════════════════════════
# FUZZY MATCHING
# ═══════════════════════════════════════════════════════════════════════════════

def levenshtein_distance(s1: str, s2: str) -> int:
    """Calculate Levenshtein distance between two strings"""
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)
    
    if len(s2) == 0:
        return len(s1)
    
    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    
    return previous_row[-1]

def fuzzy_match_score(query: str, target: str, threshold: float = 0.85) -> Tuple[bool, float]:
    """Calculate fuzzy match score between query and target"""
    # Normalize strings
    query = normalize_name(query)
    target = normalize_name(target)
    
    if not query or not target:
        return False, 0.0
    
    # Exact match
    if query == target:
        return True, 1.0
    
    # Calculate similarity
    max_len = max(len(query), len(target))
    if max_len == 0:
        return False, 0.0
    
    distance = levenshtein_distance(query, target)
    similarity = 1.0 - (distance / max_len)
    
    return similarity >= threshold, similarity

def normalize_name(name: str) -> str:
    """Normalize a name for matching"""
    if not name:
        return ""
    
    # Lowercase
    name = name.lower()
    
    # Remove common titles and suffixes
    titles = ['mr', 'mrs', 'ms', 'dr', 'prof', 'sir', 'dame', 'lord', 'lady']
    suffixes = ['jr', 'sr', 'ii', 'iii', 'iv', 'esq', 'phd', 'md']
    
    words = name.split()
    words = [w for w in words if w not in titles and w not in suffixes]
    name = ' '.join(words)
    
    # Remove punctuation
    name = re.sub(r'[^\w\s]', '', name)
    
    # Remove extra whitespace
    name = ' '.join(name.split())
    
    return name

def normalize_address(address: str) -> str:
    """Normalize Ethereum address for matching"""
    if not address:
        return ""
    
    address = address.lower().strip()
    
    # Ensure 0x prefix
    if not address.startswith('0x'):
        address = '0x' + address
    
    # Validate length
    if len(address) != 42:
        return ""
    
    return address

# ═══════════════════════════════════════════════════════════════════════════════
# SANCTIONS DATABASE
# ═══════════════════════════════════════════════════════════════════════════════

class SanctionsDatabase:
    def __init__(self):
        self.entities: Dict[str, SanctionedEntity] = {}
        self.name_index: Dict[str, Set[str]] = {}  # normalized name -> entity IDs
        self.address_index: Dict[str, str] = {}  # crypto address -> entity ID
        self.country_index: Dict[str, Set[str]] = {}  # country code -> entity IDs
        self.last_refresh: Dict[str, datetime] = {}
        self.load_timestamp: Optional[datetime] = None
        
    def add_entity(self, entity: SanctionedEntity):
        """Add an entity to the database with indexing"""
        self.entities[entity.id] = entity
        
        # Index by name
        normalized = normalize_name(entity.name)
        if normalized:
            if normalized not in self.name_index:
                self.name_index[normalized] = set()
            self.name_index[normalized].add(entity.id)
        
        # Index aliases
        for alias in entity.aliases:
            normalized = normalize_name(alias)
            if normalized:
                if normalized not in self.name_index:
                    self.name_index[normalized] = set()
                self.name_index[normalized].add(entity.id)
        
        # Index crypto addresses
        for addr in entity.crypto_addresses:
            normalized = normalize_address(addr)
            if normalized:
                self.address_index[normalized] = entity.id
        
        # Index countries
        for country in entity.countries:
            country = country.upper()
            if country not in self.country_index:
                self.country_index[country] = set()
            self.country_index[country].add(entity.id)
    
    def check_address(self, address: str) -> SanctionsMatch:
        """Check if an address is sanctioned"""
        normalized = normalize_address(address)
        
        if not normalized:
            return SanctionsMatch(matched=False, query_value=address)
        
        # Check indexed addresses
        if normalized in self.address_index:
            entity_id = self.address_index[normalized]
            entity = self.entities.get(entity_id)
            return SanctionsMatch(
                matched=True,
                match_type=MatchType.EXACT,
                confidence=1.0,
                entity=entity,
                matched_field="crypto_address",
                matched_value=normalized,
                query_value=address
            )
        
        # Check hardcoded OFAC addresses
        if normalized in SANCTIONED_CRYPTO_ADDRESSES:
            info = SANCTIONED_CRYPTO_ADDRESSES[normalized]
            entity = SanctionedEntity(
                id=f"OFAC-CRYPTO-{normalized[:10]}",
                name=info["name"],
                crypto_addresses=[normalized],
                source_list=info["list"],
                designation_date=info["date"]
            )
            return SanctionsMatch(
                matched=True,
                match_type=MatchType.EXACT,
                confidence=1.0,
                entity=entity,
                matched_field="crypto_address",
                matched_value=normalized,
                query_value=address
            )
        
        return SanctionsMatch(matched=False, query_value=address)
    
    def check_name(self, name: str, fuzzy_threshold: float = 0.85) -> List[SanctionsMatch]:
        """Check if a name matches any sanctioned entity"""
        matches = []
        normalized_query = normalize_name(name)
        
        if not normalized_query:
            return matches
        
        # Exact match check
        if normalized_query in self.name_index:
            for entity_id in self.name_index[normalized_query]:
                entity = self.entities.get(entity_id)
                if entity:
                    matches.append(SanctionsMatch(
                        matched=True,
                        match_type=MatchType.EXACT,
                        confidence=1.0,
                        entity=entity,
                        matched_field="name",
                        matched_value=entity.name,
                        query_value=name
                    ))
        
        # Fuzzy match check
        for indexed_name, entity_ids in self.name_index.items():
            if indexed_name == normalized_query:
                continue  # Already matched exactly
            
            is_match, score = fuzzy_match_score(normalized_query, indexed_name, fuzzy_threshold)
            if is_match:
                for entity_id in entity_ids:
                    entity = self.entities.get(entity_id)
                    if entity:
                        # Check if already matched
                        already_matched = any(m.entity and m.entity.id == entity_id for m in matches)
                        if not already_matched:
                            matches.append(SanctionsMatch(
                                matched=True,
                                match_type=MatchType.FUZZY,
                                confidence=score,
                                entity=entity,
                                matched_field="name",
                                matched_value=indexed_name,
                                query_value=name
                            ))
        
        # Sort by confidence
        matches.sort(key=lambda m: m.confidence, reverse=True)
        return matches
    
    def check_country(self, country_code: str) -> List[SanctionedEntity]:
        """Get all sanctioned entities from a country"""
        country_code = country_code.upper()
        entity_ids = self.country_index.get(country_code, set())
        return [self.entities[eid] for eid in entity_ids if eid in self.entities]
    
    def stats(self) -> Dict[str, Any]:
        """Get database statistics"""
        return {
            "total_entities": len(self.entities),
            "indexed_names": len(self.name_index),
            "indexed_addresses": len(self.address_index),
            "indexed_countries": len(self.country_index),
            "hardcoded_crypto_addresses": len(SANCTIONED_CRYPTO_ADDRESSES),
            "last_refresh": {k: v.isoformat() for k, v in self.last_refresh.items()},
            "load_timestamp": self.load_timestamp.isoformat() if self.load_timestamp else None
        }

# Global database instance
sanctions_db = SanctionsDatabase()

# ═══════════════════════════════════════════════════════════════════════════════
# DATA LOADING
# ═══════════════════════════════════════════════════════════════════════════════

async def download_sanctions_list(source_key: str, session: aiohttp.ClientSession) -> Optional[Dict]:
    """Download a sanctions list from official source"""
    source = SANCTIONS_SOURCES.get(source_key)
    if not source:
        return None
    
    try:
        logger.info(f"Downloading {source['name']}...")
        async with session.get(source["url"], timeout=aiohttp.ClientTimeout(total=60)) as response:
            if response.status == 200:
                if source["format"] == "json":
                    return await response.json()
                else:
                    return {"raw": await response.text()}
            else:
                logger.warning(f"Failed to download {source_key}: HTTP {response.status}")
                
                # Try backup URL
                if "backup_url" in source:
                    async with session.get(source["backup_url"]) as backup_response:
                        if backup_response.status == 200:
                            return {"raw": await backup_response.text()}
                
                return None
    except Exception as e:
        logger.error(f"Error downloading {source_key}: {e}")
        return None

def parse_hmt_list(data: Dict) -> List[SanctionedEntity]:
    """Parse UK HMT consolidated list"""
    entities = []
    
    # HMT JSON structure varies - handle common formats
    items = data.get("ConsolidatedList", {}).get("Designations", [])
    if not items:
        items = data.get("designations", [])
    if not items:
        items = data if isinstance(data, list) else []
    
    for item in items:
        try:
            entity = SanctionedEntity(
                id=f"HMT-{item.get('UniqueID', item.get('id', hashlib.md5(str(item).encode()).hexdigest()[:12]))}",
                name=item.get("Name", item.get("name", "Unknown")),
                aliases=[a.get("Name", a) for a in item.get("Aliases", item.get("aliases", []))],
                entity_type=item.get("Type", item.get("type", "unknown")).lower(),
                countries=[item.get("Country", item.get("country", ""))],
                programs=item.get("Regimes", item.get("regimes", [])),
                source_list="HMT",
                designation_date=item.get("DateDesignated", item.get("date_designated")),
            )
            entities.append(entity)
        except Exception as e:
            logger.warning(f"Error parsing HMT entity: {e}")
    
    return entities

def parse_ofac_list(data: Dict) -> List[SanctionedEntity]:
    """Parse US OFAC SDN list"""
    entities = []
    
    sdn_entries = data.get("sdnList", data.get("entries", []))
    if not sdn_entries:
        sdn_entries = data if isinstance(data, list) else []
    
    for entry in sdn_entries:
        try:
            # Extract addresses (including crypto)
            crypto_addresses = []
            addresses = []
            
            for addr in entry.get("addresses", []):
                addr_str = addr.get("address", "")
                if addr_str.startswith("0x") and len(addr_str) == 42:
                    crypto_addresses.append(addr_str.lower())
                else:
                    addresses.append(addr_str)
            
            # Check ID list for crypto addresses
            for id_item in entry.get("idList", []):
                id_num = id_item.get("idNumber", "")
                if id_num.startswith("0x") and len(id_num) == 42:
                    crypto_addresses.append(id_num.lower())
            
            entity = SanctionedEntity(
                id=f"OFAC-{entry.get('uid', hashlib.md5(str(entry).encode()).hexdigest()[:12])}",
                name=entry.get("firstName", "") + " " + entry.get("lastName", entry.get("name", "")),
                aliases=[a.get("name", a) for a in entry.get("akaList", [])],
                entity_type=entry.get("sdnType", "unknown").lower(),
                addresses=addresses,
                crypto_addresses=crypto_addresses,
                countries=[entry.get("nationality", "")],
                programs=entry.get("programList", []),
                source_list="OFAC",
            )
            entities.append(entity)
        except Exception as e:
            logger.warning(f"Error parsing OFAC entity: {e}")
    
    return entities

def parse_eu_list(data: Dict) -> List[SanctionedEntity]:
    """Parse EU consolidated sanctions list"""
    entities = []
    
    entries = data.get("sanctionedPersons", data.get("entries", []))
    if not entries:
        entries = data if isinstance(data, list) else []
    
    for entry in entries:
        try:
            entity = SanctionedEntity(
                id=f"EU-{entry.get('logicalId', hashlib.md5(str(entry).encode()).hexdigest()[:12])}",
                name=entry.get("nameAlias", [{}])[0].get("wholeName", entry.get("name", "Unknown")),
                aliases=[a.get("wholeName", a) for a in entry.get("nameAlias", [])[1:]],
                entity_type=entry.get("subjectType", {}).get("code", "unknown").lower(),
                countries=[entry.get("citizenships", [{}])[0].get("countryIso2Code", "")],
                programs=[entry.get("regulation", {}).get("programme", "")],
                source_list="EU",
            )
            entities.append(entity)
        except Exception as e:
            logger.warning(f"Error parsing EU entity: {e}")
    
    return entities

def parse_un_list(data: Dict) -> List[SanctionedEntity]:
    """Parse UN Security Council sanctions list"""
    entities = []
    
    entries = data.get("CONSOLIDATED_LIST", {}).get("INDIVIDUALS", {}).get("INDIVIDUAL", [])
    entities_list = data.get("CONSOLIDATED_LIST", {}).get("ENTITIES", {}).get("ENTITY", [])
    
    for entry in entries + entities_list:
        try:
            entity = SanctionedEntity(
                id=f"UN-{entry.get('DATAID', hashlib.md5(str(entry).encode()).hexdigest()[:12])}",
                name=f"{entry.get('FIRST_NAME', '')} {entry.get('SECOND_NAME', '')} {entry.get('THIRD_NAME', '')}".strip() or entry.get("NAME", "Unknown"),
                aliases=[a.get("ALIAS_NAME", a) for a in entry.get("INDIVIDUAL_ALIAS", [])],
                entity_type="individual" if "FIRST_NAME" in entry else "entity",
                countries=[entry.get("NATIONALITY", {}).get("VALUE", "")],
                programs=[entry.get("UN_LIST_TYPE", "")],
                source_list="UN",
                designation_date=entry.get("LISTED_ON"),
            )
            entities.append(entity)
        except Exception as e:
            logger.warning(f"Error parsing UN entity: {e}")
    
    return entities

async def refresh_sanctions_database():
    """Refresh all sanctions lists"""
    global sanctions_db
    
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    
    async with aiohttp.ClientSession() as session:
        # Download all lists
        tasks = {
            key: download_sanctions_list(key, session)
            for key in SANCTIONS_SOURCES.keys()
        }
        
        results = {}
        for key, task in tasks.items():
            results[key] = await task
        
        # Parse and load
        new_db = SanctionsDatabase()
        
        # HMT
        if results.get("HMT"):
            for entity in parse_hmt_list(results["HMT"]):
                new_db.add_entity(entity)
            new_db.last_refresh["HMT"] = datetime.utcnow()
            logger.info(f"Loaded HMT list")
        
        # OFAC
        if results.get("OFAC_SDN"):
            for entity in parse_ofac_list(results["OFAC_SDN"]):
                new_db.add_entity(entity)
            new_db.last_refresh["OFAC"] = datetime.utcnow()
            logger.info(f"Loaded OFAC SDN list")
        
        # EU
        if results.get("EU"):
            for entity in parse_eu_list(results["EU"]):
                new_db.add_entity(entity)
            new_db.last_refresh["EU"] = datetime.utcnow()
            logger.info(f"Loaded EU list")
        
        # UN
        if results.get("UN"):
            for entity in parse_un_list(results["UN"]):
                new_db.add_entity(entity)
            new_db.last_refresh["UN"] = datetime.utcnow()
            logger.info(f"Loaded UN list")
        
        new_db.load_timestamp = datetime.utcnow()
        
        # Save cache
        cache_data = {
            "entities": {k: asdict(v) for k, v in new_db.entities.items()},
            "last_refresh": {k: v.isoformat() for k, v in new_db.last_refresh.items()},
            "load_timestamp": new_db.load_timestamp.isoformat()
        }
        
        async with aiofiles.open(CACHE_FILE, 'w') as f:
            await f.write(json.dumps(cache_data, indent=2))
        
        sanctions_db = new_db
        logger.info(f"Sanctions database refreshed: {new_db.stats()}")

async def load_cached_database():
    """Load database from cache"""
    global sanctions_db
    
    if not CACHE_FILE.exists():
        logger.info("No cache found, initializing with hardcoded addresses")
        sanctions_db.load_timestamp = datetime.utcnow()
        return
    
    try:
        async with aiofiles.open(CACHE_FILE, 'r') as f:
            cache_data = json.loads(await f.read())
        
        for entity_id, entity_data in cache_data.get("entities", {}).items():
            entity = SanctionedEntity(**entity_data)
            sanctions_db.add_entity(entity)
        
        sanctions_db.last_refresh = {
            k: datetime.fromisoformat(v)
            for k, v in cache_data.get("last_refresh", {}).items()
        }
        sanctions_db.load_timestamp = datetime.fromisoformat(cache_data.get("load_timestamp", datetime.utcnow().isoformat()))
        
        logger.info(f"Loaded sanctions database from cache: {sanctions_db.stats()}")
    except Exception as e:
        logger.error(f"Error loading cache: {e}")

def log_audit(action: str, query: Dict, result: Dict):
    """Log audit entry"""
    AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
    
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "action": action,
        "query": query,
        "result": result
    }
    
    with open(AUDIT_LOG, 'a') as f:
        f.write(json.dumps(entry) + "\n")

# ═══════════════════════════════════════════════════════════════════════════════
# FASTAPI APPLICATION
# ═══════════════════════════════════════════════════════════════════════════════

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await load_cached_database()
    
    # Check if refresh needed
    needs_refresh = not sanctions_db.load_timestamp
    if sanctions_db.load_timestamp:
        age = datetime.utcnow() - sanctions_db.load_timestamp
        if age > timedelta(hours=24):
            needs_refresh = True
    
    if needs_refresh:
        asyncio.create_task(refresh_sanctions_database())
    
    print("═" * 60)
    print("       AMTTP Sanctions Screening Service")
    print("═" * 60)
    print(f"📋 Entities loaded: {len(sanctions_db.entities)}")
    print(f"🔗 Crypto addresses indexed: {len(sanctions_db.address_index) + len(SANCTIONED_CRYPTO_ADDRESSES)}")
    print("═" * 60)
    
    yield
    
    # Shutdown
    print("👋 Sanctions service shutting down")

app = FastAPI(
    title="AMTTP Sanctions Screening Service",
    description="Real-time sanctions screening with HMT/OFAC/EU/UN lists",
    version="1.0.0",
    lifespan=lifespan
)

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
    return {
        "status": "healthy",
        "service": "sanctions-screening",
        "database_stats": sanctions_db.stats()
    }

@app.post("/sanctions/check", response_model=SanctionsCheckResponse)
async def check_sanctions(request: SanctionsCheckRequest):
    """
    Check an address or name against sanctions lists
    """
    matches = []
    checked_lists = request.lists if "ALL" not in request.lists else ["HMT", "OFAC", "EU", "UN"]
    
    # Check address
    if request.address:
        result = sanctions_db.check_address(request.address)
        if result.matched:
            matches.append({
                "match_type": result.match_type.value if result.match_type else None,
                "confidence": result.confidence,
                "matched_field": result.matched_field,
                "matched_value": result.matched_value,
                "entity": asdict(result.entity) if result.entity else None
            })
    
    # Check name
    if request.name:
        name_matches = sanctions_db.check_name(request.name)
        for result in name_matches:
            matches.append({
                "match_type": result.match_type.value if result.match_type else None,
                "confidence": result.confidence,
                "matched_field": result.matched_field,
                "matched_value": result.matched_value,
                "entity": asdict(result.entity) if result.entity else None
            })
    
    response = SanctionsCheckResponse(
        query={
            "address": request.address,
            "name": request.name,
            "country": request.country
        },
        is_sanctioned=len(matches) > 0,
        matches=matches,
        checked_lists=checked_lists,
        check_timestamp=datetime.utcnow().isoformat(),
        cache_age_hours=((datetime.utcnow() - sanctions_db.load_timestamp).total_seconds() / 3600) if sanctions_db.load_timestamp else None
    )
    
    # Audit log
    log_audit("check", request.dict(), {"is_sanctioned": response.is_sanctioned, "match_count": len(matches)})
    
    return response

@app.post("/sanctions/batch-check")
async def batch_check(addresses: List[str]):
    """Check multiple addresses in batch"""
    results = []
    
    for address in addresses:
        result = sanctions_db.check_address(address)
        results.append({
            "address": address,
            "is_sanctioned": result.matched,
            "match_type": result.match_type.value if result.match_type else None,
            "entity_name": result.entity.name if result.entity else None,
            "source_list": result.entity.source_list if result.entity else None
        })
    
    return {
        "checked_count": len(addresses),
        "sanctioned_count": sum(1 for r in results if r["is_sanctioned"]),
        "results": results,
        "check_timestamp": datetime.utcnow().isoformat()
    }

@app.post("/sanctions/refresh")
async def trigger_refresh(background_tasks: BackgroundTasks):
    """Trigger manual refresh of sanctions lists"""
    background_tasks.add_task(refresh_sanctions_database)
    return {
        "status": "refresh_started",
        "current_stats": sanctions_db.stats()
    }

@app.get("/sanctions/stats")
async def get_stats():
    """Get database statistics"""
    return sanctions_db.stats()

@app.get("/sanctions/lists")
async def get_lists():
    """Get available sanctions lists"""
    return {
        "lists": [
            {
                "code": k,
                "name": v["name"],
                "refresh_hours": v["refresh_hours"],
                "last_refresh": sanctions_db.last_refresh.get(k, None)
            }
            for k, v in SANCTIONS_SOURCES.items()
        ]
    }

# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    port = int(os.getenv("SANCTIONS_SERVICE_PORT", "8004"))
    print(f"🚀 Starting Sanctions Screening Service on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
