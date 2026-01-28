# AMTTP Quick Start Guide

## Last Updated: January 22, 2026

This guide covers how to start all AMTTP services for development.

---

## 🚀 Quick Start (All Services)

### Option 1: Manual Start (Recommended for Development)

Open PowerShell terminals and run each service:

```powershell
# 1. Start Infrastructure (Docker)
cd c:\amttp
docker-compose up -d

# 2. Start ML Risk API (Port 8000)
py -3 c:\amttp\ml\Automation\ml_pipeline\inference\hybrid_api.py

# 3. Start Graph Service (Port 8001)
py -3 c:\amttp\ml\Automation\ml_pipeline\inference\run_graph_server.py

# 4. Start Compliance Orchestrator (Port 8007)
Start-Process -FilePath "py" -ArgumentList "-3", "c:\amttp\backend\compliance-service\orchestrator.py" -NoNewWindow -PassThru

# 5. Start Policy Service (Port 8003)
py -3 c:\amttp\backend\policy-service\policy_api.py

# 6. Start Sanctions Service (Port 8004)
py -3 c:\amttp\backend\compliance-service\sanctions_service.py

# 7. Start Monitoring Engine (Port 8005)
py -3 c:\amttp\backend\compliance-service\monitoring_rules.py

# 8. Start Geographic Risk (Port 8006)
py -3 c:\amttp\backend\compliance-service\geographic_risk.py

# 9. Start Integrity Service (Port 8008)
Start-Process -FilePath "py" -ArgumentList "-3", "c:\amttp\backend\compliance-service\integrity_service.py" -NoNewWindow -PassThru

# 10. Start Flutter Web (Port 3010)
Start-Process -FilePath "powershell" -ArgumentList "-NoExit", "-Command", "py -3 c:\amttp\frontend\amttp_app\flutter_server.py"

# 11. Start Next.js SIEM Dashboard (Port 3006)
Start-Process -FilePath "powershell" -ArgumentList "-NoExit", "-Command", "cd c:\amttp\frontend\frontend; npm run dev -- -p 3006"
```

---

## 🔐 Authentication & Login

### Login Options

The platform supports three authentication methods:

| Method | Description | Best For |
|--------|-------------|----------|
| **Wallet** | Connect MetaMask or Web3 wallet | Production users with crypto wallets |
| **Email** | Traditional email/password | Users without wallets |
| **Demo** | Select role without authentication | Testing & development |

### Demo Mode Login

1. Navigate to http://localhost:3006/login
2. Click the **"Demo"** tab
3. Select a role:
   - **End User** - Focus Mode (personal wallet)
   - **Enhanced End User** - Focus Mode (PEP-flagged)
   - **Institution Ops** - War Room (view only)
   - **Compliance Officer** - War Room (full access)
   - **Platform Admin** - Administration access
   - **Super Admin** - Full system access
4. Click **"Enter Demo Mode"**

### Test Credentials (Email Login)

```
Email: demo@amttp.io
Password: Demo123!
```

### Creating New Accounts

1. Go to http://localhost:3006/register
2. Choose registration method:
   - **Wallet**: Click "Connect Wallet" (requires MetaMask)
   - **Email**: Fill in the form with password requirements:
     - Minimum 8 characters
     - At least one uppercase letter
     - At least one lowercase letter
     - At least one number
     - At least one special character

---

## 👥 Role Management (Admin)

Super Admins and Platform Admins can manage user roles:

1. Login as **Super Admin** or **Platform Admin**
2. Navigate to **War Room** → **System** → **Role Management**
3. Available actions:
   - View all users across institutions
   - Create new users with assigned roles
   - Edit user roles
   - Suspend/Reactivate users
   - View audit logs

### Role Assignment Permissions

| Your Role | Can Assign |
|-----------|------------|
| Super Admin (R6) | All roles (R1-R6) |
| Platform Admin (R5) | R1, R2, R3, R4 |
| Compliance (R4) | R1, R2, R3 |

---

## 📊 Service Architecture

### Frontend Applications

| Service | Port | URL | Description |
|---------|------|-----|-------------|
| **Flutter Web App** | 3010 | http://localhost:3010 | Main DeFi transfer interface with risk analysis |
| **Next.js SIEM Dashboard** | 3006 | http://localhost:3006 | Compliance dashboard, FATF rules, monitoring |

### Backend Microservices

| Service | Port | Health Check | Description |
|---------|------|--------------|-------------|
| **ML Risk API** | 8000 | /health | Hybrid fraud detection (XGBoost + Graph + Heuristics) |
| **Graph Service** | 8001 | /health | Memgraph integration for network analysis |
| **FCA Compliance** | 8002 | /health | UK FCA regulatory compliance |
| **Policy Service** | 8003 | /health | Policy CRUD, whitelist/blacklist management |
| **Sanctions Service** | 8004 | /health | OFAC/EU/UN sanctions screening |
| **Monitoring Engine** | 8005 | /health | Real-time transaction monitoring, AML alerts |
| **Geographic Risk** | 8006 | /health | FATF country risk scoring |
| **Orchestrator** | 8007 | /health | Central API gateway, coordinates all services |
| **Integrity Service** | 8008 | /health | UI integrity verification (anti-Bybit attack) |

### Infrastructure (Docker)

| Service | Port | Description |
|---------|------|-------------|
| **MongoDB** | 27017 | Primary database |
| **Redis** | 6379 | Caching layer |
| **MinIO** | 9000 | Object storage (S3-compatible) |
| **Memgraph** | 7687 | Graph database (27,672 nodes, 10,000 edges) |

---

## 🔍 Key Features

### Flutter App (Port 3010)

1. **Secure Transfer Widget**
   - Connect wallet (MetaMask)
   - Enter recipient address
   - Click "Analyze Risk" for ML-powered fraud detection
   - View risk score, policy evaluation, sanctions check

2. **Risk Analysis Pipeline**
   - Calls orchestrator `/risk/score` endpoint
   - Scores both sender and receiver addresses in parallel
   - Returns combined risk score with explanation

### Next.js Dashboard (Port 3006)

1. **FATF Compliance** - Travel rule compliance
2. **Transaction Monitoring** - Real-time AML monitoring
3. **Sanctions Screening** - OFAC/EU/UN checks
4. **Geographic Risk** - Country risk visualization
5. **SIEM Dashboard** - Security event monitoring

---

## 🛠️ API Endpoints

### Orchestrator (Port 8007)

```bash
# Health check
curl http://localhost:8007/health

# Risk score analysis
curl -X POST http://localhost:8007/risk/score \
  -H "Content-Type: application/json" \
  -d '{"from_address":"0x123...","to_address":"0xabc...","value_eth":1.5}'

# Full compliance evaluation
curl -X POST http://localhost:8007/evaluate \
  -H "Content-Type: application/json" \
  -d '{"from_address":"0x123...","to_address":"0xabc...","value_eth":1.5}'
```

### ML Risk API (Port 8000)

```bash
# Score an address
curl -X POST http://localhost:8000/score/address \
  -H "Content-Type: application/json" \
  -d '{"address":"0x1234567890123456789012345678901234567890"}'
```

---

## ⚙️ Configuration

### Flutter App Configuration

The Flutter app automatically detects the environment:
- When running on port 3010, it uses `http://localhost:8007` as the API base
- Timeouts: 30 seconds for API calls
- CORS and CSP headers are configured in `flutter_server.py`

### Next.js Proxy Configuration

Next.js proxies API calls to backend services (see `next.config.js`):

| Frontend Path | Backend Target |
|---------------|----------------|
| `/api/*` | http://localhost:8007 |
| `/sanctions/*` | http://localhost:8004 |
| `/monitoring/*` | http://localhost:8005 |
| `/geo/*` | http://localhost:8006 |

---

## 🔧 Troubleshooting

### "Analyze Risk" spinning forever

1. Check orchestrator is running: `netstat -ano | findstr ":8007"`
2. Check ML API is running: `netstat -ano | findstr ":8000"`
3. Test directly: `curl http://localhost:8007/health`

### CSP/Content blocked errors

The Flutter web server (`flutter_server.py`) includes proper CSP headers. Restart it:
```powershell
# Find and kill existing server
netstat -ano | findstr ":3010"
Stop-Process -Id <PID> -Force

# Restart
py -3 c:\amttp\frontend\amttp_app\flutter_server.py
```

### Port already in use

```powershell
# Find process using port
netstat -ano | findstr ":<PORT>"

# Kill process
Stop-Process -Id <PID> -Force
```

### Service not responding

Check if the service is actually running:
```powershell
# Check all backend ports
netstat -ano | findstr "LISTENING" | findstr ":800"
```

---

## 📁 Key Files

| File | Purpose |
|------|---------|
| `backend/compliance-service/orchestrator.py` | Main API gateway |
| `ml/Automation/ml_pipeline/inference/hybrid_api.py` | ML risk scoring |
| `frontend/amttp_app/flutter_server.py` | Flutter web server with CSP |
| `frontend/amttp_app/lib/core/services/api_service.dart` | Flutter API client |
| `frontend/frontend/next.config.js` | Next.js configuration |

---

## ✅ Verification Checklist

Run these commands to verify all services are up:

```powershell
# Check all ports
netstat -ano | findstr "LISTENING" | findstr ":800"
netstat -ano | findstr ":3006 :3010"

# Test health endpoints
curl http://localhost:8000/health  # ML API
curl http://localhost:8007/health  # Orchestrator
curl http://localhost:3006         # Next.js
curl http://localhost:3010         # Flutter
```

Expected output: All services return HTTP 200 with health status.
