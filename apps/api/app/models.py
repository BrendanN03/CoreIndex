from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum


class Region(str, Enum):
    """Supported regions for compute jobs"""
    US_EAST = "us-east"
    US_WEST = "us-west"
    EU_CENTRAL = "eu-central"
    ASIA_PACIFIC = "asia-pacific"


class SLA(str, Enum):
    """Service Level Agreement tiers"""
    STANDARD = "standard"
    PREMIUM = "premium"
    URGENT = "urgent"


class Tier(str, Enum):
    """Compute tier levels"""
    BASIC = "basic"
    STANDARD = "standard"
    PREMIUM = "premium"
    ENTERPRISE = "enterprise"


class Window(BaseModel):
    """Window specification for job execution"""
    region: Region
    iso_hour: int = Field(..., ge=0, le=23, description="ISO hour (0-23)")
    sla: SLA
    tier: Tier


class PackageDescriptor(BaseModel):
    """Descriptor for a compute package"""
    package_id: str = Field(..., description="Unique identifier for the package")
    size_estimate_ngh: float = Field(..., gt=0, description="Estimated size in NGH (Network GPU Hours)")
    first_output_estimate_seconds: Optional[int] = Field(None, description="Estimated time to first output in seconds")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Additional package metadata")


class JobCreateRequest(BaseModel):
    """Request model for creating a new job"""
    job_id: str = Field(..., description="Unique identifier for the job")
    window: Window
    package_index: List[PackageDescriptor] = Field(..., min_length=1, description="List of package descriptors")


class JobStatus(str, Enum):
    """Job status enumeration"""
    PENDING = "pending"
    FEASIBLE = "feasible"
    INFEASIBLE = "infeasible"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class FeasibilityResponse(BaseModel):
    """Response model for job feasibility check"""
    ngh_required: float = Field(..., description="Sum of package size estimates in NGH")
    earliest_start: str = Field(..., description="Next feasible window given artifact sizes and Standard prepare rules (ISO 8601 format)")
    voucher_gap: float = Field(..., description="NGH required minus vouchers already deposited for the key")
    milestone_sanity: Dict[str, bool] = Field(
        ...,
        description="Flags for milestone sanity checks: first_output_ok, size_band_ok"
    )


class RelayLink(BaseModel):
    """Relay link for manifest access"""
    manifest_url: str = Field(..., description="URL to access the manifest")
    expires_at: Optional[str] = Field(None, description="Expiration time in ISO 8601 format")


class JobResponse(BaseModel):
    """Response model for job status"""
    job_id: str
    status: JobStatus
    window: Window
    package_index: List[PackageDescriptor]
    created_at: str = Field(..., description="Job creation timestamp in ISO 8601 format")
    relay_links: Optional[List[RelayLink]] = Field(None, description="Relay links for manifests")


# Provider-side models

class NominationRequest(BaseModel):
    """Request model for provider to declare NGH availability"""
    region: Region
    iso_hour: int = Field(..., ge=0, le=23, description="ISO hour (0-23)")
    tier: Tier
    sla: SLA
    ngh_available: float = Field(..., gt=0, description="NGH available for this window")


class NominationResponse(BaseModel):
    """Response model for nomination"""
    nomination_id: str = Field(..., description="Unique identifier for the nomination")
    region: Region
    iso_hour: int
    tier: Tier
    sla: SLA
    ngh_available: float
    created_at: str = Field(..., description="Nomination creation timestamp in ISO 8601 format")


class LotStatus(str, Enum):
    """Lot status enumeration"""
    PENDING = "pending"
    PREPARING = "preparing"
    READY = "ready"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class LotCreateRequest(BaseModel):
    """Request model for creating a lot"""
    window: Window
    job_id: Optional[str] = Field(None, description="Optional job ID to associate with this lot")


class Lot(BaseModel):
    """Model for a compute lot"""
    lot_id: str
    status: LotStatus
    job_id: Optional[str] = Field(None, description="Associated job ID if assigned")
    window: Window
    created_at: str = Field(..., description="Lot creation timestamp in ISO 8601 format")
    prepared_at: Optional[str] = Field(None, description="Preparation ready timestamp in ISO 8601 format")
    completed_at: Optional[str] = Field(None, description="Completion timestamp in ISO 8601 format")
    # Result fields
    output_root: Optional[str] = Field(None, description="Root hash or URI of output")
    item_count: Optional[int] = Field(None, description="Number of items processed")
    wall_time_seconds: Optional[float] = Field(None, description="Wall clock time in seconds")
    raw_gpu_time_seconds: Optional[float] = Field(None, description="Raw GPU time in seconds")
    logs_uri: Optional[str] = Field(None, description="URI to access logs")


class PrepareReadyRequest(BaseModel):
    """Request model for attesting lot readiness"""
    device_ok: bool = Field(..., description="Device is operational")
    driver_ok: bool = Field(..., description="Driver is operational")
    image_pulled: bool = Field(..., description="Container image has been pulled")
    inputs_prefetched: bool = Field(..., description="Inputs have been prefetched")


class PrepareReadyResponse(BaseModel):
    """Response model for prepare ready"""
    lot_id: str
    status: LotStatus
    prepared_at: str = Field(..., description="Preparation ready timestamp in ISO 8601 format")


class ResultRequest(BaseModel):
    """Request model for submitting lot results"""
    output_root: str = Field(..., description="Root hash or URI of output")
    item_count: int = Field(..., ge=0, description="Number of items processed")
    wall_time_seconds: float = Field(..., gt=0, description="Wall clock time in seconds")
    raw_gpu_time_seconds: float = Field(..., gt=0, description="Raw GPU time in seconds")
    logs_uri: Optional[str] = Field(None, description="URI to access logs")


class ResultResponse(BaseModel):
    """Response model for result submission"""
    lot_id: str
    status: LotStatus
    output_root: str
    item_count: int
    wall_time_seconds: float
    raw_gpu_time_seconds: float
    logs_uri: Optional[str]
    completed_at: str = Field(..., description="Completion timestamp in ISO 8601 format")
