#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════════
# AMTTP — Cloudflare Tunnel Setup for Contabo VPS
# ═══════════════════════════════════════════════════════════════════════════════
#
# Run on your LOCAL machine (NOT on VPS).
# Requires: cloudflared CLI installed locally.
#
# This script:
#   1. Creates a new Cloudflare tunnel (or reconfigures existing)
#   2. Generates the TUNNEL_TOKEN for use in docker-compose.vps.yml
#   3. Configures DNS routes for amttp.com and www.amttp.com
# ═══════════════════════════════════════════════════════════════════════════════

set -euo pipefail

TUNNEL_NAME="${1:-amttp-vps}"

echo "╔══════════════════════════════════════════════════════╗"
echo "║  AMTTP — Cloudflare Tunnel Setup                    ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""

# ── Check cloudflared is installed and authenticated ─────────────────────────

if ! command -v cloudflared &> /dev/null; then
  echo "❌ cloudflared CLI not found."
  echo "   Install: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/"
  exit 1
fi

echo "→ Checking Cloudflare authentication..."
if ! cloudflared tunnel list &> /dev/null; then
  echo "  Not authenticated. Running login..."
  cloudflared tunnel login
fi

# ── Create or find tunnel ────────────────────────────────────────────────────

echo ""
echo "→ Looking for existing tunnel '$TUNNEL_NAME'..."
EXISTING=$(cloudflared tunnel list --output json 2>/dev/null | jq -r ".[] | select(.name==\"$TUNNEL_NAME\") | .id" 2>/dev/null || echo "")

if [ -n "$EXISTING" ]; then
  TUNNEL_ID="$EXISTING"
  echo "  Found existing tunnel: $TUNNEL_ID"
else
  echo "  Creating new tunnel..."
  cloudflared tunnel create "$TUNNEL_NAME"
  TUNNEL_ID=$(cloudflared tunnel list --output json | jq -r ".[] | select(.name==\"$TUNNEL_NAME\") | .id")
  echo "  Created tunnel: $TUNNEL_ID"
fi

# ── Get tunnel token ─────────────────────────────────────────────────────────

echo ""
echo "→ Generating tunnel token..."
TUNNEL_TOKEN=$(cloudflared tunnel token "$TUNNEL_NAME" 2>/dev/null)
echo "  Token generated (${#TUNNEL_TOKEN} chars)"

# ── Configure DNS ────────────────────────────────────────────────────────────

echo ""
echo "→ Configuring DNS routes..."

# Route amttp.com → tunnel
echo "  Routing amttp.com → tunnel $TUNNEL_ID"
cloudflared tunnel route dns "$TUNNEL_NAME" amttp.com 2>/dev/null || echo "  (DNS record may already exist — check Cloudflare dashboard)"

# Route www.amttp.com → tunnel  
echo "  Routing www.amttp.com → tunnel $TUNNEL_ID"
cloudflared tunnel route dns "$TUNNEL_NAME" www.amttp.com 2>/dev/null || echo "  (DNS record may already exist — check Cloudflare dashboard)"

# ── Configure tunnel ingress ─────────────────────────────────────────────────

echo ""
echo "→ Writing tunnel config..."

# The tunnel config for the VPS — cloudflared runs in Docker and connects
# to nginx-gateway on the same Docker network
TUNNEL_CONFIG="tunnel: $TUNNEL_ID
credentials-file: /etc/cloudflared/credentials.json

ingress:
  - hostname: amttp.com
    service: http://nginx-gateway:80
  - hostname: www.amttp.com
    service: http://nginx-gateway:80
  - service: http_status:404"

echo "$TUNNEL_CONFIG"

# ── Output instructions ──────────────────────────────────────────────────────

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║  ✅ Tunnel Setup Complete                            ║"
echo "╠══════════════════════════════════════════════════════╣"
echo "║                                                      ║"
echo "║  Tunnel ID:    $TUNNEL_ID"
echo "║  Tunnel Name:  $TUNNEL_NAME"
echo "║                                                      ║"
echo "║  NEXT STEPS:                                         ║"
echo "║                                                      ║"
echo "║  1. Add the tunnel token to your VPS .env file:      ║"
echo "║     ssh amttp@YOUR_VPS_IP                            ║"
echo "║     nano /opt/amttp/.env                             ║"
echo "║                                                      ║"
echo "║  2. Set this value:                                  ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""
echo "CLOUDFLARE_TUNNEL_TOKEN=$TUNNEL_TOKEN"
echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║  3. Then deploy:                                     ║"
echo "║     export AMTTP_VPS_HOST=YOUR_IP                    ║"
echo "║     bash infrastructure/scripts/deploy.sh            ║"
echo "║                                                      ║"
echo "║  The tunnel token method is simpler than credential  ║"
echo "║  files — cloudflared in Docker uses the token to     ║"
echo "║  authenticate directly with Cloudflare.              ║"
echo "╚══════════════════════════════════════════════════════╝"
