# 🗺️ AMTTP UI Architecture - Complete System Map

**Last Updated:** January 8, 2026  
**Status:** Production System with Dual Frontend Architecture

---

## 🎯 System Overview

AMTTP uses a **dual frontend architecture** with distinct purposes:

1. **Next.js Dashboard** (Production/Admin) - Port 3004
2. **Flutter App** (Mobile/Cross-Platform) - Port 3003

Both connect to a **unified backend microservices architecture** across ports 8000-8007.

---

## 🌐 Frontend Applications

### **1️⃣ Next.js Dashboard** (Production SIEM & Compliance)

**Location:** `c:\amttp\frontend\frontend\`  
**Port:** 3004 (configured to avoid Memgraph conflict on 3000)  
**Access:** http://localhost:3004

#### **Pages & Routes:**

| Route | Component | Purpose | Backend Dependencies |
|-------|-----------|---------|---------------------|
| `/` | `src/app/page.tsx` | SIEM Dashboard - Real-time monitoring | Monitoring (8005) |
| `/dashboard` | `src/app/dashboard/page.tsx` | Admin service health & stats | All services (8002-8007) |
| `/compliance` | `src/app/compliance/page.tsx` | **FATF Rules & Sanctions** | Sanctions (8004), Geo-Risk (8006), Orchestrator (8007) |
| `/transfer` | `src/app/transfer/page.tsx` | Secure payment with UI integrity | Risk Engine (8002) |
| `/history` | `src/app/history/page.tsx` | Transaction history with travel rule | Risk Engine (8002) |
| `/policies` | `src/app/policies/page.tsx` | Policy management interface | Policy Service (8003) |
| `/investigate/[address]` | `src/app/investigate/[address]/page.tsx` | Deep address investigation | Multiple services |
| `/settings` | `src/app/settings/page.tsx` | User preferences & KYC | Risk Engine (8002) |

#### **Key Components:**

```
src/components/
├── SIEMDashboard.tsx           # Real-time monitoring (30s auto-refresh)
├── PolicyCard.tsx              # Policy display cards
├── PolicyForm.tsx              # Policy creation/editing
├── AlertsTable.tsx             # Live AML alerts
├── TimelineChart.tsx           # Transaction timeline visualization
├── RiskDistributionChart.tsx   # Risk analytics
├── SecurePayment.tsx           # UI integrity protected payment
└── AppLayout.tsx               # Main navigation layout
```

#### **Environment Variables:**

```bash
# .env.local
NEXT_PUBLIC_RISK_ENGINE_URL=http://localhost:8002
NEXT_PUBLIC_API_URL=http://localhost:8002
NEXT_PUBLIC_ORACLE_URL=http://localhost:3001
```

#### **Launch:**

```powershell
cd c:\amttp\frontend\frontend
$env:PORT=3004  # Override default port 3000
npm run dev
```

---

### **2️⃣ Flutter App** (Mobile/Cross-Platform)

**Location:** `c:\amttp\frontend\amttp_app\`  
**Port:** 3003  
**Access:** http://localhost:3003  
**Platforms:** Web, iOS, Android

#### **App Routes (GoRouter):**

| Route | Screen | Features |
|-------|--------|----------|
| `/` | SignInPage | Demo login, MetaMask, WalletConnect |
| `/home` | HomePage | Dashboard with quick actions |
| `/admin` | AdminPage | **DQN ML Analytics** (F1: 66.9%) |
| `/transfer` | TransferPage | UI Integrity Protected Transfers |
| `/history` | HistoryPage | Transaction history |
| `/disputes` | DisputeCenterPage | Kleros integration |
| `/settings` | SettingsPage | User preferences |

#### **Key Flutter Files:**

```
lib/
├── main.dart                                    # App entry point
├── core/
│   ├── security/ui_integrity_service.dart      # UI protection (450 lines)
│   ├── theme/app_theme.dart                    # Dark theme with neon accents
│   ├── providers/api_providers.dart            # Riverpod state management
│   └── services/api_service.dart               # Backend API integration
├── features/
│   ├── auth/presentation/pages/sign_in_page.dart
│   ├── admin/presentation/pages/admin_page.dart  # DQN Analytics Tab
│   ├── home/presentation/pages/home_page.dart
│   └── disputes/presentation/pages/dispute_center_page.dart
└── shared/
    └── widgets/
        ├── secure_transfer_protected_widget.dart  # 5-stage integrity flow (950 lines)
        └── secure_transfer_widget.dart            # Legacy transfer widget
```

#### **Environment Variables:**

```bash
# .env.local
NEXT_PUBLIC_ORACLE_API_URL=http://localhost:8000
NEXT_PUBLIC_FCA_API_URL=http://localhost:8002
NEXT_PUBLIC_WALLET_CONNECT_PROJECT_ID=your_project_id
```

#### **Launch:**

```powershell
cd c:\amttp\frontend\amttp_app
flutter run -d chrome --web-port=3003
```

---

## 🔧 Backend Microservices Architecture

### **Port Allocation Map:**

| Port | Service | Status | Description |
|------|---------|--------|-------------|
| **3000** | ⚠️ Memgraph | ✅ Running | Graph database (conflicts with Next.js default) |
| **3001** | Oracle Service | ❌ Not Running | Blockchain oracle (alternative port) |
| **3002** | Compliance Service | ✅ Running | Risk engine, KYC, compliance |
| **3003** | Flutter App | ✅ Running | Mobile/web frontend |
| **3004** | Next.js Dashboard | ✅ Running | Admin SIEM dashboard |
| **8000** | Oracle API | ❓ Unknown | Blockchain oracle service |
| **8002** | Risk Engine | ✅ Running | Main compliance API |
| **8003** | Policy Service | ❌ Not Running | Policy management |
| **8004** | Sanctions Service | ❓ Expected | OFAC/HMT/EU/UN sanctions |
| **8005** | Monitoring Service | ❓ Expected | AML monitoring & alerts |
| **8006** | Geo-Risk Service | ❓ Expected | FATF lists, country risk |
| **8007** | Orchestrator | ❓ Expected | Unified compliance API |
| **8008** | UI Integrity Service | ❓ Expected | UI protection backend |

### **Service Dependency Graph:**

```
┌─────────────────────────────────────────────────┐
│         Frontend Applications                    │
├─────────────────┬───────────────────────────────┤
│  Next.js (3004) │  Flutter (3003)               │
└────────┬────────┴──────────┬────────────────────┘
         │                   │
         ▼                   ▼
┌────────────────────────────────────────────────┐
│         API Gateway Layer                       │
├────────────────────────────────────────────────┤
│  Orchestrator (8007) - Unified Compliance API  │
└────┬───────┬────────┬────────┬─────────────────┘
     │       │        │        │
     ▼       ▼        ▼        ▼
┌────────┬─────────┬──────┬──────────┐
│Sanctions│Monitoring│ Geo  │UI Integrity│
│  8004   │   8005   │ 8006 │   8008   │
└────────┴─────────┴──────┴──────────┘
     │       │        │        │
     └───────┴────────┴────────┘
                 │
                 ▼
    ┌────────────────────────┐
    │  Risk Engine (8002)     │
    │  Policy Service (8003)  │
    └────────────────────────┘
                 │
                 ▼
    ┌────────────────────────┐
    │  Data Layer            │
    ├────────────────────────┤
    │  MongoDB (27017)       │
    │  Redis (6379)          │
    │  Memgraph (3000)       │
    └────────────────────────┘
```

---

## 📊 Feature Mapping: Where to Find What

### **FATF Compliance & Sanctions**

| Feature | Next.js | Flutter | Backend |
|---------|---------|---------|---------|
| **FATF Black List** | ✅ `/compliance` | ❌ N/A | Geo-Risk (8006) |
| **FATF Grey List** | ✅ `/compliance` | ❌ N/A | Geo-Risk (8006) |
| **Sanctions Screening** | ✅ `/compliance` | ✅ Embedded in transfer | Sanctions (8004) |
| **Country Risk Check** | ✅ `/compliance` | ❌ N/A | Geo-Risk (8006) |

### **Machine Learning & Analytics**

| Feature | Next.js | Flutter | Backend |
|---------|---------|---------|---------|
| **DQN Analytics Dashboard** | ❌ N/A | ✅ Admin page → DQN Analytics tab | ML Pipeline |
| **Real-time Risk Scoring** | ✅ SIEM Dashboard | ✅ Transfer widget | Risk Engine (8002) |
| **Transaction Predictions** | ✅ History page | ✅ Transfer widget | ML Model (F1: 66.9%) |

### **UI Integrity Protection**

| Feature | Next.js | Flutter | Backend |
|---------|---------|---------|---------|
| **Protected Transfers** | ✅ `/transfer` | ✅ `SecureTransferProtectedWidget` | UI Integrity (8008) |
| **DOM Verification** | ✅ SecurePayment component | ✅ UIIntegrityService | UI Integrity (8008) |
| **5-Stage Flow** | ✅ Implemented | ✅ Implemented (950 lines) | UI Integrity (8008) |

### **AML Monitoring**

| Feature | Next.js | Flutter | Backend |
|---------|---------|---------|---------|
| **Live Alerts** | ✅ SIEM Dashboard | ❌ N/A | Monitoring (8005) |
| **Alert History** | ✅ `/compliance` | ❌ N/A | Monitoring (8005) |
| **6 AML Rules** | ✅ Displayed | ❌ N/A | Monitoring (8005) |

### **KYC & Identity**

| Feature | Next.js | Flutter | Backend |
|---------|---------|---------|---------|
| **KYC Status** | ✅ Dashboard, Settings | ✅ Home page | Risk Engine (8002) |
| **Profile Management** | ✅ `/compliance` | ✅ Settings | Orchestrator (8007) |
| **Travel Rule** | ✅ History page | ✅ Transfer widget | Risk Engine (8002) |

### **Policy Management**

| Feature | Next.js | Flutter | Backend |
|---------|---------|---------|---------|
| **Create Policies** | ✅ `/policies` | ❌ N/A | Policy Service (8003) |
| **Edit Policies** | ✅ `/policies` | ❌ N/A | Policy Service (8003) |
| **Policy Evaluation** | ✅ Transfer page | ✅ Transfer widget | Orchestrator (8007) |

---

## 🔐 Authentication Flow

### **Next.js Authentication:**

```typescript
// Demo Accounts (for testing)
const DEMO_ACCOUNTS = {
  'admin@amttp.com': { role: 'INSTITUTIONAL', kyc: 'ENHANCED' },
  'user@amttp.com': { role: 'INDIVIDUAL', kyc: 'STANDARD' },
  'vasp@amttp.com': { role: 'VASP', kyc: 'INSTITUTIONAL' }
};

// Web3 Authentication
- MetaMask (via wagmi/ethers)
- WalletConnect
- Coinbase Wallet
```

### **Flutter Authentication:**

```dart
// Demo Login
- admin / admin123  (Admin access to DQN Analytics)
- user / user123    (Standard user)

// Web3 Login
- MetaMask Mobile
- WalletConnect
- Trust Wallet
```

---

## 🚀 Startup Sequence (Correct Order)

### **1. Data Layer (Optional - if using databases):**

```powershell
# Start Memgraph (if needed for graph queries)
# Already running on port 3000

# Start MongoDB (if compliance service needs it)
docker-compose up -d mongodb

# Start Redis (for caching)
docker-compose up -d redis
```

### **2. Backend Services (Start in this order):**

```powershell
# A. Core Compliance Service (Port 8002)
cd c:\amttp\backend\compliance-service
python orchestrator.py

# B. Policy Service (Port 8003)
cd c:\amttp\backend\policy-service
python policy_api.py

# C. Sanctions Service (Port 8004)
# TODO: Check if separate service or part of orchestrator

# D. Monitoring Service (Port 8005)
# TODO: Check if separate service or part of orchestrator

# E. Geo-Risk Service (Port 8006)
# TODO: Check if separate service or part of orchestrator

# F. Orchestrator Service (Port 8007)
# TODO: Check if separate service or part of orchestrator

# G. UI Integrity Service (Port 8008)
# TODO: Implement standalone service
```

### **3. Frontend Applications:**

```powershell
# A. Flutter App (Port 3003)
cd c:\amttp\frontend\amttp_app
flutter run -d chrome --web-port=3003

# B. Next.js Dashboard (Port 3004)
cd c:\amttp\frontend\frontend
$env:PORT=3004
npm run dev
```

---

## 🐛 Known Issues & Resolutions

### **Issue 1: Port 3000 Conflict**

**Problem:** Memgraph occupies port 3000, preventing Next.js from starting  
**Solution:** Launch Next.js on port 3004  
**Command:** `$env:PORT=3004; npm run dev`

### **Issue 2: Backend Services Not Running**

**Problem:** FATF lists, sanctions, monitoring show "Service Unavailable"  
**Impact:** Compliance page displays no data  
**Solution:** Start backend services in correct order (see Startup Sequence)

**Current Status:**
- ✅ Compliance Service (8002) - Running
- ❌ Policy Service (8003) - Needs debugging
- ❓ Sanctions/Monitoring/Geo-Risk/Orchestrator - Status unknown

### **Issue 3: Flutter Compilation Errors**

**Problem:** 20+ errors on initial launch (theme colors, API models, imports)  
**Status:** ✅ RESOLVED (all errors fixed)  
**Details:** Fixed theme colors, API model constructors, removed duplicates

---

## 📁 File Locations Quick Reference

### **Frontend:**

```
Next.js Dashboard:
  Main: c:\amttp\frontend\frontend\
  Pages: c:\amttp\frontend\frontend\src\app\
  Components: c:\amttp\frontend\frontend\src\components\
  Env: c:\amttp\frontend\frontend\.env.local

Flutter App:
  Main: c:\amttp\frontend\amttp_app\
  Core: c:\amttp\frontend\amttp_app\lib\core\
  Features: c:\amttp\frontend\amttp_app\lib\features\
  Widgets: c:\amttp\frontend\amttp_app\lib\shared\widgets\
  Env: c:\amttp\frontend\amttp_app\.env.local
```

### **Backend:**

```
Services:
  Compliance: c:\amttp\backend\compliance-service\
  Policy: c:\amttp\backend\policy-service\
  Oracle: c:\amttp\backend\oracle-service\

Configuration:
  Compliance env: c:\amttp\backend\compliance-service\.env.example
```

### **Documentation:**

```
Guides:
  Flutter Integrity: c:\amttp\FLUTTER_INTEGRITY_GUIDE.md
  Flutter ML Dashboard: c:\amttp\FLUTTER_ML_DASHBOARD_GUIDE.md
  Flutter Implementation: c:\amttp\FLUTTER_IMPLEMENTATION_SUMMARY.md
  Project Docs: c:\amttp\PROJECT_DOCUMENTATION.md
  Architecture: c:\amttp\AMTTP_PRODUCT_ARCHITECTURE.md
  Roadmap: c:\amttp\AMTTP_ROADMAP.md
```

---

## 🎯 Next Steps: Making Everything Work Together

### **Immediate Actions Required:**

1. **Map Backend Services:**
   - [ ] Identify which backend services are actually implemented
   - [ ] Check if services 8004-8007 are part of orchestrator or separate
   - [ ] Document actual service endpoints

2. **Fix Backend Connectivity:**
   - [ ] Debug Policy Service (8003) startup errors
   - [ ] Verify Orchestrator (8007) configuration
   - [ ] Test all API endpoints from frontend

3. **Update Frontend Configuration:**
   - [ ] Correct API URLs in `.env.local` files
   - [ ] Update service health checks
   - [ ] Add fallback for unavailable services

4. **Create Unified Launch Script:**
   - [ ] PowerShell script to start all services
   - [ ] Health checks after each service
   - [ ] Auto-open browsers with correct ports

---

## 📞 Support & Resources

**Documentation:**
- Complete architecture: `AMTTP_PRODUCT_ARCHITECTURE.md`
- Project overview: `PROJECT_DOCUMENTATION.md`
- Start guide: `START_HERE.md`

**Quick Access:**
- Next.js: http://localhost:3004
- Flutter: http://localhost:3003
- FATF Compliance: http://localhost:3004/compliance
- ML Dashboard: http://localhost:3003 (sign in as admin)

**Port Reference:**
- Memgraph: 3000
- Flutter: 3003
- Next.js: 3004
- Compliance: 8002
- Policy: 8003
- Orchestrator: 8007

---

**Generated:** January 8, 2026  
**System Status:** Dual frontends operational, backend services partially running  
**Next Update:** After backend service mapping complete
