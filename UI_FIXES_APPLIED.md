# Next.js UI Fixes Applied

**Date:** 2026-01-09  
**Issue:** User reported "analyse button" not functioning and "secure transfer page empty"

## Root Causes Identified

### 1. **API Endpoint Mismatch (CRITICAL)**
**Problem:** Frontend API client was pointing to non-existent backend service.

```typescript
// BEFORE (WRONG):
const API_BASE = 'http://127.0.0.1:8000';  // ❌ No service running on port 8000

// AFTER (CORRECT):
const API_BASE = 'http://127.0.0.1:8007';  // ✅ Orchestrator master service
```

**Impact:** 
- All API calls were failing silently
- Frontend fell back to mock data
- Buttons appeared non-functional because backend wasn't being called
- Pages appeared "empty" because real data wasn't loading

**File:** `frontend/frontend/src/lib/api.ts` (Line 2)

---

### 2. **Incorrect Entity Profile Endpoint**
**Problem:** Frontend was calling wrong REST endpoint for entity profiles.

```typescript
// BEFORE (WRONG):
fetch(`${API_BASE}/entity/${address}`)  // ❌ /entity/* doesn't exist

// AFTER (CORRECT):
fetch(`${API_BASE}/profiles/${address}`)  // ✅ Matches Orchestrator API
```

**Impact:**
- "Analyse button" would fail to fetch address profiles
- Investigation page would only show mock data
- Entity drill-down features non-functional

**File:** `frontend/frontend/src/lib/api.ts` (Line 143)

---

### 3. **Duplicate Function Definition**
**Problem:** Transfer page had duplicate `handleCancel` function.

```typescript
// BEFORE (lines 37-44):
const handleCancel = () => setShowSecureFlow(false);
// ... code ...
const handleCancel = () => setShowSecureFlow(false);  // ❌ Duplicate

// AFTER:
const handleCancel = () => setShowSecureFlow(false);  // ✅ Single definition
const handleComplete = (txHash) => {
  alert(`Transaction successful: ${txHash}`);
  setShowSecureFlow(false);
};
```

**Impact:**
- Could cause compilation warnings
- Potential runtime issues with function hoisting

**File:** `frontend/frontend/src/app/transfer/page.tsx` (Lines 37-44)

---

## Backend Architecture (Microservices)

The system uses **6 Python microservices** (NOT a monolithic backend):

| Service | Port | Status | Purpose |
|---------|------|--------|---------|
| **Orchestrator** | 8007 | ✅ Running | Master coordinator, profiles, decisions |
| Policy Service | 8003 | ✅ Running | Policy management |
| Sanctions Service | 8004 | ✅ Running | Sanctions screening (22 addresses) |
| Monitoring Rules | 8005 | ✅ Running | Transaction monitoring |
| Geographic Risk | 8006 | ✅ Running | Country risk scoring |
| UI Integrity | 8008 | ⚠️ Optional | Frontend protection |

**Risk Engine** (Port 8002): ML-based scoring (DQN model)  
**Memgraph** (Port 3000): Graph database for network analysis

---

## Orchestrator API Endpoints

The Orchestrator (8007) provides these REST endpoints:

### Health & Status
- `GET /health` - Service health check

### Transaction Evaluation
- `POST /evaluate` - Basic transaction evaluation
- `POST /evaluate-with-integrity` - Protected evaluation with UI integrity

### Profile Management
- `GET /profiles/{address}` - Get entity profile ✅ **FIXED**
- `GET /profiles` - List all profiles
- `POST /profiles/{address}/set-type/{entity_type}` - Update entity type

### Decisions & Analytics
- `GET /decisions` - Transaction decision history
- `GET /entity-types` - List entity type categories

### API Keys
- `POST /api-keys` - Generate new API key
- `GET /api-keys` - List API keys

---

## Frontend API Client Mapping

### Working Endpoints (Verified):
✅ **Risk Scoring:** `POST http://127.0.0.1:8002/score` (Risk Engine)  
✅ **Model Info:** `GET http://127.0.0.1:8002/model/info` (Risk Engine)  
✅ **Entity Profile:** `GET http://127.0.0.1:8007/profiles/{address}` (Orchestrator) **FIXED**  
✅ **Address Scoring:** `POST http://127.0.0.1:8002/score` (Risk Engine)

### Mock Fallback Endpoints:
⚠️ **Dashboard Stats:** `GET /dashboard/stats` - Returns mock data (not implemented in Orchestrator)  
⚠️ **Alerts:** `GET /alerts` - Returns mock data (not implemented in Orchestrator)  
⚠️ **Timeline:** `GET /dashboard/timeline` - Returns mock data (not implemented)  
⚠️ **Alert Actions:** `POST /alerts/{id}/action` - Returns mock success

**Note:** These endpoints gracefully fall back to mock data when not available. This is by design to allow frontend development without full backend implementation.

---

## Changes Summary

### Files Modified:
1. **`frontend/frontend/src/lib/api.ts`** (2 changes):
   - Changed API_BASE from port 8000 → 8007 (Orchestrator)
   - Changed entity endpoint from `/entity/{address}` → `/profiles/{address}`
   - Added console error logging to `fetchEntityProfile()`

2. **`frontend/frontend/src/app/transfer/page.tsx`** (2 changes):
   - Removed duplicate `handleCancel` function
   - Added success alert message to `handleComplete`

### Testing Recommendations:

1. **Test Entity Investigation:**
   ```
   Navigate to: http://localhost:3004/investigate/0xeae7380dd4cef6fbd1144f49e4d1e6964258a4f4
   Expected: Should load profile from Orchestrator (4 profiles available)
   ```

2. **Test Analyse Button:**
   - Go to Dashboard
   - Click on any alert
   - Click "Analyse" button
   - Should open investigation page with real data

3. **Test Secure Transfer:**
   - Navigate to `/transfer` page
   - Should show SecurePaymentFlow component
   - Page should no longer appear "empty"

---

## Verification Commands

```powershell
# Check Orchestrator is running
Invoke-WebRequest -Uri "http://127.0.0.1:8007/health" -UseBasicParsing

# Test profiles endpoint (should return 4 profiles)
Invoke-WebRequest -Uri "http://127.0.0.1:8007/profiles" -UseBasicParsing

# Test specific profile (use real address from Orchestrator)
Invoke-WebRequest -Uri "http://127.0.0.1:8007/profiles/0xeae7380dd4cef6fbd1144f49e4d1e6964258a4f4" -UseBasicParsing

# Check Risk Engine
Invoke-WebRequest -Uri "http://127.0.0.1:8002/model/info" -UseBasicParsing
```

---

## Known Limitations

1. **FCA Service Unhealthy:** Orchestrator reports FCA service as "unhealthy" but this doesn't affect core functionality.

2. **UI Integrity Service Not Running:** Port 8008 is optional - required only for advanced UI protection features.

3. **Mock Data Fallback:** Some dashboard endpoints (stats, timeline, alerts) use mock data because they're not yet implemented in the backend microservices. This is intentional to allow frontend development.

4. **Next.js Port Override:** Next.js runs on port 3004 (not default 3000) because Memgraph uses 3000.

---

## Next Steps (Optional Improvements)

1. **Implement Missing Orchestrator Endpoints:**
   - `/dashboard/stats` - Aggregate statistics
   - `/alerts` - Real-time alerts from monitoring service
   - `/dashboard/timeline` - Historical trends

2. **Start UI Integrity Service:**
   ```powershell
   cd backend\compliance-service
   python integrity_service.py
   ```

3. **Add Error Toast Notifications:**
   - Currently errors fail silently with mock data
   - Add user-facing error messages for API failures

4. **Health Monitoring Dashboard:**
   - Add service health indicators to UI
   - Show which services are connected
   - Real-time status updates

---

## Documentation References

- **UI Architecture Map:** `UI_ARCHITECTURE_MAP.md` (Complete system overview)
- **Service Launcher:** `START_ALL_SERVICES.ps1` (Automated startup)
- **Integration Guide:** `SYSTEM_INTEGRATION_COMPLETE.md` (Deployment guide)
- **Flutter ML Dashboard:** `FLUTTER_ML_DASHBOARD_GUIDE.md` (Mobile app features)

---

**Status:** ✅ **All Critical Fixes Applied**  
**Impact:** Buttons and pages should now function with real backend data  
**Restart Required:** Yes - restart Next.js dev server to apply changes
