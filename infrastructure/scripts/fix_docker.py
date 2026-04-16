import paramiko, json

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('194.35.120.52', username='root', password='DZc3n0IetkN6BQKwn35EPO8gm57S', timeout=10)

# Write proper Docker daemon.json
daemon_json = json.dumps({
    "log-driver": "json-file",
    "log-opts": {"max-size": "10m", "max-file": "3"},
    "storage-driver": "overlay2",
    "live-restore": True
}, indent=2)

commands = [
    f"cat > /etc/docker/daemon.json << 'EOF'\n{daemon_json}\nEOF",
    "cat /etc/docker/daemon.json",
    "systemctl reset-failed docker.service 2>/dev/null; systemctl start docker",
    "systemctl is-active docker",
    "docker info --format '{{.ServerVersion}}'",
]

for cmd in commands:
    _, stdout, stderr = ssh.exec_command(cmd)
    out = stdout.read().decode().strip()
    err = stderr.read().decode().strip()
    if out:
        print(out)
    if err and 'Warning' not in err:
        print(f'ERR: {err}')

ssh.close()
print("\nDocker daemon fixed and running!")
