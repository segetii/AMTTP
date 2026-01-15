#!/usr/bin/env python3
"""
AMTTP Automation CLI

Unified command-line interface for fraud detection operations.
"""
import sys
import json
from pathlib import Path
from typing import Optional
import typer

ROOT = Path(__file__).resolve().parents[1]
ML_PIPELINE = ROOT / "ml" / "Automation" / "ml_pipeline"
sys.path.insert(0, str(ROOT / "ml" / "Automation"))

app = typer.Typer(name="amttp", help="AMTTP Fraud Detection CLI")


@app.command()
def serve(
    host: str = typer.Option("0.0.0.0", help="Host to bind to"),
    port: int = typer.Option(8000, help="Port to listen on"),
    mode: str = typer.Option("cpu", help="Mode: cpu, hybrid, or realtime"),
):
    """Start the fraud detection API server."""
    import uvicorn
    
    if mode == "realtime":
        typer.echo(f"🚀 Starting Real-time Scoring API on {host}:{port}")
        uvicorn.run("ml_pipeline.graph.realtime_api:app", host=host, port=port, reload=False)
    elif mode == "hybrid":
        typer.echo(f"🚀 Starting Hybrid API on {host}:{port}")
        uvicorn.run("ml_pipeline.graph.api:app", host=host, port=port, reload=False)
    else:
        typer.echo(f"🚀 Starting CPU Inference API on {host}:{port}")
        uvicorn.run("ml_pipeline.inference.cpu_api:app", host=host, port=port, reload=False)


@app.command()
def health():
    """Check health of all services."""
    import requests
    
    typer.echo("Service Health Check:")
    typer.echo("-" * 40)
    
    # CPU Inference API
    try:
        r = requests.get("http://localhost:8000/health", timeout=3)
        status = r.json()
        typer.echo(f"✅ CPU Inference API (8000): {status.get('status')}")
    except:
        typer.echo("❌ CPU Inference API (8000): Not running")
    
    # Real-time API
    try:
        r = requests.get("http://localhost:8001/health", timeout=3)
        status = r.json()
        typer.echo(f"✅ Real-time API (8001): {status.get('status')}")
    except:
        typer.echo("❌ Real-time API (8001): Not running")
    
    # Memgraph
    try:
        from ml_pipeline.graph.service import MemgraphService
        svc = MemgraphService()
        h = svc.health_check()
        typer.echo(f"✅ Memgraph ({h.get('host')}): {h.get('driver')} - {h.get('status')}")
    except Exception as e:
        typer.echo(f"❌ Memgraph: {e}")


@app.command("graph-stats")
def graph_stats():
    """Show graph database statistics."""
    from ml_pipeline.graph.service import MemgraphService
    svc = MemgraphService()
    stats = svc.get_graph_stats()
    
    typer.echo("Graph Statistics:")
    typer.echo("-" * 40)
    typer.echo(f"  Nodes:      {stats.get('nodes', 0):,}")
    typer.echo(f"  Edges:      {stats.get('edges', 0):,}")
    typer.echo(f"  Sanctioned: {stats.get('sanctioned_addresses', 0):,}")
    typer.echo(f"  Mixers:     {stats.get('mixer_addresses', 0):,}")
    typer.echo(f"  Fraud:      {stats.get('fraud_addresses', 0):,}")
    typer.echo(f"  Density:    {stats.get('density', 0):.6f}")
    typer.echo(f"  Driver:     {stats.get('driver', 'unknown')}")


@app.command()
def info():
    """Show model and system information."""
    models_dir = ML_PIPELINE / "models" / "trained"
    
    typer.echo("AMTTP Fraud Detection System")
    typer.echo("=" * 40)
    typer.echo("\nTrained Models:")
    for f in sorted(models_dir.iterdir()):
        size = f.stat().st_size / 1024
        typer.echo(f"  {f.name:<25} {size:>8.1f} KB")
    
    typer.echo("\nAPI Endpoints:")
    typer.echo("  CPU Inference:  http://localhost:8000")
    typer.echo("  Real-time:      http://localhost:8001")
    typer.echo("  Swagger Docs:   http://localhost:8000/docs")
    typer.echo("  WebSocket:      ws://localhost:8001/ws/stream")


@app.command()
def score(
    from_addr: str = typer.Argument(..., help="Sender address"),
    to_addr: str = typer.Argument(..., help="Receiver address"),
    value: float = typer.Option(1.0, help="Transaction value in ETH"),
):
    """Score a single transaction."""
    import time
    import requests
    
    tx_hash = f"cli-{int(time.time())}"
    timestamp = int(time.time())
    
    payload = {
        "tx_hash": tx_hash,
        "from_address": from_addr,
        "to_address": to_addr,
        "value": value,
        "timestamp": timestamp,
    }
    
    try:
        r = requests.post("http://localhost:8001/score", json=payload, timeout=10)
        result = r.json()
        
        typer.echo("\nTransaction Score:")
        typer.echo("-" * 40)
        typer.echo(f"  From:       {from_addr[:10]}...{from_addr[-8:]}")
        typer.echo(f"  To:         {to_addr[:10]}...{to_addr[-8:]}")
        typer.echo(f"  Value:      {value} ETH")
        typer.echo(f"  Risk Score: {result['risk_scores']['transaction']:.3f}")
        typer.echo(f"  Action:     {result['action']}")
        typer.echo(f"  Confidence: {result['confidence']:.1%}")
        typer.echo(f"  Latency:    {result['processing_time_ms']:.1f} ms")
        
    except requests.exceptions.ConnectionError:
        typer.echo("❌ Real-time API not running. Start with: amttp serve --mode realtime --port 8001")
    except Exception as e:
        typer.echo(f"❌ Error: {e}")


@app.command("add-sanction")
def add_sanction(address: str = typer.Argument(..., help="Address to sanction")):
    """Add an address to the sanctions list."""
    from ml_pipeline.graph.service import MemgraphService
    svc = MemgraphService()
    
    query = """
    MERGE (a:Address {id: $addr})
    SET a:Sanctions
    RETURN a.id
    """
    svc.execute(query, {"addr": address.lower()})
    typer.echo(f"✅ Added {address.lower()} to sanctions list")


@app.command("add-mixer")
def add_mixer(address: str = typer.Argument(..., help="Address to tag as mixer")):
    """Tag an address as a mixer."""
    from ml_pipeline.graph.service import MemgraphService
    svc = MemgraphService()
    
    query = """
    MERGE (a:Address {id: $addr})
    SET a:Mixer
    RETURN a.id
    """
    svc.execute(query, {"addr": address.lower()})
    typer.echo(f"✅ Tagged {address.lower()} as mixer")


@app.command("address-risk")
def address_risk(address: str = typer.Argument(..., help="Address to check")):
    """Get risk assessment for an address."""
    from ml_pipeline.graph.features import GraphFeatureExtractor
    from ml_pipeline.graph.service import MemgraphService
    
    svc = MemgraphService()
    extractor = GraphFeatureExtractor(svc)
    features = extractor.extract_features(address.lower())
    
    typer.echo(f"\nRisk Assessment: {address.lower()}")
    typer.echo("-" * 50)
    typer.echo(f"  Sanctions Distance:   {features.sanctions_distance}")
    typer.echo(f"  In-Degree:            {features.in_degree}")
    typer.echo(f"  Out-Degree:           {features.out_degree}")
    typer.echo(f"  Transaction Count:    {features.transaction_count}")
    typer.echo(f"  Unique Counterparties: {features.unique_counterparties}")
    typer.echo(f"  Mixer Connected:      {features.is_mixer_connected}")
    typer.echo(f"  Loop Count:           {features.loop_count}")
    typer.echo(f"  Activity (days):      {features.activity_span_days:.1f}")


if __name__ == "__main__":
    app()
