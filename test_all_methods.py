"""Quick test: all 5 scoring methods with graph signals."""
import urllib.request, json

methods = ["ensemble", "xgboost", "lightgbm", "teacher", "heuristic"]
for m in methods:
    req = urllib.request.Request(
        "http://localhost:8000/score",
        data=json.dumps({
            "from_address": "0x28c6c06298d514db089934071355e5743bf21d60",
            "to_address": "0x21a31ee1afc51d94c2efccaa2092ad1028285549",
            "value_eth": 1.5,
            "gas_price_gwei": 30,
            "method": m,
        }).encode(),
        headers={"Content-Type": "application/json"},
    )
    resp = urllib.request.urlopen(req, timeout=45)
    r = json.loads(resp.read())
    f = r["factors"]
    gs = ""
    if f.get("gat_prob"):
        gs = f"  gat={f['gat_prob']} sage={f['sage_prob']} unc={f['gat_uncertainty']}"
    print(f"{m:12s} -> score={r['risk_score']:3d}  level={r['risk_level']:10s}  conf={r['confidence']}{gs}")
