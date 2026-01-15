"""
AMTTP ML Pipeline - Memgraph Graph Service

Core service for interacting with Memgraph graph database.
Supports both native mgclient (Bolt) and neo4j driver (fallback).
"""
import os
import logging
from typing import Dict, Any, List, Optional, Tuple, Union
from dataclasses import dataclass
from contextlib import contextmanager

logger = logging.getLogger(__name__)

# Try to import mgclient (native Memgraph driver - fastest)
# pymgclient provides the mgclient module with pre-built Windows wheels
HAVE_MGCLIENT = False
MGCLIENT_TYPE = None
try:
    import mgclient
    HAVE_MGCLIENT = True
    # Check if it's from pymgclient package
    try:
        import importlib.metadata
        pymgclient_version = importlib.metadata.version('pymgclient')
        MGCLIENT_TYPE = f"pymgclient-{pymgclient_version}"
        logger.info(f"pymgclient ({pymgclient_version}) available - will use native Memgraph driver")
    except:
        MGCLIENT_TYPE = "mgclient"
        logger.info("mgclient available - will use native Memgraph driver")
except ImportError:
    mgclient = None
    logger.info("No native Memgraph client available (mgclient/pymgclient not installed)")

# Try to import neo4j driver (fallback - good compatibility)
try:
    from neo4j import GraphDatabase
    HAVE_NEO4J = True
    logger.info("neo4j driver available - can use as fallback")
except ImportError:
    GraphDatabase = None
    HAVE_NEO4J = False
    logger.info("neo4j driver not available")

# Try to import requests for HTTP proxy
try:
    import requests
    HAVE_REQUESTS = True
except ImportError:
    requests = None
    HAVE_REQUESTS = False


@dataclass
class MemgraphConfig:
    """Configuration for Memgraph connection."""
    host: str = "localhost"
    port: int = 7687
    user: Optional[str] = None
    password: Optional[str] = None
    # HTTP proxy mode (alternative to Bolt)
    proxy_url: Optional[str] = None
    api_key: Optional[str] = None
    # Connection settings
    timeout: int = 30
    max_retries: int = 3
    # Driver preference: 'auto', 'mgclient', 'neo4j', 'proxy'
    driver_preference: str = 'auto'

    @classmethod
    def from_env(cls) -> "MemgraphConfig":
        """Create config from environment variables."""
        return cls(
            host=os.getenv("MEMGRAPH_HOST", "localhost"),
            port=int(os.getenv("MEMGRAPH_PORT", "7687")),
            user=os.getenv("MEMGRAPH_USER"),
            password=os.getenv("MEMGRAPH_PASSWORD"),
            proxy_url=os.getenv("MEMGRAPH_PROXY_URL"),
            api_key=os.getenv("MEMGRAPH_API_KEY"),
            driver_preference=os.getenv("MEMGRAPH_DRIVER", "auto"),
        )


class MemgraphService:
    """
    Service for interacting with Memgraph graph database.
    
    Driver Selection (in 'auto' mode):
    1. mgclient (native) - Fastest, requires C build tools
    2. neo4j driver - Good compatibility, pure Python
    3. HTTP proxy - For cloud/remote deployments
    
    Provides methods for:
    - Running Cypher queries
    - Graph-based feature extraction
    - Transaction graph updates
    - Sanctions checking
    """
    
    def __init__(self, config: Optional[MemgraphConfig] = None):
        """
        Initialize Memgraph service.
        
        Args:
            config: Memgraph configuration. If None, loads from environment.
        """
        self.config = config or MemgraphConfig.from_env()
        
        # Connection objects
        self._mgclient_conn = None
        self._neo4j_driver = None
        
        # Determine which driver to use
        self._driver_mode = self._select_driver()
        logger.info(f"Memgraph service initialized with driver: {self._driver_mode}")
    
    def _select_driver(self) -> str:
        """Select the best available driver."""
        preference = self.config.driver_preference.lower()
        
        # If user specified a preference, try to honor it
        if preference == 'mgclient':
            if HAVE_MGCLIENT:
                return 'mgclient'
            raise RuntimeError("mgclient requested but not installed")
        
        if preference == 'neo4j':
            if HAVE_NEO4J:
                return 'neo4j'
            raise RuntimeError("neo4j driver requested but not installed")
        
        if preference == 'proxy':
            if self.config.proxy_url and HAVE_REQUESTS:
                return 'proxy'
            raise RuntimeError("HTTP proxy requested but not configured or requests not installed")
        
        # Auto mode: try in order of preference
        if preference == 'auto':
            # Check for proxy first (explicit configuration)
            if self.config.proxy_url and HAVE_REQUESTS:
                return 'proxy'
            
            # Try mgclient (native, fastest)
            if HAVE_MGCLIENT:
                try:
                    # Test connection
                    test_conn = mgclient.connect(
                        host=self.config.host,
                        port=self.config.port,
                    )
                    test_conn.close()
                    return 'mgclient'
                except Exception as e:
                    logger.warning(f"mgclient connection test failed: {e}")
            
            # Fall back to neo4j driver
            if HAVE_NEO4J:
                try:
                    # Test connection
                    bolt_uri = f"bolt://{self.config.host}:{self.config.port}"
                    test_driver = GraphDatabase.driver(bolt_uri)
                    with test_driver.session() as session:
                        session.run("RETURN 1")
                    test_driver.close()
                    return 'neo4j'
                except Exception as e:
                    logger.warning(f"neo4j driver connection test failed: {e}")
            
            raise RuntimeError(
                "No working Memgraph driver available. "
                "Install mgclient (pip install mgclient) or neo4j (pip install neo4j)"
            )
        
        raise ValueError(f"Unknown driver preference: {preference}")
    
    def _connect_mgclient(self):
        """Establish native mgclient connection."""
        if self._mgclient_conn is not None:
            return
        
        try:
            if self.config.user and self.config.password:
                self._mgclient_conn = mgclient.connect(
                    host=self.config.host,
                    port=self.config.port,
                    username=self.config.user,
                    password=self.config.password,
                )
            else:
                self._mgclient_conn = mgclient.connect(
                    host=self.config.host,
                    port=self.config.port,
                )
            logger.info(f"Connected to Memgraph via mgclient at {self.config.host}:{self.config.port}")
        except Exception as e:
            logger.error(f"mgclient connection failed: {e}")
            raise
    
    def _connect_neo4j(self):
        """Establish neo4j driver connection."""
        if self._neo4j_driver is not None:
            return
        
        try:
            bolt_uri = f"bolt://{self.config.host}:{self.config.port}"
            if self.config.user and self.config.password:
                self._neo4j_driver = GraphDatabase.driver(
                    bolt_uri,
                    auth=(self.config.user, self.config.password)
                )
            else:
                self._neo4j_driver = GraphDatabase.driver(bolt_uri)
            logger.info(f"Connected to Memgraph via neo4j driver at {bolt_uri}")
        except Exception as e:
            logger.error(f"neo4j driver connection failed: {e}")
            raise
    
    def close(self):
        """Close all connections."""
        if self._mgclient_conn is not None:
            try:
                self._mgclient_conn.close()
            except Exception:
                pass
            self._mgclient_conn = None
        
        if self._neo4j_driver is not None:
            try:
                self._neo4j_driver.close()
            except Exception:
                pass
            self._neo4j_driver = None
    
    @contextmanager
    def cursor(self):
        """Context manager for mgclient cursor operations."""
        if self._driver_mode != 'mgclient':
            raise RuntimeError("cursor() only available with mgclient driver")
        self._connect_mgclient()
        cur = self._mgclient_conn.cursor()
        try:
            yield cur
        finally:
            cur.close()
    
    def execute(self, query: str, params: Optional[Dict[str, Any]] = None) -> List[Tuple]:
        """
        Execute a Cypher query and return results.
        
        Args:
            query: Cypher query string
            params: Query parameters
            
        Returns:
            List of result tuples
        """
        if self._driver_mode == 'proxy':
            return self._execute_proxy(query, params)
        elif self._driver_mode == 'mgclient':
            return self._execute_mgclient(query, params)
        elif self._driver_mode == 'neo4j':
            return self._execute_neo4j(query, params)
        else:
            raise RuntimeError(f"Unknown driver mode: {self._driver_mode}")
    
    def _execute_mgclient(self, query: str, params: Optional[Dict[str, Any]] = None) -> List[Tuple]:
        """Execute query via native mgclient."""
        self._connect_mgclient()
        cur = self._mgclient_conn.cursor()
        try:
            cur.execute(query, params or {})
            return cur.fetchall()
        finally:
            cur.close()
    
    def _execute_neo4j(self, query: str, params: Optional[Dict[str, Any]] = None) -> List[Tuple]:
        """Execute query via neo4j driver."""
        self._connect_neo4j()
        with self._neo4j_driver.session() as session:
            result = session.run(query, params or {})
            # Convert neo4j records to tuples
            return [tuple(record.values()) for record in result]
    
    def _execute_proxy(self, query: str, params: Optional[Dict[str, Any]] = None) -> List[Tuple]:
        """Execute query via HTTP proxy."""
        if not HAVE_REQUESTS:
            raise RuntimeError("requests not installed")
        
        url = f"{self.config.proxy_url.rstrip('/')}/query"
        headers = {"Content-Type": "application/json"}
        if self.config.api_key:
            headers["X-API-KEY"] = self.config.api_key
        
        payload = {"query": query, "params": params or {}}
        
        for attempt in range(self.config.max_retries):
            try:
                resp = requests.post(url, json=payload, timeout=self.config.timeout, headers=headers)
                resp.raise_for_status()
                data = resp.json()
                return [tuple(row) for row in data.get("results", [])]
            except Exception as e:
                logger.warning(f"Proxy query attempt {attempt + 1} failed: {e}")
                if attempt == self.config.max_retries - 1:
                    raise
        
        return []
    
    def health_check(self) -> Dict[str, Any]:
        """Check Memgraph connection health."""
        try:
            result = self.execute("RETURN 1 AS health")
            return {
                "status": "healthy",
                "connected": True,
                "driver": self._driver_mode,
                "native_client": MGCLIENT_TYPE if self._driver_mode == 'mgclient' else None,
                "host": self.config.proxy_url if self._driver_mode == 'proxy' else f"{self.config.host}:{self.config.port}",
                "mgclient_available": HAVE_MGCLIENT,
                "neo4j_available": HAVE_NEO4J,
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "connected": False,
                "driver": self._driver_mode,
                "error": str(e),
                "mgclient_available": HAVE_MGCLIENT,
                "neo4j_available": HAVE_NEO4J,
            }
    
    def get_node_count(self) -> int:
        """Get total number of nodes in the graph."""
        result = self.execute("MATCH (n) RETURN count(n) AS cnt")
        return result[0][0] if result else 0
    
    def get_edge_count(self) -> int:
        """Get total number of edges in the graph."""
        result = self.execute("MATCH ()-[r]->() RETURN count(r) AS cnt")
        return result[0][0] if result else 0
    
    def get_graph_stats(self) -> Dict[str, Any]:
        """Get comprehensive graph statistics."""
        try:
            nodes = self.get_node_count()
            edges = self.get_edge_count()
            
            # Count different address types
            stats = {"nodes": nodes, "edges": edges, "driver": self._driver_mode}
            
            # Count sanctioned addresses
            try:
                sanctioned = self.execute("MATCH (s:Sanctions) RETURN count(s) AS cnt")
                stats["sanctioned_addresses"] = sanctioned[0][0] if sanctioned else 0
            except:
                stats["sanctioned_addresses"] = 0
            
            # Count mixer addresses
            try:
                mixers = self.execute("MATCH (m:Mixer) RETURN count(m) AS cnt")
                stats["mixer_addresses"] = mixers[0][0] if mixers else 0
            except:
                stats["mixer_addresses"] = 0
            
            # Count fraud addresses
            try:
                fraud = self.execute("MATCH (f:Fraud) RETURN count(f) AS cnt")
                stats["fraud_addresses"] = fraud[0][0] if fraud else 0
            except:
                stats["fraud_addresses"] = 0
            
            # Calculate density
            stats["density"] = edges / (nodes * (nodes - 1)) if nodes > 1 else 0
            
            return stats
        except Exception as e:
            logger.error(f"Failed to get graph stats: {e}")
            return {"error": str(e), "driver": self._driver_mode}
    
    def get_driver_info(self) -> Dict[str, Any]:
        """Get information about available and active drivers."""
        return {
            "active_driver": self._driver_mode,
            "native_client_type": MGCLIENT_TYPE if self._driver_mode == 'mgclient' else None,
            "available_drivers": {
                "mgclient": HAVE_MGCLIENT,
                "mgclient_type": MGCLIENT_TYPE,
                "neo4j": HAVE_NEO4J,
                "proxy": HAVE_REQUESTS and bool(self.config.proxy_url),
            },
            "config": {
                "host": self.config.host,
                "port": self.config.port,
                "preference": self.config.driver_preference,
            }
        }


# Singleton instance
_service: Optional[MemgraphService] = None


def get_memgraph_service(config: Optional[MemgraphConfig] = None) -> MemgraphService:
    """Get or create singleton Memgraph service instance."""
    global _service
    if _service is None:
        _service = MemgraphService(config)
    return _service


def reset_memgraph_service():
    """Reset the singleton service (useful for testing or reconfiguration)."""
    global _service
    if _service is not None:
        _service.close()
        _service = None
