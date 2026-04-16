from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.v1.endpoints.auth import get_current_user_optional
from app.repositories.memory.storage import storage
from app.schemas.models import (
    FeasibilityResponse,
    JobCreateRequest,
    JobResponse,
    JobStatus,
    ProductKey,
    RelayLink,
    JobReceiptsResponse,
)
from app.services.feasibility import (
    calculate_earliest_start,
    calculate_ngh_required,
    calculate_job_voucher_gap,
    calculate_voucher_gap,
    check_milestone_sanity,
)


router = APIRouter()


@router.post("/jobs", response_model=JobResponse, status_code=status.HTTP_201_CREATED)
def create_job(
    request: JobCreateRequest,
    user=Depends(get_current_user_optional),
):
    """
    Create a new compute job.

    Body includes:
    - job_id: Unique identifier for the job
    - window: Region, ISO hour, SLA, and tier
    - package_index: List of PackageDescriptor objects

    If the request includes a valid Bearer token, the job is tied to that user (created_by).
    """
    existing_job = storage.get_job(request.job_id)
    if existing_job:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Job with id '{request.job_id}' already exists",
        )

    created_by = user.user_id if user else None
    job = storage.create_job(request, created_by=created_by)
    return job


@router.get("/jobs", response_model=List[JobResponse])
def list_jobs(
    user=Depends(get_current_user_optional),
    limit: int = Query(120, ge=1, le=500, description="Max jobs to return (newest first)"),
):
    """
    List jobs (newest first).
    If the request includes a valid Bearer token, only that user's jobs are returned.
    Otherwise all jobs are returned (for demo/backward compatibility).
    """
    created_by = user.user_id if user else None
    return storage.list_jobs(created_by=created_by, limit=limit)


@router.get("/jobs/{job_id}/feasibility", response_model=FeasibilityResponse)
def get_job_feasibility(job_id: str, key: Optional[str] = None):
    """
    Get feasibility information for a job.

    Returns:
    - NGH required: Sum of package size estimates
    - Earliest start: Next feasible window given artifact sizes and Standard prepare rules
    - Voucher gap: NGH required minus vouchers already deposited for the key
    - Milestone sanity: Flags if any package likely misses first-output <= 2 min or is out of size band [5, 15] NGH
    """
    job = storage.get_job(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job with id '{job_id}' not found",
        )

    ngh_required = calculate_ngh_required(job.package_index)
    earliest_start = calculate_earliest_start(job.package_index, job.window)

    if key:
        voucher_gap = calculate_voucher_gap(ngh_required, key)
    else:
        voucher_gap = calculate_job_voucher_gap(
            ngh_required,
            job.job_id,
            ProductKey.from_window(job.window),
        )

    milestone_sanity = check_milestone_sanity(job.package_index)

    return FeasibilityResponse(
        ngh_required=ngh_required,
        earliest_start=earliest_start,
        voucher_gap=voucher_gap,
        milestone_sanity=milestone_sanity,
    )


@router.get("/jobs/{job_id}", response_model=JobResponse)
def get_job(job_id: str):
    """
    Get job status summary.

    Returns:
    - Status summary
    - Immutable descriptors (window, package_index)
    - Relay links for manifests (if available)
    """
    job = storage.get_job(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job with id '{job_id}' not found",
        )

    relay_links = None
    if job.status in [JobStatus.RUNNING, JobStatus.COMPLETED]:
        relay_links = [
            RelayLink(
                manifest_url=f"https://relay.example.com/manifests/{job_id}/manifest.json",
                expires_at=None,
            )
        ]

    job.relay_links = relay_links
    return job


@router.get("/jobs/{job_id}/receipts", response_model=JobReceiptsResponse)
def get_job_receipts(job_id: str):
    if not storage.get_job(job_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job with id '{job_id}' not found",
        )
    return storage.get_job_receipts(job_id)

