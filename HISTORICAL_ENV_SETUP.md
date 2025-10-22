# Historical AML/Fraud Environment Setup (DuckDB + Memgraph + Redis + Python)

This guide spins up a fast, memory-efficient stack for historical modeling using Docker and gives you a minimal Python quickstart.

- OLAP: DuckDB (embedded in Python)
- Graph: Memgraph CE (Bolt 7687)
- Cache/Store: Redis (6379)
- ML: Python + scikit-learn/XGBoost (start with sklearn)

## 1) Bring up infra

Requirements: Docker Desktop, a terminal (Windows PowerShell).

Services added to `docker-compose.yml`:
- memgraph (Bolt 7687) with telemetry off, 2GB memory limit, 30s query timeout
- redis (6379) with 512MB maxmemory, allkeys-lru

Start the stack:

```powershell
# From repo root
docker compose up -d memgraph redis

# Optional: bring up everything else if you use oracle/risk too
# docker compose up -d
```

Verify health:

```powershell
# Memgraph (expects a Bolt client; we just check port here)
Test-NetConnection -ComputerName 127.0.0.1 -Port 7687

# Redis ping
docker exec -it redis redis-cli PING
```

## 2) Python environment

You can run Python either on your host or in a transient container.

- Host (if Python 3.11+ available):
  ```powershell
  python -m venv .venv; . .venv\Scripts\Activate.ps1
  pip install -r historical\requirements.txt
  ```

- Transient container (no host Python needed):
  ```powershell
  docker run --rm -it ^
    --network amttp-network ^
    -v "${PWD}\historical":/app ^
    -w /app ^
    python:3.11-slim bash -lc "pip install -r requirements.txt && python quickstart.py"
  ```

## 3) Quickstart workflow

- `historical/quickstart.py` demonstrates:
  - Creating a small synthetic dataset with pandas
  - Querying/aggregating with DuckDB (in-process)
  - Writing nodes/relationships to Memgraph over Bolt
  - Using Redis for feature cache

Run it (host):
```powershell
python historical\quickstart.py
```

Expected outputs:
- Redis PING OK and a round-trip get
- Memgraph node/edge counts (small numbers) printed
- A tiny aggregated table from DuckDB

## 4) Training from scratch (baseline)

We included a simple sklearn trainer to avoid heavy GPU requirements initially:

```powershell
# If risk-engine is running:
docker compose exec risk-engine bash -lc "python train_baseline.py"
# Or pass a CSV/Parquet with a 'label' column
# docker compose exec risk-engine bash -lc "python train_baseline.py --data /app/data/transactions.csv"

# Then reload the server model
Invoke-WebRequest -Method POST http://localhost:8001/reload-model | Select-Object -Expand Content
Invoke-WebRequest http://localhost:8001/model-info | Select-Object -Expand Content
```

## 5) Tuning cheatsheet

- Memgraph:
  - `--memory-limit=2048` (MB) – adjust to your machine; set lower on laptops
  - `--query-execution-timeout-sec=30` – keep runaway queries in check
- Redis:
  - `--maxmemory 512mb --maxmemory-policy allkeys-lru`
- DuckDB:
  - Embedded; prefers columnar sources (Parquet). Use `PRAGMA threads=<cores>;` in SQL as needed
- Python training:
  - Start with sklearn; for XGBoost, constrain `max_depth`, `n_estimators`, and add `tree_method=hist`

## 6) Next steps

- Swap sklearn with XGBoost after you’re comfortable (add to `historical/requirements.txt` and quickstart)
- Add Memgraph MAGE algorithms for community detection/flows
- Promote DuckDB extracts into Parquet partitions and reuse across experiments

That’s it — you have a fast, stable, low-memory historical environment ready for AML/fraud modeling.
