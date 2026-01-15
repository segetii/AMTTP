"""
AMTTP Transaction Monitoring Rules Engine
AML pattern detection for structuring, layering, round-trips, and suspicious patterns

Detection Patterns:
1. Structuring (Smurfing) - Breaking up transactions to avoid thresholds
2. Round-trip transactions - Money returning to origin
3. Layering - Complex transaction chains to obscure origin
4. Rapid movement - Fast in/out patterns
5. Velocity anomalies - Unusual transaction frequency
6. Value clustering - Transactions just below thresholds
"""

import os
import json
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any, Set, Tuple
from dataclasses import dataclass, field, asdict
from enum import Enum
from collections import defaultdict
import statistics
import math

import uvicorn
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from contextlib import asynccontextmanager

# ═══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════

DATA_DIR = Path(__file__).parent / "data" / "monitoring"
ALERTS_FILE = DATA_DIR / "alerts.json"
RULES_FILE = DATA_DIR / "rules.json"

# Thresholds (configurable)
THRESHOLDS = {
    # Structuring detection
    "structuring_window_hours": 24,
    "structuring_threshold_eth": 10.0,  # Regulatory threshold
    "structuring_min_transactions": 3,
    "structuring_max_individual_pct": 0.90,  # Max 90% of threshold per tx
    
    # Round-trip detection
    "roundtrip_window_hours": 72,
    "roundtrip_min_return_pct": 0.80,  # 80% of original amount
    "roundtrip_max_hops": 5,
    
    # Layering detection
    "layering_window_hours": 48,
    "layering_min_hops": 3,
    "layering_value_decay_tolerance": 0.15,  # 15% value loss per hop
    
    # Velocity
    "velocity_window_hours": 1,
    "velocity_max_transactions": 10,
    "velocity_daily_max": 50,
    
    # Value clustering
    "clustering_threshold_eth": 10.0,
    "clustering_range_pct": 0.10,  # Within 10% of threshold
}

# ═══════════════════════════════════════════════════════════════════════════════
# DATA MODELS
# ═══════════════════════════════════════════════════════════════════════════════

class RuleType(str, Enum):
    STRUCTURING = "STRUCTURING"
    ROUND_TRIP = "ROUND_TRIP"
    LAYERING = "LAYERING"
    RAPID_MOVEMENT = "RAPID_MOVEMENT"
    VELOCITY_ANOMALY = "VELOCITY_ANOMALY"
    VALUE_CLUSTERING = "VALUE_CLUSTERING"
    HIGH_VALUE = "HIGH_VALUE"
    UNUSUAL_TIME = "UNUSUAL_TIME"
    NEW_COUNTERPARTY = "NEW_COUNTERPARTY"
    DORMANT_REACTIVATION = "DORMANT_REACTIVATION"

class AlertSeverity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"

class AlertStatus(str, Enum):
    OPEN = "OPEN"
    INVESTIGATING = "INVESTIGATING"
    ESCALATED = "ESCALATED"
    CLOSED_FALSE_POSITIVE = "CLOSED_FALSE_POSITIVE"
    CLOSED_SAR_FILED = "CLOSED_SAR_FILED"
    CLOSED_NO_ACTION = "CLOSED_NO_ACTION"

@dataclass
class Transaction:
    tx_hash: str
    from_address: str
    to_address: str
    value_eth: float
    timestamp: datetime
    block_number: int
    chain: str = "ethereum"
    gas_used: int = 0
    gas_price_gwei: float = 0
    
    def __hash__(self):
        return hash(self.tx_hash)

@dataclass
class MonitoringAlert:
    id: str
    rule_type: RuleType
    severity: AlertSeverity
    status: AlertStatus
    address: str
    description: str
    transactions: List[str]  # tx hashes
    created_at: datetime
    updated_at: datetime
    metadata: Dict[str, Any] = field(default_factory=dict)
    notes: List[str] = field(default_factory=list)
    assigned_to: Optional[str] = None

class TransactionInput(BaseModel):
    tx_hash: str
    from_address: str
    to_address: str
    value_eth: float
    timestamp: str
    block_number: int
    chain: str = "ethereum"
    gas_used: int = 0
    gas_price_gwei: float = 0

class MonitorRequest(BaseModel):
    transactions: List[TransactionInput]

class RuleResult(BaseModel):
    rule_type: str
    triggered: bool
    severity: Optional[str] = None
    confidence: float = 0.0
    description: str = ""
    evidence: Dict[str, Any] = {}

# ═══════════════════════════════════════════════════════════════════════════════
# TRANSACTION HISTORY STORE
# ═══════════════════════════════════════════════════════════════════════════════

class TransactionHistoryStore:
    def __init__(self):
        self.transactions: Dict[str, Transaction] = {}  # tx_hash -> Transaction
        self.by_address: Dict[str, List[str]] = defaultdict(list)  # address -> [tx_hashes]
        self.by_time: List[Tuple[datetime, str]] = []  # [(timestamp, tx_hash)]
        
    def add_transaction(self, tx: Transaction):
        if tx.tx_hash in self.transactions:
            return
        
        self.transactions[tx.tx_hash] = tx
        self.by_address[tx.from_address.lower()].append(tx.tx_hash)
        self.by_address[tx.to_address.lower()].append(tx.tx_hash)
        self.by_time.append((tx.timestamp, tx.tx_hash))
        self.by_time.sort(key=lambda x: x[0])
    
    def get_transactions_for_address(self, address: str, hours: int = 24) -> List[Transaction]:
        address = address.lower()
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        
        tx_hashes = self.by_address.get(address, [])
        txs = []
        for tx_hash in tx_hashes:
            tx = self.transactions.get(tx_hash)
            if tx and tx.timestamp >= cutoff:
                txs.append(tx)
        
        return sorted(txs, key=lambda x: x.timestamp)
    
    def get_outgoing(self, address: str, hours: int = 24) -> List[Transaction]:
        address = address.lower()
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        
        result = []
        for tx_hash in self.by_address.get(address, []):
            tx = self.transactions.get(tx_hash)
            if tx and tx.from_address.lower() == address and tx.timestamp >= cutoff:
                result.append(tx)
        
        return sorted(result, key=lambda x: x.timestamp)
    
    def get_incoming(self, address: str, hours: int = 24) -> List[Transaction]:
        address = address.lower()
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        
        result = []
        for tx_hash in self.by_address.get(address, []):
            tx = self.transactions.get(tx_hash)
            if tx and tx.to_address.lower() == address and tx.timestamp >= cutoff:
                result.append(tx)
        
        return sorted(result, key=lambda x: x.timestamp)
    
    def trace_path(self, from_addr: str, to_addr: str, max_hops: int = 5, hours: int = 72) -> List[List[Transaction]]:
        """Find transaction paths from one address to another"""
        from_addr = from_addr.lower()
        to_addr = to_addr.lower()
        
        paths = []
        self._dfs_path(from_addr, to_addr, [], set(), max_hops, hours, paths)
        return paths
    
    def _dfs_path(self, current: str, target: str, path: List[Transaction], 
                  visited: Set[str], max_hops: int, hours: int, paths: List):
        if len(path) > max_hops:
            return
        
        if current == target and len(path) > 0:
            paths.append(path.copy())
            return
        
        if current in visited:
            return
        
        visited.add(current)
        
        for tx in self.get_outgoing(current, hours):
            path.append(tx)
            self._dfs_path(tx.to_address.lower(), target, path, visited, max_hops, hours, paths)
            path.pop()
        
        visited.remove(current)

# Global store
tx_store = TransactionHistoryStore()
alerts_store: Dict[str, MonitoringAlert] = {}

# ═══════════════════════════════════════════════════════════════════════════════
# DETECTION RULES
# ═══════════════════════════════════════════════════════════════════════════════

def detect_structuring(address: str, new_tx: Transaction) -> Optional[RuleResult]:
    """
    Detect structuring (smurfing) - breaking up transactions to avoid thresholds
    
    Indicators:
    - Multiple transactions just below reporting threshold
    - Total exceeds threshold when combined
    - Short time window
    """
    window_hours = THRESHOLDS["structuring_window_hours"]
    threshold = THRESHOLDS["structuring_threshold_eth"]
    min_txs = THRESHOLDS["structuring_min_transactions"]
    max_pct = THRESHOLDS["structuring_max_individual_pct"]
    
    # Get recent outgoing transactions
    recent_txs = tx_store.get_outgoing(address, window_hours)
    if len(recent_txs) < min_txs:
        return None
    
    # Check if individual transactions are below threshold but total exceeds
    total_value = sum(tx.value_eth for tx in recent_txs)
    individual_below_threshold = all(tx.value_eth < threshold * max_pct for tx in recent_txs)
    total_exceeds = total_value >= threshold
    
    if individual_below_threshold and total_exceeds:
        # Calculate confidence based on how close to threshold individual txs are
        avg_pct = statistics.mean(tx.value_eth / threshold for tx in recent_txs)
        confidence = min(0.95, avg_pct * 1.2)  # Higher avg = higher confidence
        
        # Determine severity
        if total_value >= threshold * 3:
            severity = AlertSeverity.CRITICAL
        elif total_value >= threshold * 2:
            severity = AlertSeverity.HIGH
        else:
            severity = AlertSeverity.MEDIUM
        
        return RuleResult(
            rule_type=RuleType.STRUCTURING.value,
            triggered=True,
            severity=severity.value,
            confidence=confidence,
            description=f"Potential structuring detected: {len(recent_txs)} transactions totaling {total_value:.2f} ETH, each below {threshold * max_pct:.2f} ETH threshold",
            evidence={
                "transaction_count": len(recent_txs),
                "total_value_eth": total_value,
                "threshold_eth": threshold,
                "window_hours": window_hours,
                "individual_values": [tx.value_eth for tx in recent_txs],
                "tx_hashes": [tx.tx_hash for tx in recent_txs]
            }
        )
    
    return None

def detect_round_trip(address: str, new_tx: Transaction) -> Optional[RuleResult]:
    """
    Detect round-trip transactions - money returning to origin
    
    Indicators:
    - Funds sent out and returned within time window
    - May go through intermediaries
    """
    window_hours = THRESHOLDS["roundtrip_window_hours"]
    min_return_pct = THRESHOLDS["roundtrip_min_return_pct"]
    max_hops = THRESHOLDS["roundtrip_max_hops"]
    
    address = address.lower()
    
    # Get outgoing transactions
    outgoing = tx_store.get_outgoing(address, window_hours)
    
    for out_tx in outgoing:
        sent_value = out_tx.value_eth
        destination = out_tx.to_address.lower()
        
        # Look for paths back to origin
        paths = tx_store.trace_path(destination, address, max_hops, window_hours)
        
        for path in paths:
            if not path:
                continue
            
            # Calculate returned value (accounting for gas/fees)
            returned_value = path[-1].value_eth
            
            if returned_value >= sent_value * min_return_pct:
                hop_count = len(path)
                confidence = 0.9 - (hop_count * 0.1)  # Lower confidence for more hops
                
                severity = AlertSeverity.HIGH if hop_count <= 2 else AlertSeverity.MEDIUM
                
                return RuleResult(
                    rule_type=RuleType.ROUND_TRIP.value,
                    triggered=True,
                    severity=severity.value,
                    confidence=max(0.5, confidence),
                    description=f"Round-trip detected: {sent_value:.2f} ETH sent, {returned_value:.2f} ETH returned via {hop_count} hop(s)",
                    evidence={
                        "sent_value_eth": sent_value,
                        "returned_value_eth": returned_value,
                        "return_percentage": returned_value / sent_value * 100,
                        "hop_count": hop_count,
                        "path": [tx.tx_hash for tx in [out_tx] + path],
                        "intermediaries": [tx.to_address for tx in path[:-1]]
                    }
                )
    
    return None

def detect_layering(address: str, new_tx: Transaction) -> Optional[RuleResult]:
    """
    Detect layering - complex transaction chains to obscure fund origin
    
    Indicators:
    - Multiple rapid hops
    - Value approximately preserved (minus fees)
    - Quick turnaround at each hop
    """
    window_hours = THRESHOLDS["layering_window_hours"]
    min_hops = THRESHOLDS["layering_min_hops"]
    value_tolerance = THRESHOLDS["layering_value_decay_tolerance"]
    
    address = address.lower()
    
    # Get recent incoming
    incoming = tx_store.get_incoming(address, window_hours)
    
    for in_tx in incoming:
        # Check if funds are quickly moved out
        outgoing = tx_store.get_outgoing(address, 2)  # 2 hours for quick turnaround
        
        for out_tx in outgoing:
            if out_tx.timestamp <= in_tx.timestamp:
                continue
            
            time_diff = (out_tx.timestamp - in_tx.timestamp).total_seconds() / 3600
            value_diff = abs(in_tx.value_eth - out_tx.value_eth) / in_tx.value_eth
            
            # Quick turnaround with value preserved
            if time_diff < 1 and value_diff < value_tolerance:
                # Trace backwards to find the chain
                chain_length = 1
                current_addr = in_tx.from_address.lower()
                chain_txs = [in_tx]
                
                for _ in range(min_hops + 2):
                    prev_incoming = tx_store.get_incoming(current_addr, window_hours)
                    matching = [tx for tx in prev_incoming 
                               if abs(tx.value_eth - in_tx.value_eth) / in_tx.value_eth < value_tolerance * (chain_length + 1)]
                    
                    if matching:
                        chain_txs.insert(0, matching[0])
                        current_addr = matching[0].from_address.lower()
                        chain_length += 1
                    else:
                        break
                
                if chain_length >= min_hops:
                    confidence = min(0.95, 0.6 + (chain_length - min_hops) * 0.1)
                    
                    return RuleResult(
                        rule_type=RuleType.LAYERING.value,
                        triggered=True,
                        severity=AlertSeverity.HIGH.value,
                        confidence=confidence,
                        description=f"Layering pattern detected: {chain_length}-hop chain with {in_tx.value_eth:.2f} ETH, quick turnarounds",
                        evidence={
                            "chain_length": chain_length,
                            "value_eth": in_tx.value_eth,
                            "avg_turnaround_hours": time_diff,
                            "value_preserved_pct": (1 - value_diff) * 100,
                            "tx_hashes": [tx.tx_hash for tx in chain_txs]
                        }
                    )
    
    return None

def detect_velocity_anomaly(address: str, new_tx: Transaction) -> Optional[RuleResult]:
    """
    Detect unusual transaction velocity
    """
    hourly_max = THRESHOLDS["velocity_max_transactions"]
    daily_max = THRESHOLDS["velocity_daily_max"]
    
    hourly_txs = tx_store.get_transactions_for_address(address, 1)
    daily_txs = tx_store.get_transactions_for_address(address, 24)
    
    if len(hourly_txs) > hourly_max:
        confidence = min(0.95, 0.7 + (len(hourly_txs) - hourly_max) * 0.05)
        
        return RuleResult(
            rule_type=RuleType.VELOCITY_ANOMALY.value,
            triggered=True,
            severity=AlertSeverity.MEDIUM.value,
            confidence=confidence,
            description=f"Velocity anomaly: {len(hourly_txs)} transactions in last hour (threshold: {hourly_max})",
            evidence={
                "hourly_count": len(hourly_txs),
                "hourly_threshold": hourly_max,
                "daily_count": len(daily_txs),
                "tx_hashes": [tx.tx_hash for tx in hourly_txs]
            }
        )
    
    if len(daily_txs) > daily_max:
        return RuleResult(
            rule_type=RuleType.VELOCITY_ANOMALY.value,
            triggered=True,
            severity=AlertSeverity.LOW.value,
            confidence=0.7,
            description=f"Daily velocity exceeded: {len(daily_txs)} transactions (threshold: {daily_max})",
            evidence={
                "daily_count": len(daily_txs),
                "daily_threshold": daily_max
            }
        )
    
    return None

def detect_value_clustering(address: str, new_tx: Transaction) -> Optional[RuleResult]:
    """
    Detect transactions clustering just below thresholds
    """
    threshold = THRESHOLDS["clustering_threshold_eth"]
    range_pct = THRESHOLDS["clustering_range_pct"]
    
    lower_bound = threshold * (1 - range_pct)
    upper_bound = threshold
    
    recent_txs = tx_store.get_outgoing(address, 24)
    clustering_txs = [tx for tx in recent_txs if lower_bound <= tx.value_eth < upper_bound]
    
    if len(clustering_txs) >= 2:
        total_value = sum(tx.value_eth for tx in clustering_txs)
        confidence = min(0.9, 0.5 + len(clustering_txs) * 0.1)
        
        return RuleResult(
            rule_type=RuleType.VALUE_CLUSTERING.value,
            triggered=True,
            severity=AlertSeverity.MEDIUM.value,
            confidence=confidence,
            description=f"Value clustering detected: {len(clustering_txs)} transactions between {lower_bound:.2f} and {upper_bound:.2f} ETH",
            evidence={
                "transaction_count": len(clustering_txs),
                "threshold_eth": threshold,
                "range_lower": lower_bound,
                "range_upper": upper_bound,
                "values": [tx.value_eth for tx in clustering_txs],
                "total_value": total_value,
                "tx_hashes": [tx.tx_hash for tx in clustering_txs]
            }
        )
    
    return None

def detect_rapid_movement(address: str, new_tx: Transaction) -> Optional[RuleResult]:
    """
    Detect rapid in/out movements (pass-through behavior)
    """
    address = address.lower()
    
    # Get recent transactions
    incoming = tx_store.get_incoming(address, 2)
    outgoing = tx_store.get_outgoing(address, 2)
    
    for in_tx in incoming:
        for out_tx in outgoing:
            if out_tx.timestamp <= in_tx.timestamp:
                continue
            
            time_diff_minutes = (out_tx.timestamp - in_tx.timestamp).total_seconds() / 60
            value_diff_pct = abs(in_tx.value_eth - out_tx.value_eth) / in_tx.value_eth if in_tx.value_eth > 0 else 1
            
            # Very rapid movement with similar value
            if time_diff_minutes < 10 and value_diff_pct < 0.05:
                return RuleResult(
                    rule_type=RuleType.RAPID_MOVEMENT.value,
                    triggered=True,
                    severity=AlertSeverity.HIGH.value,
                    confidence=0.85,
                    description=f"Rapid pass-through: {in_tx.value_eth:.2f} ETH in, {out_tx.value_eth:.2f} ETH out within {time_diff_minutes:.1f} minutes",
                    evidence={
                        "incoming_value": in_tx.value_eth,
                        "outgoing_value": out_tx.value_eth,
                        "time_diff_minutes": time_diff_minutes,
                        "incoming_tx": in_tx.tx_hash,
                        "outgoing_tx": out_tx.tx_hash
                    }
                )
    
    return None

# All rules
DETECTION_RULES = [
    detect_structuring,
    detect_round_trip,
    detect_layering,
    detect_velocity_anomaly,
    detect_value_clustering,
    detect_rapid_movement,
]

# ═══════════════════════════════════════════════════════════════════════════════
# ALERT MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════════════

def create_alert(address: str, rule_result: RuleResult) -> MonitoringAlert:
    """Create a new monitoring alert"""
    alert_id = hashlib.md5(
        f"{address}{rule_result.rule_type}{datetime.utcnow().isoformat()}".encode()
    ).hexdigest()[:16]
    
    alert = MonitoringAlert(
        id=alert_id,
        rule_type=RuleType(rule_result.rule_type),
        severity=AlertSeverity(rule_result.severity),
        status=AlertStatus.OPEN,
        address=address,
        description=rule_result.description,
        transactions=rule_result.evidence.get("tx_hashes", []),
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        metadata={
            "confidence": rule_result.confidence,
            "evidence": rule_result.evidence
        }
    )
    
    alerts_store[alert_id] = alert
    save_alerts()
    
    return alert

def save_alerts():
    """Save alerts to file"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    
    data = {
        alert_id: {
            **asdict(alert),
            "created_at": alert.created_at.isoformat(),
            "updated_at": alert.updated_at.isoformat(),
            "rule_type": alert.rule_type.value,
            "severity": alert.severity.value,
            "status": alert.status.value,
        }
        for alert_id, alert in alerts_store.items()
    }
    
    with open(ALERTS_FILE, 'w') as f:
        json.dump(data, f, indent=2)

def load_alerts():
    """Load alerts from file"""
    global alerts_store
    
    if not ALERTS_FILE.exists():
        return
    
    try:
        with open(ALERTS_FILE, 'r') as f:
            data = json.load(f)
        
        for alert_id, alert_data in data.items():
            alerts_store[alert_id] = MonitoringAlert(
                id=alert_data["id"],
                rule_type=RuleType(alert_data["rule_type"]),
                severity=AlertSeverity(alert_data["severity"]),
                status=AlertStatus(alert_data["status"]),
                address=alert_data["address"],
                description=alert_data["description"],
                transactions=alert_data["transactions"],
                created_at=datetime.fromisoformat(alert_data["created_at"]),
                updated_at=datetime.fromisoformat(alert_data["updated_at"]),
                metadata=alert_data.get("metadata", {}),
                notes=alert_data.get("notes", []),
                assigned_to=alert_data.get("assigned_to")
            )
    except Exception as e:
        print(f"Error loading alerts: {e}")

# ═══════════════════════════════════════════════════════════════════════════════
# FASTAPI APPLICATION
# ═══════════════════════════════════════════════════════════════════════════════

@asynccontextmanager
async def lifespan(app: FastAPI):
    load_alerts()
    
    print("═" * 60)
    print("       AMTTP Transaction Monitoring Rules Engine")
    print("═" * 60)
    print(f"📋 Loaded {len(alerts_store)} existing alerts")
    print(f"🔍 Active rules: {len(DETECTION_RULES)}")
    print("═" * 60)
    
    yield
    
    save_alerts()
    print("👋 Monitoring engine shutting down")

app = FastAPI(
    title="AMTTP Transaction Monitoring Rules Engine",
    description="AML pattern detection for structuring, layering, round-trips",
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
        "service": "transaction-monitoring",
        "active_rules": len(DETECTION_RULES),
        "open_alerts": sum(1 for a in alerts_store.values() if a.status == AlertStatus.OPEN)
    }

@app.post("/monitor/transaction")
async def monitor_transaction(tx: TransactionInput):
    """
    Monitor a single transaction against all rules
    """
    transaction = Transaction(
        tx_hash=tx.tx_hash,
        from_address=tx.from_address,
        to_address=tx.to_address,
        value_eth=tx.value_eth,
        timestamp=datetime.fromisoformat(tx.timestamp.replace('Z', '+00:00')),
        block_number=tx.block_number,
        chain=tx.chain,
        gas_used=tx.gas_used,
        gas_price_gwei=tx.gas_price_gwei
    )
    
    # Add to store
    tx_store.add_transaction(transaction)
    
    # Run all rules
    results = []
    alerts_created = []
    
    for address in [transaction.from_address, transaction.to_address]:
        for rule_fn in DETECTION_RULES:
            try:
                result = rule_fn(address, transaction)
                if result and result.triggered:
                    results.append(result)
                    alert = create_alert(address, result)
                    alerts_created.append(asdict(alert))
            except Exception as e:
                print(f"Error in rule {rule_fn.__name__}: {e}")
    
    return {
        "tx_hash": tx.tx_hash,
        "rules_triggered": len(results),
        "alerts_created": len(alerts_created),
        "results": [r.dict() for r in results],
        "alerts": alerts_created
    }

@app.post("/monitor/batch")
async def monitor_batch(request: MonitorRequest):
    """
    Monitor a batch of transactions
    """
    total_alerts = []
    
    for tx in request.transactions:
        transaction = Transaction(
            tx_hash=tx.tx_hash,
            from_address=tx.from_address,
            to_address=tx.to_address,
            value_eth=tx.value_eth,
            timestamp=datetime.fromisoformat(tx.timestamp.replace('Z', '+00:00')),
            block_number=tx.block_number,
            chain=tx.chain
        )
        tx_store.add_transaction(transaction)
        
        for address in [transaction.from_address, transaction.to_address]:
            for rule_fn in DETECTION_RULES:
                try:
                    result = rule_fn(address, transaction)
                    if result and result.triggered:
                        alert = create_alert(address, result)
                        total_alerts.append(alert.id)
                except Exception:
                    pass
    
    return {
        "transactions_processed": len(request.transactions),
        "alerts_created": len(total_alerts),
        "alert_ids": total_alerts
    }

@app.get("/alerts")
async def list_alerts(
    status: Optional[str] = None,
    severity: Optional[str] = None,
    rule_type: Optional[str] = None,
    limit: int = 50
):
    """List monitoring alerts"""
    alerts = list(alerts_store.values())
    
    if status:
        alerts = [a for a in alerts if a.status.value == status]
    if severity:
        alerts = [a for a in alerts if a.severity.value == severity]
    if rule_type:
        alerts = [a for a in alerts if a.rule_type.value == rule_type]
    
    # Sort by created_at descending
    alerts.sort(key=lambda a: a.created_at, reverse=True)
    
    return {
        "total": len(alerts),
        "alerts": [
            {
                **asdict(a),
                "created_at": a.created_at.isoformat(),
                "updated_at": a.updated_at.isoformat(),
                "rule_type": a.rule_type.value,
                "severity": a.severity.value,
                "status": a.status.value,
            }
            for a in alerts[:limit]
        ]
    }

@app.get("/alerts/{alert_id}")
async def get_alert(alert_id: str):
    """Get a specific alert"""
    alert = alerts_store.get(alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    
    return {
        **asdict(alert),
        "created_at": alert.created_at.isoformat(),
        "updated_at": alert.updated_at.isoformat(),
        "rule_type": alert.rule_type.value,
        "severity": alert.severity.value,
        "status": alert.status.value,
    }

@app.patch("/alerts/{alert_id}")
async def update_alert(alert_id: str, status: Optional[str] = None, note: Optional[str] = None, assigned_to: Optional[str] = None):
    """Update an alert"""
    alert = alerts_store.get(alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    
    if status:
        alert.status = AlertStatus(status)
    if note:
        alert.notes.append(f"{datetime.utcnow().isoformat()}: {note}")
    if assigned_to:
        alert.assigned_to = assigned_to
    
    alert.updated_at = datetime.utcnow()
    save_alerts()
    
    return {"status": "updated", "alert_id": alert_id}

@app.get("/rules")
async def list_rules():
    """List active detection rules"""
    return {
        "rules": [
            {
                "name": rule.__name__,
                "type": rule.__name__.replace("detect_", "").upper(),
                "description": rule.__doc__.strip() if rule.__doc__ else ""
            }
            for rule in DETECTION_RULES
        ],
        "thresholds": THRESHOLDS
    }

@app.get("/stats")
async def get_stats():
    """Get monitoring statistics"""
    alerts = list(alerts_store.values())
    
    by_status = defaultdict(int)
    by_severity = defaultdict(int)
    by_rule = defaultdict(int)
    
    for alert in alerts:
        by_status[alert.status.value] += 1
        by_severity[alert.severity.value] += 1
        by_rule[alert.rule_type.value] += 1
    
    return {
        "total_alerts": len(alerts),
        "by_status": dict(by_status),
        "by_severity": dict(by_severity),
        "by_rule_type": dict(by_rule),
        "transactions_stored": len(tx_store.transactions),
        "addresses_tracked": len(tx_store.by_address)
    }

# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    port = int(os.getenv("MONITORING_SERVICE_PORT", "8005"))
    print(f"🚀 Starting Transaction Monitoring Engine on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
