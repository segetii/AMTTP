# AMTTP — Contabo VPS Deployment Guide

## Architecture

```
Internet → Cloudflare (SSL/CDN/WAF) → Tunnel → VPS nginx:80 → Docker services
```

**VPS**: Contabo VPS L (12 vCPU, 48GB RAM, 400GB NVMe)  
**OS**: Ubuntu 22.04/24.04 LTS  
**CDN/SSL**: Cloudflare (existing amttp.com)  
**Containers**: Same 18-service stack, resource-limited for VPS

## Quick Start (5 steps)

### Step 1: Provision VPS

After purchasing Contabo VPS L with Ubuntu:

```bash
# From your local machine (Git Bash / WSL)
ssh root@YOUR_VPS_IP 'bash -s' < infrastructure/contabo/setup-vps.sh
```

This installs Docker, hardens SSH, sets up firewall, creates `amttp` user, and prepares `/opt/amttp`.

### Step 2: Set up Cloudflare Tunnel

**Option A: Use the script** (requires cloudflared CLI locally):
```bash
bash infrastructure/scripts/setup-cloudflare-tunnel.sh amttp-vps
```

**Option B: Manual via Cloudflare Dashboard**:
1. Go to [Cloudflare Zero Trust](https://one.dash.cloudflare.com/) → Networks → Tunnels
2. Create tunnel named `amttp-vps`
3. Copy the tunnel token (long base64 string)
4. Add public hostnames:
   - `amttp.com` → `http://nginx-gateway:80`
   - `www.amttp.com` → `http://nginx-gateway:80`
5. **Delete or disable** the old tunnel pointing to your local machine

### Step 3: Configure VPS environment

SSH into the VPS and edit the `.env` file:

```bash
ssh amttp@YOUR_VPS_IP
nano /opt/amttp/.env
```

Set these values:
```env
# Required
CLOUDFLARE_TUNNEL_TOKEN=eyJh...your_tunnel_token_here

# Passwords (change these!)
MONGO_INITDB_ROOT_USERNAME=admin
MONGO_INITDB_ROOT_PASSWORD=<generate-strong-password>
REDIS_PASSWORD=<generate-strong-password>
MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=<generate-strong-password>

# API keys (from your existing setup)
INFURA_API_KEY=17e45820418f4461a48ceb80774afecb
ALCHEMY_API_KEY=89pxLpYGB_qLyt6T-mVQC

# Optional: Webhook alerts (Discord/Slack)
AMTTP_WEBHOOK_URL=https://discord.com/api/webhooks/...
```

### Step 4: Deploy

```bash
# From your local machine
export AMTTP_VPS_HOST=YOUR_CONTABO_IP
bash infrastructure/scripts/deploy.sh
```

This rsyncs the project, builds images on VPS, starts services, and verifies health.

### Step 5: Migrate MongoDB data

```bash
# From your local machine (with local Docker running)
bash infrastructure/scripts/migrate-data.sh
```

Dumps 920K+ transactions from local MongoDB, transfers and restores on VPS.

## Files Reference

| File | Purpose |
|------|---------|
| `infrastructure/contabo/setup-vps.sh` | One-time VPS provisioning (Docker, SSH, firewall, kernel) |
| `infrastructure/contabo/docker-compose.vps.yml` | VPS-optimized compose with resource limits |
| `infrastructure/scripts/deploy.sh` | Rsync + build + start (repeatable) |
| `infrastructure/scripts/migrate-data.sh` | MongoDB data migration (local → VPS) |
| `infrastructure/scripts/setup-cloudflare-tunnel.sh` | Creates/configures Cloudflare tunnel |
| `infrastructure/scripts/backup.sh` | Automated daily/weekly backups |
| `infrastructure/scripts/health-check.sh` | Health monitoring with webhook alerts |

## Resource Budget (48GB VPS RAM)

| Service | Memory Limit | Notes |
|---------|-------------|-------|
| MongoDB | 6 GB | WiredTiger cache: 4GB |
| Memgraph | 5 GB | Graph analytics |
| ML Risk Engine | 4 GB | CPU inference, student model |
| Orchestrator | 2 GB | Fan-out to all services |
| Redis | 1.5 GB | Cache + sessions |
| Dashboard (Next.js) | 1 GB | SSR + API routes |
| ZK-NAF Service | 1 GB | Zero-knowledge proofs |
| MinIO | 512 MB | Object storage |
| Prometheus | 512 MB | Metrics |
| IPFS (Helia) | 512 MB | Decentralized storage |
| Nginx | 256 MB | Reverse proxy |
| Grafana | 256 MB | Dashboards |
| Cloudflared | 128 MB | Tunnel agent |
| **Total allocated** | **~22.5 GB** | **25.5 GB free for OS + other services** |

## Post-Deploy Checklist

- [ ] Verify `https://amttp.com` loads the landing page
- [ ] Verify `https://amttp.com/app/` loads the dashboard
- [ ] Check MongoDB data: `https://amttp.com/app-api/data/stats` returns 920K+ transactions
- [ ] Check ML endpoint: `https://amttp.com/ml/health`
- [ ] Set up cron jobs:
  ```bash
  ssh amttp@VPS_IP
  crontab -e
  # Add:
  */5 * * * * /opt/amttp/infrastructure/scripts/health-check.sh >> /var/log/amttp-health.log 2>&1
  0 3 * * * /opt/amttp/infrastructure/scripts/backup.sh >> /var/log/amttp-backup.log 2>&1
  0 2 * * 0 /opt/amttp/infrastructure/scripts/backup.sh --full >> /var/log/amttp-backup.log 2>&1
  ```
- [ ] Delete old Cloudflare tunnel pointing to local machine
- [ ] Confirm webhook alerts work (if configured)

## Updating (after code changes)

```bash
export AMTTP_VPS_HOST=YOUR_CONTABO_IP
bash infrastructure/scripts/deploy.sh
```

The deploy script is idempotent — rsync only transfers changed files, `docker compose up -d` only recreates changed containers.

## Troubleshooting

### Services won't start
```bash
ssh amttp@VPS_IP
cd /opt/amttp
docker compose -f docker-compose.vps.yml logs --tail 50 SERVICE_NAME
```

### Cloudflare tunnel not connecting
```bash
# Check tunnel container logs
docker logs amttp-cloudflared --tail 30
# Verify token is set
grep CLOUDFLARE_TUNNEL_TOKEN /opt/amttp/.env
```

### High memory usage
```bash
# Check per-container usage
docker stats --no-stream --format "table {{.Name}}\t{{.MemUsage}}\t{{.MemPerc}}"
```

### MongoDB connection issues
```bash
# Test from inside the network
docker exec amttp-mongo mongosh --eval "db.adminCommand('ping')"
# Check connection from dashboard
docker logs amttp-dashboard --tail 20 | grep -i mongo
```

## Cost Summary

| Item | Monthly Cost |
|------|-------------|
| Contabo VPS L (12 vCPU, 48GB, 400GB NVMe) | ~€18 |
| Cloudflare (Free plan) | €0 |
| Domain (amttp.com) | ~€1 |
| **Total** | **~€19/month** |
