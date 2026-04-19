"""Spawn ``dev_remote_factor_server`` when local dev expects a factor HTTP service.

``npm run dev`` (scripts/dev-stack.mjs) starts this by default. When the API is run
alone with ``uvicorn``, we optionally start the same stub so ``FACTORING_REMOTE_HTTP_URL``
does not point at a dead port.

Opt out everywhere: ``COREINDEX_DEV_FACTOR_STUB=0``.
Force start when the port is free: ``COREINDEX_DEV_FACTOR_STUB=1`` (if the port is already in use, the stub is skipped).
Default / unset: auto-start only for ``http://127.0.0.1`` / ``http://localhost`` when the TCP probe fails.
"""

from __future__ import annotations

import logging
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

from app.gpu_backend_config import factoring_base_url, probe_gpu_backend_tcp

_log = logging.getLogger("uvicorn.error")

_proc: subprocess.Popen[bytes] | None = None


def _local_http_bind_target(url: str) -> tuple[str, int] | None:
    u = urlparse(url)
    if u.scheme != "http":
        return None
    h = (u.hostname or "").lower()
    if h not in ("127.0.0.1", "localhost"):
        return None
    port = u.port or 80
    return ("127.0.0.1", port)


def _can_bind_local(port: int) -> bool:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        s.bind(("127.0.0.1", port))
        return True
    except OSError:
        return False
    finally:
        s.close()


def start_if_configured() -> None:
    global _proc
    if _proc is not None and _proc.poll() is None:
        return

    flag = os.getenv("COREINDEX_DEV_FACTOR_STUB", "").strip().lower()
    if flag == "0":
        return

    base = factoring_base_url()
    bind = _local_http_bind_target(base)
    if bind is None:
        if flag == "1":
            _log.warning(
                "COREINDEX_DEV_FACTOR_STUB=1 but FACTORING_REMOTE_HTTP_URL=%r is not http on "
                "127.0.0.1/localhost — not starting dev_remote_factor_server.",
                base,
            )
        return

    _, port = bind

    if flag == "1":
        want_stub = True
    else:
        ok, _ = probe_gpu_backend_tcp()
        want_stub = not ok

    if not want_stub:
        return

    if not _can_bind_local(port):
        _log.info(
            "Dev factor stub not started: port %s is already bound (SSH tunnel or another "
            "process is serving FACTORING_REMOTE_HTTP_URL).",
            port,
        )
        return

    api_dir = Path(__file__).resolve().parent.parent
    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "dev_remote_factor_server:app",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
    ]
    try:
        _proc = subprocess.Popen(
            cmd,
            cwd=str(api_dir),
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
            stdout=None,
            stderr=None,
        )
    except OSError as exc:
        _log.warning("Could not start dev_remote_factor_server: %s", exc)
        return

    ok = False
    terr: str | None = None
    deadline = time.monotonic() + 8.0
    while time.monotonic() < deadline:
        if _proc.poll() is not None:
            _log.warning(
                "dev_remote_factor_server exited early (code=%s); check apps/api logs / venv deps.",
                _proc.returncode,
            )
            _proc = None
            return
        ok, terr = probe_gpu_backend_tcp()
        if ok:
            break
        time.sleep(0.2)

    if ok:
        _log.info(
            "Started local dev factor stub (dev_remote_factor_server) on http://127.0.0.1:%s",
            port,
        )
    else:
        _log.warning(
            "dev_remote_factor_server subprocess running but TCP probe still fails after wait: %s",
            terr or "unknown",
        )


def stop_if_started() -> None:
    global _proc
    if _proc is None:
        return
    if _proc.poll() is not None:
        _proc = None
        return
    try:
        _proc.terminate()
        try:
            _proc.wait(timeout=3.0)
        except subprocess.TimeoutExpired:
            _proc.kill()
    except Exception:
        _log.warning("Could not terminate dev_remote_factor_server", exc_info=True)
    finally:
        _proc = None
