import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('194.35.120.52', username='root', password='DZc3n0IetkN6BQKwn35EPO8gm57S', timeout=10)

env_content = """# AMTTP Production — Contabo VPS

# MongoDB
MONGO_PASSWORD=AmTTp_M0ng0_2026_Pr0d

# Redis
REDIS_PASSWORD=AmTTp_R3d1s_2026_Pr0d

# MinIO
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=AmTTp_M1n10_2026_Pr0d

# Grafana
GRAFANA_PASSWORD=AmTTp_Gr4f_2026

# Cloudflare tunnel token (set this after creating tunnel)
CLOUDFLARE_TUNNEL_TOKEN=placeholder

# Domain
DOMAIN=amttp.com
"""

_, stdout, stderr = ssh.exec_command(f"cat > /opt/amttp/.env << 'ENVEOF'\n{env_content}\nENVOF")
stdout.read()
_, stdout, _ = ssh.exec_command("chmod 600 /opt/amttp/.env; chown amttp:amttp /opt/amttp/.env; cat /opt/amttp/.env | grep -v '^$' | grep -v '^#'")
print(stdout.read().decode())
ssh.close()
