"""
AMTTP ML Pipeline - Configuration Settings

Simplified configuration for production inference.
"""
import os
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field


@dataclass
class InferenceConfig:
    """Inference settings."""
    models_dir: Path = Path("models/trained")
    threshold: float = 0.55  # OPTIMIZED: best F1 score, balances detection vs false positives
    batch_size: int = 1000
    
    # Action thresholds - OPTIMIZED to minimize false positives
    approve_threshold: float = 0.20   # Very low risk - auto approve
    monitor_threshold: float = 0.40   # Raised from 0.35 - reduce FPs
    review_threshold: float = 0.55    # Raised from 0.50 - optimal F1
    escrow_threshold: float = 0.75    # Raised from 0.65 - only high confidence
    
    # IMPORTANT: Only flag if BOTH ML score high AND has supporting evidence
    require_multi_signal: bool = True  # Require graph OR pattern evidence
    
    # NEW: Behavioral pattern boosts (add to ML score)
    pattern_boosts: dict = field(default_factory=lambda: {
        "SMURFING": 0.25,
        "LAYERING": 0.15,
        "FAN_OUT": 0.15,
        "FAN_IN": 0.10,
        "PEELING": 0.20,
        "STRUCTURING": 0.25,
    })
    
    # NEW: Graph connection boosts
    graph_boosts: dict = field(default_factory=lambda: {
        "direct_sanctioned": 0.40,
        "direct_mixer": 0.30,
        "2hop_sanctioned": 0.20,
        "3hop_sanctioned": 0.10,
        "high_centrality": 0.05,
    })


@dataclass
class MemgraphConfig:
    """Memgraph connection settings."""
    host: str = "localhost"
    port: int = 7687
    user: Optional[str] = None
    password: Optional[str] = None
    driver_preference: str = "auto"  # 'auto', 'mgclient', 'neo4j'
    
    @classmethod
    def from_env(cls) -> "MemgraphConfig":
        """Load from environment variables."""
        return cls(
            host=os.getenv("MEMGRAPH_HOST", "localhost"),
            port=int(os.getenv("MEMGRAPH_PORT", "7687")),
            user=os.getenv("MEMGRAPH_USER"),
            password=os.getenv("MEMGRAPH_PASSWORD"),
            driver_preference=os.getenv("MEMGRAPH_DRIVER", "auto"),
        )


@dataclass
class HybridConfig:
    """Hybrid prediction settings - RECALIBRATED Dec 2024."""
    # Changed from 70/30 to 30/35/35 (ML/Graph/Patterns)
    tabular_weight: float = 0.30      # Was 0.70 - ML alone misses threats
    graph_weight: float = 0.35        # Was 0.30 - graph connections important
    pattern_weight: float = 0.35      # NEW - behavioral patterns
    fallback_to_tabular: bool = True
    
    # Multi-signal multipliers
    two_signal_boost: float = 1.20    # 20% boost if 2 methods agree
    three_signal_boost: float = 1.50  # 50% boost if all 3 methods agree


@dataclass
class APIConfig:
    """API server settings."""
    host: str = "0.0.0.0"
    port: int = 8000
    workers: int = 1
    reload: bool = False


@dataclass
class Settings:
    """Master settings container."""
    project_name: str = "amttp_ml"
    base_dir: Path = field(default_factory=lambda: Path(__file__).parent.parent)
    
    # Sub-configs
    inference: InferenceConfig = field(default_factory=InferenceConfig)
    memgraph: MemgraphConfig = field(default_factory=MemgraphConfig)
    hybrid: HybridConfig = field(default_factory=HybridConfig)
    api: APIConfig = field(default_factory=APIConfig)
    
    @classmethod
    def from_env(cls) -> "Settings":
        """Create settings from environment variables."""
        settings = cls()
        settings.memgraph = MemgraphConfig.from_env()
        
        # Override from env
        if os.getenv("AMTTP_THRESHOLD"):
            settings.inference.threshold = float(os.getenv("AMTTP_THRESHOLD"))
        if os.getenv("AMTTP_API_PORT"):
            settings.api.port = int(os.getenv("AMTTP_API_PORT"))
        
        return settings


# Global settings singleton
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Get or create global settings instance."""
    global _settings
    if _settings is None:
        _settings = Settings.from_env()
    return _settings


def reset_settings():
    """Reset settings (useful for testing)."""
    global _settings
    _settings = None
