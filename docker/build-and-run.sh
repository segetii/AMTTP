#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════════
# AMTTP Docker Build & Run Script (Linux/Mac)
# ═══════════════════════════════════════════════════════════════════════════════

set -e

IMAGE_NAME="amttp-platform"
CONTAINER_NAME="amttp-unified"

echo "╔══════════════════════════════════════════════════════════════════════════════╗"
echo "║                    AMTTP Platform - Docker Deployment                        ║"
echo "╚══════════════════════════════════════════════════════════════════════════════╝"

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker is not running. Please start Docker and try again."
    exit 1
fi

echo ""
echo "🔨 Building Docker image..."
docker build -t $IMAGE_NAME .

echo ""
echo "🧹 Stopping existing container if running..."
docker stop $CONTAINER_NAME 2>/dev/null || true
docker rm $CONTAINER_NAME 2>/dev/null || true

echo ""
echo "🚀 Starting AMTTP Platform..."
docker run -d \
    --name $CONTAINER_NAME \
    -p 80:80 \
    -p 3004:3004 \
    -p 8007:8007 \
    $IMAGE_NAME

echo ""
echo "⏳ Waiting for services to start..."
sleep 10

# Check health
if curl -s http://localhost/health > /dev/null; then
    echo "✅ AMTTP Platform is running!"
    echo ""
    echo "╔══════════════════════════════════════════════════════════════════════════════╗"
    echo "║                              Access URLs                                      ║"
    echo "╠══════════════════════════════════════════════════════════════════════════════╣"
    echo "║  🌐 Main App (Flutter):     http://localhost                                 ║"
    echo "║  📊 Dashboard (Next.js):    http://localhost:3004                            ║"
    echo "║  🔌 API (Orchestrator):     http://localhost:8007                            ║"
    echo "║  ❤️  Health Check:          http://localhost/health                          ║"
    echo "╚══════════════════════════════════════════════════════════════════════════════╝"
else
    echo "⚠️  Platform started but health check failed. Check logs:"
    echo "   docker logs $CONTAINER_NAME"
fi
