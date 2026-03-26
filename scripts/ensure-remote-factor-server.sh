#!/usr/bin/env bash
# Start remote_factor_server on the GPU host if it is not already running.
#
# Prerequisites on the GPU machine:
#   - /home/coreindex/cado_improved/remote_factor_server.py
#   - python3 with: pip install --user fastapi "uvicorn[standard]" pydantic
#
# From your laptop (after SSH tunnel is up):
#   export GPU_SSH_USER=arnab
#   export GPU_SSH_HOST=your.gpu.host
#   export SSHPASS='...'   # optional; prefer ssh-agent keys
#   ./scripts/ensure-remote-factor-server.sh
#
# Tunnel (separate terminal, leave running):
#   ssh -N -L 8000:127.0.0.1:8000 "${GPU_SSH_USER}@${GPU_SSH_HOST}"
#
set -euo pipefail
GPU_SSH_USER="${GPU_SSH_USER:-arnab}"
GPU_SSH_HOST="${GPU_SSH_HOST:-}"

if [[ -z "$GPU_SSH_HOST" ]]; then
  echo "Set GPU_SSH_HOST (e.g. export GPU_SSH_HOST=158.130.4.234)" >&2
  exit 1
fi

REMOTE_CMD='cd /home/coreindex/cado_improved && if pgrep -f "uvicorn remote_factor_server:app" >/dev/null; then echo "remote_factor_server already running"; else nohup python3 -m uvicorn remote_factor_server:app --host 127.0.0.1 --port 8000 >> /tmp/remote_factor_server.log 2>&1 & sleep 1; pgrep -af "uvicorn remote_factor_server" || true; fi'

SSH_BASE=(ssh -o StrictHostKeyChecking=accept-new -o ConnectTimeout=15 "${GPU_SSH_USER}@${GPU_SSH_HOST}")

if command -v sshpass >/dev/null 2>&1 && [[ -n "${SSHPASS:-}" ]]; then
  SSHPASS="$SSHPASS" sshpass -e "${SSH_BASE[@]}" "$REMOTE_CMD"
else
  "${SSH_BASE[@]}" "$REMOTE_CMD"
fi
