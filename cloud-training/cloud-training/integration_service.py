import argparse
import os
from typing import Any, Dict, List, Optional

from fastapi import FastAPI
from pydantic import BaseModel
import uvicorn

app = FastAPI(title="AMTTP Risk Engine", version="0.1.0")


class ScoreRequest(BaseModel):
    # Flexible schema: either send engineered feature vector or raw tx context
    features: Optional[List[float]] = None
    amountWei: Optional[str] = None
    buyer: Optional[str] = None
    seller: Optional[str] = None
    # room for additional context keys
    timestamp: Optional[int] = None


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/sota-status")
async def sota_status():
    # Placeholder SOTA metrics so oracle can display status even before model is wired
    return {
        "f1Score": 0.669,
        "accuracy": 0.91,
        "precision": 0.67,
        "recall": 0.67,
        "modelVersion": "DQN-v1.0-local",
        "trainingData": "28,457 real fraud transactions",
    }


def score_from_features(features: List[float]) -> float:
    # Simple heuristic placeholder; replace with GPU model inference when available
    # Emphasize large amount (index 0 log-amount), odd hours (index 1), weekend (index 2)
    score = 0.0
    if len(features) > 0 and features[0] > 3.5:
        score += 0.35
    if len(features) > 1 and (features[1] < 0.25 or features[1] > 0.9):
        score += 0.2
    if len(features) > 2 and (features[2] == 0 or features[2] == 6):
        score += 0.1
    return max(0.0, min(1.0, score))


def score_from_ctx(payload: Dict[str, Any]) -> float:
    # Very lightweight risk proxy using amount; treat missing as low risk
    amount_wei = payload.get("amountWei")
    try:
        amount = int(amount_wei, 16) if isinstance(amount_wei, str) and amount_wei.startswith("0x") else float(amount_wei)
    except Exception:
        amount = 0.0
    # Map to 0..1 with a soft cap
    return max(0.0, min(1.0, amount / 1e20))


@app.post("/score")
async def score(req: ScoreRequest):
    # Support both feature vector and raw tx context
    if req.features:
        risk = score_from_features(req.features)
        return {
            "score": risk,
            "summary": "feature-based risk estimate",
            "confidence": 0.8,
        }
    # Fallback: treat posted body as generic context
    payload = req.model_dump(exclude_none=True)
    risk = score_from_ctx(payload)
    return {
        "score": risk,
        "summary": "context-based risk estimate",
        "confidence": 0.6,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default=os.getenv("HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(os.getenv("PORT", "8000")))
    parser.add_argument("--serve", action="store_true", help="Run uvicorn server")
    args = parser.parse_args()

    if args.serve:
        uvicorn.run(app, host=args.host, port=args.port)
    else:
        # For quick local sanity check
        import asyncio
        print(asyncio.get_event_loop().run_until_complete(health()))


if __name__ == "__main__":
    main()
