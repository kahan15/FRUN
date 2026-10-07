#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
command -v docker >/dev/null || { echo 'Install and start a Docker-compatible engine with Docker Compose first.'; exit 1; }
docker compose version >/dev/null
command -v python3 >/dev/null || { echo 'Python 3 is required to generate local secrets.'; exit 1; }
umask 077
if [[ ! -f .env ]]; then
  python3 - <<'PY'
from pathlib import Path
import secrets
text = Path('.env.example').read_text()
text = text.replace('replace-with-random-url-safe-secret', secrets.token_urlsafe(32))
text = text.replace('replace-with-at-least-32-random-characters', secrets.token_urlsafe(48))
Path('.env').write_text(text)
PY
fi
mkdir -p data backups secrets
docker compose up -d --build db migrate api expiry
python3 - <<'PY'
import socket
import time
import urllib.request
for attempt in range(60):
    try:
        with urllib.request.urlopen('http://127.0.0.1:8000/health/ready', timeout=2) as response:
            if response.status == 200:
                break
    except OSError:
        time.sleep(2)
else:
    raise SystemExit('API did not become ready. Inspect: docker compose logs api migrate db')
address = 'YOUR-LAPTOP-LAN-IP'
try:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.connect(('192.0.2.1', 9))
        address = sock.getsockname()[0]
except OSError:
    pass
print('\nTerritory Run is ready.')
print('iPhone server address: http://' + address + ':8000')
print('Simulator address: http://localhost:8000')
print('API documentation: http://localhost:8000/docs')
print('Use a trusted local network. Do not forward port 8000 from your router.')
PY
