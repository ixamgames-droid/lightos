#!/usr/bin/env bash
# LightOS Start-Script (Linux / macOS)
set -e

cd "$(dirname "$0")"

# venv-Python suchen
if [ -x "venv/bin/python" ]; then
    PYTHON="venv/bin/python"
elif [ -x "venv/bin/python3" ]; then
    PYTHON="venv/bin/python3"
else
    echo "[start] Kein venv gefunden - nutze System-Python"
    PYTHON="python3"
fi

ARCH=$(uname -m)
echo "[start] Arch: $ARCH"
echo "[start] Python: $PYTHON"

# Argumente weiterreichen
exec "$PYTHON" main.py "$@"
