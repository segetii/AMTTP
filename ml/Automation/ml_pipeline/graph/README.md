# AMTTP ML Pipeline - Memgraph Integration

Graph-based fraud detection using Memgraph to enhance ML predictions.

## Architecture

```
┌────────────────────────────────────────────────────────────────┐
│                     Hybrid Predictor                            │
│  ┌──────────────────┐    ┌────────────────────────────────┐    │
│  │  Tabular Model   │    │      Graph Features            │    │
│  │  (XGBoost)       │    │  (Memgraph)                    │    │
│  │  Weight: 70%     │    │  Weight: 30%                   │    │
│  └────────┬─────────┘    └──────────────┬─────────────────┘    │
│           │                              │                      │
│           └──────────┬───────────────────┘                      │
│                      ▼                                          │
│           ┌──────────────────┐                                  │
│           │  Combined Score  │                                  │
│           │  Action Decision │                                  │
│           └──────────────────┘                                  │
└────────────────────────────────────────────────────────────────┘
```

## Features

### Graph-Based Risk Factors

| Feature | Description | Risk Weight |
|---------|-------------|-------------|
| `sanctions_distance` | Shortest path to sanctioned address | High (≤1 = +50%) |
| `mixer_connected` | Connected to known mixer | High (+25%) |
| `loop_count` | A→B→A transaction patterns | Medium (+15%) |
| `community_risk` | Aggregate risk of cluster | Low (+10%) |

### Tabular Features (171 total)

- Transaction volumes (sent/received)
- Account activity patterns
- ERC20 token interactions
- Network metrics (degree, counterparties)
- Temporal features (activity span)

## Quick Start

### 1. Start Memgraph (Docker)

```bash
docker-compose up -d memgraph
```

Or standalone:
```bash
docker run -d -p 7687:7687 memgraph/memgraph:latest
```

### 2. Install Dependencies

```bash
pip install -r requirements_cpu.txt

# For Memgraph Bolt connection (optional but recommended)
pip install mgclient
```

### 3. Run the Graph API

```bash
cd c:\amttp\ml\Automation\ml_pipeline
python run_graph_server.py
```

Server runs at: http://127.0.0.1:8001

### 4. Test Prediction

```bash
curl -X POST http://127.0.0.1:8001/predict/hybrid \
  -H "Content-Type: application/json" \
  -d '{
    "transaction_id": "tx-001",
    "features": {"total_ether_sent": 100, "sent_tnx": 10},
    "from_address": "0x1234...",
    "to_address": "0xabcd..."
  }'
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/predict/hybrid` | POST | Hybrid ML + graph prediction |
| `/predict/batch` | POST | Batch predictions |
| `/graph/address-risk` | POST | Graph-only risk for address |
| `/graph/stats` | GET | Graph statistics |
| `/graph/add-transaction` | POST | Add transaction to graph |
| `/graph/tag-address` | POST | Tag address (sanctioned, mixer) |
| `/graph/address/{addr}` | GET | Full address details |
| `/model/info` | GET | Model configuration |
| `/health` | GET | Health check |

## Modules

### `graph/service.py` - Memgraph Connection

```python
from graph.service import MemgraphService, MemgraphConfig

# Connect via environment variables
service = MemgraphService()

# Or explicit config
config = MemgraphConfig(
    host="localhost",
    port=7687,
    user="memgraph",
    password="memgraph",
)
service = MemgraphService(config)

# Run queries
result = service.execute("MATCH (n) RETURN count(n)")
```

### `graph/features.py` - Feature Extraction

```python
from graph.features import GraphFeatureExtractor

extractor = GraphFeatureExtractor()

# Single address
features = extractor.extract_features("0x1234...")
print(f"Sanctions distance: {features.sanctions_distance}")
print(f"Is mixer connected: {features.is_mixer_connected}")

# Batch extraction
results = extractor.extract_features_batch(["0x1234...", "0xabcd..."])

# Graph-only risk score
risk = extractor.get_risk_score_from_graph("0x1234...")
```

### `graph/updater.py` - Graph Updates

```python
from graph.updater import GraphUpdater, Transaction

updater = GraphUpdater()

# Add transaction
txn = Transaction(
    hash="0xabc...",
    from_address="0x1234...",
    to_address="0xabcd...",
    value=1.5,
    timestamp=1703030400,
)
updater.add_transaction(txn)

# Tag sanctioned address
updater.tag_address("0x1234...", "sanctioned")

# Batch ingest
updater.add_transactions_batch(transactions, batch_size=1000)
```

### `graph/hybrid_predictor.py` - Combined Prediction

```python
from graph.hybrid_predictor import HybridPredictor

predictor = HybridPredictor(
    models_dir="models/trained",
    tabular_weight=0.7,
    graph_weight=0.3,
)

result = predictor.predict(
    transaction_id="tx-001",
    tabular_features={"total_ether_sent": 100},
    from_address="0x1234...",
    to_address="0xabcd...",
)

print(f"Combined risk: {result.combined_risk_score}")
print(f"Action: {result.combined_action}")
```

## Graph Schema

```cypher
// Nodes
(:Address {id: "0x..."})
(:Tag {name: "sanctioned" | "mixer" | "exchange"})
(:Cluster {id: 1, score: 0.5})

// Edges
(:Address)-[:TRANSFER {hash, value, ts, block}]->(:Address)
(:Address)-[:TAGGED_AS]->(:Tag)
(:Address)-[:IN_CLUSTER]->(:Cluster)
```

## Fallback Mode

If Memgraph is unavailable, the system automatically runs in **tabular-only mode**:

- Tabular weight becomes 100%
- Graph features return defaults (distance=999, etc.)
- API continues to function normally

Check mode via:
```bash
curl http://127.0.0.1:8001/health
# {"graph_available": true/false, "mode": "hybrid"/"tabular-only"}
```

## Performance

| Operation | Time (typical) |
|-----------|----------------|
| Single prediction (tabular) | ~10-30ms |
| Single prediction (hybrid) | ~30-100ms |
| Batch prediction (100 txns) | ~200-500ms |
| Graph feature extraction | ~20-50ms |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MEMGRAPH_HOST` | localhost | Memgraph host |
| `MEMGRAPH_PORT` | 7687 | Memgraph Bolt port |
| `MEMGRAPH_USER` | - | Username (if auth enabled) |
| `MEMGRAPH_PASSWORD` | - | Password (if auth enabled) |
| `MEMGRAPH_PROXY_URL` | - | HTTP proxy URL (alternative to Bolt) |
