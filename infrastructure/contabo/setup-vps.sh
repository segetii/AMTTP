#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════════
# AMTTP — Contabo VPS Initial Setup
# ═══════════════════════════════════════════════════════════════════════════════
#
# Run this ONCE on a fresh Contabo Ubuntu 22.04/24.04 VPS:
#   ssh root@YOUR_VPS_IP 'bash -s' < infrastructure/contabo/setup-vps.sh
#
# What it does:
#   1. Hardens SSH (key-only, no root password)
#   2. Creates 'amttp' deploy user
#   3. Installs Docker Engine + Compose
#   4. Configures UFW firewall (only 22, 80, 443 open)
#   5. Sets kernel tuning for Docker + MongoDB
#   6. Installs Cloudflare tunnel daemon
#   7. Creates app directory structure
# ═══════════════════════════════════════════════════════════════════════════════

set -euo pipefail

echo "╔══════════════════════════════════════════════════════╗"
echo "║  AMTTP — Contabo VPS Provisioning                   ║"
echo "╚══════════════════════════════════════════════════════╝"

# ── 0. Check we're root on Ubuntu ────────────────────────────────────────────

if [ "$(id -u)" -ne 0 ]; then
  echo "❌ Must run as root"
  exit 1
fi

if ! grep -qi "ubuntu" /etc/os-release 2>/dev/null; then
  echo "⚠️  Not Ubuntu — script is written for Ubuntu 22.04/24.04"
  echo "   Proceeding anyway..."
fi

# ── 1. System update ────────────────────────────────────────────────────────

echo "→ Updating system packages..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get upgrade -y -qq

# ── 2. Create deploy user ───────────────────────────────────────────────────

DEPLOY_USER="amttp"
echo "→ Creating deploy user: $DEPLOY_USER"

if ! id "$DEPLOY_USER" &>/dev/null; then
  useradd -m -s /bin/bash -G sudo "$DEPLOY_USER"
  echo "$DEPLOY_USER ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/$DEPLOY_USER
  chmod 440 /etc/sudoers.d/$DEPLOY_USER
fi

# Copy root's authorized_keys to deploy user
mkdir -p /home/$DEPLOY_USER/.ssh
cp /root/.ssh/authorized_keys /home/$DEPLOY_USER/.ssh/ 2>/dev/null || true
chown -R $DEPLOY_USER:$DEPLOY_USER /home/$DEPLOY_USER/.ssh
chmod 700 /home/$DEPLOY_USER/.ssh
chmod 600 /home/$DEPLOY_USER/.ssh/authorized_keys 2>/dev/null || true

# ── 3. Harden SSH ───────────────────────────────────────────────────────────

echo "→ Hardening SSH..."
sed -i 's/^#\?PermitRootLogin.*/PermitRootLogin prohibit-password/' /etc/ssh/sshd_config
sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
sed -i 's/^#\?PubkeyAuthentication.*/PubkeyAuthentication yes/' /etc/ssh/sshd_config
sed -i 's/^#\?MaxAuthTries.*/MaxAuthTries 3/' /etc/ssh/sshd_config
systemctl restart sshd

# ── 4. Install Docker ───────────────────────────────────────────────────────

echo "→ Installing Docker Engine..."
if ! command -v docker &>/dev/null; then
  apt-get install -y -qq ca-certificates curl gnupg lsb-release

  # Docker GPG key
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
    | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  chmod a+r /etc/apt/keyrings/docker.gpg

  # Docker repo
  echo \
    "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
    https://download.docker.com/linux/ubuntu \
    $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
    | tee /etc/apt/sources.list.d/docker.list > /dev/null

  apt-get update -qq
  apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi

# Add deploy user to docker group
usermod -aG docker $DEPLOY_USER

# ── 5. Firewall (UFW) ───────────────────────────────────────────────────────

echo "→ Configuring firewall..."
apt-get install -y -qq ufw

ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp comment 'SSH'
# No 80/443 needed — Cloudflare tunnel runs outbound only
# But allow them in case you need direct access for debugging
ufw allow 80/tcp comment 'HTTP (debug only)'
ufw allow 443/tcp comment 'HTTPS (debug only)'
ufw --force enable

# ── 6. Kernel tuning for Docker + MongoDB ────────────────────────────────────

echo "→ Applying kernel tuning..."
cat > /etc/sysctl.d/99-amttp.conf << 'SYSCTL'
# MongoDB performance
vm.swappiness = 1
vm.dirty_ratio = 15
vm.dirty_background_ratio = 5
net.core.somaxconn = 65535
net.ipv4.tcp_max_syn_backlog = 65535

# Docker networking
net.bridge.bridge-nf-call-iptables = 1
net.bridge.bridge-nf-call-ip6tables = 1
net.ipv4.ip_forward = 1

# File descriptors
fs.file-max = 2097152
fs.inotify.max_user_watches = 524288
SYSCTL
sysctl --system > /dev/null 2>&1

# Increase open file limit for docker
mkdir -p /etc/systemd/system/docker.service.d
cat > /etc/systemd/system/docker.service.d/limits.conf << 'LIMITS'
[Service]
LimitNOFILE=1048576
LimitNPROC=65536
LIMITS
systemctl daemon-reload
systemctl restart docker

# ── 7. Install additional tools ──────────────────────────────────────────────

echo "→ Installing utilities..."
apt-get install -y -qq \
  htop \
  ncdu \
  jq \
  unzip \
  fail2ban \
  logrotate

# Configure fail2ban
cat > /etc/fail2ban/jail.local << 'F2B'
[sshd]
enabled = true
port = ssh
filter = sshd
logpath = /var/log/auth.log
maxretry = 3
bantime = 3600
findtime = 600
F2B
systemctl enable --now fail2ban

# ── 8. Create app directory structure ────────────────────────────────────────

echo "→ Creating AMTTP directory structure..."
APP_DIR="/opt/amttp"
mkdir -p $APP_DIR/{data,backups,logs,secrets}
chown -R $DEPLOY_USER:$DEPLOY_USER $APP_DIR

# Create .env template
cat > $APP_DIR/.env << 'ENVFILE'
# ═══════════════════════════════════════════════════════════
# AMTTP Production Environment — Contabo VPS
# ═══════════════════════════════════════════════════════════
# CHANGE THESE BEFORE FIRST DEPLOY

MONGO_PASSWORD=CHANGE_ME_STRONG_PASSWORD_HERE
REDIS_PASSWORD=CHANGE_ME_STRONG_PASSWORD_HERE
MINIO_ACCESS_KEY=CHANGE_ME_ACCESS_KEY
MINIO_SECRET_KEY=CHANGE_ME_SECRET_KEY
GRAFANA_PASSWORD=CHANGE_ME_GRAFANA_PASS

# Cloudflare tunnel token (from Zero Trust dashboard)
CLOUDFLARE_TUNNEL_TOKEN=

# Domain
DOMAIN=amttp.com
ENVFILE
chmod 600 $APP_DIR/.env
chown $DEPLOY_USER:$DEPLOY_USER $APP_DIR/.env

# ── 9. Docker log rotation ──────────────────────────────────────────────────

echo "→ Configuring Docker log rotation..."
cat > /etc/docker/daemon.json << 'DOCKER_JSON'
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  },
  "storage-driver": "overlay2",
  "live-restore": true,
  "default-ulimits": {
    "nofile": {
      "Name": "nofile",
      "Hard": 65536,
      "Soft": 65536
    }
  }
}
DOCKER_JSON
systemctl restart docker

# ── 10. Swap file (Contabo VPS L has 48GB RAM, but good to have for MongoDB) ─

echo "→ Creating swap file..."
if [ ! -f /swapfile ]; then
  fallocate -l 4G /swapfile
  chmod 600 /swapfile
  mkswap /swapfile
  swapon /swapfile
  echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

# ── Done ─────────────────────────────────────────────────────────────────────

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║  ✅ VPS Setup Complete                              ║"
echo "╠══════════════════════════════════════════════════════╣"
echo "║  Deploy user: amttp                                 ║"
echo "║  App dir:     /opt/amttp                            ║"
echo "║  SSH:         ssh amttp@$(hostname -I | awk '{print $1}')  ║"
echo "║                                                      ║"
echo "║  ⚠️  NEXT STEPS:                                     ║"
echo "║  1. Edit /opt/amttp/.env with real passwords         ║"
echo "║  2. Run deploy.sh from your local machine            ║"
echo "╚══════════════════════════════════════════════════════╝"
