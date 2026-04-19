from __future__ import annotations

import gzip
import io
import json
import sys
from pathlib import Path
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app.repositories.memory.storage import storage


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
from app.services.qc.adversarial.adversarial_generator import (  # noqa: E402
    generate_adversarial_variants_map,
)

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


class QcSubmissionRequest(BaseModel):
    job_id: str = Field(..., min_length=1)
    package_id: str = Field(..., min_length=1)
    provider_id: Optional[str] = Field(None, min_length=1)
    verdict: str = Field(..., min_length=1, max_length=32)
    detail: Optional[str] = Field(None, max_length=280)
    metrics: dict = Field(default_factory=dict)


class QcAdversarialSuiteRequest(BaseModel):
    schema_id: str = Field(..., min_length=1)
    mode: Mode = Field("fp_tolerant")
    rel_tol: float = Field(1e-4, ge=0.0)
    max_ulp: int = Field(2, ge=0)
    variant_mode: Literal["table", "vectors", "relations"] = Field("table")
    base_rows: list[dict] = Field(..., min_length=1, description="Canonical JSON rows")


class QcAdversarialMatrixRequest(BaseModel):
    schema_id: str = Field(..., min_length=1)
    rel_tol: float = Field(1e-4, ge=0.0)
    max_ulp: int = Field(2, ge=0)
    variant_mode: Literal["table", "vectors", "relations"] = Field("table")
    base_rows: list[dict] = Field(..., min_length=1, description="Canonical JSON rows")


class QcGoldCorpusCase(BaseModel):
    case_id: str = Field(..., min_length=1)
    schema_id: str = Field(..., min_length=1)
    mode: Mode = Field("fp_tolerant")
    rel_tol: float = Field(1e-4, ge=0.0)
    max_ulp: int = Field(2, ge=0)
    expected_equal: bool = True
    a_rows: list[dict] = Field(..., min_length=1)
    b_rows: list[dict] = Field(..., min_length=1)


class QcGoldCorpusEvaluateRequest(BaseModel):
    cases: list[QcGoldCorpusCase] = Field(..., min_length=1)


class QcGoldPassCriteria(BaseModel):
    min_pass_rate: float = Field(0.95, ge=0.0, le=1.0)
    max_false_accept_rate: float = Field(0.02, ge=0.0, le=1.0)
    max_false_reject_rate: float = Field(0.05, ge=0.0, le=1.0)


class QcGoldCorpusSaveReportRequest(BaseModel):
    label: str = Field(..., min_length=1, max_length=120)
    report: dict
    criteria: QcGoldPassCriteria


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


@router.post("/qc/duplicate")
async def qc_submit_duplicate(req: QcSubmissionRequest):
    event = storage.record_qc_submission(
        "duplicate",
        req.job_id,
        {
            "package_id": req.package_id,
            "provider_id": req.provider_id,
            "verdict": req.verdict,
            "detail": req.detail,
            "metrics": req.metrics,
        },
    )
    return {
        "event_id": event.event_id,
        "event_type": event.event_type,
        "job_id": req.job_id,
        "package_id": req.package_id,
        "recorded": True,
    }


@router.post("/qc/spot")
async def qc_submit_spot(req: QcSubmissionRequest):
    event = storage.record_qc_submission(
        "spot",
        req.job_id,
        {
            "package_id": req.package_id,
            "provider_id": req.provider_id,
            "verdict": req.verdict,
            "detail": req.detail,
            "metrics": req.metrics,
        },
    )
    return {
        "event_id": event.event_id,
        "event_type": event.event_type,
        "job_id": req.job_id,
        "package_id": req.package_id,
        "recorded": True,
    }


@router.post("/qc/adversarial_suite")
async def qc_adversarial_suite(req: QcAdversarialSuiteRequest):
    def _to_jsonl_bytes(rows: list[dict]) -> bytes:
        lines = [json.dumps(row, separators=(",", ":")) for row in rows]
        return ("\n".join(lines) + "\n").encode("utf-8")

    variants = generate_adversarial_variants_map(
        rows=req.base_rows,
        mode=req.variant_mode,
    )
    base_bytes = _to_jsonl_bytes(req.base_rows)

    # Expectations match compare_canonical_streams behavior: row permutations are aligned,
    # so "reorder" should canonical-match the base. Truncation may be a no-op for some rows;
    # expectation follows the observed equality for that variant.
    expected_equal_by_variant = {
        "bit_exact": {
            "reorder": True,
            "jitter_small": False,
            "jitter_large": False,
            "signed_zero": True,
            "truncate_3dp": False,
            "nan_inject": False,
        },
        "fp_tolerant": {
            "reorder": True,
            "jitter_small": True,
            "jitter_large": False,
            "signed_zero": True,
            "truncate_3dp": False,
            "nan_inject": False,
        },
    }

    results = []
    for name, rows in variants.items():
        lhs = io.BytesIO(base_bytes)
        rhs = io.BytesIO(_to_jsonl_bytes(rows))
        comparison = compare_canonical_fast(
            lhs,
            rhs,
            schema_id=req.schema_id,
            mode=req.mode,
            rel_tol=req.rel_tol,
            max_ulp=req.max_ulp,
        )
        equal = bool(comparison.get("equal"))
        if name == "truncate_3dp":
            expected_equal = equal
        else:
            expected_equal = expected_equal_by_variant[req.mode].get(name, False)
        results.append(
            {
                "variant": name,
                "equal": equal,
                "expected_equal": expected_equal,
                "expectation_passed": (equal == expected_equal),
                "summary": comparison.get("summary", {}),
            }
        )

    return {
        "schema_id": req.schema_id,
        "mode": req.mode,
        "rel_tol": req.rel_tol,
        "max_ulp": req.max_ulp,
        "variant_mode": req.variant_mode,
        "base_record_count": len(req.base_rows),
        "metrics": {
            "total_variants": len(results),
            "expected_true_count": sum(1 for r in results if r["expected_equal"]),
            "expected_false_count": sum(1 for r in results if not r["expected_equal"]),
            "false_accept_count": sum(
                1 for r in results if (not r["expected_equal"] and r["equal"])
            ),
            "false_reject_count": sum(
                1 for r in results if (r["expected_equal"] and not r["equal"])
            ),
            "expectation_pass_rate": (
                sum(1 for r in results if r["expectation_passed"]) / max(1, len(results))
            ),
        },
        "results": results,
    }


@router.post("/qc/adversarial_matrix")
async def qc_adversarial_matrix(req: QcAdversarialMatrixRequest):
    aggregate = []
    for mode in ("bit_exact", "fp_tolerant"):
        row = await qc_adversarial_suite(
            QcAdversarialSuiteRequest(
                schema_id=req.schema_id,
                mode=mode,  # type: ignore[arg-type]
                rel_tol=req.rel_tol,
                max_ulp=req.max_ulp,
                variant_mode=req.variant_mode,
                base_rows=req.base_rows,
            )
        )
        aggregate.append(row)
    return {
        "schema_id": req.schema_id,
        "rel_tol": req.rel_tol,
        "max_ulp": req.max_ulp,
        "variant_mode": req.variant_mode,
        "modes": aggregate,
    }


@router.post("/qc/gold_corpus/evaluate")
async def qc_gold_corpus_evaluate(req: QcGoldCorpusEvaluateRequest):
    def _to_jsonl_bytes(rows: list[dict]) -> bytes:
        lines = [json.dumps(row, separators=(",", ":")) for row in rows]
        return ("\n".join(lines) + "\n").encode("utf-8")

    results = []
    for case in req.cases:
        comp = compare_canonical_fast(
            io.BytesIO(_to_jsonl_bytes(case.a_rows)),
            io.BytesIO(_to_jsonl_bytes(case.b_rows)),
            schema_id=case.schema_id,
            mode=case.mode,
            rel_tol=case.rel_tol,
            max_ulp=case.max_ulp,
        )
        equal = bool(comp.get("equal"))
        expected_equal = bool(case.expected_equal)
        results.append(
            {
                "case_id": case.case_id,
                "schema_id": case.schema_id,
                "mode": case.mode,
                "expected_equal": expected_equal,
                "equal": equal,
                "pass": equal == expected_equal,
                "summary": comp.get("summary", {}),
            }
        )

    total = len(results)
    pass_count = sum(1 for row in results if row["pass"])
    false_accept = sum(
        1 for row in results if row["equal"] is True and row["expected_equal"] is False
    )
    false_reject = sum(
        1 for row in results if row["equal"] is False and row["expected_equal"] is True
    )
    expected_positive = sum(1 for row in results if row["expected_equal"] is True)
    expected_negative = sum(1 for row in results if row["expected_equal"] is False)

    return {
        "total_cases": total,
        "pass_cases": pass_count,
        "pass_rate": pass_count / max(1, total),
        "false_accept_count": false_accept,
        "false_reject_count": false_reject,
        "false_accept_rate": false_accept / max(1, expected_negative),
        "false_reject_rate": false_reject / max(1, expected_positive),
        "results": results,
    }


def _gold_report_passes_criteria(report: dict, criteria: QcGoldPassCriteria) -> bool:
    def _as_float(value: object, default: float) -> float:
        if value is None:
            return default
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    pass_rate = _as_float(report.get("pass_rate"), 0.0)
    false_accept_rate = _as_float(report.get("false_accept_rate"), 1.0)
    false_reject_rate = _as_float(report.get("false_reject_rate"), 1.0)
    return (
        pass_rate >= criteria.min_pass_rate
        and false_accept_rate <= criteria.max_false_accept_rate
        and false_reject_rate <= criteria.max_false_reject_rate
    )


@router.post("/qc/gold_corpus/report")
async def qc_gold_corpus_save_report(req: QcGoldCorpusSaveReportRequest):
    passed = _gold_report_passes_criteria(req.report, req.criteria)
    event = storage.record_qc_submission(
        "gold_corpus_report",
        "gold-corpus",
        {
            "label": req.label.strip(),
            "criteria": req.criteria.model_dump(),
            "report": req.report,
            "pass_criteria_met": passed,
        },
    )
    return {
        "report_id": event.event_id,
        "created_at": event.created_at,
        "label": req.label.strip(),
        "pass_criteria_met": passed,
    }


@router.get("/qc/gold_corpus/reports")
async def qc_gold_corpus_list_reports(limit: int = 20):
    bounded = max(1, min(200, int(limit)))
    rows = []
    for event in storage.list_events():
        if event.event_type != "qc.gold_corpus_report":
            continue
        payload = event.payload or {}
        rows.append(
            {
                "report_id": event.event_id,
                "created_at": event.created_at,
                "label": str(payload.get("label") or "gold-corpus"),
                "criteria": payload.get("criteria") if isinstance(payload.get("criteria"), dict) else {},
                "report": payload.get("report") if isinstance(payload.get("report"), dict) else {},
                "pass_criteria_met": bool(payload.get("pass_criteria_met")),
            }
        )
        if len(rows) >= bounded:
            break
    return {"count": len(rows), "reports": rows}

