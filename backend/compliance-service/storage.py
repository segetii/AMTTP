"""
AMTTP Storage Layer
Unified storage interface for MongoDB, Redis, MinIO, and IPFS.

Components:
- MongoDB: Profiles, decisions, audit logs (motor async driver)
- Redis: Rate limiting, caching, real-time counters
- MinIO: KYC documents, evidence files, reports
- IPFS: Immutable audit hashes, compliance proofs
"""

import os
import json
import hashlib
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any, BinaryIO
from dataclasses import dataclass, asdict
from enum import Enum
from pathlib import Path
import logging

logger = logging.getLogger("storage")

# ═══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════

# MongoDB (Docker default: admin:changeme)
MONGODB_URL = os.getenv("MONGODB_URL", "mongodb://admin:changeme@localhost:27017")
MONGODB_DB = os.getenv("MONGODB_DB", "amttp")

# Redis
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

# MinIO (Docker default: localtest:localtest123)
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "localhost:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "localtest")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "localtest123")
MINIO_SECURE = os.getenv("MINIO_SECURE", "false").lower() == "true"
MINIO_BUCKET = os.getenv("MINIO_BUCKET", "amttp-documents")

# IPFS
IPFS_API_URL = os.getenv("IPFS_API_URL", "http://localhost:5001")

# ═══════════════════════════════════════════════════════════════════════════════
# OPTIONAL IMPORTS
# ═══════════════════════════════════════════════════════════════════════════════

try:
    from motor.motor_asyncio import AsyncIOMotorClient
    HAS_MOTOR = True
except ImportError:
    HAS_MOTOR = False
    logger.warning("motor not installed - MongoDB disabled")

try:
    import redis.asyncio as aioredis
    HAS_REDIS = True
except ImportError:
    try:
        import aioredis
        HAS_REDIS = True
    except ImportError:
        HAS_REDIS = False
        logger.warning("redis/aioredis not installed - Redis disabled")

try:
    from minio import Minio
    from minio.error import S3Error
    HAS_MINIO = True
except ImportError:
    HAS_MINIO = False
    logger.warning("minio not installed - MinIO disabled")

try:
    import ipfshttpclient
    HAS_IPFS = True
except ImportError:
    HAS_IPFS = False
    logger.warning("ipfshttpclient not installed - IPFS disabled")

# ═══════════════════════════════════════════════════════════════════════════════
# MONGODB CLIENT
# ═══════════════════════════════════════════════════════════════════════════════

class MongoDBClient:
    """MongoDB async client for document storage"""
    
    def __init__(self):
        self.client: Optional[AsyncIOMotorClient] = None
        self.db = None
    
    async def connect(self):
        if not HAS_MOTOR:
            logger.error("motor not installed")
            return False
        
        try:
            self.client = AsyncIOMotorClient(
                MONGODB_URL,
                serverSelectionTimeoutMS=5000,
                connectTimeoutMS=5000
            )
            self.db = self.client[MONGODB_DB]
            # Test connection
            await self.client.admin.command('ping')
            logger.info("Connected to MongoDB: %s/%s", MONGODB_URL, MONGODB_DB)
            
            # Create indexes
            await self._create_indexes()
            return True
        except Exception as e:
            logger.error("MongoDB connection failed: %s", e)
            return False
    
    async def _create_indexes(self):
        """Create indexes for efficient queries"""
        # Profiles
        await self.db.profiles.create_index("address", unique=True)
        await self.db.profiles.create_index("entity_type")
        await self.db.profiles.create_index("updated_at")
        
        # Decisions
        await self.db.decisions.create_index("decision_id", unique=True)
        await self.db.decisions.create_index("from_address")
        await self.db.decisions.create_index("to_address")
        await self.db.decisions.create_index([("timestamp", -1)])
        await self.db.decisions.create_index("action")
        
        # Profile history
        await self.db.profile_history.create_index([("address", 1), ("version", -1)])
        
        # API keys
        await self.db.api_keys.create_index("key_hash", unique=True)
        
        # Audit logs
        await self.db.audit_logs.create_index([("timestamp", -1)])
        await self.db.audit_logs.create_index("event_type")
        await self.db.audit_logs.create_index("address")
        
        logger.info("MongoDB indexes created")
    
    async def close(self):
        if self.client:
            self.client.close()
    
    # ─────────────────────────────────────────────────────────────────────────
    # PROFILES
    # ─────────────────────────────────────────────────────────────────────────
    
    async def get_profile(self, address: str) -> Optional[Dict]:
        if not self.db:
            return None
        doc = await self.db.profiles.find_one({"address": address.lower()})
        if doc:
            doc.pop("_id", None)
        return doc
    
    async def save_profile(self, profile: Dict, changed_by: str = "system", reason: str = "") -> Dict:
        if not self.db:
            return profile
        
        address = profile["address"].lower()
        profile["address"] = address
        
        # Get existing for versioning
        existing = await self.db.profiles.find_one({"address": address})
        
        if existing:
            # Save to history
            history_doc = {
                "address": address,
                "version": existing.get("version", 1),
                "profile_data": existing,
                "changed_at": datetime.now(timezone.utc),
                "changed_by": changed_by,
                "change_reason": reason
            }
            history_doc["profile_data"].pop("_id", None)
            await self.db.profile_history.insert_one(history_doc)
            
            profile["version"] = existing.get("version", 1) + 1
        else:
            profile["version"] = 1
            profile["created_at"] = datetime.now(timezone.utc)
        
        profile["updated_at"] = datetime.now(timezone.utc)
        
        await self.db.profiles.update_one(
            {"address": address},
            {"$set": profile},
            upsert=True
        )
        
        return profile
    
    async def list_profiles(self, limit: int = 50, skip: int = 0, 
                           entity_type: Optional[str] = None) -> List[Dict]:
        if not self.db:
            return []
        
        query = {}
        if entity_type:
            query["entity_type"] = entity_type
        
        cursor = self.db.profiles.find(query).sort("updated_at", -1).skip(skip).limit(limit)
        profiles = []
        async for doc in cursor:
            doc.pop("_id", None)
            profiles.append(doc)
        return profiles
    
    async def get_profile_history(self, address: str, limit: int = 10) -> List[Dict]:
        if not self.db:
            return []
        
        cursor = self.db.profile_history.find(
            {"address": address.lower()}
        ).sort("version", -1).limit(limit)
        
        history = []
        async for doc in cursor:
            doc.pop("_id", None)
            history.append(doc)
        return history
    
    # ─────────────────────────────────────────────────────────────────────────
    # DECISIONS
    # ─────────────────────────────────────────────────────────────────────────
    
    async def save_decision(self, decision: Dict) -> str:
        if not self.db:
            return decision.get("decision_id", "")
        
        decision["_created_at"] = datetime.now(timezone.utc)
        await self.db.decisions.insert_one(decision)
        return decision.get("decision_id", "")
    
    async def get_decision(self, decision_id: str) -> Optional[Dict]:
        if not self.db:
            return None
        
        doc = await self.db.decisions.find_one({"decision_id": decision_id})
        if doc:
            doc.pop("_id", None)
        return doc
    
    async def list_decisions(self, limit: int = 50, address: Optional[str] = None,
                            action: Optional[str] = None,
                            start_date: Optional[datetime] = None,
                            end_date: Optional[datetime] = None) -> List[Dict]:
        if not self.db:
            return []
        
        query = {}
        if address:
            query["$or"] = [
                {"from_address": address.lower()},
                {"to_address": address.lower()}
            ]
        if action:
            query["action"] = action
        if start_date or end_date:
            query["timestamp"] = {}
            if start_date:
                query["timestamp"]["$gte"] = start_date.isoformat()
            if end_date:
                query["timestamp"]["$lte"] = end_date.isoformat()
        
        cursor = self.db.decisions.find(query).sort("timestamp", -1).limit(limit)
        decisions = []
        async for doc in cursor:
            doc.pop("_id", None)
            decisions.append(doc)
        return decisions
    
    async def get_decision_stats(self, address: Optional[str] = None,
                                  days: int = 30) -> Dict:
        """Get aggregated decision statistics"""
        if not self.db:
            return {}
        
        start_date = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        
        match_stage = {"timestamp": {"$gte": start_date}}
        if address:
            match_stage["$or"] = [
                {"from_address": address.lower()},
                {"to_address": address.lower()}
            ]
        
        pipeline = [
            {"$match": match_stage},
            {"$group": {
                "_id": "$action",
                "count": {"$sum": 1},
                "total_value": {"$sum": "$value_eth"},
                "avg_risk_score": {"$avg": "$risk_score"}
            }}
        ]
        
        stats = {"by_action": {}, "total": 0, "total_value": 0}
        async for doc in self.db.decisions.aggregate(pipeline):
            action = doc["_id"]
            stats["by_action"][action] = {
                "count": doc["count"],
                "total_value": doc["total_value"],
                "avg_risk_score": doc["avg_risk_score"]
            }
            stats["total"] += doc["count"]
            stats["total_value"] += doc["total_value"]
        
        return stats
    
    # ─────────────────────────────────────────────────────────────────────────
    # API KEYS
    # ─────────────────────────────────────────────────────────────────────────
    
    async def get_api_key(self, key_hash: str) -> Optional[Dict]:
        if not self.db:
            return None
        
        doc = await self.db.api_keys.find_one({"key_hash": key_hash, "active": True})
        if doc:
            doc.pop("_id", None)
        return doc
    
    async def save_api_key(self, key_data: Dict):
        if not self.db:
            return
        
        key_data["updated_at"] = datetime.now(timezone.utc)
        await self.db.api_keys.update_one(
            {"key_hash": key_data["key_hash"]},
            {"$set": key_data},
            upsert=True
        )
    
    async def list_api_keys(self, org_id: Optional[str] = None) -> List[Dict]:
        if not self.db:
            return []
        
        query = {"active": True}
        if org_id:
            query["org_id"] = org_id
        
        cursor = self.db.api_keys.find(query)
        keys = []
        async for doc in cursor:
            doc.pop("_id", None)
            # Don't expose full hash
            doc["key_hash"] = doc["key_hash"][:8] + "..."
            keys.append(doc)
        return keys
    
    # ─────────────────────────────────────────────────────────────────────────
    # AUDIT LOGS
    # ─────────────────────────────────────────────────────────────────────────
    
    async def log_audit_event(self, event_type: str, address: Optional[str],
                              details: Dict, user: str = "system"):
        if not self.db:
            return
        
        doc = {
            "event_type": event_type,
            "address": address.lower() if address else None,
            "details": details,
            "user": user,
            "timestamp": datetime.now(timezone.utc),
            "ip_address": details.get("ip_address"),
            "request_id": details.get("request_id")
        }
        await self.db.audit_logs.insert_one(doc)
    
    async def get_audit_logs(self, address: Optional[str] = None,
                             event_type: Optional[str] = None,
                             limit: int = 100) -> List[Dict]:
        if not self.db:
            return []
        
        query = {}
        if address:
            query["address"] = address.lower()
        if event_type:
            query["event_type"] = event_type
        
        cursor = self.db.audit_logs.find(query).sort("timestamp", -1).limit(limit)
        logs = []
        async for doc in cursor:
            doc.pop("_id", None)
            logs.append(doc)
        return logs


# ═══════════════════════════════════════════════════════════════════════════════
# REDIS CLIENT
# ═══════════════════════════════════════════════════════════════════════════════

class RedisClient:
    """Redis client for caching and rate limiting"""
    
    def __init__(self):
        self.client = None
    
    async def connect(self):
        if not HAS_REDIS:
            logger.error("redis not installed")
            return False
        
        try:
            self.client = aioredis.from_url(REDIS_URL, decode_responses=True)
            await self.client.ping()
            logger.info("Connected to Redis: %s", REDIS_URL)
            return True
        except Exception as e:
            logger.error("Redis connection failed: %s", e)
            return False
    
    async def close(self):
        if self.client:
            await self.client.close()
    
    # ─────────────────────────────────────────────────────────────────────────
    # RATE LIMITING
    # ─────────────────────────────────────────────────────────────────────────
    
    async def check_rate_limit(self, key: str, limit: int = 100, 
                                window_seconds: int = 60) -> tuple[bool, int]:
        """
        Check and increment rate limit counter.
        Returns (allowed, remaining_requests)
        """
        if not self.client:
            return True, limit
        
        rate_key = f"rate:{key}"
        
        pipe = self.client.pipeline()
        pipe.incr(rate_key)
        pipe.ttl(rate_key)
        results = await pipe.execute()
        
        count = results[0]
        ttl = results[1]
        
        if ttl == -1:  # No expiry set
            await self.client.expire(rate_key, window_seconds)
        
        remaining = max(0, limit - count)
        allowed = count <= limit
        
        return allowed, remaining
    
    async def get_rate_limit_status(self, key: str) -> Dict:
        """Get current rate limit status without incrementing"""
        if not self.client:
            return {"count": 0, "ttl": 0}
        
        rate_key = f"rate:{key}"
        
        pipe = self.client.pipeline()
        pipe.get(rate_key)
        pipe.ttl(rate_key)
        results = await pipe.execute()
        
        return {
            "count": int(results[0] or 0),
            "ttl": max(0, results[1])
        }
    
    # ─────────────────────────────────────────────────────────────────────────
    # CACHING
    # ─────────────────────────────────────────────────────────────────────────
    
    async def cache_get(self, key: str) -> Optional[Dict]:
        """Get cached value"""
        if not self.client:
            return None
        
        value = await self.client.get(f"cache:{key}")
        if value:
            return json.loads(value)
        return None
    
    async def cache_set(self, key: str, value: Dict, ttl_seconds: int = 300):
        """Set cached value with TTL"""
        if not self.client:
            return
        
        await self.client.setex(
            f"cache:{key}",
            ttl_seconds,
            json.dumps(value, default=str)
        )
    
    async def cache_delete(self, key: str):
        """Delete cached value"""
        if not self.client:
            return
        
        await self.client.delete(f"cache:{key}")
    
    async def cache_profile(self, address: str, profile: Dict, ttl: int = 300):
        """Cache profile data"""
        await self.cache_set(f"profile:{address.lower()}", profile, ttl)
    
    async def get_cached_profile(self, address: str) -> Optional[Dict]:
        """Get cached profile"""
        return await self.cache_get(f"profile:{address.lower()}")
    
    # ─────────────────────────────────────────────────────────────────────────
    # REAL-TIME COUNTERS
    # ─────────────────────────────────────────────────────────────────────────
    
    async def increment_counter(self, name: str, amount: float = 1) -> float:
        """Increment a counter and return new value"""
        if not self.client:
            return 0
        
        return await self.client.incrbyfloat(f"counter:{name}", amount)
    
    async def get_counter(self, name: str) -> float:
        """Get counter value"""
        if not self.client:
            return 0
        
        value = await self.client.get(f"counter:{name}")
        return float(value) if value else 0
    
    async def track_daily_volume(self, address: str, amount_eth: float):
        """Track daily transaction volume per address"""
        if not self.client:
            return
        
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        key = f"volume:daily:{address.lower()}:{today}"
        
        await self.client.incrbyfloat(key, amount_eth)
        await self.client.expire(key, 86400 * 2)  # Keep for 2 days
    
    async def get_daily_volume(self, address: str) -> float:
        """Get today's transaction volume for address"""
        if not self.client:
            return 0
        
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        key = f"volume:daily:{address.lower()}:{today}"
        
        value = await self.client.get(key)
        return float(value) if value else 0
    
    # ─────────────────────────────────────────────────────────────────────────
    # SESSION / LOCKS
    # ─────────────────────────────────────────────────────────────────────────
    
    async def acquire_lock(self, name: str, ttl_seconds: int = 30) -> bool:
        """Acquire a distributed lock"""
        if not self.client:
            return True
        
        return await self.client.set(
            f"lock:{name}",
            "1",
            nx=True,
            ex=ttl_seconds
        )
    
    async def release_lock(self, name: str):
        """Release a distributed lock"""
        if not self.client:
            return
        
        await self.client.delete(f"lock:{name}")


# ═══════════════════════════════════════════════════════════════════════════════
# MINIO CLIENT
# ═══════════════════════════════════════════════════════════════════════════════

class MinIOClient:
    """MinIO client for document storage"""
    
    def __init__(self):
        self.client: Optional[Minio] = None
    
    def connect(self) -> bool:
        if not HAS_MINIO:
            logger.error("minio not installed")
            return False
        
        try:
            self.client = Minio(
                MINIO_ENDPOINT,
                access_key=MINIO_ACCESS_KEY,
                secret_key=MINIO_SECRET_KEY,
                secure=MINIO_SECURE
            )
            
            # Ensure bucket exists
            if not self.client.bucket_exists(MINIO_BUCKET):
                self.client.make_bucket(MINIO_BUCKET)
            
            logger.info("Connected to MinIO: %s", MINIO_ENDPOINT)
            return True
        except Exception as e:
            logger.error("MinIO connection failed: %s", e)
            return False
    
    # ─────────────────────────────────────────────────────────────────────────
    # DOCUMENT STORAGE
    # ─────────────────────────────────────────────────────────────────────────
    
    def upload_document(self, object_name: str, file_path: str,
                        content_type: str = "application/octet-stream",
                        metadata: Optional[Dict] = None) -> str:
        """Upload a document file"""
        if not self.client:
            return ""
        
        try:
            self.client.fput_object(
                MINIO_BUCKET,
                object_name,
                file_path,
                content_type=content_type,
                metadata=metadata or {}
            )
            return f"{MINIO_BUCKET}/{object_name}"
        except S3Error as e:
            logger.error("MinIO upload failed: %s", e)
            return ""
    
    def upload_bytes(self, object_name: str, data: bytes,
                     content_type: str = "application/octet-stream",
                     metadata: Optional[Dict] = None) -> str:
        """Upload bytes directly"""
        if not self.client:
            return ""
        
        try:
            from io import BytesIO
            self.client.put_object(
                MINIO_BUCKET,
                object_name,
                BytesIO(data),
                length=len(data),
                content_type=content_type,
                metadata=metadata or {}
            )
            return f"{MINIO_BUCKET}/{object_name}"
        except S3Error as e:
            logger.error("MinIO upload failed: %s", e)
            return ""
    
    def download_document(self, object_name: str, file_path: str) -> bool:
        """Download a document to file"""
        if not self.client:
            return False
        
        try:
            self.client.fget_object(MINIO_BUCKET, object_name, file_path)
            return True
        except S3Error as e:
            logger.error("MinIO download failed: %s", e)
            return False
    
    def download_bytes(self, object_name: str) -> Optional[bytes]:
        """Download document as bytes"""
        if not self.client:
            return None
        
        try:
            response = self.client.get_object(MINIO_BUCKET, object_name)
            data = response.read()
            response.close()
            response.release_conn()
            return data
        except S3Error as e:
            logger.error("MinIO download failed: %s", e)
            return None
    
    def delete_document(self, object_name: str) -> bool:
        """Delete a document"""
        if not self.client:
            return False
        
        try:
            self.client.remove_object(MINIO_BUCKET, object_name)
            return True
        except S3Error as e:
            logger.error("MinIO delete failed: %s", e)
            return False
    
    def get_presigned_url(self, object_name: str, 
                          expires_hours: int = 1) -> Optional[str]:
        """Get a presigned URL for temporary access"""
        if not self.client:
            return None
        
        try:
            return self.client.presigned_get_object(
                MINIO_BUCKET,
                object_name,
                expires=timedelta(hours=expires_hours)
            )
        except S3Error as e:
            logger.error("MinIO presigned URL failed: %s", e)
            return None
    
    def list_documents(self, prefix: str = "", limit: int = 100) -> List[Dict]:
        """List documents with optional prefix filter"""
        if not self.client:
            return []
        
        try:
            objects = self.client.list_objects(
                MINIO_BUCKET,
                prefix=prefix,
                recursive=True
            )
            docs = []
            for obj in objects:
                if len(docs) >= limit:
                    break
                docs.append({
                    "name": obj.object_name,
                    "size": obj.size,
                    "modified": obj.last_modified.isoformat() if obj.last_modified else None,
                    "etag": obj.etag
                })
            return docs
        except S3Error as e:
            logger.error("MinIO list failed: %s", e)
            return []
    
    # ─────────────────────────────────────────────────────────────────────────
    # KYC DOCUMENT HELPERS
    # ─────────────────────────────────────────────────────────────────────────
    
    def store_kyc_document(self, address: str, doc_type: str, 
                           data: bytes, filename: str) -> str:
        """Store a KYC document for an address"""
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        object_name = f"kyc/{address.lower()}/{doc_type}/{timestamp}_{filename}"
        
        return self.upload_bytes(
            object_name,
            data,
            metadata={
                "address": address.lower(),
                "doc_type": doc_type,
                "original_filename": filename,
                "uploaded_at": datetime.now(timezone.utc).isoformat()
            }
        )
    
    def list_kyc_documents(self, address: str) -> List[Dict]:
        """List all KYC documents for an address"""
        return self.list_documents(prefix=f"kyc/{address.lower()}/")
    
    def store_evidence_file(self, decision_id: str, data: bytes, 
                            filename: str) -> str:
        """Store evidence file linked to a decision"""
        object_name = f"evidence/{decision_id}/{filename}"
        
        return self.upload_bytes(
            object_name,
            data,
            metadata={
                "decision_id": decision_id,
                "original_filename": filename,
                "uploaded_at": datetime.now(timezone.utc).isoformat()
            }
        )


# ═══════════════════════════════════════════════════════════════════════════════
# IPFS CLIENT
# ═══════════════════════════════════════════════════════════════════════════════

class IPFSClient:
    """IPFS client for immutable audit trail - uses HTTP API directly for compatibility"""
    
    def __init__(self):
        self.client = None
        self.api_url = IPFS_API_URL.rstrip('/')
        self._use_http = False  # Flag to use HTTP API directly
    
    def connect(self) -> bool:
        if not HAS_IPFS:
            # Try HTTP API directly
            self._use_http = True
            try:
                import requests
                resp = requests.post(f"{self.api_url}/api/v0/id", timeout=5)
                if resp.status_code == 200:
                    logger.info("Connected to IPFS via HTTP API: %s", self.api_url)
                    return True
            except Exception as e:
                logger.error("IPFS HTTP connection failed: %s", e)
            return False
        
        try:
            # Try standard client first
            self.client = ipfshttpclient.connect(IPFS_API_URL)
            logger.info("Connected to IPFS: %s", IPFS_API_URL)
            return True
        except Exception as e:
            # Version mismatch - fall back to HTTP API
            logger.warning("ipfshttpclient failed (%s), using HTTP API", e)
            self._use_http = True
            try:
                import requests
                resp = requests.post(f"{self.api_url}/api/v0/id", timeout=5)
                if resp.status_code == 200:
                    logger.info("Connected to IPFS via HTTP API fallback: %s", self.api_url)
                    return True
            except Exception as e2:
                logger.error("IPFS HTTP fallback failed: %s", e2)
            return False
    
    def close(self):
        if self.client:
            self.client.close()
    
    # ─────────────────────────────────────────────────────────────────────────
    # IMMUTABLE STORAGE
    # ─────────────────────────────────────────────────────────────────────────
    
    def add_json(self, data: Dict) -> Optional[str]:
        """Add JSON data to IPFS, return CID"""
        if not self.client:
            return None
        
        try:
            result = self.client.add_json(data)
            return result
        except Exception as e:
            logger.error("IPFS add failed: %s", e)
            return None
    
    def add_bytes(self, data: bytes) -> Optional[str]:
        """Add bytes to IPFS, return CID"""
        if not self.client:
            return None
        
        try:
            result = self.client.add_bytes(data)
            return result
        except Exception as e:
            logger.error("IPFS add failed: %s", e)
            return None
    
    def get_json(self, cid: str) -> Optional[Dict]:
        """Get JSON data from IPFS by CID"""
        if not self.client:
            return None
        
        try:
            return self.client.get_json(cid)
        except Exception as e:
            logger.error("IPFS get failed: %s", e)
            return None
    
    def get_bytes(self, cid: str) -> Optional[bytes]:
        """Get bytes from IPFS by CID"""
        if not self.client:
            return None
        
        try:
            return self.client.cat(cid)
        except Exception as e:
            logger.error("IPFS get failed: %s", e)
            return None
    
    def pin(self, cid: str) -> bool:
        """Pin content to prevent garbage collection"""
        if not self.client:
            return False
        
        try:
            self.client.pin.add(cid)
            return True
        except Exception as e:
            logger.error("IPFS pin failed: %s", e)
            return False
    
    # ─────────────────────────────────────────────────────────────────────────
    # AUDIT TRAIL HELPERS
    # ─────────────────────────────────────────────────────────────────────────
    
    def store_decision_proof(self, decision: Dict) -> Optional[str]:
        """
        Store a compliance decision as immutable proof.
        Returns IPFS CID that can be used to verify the decision later.
        """
        # Create a canonical hash of the decision
        proof = {
            "decision_id": decision.get("decision_id"),
            "timestamp": decision.get("timestamp"),
            "from_address": decision.get("from_address"),
            "to_address": decision.get("to_address"),
            "value_eth": decision.get("value_eth"),
            "action": decision.get("action"),
            "risk_score": decision.get("risk_score"),
            "reasons": decision.get("reasons", []),
            "proof_created_at": datetime.now(timezone.utc).isoformat(),
            "content_hash": hashlib.sha256(
                json.dumps(decision, sort_keys=True, default=str).encode()
            ).hexdigest()
        }
        
        cid = self.add_json(proof)
        if cid:
            self.pin(cid)
        return cid
    
    def verify_decision_proof(self, cid: str, decision: Dict) -> bool:
        """Verify a decision matches its IPFS proof"""
        proof = self.get_json(cid)
        if not proof:
            return False
        
        # Recalculate hash
        expected_hash = hashlib.sha256(
            json.dumps(decision, sort_keys=True, default=str).encode()
        ).hexdigest()
        
        return proof.get("content_hash") == expected_hash
    
    def store_profile_snapshot(self, profile: Dict, reason: str) -> Optional[str]:
        """Store a profile snapshot for audit purposes"""
        snapshot = {
            "address": profile.get("address"),
            "entity_type": profile.get("entity_type"),
            "kyc_level": profile.get("kyc_level"),
            "version": profile.get("version"),
            "snapshot_at": datetime.now(timezone.utc).isoformat(),
            "reason": reason,
            "content_hash": hashlib.sha256(
                json.dumps(profile, sort_keys=True, default=str).encode()
            ).hexdigest()
        }
        
        cid = self.add_json(snapshot)
        if cid:
            self.pin(cid)
        return cid


# ═══════════════════════════════════════════════════════════════════════════════
# UNIFIED STORAGE MANAGER
# ═══════════════════════════════════════════════════════════════════════════════

class StorageManager:
    """
    Unified storage manager that coordinates all storage backends.
    Provides a single interface for the orchestrator.
    """
    
    def __init__(self):
        self.mongo = MongoDBClient()
        self.redis = RedisClient()
        self.minio = MinIOClient()
        self.ipfs = IPFSClient()
        
        self._mongo_connected = False
        self._redis_connected = False
        self._minio_connected = False
        self._ipfs_connected = False
    
    async def connect_all(self) -> Dict[str, bool]:
        """Connect to all storage backends"""
        results = {}
        
        self._mongo_connected = await self.mongo.connect()
        results["mongodb"] = self._mongo_connected
        
        self._redis_connected = await self.redis.connect()
        results["redis"] = self._redis_connected
        
        self._minio_connected = self.minio.connect()
        results["minio"] = self._minio_connected
        
        self._ipfs_connected = self.ipfs.connect()
        results["ipfs"] = self._ipfs_connected
        
        return results
    
    async def close_all(self):
        """Close all connections"""
        await self.mongo.close()
        await self.redis.close()
        self.ipfs.close()
    
    def health_check(self) -> Dict[str, str]:
        """Check health of all storage backends"""
        return {
            "mongodb": "connected" if self._mongo_connected else "disconnected",
            "redis": "connected" if self._redis_connected else "disconnected",
            "minio": "connected" if self._minio_connected else "disconnected",
            "ipfs": "connected" if self._ipfs_connected else "disconnected"
        }
    
    # ─────────────────────────────────────────────────────────────────────────
    # HIGH-LEVEL OPERATIONS
    # ─────────────────────────────────────────────────────────────────────────
    
    async def get_profile(self, address: str) -> Optional[Dict]:
        """Get profile with Redis caching"""
        # Try cache first
        cached = await self.redis.get_cached_profile(address)
        if cached:
            return cached
        
        # Get from MongoDB
        profile = await self.mongo.get_profile(address)
        if profile:
            await self.redis.cache_profile(address, profile)
        
        return profile
    
    async def save_profile(self, profile: Dict, changed_by: str = "system",
                           reason: str = "", store_ipfs_proof: bool = False) -> Dict:
        """Save profile with cache invalidation and optional IPFS proof"""
        address = profile.get("address", "").lower()
        
        # Save to MongoDB
        saved = await self.mongo.save_profile(profile, changed_by, reason)
        
        # Invalidate cache
        await self.redis.cache_delete(f"profile:{address}")
        
        # Store IPFS proof if requested
        if store_ipfs_proof and self._ipfs_connected:
            cid = self.ipfs.store_profile_snapshot(saved, reason)
            if cid:
                saved["ipfs_proof_cid"] = cid
                await self.mongo.log_audit_event(
                    "profile_proof_stored",
                    address,
                    {"cid": cid, "reason": reason},
                    changed_by
                )
        
        return saved
    
    async def save_decision(self, decision: Dict, 
                            store_ipfs_proof: bool = True) -> str:
        """Save decision with IPFS proof"""
        # Save to MongoDB
        decision_id = await self.mongo.save_decision(decision)
        
        # Track volume in Redis
        await self.redis.track_daily_volume(
            decision.get("from_address", ""),
            decision.get("value_eth", 0)
        )
        
        # Store IPFS proof
        if store_ipfs_proof and self._ipfs_connected:
            cid = self.ipfs.store_decision_proof(decision)
            if cid:
                # Update decision with CID
                await self.mongo.db.decisions.update_one(
                    {"decision_id": decision_id},
                    {"$set": {"ipfs_proof_cid": cid}}
                )
        
        return decision_id
    
    async def check_rate_limit(self, key: str, limit: int = 100) -> tuple[bool, int]:
        """Check rate limit using Redis"""
        return await self.redis.check_rate_limit(key, limit)
    
    async def get_daily_volume(self, address: str) -> float:
        """Get today's transaction volume"""
        return await self.redis.get_daily_volume(address)


# ═══════════════════════════════════════════════════════════════════════════════
# SINGLETON INSTANCE
# ═══════════════════════════════════════════════════════════════════════════════

_storage: Optional[StorageManager] = None

async def get_storage() -> StorageManager:
    """Get or create storage manager singleton"""
    global _storage
    if _storage is None:
        _storage = StorageManager()
        results = await _storage.connect_all()
        logger.info("Storage connections: %s", results)
    return _storage

async def close_storage():
    """Close storage connections"""
    global _storage
    if _storage:
        await _storage.close_all()
        _storage = None
