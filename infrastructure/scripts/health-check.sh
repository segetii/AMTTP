#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════════
# AMTTP — Health Monitor (runs via cron, sends alerts)
# ═══════════════════════════════════════════════════════════════════════════════
#
# Install cron job:
#   crontab -e
#   # Check every 5 minutes:
#   */5 * * * * /opt/amttp/infrastructure/scripts/health-check.sh >> /var/log/amttp-health.log 2>&1
#
# Optional: Set AMTTP_WEBHOOK_URL for Discord/Slack alerts
# ═══════════════════════════════════════════════════════════════════════════════

set -euo pipefail

WEBHOOK_URL="${AMTTP_WEBHOOK_URL:-}"
ALERT_FILE="/tmp/amttp-last-alert"
ALERT_COOLDOWN=1800  # 30 minutes between repeated alerts
DATE=$(date '+%Y-%m-%d %H:%M:%S')

ERRORS=()

# ── Check critical services ──────────────────────────────────────────────────

check_endpoint() {
  local name="$1"
  local url="$2"
  local expected="${3:-200}"
  
  STATUS=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "$url" 2>/dev/null || echo "000")
  if [ "$STATUS" != "$expected" ]; then
    ERRORS+=("$name: HTTP $STATUS (expected $expected)")
    return 1
  fi
  return 0
}

# Check internal endpoints (nginx → services)
check_endpoint "Landing Page" "http://127.0.0.1:8888/"
check_endpoint "Health" "http://127.0.0.1:8888/health"
check_endpoint "ML Risk API" "http://127.0.0.1:8888/ml/health"
check_endpoint "Orchestrator" "http://127.0.0.1:8888/compliance/health"

# Check public endpoint (through Cloudflare)
check_endpoint "Cloudflare (amttp.com)" "https://amttp.com/" || true

# ── Check Docker containers ──────────────────────────────────────────────────

UNHEALTHY=$(docker ps --filter "health=unhealthy" --format "{{.Names}}" 2>/dev/null || echo "")
if [ -n "$UNHEALTHY" ]; then
  for c in $UNHEALTHY; do
    ERRORS+=("Container unhealthy: $c")
  done
fi

EXITED=$(docker ps -a --filter "status=exited" --format "{{.Names}}: exited {{.Status}}" 2>/dev/null | grep -v "setup\|init\|migration" || echo "")
if [ -n "$EXITED" ]; then
  while IFS= read -r line; do
    ERRORS+=("Container stopped: $line")
  done <<< "$EXITED"
fi

# ── Check disk space ─────────────────────────────────────────────────────────

DISK_USED=$(df / | tail -1 | awk '{print $5}' | tr -d '%')
if [ "$DISK_USED" -gt 85 ]; then
  ERRORS+=("Disk usage: ${DISK_USED}% (threshold: 85%)")
fi

# ── Check memory ─────────────────────────────────────────────────────────────

MEM_USED=$(free | awk '/Mem:/ {printf "%.0f", $3/$2 * 100}')
if [ "$MEM_USED" -gt 90 ]; then
  ERRORS+=("Memory usage: ${MEM_USED}% (threshold: 90%)")
fi

# ── Report ───────────────────────────────────────────────────────────────────

if [ ${#ERRORS[@]} -eq 0 ]; then
  echo "[$DATE] ✅ All systems healthy"
  # Clear alert cooldown on recovery
  rm -f "$ALERT_FILE"
  exit 0
fi

# Errors found
echo "[$DATE] ❌ ${#ERRORS[@]} issue(s) detected:"
for err in "${ERRORS[@]}"; do
  echo "  - $err"
done

# ── Send alert (with cooldown) ───────────────────────────────────────────────

send_alert() {
  # Check cooldown
  if [ -f "$ALERT_FILE" ]; then
    LAST_ALERT=$(cat "$ALERT_FILE")
    NOW=$(date +%s)
    ELAPSED=$((NOW - LAST_ALERT))
    if [ "$ELAPSED" -lt "$ALERT_COOLDOWN" ]; then
      echo "  (Alert suppressed — cooldown ${ELAPSED}s/${ALERT_COOLDOWN}s)"
      return
    fi
  fi
  
  date +%s > "$ALERT_FILE"
  
  if [ -n "$WEBHOOK_URL" ]; then
    ERROR_TEXT=$(printf '• %s\\n' "${ERRORS[@]}")
    PAYLOAD=$(jq -n \
      --arg title "🚨 AMTTP Health Alert" \
      --arg desc "$ERROR_TEXT" \
      --arg ts "$DATE" \
      '{content: ("**" + $title + "** (" + $ts + ")\n" + $desc)}')
    
    curl -s -X POST -H "Content-Type: application/json" \
      -d "$PAYLOAD" "$WEBHOOK_URL" > /dev/null 2>&1 || echo "  ⚠️  Webhook delivery failed"
    
    echo "  Alert sent to webhook"
  else
    echo "  (No AMTTP_WEBHOOK_URL set — logging only)"
  fi
}

send_alert

# ── Auto-restart crashed containers ─────────────────────────────────────────

if [ -n "$EXITED" ]; then
  echo "  Attempting auto-restart of stopped containers..."
  cd /opt/amttp
  docker compose -f docker-compose.vps.yml up -d 2>&1
  echo "  Auto-restart triggered"
fi
