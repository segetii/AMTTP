import paramiko
import sys

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('194.35.120.52', username='root', password='DZc3n0IetkN6BQKwn35EPO8gm57S', timeout=10)

# Read local SSH public key
with open(r'C:\Users\Administrator\.ssh\id_ed25519.pub') as f:
    pubkey = f.read().strip()

commands = [
    'mkdir -p /root/.ssh && chmod 700 /root/.ssh',
    f'echo "{pubkey}" >> /root/.ssh/authorized_keys',
    'sort -u /root/.ssh/authorized_keys -o /root/.ssh/authorized_keys',
    'chmod 600 /root/.ssh/authorized_keys',
    'cat /root/.ssh/authorized_keys',
]

for cmd in commands:
    _, stdout, stderr = ssh.exec_command(cmd)
    out = stdout.read().decode().strip()
    err = stderr.read().decode().strip()
    if out:
        print(out)
    if err:
        print(f'ERR: {err}', file=sys.stderr)

print('\nSSH key installed. Testing key count:')
_, stdout, _ = ssh.exec_command('wc -l /root/.ssh/authorized_keys')
print(stdout.read().decode().strip())

ssh.close()
