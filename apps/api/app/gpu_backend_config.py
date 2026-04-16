"""Environment-driven URL for the remote CADO / GPU factoring HTTP service."""

from __future__ import annotations

import os
import socket
from urllib.parse import urlparse


def _strip(value: str | None) -> str:
    return (value or "").strip()


def factoring_base_url() -> str:
    """Base URL for uvicorn remote_factor_server (no trailing slash)."""
    raw = _strip(os.getenv("FACTORING_REMOTE_HTTP_URL"))
    if not raw:
        raw = "http://127.0.0.1:8000"
    return raw.rstrip("/")


def factoring_factor_path() -> str:
    path = _strip(os.getenv("FACTORING_REMOTE_FACTOR_PATH")) or "/factor"
    return path if path.startswith("/") else f"/{path}"


def factoring_post_url() -> str:
    return f"{factoring_base_url()}{factoring_factor_path()}"


def factoring_timeouts() -> tuple[float, float | None]:
    """(connect seconds, read seconds) for requests.post to /factor.

    Read timeout ``None`` means no limit (required for long CADO-NFS runs). Set
    ``FACTORING_HTTP_READ_TIMEOUT_SECONDS=0`` or ``none`` for that behavior.
    A positive number caps idle time between recv chunks (can kill very slow streams).
    """
    connect = float(os.getenv("FACTORING_HTTP_CONNECT_TIMEOUT_SECONDS", "15"))
    read_raw = (
        os.getenv("FACTORING_HTTP_READ_TIMEOUT_SECONDS")
        or os.getenv("FACTORING_HTTP_TIMEOUT_SECONDS")
        or ""
    ).strip().lower()
    if read_raw in ("", "0", "none", "inf", "infinity"):
        return (connect, None)
    return (connect, float(read_raw))


def factoring_ssh_host_label() -> str:
    return _strip(os.getenv("FACTORING_SSH_HOST")) or urlparse(factoring_base_url()).netloc or "gpu-host"


def setup_instructions_hint() -> str:
    custom = _strip(os.getenv("FACTORING_SETUP_HINT"))
    if custom:
        return custom
    host = factoring_ssh_host_label()
    return (
        "Local dev (no GPU): from apps/api run "
        "`.venv/bin/python -m uvicorn dev_remote_factor_server:app --host 127.0.0.1 --port 8000` "
        "with FACTORING_REMOTE_HTTP_URL=http://127.0.0.1:8000 in apps/api/.env, "
        "or start the full stack with COREINDEX_DEV_FACTOR_STUB=1. "
        "Production: on the GPU server run "
        "`uvicorn remote_factor_server:app --host 0.0.0.0 --port 8000`, then from your laptop "
        f"`ssh -N -L 8000:127.0.0.1:8000 you@{host}` "
        "and keep FACTORING_REMOTE_HTTP_URL=http://127.0.0.1:8000. "
        "Leave that ssh -N window open; a normal interactive ssh session does not forward ports. "
        "If HTTP_PROXY is set, CoreIndex disables proxying for the factor URL; you can also set "
        "NO_PROXY=127.0.0.1,localhost."
    )


def probe_gpu_backend_tcp() -> tuple[bool, str | None]:
    """Check that something is listening (TCP) without calling /factor."""
    url = factoring_base_url()
    parsed = urlparse(url)
    host = parsed.hostname
    if not host:
        return False, "invalid FACTORING_REMOTE_HTTP_URL (no host)"
    if parsed.scheme not in ("http", "https"):
        return False, f"unsupported URL scheme: {parsed.scheme!r}"
    port = parsed.port
    if port is None:
        port = 443 if parsed.scheme == "https" else 80
    try:
        with socket.create_connection((host, port), timeout=1.25):
            pass
    except OSError as exc:
        return False, str(exc)
    return True, None
