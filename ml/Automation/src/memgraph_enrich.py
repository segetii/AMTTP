#!/usr/bin/env python3
"""
Memgraph enrichment helper (packaged for src.memgraph_enrich import).
This is based on Version4 implementation and supports Bolt or HTTP proxy.
"""
from __future__ import annotations
import time
import logging
from typing import List, Dict, Any, Optional

log = logging.getLogger("MemgraphEnricher")
log.setLevel(logging.INFO)

# Optional imports
try:
    import mgclient  # type: ignore
    HAVE_MGCLIENT = True
except Exception:
    mgclient = None  # type: ignore
    HAVE_MGCLIENT = False

try:
    import requests  # type: ignore
    HAVE_REQUESTS = True
except Exception:
    requests = None  # type: ignore
    HAVE_REQUESTS = False


class MemgraphEnricher:
    """
    Instantiate with either:
      MemgraphEnricher(host=..., port=7687)          -> uses Bolt (mgclient)
    or
      MemgraphEnricher(proxy_url="https://abcd.trycloudflare.com", api_key="...") -> uses HTTP proxy
    """

    def __init__(
        self,
        host: Optional[str] = None,
        port: int = 7687,
        user: Optional[str] = None,
        password: Optional[str] = None,
        proxy_url: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout: int = 30,
    ) -> None:
        self.host = host
        self.port = int(port) if port is not None else None
        self.user = user
        self.password = password
        self.proxy_url = proxy_url.rstrip("/") if proxy_url else None
        self.api_key = api_key
        self.timeout = timeout
        self.conn = None
        self._using_proxy = bool(self.proxy_url)
        if self._using_proxy and not HAVE_REQUESTS:
            raise RuntimeError("requests library required for HTTP proxy mode")
        if (not self._using_proxy) and not HAVE_MGCLIENT:
            raise RuntimeError("mgclient required for Bolt mode but not available")

    # ---------------------------
    # Bolt (mgclient) path
    # ---------------------------
    def _connect_bolt(self) -> None:
        if self.conn:
            return
        if not HAVE_MGCLIENT:
            raise RuntimeError("mgclient not installed")
        if self.user and self.password:
            self.conn = mgclient.connect(host=self.host, port=self.port, username=self.user, password=self.password)  # type: ignore[arg-type]
        else:
            self.conn = mgclient.connect(host=self.host, port=self.port)  # type: ignore[arg-type]
        log.info(f"Connected to Memgraph (bolt) at {self.host}:{self.port}")

    def _query_bolt(self, addrs: List[str]) -> Dict[str, Dict[str, Any]]:
        self._connect_bolt()
        cur = self.conn.cursor()
        q = (
            """
        UNWIND $addrs AS a
        OPTIONAL MATCH (addr:Address {id: a})
        OPTIONAL MATCH (s:Address)-[:TAGGED_AS]->(:Tag {name:'sanctioned'})
        OPTIONAL MATCH p = shortestPath((addr)-[*..6]-(s))
        OPTIONAL MATCH (addr)-[:IN_CLUSTER]->(c:Cluster)
        RETURN a AS addr, CASE WHEN p IS NULL THEN 999 ELSE length(p) END AS dist,
               coalesce(c.id, -1) AS community, coalesce(c.score, 0.0) AS score
        """
        )
        try:
            cur.execute(q, {"addrs": addrs})
            rows = cur.fetchall()
            out: Dict[str, Dict[str, Any]] = {}
            for row in rows:
                a = row[0]
                dist = int(row[1]) if row[1] is not None else 999
                comm = int(row[2]) if row[2] is not None else -1
                score = float(row[3]) if row[3] is not None else 0.0
                out[a] = {"dist": dist, "community": comm, "score": score}
            for a in addrs:
                if a not in out:
                    out[a] = {"dist": 999, "community": -1, "score": 0.0}
            return out
        finally:
            cur.close()

    # ---------------------------
    # HTTP proxy path
    # ---------------------------
    def _query_http_proxy(self, addrs: List[str]) -> Dict[str, Dict[str, Any]]:
        if not HAVE_REQUESTS:
            raise RuntimeError("requests not installed")
        url = f"{self.proxy_url.rstrip('/')}/batch_query"  # type: ignore[union-attr]
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["X-API-KEY"] = self.api_key
        payload = {"addrs": addrs}
        # retry with exponential backoff for transient failures
        backoff = 1.0
        for attempt in range(3):
            try:
                resp = requests.post(url, json=payload, timeout=self.timeout, headers=headers)  # type: ignore[operator]
                if resp.status_code != 200:
                    log.warning(f"Proxy returned status {resp.status_code}: {resp.text}")
                    resp.raise_for_status()
                data = resp.json()
                # ensure keys exist for all addrs
                for a in addrs:
                    if a not in data:
                        data[a] = {"dist": 999, "community": -1, "score": 0.0}
                return data
            except Exception as e:
                log.exception(f"HTTP proxy query attempt {attempt+1} failed: {e}")
                time.sleep(backoff)
                backoff *= 2
        # final fallback: return defaults
        out = {a: {"dist": 999, "community": -1, "score": 0.0} for a in addrs}
        return out

    # ---------------------------
    # Public entrypoint
    # ---------------------------
    def query_batch_addresses(self, addrs: List[str]) -> Dict[str, Dict[str, Any]]:
        """
        Query in batches and return dict[address] -> {"dist":int,"community":int,"score":float}
        """
        if not addrs:
            return {}
        if self._using_proxy:
            # split into conservative batches to avoid payloads too large
            out: Dict[str, Dict[str, Any]] = {}
            batch_size = 500
            for i in range(0, len(addrs), batch_size):
                b = addrs[i : i + batch_size]
                res = self._query_http_proxy(b)
                out.update(res)
            return out
        else:
            # bolt path: query up to ~2000 addresses per UNWIND to avoid huge results
            out = {}
            batch_size = 2000
            for i in range(0, len(addrs), batch_size):
                b = addrs[i : i + batch_size]
                res = self._query_bolt(b)
                out.update(res)
            return out
