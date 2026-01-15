# AMTTP UI Integrity Protection System

**Anti-Bybit Attack Protection** - Comprehensive guide to preventing UI manipulation attacks

---

## 📋 Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Deployment](#deployment)
4. [Security Configuration](#security-configuration)
5. [Monitoring & Alerts](#monitoring--alerts)
6. [Testing](#testing)
7. [Incident Response](#incident-response)

---

## Overview

### What This System Protects Against

This system prevents **Bybit-style UI manipulation attacks** where attackers inject malicious code to:
- Modify displayed transaction details (show 1 ETH, actually send 100 ETH)
- Replace signing logic to steal signatures
- Inject scripts to redirect funds
- Manipulate event handlers to intercept transactions

### Protection Layers

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **Component Hashing** | SHA-256 | Detect UI code changes at runtime |
| **Intent Signing** | EIP-712 | Sign actual data, not displayed values |
| **Mutation Monitoring** | MutationObserver | Real-time DOM tampering detection |
| **Server Verification** | FastAPI Service | Validate UI integrity server-side |
| **Visual Confirmation** | React Component | Isolated confirmation layer |

---

## Architecture

### Components

```
┌─────────────────────────────────────────────────────────────┐
│                    Frontend (Next.js)                        │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ SecurePayment Component                                │ │
│  │  - UI Integrity Capture                                │ │
│  │  - Mutation Monitoring                                 │ │
│  │  - Transaction Intent Generation                       │ │
│  └────────────────────────────────────────────────────────┘ │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        ├──> Integrity Service (Port 8008)
                        │    - Hash Verification
                        │    - Violation Logging
                        │
                        └──> Orchestrator (Port 8007)
                             - Compliance Checks
                             - Intent Verification
```

### Files

```
AMTTP/
├── frontend/frontend/
│   ├── src/
│   │   ├── components/
│   │   │   └── SecurePayment.tsx        # Protected payment flow
│   │   ├── lib/
│   │   │   ├── ui-integrity.ts          # Integrity utilities
│   │   │   └── integrity-tests.ts       # Test suite
│   │   └── app/
│   │       └── transfer/page.tsx        # Transfer page (uses SecurePayment)
│   ├── scripts/
│   │   └── generate-integrity-hashes.ts # Build-time hash generation
│   └── public/
│       ├── integrity-hashes.json        # Generated hashes
│       └── register-hashes.sh           # Registration script
│
├── backend/compliance-service/
│   ├── integrity_service.py             # Integrity verification service
│   ├── orchestrator.py                  # Compliance orchestrator
│   ├── storage.py                       # MongoDB/Redis/MinIO/IPFS
│   ├── Dockerfile.integrity             # Container for integrity service
│   └── data/
│       └── integrity/
│           ├── trusted_hashes.json      # Known-good hashes
│           └── violations.jsonl         # Violation log
│
└── .github/workflows/
    └── deploy-with-integrity.yml        # CI/CD with hash registration
```

---

## Deployment

### Step 1: Environment Variables

Create `.env` file in `backend/compliance-service/`:

```bash
# Integrity Service
INTEGRITY_ADMIN_KEY=<GENERATE_STRONG_KEY>  # Use: openssl rand -hex 32
INTEGRITY_SERVICE_URL=http://localhost:8008

# Storage
MONGODB_URL=mongodb://admin:changeme@localhost:27017
MONGODB_DB=amttp
REDIS_URL=redis://localhost:6379
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=<YOUR_KEY>
MINIO_SECRET_KEY=<YOUR_SECRET>
IPFS_API_URL=http://localhost:5001

# Security
AUTH_ENABLED=true
USE_STORAGE_LAYER=true
```

### Step 2: Generate Strong Admin Key

```bash
# Generate a secure admin key
openssl rand -hex 32

# Or use Python
python -c "import secrets; print(secrets.token_hex(32))"

# Add to .env
echo "INTEGRITY_ADMIN_KEY=<generated_key>" >> backend/compliance-service/.env
```

### Step 3: Build Frontend with Hash Generation

```bash
cd frontend/frontend

# Install dependencies
npm install

# Generate integrity hashes (part of build)
npm run build:prod

# Verify hashes were created
ls -la public/integrity-hashes.json
```

### Step 4: Start Services

```bash
# Option A: Docker Compose (recommended)
docker-compose up -d orchestrator integrity

# Option B: Manual start
cd backend/compliance-service

# Start integrity service
python -m uvicorn integrity_service:app --host 0.0.0.0 --port 8008 &

# Start orchestrator
python -m uvicorn orchestrator:app --host 0.0.0.0 --port 8007 &
```

### Step 5: Register Hashes

```bash
cd frontend/frontend

# Set admin key
export INTEGRITY_ADMIN_KEY=<your_admin_key>

# Register hashes with integrity service
bash public/register-hashes.sh
```

### Step 6: Verify Deployment

```bash
# Check integrity service
curl http://localhost:8008/health

# Check orchestrator
curl http://localhost:8007/health

# Verify hash registration
curl "http://localhost:8008/violations?admin_key=<your_admin_key>&limit=1"
```

---

## Security Configuration

### Production Settings

#### 1. Restrict Admin Endpoints

Update `integrity_service.py`:

```python
# Add IP whitelist for admin endpoints
ADMIN_IPS = os.getenv("ADMIN_IPS", "127.0.0.1").split(",")

@app.post("/register-hash")
async def register_hash(request: Request, ...):
    client_ip = request.client.host if request.client else "unknown"
    if client_ip not in ADMIN_IPS:
        raise HTTPException(status_code=403, detail="Access denied")
    # ... rest of code
```

#### 2. Enable CORS Restrictions

Update `orchestrator.py`:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://your-domain.com",
        "https://app.your-domain.com"
    ],  # NO wildcards in production!
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-API-Key"],
)
```

#### 3. Rate Limiting

Already implemented via Redis in `storage.py`. Configure in `.env`:

```bash
RATE_LIMIT_REQUESTS=100    # Requests per window
RATE_LIMIT_WINDOW=60       # Window in seconds
```

#### 4. Logging & Monitoring

Configure structured logging:

```python
# In production, send to centralized logging (e.g., CloudWatch, Datadog)
import logging
import watchtower  # For AWS CloudWatch

logger.addHandler(watchtower.CloudWatchLogHandler())
```

---

## Monitoring & Alerts

### Real-Time Violation Monitoring

```bash
# Watch violations in real-time
tail -f backend/compliance-service/data/integrity/violations.jsonl

# Or via API
watch -n 10 'curl -s "http://localhost:8008/violations?admin_key=<key>&limit=10" | jq'
```

### Alert Setup

#### Option 1: Email Alerts (Python)

```python
# Add to integrity_service.py
async def send_alert_email(violation: IntegrityViolation):
    if violation.severity == "critical":
        import smtplib
        from email.message import EmailMessage
        
        msg = EmailMessage()
        msg["Subject"] = f"CRITICAL: UI Integrity Violation"
        msg["From"] = "alerts@your-domain.com"
        msg["To"] = "security@your-domain.com"
        msg.set_content(f"""
        CRITICAL integrity violation detected:
        
        Type: {violation.violation_type}
        IP: {violation.client_ip}
        Details: {violation.details}
        Time: {violation.timestamp}
        """)
        
        with smtplib.SMTP("smtp.gmail.com", 587) as smtp:
            smtp.starttls()
            smtp.login("user", "password")
            smtp.send_message(msg)
```

#### Option 2: Slack/Discord Webhooks

```python
async def send_slack_alert(violation: IntegrityViolation):
    if violation.severity in ["critical", "high"]:
        import aiohttp
        
        webhook_url = os.getenv("SLACK_WEBHOOK_URL")
        async with aiohttp.ClientSession() as session:
            await session.post(webhook_url, json={
                "text": f"🚨 {violation.severity.upper()} Integrity Violation",
                "blocks": [{
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Type:* {violation.violation_type}\n*IP:* {violation.client_ip}\n*Time:* {violation.timestamp}"
                    }
                }]
            })
```

### Metrics Dashboard

Create a monitoring dashboard showing:

```javascript
// Fetch metrics
const metrics = {
  totalViolations: violations.length,
  criticalCount: violations.filter(v => v.severity === 'critical').length,
  last24h: violations.filter(v => 
    new Date(v.timestamp) > Date.now() - 86400000
  ).length,
  byType: violations.reduce((acc, v) => {
    acc[v.violation_type] = (acc[v.violation_type] || 0) + 1;
    return acc;
  }, {})
};
```

---

## Testing

### Automated Tests

Run the test suite:

```bash
# In browser console on /transfer page
integrityTests.runAll()

# Or programmatically
import { runAllTests } from '@/lib/integrity-tests';
const results = await runAllTests();
```

### Manual Testing Scenarios

#### Scenario 1: Script Injection
```javascript
// Open browser console on transfer page
const script = document.createElement('script');
script.textContent = 'alert("XSS")';
document.querySelector('[data-integrity-protected]').appendChild(script);
// EXPECTED: Transaction blocked, mutation alert triggered
```

#### Scenario 2: Value Manipulation
```javascript
// Modify displayed amount
const input = document.querySelector('input[type="text"]');
input.value = "1.0";  // Display 1 ETH
input.dataset.actualValue = "100.0";  // Actually try to send 100 ETH
// EXPECTED: Hash mismatch during verification
```

#### Scenario 3: Hash Tampering
```bash
# Try to submit with fake hash
curl -X POST http://localhost:8008/submit-payment \
  -H "Content-Type: application/json" \
  -d '{
    "intent": {...},
    "intentHash": "fake_hash",
    "signature": "...",
    "integrityReport": {...}
  }'
# EXPECTED: 400 error "Intent hash mismatch"
```

---

## Incident Response

### If Violation Detected

1. **Immediate Actions**
   - Block the IP address
   - Invalidate any sessions from that IP
   - Review all transactions from that user

2. **Investigation**
   ```bash
   # Get full violation details
   curl "http://localhost:8008/violations?admin_key=<key>" | \
     jq '.[] | select(.client_ip == "X.X.X.X")'
   
   # Check orchestrator logs
   grep "X.X.X.X" backend/compliance-service/data/orchestrator/*.log
   ```

3. **Mitigation**
   - Rotate `INTEGRITY_ADMIN_KEY`
   - Regenerate and re-register UI hashes
   - Review and update trusted hash store

4. **Communication**
   - Notify security team
   - Document incident
   - Update security policies if needed

### False Positives

If legitimate deployments trigger violations:

1. **Verify the deployment was authorized**
2. **Generate new hashes**:
   ```bash
   cd frontend/frontend
   npm run generate-hashes
   ```
3. **Register new hashes**:
   ```bash
   export INTEGRITY_ADMIN_KEY=<key>
   bash public/register-hashes.sh
   ```
4. **Clear false positive violations** (optional)

---

## Best Practices

### Development
- ✅ Always run `npm run generate-hashes` before deployment
- ✅ Test integrity protection in staging environment
- ✅ Never commit `INTEGRITY_ADMIN_KEY` to git
- ✅ Review violation logs weekly

### Production
- ✅ Use strong admin keys (32+ bytes random)
- ✅ Rotate admin keys every 90 days
- ✅ Monitor violations dashboard daily
- ✅ Set up automated alerts for critical violations
- ✅ Restrict admin endpoints to VPN/internal IPs
- ✅ Keep integrity service separate from public traffic

### Operations
- ✅ Document hash registration process
- ✅ Train team on incident response
- ✅ Regular security audits of violation logs
- ✅ Backup trusted hash store
- ✅ Test recovery procedures

---

## Troubleshooting

### Common Issues

**Q: "Integrity verification failed" on legitimate page**  
A: Regenerate hashes and re-register:
```bash
cd frontend/frontend
npm run build:prod
```

**Q: Violations service shows 403 Forbidden**  
A: Check `INTEGRITY_ADMIN_KEY` is correct:
```bash
echo $INTEGRITY_ADMIN_KEY
```

**Q: Hashes not matching after deployment**  
A: Ensure build artifacts include `integrity-hashes.json`:
```bash
ls -la frontend/frontend/public/integrity-hashes.json
```

**Q: MongoDB/Redis connection failures**  
A: Check storage layer configuration:
```bash
curl http://localhost:8007/health | jq '.storage'
```

---

## Support

For issues or questions:
- Security incidents: security@your-domain.com
- Technical support: support@your-domain.com
- Documentation: https://docs.your-domain.com/integrity

---

**Last Updated:** January 2026  
**Version:** 1.0.0
