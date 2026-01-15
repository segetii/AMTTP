"""
Run the Graph-Enhanced Fraud Detection API
Usage: python run_graph_server.py
"""
import sys
import os

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Force CPU mode
os.environ["CUDA_VISIBLE_DEVICES"] = ""

if __name__ == "__main__":
    import uvicorn
    from graph.api import app
    
    print("=" * 55)
    print("AMTTP Graph-Enhanced Fraud Detection API")
    print("=" * 55)
    print()
    print("Endpoints:")
    print("  - http://127.0.0.1:8001/docs         (Swagger UI)")
    print("  - http://127.0.0.1:8001/health       (Health Check)")
    print("  - http://127.0.0.1:8001/predict/hybrid  (Hybrid Prediction)")
    print("  - http://127.0.0.1:8001/graph/stats  (Graph Statistics)")
    print()
    print("Note: Requires Memgraph running on localhost:7687")
    print("      Falls back to tabular-only mode if unavailable")
    print()
    
    uvicorn.run(app, host="127.0.0.1", port=8001)
