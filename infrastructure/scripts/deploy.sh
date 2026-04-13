#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════════
# AMTTP — Deploy to Contabo VPS
# ═══════════════════════════════════════════════════════════════════════════════
#
# Run from your LOCAL machine (Windows: use Git Bash or WSL):
#   bash infrastructure/scripts/deploy.sh
#
# Prerequisites:
#   - SSH key access to VPS (ssh amttp@VPS_IP works without password)
#   - VPS already provisioned with setup-vps.sh
#   - .env configured on VPS at /opt/amttp/.env
#
# What it does:
#   1. Syncs entire project to VPS via rsync
#   2. Builds images on VPS (no registry needed)
#   3. Runs database migrations
#   4. Starts/updates all services
#   5. Verifies health
# ═══════════════════════════════════════════════════════════════════════════════

set -euo pipefail

# ── Configuration ────────────────────────────────────────────────────────────

VPS_HOST="${AMTTP_VPS_HOST:-}"
VPS_USER="${AMTTP_VPS_USER:-amttp}"
VPS_DIR="/opt/amttp"
SSH_OPTS="-o StrictHostKeyChecking=accept-new -o ConnectTimeout=10"

if [ -z "$VPS_HOST" ]; then
  echo "╔══════════════════════════════════════════════════════╗"
  echo "║  AMTTP Deploy to Contabo VPS                        ║"
  echo "╚══════════════════════════════════════════════════════╝"
  echo ""
  echo "Set VPS_HOST first:"
  echo "  export AMTTP_VPS_HOST=YOUR_CONTABO_IP"
  echo "  bash infrastructure/scripts/deploy.sh"
  exit 1
fi

SSH_CMD="ssh $SSH_OPTS $VPS_USER@$VPS_HOST"
SCP_CMD="scp $SSH_OPTS"

echo "╔══════════════════════════════════════════════════════╗"
echo "║  Deploying AMTTP → $VPS_HOST"
echo "╚══════════════════════════════════════════════════════╝"

# ── 1. Test connectivity ─────────────────────────────────────────────────────

echo ""
echo "→ [1/7] Testing SSH connection..."
$SSH_CMD "echo '  Connected as \$(whoami) on \$(hostname)'"

# ── 2. Sync project files ────────────────────────────────────────────────────

echo ""
echo "→ [2/7] Syncing project to VPS (this may take a while first time)..."

# Get the repo root (script might be called from anywhere)
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

rsync -avz --progress \
  --exclude '.git' \
  --exclude 'node_modules' \
  --exclude '.next' \
  --exclude '__pycache__' \
  --exclude '*.pyc' \
  --exclude 'forge-cache' \
  --exclude 'forge-out' \
  --exclude 'cache' \
  --exclude 'coverage' \
  --exclude 'data/mongo' \
  --exclude '.env' \
  --exclude 'venv' \
  --exclude '.venv' \
  --exclude 'research' \
  --exclude 'notebooks' \
  --exclude 'screenshots' \
  --exclude 'reports/figures' \
  -e "ssh $SSH_OPTS" \
  "$REPO_ROOT/" \
  "$VPS_USER@$VPS_HOST:$VPS_DIR/"

# Copy VPS-specific compose file to root
$SSH_CMD "cp $VPS_DIR/infrastructure/contabo/docker-compose.vps.yml $VPS_DIR/docker-compose.vps.yml"

# ── 3. Build images on VPS ───────────────────────────────────────────────────

echo ""
echo "→ [3/7] Building Docker images on VPS..."
$SSH_CMD "cd $VPS_DIR && docker compose -f docker-compose.vps.yml build --parallel 2>&1 | tail -20"

# ── 4. Start/update services ─────────────────────────────────────────────────

echo ""
echo "→ [4/7] Starting services..."
$SSH_CMD "cd $VPS_DIR && docker compose -f docker-compose.vps.yml up -d 2>&1"

# ── 5. Wait for health checks ────────────────────────────────────────────────

echo ""
echo "→ [5/7] Waiting for services to become healthy (60s)..."
sleep 15
$SSH_CMD "cd $VPS_DIR && docker compose -f docker-compose.vps.yml ps --format 'table {{.Name}}\t{{.Status}}'"

echo ""
echo "  Waiting 45 more seconds for full startup..."
sleep 45

# ── 6. Verify endpoints ──────────────────────────────────────────────────────

echo ""
echo "→ [6/7] Verifying endpoints..."
$SSH_CMD bash << 'VERIFY'
  echo "  Internal checks (via localhost:8888):"
  
  # Landing page
  STATUS=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 http://127.0.0.1:8888/ 2>/dev/null || echo "000")
  echo "    Landing page:   $STATUS $([ "$STATUS" = "200" ] && echo "✅" || echo "❌")"
  
  # Flutter app
  STATUS=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 http://127.0.0.1:8888/app/ 2>/dev/null || echo "000")
  echo "    Flutter app:    $STATUS $([ "$STATUS" = "200" ] && echo "✅" || echo "❌")"
  
  # Health endpoint
  STATUS=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 http://127.0.0.1:8888/health 2>/dev/null || echo "000")
  echo "    Health:         $STATUS $([ "$STATUS" = "200" ] && echo "✅" || echo "❌")"
  
  # API stats (MongoDB)
  STATS=$(curl -s --max-time 10 http://127.0.0.1:8888/app-api/data/stats 2>/dev/null || echo "{}")
  TX_COUNT=$(echo "$STATS" | jq -r '.totalTransactions // 0' 2>/dev/null || echo "0")
  echo "    MongoDB data:   $TX_COUNT transactions $([ "$TX_COUNT" -gt 0 ] 2>/dev/null && echo "✅" || echo "⚠️  (need to seed)")"
  
  # ML Risk Engine
  STATUS=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 http://127.0.0.1:8888/ml/health 2>/dev/null || echo "000")
  echo "    ML Risk API:    $STATUS $([ "$STATUS" = "200" ] && echo "✅" || echo "❌")"
  
  # Orchestrator
  STATUS=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 http://127.0.0.1:8888/compliance/health 2>/dev/null || echo "000")
  echo "    Orchestrator:   $STATUS $([ "$STATUS" = "200" ] && echo "✅" || echo "❌")"
VERIFY

# ── 7. Show status summary ───────────────────────────────────────────────────

echo ""
echo "→ [7/7] Final status..."
$SSH_CMD "docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}' | sort"

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║  ✅ Deploy complete                                  ║"
echo "╠══════════════════════════════════════════════════════╣"
echo "║  VPS:         $VPS_HOST"
echo "║  Internal:    http://$VPS_HOST:8888"
echo "║  Public:      https://amttp.com (via Cloudflare)    ║"
echo "║                                                      ║"
echo "║  If MongoDB is empty, run:                           ║"
echo "║    bash infrastructure/scripts/migrate-data.sh       ║"
echo "╚══════════════════════════════════════════════════════╝"
