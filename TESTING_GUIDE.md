# AMTTP Testing Guide
## Version 2.3 - January 22, 2026

---

## 📋 Application URLs

| Application | URL | Description |
|-------------|-----|-------------|
| **Flutter App** | http://localhost:3010 | Main mobile/web app |
| **Next.js App** | http://localhost:3006 | Web dashboard |
| **Risk Engine API** | http://localhost:8002 | ML scoring service |
| **Memgraph Lab** | http://localhost:3000 | Graph database UI |
| **Memgraph Bolt** | bolt://localhost:7687 | Graph database connection |

---

## 🔐 Demo Login Credentials

### Focus Mode Users (R1-R2) - Simplified Interface

| Role | Email | Password | Mode | Capabilities |
|------|-------|----------|------|--------------|
| **R1 - End User** | user@amttp.io | user123 | Focus Mode | Personal wallet, send/receive, view history |
| **R2 - End User (PEP)** | pep@amttp.io | pep123 | Focus Mode | Same as R1 + enhanced monitoring |

### War Room Users (R3-R6) - Full Analytics Dashboard

| Role | Email | Password | Mode | Capabilities |
|------|-------|----------|------|--------------|
| **R3 - Institution Ops** | ops@amttp.io | ops123 | War Room (View) | Read-only analytics, view flagged queue |
| **R4 - Compliance Officer** | compliance@amttp.io | comply123 | War Room (Full) | Policy management, approve/reject, multisig |
| **R5 - Platform Admin** | admin@amttp.io | admin123 | War Room (Admin) | User management, system config, audit logs |
| **R6 - Super Admin** | super@amttp.io | super123 | War Room (Super) | Emergency override ONLY |

---

## 🧪 Test Cases by Role

### R1/R2 - Focus Mode Tests (http://localhost:3010)

#### Authentication
- [ ] Login with email/password
- [ ] Login via demo account tile
- [ ] Logout functionality
- [ ] Session persistence after refresh

#### Home Page
- [ ] Dashboard loads correctly
- [ ] Balance display
- [ ] Recent transactions list
- [ ] Quick action buttons visible

#### Wallet
- [ ] View wallet address
- [ ] Copy address to clipboard
- [ ] View token balances

#### Transfer
- [ ] Send transaction form
- [ ] Recipient address validation
- [ ] Amount input
- [ ] Pre-transaction trust check

#### History
- [ ] Transaction list loads
- [ ] Filter by date
- [ ] Transaction details view

#### Settings
- [ ] Profile settings
- [ ] Security settings
- [ ] Notification preferences

---

### R3 - Institution Ops Tests (http://localhost:3010 or http://localhost:3006)

#### War Room Landing
- [ ] Dashboard overview loads
- [ ] Statistics cards display
- [ ] Risk distribution chart

#### Flagged Queue
- [ ] List of flagged transactions
- [ ] Risk score display
- [ ] Transaction details
- [ ] **Cannot approve/reject** (view only)

#### Graph Explorer
- [ ] Graph visualization loads
- [ ] Node click shows details
- [ ] Zoom/pan functionality
- [ ] Search by address

#### Detection Studio
- [ ] **Cannot access** (should be blocked)

---

### R4 - Compliance Officer Tests

#### All R3 capabilities PLUS:

#### Flagged Queue Actions
- [ ] Approve transaction
- [ ] Reject transaction
- [ ] Add notes/comments
- [ ] Escalate to admin

#### Policy Management
- [ ] View active policies
- [ ] Create new policy
- [ ] Edit existing policy
- [ ] Policy version history

#### Reports
- [ ] Generate compliance report
- [ ] Export to PDF/CSV
- [ ] Scheduled reports

---

### R5 - Platform Admin Tests

#### All R4 capabilities PLUS:

#### User Management
- [ ] View all users
- [ ] Create new user
- [ ] Edit user role
- [ ] Disable/enable user
- [ ] Reset password

#### System Configuration
- [ ] Risk thresholds
- [ ] API settings
- [ ] Integration config

#### Audit Logs
- [ ] View system audit trail
- [ ] Filter by action type
- [ ] Export audit logs

---

### R6 - Super Admin Tests

#### Emergency Override ONLY
- [ ] Emergency pause system
- [ ] Override frozen transaction
- [ ] **No access to Detection Studio**
- [ ] **No policy creation**

---

## 🔗 API Endpoints to Test

### Risk Engine (http://localhost:8002)

```
GET  /health                    - Health check
POST /score                     - Score a transaction
GET  /model/info               - Model information
```

### Memgraph Queries (bolt://localhost:7687)

```cypher
-- Count nodes
MATCH (n) RETURN count(n) as nodes;

-- Count edges
MATCH ()-[r]->() RETURN count(r) as edges;

-- Get sanctioned addresses
MATCH (a:Address {is_sanctioned: true}) RETURN a.address;

-- Get transaction graph
MATCH (from:Address)-[tx:SENT]->(to:Address)
RETURN from, tx, to LIMIT 100;
```

---

## 📊 Data Loaded

- **Address Nodes**: 2,830
- **Transaction Edges**: 5,000
- **Sanctioned Addresses**: 2
- **Data Source**: eth_transactions_full_labeled.parquet (30% sample)

---

## ⚠️ Known Issues

1. Service worker caching - Use Ctrl+Shift+R for hard refresh
2. First login may take a moment to initialize SharedPreferences

---

## 📝 Test Execution Log

| Date | Tester | Test Case | Status | Notes |
|------|--------|-----------|--------|-------|
| 2026-01-22 | Auto | Flutter App Response | ✅ PASS | HTML loads correctly at :3010 |
| 2026-01-22 | Auto | Next.js App Response | ✅ PASS | Server running at :3006 |
| 2026-01-22 | Auto | Risk Engine Health | ✅ PASS | Model loaded, healthy |
| 2026-01-22 | Auto | Memgraph Connection | ✅ PASS | 2,830 nodes, 5,000 edges |
| 2026-01-22 | Auto | Docker Containers | ✅ PASS | 12 containers running |

### Infrastructure Tests Completed:
- ✅ Flutter web server (port 3010) - Serving static files
- ✅ Next.js dev server (port 3006) - Running with hot reload
- ✅ Risk Engine API (port 8002) - Model: stacking-lgbm-ensemble-v1.0
- ✅ Memgraph database (port 7687) - Data loaded successfully
- ✅ Redis (port 6379) - Running
- ✅ MongoDB (port 27017) - Running

---

*Document generated: January 22, 2026*
