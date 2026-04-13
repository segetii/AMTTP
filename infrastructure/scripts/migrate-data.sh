#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════════
# AMTTP — Migrate MongoDB Data to VPS
# ═══════════════════════════════════════════════════════════════════════════════
#
# Run from your LOCAL machine (Windows: use Git Bash or WSL):
#   bash infrastructure/scripts/migrate-data.sh
#
# What it does:
#   1. Dumps MongoDB from local Docker container
#   2. Compresses the dump
#   3. Transfers to VPS via scp
#   4. Restores into VPS MongoDB container
# ═══════════════════════════════════════════════════════════════════════════════

set -euo pipefail

VPS_HOST="${AMTTP_VPS_HOST:-}"
VPS_USER="${AMTTP_VPS_USER:-amttp}"
VPS_DIR="/opt/amttp"
SSH_OPTS="-o StrictHostKeyChecking=accept-new -o ConnectTimeout=10"
LOCAL_DUMP_DIR="/tmp/amttp-mongodump"
MONGO_DB="amttp"

if [ -z "$VPS_HOST" ]; then
  echo "Set VPS_HOST first:  export AMTTP_VPS_HOST=YOUR_CONTABO_IP"
  exit 1
fi

SSH_CMD="ssh $SSH_OPTS $VPS_USER@$VPS_HOST"
SCP_CMD="scp $SSH_OPTS"

echo "╔══════════════════════════════════════════════════════╗"
echo "║  AMTTP — MongoDB Data Migration                     ║"
echo "╚══════════════════════════════════════════════════════╝"

# ── 1. Dump from local MongoDB ───────────────────────────────────────────────

echo ""
echo "→ [1/5] Dumping local MongoDB ($MONGO_DB database)..."
rm -rf "$LOCAL_DUMP_DIR"
mkdir -p "$LOCAL_DUMP_DIR"

# Find the local mongo container
LOCAL_MONGO=$(docker ps --filter "name=mongo" --format "{{.Names}}" | head -1)
if [ -z "$LOCAL_MONGO" ]; then
  echo "  ❌ No local MongoDB container found. Is it running?"
  echo "     Try: docker compose -f docker-compose.production.yml up -d mongo"
  exit 1
fi

echo "  Found container: $LOCAL_MONGO"

# Run mongodump inside the container and copy out
docker exec "$LOCAL_MONGO" mongodump \
  --db "$MONGO_DB" \
  --out /tmp/mongodump \
  --quiet 2>&1

docker cp "$LOCAL_MONGO:/tmp/mongodump/$MONGO_DB" "$LOCAL_DUMP_DIR/$MONGO_DB"
docker exec "$LOCAL_MONGO" rm -rf /tmp/mongodump

COLLECTIONS=$(ls "$LOCAL_DUMP_DIR/$MONGO_DB"/*.bson 2>/dev/null | wc -l)
echo "  Dumped $COLLECTIONS collections"

# Show collection sizes
for bson in "$LOCAL_DUMP_DIR/$MONGO_DB"/*.bson; do
  CNAME=$(basename "$bson" .bson)
  SIZE=$(du -h "$bson" | cut -f1)
  echo "    $CNAME: $SIZE"
done

# ── 2. Compress ──────────────────────────────────────────────────────────────

echo ""
echo "→ [2/5] Compressing dump..."
ARCHIVE="/tmp/amttp-mongodump.tar.gz"
tar -czf "$ARCHIVE" -C "$LOCAL_DUMP_DIR" "$MONGO_DB"
ARCHIVE_SIZE=$(du -h "$ARCHIVE" | cut -f1)
echo "  Archive: $ARCHIVE ($ARCHIVE_SIZE)"

# ── 3. Transfer to VPS ──────────────────────────────────────────────────────

echo ""
echo "→ [3/5] Uploading to VPS..."
$SCP_CMD "$ARCHIVE" "$VPS_USER@$VPS_HOST:/tmp/amttp-mongodump.tar.gz"
echo "  Uploaded ✅"

# ── 4. Restore on VPS ────────────────────────────────────────────────────────

echo ""
echo "→ [4/5] Restoring on VPS..."
$SSH_CMD bash << 'RESTORE'
  cd /tmp
  tar -xzf amttp-mongodump.tar.gz
  
  # Find the VPS mongo container
  VPS_MONGO=$(docker ps --filter "name=mongo" --format "{{.Names}}" | head -1)
  if [ -z "$VPS_MONGO" ]; then
    echo "  ❌ MongoDB container not running on VPS"
    exit 1
  fi
  
  echo "  Restoring into container: $VPS_MONGO"
  
  # Copy dump into container
  docker cp /tmp/amttp "$VPS_MONGO:/tmp/amttp"
  
  # Restore with --drop (replace existing data)
  docker exec "$VPS_MONGO" mongorestore \
    --db amttp \
    --drop \
    /tmp/amttp \
    2>&1
  
  # Cleanup
  docker exec "$VPS_MONGO" rm -rf /tmp/amttp
  rm -rf /tmp/amttp /tmp/amttp-mongodump.tar.gz
  
  # Verify
  echo ""
  echo "  Verifying data..."
  docker exec "$VPS_MONGO" mongosh --quiet --eval '
    const db = db.getSiblingDB("amttp");
    const collections = db.getCollectionNames();
    collections.forEach(c => {
      const count = db[c].countDocuments();
      print("    " + c + ": " + count.toLocaleString() + " documents");
    });
  '
RESTORE

# ── 5. Cleanup local temp ────────────────────────────────────────────────────

echo ""
echo "→ [5/5] Cleaning up local temp files..."
rm -rf "$LOCAL_DUMP_DIR" "$ARCHIVE"

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║  ✅ MongoDB migration complete                       ║"
echo "║     920K+ transactions should now be on VPS          ║"
echo "╚══════════════════════════════════════════════════════╝"
