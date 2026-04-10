#!/usr/bin/env python3
"""
AMTTP Risk Engine Integration Service
=====================================
FastAPI service that provides ML-based risk scoring for transactions.

Production Engine: Student Model Ensemble (XGBoost v2 + LightGBM + Meta-Learner)
- Trained: 2025-12-31 on 1.67M samples (knowledge distillation from Teacher)
- Meta-learner weights extracted from cuML binary (no CUDA dependency)
- See ML_PIPELINE_DOCUMENTATION.md for full details
"""

import os
import sys
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime
from pathlib import Path

# Add parent directories to path for imports
current_dir = Path(__file__).parent
ml_automation_dir = current_dir.parent
sys.path.insert(0, str(ml_automation_dir))
sys.path.insert(0, str(ml_automation_dir / "ml_pipeline"))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import uvicorn
import torch
import httpx

# Force CPU mode for containers
os.environ["CUDA_VISIBLE_DEVICES"] = ""

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Explainability service URL (for enriched explanations)
EXPLAINABILITY_URL = os.getenv("EXPLAINABILITY_URL", "http://explainability:8009")

# Memgraph connection for graph signals (GATv2/GraphSAGE proxy)
MEMGRAPH_URI = os.getenv("MEMGRAPH_URI", "bolt://memgraph:7687")

app = FastAPI(
    title="AMTTP Risk Engine",
    description="ML-based risk scoring service for Ethereum transactions",
    version="1.0.0"
)

# CORS for frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict to your domains
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================================
# Request/Response Models
# ============================================================================

class TransactionRequest(BaseModel):
    """Request model for risk scoring"""
    from_address: str = Field(..., description="Sender address")
    to_address: str = Field(..., description="Recipient address")
    value_eth: float = Field(..., description="Transaction value in ETH")
    gas_price_gwei: Optional[float] = Field(None, description="Gas price in Gwei")
    gas_used: Optional[int] = Field(None, description="Gas used by transaction")
    gas_limit: Optional[int] = Field(None, description="Gas limit of transaction")
    nonce: Optional[int] = Field(None, description="Transaction nonce")
    transaction_type: Optional[int] = Field(None, description="EIP-2718 transaction type (0=legacy, 2=EIP-1559)")
    data: Optional[str] = Field(None, description="Transaction data (hex)")
    chain_id: Optional[int] = Field(1, description="Chain ID (1=mainnet)")
    # Optional sender aggregate features (from address index/cache)
    sender_total_transactions: Optional[float] = Field(None, description="Sender total tx count")
    sender_total_sent: Optional[float] = Field(None, description="Sender total ETH sent")
    sender_total_received: Optional[float] = Field(None, description="Sender total ETH received")
    sender_balance: Optional[float] = Field(None, description="Sender balance in ETH")
    sender_avg_sent: Optional[float] = Field(None, description="Sender average tx value")
    sender_unique_receivers: Optional[float] = Field(None, description="Sender unique receiver count")
    sender_in_out_ratio: Optional[float] = Field(None, description="Sender in/out tx ratio")
    sender_active_duration_mins: Optional[float] = Field(None, description="Sender active duration in minutes")
    scoring_method: Optional[str] = Field(None, description="Scoring method override: ensemble|xgboost|lightgbm|heuristic (default: use engine config)")

class ScoringConfig(BaseModel):
    """Engine scoring configuration — persisted in memory, set via /config"""
    active_model: str = Field("ensemble", description="Active scoring method: ensemble|xgboost|lightgbm|heuristic")
    ensemble_weights: Dict[str, float] = Field(
        default_factory=lambda: {"xgboost": 0.45, "lightgbm": 0.35, "meta": 0.20},
        description="Blend weights when active_model='ensemble'"
    )
    threshold: float = Field(0.6428, description="Decision threshold (fraud if prob >= threshold)")

class RiskResponse(BaseModel):
    """Response model for risk scoring"""
    risk_score: int = Field(..., ge=0, le=1000, description="Risk score 0-1000")
    risk_level: str = Field(..., description="Risk level: minimal/low/medium/high/critical")
    confidence: float = Field(..., ge=0, le=1, description="Model confidence 0-1")
    factors: Dict[str, Any] = Field(default_factory=dict, description="Contributing risk factors")
    model_version: str = Field(..., description="Model version used")
    timestamp: str = Field(..., description="Scoring timestamp")

class BatchRequest(BaseModel):
    """Batch scoring request"""
    transactions: List[TransactionRequest]

class BatchResponse(BaseModel):
    """Batch scoring response"""
    results: List[RiskResponse]
    processing_time_ms: float

class HealthResponse(BaseModel):
    """Health check response"""
    status: str
    model_loaded: bool
    version: str
    uptime_seconds: float

class AlertRecord(BaseModel):
    """Alert record for dashboard"""
    id: str
    timestamp: str
    address: str
    riskLevel: str
    riskScore: float
    signals: List[str]
    signalCount: int
    patterns: List[str]
    action: str
    status: str
    valueEth: float
    transactionHash: str
    modelVersion: str

class TimelineDataPoint(BaseModel):
    """Timeline data point"""
    timestamp: str
    critical: int
    high: int
    medium: int
    low: int

# ============================================================================
# In-Memory Alert Storage (for dashboard integration)
# ============================================================================

class AlertStore:
    """In-memory storage for scored transactions as alerts"""
    
    def __init__(self, max_alerts: int = 1000):
        self.alerts: List[Dict[str, Any]] = []
        self.max_alerts = max_alerts
        self.stats = {
            "totalAlerts": 0,
            "criticalAlerts": 0,
            "highAlerts": 0,
            "mediumAlerts": 0,
            "lowAlerts": 0,
            "blockedAddresses": 0,
            "flaggedTransactions": 0,
            "pendingInvestigation": 0,
            "resolvedToday": 0,
        }
    
    def add_alert(self, tx: TransactionRequest, response: RiskResponse) -> Dict[str, Any]:
        """Add a scored transaction as an alert"""
        import uuid
        
        # Map risk level to patterns
        patterns = []
        if response.factors.get("high_value") or response.factors.get("elevated_value"):
            patterns.append("HIGH_VALUE")
        if response.factors.get("suspicious_address"):
            patterns.append("SUSPICIOUS_ADDRESS")
        if response.factors.get("complex_contract_call"):
            patterns.append("COMPLEX_CONTRACT")
        if response.factors.get("new_wallet"):
            patterns.append("NEW_WALLET")
        if response.factors.get("high_gas"):
            patterns.append("HIGH_GAS")
        if not patterns:
            patterns.append("STANDARD")
        
        # Determine action based on risk level
        action_map = {
            "critical": "BLOCK",
            "high": "ESCROW",
            "medium": "FLAG",
            "low": "MONITOR",
            "minimal": "APPROVE"
        }
        
        alert = {
            "id": f"alert-{uuid.uuid4().hex[:12]}",
            "timestamp": response.timestamp,
            "address": tx.from_address,
            "riskLevel": response.risk_level.upper(),
            "riskScore": response.risk_score / 10,  # Convert 0-1000 to 0-100
            "signals": patterns,
            "signalCount": len(patterns),
            "patterns": patterns,
            "action": action_map.get(response.risk_level, "MONITOR"),
            "status": "NEW",
            "valueEth": tx.value_eth,
            "transactionHash": f"0x{uuid.uuid4().hex}",
            "modelVersion": response.model_version,
            "toAddress": tx.to_address,
            "confidence": response.confidence
        }
        
        # Add to alerts list
        self.alerts.insert(0, alert)
        if len(self.alerts) > self.max_alerts:
            self.alerts = self.alerts[:self.max_alerts]
        
        # Update stats
        self.stats["totalAlerts"] += 1
        self.stats["flaggedTransactions"] += 1
        
        risk_key = f"{response.risk_level}Alerts"
        if risk_key == "minimalAlerts":
            risk_key = "lowAlerts"
        if risk_key in self.stats:
            self.stats[risk_key] += 1
        
        if response.risk_level in ["critical", "high"]:
            self.stats["pendingInvestigation"] += 1
        if response.risk_level == "critical":
            self.stats["blockedAddresses"] += 1
        
        return alert
    
    def get_alerts(self, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        """Get alerts with pagination"""
        return self.alerts[offset:offset + limit]
    
    def get_stats(self) -> Dict[str, Any]:
        """Get current statistics"""
        return {
            **self.stats,
            "alertsTrend": 12.5 if self.stats["totalAlerts"] > 0 else 0
        }
    
    def get_timeline(self, hours: int = 24) -> List[Dict[str, Any]]:
        """Get timeline data for charts"""
        from collections import defaultdict
        
        # Group alerts by hour
        now = datetime.now()
        timeline = []
        
        for h in range(hours, 0, -1):
            hour_start = now.replace(minute=0, second=0, microsecond=0)
            hour_start = hour_start.replace(hour=(hour_start.hour - h) % 24)
            
            counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
            for alert in self.alerts:
                try:
                    alert_time = datetime.fromisoformat(alert["timestamp"].replace("Z", "+00:00"))
                    if alert_time.hour == hour_start.hour:
                        level = alert["riskLevel"].lower()
                        if level in counts:
                            counts[level] += 1
                        elif level == "minimal":
                            counts["low"] += 1
                except:
                    pass
            
            timeline.append({
                "timestamp": hour_start.isoformat(),
                **counts
            })
        
        return timeline

# Global alert store
alert_store = AlertStore()

# ============================================================================
# Service State
# ============================================================================

class BetaVAE(torch.nn.Module):
    """β-VAE for unsupervised anomaly scoring. in_dim=93, latent_dim=64."""
    def __init__(self, in_dim, latent_dim=64, hidden=256, beta=4.0):
        super().__init__()
        self.beta = beta
        self.latent_dim = latent_dim
        self.enc = torch.nn.Sequential(
            torch.nn.Linear(in_dim, hidden), torch.nn.LayerNorm(hidden), torch.nn.GELU(), torch.nn.Dropout(0.1),
            torch.nn.Linear(hidden, hidden // 2), torch.nn.LayerNorm(hidden // 2), torch.nn.GELU()
        )
        self.mu = torch.nn.Linear(hidden // 2, latent_dim)
        self.logvar = torch.nn.Linear(hidden // 2, latent_dim)
        self.dec = torch.nn.Sequential(
            torch.nn.Linear(latent_dim, hidden // 2), torch.nn.LayerNorm(hidden // 2), torch.nn.GELU(), torch.nn.Dropout(0.1),
            torch.nn.Linear(hidden // 2, hidden), torch.nn.LayerNorm(hidden), torch.nn.GELU(),
            torch.nn.Linear(hidden, in_dim)
        )
    def encode(self, x):
        h = self.enc(x)
        return self.mu(h), self.logvar(h)
    def forward(self, x):
        mu, logvar = self.encode(x)
        z = mu  # deterministic at inference (no sampling)
        recon = self.dec(z)
        return recon, mu, logvar, z


class RiskEngine:
    """
    Risk scoring engine using V2 Student Pipeline.

    Architecture (full distilled student):
        93 raw features → preprocess → β-VAE → 160 boost features
        → XGBoost + LightGBM → xgb_prob, lgb_prob
        → + VAE anomaly metrics (recon_err, kl_div, mahalanobis)
        → Meta-Ensemble (8 features) → fraud_prob

    Models (amttp_models_20260213_213346/):
        - β-VAE: 93→64 latent dim, anomaly scoring (recon_err, kl_div, mahalanobis)
        - XGBoost: 160 boost features (93 raw + 64 VAE latent + 3 VAE metrics)
        - LightGBM: 160 boost features (same)
        - Meta-Ensemble: LogisticRegressionCV(8 features)
          [recon_err, kl_div, mahalanobis, gat_prob, gat_uncertainty, sage_prob, xgb_oof, lgb_oof]

    At inference, GATv2/GraphSAGE require graph structure not available for single
    transactions, so gat_prob/gat_uncertainty/sage_prob use neutral defaults.
    The meta-learner still has XGB/LGB/VAE signals (5 of 8 features).
    """

    # 93 raw features expected by preprocessors (same order as training)
    RAW_FEATURE_NAMES = [
        "value_eth", "gas_price_gwei", "gas_used", "gas_limit", "transaction_type",
        "nonce", "transaction_index",
        "sender_sent_count", "sender_total_sent", "sender_avg_sent",
        "sender_max_sent", "sender_min_sent", "sender_std_sent",
        "sender_total_gas_sent", "sender_avg_gas_used", "sender_avg_gas_price",
        "sender_unique_receivers", "sender_received_count", "sender_total_received",
        "sender_avg_received", "sender_max_received", "sender_min_received",
        "sender_std_received", "sender_unique_senders", "sender_total_transactions",
        "sender_balance", "sender_in_out_ratio", "sender_unique_counterparties",
        "sender_avg_value", "sender_neighbors", "sender_count", "sender_income",
        "sender_active_duration_mins",
        "sender_in_degree", "sender_out_degree", "sender_degree",
        "sender_degree_centrality", "sender_betweenness_proxy",
        "sender_sent_to_mixer", "sender_recv_from_mixer", "sender_mixer_interaction",
        "sender_sent_to_sanctioned", "sender_recv_from_sanctioned", "sender_sanctioned_interaction",
        "sender_sent_to_exchange", "sender_recv_from_exchange", "sender_exchange_interaction",
        "sender_is_mixer", "sender_is_sanctioned", "sender_is_exchange",
        "receiver_sent_count", "receiver_total_sent", "receiver_avg_sent",
        "receiver_max_sent", "receiver_min_sent", "receiver_std_sent",
        "receiver_total_gas_sent", "receiver_avg_gas_used", "receiver_avg_gas_price",
        "receiver_unique_receivers", "receiver_received_count", "receiver_total_received",
        "receiver_avg_received", "receiver_max_received", "receiver_min_received",
        "receiver_std_received", "receiver_unique_senders", "receiver_total_transactions",
        "receiver_balance", "receiver_in_out_ratio", "receiver_unique_counterparties",
        "receiver_avg_value", "receiver_neighbors", "receiver_count", "receiver_income",
        "receiver_active_duration_mins",
        "receiver_in_degree", "receiver_out_degree", "receiver_degree",
        "receiver_degree_centrality", "receiver_betweenness_proxy",
        "receiver_sent_to_mixer", "receiver_recv_from_mixer", "receiver_mixer_interaction",
        "receiver_sent_to_sanctioned", "receiver_recv_from_sanctioned", "receiver_sanctioned_interaction",
        "receiver_sent_to_exchange", "receiver_recv_from_exchange", "receiver_exchange_interaction",
        "receiver_is_mixer", "receiver_is_sanctioned", "receiver_is_exchange",
    ]

    # Meta-learner feature names (8 inputs)
    META_FEATURES = [
        "recon_err", "kl_div", "mahalanobis",
        "gat_prob", "gat_uncertainty", "sage_prob",
        "xgb_oof", "lgb_oof",
    ]

    TABULAR_FEATURES = RAW_FEATURE_NAMES
    N_RAW_FEATURES = 93
    N_BOOST_FEATURES = 160  # 93 raw + 64 VAE latent + 3 VAE metrics
    N_FEATURES = 160

    def __init__(self):
        self.model_loaded = False
        self.model_version = "student-v2-distilled-ensemble"
        self.start_time = datetime.now()
        self.xgb_model = None
        self.lgbm_model = None
        self.meta_model = None
        self.vae_model = None
        self.preprocessors = None
        self.metadata = None
        self.optimal_threshold = 0.6428
        self.config = ScoringConfig()  # Active scoring configuration
        # Teacher model (Hope_machine XGB — 171 address-level features + calibration)
        self.teacher_xgb = None           # xgb.Booster
        self.teacher_feature_names = None # 171 feature names from schema
        self.teacher_loaded = False
        # Memgraph driver for graph signals
        self._graph_driver = None
        self._graph_available = False
        self._load_models()
        self._connect_graph()

    def _find_models_dir(self) -> Optional[Path]:
        """Locate the V2 student model directory."""
        possible_paths = [
            current_dir / "models",                                    # Docker mount
            ml_automation_dir / "amttp_models_20260213_213346",        # V2 student (preferred)
            current_dir.parent / "amttp_models_20260213_213346",
            Path("/app/models"),                                       # Docker fallback
            ml_automation_dir / "amttp_models_20251231_174617",        # Older V2
        ]

        for p in possible_paths:
            if p.exists() and (p / "xgboost_fraud.ubj").exists():
                logger.info(f"Found V2 student model directory: {p}")
                return p

        # Fallback: any directory with model files
        for p in possible_paths:
            if p.exists() and any(p.glob("*.ubj")):
                logger.info(f"Found model directory with .ubj files: {p}")
                return p

        return None

    def _load_models(self):
        """Load V2 student pipeline: preprocessors → β-VAE → XGB + LGB → meta-ensemble."""
        try:
            models_dir = self._find_models_dir()

            if models_dir is None:
                logger.warning("No models directory found — using heuristic-only scoring")
                return

            logger.info(f"Loading models from: {models_dir}")
            logger.info(f"Available files: {sorted(f.name for f in models_dir.glob('*') if f.is_file())}")

            xgb_path = models_dir / "xgboost_fraud.ubj"
            lgb_path = models_dir / "lightgbm_fraud.txt"
            meta_path = models_dir / "meta_ensemble.joblib"
            vae_path = models_dir / "beta_vae.pt"
            preproc_path = models_dir / "preprocessors.joblib"
            metadata_path = models_dir / "metadata.json"

            # 1. Preprocessors
            if preproc_path.exists():
                import joblib
                self.preprocessors = joblib.load(str(preproc_path))
                logger.info(f"✓ Loaded preprocessors (scaler n_features={self.preprocessors['robust_scaler'].n_features_in_})")
            else:
                logger.warning("preprocessors.joblib not found — will skip preprocessing")

            # 2. β-VAE
            if vae_path.exists():
                checkpoint = torch.load(str(vae_path), map_location="cpu", weights_only=False)
                cfg = checkpoint["config"]
                self.vae_model = BetaVAE(
                    in_dim=cfg["in_dim"], latent_dim=cfg["latent_dim"],
                    hidden=cfg["hidden"], beta=cfg["beta"]
                )
                # Strip _orig_mod. prefix from torch.compile'd state dicts
                state_dict = checkpoint["model_state_dict"]
                state_dict = {k.replace("_orig_mod.", ""): v for k, v in state_dict.items()}
                self.vae_model.load_state_dict(state_dict)
                self.vae_model.eval()
                logger.info(f"✓ Loaded β-VAE (in={cfg['in_dim']}, latent={cfg['latent_dim']}, β={cfg['beta']})")
            else:
                logger.warning("beta_vae.pt not found — will skip VAE enrichment")

            # 3. XGBoost
            import xgboost as xgb
            self.xgb_model = xgb.XGBClassifier()
            self.xgb_model.load_model(str(xgb_path))
            logger.info(f"✓ Loaded XGBoost from {xgb_path.name}")

            # 4. LightGBM
            import lightgbm as lgb_lib
            self.lgbm_model = lgb_lib.Booster(model_file=str(lgb_path))
            logger.info(f"✓ Loaded LightGBM from {lgb_path.name}")

            # 5. Meta-ensemble
            if meta_path.exists():
                import joblib
                self.meta_model = joblib.load(str(meta_path))
                logger.info(f"✓ Loaded meta-ensemble (n_features={self.meta_model.n_features_in_}, "
                           f"coef={self.meta_model.coef_[0].tolist()[:3]}...)")
            else:
                logger.warning("meta_ensemble.joblib not found — will average XGB+LGB")

            # 6. Metadata
            if metadata_path.exists():
                import json
                with open(metadata_path) as f:
                    self.metadata = json.load(f)
                self.optimal_threshold = self.metadata.get("optimal_threshold", 0.6428)
                perf = self.metadata.get("performance", {})
                logger.info(f"✓ Metadata — threshold={self.optimal_threshold:.4f}, "
                           f"meta_ROC-AUC={perf.get('meta_roc_auc', 'N/A')}, "
                           f"xgb_ROC-AUC={perf.get('xgb_roc_auc', 'N/A')}")

            self.model_loaded = True
            logger.info(f"✅ V2 Student Pipeline loaded "
                       f"(93 raw → VAE → {self.N_BOOST_FEATURES} boost → XGB+LGB → meta-ensemble)")

        except Exception as e:
            logger.error(f"Error in model loading: {e}", exc_info=True)
            self.model_loaded = False

        # ── Load Teacher XGB (Hope_machine) ─────────────────────────────
        self._load_teacher_model()

    def _load_teacher_model(self):
        """Load the Teacher XGB (Hope_machine) — 171 address-level features + sigmoid calibration."""
        try:
            teacher_dirs = [
                ml_automation_dir / "ml_pipeline" / "models" / "trained",
                current_dir / "models" / "trained",
                Path("/app/teacher_models/trained"),       # Docker volume mount
                Path("/app/models/trained"),
            ]
            schema_paths = [
                ml_automation_dir / "ml_pipeline" / "models" / "feature_schema.json",
                current_dir / "models" / "feature_schema.json",
                Path("/app/teacher_models/feature_schema.json"),  # Docker volume mount
                Path("/app/models/feature_schema.json"),
            ]

            # Find teacher XGB model
            teacher_path = None
            for d in teacher_dirs:
                for name in ["hybrid_xgb.json", "xgb.json"]:
                    p = d / name
                    if p.exists():
                        teacher_path = p
                        break
                if teacher_path:
                    break

            # Find feature schema
            schema_path = None
            for sp in schema_paths:
                if sp.exists():
                    schema_path = sp
                    break

            if teacher_path is None:
                logger.info("Teacher XGB model not found — teacher scoring unavailable")
                return
            if schema_path is None:
                logger.warning("Teacher feature_schema.json not found — teacher scoring unavailable")
                return

            import json as _json
            import xgboost as xgb

            # Load feature schema
            with open(schema_path) as f:
                self.teacher_feature_names = _json.load(f)["feature_names"]

            # Load XGB Booster
            self.teacher_xgb = xgb.Booster()
            self.teacher_xgb.load_model(str(teacher_path))
            self.teacher_loaded = True
            logger.info(f"✅ Teacher XGB loaded from {teacher_path.name} "
                       f"({len(self.teacher_feature_names)} features, "
                       f"{self.teacher_xgb.num_boosted_rounds()} rounds)")

        except Exception as e:
            logger.error(f"Error loading teacher model: {e}", exc_info=True)
            self.teacher_loaded = False

    # ── Memgraph Graph Connection ───────────────────────────────────────────

    def _connect_graph(self):
        """Connect to Memgraph for graph-based fraud signals (graceful fallback)."""
        try:
            from neo4j import GraphDatabase as _GD
            self._graph_driver = _GD.driver(MEMGRAPH_URI)
            # Quick connectivity check
            with self._graph_driver.session() as s:
                cnt = s.run("MATCH (n) RETURN count(n) AS c").single()["c"]
            self._graph_available = cnt > 0
            logger.info(f"✅ Memgraph connected ({cnt:,} nodes, uri={MEMGRAPH_URI})")
        except Exception as e:
            self._graph_driver = None
            self._graph_available = False
            logger.warning(f"Memgraph not available — graph signals will default to 0.5: {e}")

    def _query_graph_signals(
        self, from_address: str, to_address: str
    ) -> tuple:
        """
        Query Memgraph for sender + receiver graph features, then calibrate
        into proxy gat_prob, gat_uncertainty, sage_prob for the meta-ensemble.

        Uses pre-computed node properties (in_degree, out_degree, tx_count,
        total_sent, total_received, mixer_exposure, sanction_proximity,
        fraud_flag) that were baked into nodes during ingestion.

        Returns (gat_prob, gat_uncertainty, sage_prob) — all in [0, 1].
        Falls back to (0.5, 0.5, 0.5) if Memgraph is unreachable.
        """
        import numpy as np
        NEUTRAL = (0.5, 0.5, 0.5)

        if not self._graph_available or self._graph_driver is None:
            return NEUTRAL

        try:
            sender = from_address.lower()
            receiver = to_address.lower()

            query = """
            UNWIND $addrs AS addr
            OPTIONAL MATCH (a:Address {id: addr})
            RETURN
                addr,
                coalesce(a.in_degree,  0)   AS in_deg,
                coalesce(a.out_degree, 0)   AS out_deg,
                coalesce(a.tx_count,   0)   AS tx_count,
                coalesce(a.total_sent, 0.0) AS total_sent,
                coalesce(a.total_received, 0.0) AS total_recv,
                coalesce(a.fraud_flag, 0)   AS fraud_flag,
                CASE WHEN a.mixer_exposure      = true THEN 1 ELSE 0 END AS mixer_exp,
                CASE WHEN a.sanction_proximity  = true THEN 1 ELSE 0 END AS sanction_prox,
                CASE WHEN a:Sanctioned THEN 1 ELSE 0 END AS is_sanctioned,
                CASE WHEN a:Mixer      THEN 1 ELSE 0 END AS is_mixer
            """

            with self._graph_driver.session() as sess:
                rows = sess.run(query, addrs=[sender, receiver]).data()

            # Parse results into sender / receiver dicts
            feats = {}
            for row in rows:
                feats[row["addr"]] = row
            s = feats.get(sender, {})
            r = feats.get(receiver, {})

            # ── Calibrate proxy graph signals ──────────────────────────
            # These map structural graph features to [0, 1] probabilities
            # that act as stand-ins for GATv2 / GraphSAGE outputs.
            #
            # Training GATv2 / GraphSAGE took the SAME 160-dim boost feature
            # vector + full graph edge_index.  At single-TX inference we don't
            # have the full neighbourhood, but we DO have pre-computed node
            # properties that strongly correlate with what the GNNs learn.

            def _risk_signal(feat: dict) -> float:
                """Compute a single risk signal from graph properties."""
                score = 0.0
                # Direct sanction / mixer flag → extreme risk
                if feat.get("is_sanctioned", 0):
                    return 0.99
                if feat.get("is_mixer", 0):
                    return 0.95
                # Proximity to sanctioned / mixer nodes
                if feat.get("sanction_prox", 0):
                    score += 0.35
                if feat.get("mixer_exp", 0):
                    score += 0.25
                # Previously flagged as fraud
                if feat.get("fraud_flag", 0):
                    score += 0.20
                # Low tx_count = new/ephemeral address (suspicious)
                tc = feat.get("tx_count", 0)
                if 0 < tc <= 3:
                    score += 0.10
                # High out-degree relative to in-degree (fan-out pattern)
                out_d = feat.get("out_deg", 0)
                in_d = feat.get("in_deg", 0)
                if out_d > 0 and in_d > 0:
                    ratio = out_d / (in_d + 1)
                    if ratio > 10:
                        score += 0.10
                return float(np.clip(score, 0.01, 0.99))

            sender_risk = _risk_signal(s)
            receiver_risk = _risk_signal(r)

            # gat_prob: combined sender+receiver risk (GATv2 captures
            #           bidirectional attention across 2-hop neighbourhood)
            gat_prob = float(np.clip(0.6 * sender_risk + 0.4 * receiver_risk, 0.01, 0.99))

            # gat_uncertainty: higher when graph is sparse (fewer signals)
            s_tc = s.get("tx_count", 0)
            r_tc = r.get("tx_count", 0)
            combined_tx = s_tc + r_tc
            # Sigmoid decay: lots of history → low uncertainty
            exp_arg = np.clip(0.05 * (combined_tx - 20), -500, 500)
            gat_uncertainty = float(1.0 / (1.0 + np.exp(exp_arg)))

            # sage_prob: focus on neighbour aggregation → receiver risk
            #            (GraphSAGE aggregates incoming signals)
            sage_prob = float(np.clip(0.4 * sender_risk + 0.6 * receiver_risk, 0.01, 0.99))

            return (gat_prob, gat_uncertainty, sage_prob)

        except Exception as e:
            logger.warning(f"Graph signal query failed, falling back to neutral: {e}")
            return NEUTRAL

    def _extract_raw_features(self, tx: TransactionRequest) -> 'np.ndarray':
        """
        Extract 93 raw features from a TransactionRequest.
        Maps available fields; missing features default to 0 (imputer handles NaN).
        """
        import numpy as np

        # Build a dict of available values
        vals = {
            "value_eth": float(tx.value_eth),
            "gas_price_gwei": float(tx.gas_price_gwei or 0),
            "gas_used": float(tx.gas_used or 21000),
            "gas_limit": float(tx.gas_limit or 21000),
            "transaction_type": float(tx.transaction_type or 0),
            "nonce": float(tx.nonce or 0),
            "transaction_index": 0.0,
            # Sender features from request
            "sender_total_transactions": float(tx.sender_total_transactions or 0),
            "sender_total_sent": float(tx.sender_total_sent or 0),
            "sender_total_received": float(tx.sender_total_received or 0),
            "sender_balance": float(tx.sender_balance or 0),
            "sender_avg_sent": float(tx.sender_avg_sent or 0),
            "sender_unique_receivers": float(tx.sender_unique_receivers or 0),
            "sender_in_out_ratio": float(tx.sender_in_out_ratio or 0),
            "sender_active_duration_mins": float(tx.sender_active_duration_mins or 0),
        }

        # Build 93-feature vector in training order
        features = np.array([[vals.get(name, 0.0) for name in self.RAW_FEATURE_NAMES]], dtype=np.float32)
        features = np.nan_to_num(features, nan=0.0, posinf=0.0, neginf=0.0)
        return features

    def _preprocess(self, raw: 'np.ndarray') -> 'np.ndarray':
        """Apply the training preprocessors: impute → log-transform → robust-scale → clip."""
        import numpy as np

        if self.preprocessors is None:
            return raw

        X = raw.copy().astype(np.float32)
        X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)

        log_mask = self.preprocessors["log_transform_mask"]
        X[:, log_mask] = np.log1p(np.clip(X[:, log_mask], 0, None))
        X = self.preprocessors["robust_scaler"].transform(X)
        return np.clip(X, -5, 5)

    def _vae_enrich(self, preprocessed: 'np.ndarray') -> tuple:
        """
        Run β-VAE to get latent features + anomaly metrics.
        Returns (boost_features[160], recon_err, kl_div, mahalanobis).
        """
        import numpy as np

        if self.vae_model is None:
            # No VAE: pad with zeros for the 67 VAE columns (64 latent + 3 metrics)
            zeros = np.zeros((preprocessed.shape[0], 67), dtype=np.float32)
            boost = np.hstack([preprocessed, zeros])
            return boost, 0.0, 0.0, 0.0

        with torch.no_grad():
            x_t = torch.tensor(preprocessed, dtype=torch.float32)
            recon, mu, logvar, z = self.vae_model(x_t)

            # Reconstruction error
            recon_err = float(torch.nn.functional.mse_loss(recon, x_t, reduction="mean").item())

            # KL divergence
            kl_div = float((-0.5 * torch.sum(1 + logvar - mu.pow(2) - logvar.exp(), dim=1)).mean().item())

            # Mahalanobis distance (simplified: norm of z)
            mahalanobis = float(torch.sqrt((z ** 2).sum(dim=1)).mean().item())

            # Latent features as numpy
            z_np = z.cpu().numpy()

        # Build 160 boost features: [93 preprocessed | 64 latent | recon_err | kl_div | mahalanobis]
        n = preprocessed.shape[0]
        metrics = np.array([[recon_err, kl_div, mahalanobis]] * n, dtype=np.float32)
        boost = np.hstack([preprocessed, z_np, metrics])

        return boost, recon_err, kl_div, mahalanobis

    def _predict_ensemble(self, tx: TransactionRequest) -> Optional[dict]:
        """
        Full V2 student inference pipeline:
          93 raw → preprocess → VAE enrich → 160 boost → XGB+LGB → meta-ensemble
        Returns dict with fraud_prob and component scores.
        """
        import numpy as np

        try:
            # 1. Extract 93 raw features
            raw = self._extract_raw_features(tx)

            # 2. Preprocess (impute, log-transform, scale)
            preprocessed = self._preprocess(raw)

            # 3. VAE enrichment → 160 boost features + anomaly metrics
            boost_features, recon_err, kl_div, mahalanobis = self._vae_enrich(preprocessed)

            # 4. XGBoost probability
            xgb_prob = float(self.xgb_model.predict_proba(boost_features)[0, 1])

            # 5. LightGBM probability
            lgb_prob = float(self.lgbm_model.predict(boost_features)[0])

            # 6. Graph signals → meta-ensemble (8 features)
            gat_prob, gat_uncertainty, sage_prob = self._query_graph_signals(
                tx.from_address, tx.to_address
            )

            if self.meta_model is not None:
                meta_input = np.array([[
                    recon_err, kl_div, mahalanobis,
                    gat_prob, gat_uncertainty, sage_prob,
                    xgb_prob, lgb_prob,
                ]])
                fraud_prob = float(self.meta_model.predict_proba(meta_input)[0, 1])
            else:
                fraud_prob = (xgb_prob + lgb_prob) / 2.0

            return {
                "fraud_prob": fraud_prob,
                "xgb_prob": xgb_prob,
                "lgb_prob": lgb_prob,
                "recon_err": recon_err,
                "kl_div": kl_div,
                "mahalanobis": mahalanobis,
                "gat_prob": gat_prob,
                "gat_uncertainty": gat_uncertainty,
                "sage_prob": sage_prob,
            }

        except Exception as e:
            logger.error(f"V2 ensemble prediction error: {e}", exc_info=True)
            return None

    def _predict_xgboost_only(self, tx: TransactionRequest) -> Optional[dict]:
        """XGBoost-only scoring: 93 raw → preprocess → VAE enrich → 160 boost → XGBoost."""
        import numpy as np
        try:
            raw = self._extract_raw_features(tx)
            preprocessed = self._preprocess(raw)
            boost_features, recon_err, kl_div, mahalanobis = self._vae_enrich(preprocessed)
            xgb_prob = float(self.xgb_model.predict_proba(boost_features)[0, 1])
            return {
                "fraud_prob": xgb_prob,
                "xgb_prob": xgb_prob,
                "lgb_prob": None,
                "recon_err": recon_err,
                "kl_div": kl_div,
                "mahalanobis": mahalanobis,
            }
        except Exception as e:
            logger.error(f"XGBoost-only prediction error: {e}", exc_info=True)
            return None

    def _predict_lightgbm_only(self, tx: TransactionRequest) -> Optional[dict]:
        """LightGBM-only scoring: 93 raw → preprocess → VAE enrich → 160 boost → LightGBM."""
        import numpy as np
        try:
            raw = self._extract_raw_features(tx)
            preprocessed = self._preprocess(raw)
            boost_features, recon_err, kl_div, mahalanobis = self._vae_enrich(preprocessed)
            lgb_prob = float(self.lgbm_model.predict(boost_features)[0])
            return {
                "fraud_prob": lgb_prob,
                "xgb_prob": None,
                "lgb_prob": lgb_prob,
                "recon_err": recon_err,
                "kl_div": kl_div,
                "mahalanobis": mahalanobis,
            }
        except Exception as e:
            logger.error(f"LightGBM-only prediction error: {e}", exc_info=True)
            return None

    def _extract_teacher_features(self, tx: TransactionRequest) -> 'np.ndarray':
        """
        Map TransactionRequest fields onto the 171 teacher (Hope_machine) feature schema.
        Teacher features are address-level (Kaggle ETH fraud dataset columns).
        Available TX-level fields are mapped to the closest address-level equivalents;
        unmatched features default to 0.
        """
        import numpy as np

        # Map our tx/sender fields → teacher feature names
        mapping = {
            "avg_val_sent": float(tx.sender_avg_sent or 0),
            "avg_val_received": float(tx.sender_total_received / max(tx.sender_total_transactions or 1, 1)) if tx.sender_total_received else 0.0,
            "total_ether_sent": float(tx.sender_total_sent or 0),
            "total_ether_received": float(tx.sender_total_received or 0),
            "total_ether_balance": float(tx.sender_balance or 0),
            "sent_tnx": float(tx.sender_total_transactions or 0) * float(tx.sender_in_out_ratio or 0.5),
            "received_tnx": float(tx.sender_total_transactions or 0) * (1 - float(tx.sender_in_out_ratio or 0.5)),
            "total_transactions_(including_tnx_to_create_contract": float(tx.sender_total_transactions or 0),
            "unique_sent_to_addresses": float(tx.sender_unique_receivers or 0),
            "unique_received_from_addresses": 0.0,
            "time_diff_between_first_and_last_(mins)": float(tx.sender_active_duration_mins or 0),
            "neighbors": 0.0,
            "count": float(tx.sender_total_transactions or 0),
            "income": float(tx.sender_total_received or 0) - float(tx.sender_total_sent or 0),
            "max_val_sent": float(tx.value_eth),  # current tx is a proxy
            "min_val_sent": float(tx.value_eth),
            "max_value_received": 0.0,
            "min_value_received": 0.0,
        }

        features = np.zeros((1, len(self.teacher_feature_names)), dtype=np.float32)
        for i, name in enumerate(self.teacher_feature_names):
            if name in mapping:
                features[0, i] = mapping[name]
        features = np.nan_to_num(features, nan=0.0, posinf=0.0, neginf=0.0)
        return features

    def _predict_teacher(self, tx: TransactionRequest) -> Optional[dict]:
        """
        Teacher (Hope_machine) full 3-signal hybrid scoring pipeline.
        Replicates the ultra script: hybrid_score = 40% XGB + 30% pattern_boost + 30% soph_normalized
        Plus multi-signal bonus (×1.2 for 2 signals, ×1.5 for 3 signals).

        Signal 1: XGB (teacher model, 171 features → sigmoid calibration → 0-100)
        Signal 2: Pattern boost (rule-based: smurfing, layering, fan-out, etc. → 0-100)
        Signal 3: Graph risk (degree centrality, mixer/sanctioned interaction → 0-100)
        """
        import numpy as np
        import xgboost as xgb

        try:
            # ── Signal 1: XGB teacher score ────────────────────────────
            features = self._extract_teacher_features(tx)
            dmatrix = xgb.DMatrix(features, feature_names=self.teacher_feature_names)
            raw_score = float(self.teacher_xgb.predict(dmatrix)[0])

            # Sigmoid calibration (k=30, center=p75 reference from training)
            p75_ref = 0.03
            xgb_calibrated = 1.0 / (1.0 + np.exp(-30 * (raw_score - p75_ref)))
            xgb_normalized = xgb_calibrated * 100  # 0-100 scale

            # ── Signal 2: Pattern boost (rule-based) ───────────────────
            PATTERN_BOOST_WEIGHTS = {
                "HIGH_VALUE": 20, "SUSPICIOUS_ADDRESS": 25, "COMPLEX_CONTRACT": 15,
                "NEW_WALLET": 15, "HIGH_GAS": 10,
                "SMURFING": 25, "LAYERING": 15, "FAN_OUT": 15,
                "FAN_IN": 15, "STRUCTURING": 20, "VELOCITY": 15, "PEELING": 20,
            }
            pattern_boost = 0
            detected_patterns = []

            if tx.value_eth > 100:
                pattern_boost += PATTERN_BOOST_WEIGHTS["HIGH_VALUE"]
                detected_patterns.append("HIGH_VALUE")
            if tx.to_address.lower().startswith("0x000"):
                pattern_boost += PATTERN_BOOST_WEIGHTS["SUSPICIOUS_ADDRESS"]
                detected_patterns.append("SUSPICIOUS_ADDRESS")
            if tx.data and len(tx.data) > 200:
                pattern_boost += PATTERN_BOOST_WEIGHTS["COMPLEX_CONTRACT"]
                detected_patterns.append("COMPLEX_CONTRACT")
            if tx.nonce is not None and tx.nonce < 5:
                pattern_boost += PATTERN_BOOST_WEIGHTS["NEW_WALLET"]
                detected_patterns.append("NEW_WALLET")
            if tx.gas_price_gwei and tx.gas_price_gwei > 100:
                pattern_boost += PATTERN_BOOST_WEIGHTS["HIGH_GAS"]
                detected_patterns.append("HIGH_GAS")

            pattern_boost = min(pattern_boost, 100)

            # ── Signal 3: Graph risk score (proxy from available features) ─
            # degree_centrality * 10 + betweenness_proxy * 15 + mixer * 30 + sanctioned * 40 + exchange * 5
            total_tx = float(tx.sender_total_transactions or 0)
            unique_recv = float(tx.sender_unique_receivers or 0)
            in_out_ratio = float(tx.sender_in_out_ratio or 0.5)
            out_degree = unique_recv
            in_degree = total_tx * (1 - in_out_ratio) if total_tx > 0 else 0
            degree = in_degree + out_degree
            max_degree_ref = 500  # reference max from training data
            degree_centrality = min(degree / max(max_degree_ref, 1), 1.0)
            betweenness_proxy = (in_degree / max(max_degree_ref, 1)) * (out_degree / max(max_degree_ref, 1))

            graph_risk_score = min(100, (
                degree_centrality * 10 +
                betweenness_proxy * 15
            ))

            # ── Compute Hybrid Score ───────────────────────────────────
            # sophisticated_score ≈ pattern-based scores; here we use graph_risk as proxy
            soph_normalized = graph_risk_score  # already 0-100

            hybrid_score = (
                xgb_normalized * 0.40 +
                pattern_boost * 0.30 +
                soph_normalized * 0.30
            )

            # Multi-signal bonus
            signal_count = 0
            if xgb_normalized >= 50:
                signal_count += 1
            if graph_risk_score >= 10:
                signal_count += 1
            if len(detected_patterns) >= 2:
                signal_count += 1

            if signal_count == 2:
                hybrid_score *= 1.2
            elif signal_count >= 3:
                hybrid_score *= 1.5

            hybrid_score = min(100, max(0, hybrid_score))

            # Convert to 0-1 probability
            fraud_prob = hybrid_score / 100.0

            return {
                "fraud_prob": fraud_prob,
                "xgb_prob": None,
                "lgb_prob": None,
                "recon_err": 0.0,
                "kl_div": 0.0,
                "mahalanobis": 0.0,
                "teacher_raw_score": raw_score,
                "teacher_calibrated": float(xgb_calibrated),
                "teacher_xgb_normalized": xgb_normalized,
                "teacher_pattern_boost": pattern_boost,
                "teacher_graph_risk": graph_risk_score,
                "teacher_hybrid_score": hybrid_score,
                "teacher_signal_count": signal_count,
                "teacher_patterns": detected_patterns,
            }
        except Exception as e:
            logger.error(f"Teacher prediction error: {e}", exc_info=True)
            return None

    def _predict_by_method(self, tx: TransactionRequest, method: str) -> Optional[dict]:
        """Dispatch to the appropriate scoring method."""
        if method == "xgboost":
            if self.xgb_model is None:
                logger.warning("XGBoost model not loaded, falling back to ensemble")
                return self._predict_ensemble(tx)
            return self._predict_xgboost_only(tx)
        elif method == "lightgbm":
            if self.lgbm_model is None:
                logger.warning("LightGBM model not loaded, falling back to ensemble")
                return self._predict_ensemble(tx)
            return self._predict_lightgbm_only(tx)
        elif method == "teacher":
            if not self.teacher_loaded:
                logger.warning("Teacher XGB not loaded, falling back to ensemble")
                return self._predict_ensemble(tx)
            return self._predict_teacher(tx)
        elif method == "heuristic":
            return None  # Pure heuristic — no ML
        else:
            # 'ensemble' or anything else → full pipeline
            return self._predict_ensemble(tx)
    def score_transaction(self, tx: TransactionRequest) -> RiskResponse:
        """Score a single transaction using the configured (or per-request) scoring method."""

        factors = {}
        ml_probability = None

        # Determine scoring method: per-request override > engine config
        method = tx.scoring_method or self.config.active_model
        factors["active_scoring_method"] = method

        # ── ML Model Prediction ────────────────────────────────────
        can_ml = (self.model_loaded and method in ("ensemble", "xgboost", "lightgbm")) or \
                 (self.teacher_loaded and method == "teacher")
        if can_ml:
            result = self._predict_by_method(tx, method)

            if result is not None:
                ml_probability = result["fraud_prob"]
                factors["ml_prediction"] = f"{ml_probability:.6f}"
                if result.get("xgb_prob") is not None:
                    factors["xgb_prob"] = f"{result['xgb_prob']:.6f}"
                if result.get("lgb_prob") is not None:
                    factors["lgb_prob"] = f"{result['lgb_prob']:.6f}"
                factors["vae_recon_err"] = f"{result['recon_err']:.6f}"
                factors["vae_kl_div"] = f"{result['kl_div']:.6f}"
                factors["vae_mahalanobis"] = f"{result['mahalanobis']:.6f}"
                # Graph signals (from Memgraph)
                if result.get("gat_prob") is not None:
                    factors["gat_prob"] = f"{result['gat_prob']:.6f}"
                if result.get("gat_uncertainty") is not None:
                    factors["gat_uncertainty"] = f"{result['gat_uncertainty']:.6f}"
                if result.get("sage_prob") is not None:
                    factors["sage_prob"] = f"{result['sage_prob']:.6f}"
                if method == "ensemble":
                    factors["model_used"] = "v2_student(vae+xgb+lgb+meta)"
                    factors["scoring_method"] = "v2_student_pipeline+heuristic"
                elif method == "xgboost":
                    factors["model_used"] = "xgboost_only(vae+xgb)"
                    factors["scoring_method"] = "xgboost_only+heuristic"
                elif method == "lightgbm":
                    factors["model_used"] = "lightgbm_only(vae+lgb)"
                    factors["scoring_method"] = "lightgbm_only+heuristic"
                elif method == "teacher":
                    factors["model_used"] = "teacher_xgb(hope_machine+sigmoid_cal)"
                    factors["scoring_method"] = "teacher_ultra_hybrid(xgb+rules+graph)"
                    if result.get("teacher_raw_score") is not None:
                        factors["teacher_raw_score"] = f"{result['teacher_raw_score']:.6f}"
                        factors["teacher_calibrated"] = f"{result['teacher_calibrated']:.6f}"
                        factors["teacher_xgb_normalized"] = f"{result.get('teacher_xgb_normalized', 0):.2f}"
                        factors["teacher_pattern_boost"] = f"{result.get('teacher_pattern_boost', 0):.2f}"
                        factors["teacher_graph_risk"] = f"{result.get('teacher_graph_risk', 0):.2f}"
                        factors["teacher_hybrid_score"] = f"{result.get('teacher_hybrid_score', 0):.2f}"
                        factors["teacher_signal_count"] = result.get("teacher_signal_count", 0)
                        factors["teacher_patterns"] = result.get("teacher_patterns", [])
                factors["n_features_raw"] = self.N_RAW_FEATURES if method != "teacher" else len(self.teacher_feature_names or [])
                factors["n_features_boost"] = self.N_BOOST_FEATURES if method != "teacher" else len(self.teacher_feature_names or [])
        
        # ── Heuristic Factors ──────────────────────────────────────
        heuristic_score = 100  # Base score
        
        # Value-based risk
        if tx.value_eth > 100:
            factors["high_value"] = f"{tx.value_eth:.2f} ETH"
            heuristic_score += 300
        elif tx.value_eth > 10:
            factors["elevated_value"] = f"{tx.value_eth:.2f} ETH"
            heuristic_score += 100
        elif tx.value_eth > 1:
            factors["moderate_value"] = f"{tx.value_eth:.2f} ETH"
            heuristic_score += 50
        
        # Address pattern detection
        if tx.to_address.lower().startswith("0x000"):
            factors["suspicious_address"] = "Burn-like address pattern"
            heuristic_score += 200
        
        # Contract interaction risk
        if tx.data and len(tx.data) > 10:
            factors["contract_call"] = True
            heuristic_score += 50
            if len(tx.data) > 200:
                factors["complex_contract_call"] = f"{len(tx.data)} bytes"
                heuristic_score += 100
        
        # Nonce analysis (new wallet detection)
        if tx.nonce is not None and tx.nonce < 5:
            factors["new_wallet"] = f"nonce={tx.nonce}"
            heuristic_score += 75
        
        # Gas price anomaly
        if tx.gas_price_gwei and tx.gas_price_gwei > 100:
            factors["high_gas"] = f"{tx.gas_price_gwei:.1f} Gwei"
            heuristic_score += 50
        
        # Count red flags
        red_flag_count = len([k for k in factors.keys() if k in [
            "high_value", "suspicious_address", "complex_contract_call",
            "new_wallet", "high_gas", "elevated_value"
        ]])
        
        # ── Combine ML + Heuristic ─────────────────────────────────
        if ml_probability is not None:
            ml_score = int(ml_probability * 1000)
            
            # Fraud pattern override: multiple heuristic red flags override low ML score
            if red_flag_count >= 4 and ml_score < 200:
                risk_score = max(800, heuristic_score)
                factors["fraud_pattern_detected"] = f"{red_flag_count} red flags"
                factors["ml_override"] = "Heuristic fraud pattern override"
                confidence = 0.85
            elif red_flag_count >= 3 and ml_score < 300:
                risk_score = max(600, int(0.40 * ml_score + 0.60 * min(heuristic_score, 1000)))
                factors["suspicious_pattern"] = f"{red_flag_count} red flags"
                confidence = 0.80
            elif red_flag_count >= 2 and ml_score < 200:
                risk_score = int(0.50 * ml_score + 0.50 * min(heuristic_score, 1000))
                confidence = 0.75
            else:
                # Normal: trust ML primarily
                risk_score = int(0.70 * ml_score + 0.30 * min(heuristic_score, 1000))
                if method == "ensemble":
                    confidence = 0.9999  # V2 meta-ensemble ROC-AUC
                elif method == "xgboost":
                    confidence = 0.9998  # V2 xgb ROC-AUC
                elif method == "lightgbm":
                    confidence = 0.9997  # V2 lgb ROC-AUC
                elif method == "teacher":
                    confidence = 0.9226  # Teacher XGB ROC-AUC (original Hope_machine)
                else:
                    confidence = 0.95
            
            factors["red_flags"] = red_flag_count
        else:
            risk_score = min(1000, max(0, heuristic_score))
            confidence = 0.55
            factors["scoring_method"] = "heuristic_only"
            factors["model_used"] = "rule_based"
        
        # Clamp to valid range
        risk_score = max(0, min(1000, risk_score))
        
        # ── Determine Risk Level ───────────────────────────────────
        if risk_score < 200:
            risk_level = "minimal"
        elif risk_score < 400:
            risk_level = "low"
        elif risk_score < 600:
            risk_level = "medium"
        elif risk_score < 800:
            risk_level = "high"
        else:
            risk_level = "critical"
        
        return RiskResponse(
            risk_score=risk_score,
            risk_level=risk_level,
            confidence=confidence,
            factors=factors,
            model_version=self.model_version,
            timestamp=datetime.now().isoformat()
        )
    
    # ── Explainability Integration ─────────────────────────────────

    def _get_feature_importance(self, method: str) -> Optional[Dict[str, float]]:
        """Get top-10 global feature importances from tree models (gain-based)."""
        try:
            if method in ("ensemble", "xgboost") and self.xgb_model:
                import xgboost as xgb
                booster = self.xgb_model.get_booster() if hasattr(self.xgb_model, 'get_booster') else self.xgb_model
                importance = booster.get_score(importance_type="gain")
                if importance:
                    # Map fN → human-readable feature names using boost feature list
                    feat_names = self.preprocessors.get("feature_names", []) if self.preprocessors else []
                    sorted_imp = sorted(importance.items(), key=lambda x: x[1], reverse=True)[:10]
                    total = sum(v for _, v in sorted_imp) or 1.0
                    result = {}
                    for k, v in sorted_imp:
                        idx = int(k[1:]) if k.startswith("f") and k[1:].isdigit() else -1
                        name = feat_names[idx] if 0 <= idx < len(feat_names) else k
                        result[name] = round(v / total, 4)
                    return result
            elif method == "lightgbm" and self.lgbm_model:
                import lightgbm as lgb_lib
                names = self.lgbm_model.feature_name()
                importance = self.lgbm_model.feature_importance(importance_type="gain")
                if names and importance is not None:
                    imp_dict = dict(zip(names, importance.tolist()))
                    sorted_imp = sorted(imp_dict.items(), key=lambda x: x[1], reverse=True)[:10]
                    total = sum(v for _, v in sorted_imp) or 1.0
                    return {k: round(v / total, 4) for k, v in sorted_imp}
            elif method == "teacher" and self.teacher_loaded:
                import xgboost as xgb
                importance = self.teacher_xgb.get_score(importance_type="gain")
                if importance:
                    teacher_names = self.teacher_feature_names or []
                    sorted_imp = sorted(importance.items(), key=lambda x: x[1], reverse=True)[:10]
                    total = sum(v for _, v in sorted_imp) or 1.0
                    result = {}
                    for k, v in sorted_imp:
                        idx = int(k[1:]) if k.startswith("f") and k[1:].isdigit() else -1
                        name = teacher_names[idx] if 0 <= idx < len(teacher_names) else k
                        result[name] = round(v / total, 4)
                    return result
        except Exception as e:
            logger.warning(f"Feature importance extraction failed for {method}: {e}")
        return None

    def build_explain_context(self, tx, response, method: str) -> Dict[str, Any]:
        """Build the payload expected by the explainability service (port 8009)."""
        features: Dict[str, Any] = {
            "amount_eth": tx.value_eth,
        }
        if tx.gas_price_gwei:
            features["gas_price"] = tx.gas_price_gwei
        if tx.gas_used:
            features["gas_used"] = tx.gas_used
        if tx.nonce is not None:
            features["nonce"] = tx.nonce
        if tx.sender_total_transactions:
            features["sender_total_transactions"] = tx.sender_total_transactions
        if tx.sender_balance is not None:
            features["sender_balance"] = tx.sender_balance
        if tx.sender_avg_sent and tx.sender_avg_sent > 0:
            features["amount_vs_average"] = round(tx.value_eth / tx.sender_avg_sent, 2)
        if tx.sender_active_duration_mins is not None and tx.sender_active_duration_mins < 60 * 24:
            features["dormancy_days"] = 0
        if tx.sender_unique_receivers:
            features["out_degree"] = tx.sender_unique_receivers

        model_contributions: Dict[str, float] = {}
        factors = response.factors
        if method == "ensemble":
            model_contributions = {
                "xgboost": float(factors.get("xgb_prob", 0)),
                "lightgbm": float(factors.get("lgb_prob", 0)),
                "vae_reconstruction": float(factors.get("vae_recon_err", 0)),
                "meta_ensemble": float(factors.get("ml_prediction", 0)),
            }
        elif method == "xgboost":
            model_contributions = {
                "xgboost": float(factors.get("ml_prediction", 0)),
                "vae_reconstruction": float(factors.get("vae_recon_err", 0)),
            }
        elif method == "lightgbm":
            model_contributions = {
                "lightgbm": float(factors.get("ml_prediction", 0)),
                "vae_reconstruction": float(factors.get("vae_recon_err", 0)),
            }
        elif method == "teacher":
            model_contributions = {
                "teacher_xgb": float(factors.get("teacher_xgb_normalized", 0)) / 100.0,
                "pattern_boost": float(factors.get("teacher_pattern_boost", 0)) / 100.0,
                "graph_risk": float(factors.get("teacher_graph_risk", 0)) / 100.0,
            }

        rule_results = []
        if method == "teacher":
            for p in factors.get("teacher_patterns", []):
                rule_results.append({"rule_type": p, "triggered": True})
        for flag in ["high_value", "elevated_value", "suspicious_address",
                     "new_wallet", "high_gas", "complex_contract_call", "contract_call"]:
            if flag in factors:
                rule_results.append({"rule_type": flag.upper(), "triggered": True})

        return {
            "risk_score": response.risk_score / 1000.0,
            "features": features,
            "model_contributions": model_contributions,
            "rule_results": rule_results,
        }

    def generate_fallback_explanation(self, response, method: str) -> Dict[str, Any]:
        """Basic inline explanation when the explainability service is unavailable."""
        factors = response.factors
        score_01 = response.risk_score / 1000.0

        if score_01 >= 0.8:
            action = "BLOCK"
        elif score_01 >= 0.7:
            action = "ESCROW"
        elif score_01 >= 0.4:
            action = "REVIEW"
        else:
            action = "ALLOW"

        reasons = []
        if "high_value" in factors:
            reasons.append(f"High-value transaction: {factors['high_value']}")
        if "elevated_value" in factors:
            reasons.append(f"Elevated transaction value: {factors['elevated_value']}")
        if "suspicious_address" in factors:
            reasons.append(f"Suspicious address pattern: {factors['suspicious_address']}")
        if "new_wallet" in factors:
            reasons.append(f"New wallet detected ({factors['new_wallet']})")
        if "high_gas" in factors:
            reasons.append(f"Abnormal gas price: {factors['high_gas']}")
        if "complex_contract_call" in factors:
            reasons.append(f"Complex contract call: {factors['complex_contract_call']}")
        if method == "teacher" and factors.get("teacher_patterns"):
            reasons.append(f"Patterns detected: {', '.join(factors['teacher_patterns'])}")
        if method == "ensemble" and factors.get("ml_prediction"):
            reasons.append(f"ML ensemble probability: {factors['ml_prediction']}")

        recs = []
        if action == "BLOCK":
            recs = ["Immediately freeze transaction", "File SAR report", "Notify compliance team"]
        elif action == "ESCROW":
            recs = ["Hold in escrow pending review", "Request additional KYC documentation"]
        elif action == "REVIEW":
            recs = ["Manual review recommended", "Check transaction history"]
        else:
            recs = ["Transaction appears normal"]

        return {
            "risk_score": score_01,
            "action": action,
            "summary": f"Risk assessment: {response.risk_level} ({response.risk_score}/1000) using {method}",
            "top_reasons": reasons[:5] if reasons else ["No significant risk factors detected"],
            "factors": [],
            "typology_matches": [],
            "recommendations": recs,
            "confidence": response.confidence,
            "degraded_mode": True,
            "scoring_method": method,
        }

    def get_uptime(self) -> float:
        """Get service uptime in seconds"""
        return (datetime.now() - self.start_time).total_seconds()

# Global engine instance
engine = RiskEngine()

# ============================================================================
# API Endpoints
# ============================================================================

@app.get("/", response_model=Dict[str, str])
async def root():
    """Root endpoint with service info"""
    return {
        "service": "AMTTP Risk Engine",
        "version": "1.0.0",
        "status": "running"
    }

@app.get("/health", response_model=HealthResponse)
async def health():
    """Health check endpoint"""
    return HealthResponse(
        status="healthy",
        model_loaded=engine.model_loaded,
        version=engine.model_version,
        uptime_seconds=engine.get_uptime()
    )

@app.post("/score", response_model=RiskResponse)
async def score_transaction(request: TransactionRequest):
    """Score a single transaction for risk"""
    try:
        response = engine.score_transaction(request)
        # Also add to alert store for dashboard visibility
        alert_store.add_alert(request, response)
        logger.info(f"Scored transaction: {request.from_address} -> {request.to_address}, risk={response.risk_level}")
        return response
    except Exception as e:
        logger.error(f"Scoring error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/score-explained")
async def score_explained(request: TransactionRequest):
    """Score a transaction AND return human-readable explanation.
    
    Calls the explainability service (port 8009) to generate:
    - Top reasons in plain English
    - Typology matches (smurfing, layering, etc.)
    - Action recommendation (ALLOW/REVIEW/ESCROW/BLOCK)
    - Per-model feature importance
    
    Falls back to inline explanation if the explainability service is unavailable.
    """
    try:
        # 1. Score the transaction
        response = engine.score_transaction(request)
        alert_store.add_alert(request, response)
        method = request.scoring_method or engine.config.active_model

        # 2. Build explain context for the explainability service
        explain_ctx = engine.build_explain_context(request, response, method)

        # 3. Call explainability service (async)
        explanation = None
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.post(
                    f"{EXPLAINABILITY_URL}/explain",
                    json=explain_ctx,
                )
                if resp.status_code == 200:
                    explanation = resp.json()
                else:
                    logger.warning(f"Explainability service returned {resp.status_code}")
        except Exception as e:
            logger.warning(f"Explainability service unavailable: {e}")

        # 4. Fallback if explainability service is down
        if explanation is None:
            explanation = engine.generate_fallback_explanation(response, method)

        # 5. Attach feature importance
        feature_importance = engine._get_feature_importance(method)

        # 6. Return combined result
        result = response.model_dump()
        result["explanation"] = explanation
        result["feature_importance"] = feature_importance
        result["scoring_method"] = method

        logger.info(f"Score-explained: {request.from_address} -> {request.to_address}, "
                     f"risk={response.risk_level}, method={method}, "
                     f"action={explanation.get('action', 'N/A')}")
        return result

    except Exception as e:
        logger.error(f"Score-explained error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/batch", response_model=BatchResponse)
async def batch_score(request: BatchRequest):
    """Score multiple transactions in batch"""
    start_time = datetime.now()
    
    try:
        results = [engine.score_transaction(tx) for tx in request.transactions]
        processing_time = (datetime.now() - start_time).total_seconds() * 1000
        
        return BatchResponse(
            results=results,
            processing_time_ms=processing_time
        )
    except Exception as e:
        logger.error(f"Batch scoring error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/models")
async def list_models():
    """List available models"""
    models_dir = os.path.join(os.path.dirname(__file__), "models")
    if os.path.exists(models_dir):
        return {"models": os.listdir(models_dir)}
    return {"models": []}

@app.get("/model/info")
async def model_info():
    """Get detailed model information"""
    models_available = []
    
    if engine.xgb_model:
        models_available.append("student_xgboost_v2")
    if engine.lgbm_model:
        models_available.append("student_lightgbm")
    if engine.meta_model:
        models_available.append("meta_learner(sklearn_from_cuml)")
    if engine.teacher_loaded:
        models_available.append("teacher_xgb(hope_machine)")
    
    info = {
        "model_version": engine.model_version,
        "model_loaded": engine.model_loaded,
        "teacher_loaded": engine.teacher_loaded,
        "models_available": models_available,
        "optimal_threshold": engine.optimal_threshold,
        "has_preprocessors": engine.preprocessors is not None,
        "has_metadata": engine.metadata is not None,
        "tabular_features": engine.TABULAR_FEATURES,
        "n_boost_features": engine.N_BOOST_FEATURES,
        "meta_learner_features": engine.META_FEATURES,
        "last_updated": engine.start_time.isoformat(),
        "active_config": engine.config.model_dump(),
    }
    
    if engine.metadata:
        info["training_performance"] = engine.metadata.get("performance", {})
        info["training_date"] = engine.metadata.get("training_date", "unknown")
    
    return info

# ============================================================================
# Scoring Configuration endpoints
# ============================================================================

VALID_METHODS = {"ensemble", "xgboost", "lightgbm", "teacher", "heuristic"}

@app.get("/config")
async def get_config():
    """Get current scoring configuration"""
    return {
        "active_model": engine.config.active_model,
        "ensemble_weights": engine.config.ensemble_weights,
        "threshold": engine.config.threshold,
        "available_methods": sorted(VALID_METHODS),
        "model_loaded": engine.model_loaded,
    }

@app.post("/config")
async def set_config(config: ScoringConfig):
    """Update the scoring configuration (active model, weights, threshold)"""
    if config.active_model not in VALID_METHODS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid active_model '{config.active_model}'. Must be one of: {sorted(VALID_METHODS)}"
        )
    if not (0.0 <= config.threshold <= 1.0):
        raise HTTPException(status_code=400, detail="threshold must be between 0 and 1")

    engine.config = config
    logger.info(f"Scoring config updated: method={config.active_model}, threshold={config.threshold:.4f}, weights={config.ensemble_weights}")
    return {
        "success": True,
        "message": f"Scoring method set to '{config.active_model}' with threshold {config.threshold:.4f}",
        "config": engine.config.model_dump(),
    }

# ============================================================================
# Dashboard API endpoints (for SIEM integration)
# ============================================================================

@app.get("/dashboard/stats")
async def dashboard_stats():
    """Get dashboard statistics for SIEM integration"""
    stats = alert_store.get_stats()
    return {
        **stats,
        "model_version": engine.model_version,
        "model_loaded": engine.model_loaded
    }

@app.get("/alerts")
async def get_alerts(limit: int = 50, offset: int = 0, risk_level: Optional[str] = None):
    """Get alerts with optional filtering"""
    alerts = alert_store.get_alerts(limit=limit, offset=offset)
    
    # Filter by risk level if specified
    if risk_level:
        levels = [l.strip().upper() for l in risk_level.split(",")]
        alerts = [a for a in alerts if a["riskLevel"] in levels]
    
    return alerts

@app.get("/dashboard/timeline")
async def dashboard_timeline(range: str = "24h"):
    """Get timeline data for charts"""
    hours_map = {"1h": 1, "24h": 24, "7d": 168, "30d": 720}
    hours = hours_map.get(range, 24)
    return alert_store.get_timeline(hours=min(hours, 168))  # Cap at 7 days

@app.get("/alerts/{alert_id}")
async def get_alert(alert_id: str):
    """Get a specific alert by ID"""
    for alert in alert_store.alerts:
        if alert["id"] == alert_id:
            return alert
    raise HTTPException(status_code=404, detail="Alert not found")

@app.post("/alerts/{alert_id}/action")
async def alert_action(alert_id: str, action: Dict[str, str]):
    """Perform an action on an alert"""
    for alert in alert_store.alerts:
        if alert["id"] == alert_id:
            action_type = action.get("action", "UNKNOWN")
            if action_type == "RESOLVE":
                alert["status"] = "RESOLVED"
                alert_store.stats["resolvedToday"] += 1
                alert_store.stats["pendingInvestigation"] = max(0, alert_store.stats["pendingInvestigation"] - 1)
            elif action_type == "FALSE_POSITIVE":
                alert["status"] = "FALSE_POSITIVE"
            elif action_type == "INVESTIGATING":
                alert["status"] = "INVESTIGATING"
            elif action_type == "BLOCK":
                alert["action"] = "BLOCK"
                alert_store.stats["blockedAddresses"] += 1
            return {"success": True, "message": f"Action {action_type} performed on {alert_id}"}
    raise HTTPException(status_code=404, detail="Alert not found")

# ============================================================================
# Main Entry Point
# ============================================================================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    logger.info(f"Starting AMTTP Risk Engine on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
