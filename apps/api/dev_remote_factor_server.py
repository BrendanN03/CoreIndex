"""
Local stand-in for ``remote_factor_server`` — returns ECM/CADO-shaped JSON for CoreIndex.

The CoreIndex API POSTs JSON ``{ "gpu_count": int, "composite": str }`` to ``/factor`` and
expects a JSON body whose ``summary`` object matches what the real GPU pipeline returns.

Run from ``apps/api`` (with the same venv as the API)::

    .venv/bin/python -m uvicorn dev_remote_factor_server:app --host 127.0.0.1 --port 8000

Set in ``apps/api/.env``::

    FACTORING_REMOTE_HTTP_URL=http://127.0.0.1:8000
"""

from __future__ import annotations

import os
import time
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, field_validator

app = FastAPI(title="CoreIndex dev factor stub", version="0.1.0")

# SymPy factorization for demo-sized composites (override via env for local tuning).
_MAX_COMPOSITE_DIGITS = int(os.environ.get("DEV_STUB_MAX_COMPOSITE_DIGITS", "64"))
# Legacy name — ``gpu_backend_config`` probes this for UI limits.
_MAX_TRIAL_DIGITS = _MAX_COMPOSITE_DIGITS

_TRIAL_FALLBACK_MAX_DIGITS = 22


def _trial_prime_factors(n: int) -> list[int]:
    if n < 2:
        return []
    factors: list[int] = []
    while n % 2 == 0:
        factors.append(2)
        n //= 2
    f = 3
    while f * f <= n:
        while n % f == 0:
            factors.append(f)
            n //= f
        f += 2
    if n > 1:
        factors.append(n)
    return factors


def _prime_factors_via_sympy(n: int) -> list[int]:
    from sympy import factorint

    fac: dict[int, int] = factorint(n)
    out: list[int] = []
    for p in sorted(fac.keys()):
        out.extend([p] * fac[p])
    return out


class FactorBody(BaseModel):
    gpu_count: int = Field(..., ge=1, le=64)
    composite: str = Field(..., min_length=2)

    @field_validator("composite")
    @classmethod
    def digits_only(cls, value: str) -> str:
        t = value.strip()
        if not t.isdigit():
            raise ValueError("composite must contain only digits")
        return t


@app.get("/")
def root() -> dict[str, Any]:
    return {
        "service": "dev_remote_factor_server",
        "post": "/factor",
        "max_composite_digits": _MAX_COMPOSITE_DIGITS,
    }


@app.post("/factor")
def factor(req: FactorBody) -> dict[str, Any]:
    digits = req.composite
    if len(digits) > _MAX_COMPOSITE_DIGITS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"composite too long ({len(digits)} digits; max {_MAX_COMPOSITE_DIGITS} for this demo service)"
            ),
        )
    n = int(digits)
    t0 = time.perf_counter()
    try:
        if len(digits) <= _TRIAL_FALLBACK_MAX_DIGITS:
            factors = _trial_prime_factors(n)
            method = "dev_trial_division_stub"
        else:
            factors = _prime_factors_via_sympy(n)
            method = "sympy_factorint_stub"
    except Exception as exc:  # pragma: no cover — defensive for odd SymPy inputs
        raise HTTPException(
            status_code=422,
            detail=f"factorization failed for this composite: {exc}",
        ) from exc
    elapsed = time.perf_counter() - t0

    summary: dict[str, Any] = {
        "method": method,
        "input_n": digits,
        "final_prime_factors": factors,
        "ecm_elapsed_sec": round(elapsed * 0.25 + 0.0001, 6),
        "cado_elapsed_sec": 0.0,
        "total_elapsed_sec": round(elapsed + 0.0002, 6),
        "cado_runs": [],
        "gpu_devices": [f"dev-stub-gpu-{i}" for i in range(min(req.gpu_count, 8))],
    }
    return {"summary": summary}
