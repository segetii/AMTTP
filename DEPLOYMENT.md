# AMTTP Platform - Cloudflare Tunnel Deployment Guide

Deploy the complete AMTTP Anti-Money Laundering Transaction Protocol platform with secure public access via Cloudflare Tunnel.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              CLOUDFLARE                                      │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                    Cloudflare Tunnel                                 │    │
│  │   https://amttp.yourdomain.com  ──────────────────────────┐        │    │
│  └───────────────────────────────────────────────────────────│────────┘    │
└──────────────────────────────────────────────────────────────│──────────────┘
                                                               │
                                                               ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                           DOCKER COMPOSE                                      │
│                                                                               │
│  ┌──────────────┐    ┌─────────────────────────────────────────────────┐    │
│  │  cloudflared │───▶│               amttp-platform                     │    │
│  │              │    │  ┌─────────┐  ┌───────────┐  ┌──────────────┐   │    │
│  └──────────────┘    │  │  nginx  │  │  Next.js  │  │  Python API  │   │    │
│                      │  │  :80    │  │  :3000    │  │  :8002-8008  │   │    │
│                      │  └─────────┘  └───────────┘  └──────────────┘   │    │
│                      │                                                  │    │
│                      │  ┌────────────┐  ┌────────────┐                 │    │
│                      │  │  Flutter   │  │   zkNAF    │                 │    │
│                      │  │  Web App   │  │  Circuits  │                 │    │
│                      │  └────────────┘  └────────────┘                 │    │
│                      └─────────────────────────────────────────────────┘    │
│                                                                               │
│  ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌───────────┐              │
│  │  MongoDB  │  │   Redis   │  │ Memgraph  │  │   MinIO   │              │
│  │   :27017  │  │   :6379   │  │   :7687   │  │   :9000   │              │
│  └───────────┘  └───────────┘  └───────────┘  └───────────┘              │
│                                                                               │
└──────────────────────────────────────────────────────────────────────────────┘
```

## Prerequisites

- **Docker Desktop** v24.0+ with Docker Compose v2
- **Cloudflare Account** with a domain configured
- **4GB+ RAM** available for Docker
- **20GB disk space** for images and data

## Quick Start

### 1. Get Cloudflare Tunnel Token

1. Log into [Cloudflare Dashboard](https://one.dash.cloudflare.com)
2. Navigate to **Zero Trust** → **Networks** → **Tunnels**
3. Click **Create a tunnel**
4. Name it `amttp-production`
5. Copy the tunnel token (starts with `eyJ...`)

### 2. Deploy

**Windows (PowerShell):**
```powershell
cd c:\amttp
.\scripts\deploy-cloudflare.ps1 -Action deploy -TunnelToken "eyJhIjoiY..."
```

**Linux/macOS:**
```bash
cd /path/to/amttp
chmod +x scripts/deploy-cloudflare.sh
./scripts/deploy-cloudflare.sh deploy --token "eyJhIjoiY..."
```

### 3. Configure Cloudflare Public Hostname

1. In Cloudflare Dashboard, go to your tunnel configuration
2. Add a **Public Hostname**:
   - Subdomain: `amttp` (or your choice)
   - Domain: your domain
   - Service: `http://amttp-platform:80`
3. Save the configuration

### 4. Access Your Platform

- **Main App**: `https://amttp.yourdomain.com`
- **Dashboard**: `https://amttp.yourdomain.com/dashboard`
- **API**: `https://amttp.yourdomain.com/api`

## Available Commands

| Command | Description |
|---------|-------------|
| `deploy` | Build and start all services |
| `build` | Build Docker images only |
| `start` | Start existing containers |
| `stop` | Stop all containers |
| `status` | Show container health status |
| `logs` | Stream logs (use `--tail N`) |
| `clean` | Remove all containers and volumes |

### Examples

```powershell
# Check status
.\scripts\deploy-cloudflare.ps1 -Action status

# View logs
.\scripts\deploy-cloudflare.ps1 -Action logs -LogTail 200

# Stop services
.\scripts\deploy-cloudflare.ps1 -Action stop

# Include Hardhat dev node
.\scripts\deploy-cloudflare.ps1 -Action deploy -WithDev
```

## Configuration

### Environment Variables

Edit `.env.production` after first deploy:

```env
# Required: Cloudflare tunnel token
CLOUDFLARE_TUNNEL_TOKEN=eyJhIjoiY...

# Ethereum RPC (update for production)
ETH_RPC_URL=https://mainnet.infura.io/v3/YOUR_KEY
CHAIN_ID=1

# Contract addresses (after deployment)
AMTTP_CORE_ADDRESS=0x...
AMTTP_NFT_ADDRESS=0x...
AMTTP_ZKNAF_ADDRESS=0x...
```

### Service Ports (Internal)

| Service | Port | Purpose |
|---------|------|---------|
| nginx | 80 | Main gateway |
| Next.js | 3000 | Dashboard |
| Orchestrator | 8007 | API gateway |
| Risk Engine | 8002 | ML scoring |
| Sanctions | 8004 | Sanctions check |
| Monitoring | 8005 | Metrics |
| Geo Risk | 8006 | Geographic risk |
| Integrity | 8008 | Data verification |

## Security Features

### Cloudflare Protection
- DDoS mitigation
- WAF (Web Application Firewall)
- Bot management
- Rate limiting
- TLS termination

### Application Security
- No ports exposed directly to internet
- All traffic through encrypted Cloudflare tunnel
- MongoDB authentication enabled
- Redis in-memory only
- Non-root container user

### Recommended Cloudflare Settings

1. **Access Policies** (Zero Trust → Access → Applications):
   - Restrict `/api/admin` to authenticated users
   - Enable 2FA for admin access

2. **WAF Rules**:
   - Block known bad actors
   - Rate limit API endpoints (100 req/min)

3. **Security Headers**:
   - Strict-Transport-Security
   - Content-Security-Policy

## Health Checks

The platform exposes health endpoints:

```bash
# Overall health
curl https://amttp.yourdomain.com/health

# Individual services (internal)
docker exec amttp-platform curl http://localhost:8007/health  # Orchestrator
docker exec amttp-platform curl http://localhost:8002/health  # Risk Engine
```

## Troubleshooting

### Tunnel Not Connecting

```bash
# Check cloudflared logs
docker logs amttp-cloudflared

# Verify token
echo $CLOUDFLARE_TUNNEL_TOKEN | cut -c1-20
```

### Platform Not Healthy

```bash
# Check container logs
docker logs amttp-platform

# Check nginx
docker exec amttp-platform nginx -t
docker exec amttp-platform cat /var/log/nginx/error.log
```

### Database Connection Issues

```bash
# Test MongoDB
docker exec amttp-mongo mongosh --eval "db.adminCommand('ping')"

# Test Redis
docker exec amttp-redis redis-cli ping
```

## Scaling

For production deployments needing more capacity:

```yaml
# docker-compose.cloudflare.yml
services:
  amttp-platform:
    deploy:
      replicas: 3
      resources:
        limits:
          cpus: '2'
          memory: 4G
```

## Backup & Recovery

### Backup Data Volumes

```bash
# Backup MongoDB
docker exec amttp-mongo mongodump --archive=/backup/mongo.archive
docker cp amttp-mongo:/backup/mongo.archive ./backups/

# Backup all volumes
docker run --rm -v amttp-mongo-data:/data -v $(pwd)/backups:/backup alpine \
  tar cvzf /backup/mongo-data.tar.gz /data
```

### Restore

```bash
# Restore MongoDB
docker cp ./backups/mongo.archive amttp-mongo:/backup/
docker exec amttp-mongo mongorestore --archive=/backup/mongo.archive
```

## Support

- **Documentation**: See `/docs` folder
- **Issues**: Create issue in repository
- **Security**: Report to security@amttp.io
