from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional
from app.models import (
    JobCreateRequest,
    JobResponse,
    FeasibilityResponse,
    JobStatus,
    RelayLink,
    NominationRequest,
    NominationResponse,
    PrepareReadyRequest,
    PrepareReadyResponse,
    ResultRequest,
    ResultResponse,
    LotStatus,
    Lot,
    LotCreateRequest
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
    description="API for compute market exchange - buyer and provider endpoints",
    version="1.0.0"
)

# Add CORS middleware to allow browser requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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


# Provider-facing endpoints

@app.post("/nominations", response_model=NominationResponse, status_code=status.HTTP_201_CREATED)
def create_nomination(request: NominationRequest):
    """
    Provider endpoint: Declare NGH availability per (region, hour, tier, SLA).
    
    Body includes:
    - region: Region where compute is available
    - iso_hour: Hour of day (0-23)
    - tier: Compute tier level
    - sla: Service level agreement
    - ngh_available: Amount of NGH available for this window
    """
    nomination = storage.create_nomination(request)
    return nomination


@app.post("/lots", response_model=Lot, status_code=status.HTTP_201_CREATED)
def create_lot(request: LotCreateRequest):
    """
    Provider endpoint: Create a new lot for execution.
    
    Body includes:
    - window: Window specification (region, iso_hour, sla, tier)
    - job_id: Optional job ID to associate with this lot
    """
    lot = storage.create_lot(request.window, request.job_id)
    return lot


@app.post("/lots/{lot_id}/prepare_ready", response_model=PrepareReadyResponse)
def attest_prepare_ready(lot_id: str, request: PrepareReadyRequest):
    """
    Provider endpoint: Attest readiness for a lot.
    
    Confirms that:
    - device_ok: Device is operational
    - driver_ok: Driver is operational
    - image_pulled: Container image has been pulled
    - inputs_prefetched: Inputs have been prefetched
    """
    lot = storage.get_lot(lot_id)
    if not lot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Lot with id '{lot_id}' not found"
        )
    
    # Validate all readiness checks are true
    if not all([
        request.device_ok,
        request.driver_ok,
        request.image_pulled,
        request.inputs_prefetched
    ]):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="All readiness checks must be true"
        )
    
    # Update lot status
    updated_lot = storage.update_lot_prepare_ready(lot_id)
    if not updated_lot:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update lot status"
        )
    
    return PrepareReadyResponse(
        lot_id=lot_id,
        status=updated_lot.status,
        prepared_at=updated_lot.prepared_at or ""
    )


@app.post("/lots/{lot_id}/result", response_model=ResultResponse)
def submit_result(lot_id: str, request: ResultRequest):
    """
    Provider endpoint: Submit execution results for a lot.
    
    Body includes:
    - output_root: Root hash or URI of output
    - item_count: Number of items processed
    - wall_time_seconds: Wall clock time in seconds
    - raw_gpu_time_seconds: Raw GPU time in seconds
    - logs_uri: Optional URI to access logs
    """
    lot = storage.get_lot(lot_id)
    if not lot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Lot with id '{lot_id}' not found"
        )
    
    # Update lot with result data
    result_data = {
        "output_root": request.output_root,
        "item_count": request.item_count,
        "wall_time_seconds": request.wall_time_seconds,
        "raw_gpu_time_seconds": request.raw_gpu_time_seconds,
        "logs_uri": request.logs_uri
    }
    updated_lot = storage.update_lot_result(lot_id, result_data)
    if not updated_lot:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update lot with result"
        )
    
    return ResultResponse(
        lot_id=lot_id,
        status=updated_lot.status,
        output_root=request.output_root,
        item_count=request.item_count,
        wall_time_seconds=request.wall_time_seconds,
        raw_gpu_time_seconds=request.raw_gpu_time_seconds,
        logs_uri=request.logs_uri,
        completed_at=updated_lot.completed_at or ""
    )
