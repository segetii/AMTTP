# AMTTP Production Deployment Runbook

**Version:** 1.0.0  
**Last Updated:** January 2026  
**Maintainer:** DevOps & Security Team

---

## Table of Contents

1. [Pre-Deployment Checklist](#pre-deployment-checklist)
2. [Deployment Process](#deployment-process)
3. [Post-Deployment Verification](#post-deployment-verification)
4. [Rollback Procedures](#rollback-procedures)
5. [Monitoring & Health Checks](#monitoring--health-checks)
6. [Incident Response](#incident-response)
7. [Maintenance Procedures](#maintenance-procedures)

---

## Pre-Deployment Checklist

### Environment Setup

- [ ] `.env` file created from `.env.example`
- [ ] All secrets generated with strong cryptographic randomness:
  ```bash
  # Generate all required secrets
  echo "INTEGRITY_ADMIN_KEY=$(openssl rand -hex 32)" >> .env
  echo "ORCHESTRATOR_API_KEY=$(python -c 'import secrets; print(secrets.token_urlsafe(32))')" >> .env
  echo "JWT_SECRET=$(openssl rand -base64 32)" >> .env
  echo "ENCRYPTION_KEY=$(openssl rand -hex 32)" >> .env
  ```
- [ ] MongoDB connection verified: `mongosh $MONGODB_URL --eval "db.stats()"`
- [ ] Redis connection verified: `redis-cli -u $REDIS_URL ping`
- [ ] MinIO buckets created: `amttp-kyc-documents`, `amttp-compliance-evidence`, `amttp-reports`
- [ ] IPFS daemon running and accessible: `curl $IPFS_API_URL/version`

### Security Configuration

- [ ] `AUTH_ENABLED=true` in production
- [ ] `DEV_MODE=false` in production
- [ ] `CORS_ORIGINS` set to actual frontend domain(s), NO wildcards
- [ ] `ADMIN_IPS` restricted to VPN/internal networks
- [ ] SSL/TLS certificates installed and valid
- [ ] Firewall rules configured:
  - Port 8007: Orchestrator (internal only)
  - Port 8008: Integrity Service (internal only)
  - Port 443: Frontend (public)

### Code & Build Verification

- [ ] Git branch: `main` or `release/*`
- [ ] All tests passing: `npm test && pytest`
- [ ] Frontend integrity hashes generated: `npm run generate-hashes`
- [ ] Docker images built and tagged:
  ```bash
  docker build -t amttp-orchestrator:latest -f backend/compliance-service/Dockerfile .
  docker build -t amttp-integrity:latest -f backend/compliance-service/Dockerfile.integrity .
  docker build -t amttp-frontend:latest -f frontend/frontend/Dockerfile .
  ```

### Compliance & Audit

- [ ] Security audit completed (if major changes)
- [ ] Change request approved
- [ ] Deployment window scheduled
- [ ] Stakeholders notified

---

## Deployment Process

### Phase 1: Storage Layer

**Estimated Time:** 5 minutes

```bash
# 1. Start MongoDB
docker-compose up -d mongo

# 2. Wait for MongoDB to be ready
until docker exec amttp-mongo mongosh --eval "db.stats()" > /dev/null 2>&1; do
  echo "Waiting for MongoDB..."
  sleep 2
done

# 3. Initialize indexes
docker exec amttp-mongo mongosh amttp /app/scripts/init-mongo-indexes.js

# 4. Start Redis
docker-compose up -d redis

# 5. Start MinIO
docker-compose up -d minio

# 6. Create MinIO buckets
docker exec amttp-minio mc alias set local http://localhost:9000 $MINIO_ACCESS_KEY $MINIO_SECRET_KEY
docker exec amttp-minio mc mb local/amttp-kyc-documents
docker exec amttp-minio mc mb local/amttp-compliance-evidence
docker exec amttp-minio mc mb local/amttp-reports

# 7. Start IPFS
docker-compose up -d helia

# Verify all storage services
docker-compose ps | grep -E "(mongo|redis|minio|helia)"
```

### Phase 2: Backend Services

**Estimated Time:** 3 minutes

```bash
# 1. Start compliance services
docker-compose up -d sanctions-service monitoring-service geo-risk-service

# 2. Wait for services to be healthy
for service in sanctions monitoring geo-risk; do
  until curl -sf http://localhost:800$((${service##*-}+3))/health > /dev/null; do
    echo "Waiting for $service..."
    sleep 2
  done
done

# 3. Start zkNAF and Risk Router
docker-compose up -d zknaf risk-router

# 4. Start Orchestrator
docker-compose up -d orchestrator

# Wait for orchestrator
until curl -sf http://localhost:8007/health > /dev/null; do
  echo "Waiting for orchestrator..."
  sleep 2
done
```

### Phase 3: Integrity Service

**Estimated Time:** 2 minutes

```bash
# 1. Ensure INTEGRITY_ADMIN_KEY is set
if [ -z "$INTEGRITY_ADMIN_KEY" ]; then
  echo "ERROR: INTEGRITY_ADMIN_KEY not set!"
  exit 1
fi

# 2. Start integrity service
docker-compose up -d integrity

# Wait for service
until curl -sf http://localhost:8008/health > /dev/null; do
  echo "Waiting for integrity service..."
  sleep 2
done

# 3. Register UI hashes
cd frontend/frontend
export INTEGRITY_ADMIN_KEY=$INTEGRITY_ADMIN_KEY
bash public/register-hashes.sh

# Verify registration
curl -s "http://localhost:8008/violations?admin_key=$INTEGRITY_ADMIN_KEY&limit=1" | jq
```

### Phase 4: Frontend Deployment

**Estimated Time:** 5 minutes

```bash
# 1. Build frontend with integrity hashes
cd frontend/frontend
npm ci
npm run build:prod

# 2. Verify build artifacts
ls -la .next/static
ls -la public/integrity-hashes.json

# 3. Deploy to CDN/hosting (example: Vercel)
vercel --prod

# OR: Docker deployment
docker-compose up -d frontend
```

### Phase 5: Smoke Tests

**Estimated Time:** 3 minutes

```bash
# 1. Health checks
curl http://localhost:8007/health | jq
curl http://localhost:8008/health | jq

# 2. Test orchestrator evaluation
curl -X POST http://localhost:8007/evaluate \
  -H "Content-Type: application/json" \
  -d '{
    "address": "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb",
    "amount": "1.0",
    "destination": "0xRecipient",
    "profile": "retail_user",
    "metadata": {}
  }' | jq

# 3. Test integrity verification
curl -X POST http://localhost:8008/verify-integrity \
  -H "Content-Type: application/json" \
  -d '{
    "componentId": "SecurePayment",
    "sourceHash": "test",
    "domHash": "test",
    "handlerHash": "test",
    "timestamp": "'$(date -u +%Y-%m-%dT%H:%M:%SZ)'"
  }' | jq

# 4. Test frontend
curl -I https://your-domain.com/transfer
curl https://your-domain.com/api/health
```

---

## Post-Deployment Verification

### Automated Checks

Run the verification script:

```bash
#!/bin/bash
# verify-deployment.sh

set -e

echo "=== AMTTP Deployment Verification ==="

# Service health
echo "[1/6] Checking service health..."
for port in 8007 8008; do
  if curl -sf http://localhost:$port/health > /dev/null; then
    echo "  ✓ Port $port healthy"
  else
    echo "  ✗ Port $port FAILED"
    exit 1
  fi
done

# Storage connections
echo "[2/6] Verifying storage connections..."
HEALTH=$(curl -s http://localhost:8007/health | jq -r '.storage')
if [ "$HEALTH" != "null" ]; then
  echo "  ✓ Storage layer connected"
else
  echo "  ✗ Storage layer FAILED"
  exit 1
fi

# Integrity hashes
echo "[3/6] Checking integrity hashes..."
if [ -f frontend/frontend/public/integrity-hashes.json ]; then
  COUNT=$(jq 'length' frontend/frontend/public/integrity-hashes.json)
  echo "  ✓ $COUNT component hashes registered"
else
  echo "  ✗ No integrity hashes found"
  exit 1
fi

# Test transaction flow
echo "[4/6] Testing transaction evaluation..."
RESPONSE=$(curl -s -X POST http://localhost:8007/evaluate \
  -H "Content-Type: application/json" \
  -d '{
    "address": "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb",
    "amount": "1.0",
    "destination": "0xRecipient",
    "profile": "retail_user",
    "metadata": {}
  }')
ACTION=$(echo $RESPONSE | jq -r '.action')
if [ "$ACTION" != "null" ]; then
  echo "  ✓ Transaction evaluation working (Action: $ACTION)"
else
  echo "  ✗ Transaction evaluation FAILED"
  exit 1
fi

# Integrity tests
echo "[5/6] Running integrity tests..."
# Open browser console and run: integrityTests.runAll()
echo "  ⚠ Manual step: Run integrityTests.runAll() in browser console"

# Monitoring
echo "[6/6] Checking monitoring endpoints..."
if curl -sf "http://localhost:8008/violations?admin_key=$INTEGRITY_ADMIN_KEY&limit=1" > /dev/null; then
  echo "  ✓ Violations endpoint accessible"
else
  echo "  ✗ Violations endpoint FAILED"
  exit 1
fi

echo ""
echo "=== Deployment verification complete ==="
```

### Manual Verification

1. **UI Integrity Test**
   - Navigate to https://your-domain.com/transfer
   - Open browser console
   - Run: `integrityTests.runAll()`
   - Verify all tests pass

2. **Transaction Flow Test**
   - Connect MetaMask wallet
   - Initiate a small test transaction (0.001 ETH)
   - Verify compliance checks execute
   - Verify UI integrity protection activated
   - Complete transaction signature
   - Check transaction appears in history

3. **Violation Detection Test**
   - Open browser console
   - Try to inject script: 
     ```javascript
     const script = document.createElement('script');
     script.textContent = 'alert("test")';
     document.querySelector('[data-integrity-protected]').appendChild(script);
     ```
   - Verify mutation alert appears
   - Check violation logged: `curl "http://localhost:8008/violations?admin_key=$ADMIN_KEY&limit=1"`

---

## Rollback Procedures

### Scenario 1: Service Failure

If orchestrator or integrity service fails:

```bash
# 1. Stop failed service
docker-compose stop orchestrator  # or integrity

# 2. Check logs
docker-compose logs --tail=100 orchestrator

# 3. Rollback to previous image
docker-compose pull amttp-orchestrator:previous
docker tag amttp-orchestrator:previous amttp-orchestrator:latest

# 4. Restart
docker-compose up -d orchestrator

# 5. Verify
curl http://localhost:8007/health
```

### Scenario 2: Integrity Hash Mismatch

If legitimate users see "Integrity verification failed":

```bash
# 1. Confirm deployment was authorized
git log -1 --oneline

# 2. Regenerate hashes from current code
cd frontend/frontend
npm run generate-hashes

# 3. Re-register hashes
export INTEGRITY_ADMIN_KEY=$ADMIN_KEY
bash public/register-hashes.sh

# 4. Verify
curl "http://localhost:8008/violations?admin_key=$ADMIN_KEY&limit=10" | \
  jq '.[] | select(.violation_type == "hash_mismatch")'

# 5. If false positives, clear them (optional)
# This should be done carefully!
```

### Scenario 3: Critical Security Breach

If active attack detected:

```bash
# IMMEDIATE ACTIONS (within 5 minutes)

# 1. Block malicious IPs
iptables -A INPUT -s <ATTACKER_IP> -j DROP

# 2. Rotate all secrets
./scripts/rotate-secrets.sh

# 3. Invalidate all sessions
redis-cli FLUSHDB

# 4. Enable emergency mode (block all new transactions)
curl -X POST http://localhost:8007/emergency-mode \
  -H "X-Admin-Key: $ADMIN_KEY" \
  -d '{"enabled": true}'

# 5. Notify security team
./scripts/send-alert.sh "CRITICAL: Security breach detected"

# INVESTIGATION (within 1 hour)
# 6. Collect evidence
docker-compose logs > incident-logs.txt
curl "http://localhost:8008/violations?admin_key=$ADMIN_KEY" > violations.json

# 7. Review all transactions from attacker
mongo amttp --eval 'db.compliance_decisions.find({client_ip: "<IP>"})'

# 8. Check for data exfiltration
grep -r "SELECT \*" logs/
grep -r "dump" logs/

# RECOVERY (within 4 hours)
# 9. Patch vulnerability
# 10. Deploy patched version
# 11. Re-enable services gradually
# 12. Monitor closely for 24h
```

---

## Monitoring & Health Checks

### Automated Monitoring

#### Uptime Monitoring

```bash
# Add to crontab (check every 2 minutes)
*/2 * * * * /opt/amttp/scripts/health-check.sh
```

**health-check.sh:**
```bash
#!/bin/bash
SERVICES="8007 8008"
for port in $SERVICES; do
  if ! curl -sf http://localhost:$port/health > /dev/null; then
    echo "Service on port $port is DOWN" | mail -s "ALERT: Service Down" ops@your-domain.com
    # Auto-restart (optional)
    docker-compose restart $(docker-compose ps | grep $port | awk '{print $1}')
  fi
done
```

#### Violation Monitoring

```bash
# Check for critical violations every 10 minutes
*/10 * * * * /opt/amttp/scripts/check-violations.sh
```

**check-violations.sh:**
```bash
#!/bin/bash
ADMIN_KEY=$(cat /opt/amttp/.env | grep INTEGRITY_ADMIN_KEY | cut -d= -f2)
VIOLATIONS=$(curl -s "http://localhost:8008/violations?admin_key=$ADMIN_KEY&limit=100" | \
  jq '[.[] | select(.severity == "critical")] | length')

if [ "$VIOLATIONS" -gt 0 ]; then
  echo "$VIOLATIONS critical violations detected in last 10 min" | \
    mail -s "ALERT: Security Violations" security@your-domain.com
fi
```

### Manual Monitoring

#### Daily Checks (5 minutes)

```bash
# 1. Check service health
docker-compose ps

# 2. Review violation summary
curl -s "http://localhost:8008/violations?admin_key=$ADMIN_KEY&limit=100" | \
  jq 'group_by(.severity) | map({severity: .[0].severity, count: length})'

# 3. Check storage usage
df -h /var/lib/docker
docker exec amttp-mongo mongosh --eval "db.stats()"
docker exec amttp-minio mc du local/

# 4. Review error logs
docker-compose logs --tail=100 orchestrator | grep ERROR
docker-compose logs --tail=100 integrity | grep ERROR
```

#### Weekly Checks (15 minutes)

```bash
# 1. Analyze violation trends
python3 scripts/analyze-violations.py --days 7

# 2. Review compliance decisions
mongo amttp --eval '
  db.compliance_decisions.aggregate([
    {$match: {timestamp: {$gte: new Date(Date.now() - 7*24*60*60*1000)}}},
    {$group: {_id: "$action", count: {$sum: 1}}}
  ])
'

# 3. Check storage growth
python3 scripts/storage-report.py

# 4. Test disaster recovery backups
./scripts/test-backup-restore.sh
```

---

## Incident Response

### Severity Levels

| Level | Response Time | Examples |
|-------|---------------|----------|
| **P0 - Critical** | < 15 min | Service down, active attack, data breach |
| **P1 - High** | < 1 hour | Integrity violations, compliance failures |
| **P2 - Medium** | < 4 hours | Performance degradation, minor bugs |
| **P3 - Low** | < 24 hours | Feature requests, documentation |

### P0 - Critical Incident

**Within 15 minutes:**

1. **Acknowledge & Assess**
   ```bash
   # Check all services
   docker-compose ps
   curl http://localhost:8007/health | jq
   curl http://localhost:8008/health | jq
   
   # Check recent logs
   docker-compose logs --tail=500 --timestamps
   ```

2. **Notify Team**
   ```bash
   # Send alert
   ./scripts/send-alert.sh "P0: [Brief description]" "security@your-domain.com ops@your-domain.com"
   ```

3. **Mitigate**
   - If service down → restart: `docker-compose restart <service>`
   - If attack → block IP: `iptables -A INPUT -s <IP> -j DROP`
   - If data breach → enable emergency mode, rotate secrets

**Within 1 hour:**

4. **Investigate Root Cause**
   - Collect logs: `docker-compose logs > incident-$(date +%Y%m%d_%H%M%S).log`
   - Review violations: `curl "http://localhost:8008/violations?admin_key=$ADMIN_KEY"`
   - Check database: `mongosh amttp --eval "db.audit_log.find().sort({timestamp:-1}).limit(100)"`

5. **Document Incident**
   - Create incident report in `docs/incidents/YYYYMMDD-incident-name.md`
   - Document timeline, root cause, impact, resolution

**Within 4 hours:**

6. **Implement Fix**
   - Deploy patch if needed
   - Update monitoring/alerting to catch similar issues
   - Conduct post-mortem meeting

---

## Maintenance Procedures

### Daily Maintenance

```bash
# Automated daily cleanup (add to crontab)
0 2 * * * /opt/amttp/scripts/daily-maintenance.sh
```

**daily-maintenance.sh:**
```bash
#!/bin/bash
# Remove old Docker logs
docker system prune -f --filter "until=24h"

# Compress old application logs
find /var/log/amttp -name "*.log" -mtime +1 -exec gzip {} \;

# Clean Redis cache (optional)
redis-cli --scan --pattern "amttp:cache:*" | xargs redis-cli DEL

# Archive old violations (keep last 30 days)
python3 /opt/amttp/scripts/archive-violations.py --days 30
```

### Weekly Maintenance

- [ ] Review and rotate secrets (if needed)
- [ ] Update security patches: `apt update && apt upgrade`
- [ ] Backup MongoDB: `mongodump --uri=$MONGODB_URL --out=/backups/mongo-$(date +%Y%m%d)`
- [ ] Test backups: `./scripts/test-backup-restore.sh`
- [ ] Review storage growth and cleanup if needed

### Monthly Maintenance

- [ ] Rotate INTEGRITY_ADMIN_KEY: `./scripts/rotate-admin-key.sh`
- [ ] Security audit: Review violation logs, access logs, compliance decisions
- [ ] Performance optimization: Analyze slow queries, optimize indexes
- [ ] Update dependencies: `npm audit fix && pip list --outdated`

### Quarterly Maintenance

- [ ] Disaster recovery drill
- [ ] Security penetration testing
- [ ] Compliance audit
- [ ] Documentation review and updates

---

## Emergency Contacts

| Role | Name | Email | Phone |
|------|------|-------|-------|
| **On-Call Engineer** | [Name] | oncall@your-domain.com | +1-XXX-XXX-XXXX |
| **Security Lead** | [Name] | security@your-domain.com | +1-XXX-XXX-XXXX |
| **DevOps Lead** | [Name] | devops@your-domain.com | +1-XXX-XXX-XXXX |
| **CTO/Engineering VP** | [Name] | cto@your-domain.com | +1-XXX-XXX-XXXX |

### Escalation Path

1. On-Call Engineer (0-15 min)
2. DevOps Lead (15-30 min)
3. Security Lead (30-60 min)
4. CTO/VP Engineering (60+ min or business impact)

---

## Appendix

### Useful Commands

```bash
# View real-time logs
docker-compose logs -f orchestrator integrity

# Check disk usage
docker system df
df -h /var/lib/docker

# Database queries
mongosh amttp --eval "db.compliance_decisions.find().sort({timestamp:-1}).limit(10)"

# Redis inspection
redis-cli --scan --pattern "amttp:*"

# MinIO statistics
docker exec amttp-minio mc admin info local

# IPFS status
curl http://localhost:5001/api/v0/stats/bw
```

### Maintenance Scripts

All scripts located in `scripts/`:
- `health-check.sh` - Service health monitoring
- `check-violations.sh` - Security violation monitoring
- `daily-maintenance.sh` - Daily cleanup tasks
- `rotate-secrets.sh` - Secret rotation
- `backup-mongodb.sh` - Database backups
- `test-backup-restore.sh` - Backup verification
- `send-alert.sh` - Alert notifications

---

**Document Owner:** DevOps Team  
**Review Frequency:** Quarterly  
**Last Reviewed:** January 2026
