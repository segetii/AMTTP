# API Integration Tests

Scripts that test the backend REST API, authentication flows, and service endpoints.

| Script | What It Tests |
|---|---|
| `test_backend_api.py` | Full API surface: health, auth, fraud scoring, address lookup |
| `test_backend_endpoints.py` | Individual endpoint response codes and schemas |
| `test_monitoring_api.py` | Prometheus metrics, health-check, and alerting endpoints |
| `test_api_comprehensive.py` | Combined end-to-end test suite across all services |
| `test_integration.sh` | Shell-based smoke test hitting all services sequentially |
| `test_api.sh` | Lightweight curl-based API test |
| `test_dao_governance.py` | DAO voting and proposal endpoints |
| `test_layerzero.py` | Cross-chain LayerZero bridge integration |
| `test_kleros.py` | Kleros dispute-resolution endpoint tests |
| `test_full_system.py` | End-to-end system test: deploy → score → verify |

## Running

```bash
# Ensure backend is running (default: http://localhost:8000)
cd backend && uvicorn app.main:app --reload

# Run a specific test
python tests/api-integration/test_backend_api.py

# Run all API tests
python -m pytest tests/api-integration/ -v
```
