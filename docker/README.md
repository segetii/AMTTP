# 🐳 AMTTP Platform - Docker Deployment

## Overview

Deploy the entire AMTTP platform as a **single container** containing:

| Service | Port | Description |
|---------|------|-------------|
| **Flutter Web App** | 80 | Main application interface |
| **Next.js Dashboard** | 3004 | ML Detection Studio & Analytics |
| **Orchestrator API** | 8007 | Main compliance API |
| **Sanctions Service** | 8004 | OFAC/UN sanctions screening |
| **Monitoring Service** | 8005 | Transaction monitoring rules |
| **Geo-Risk Service** | 8006 | FATF country risk assessment |

## Quick Start

### Windows (PowerShell)
```powershell
cd c:\amttp
.\docker\build-and-run.ps1
```

### Linux/Mac
```bash
cd /path/to/amttp
chmod +x docker/build-and-run.sh
./docker/build-and-run.sh
```

### Manual Build & Run
```bash
# Build the image
docker build -t amttp-platform .

# Run the container
docker run -d \
  --name amttp-unified \
  -p 80:80 \
  -p 3004:3004 \
  -p 8007:8007 \
  amttp-platform

# Check health
curl http://localhost/health
```

## Access URLs

| Service | URL |
|---------|-----|
| Main App | http://localhost |
| Dashboard | http://localhost:3004 |
| API Docs | http://localhost:8007/docs |
| Health | http://localhost/health |

## Docker Compose (with external services)

If you need MongoDB, Redis, etc.:

```bash
docker-compose -f docker-compose.unified.yml up --build
```

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Docker Container                              │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │                    NGINX (Port 80)                          │ │
│  │                   Reverse Proxy                             │ │
│  └────────┬──────────────┬──────────────┬────────────────────┘ │
│           │              │              │                       │
│  ┌────────▼────────┐ ┌───▼───┐ ┌───────▼────────────────────┐ │
│  │  Flutter Web    │ │ /api  │ │      Next.js (3004)        │ │
│  │  Static Files   │ │ /risk │ │      Dashboard             │ │
│  │  /var/www/flutter│ │ /geo  │ └────────────────────────────┘ │
│  └─────────────────┘ └───┬───┘                                 │
│                          │                                      │
│  ┌───────────────────────▼──────────────────────────────────┐  │
│  │                 Python Backend Services                    │  │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐     │  │
│  │  │Orchestrator│ │Sanctions │ │Monitoring│ │ Geo-Risk │     │  │
│  │  │  :8007   │ │  :8004   │ │  :8005   │ │  :8006   │     │  │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘     │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

## Management Commands

```bash
# View logs
docker logs -f amttp-unified

# Enter container
docker exec -it amttp-unified sh

# Check service status
docker exec amttp-unified supervisorctl status

# Restart a specific service
docker exec amttp-unified supervisorctl restart nextjs

# Stop container
docker stop amttp-unified

# Remove container
docker rm amttp-unified
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MONGODB_URL` | `mongodb://localhost:27017` | MongoDB connection string |
| `REDIS_URL` | `redis://localhost:6379` | Redis connection string |
| `NODE_ENV` | `production` | Node environment |

## Cloud Deployment

### Deploy to fly.io
```bash
fly launch
fly deploy
```

### Deploy to Railway
```bash
railway login
railway init
railway up
```

### Deploy to Render
Connect your GitHub repo and select the Dockerfile.

### Deploy to AWS ECS/Fargate
```bash
# Build and push to ECR
aws ecr get-login-password | docker login --username AWS --password-stdin <account>.dkr.ecr.<region>.amazonaws.com
docker tag amttp-platform:latest <account>.dkr.ecr.<region>.amazonaws.com/amttp-platform:latest
docker push <account>.dkr.ecr.<region>.amazonaws.com/amttp-platform:latest
```

## Troubleshooting

### Build Fails
```bash
# Clean Docker cache
docker system prune -a

# Build with no cache
docker build --no-cache -t amttp-platform .
```

### Services Not Starting
```bash
# Check supervisor logs
docker exec amttp-unified cat /var/log/supervisor/supervisord.log

# Check individual service logs
docker exec amttp-unified cat /var/log/supervisor/nextjs-stderr.log
```

### Port Conflicts
```bash
# Check what's using ports
netstat -ano | findstr "80"    # Windows
lsof -i :80                    # Linux/Mac
```

## Resource Requirements

| Resource | Minimum | Recommended |
|----------|---------|-------------|
| CPU | 2 cores | 4 cores |
| RAM | 2 GB | 4 GB |
| Disk | 5 GB | 10 GB |

## Security Notes

- The container runs NGINX as a reverse proxy
- All backend APIs are only accessible through NGINX
- CORS is configured for cross-origin requests
- For production, add SSL/TLS termination (use a load balancer or nginx-proxy)
