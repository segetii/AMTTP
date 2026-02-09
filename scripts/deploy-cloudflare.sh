#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════════
# AMTTP Platform Deployment Script for Linux/macOS
# ═══════════════════════════════════════════════════════════════════════════════
#
# Deploy the AMTTP platform with Cloudflare Tunnel for secure public access.
#
# Usage:
#   ./deploy-cloudflare.sh deploy --token <CLOUDFLARE_TUNNEL_TOKEN>
#   ./deploy-cloudflare.sh start
#   ./deploy-cloudflare.sh stop
#   ./deploy-cloudflare.sh status
#   ./deploy-cloudflare.sh logs
#   ./deploy-cloudflare.sh clean
#
# ═══════════════════════════════════════════════════════════════════════════════

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
COMPOSE_FILE="$PROJECT_ROOT/docker-compose.cloudflare.yml"
ENV_FILE="$PROJECT_ROOT/.env.production"

# ═══════════════════════════════════════════════════════════════════════════════
# Helper Functions
# ═══════════════════════════════════════════════════════════════════════════════

header() {
    echo ""
    echo -e "${CYAN}═══════════════════════════════════════════════════════════════════${NC}"
    echo -e "${CYAN} $1${NC}"
    echo -e "${CYAN}═══════════════════════════════════════════════════════════════════${NC}"
    echo ""
}

step() {
    echo -e "${GREEN}→ $1${NC}"
}

warn() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

error() {
    echo -e "${RED}✗ $1${NC}"
}

check_docker() {
    if ! docker info > /dev/null 2>&1; then
        error "Docker is not running. Please start Docker."
        exit 1
    fi
}

check_compose() {
    if ! docker compose version > /dev/null 2>&1; then
        error "Docker Compose is not available."
        exit 1
    fi
}

generate_password() {
    openssl rand -hex 8
}

create_env_file() {
    step "Creating production environment file..."
    
    local mongo_pwd=$(generate_password)
    local memgraph_pwd=$(generate_password)
    local minio_pwd=$(generate_password)
    
    cat > "$ENV_FILE" << EOF
# ═══════════════════════════════════════════════════════════════════════════════
# AMTTP Production Environment Configuration
# Generated: $(date '+%Y-%m-%d %H:%M:%S')
# ═══════════════════════════════════════════════════════════════════════════════

# Cloudflare Tunnel
CLOUDFLARE_TUNNEL_TOKEN=${TUNNEL_TOKEN}

# MongoDB
MONGO_ROOT_USER=admin
MONGO_ROOT_PASSWORD=${mongo_pwd}
MONGODB_URI=mongodb://admin:${mongo_pwd}@mongo:27017/amttp?authSource=admin

# Redis
REDIS_URL=redis://redis:6379

# Memgraph
MEMGRAPH_PASSWORD=${memgraph_pwd}

# MinIO
MINIO_ROOT_USER=amttp_admin
MINIO_ROOT_PASSWORD=${minio_pwd}

# Ethereum (Update with your RPC endpoint)
ETH_RPC_URL=https://sepolia.infura.io/v3/YOUR_INFURA_KEY
CHAIN_ID=11155111

# Contract Addresses (Update after deployment)
AMTTP_CORE_ADDRESS=
AMTTP_NFT_ADDRESS=
AMTTP_ZKNAF_ADDRESS=

# Application
NODE_ENV=production
LOG_LEVEL=info
EOF
    
    chmod 600 "$ENV_FILE"
    step "Environment file created at: $ENV_FILE"
    warn "Please update ETH_RPC_URL and contract addresses in $ENV_FILE"
}

# ═══════════════════════════════════════════════════════════════════════════════
# Main Actions
# ═══════════════════════════════════════════════════════════════════════════════

do_build() {
    header "Building AMTTP Platform"
    check_docker
    check_compose
    
    step "Building Docker images..."
    docker compose -f "$COMPOSE_FILE" build --no-cache
    
    step "Build complete!"
}

do_deploy() {
    header "Deploying AMTTP Platform with Cloudflare Tunnel"
    check_docker
    check_compose
    
    # Check tunnel token
    if [ -z "$TUNNEL_TOKEN" ]; then
        error "Cloudflare Tunnel token is required."
        echo ""
        echo -e "${YELLOW}To get a tunnel token:${NC}"
        echo -e "${YELLOW}  1. Go to https://one.dash.cloudflare.com${NC}"
        echo -e "${YELLOW}  2. Navigate to: Zero Trust → Networks → Tunnels${NC}"
        echo -e "${YELLOW}  3. Create a new tunnel or use existing one${NC}"
        echo -e "${YELLOW}  4. Copy the tunnel token${NC}"
        echo ""
        echo -e "${CYAN}Then run:${NC}"
        echo -e "${CYAN}  ./deploy-cloudflare.sh deploy --token 'your-token-here'${NC}"
        exit 1
    fi
    
    # Create env file if not exists
    if [ ! -f "$ENV_FILE" ]; then
        create_env_file
    else
        # Update tunnel token
        sed -i.bak "s/^CLOUDFLARE_TUNNEL_TOKEN=.*/CLOUDFLARE_TUNNEL_TOKEN=${TUNNEL_TOKEN}/" "$ENV_FILE"
        rm -f "${ENV_FILE}.bak"
    fi
    
    step "Building Docker images..."
    docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" build
    
    step "Starting services..."
    local profiles=""
    if [ "$WITH_DEV" = "true" ]; then
        profiles="--profile dev"
    fi
    
    docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" $profiles up -d
    
    step "Waiting for services to be healthy..."
    sleep 10
    
    do_status
    
    header "Deployment Complete!"
    echo -e "${GREEN}Your AMTTP platform is now accessible via Cloudflare Tunnel.${NC}"
    echo ""
    echo -e "${YELLOW}Configure your Cloudflare Tunnel public hostname to point to this container.${NC}"
    echo -e "${YELLOW}The tunnel will route traffic to the internal nginx on port 80.${NC}"
}

do_start() {
    header "Starting AMTTP Platform"
    check_docker
    
    if [ ! -f "$ENV_FILE" ]; then
        error "Environment file not found. Run 'deploy' first."
        exit 1
    fi
    
    local profiles=""
    if [ "$WITH_DEV" = "true" ]; then
        profiles="--profile dev"
    fi
    
    docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" $profiles up -d
    
    step "Services starting..."
    sleep 5
    do_status
}

do_stop() {
    header "Stopping AMTTP Platform"
    
    docker compose -f "$COMPOSE_FILE" down
    
    step "All services stopped."
}

do_status() {
    header "AMTTP Platform Status"
    
    docker compose -f "$COMPOSE_FILE" ps -a
    
    echo ""
    step "Checking health endpoints..."
    
    if docker exec amttp-platform curl -sf http://localhost/health > /dev/null 2>&1; then
        echo -e "  Platform Health: ${GREEN}HEALTHY${NC}"
    else
        echo -e "  Platform Health: ${YELLOW}STARTING...${NC}"
    fi
}

do_logs() {
    header "AMTTP Platform Logs"
    
    docker compose -f "$COMPOSE_FILE" logs --tail="${LOG_TAIL:-100}" -f
}

do_clean() {
    header "Cleaning AMTTP Platform"
    
    warn "This will remove all containers, volumes, and images!"
    read -p "Are you sure? (yes/no): " confirm
    
    if [ "$confirm" = "yes" ]; then
        step "Stopping containers..."
        docker compose -f "$COMPOSE_FILE" down -v --rmi all
        
        step "Pruning Docker resources..."
        docker system prune -f
        
        step "Cleanup complete."
    else
        step "Cleanup cancelled."
    fi
}

# ═══════════════════════════════════════════════════════════════════════════════
# Argument Parsing
# ═══════════════════════════════════════════════════════════════════════════════

ACTION=""
TUNNEL_TOKEN="${CLOUDFLARE_TUNNEL_TOKEN:-}"
WITH_DEV="false"
LOG_TAIL="100"

while [[ $# -gt 0 ]]; do
    case $1 in
        deploy|build|start|stop|status|logs|clean)
            ACTION="$1"
            shift
            ;;
        --token|-t)
            TUNNEL_TOKEN="$2"
            shift 2
            ;;
        --with-dev)
            WITH_DEV="true"
            shift
            ;;
        --tail)
            LOG_TAIL="$2"
            shift 2
            ;;
        --help|-h)
            echo "Usage: $0 <action> [options]"
            echo ""
            echo "Actions:"
            echo "  deploy    Build and start the platform"
            echo "  build     Build Docker images only"
            echo "  start     Start existing containers"
            echo "  stop      Stop all containers"
            echo "  status    Show container status"
            echo "  logs      Stream container logs"
            echo "  clean     Remove all containers and volumes"
            echo ""
            echo "Options:"
            echo "  --token, -t    Cloudflare Tunnel token"
            echo "  --with-dev     Include development services (Hardhat)"
            echo "  --tail N       Number of log lines (default: 100)"
            exit 0
            ;;
        *)
            error "Unknown option: $1"
            exit 1
            ;;
    esac
done

# ═══════════════════════════════════════════════════════════════════════════════
# Main Entry Point
# ═══════════════════════════════════════════════════════════════════════════════

echo ""
echo -e "${MAGENTA}╔═══════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${MAGENTA}║           AMTTP Platform - Cloudflare Deployment                  ║${NC}"
echo -e "${MAGENTA}╚═══════════════════════════════════════════════════════════════════╝${NC}"

case "$ACTION" in
    build)  do_build ;;
    deploy) do_deploy ;;
    start)  do_start ;;
    stop)   do_stop ;;
    status) do_status ;;
    logs)   do_logs ;;
    clean)  do_clean ;;
    *)
        error "No action specified. Use --help for usage."
        exit 1
        ;;
esac

echo ""
