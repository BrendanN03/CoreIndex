"""Environment-driven URL for the remote CADO / GPU factoring HTTP service."""

from __future__ import annotations

import logging
import os
import socket
from typing import Optional, Tuple
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
        "Local dev: `npm run dev` starts the in-repo factor stub on port 8000 by default "
        "(set COREINDEX_DEV_FACTOR_STUB=0 if you use an SSH tunnel on that port). "
        "Running only uvicorn from apps/api auto-starts the same stub when "
        "FACTORING_REMOTE_HTTP_URL is http://127.0.0.1 or http://localhost and nothing is listening. "
        "Manual stub: `.venv/bin/python -m uvicorn dev_remote_factor_server:app --host 127.0.0.1 --port 8000`. "
        "Production: on the GPU server run "
        "`uvicorn remote_factor_server:app --host 0.0.0.0 --port 8000`, then from your laptop "
        f"`ssh -N -L 8000:127.0.0.1:8000 you@{host}` "
        "and keep FACTORING_REMOTE_HTTP_URL=http://127.0.0.1:8000. "
        "Leave that ssh -N window open; a normal interactive ssh session does not forward ports. "
        "If HTTP_PROXY is set, CoreIndex disables proxying for the factor URL; you can also set "
        "NO_PROXY=127.0.0.1,localhost."
    )


def probe_factor_http_identity() -> Tuple[Optional[str], Optional[int]]:
    """If TCP is already OK, GET the factor base URL root JSON (dev stub exposes service + limits).

    Returns ``(kind, dev_stub_max_digits)`` where ``kind`` is e.g. ``dev_remote_factor_server`` or ``None``.
    """
    try:
        import requests
    except Exception:
        return None, None

    url = factoring_base_url().rstrip("/") + "/"
    try:
        with requests.Session() as session:
            session.trust_env = False
            response = session.get(url, timeout=(2.0, 2.0))
    except requests.RequestException as exc:
        logging.getLogger("uvicorn.error").debug("factor HTTP identity probe failed: %s", exc)
        return None, None

    if response.status_code != 200:
        return None, None
    try:
        payload = response.json()
    except Exception:
        return None, None
    if not isinstance(payload, dict):
        return None, None
    service = payload.get("service")
    if service == "dev_remote_factor_server":
        try:
            import dev_remote_factor_server as dev_stub

            return "dev_remote_factor_server", int(dev_stub._MAX_TRIAL_DIGITS)
        except Exception:
            return "dev_remote_factor_server", None
    return None, None


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
