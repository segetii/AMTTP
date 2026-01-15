"""
Run the CPU-only FastAPI server
Usage: python run_server.py
"""
import sys
import os

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Force CPU mode
os.environ["CUDA_VISIBLE_DEVICES"] = ""

if __name__ == "__main__":
    import uvicorn
    from inference.cpu_api import app
    
    print("=" * 50)
    print("AMTTP Fraud Detection API - CPU Mode")
    print("=" * 50)
    print()
    print("Endpoints:")
    print("  - http://127.0.0.1:8000/docs    (Swagger UI)")
    print("  - http://127.0.0.1:8000/health  (Health Check)")
    print("  - http://127.0.0.1:8000/predict (Single Prediction)")
    print()
    
    uvicorn.run(app, host="127.0.0.1", port=8000)
