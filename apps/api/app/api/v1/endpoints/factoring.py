from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, field_validator

from app.gpu_backend_config import (
    factoring_post_url,
    factoring_ssh_host_label,
    factoring_timeouts,
)

router = APIRouter()


class FactorRequest(BaseModel):
    gpu_count: int = Field(..., ge=1, le=4, description="Number of GPUs to use (1-4)")
    composite: str = Field(
        ...,
        min_length=2,
        description="Large integer to factor, passed as a string to avoid precision loss",
    )

    @field_validator("composite")
    @classmethod
    def validate_composite(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized.isdigit():
            raise ValueError("composite must contain only digits")
        return normalized


class FactorResponse(BaseModel):
    gpu_count: int
    gpu_ids: list[int]
    composite: str
    remote_host: str
    summary: Any


def _build_gpu_ids(gpu_count: int) -> list[int]:
    return list(range(gpu_count))


def _run_remote_factoring(gpu_ids: list[int], composite: str) -> Any:
    # Lazy import to avoid making this endpoint a hard dependency for startup.
    try:
        import requests
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="requests is required for /factor remote calls",
        ) from exc

    url = factoring_post_url()
    connect_s, read_s = factoring_timeouts()

    try:
        # Ignore HTTP(S)_PROXY for localhost / tunnel URLs — corporate proxies often wedge 127.0.0.1.
        with requests.Session() as session:
            session.trust_env = False
            response = session.post(
                url,
                json={
                    "gpu_count": len(gpu_ids),
                    "composite": composite,
                },
                timeout=(connect_s, read_s),
            )
    except requests.RequestException as exc:
        msg = str(exc)
        if (
            "Connection refused" in msg
            or "Failed to establish a new connection" in msg
            or "Errno 61" in msg
            or "Errno 111" in msg
        ):
            msg += (
                " — Nothing is listening on FACTORING_REMOTE_HTTP_URL from the API process. "
                "Start the tunnel from your laptop, e.g. "
                "ssh -N -L 8000:127.0.0.1:8000 you@GPU_HOST "
                "(leave it running), with remote_factor_server on port 8000 on the GPU host."
            )
        elif "Read timed out" in msg or "ReadTimeout" in msg:
            msg += (
                " — Increase FACTORING_HTTP_READ_TIMEOUT_SECONDS in apps/api/.env "
                "or set it to 0 for no read limit (long CADO-NFS jobs)."
            )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Could not reach remote factoring server: {msg}",
        ) from exc

    if response.status_code != 200:
        try:
            detail = response.json()
        except Exception:
            detail = response.text
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "message": "Remote factoring server returned an error",
                "remote_status": response.status_code,
                "remote_response": detail,
            },
        )

    try:
        payload = response.json()
    except Exception:
        text = (response.text or "").strip()
        return {"_parse_note": "remote returned non-JSON body", "body_preview": text[:8000]}

    if isinstance(payload, dict) and "summary" in payload:
        return payload["summary"]
    return payload


@router.post("/factor", response_model=FactorResponse)
def factor_composite(request: FactorRequest):
    """Proxy multi-GPU factoring request to the remote GPU backend."""
    gpu_ids = _build_gpu_ids(request.gpu_count)
    summary = _run_remote_factoring(gpu_ids, request.composite)
    remote_host = factoring_ssh_host_label()

    return FactorResponse(
        gpu_count=request.gpu_count,
        gpu_ids=gpu_ids,
        composite=request.composite,
        remote_host=remote_host,
        summary=summary,
    )
