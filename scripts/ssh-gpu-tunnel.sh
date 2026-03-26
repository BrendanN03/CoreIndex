#!/usr/bin/env bash
# Forward the GPU machine's CADO server (port 8000) to this laptop's port 8000.
# Usage:
#   export GPU_USER=you
#   export GPU_HOST=your.server.edu
#   ./scripts/ssh-gpu-tunnel.sh
#
# Leave this running in a terminal, then run `npm run dev` from the repo root.
set -euo pipefail
: "${GPU_USER:?Set GPU_USER (SSH login name)}"
: "${GPU_HOST:?Set GPU_HOST (hostname or IP)}"
exec ssh -N -L 8000:127.0.0.1:8000 "${GPU_USER}@${GPU_HOST}"
