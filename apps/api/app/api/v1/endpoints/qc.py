from __future__ import annotations

import gzip
import io
import sys
from pathlib import Path
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, UploadFile
from pydantic import BaseModel, Field


def _ensure_repo_root_on_sys_path() -> None:
    """
    Make the monorepo root importable.

    In a monorepo, shared libs like `packages/` and `canonx/` live at the repo root.
    If you run the API from `apps/api`, that root is not automatically on `sys.path`.
    """
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "packages").is_dir() and (parent / "apps").is_dir():
            if str(parent) not in sys.path:
                sys.path.insert(0, str(parent))
            return

    # If we can't find the repo root, imports will fail anyway; raise a clear error.
    raise RuntimeError("Could not locate repo root (expected to find /packages and /apps).")


_ensure_repo_root_on_sys_path()

# Import after sys.path fix.
from canonx.api_compare import compare_canonical_fast  # noqa: E402
from canonx.iohelpers import open_maybe_gzip  # noqa: E402
from canonx.merkle import merkle_stream  # noqa: E402
from canonx.util import count_jsonl_records  # noqa: E402
from canonx.canonicalize import canonicalize_bytes  # noqa: E402

from app.services.qc.sampling import load_policy, plan_sampling  # noqa: E402
from app.services.qc.dispute import decision as dispute_decision  # noqa: E402

from packages.cado_proofkit.verifier_f2 import verify_f2_matrix_vector  # noqa: E402
from packages.cado_proofkit.hash_commit import hash_matrix_rows  # noqa: E402


router = APIRouter()

Mode = Literal["bit_exact", "fp_tolerant"]


class SamplingPlanRequest(BaseModel):
    job_id: str
    window: str
    tier: str
    package_id: str
    n_items: int = Field(..., gt=0)
    secret_epoch: str = Field(..., description="Scheduler-provided epoch salt")
    job_seed_hex: Optional[str] = Field(
        None, description="Optional explicit job seed hex"
    )


class DisputeDecisionRequest(BaseModel):
    x_mismatch: int = Field(..., ge=0)
    n_checked: int = Field(..., gt=0)
    eps0: float = Field(0.01, gt=0.0)
    alpha: float = Field(0.01, gt=0.0)


class CertVerifyRequest(BaseModel):
    matrix_rows: list[str] = Field(..., min_length=1)
    vector_bits: str = Field(..., min_length=1)


class LaOutputVerifyRequest(BaseModel):
    matrix_hash: str = Field(..., min_length=3, description="Hex hash of matrix rows")
    vector_bits: str = Field(..., min_length=1)
    iterations: int = Field(..., ge=0)
    rank: int = Field(..., ge=0)
    world_size: int = Field(..., ge=1)
    seed: str = Field(..., min_length=1)
    matrix_rows: Optional[list[str]] = Field(
        None,
        description="Optional rows for full Mv=0 verification (demo-friendly)",
    )


def _read_upload_as_seekable(upload: UploadFile) -> io.BytesIO:
    """
    Read an UploadFile into a seekable buffer.

    Notes:
    - This is memory-inefficient for very large outputs, but it is the simplest
      correct behavior for early integration and demos.
    - The v2 path later is: stream canonicalization output into hashing without
      buffering the whole file in RAM.
    """
    raw = upload.file
    stream = open_maybe_gzip(raw)
    data = stream.read()
    return io.BytesIO(data)


@router.post("/qc/hash")
async def qc_hash(file: UploadFile):
    """
    Hash a blob/stream into a SHA-256 Merkle root.

    For now, this assumes the uploaded bytes are already in canonical form
    (e.g., canonical JSONL) and just computes the Merkle root.
    """
    buf = _read_upload_as_seekable(file)
    buf.seek(0)
    root, leaves, nbytes, nchunks, csize = merkle_stream(buf)
    return {
        "merkle_root": root,
        "chunk_roots": leaves,
        "bytes": nbytes,
        "chunks": nchunks,
        "chunk_size": csize,
    }


@router.get("/qc/policy")
async def qc_policy():
    """
    Return the QC policy JSON (sampling rates, dispute parameters).
    """
    return load_policy()


@router.post("/qc/sampling_plan")
async def qc_sampling_plan(req: SamplingPlanRequest):
    """
    Return deterministic sampling indices for canaries and spot checks.
    """
    plan = plan_sampling(
        job_id=req.job_id,
        window=req.window,
        tier=req.tier,
        package_id=req.package_id,
        n_items=req.n_items,
        secret_epoch=req.secret_epoch,
        job_seed_hex=req.job_seed_hex,
    )
    return {
        "dup_selected": plan.dup_selected,
        "canary_indices": plan.canary_indices,
        "spot_indices": plan.spot_indices,
        "canary_count": plan.canary_count,
        "spot_count": plan.spot_count,
    }


@router.post("/qc/canonicalize")
async def qc_canonicalize(
    schema_id: str,
    file: UploadFile,
    input_format: Optional[str] = None,
):
    """
    Canonicalize + hash an output.

    IMPORTANT (current state):
    - This endpoint does NOT yet convert Parquet/CSV/etc into canonical JSONL.
    - It assumes the upload is already the canonical bytes for `schema_id`.

    What this returns is exactly what you store alongside receipts:
    `{schema_id, canonicalization_version, record_count, merkle_root, chunk_roots}`.
    """
    buf = _read_upload_as_seekable(file)
    if input_format and input_format != "canonical_jsonl":
        buf.seek(0)
        canonical = canonicalize_bytes(
            schema_id=schema_id,
            input_bytes=buf.read(),
            input_format=input_format,
        )
        buf = io.BytesIO(canonical)

    # record_count assumes JSONL (one record per line). For non-JSONL schemas, this
    # will be updated later when those schema canonicalizers exist.
    buf.seek(0)
    record_count = count_jsonl_records(buf)

    buf.seek(0)
    root, leaves, nbytes, nchunks, csize = merkle_stream(buf)

    return {
        "schema_id": schema_id,
        "canonicalization_version": "canonx/1.0.0",
        "record_count": record_count,
        "merkle_root": root,
        "chunk_roots": leaves,
        "bytes": nbytes,
        "chunks": nchunks,
        "chunk_size": csize,
    }


@router.post("/qc/compare")
async def qc_compare(
    schema_id: str,
    mode: Mode,
    a: UploadFile,
    b: UploadFile,
    rel_tol: float = 1e-4,
    max_ulp: int = 2,
):
    """
    Compare two outputs for equality under the v2 rules.

    IMPORTANT (current state):
    - This assumes both uploads are already canonical JSONL streams, sorted by schema keys.
    - `bit_exact`: exact equality on canonical bytes (fast when roots match).
    - `fp_tolerant`: allow bounded FP differences (rel_tol + max_ulp), everything else exact.
    """
    if mode not in ("bit_exact", "fp_tolerant"):
        raise HTTPException(
            status_code=400,
            detail="mode must be 'bit_exact' or 'fp_tolerant'",
        )

    buf_a = _read_upload_as_seekable(a)
    buf_b = _read_upload_as_seekable(b)

    buf_a.seek(0)
    buf_b.seek(0)
    return compare_canonical_fast(
        buf_a,
        buf_b,
        schema_id=schema_id,
        mode=mode,
        rel_tol=rel_tol,
        max_ulp=max_ulp,
    )


@router.post("/qc/dispute/decide")
async def qc_dispute_decide(req: DisputeDecisionRequest):
    """
    Decide accept vs reject+slash based on mismatch count in dispute re-exec.
    """
    outcome = dispute_decision(
        x=req.x_mismatch,
        n=req.n_checked,
        eps0=req.eps0,
        alpha=req.alpha,
    )
    return {"decision": outcome}


@router.post("/qc/cert/verify")
async def qc_cert_verify(req: CertVerifyRequest):
    """
    Verify an F2 certificate: Mv = 0 over GF(2).
    Returns verified flag + a simple hash commitment for the matrix.
    """
    verified = verify_f2_matrix_vector(req.matrix_rows, req.vector_bits)
    matrix_hash = hash_matrix_rows(req.matrix_rows)
    return {"verified": verified, "matrix_hash": matrix_hash}


@router.post("/qc/cert/verify_la_output")
async def qc_cert_verify_la_output(req: LaOutputVerifyRequest):
    """
    Verify a full LA output object.

    - If matrix_rows are provided, we verify Mv=0 and validate matrix_hash.
    - If matrix_rows are omitted, we only return the provided hash and metadata
      (useful for large matrices stored elsewhere).
    """
    matrix_hash = req.matrix_hash
    verified = None

    if req.matrix_rows:
        computed_hash = hash_matrix_rows(req.matrix_rows)
        if computed_hash != req.matrix_hash:
            return {
                "verified": False,
                "matrix_hash": computed_hash,
                "reason": "matrix_hash_mismatch",
            }
        verified = verify_f2_matrix_vector(req.matrix_rows, req.vector_bits)
        matrix_hash = computed_hash

    return {
        "verified": verified,
        "matrix_hash": matrix_hash,
        "iterations": req.iterations,
        "rank": req.rank,
        "world_size": req.world_size,
        "seed": req.seed,
    }

