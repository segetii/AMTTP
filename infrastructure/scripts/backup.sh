#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════════
# AMTTP — Automated Backup Script (runs via cron on VPS)
# ═══════════════════════════════════════════════════════════════════════════════
#
# Install cron job:
#   crontab -e
#   # Daily at 3 AM UTC:
#   0 3 * * * /opt/amttp/infrastructure/scripts/backup.sh >> /var/log/amttp-backup.log 2>&1
#   # Weekly full backup Sundays at 2 AM:
#   0 2 * * 0 /opt/amttp/infrastructure/scripts/backup.sh --full >> /var/log/amttp-backup.log 2>&1
# ═══════════════════════════════════════════════════════════════════════════════

set -euo pipefail

BACKUP_DIR="/opt/amttp/backups"
RETENTION_DAYS=14
MONGO_CONTAINER=$(docker ps --filter "name=mongo" --format "{{.Names}}" | head -1)
DATE=$(date +%Y%m%d_%H%M%S)
FULL_BACKUP="${1:-}"

mkdir -p "$BACKUP_DIR/daily" "$BACKUP_DIR/weekly"

echo "[$DATE] Starting backup..."

# ── MongoDB backup ───────────────────────────────────────────────────────────

if [ -n "$MONGO_CONTAINER" ]; then
  echo "  Dumping MongoDB..."
  docker exec "$MONGO_CONTAINER" mongodump \
    --db amttp \
    --out "/tmp/mongodump_$DATE" \
    --quiet 2>&1
  
  docker cp "$MONGO_CONTAINER:/tmp/mongodump_$DATE" "/tmp/mongodump_$DATE"
  docker exec "$MONGO_CONTAINER" rm -rf "/tmp/mongodump_$DATE"
  
  if [ "$FULL_BACKUP" = "--full" ]; then
    DEST="$BACKUP_DIR/weekly/mongo_$DATE.tar.gz"
  else
    DEST="$BACKUP_DIR/daily/mongo_$DATE.tar.gz"
  fi
  
  tar -czf "$DEST" -C "/tmp" "mongodump_$DATE"
  rm -rf "/tmp/mongodump_$DATE"
  
  SIZE=$(du -h "$DEST" | cut -f1)
  echo "  MongoDB backed up: $DEST ($SIZE)"
else
  echo "  ⚠️  MongoDB container not found, skipping"
fi

# ── Docker volumes backup (weekly only) ─────────────────────────────────────

if [ "$FULL_BACKUP" = "--full" ]; then
  echo "  Backing up Docker volumes..."
  
  # Redis
  REDIS_CONTAINER=$(docker ps --filter "name=redis" --format "{{.Names}}" | head -1)
  if [ -n "$REDIS_CONTAINER" ]; then
    docker exec "$REDIS_CONTAINER" redis-cli BGSAVE 2>/dev/null || true
    sleep 2
    docker cp "$REDIS_CONTAINER:/data/dump.rdb" "$BACKUP_DIR/weekly/redis_$DATE.rdb" 2>/dev/null || echo "  ⚠️  Redis backup skipped"
  fi
  
  # MinIO data
  MINIO_VOL=$(docker volume ls --filter "name=minio" --format "{{.Name}}" | head -1)
  if [ -n "$MINIO_VOL" ]; then
    docker run --rm -v "$MINIO_VOL:/data" -v "$BACKUP_DIR/weekly:/backup" \
      alpine tar czf "/backup/minio_$DATE.tar.gz" /data 2>/dev/null || echo "  ⚠️  MinIO backup skipped"
  fi
  
  echo "  Volume backups complete"
fi

# ── .env backup ──────────────────────────────────────────────────────────────

if [ -f "/opt/amttp/.env" ]; then
  cp "/opt/amttp/.env" "$BACKUP_DIR/daily/env_$DATE.bak"
  chmod 600 "$BACKUP_DIR/daily/env_$DATE.bak"
fi

# ── Prune old backups ────────────────────────────────────────────────────────

echo "  Pruning backups older than ${RETENTION_DAYS} days..."
find "$BACKUP_DIR/daily" -type f -mtime +$RETENTION_DAYS -delete 2>/dev/null || true
find "$BACKUP_DIR/weekly" -type f -mtime +60 -delete 2>/dev/null || true

# ── Docker cleanup ───────────────────────────────────────────────────────────

echo "  Cleaning Docker (dangling images/volumes)..."
docker image prune -f --filter "until=72h" > /dev/null 2>&1 || true

# ── Summary ──────────────────────────────────────────────────────────────────

TOTAL_SIZE=$(du -sh "$BACKUP_DIR" | cut -f1)
echo "[$DATE] Backup complete. Total backup size: $TOTAL_SIZE"
