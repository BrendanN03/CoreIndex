from __future__ import annotations

import json
import os
import shlex
import subprocess
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, field_validator


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


def _extract_json_summary(stdout: str) -> Any:
    stripped = stdout.strip()
    if not stripped:
        raise ValueError("Remote command returned empty stdout")

    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass

    for line in reversed(stripped.splitlines()):
        candidate = line.strip()
        if not candidate:
            continue
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue

    raise ValueError("Could not parse JSON summary from remote stdout")


import os
from typing import Any

import requests
from fastapi import HTTPException, status


def _run_remote_factoring(gpu_ids: list[int], composite: str) -> Any:
    remote_base_url = os.getenv("FACTORING_REMOTE_HTTP_URL", "http://158.130.4.234:8000")
    timeout_seconds = int(os.getenv("FACTORING_HTTP_TIMEOUT_SECONDS", "86400"))

    try:
        response = requests.post(
            f"{remote_base_url}/factor",
            json={
                "gpu_count": len(gpu_ids),
                "composite": composite,
            },
            timeout=timeout_seconds,
        )
    except requests.RequestException as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Could not reach remote factoring server: {exc}",
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

    payload = response.json()
    return payload["summary"]


@router.post("/factor", response_model=FactorResponse)
def factor_composite(request: FactorRequest):
    """
    Run the remote multi-GPU factoring script over SSH and return its JSON summary.
    """
    gpu_ids = _build_gpu_ids(request.gpu_count)
    summary = _run_remote_factoring(gpu_ids, request.composite)
    remote_host = os.getenv("FACTORING_SSH_HOST", "158.130.4.234")

    return FactorResponse(
        gpu_count=request.gpu_count,
        gpu_ids=gpu_ids,
        composite=request.composite,
        remote_host=remote_host,
        summary=summary,
    )
