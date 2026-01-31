"""
Compatibility shim for `canonx`.

The real implementation lives at `packages/canonicalization/canonx/`.
This package keeps `import canonx.*` working regardless of the current working
directory by ensuring the repo root is on `sys.path`, then forwarding imports.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure repo root is importable even when running from subdirectories (e.g. apps/api).
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# Re-export public API
from packages.canonicalization.canonx import *  # noqa: F401,F403

