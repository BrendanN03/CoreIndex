from fastapi import FastAPI, HTTPException, status
from typing import Optional
from app.models import (
    JobCreateRequest,
    JobResponse,
    FeasibilityResponse,
    JobStatus,
    RelayLink
)
from app.storage import storage
from app.feasibility import (
    calculate_ngh_required,
    calculate_earliest_start,
    calculate_voucher_gap,
    check_milestone_sanity
)

app = FastAPI(
    title="Compute Market Exchange API",
    description="API for compute market exchange - buyer-facing endpoints",
    version="1.0.0"
)


@app.get("/")
def health():
    return {"status": "ok"}


@app.post("/jobs", response_model=JobResponse, status_code=status.HTTP_201_CREATED)
def create_job(request: JobCreateRequest):
    """
    Create a new compute job.
    
    Body includes:
    - job_id: Unique identifier for the job
    - window: Region, ISO hour, SLA, and tier
    - package_index: List of PackageDescriptor objects
    """
    # Check if job already exists
    existing_job = storage.get_job(request.job_id)
    if existing_job:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Job with id '{request.job_id}' already exists"
        )
    
    # Create the job
    job = storage.create_job(request)
    return job


@app.get("/jobs/{job_id}/feasibility", response_model=FeasibilityResponse)
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
            detail=f"Job with id '{job_id}' not found"
        )
    
    # Calculate NGH required
    ngh_required = calculate_ngh_required(job.package_index)
    
    # Calculate earliest start
    earliest_start = calculate_earliest_start(job.package_index, job.window)
    
    # Calculate voucher gap (use job_id as key if no key provided)
    voucher_key = key or job_id
    voucher_gap = calculate_voucher_gap(ngh_required, voucher_key)
    
    # Check milestone sanity
    milestone_sanity = check_milestone_sanity(job.package_index)
    
    return FeasibilityResponse(
        ngh_required=ngh_required,
        earliest_start=earliest_start,
        voucher_gap=voucher_gap,
        milestone_sanity=milestone_sanity
    )


@app.get("/jobs/{job_id}", response_model=JobResponse)
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
            detail=f"Job with id '{job_id}' not found"
        )
    
    # Generate relay links if job is in a state that has manifests
    relay_links = None
    if job.status in [JobStatus.RUNNING, JobStatus.COMPLETED]:
        # In a real implementation, these would be generated based on actual manifest locations
        relay_links = [
            RelayLink(
                manifest_url=f"https://relay.example.com/manifests/{job_id}/manifest.json",
                expires_at=None  # Could set expiration if needed
            )
        ]
    
    # Return job with relay links
    job.relay_links = relay_links
    return job
