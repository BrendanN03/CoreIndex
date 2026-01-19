"""
In-memory storage for jobs, nominations, and lots. Can be replaced with a database in production.
"""
from typing import Dict, Optional
from app.models import (
    JobCreateRequest, JobResponse, JobStatus, Window, PackageDescriptor,
    NominationRequest, NominationResponse, Lot, LotStatus, PrepareReadyRequest
)
from datetime import datetime
import uuid


class JobStorage:
    """Simple in-memory job storage"""
    
    def __init__(self):
        self._jobs: Dict[str, JobResponse] = {}
        self._vouchers: Dict[str, float] = {}  # key -> voucher amount in NGH
        self._nominations: Dict[str, NominationResponse] = {}
        self._lots: Dict[str, Lot] = {}
    
    def create_job(self, request: JobCreateRequest) -> JobResponse:
        """Create a new job"""
        job = JobResponse(
            job_id=request.job_id,
            status=JobStatus.PENDING,
            window=request.window,
            package_index=request.package_index,
            created_at=datetime.utcnow().isoformat() + "Z",
            relay_links=None
        )
        self._jobs[request.job_id] = job
        return job
    
    def get_job(self, job_id: str) -> Optional[JobResponse]:
        """Get a job by ID"""
        return self._jobs.get(job_id)
    
    def get_voucher_balance(self, key: str) -> float:
        """Get voucher balance for a given key"""
        return self._vouchers.get(key, 0.0)
    
    def set_voucher_balance(self, key: str, amount: float):
        """Set voucher balance for a given key (for testing/demo purposes)"""
        self._vouchers[key] = amount
    
    def create_nomination(self, request: NominationRequest) -> NominationResponse:
        """Create a new nomination"""
        nomination_id = str(uuid.uuid4())
        nomination = NominationResponse(
            nomination_id=nomination_id,
            region=request.region,
            iso_hour=request.iso_hour,
            tier=request.tier,
            sla=request.sla,
            ngh_available=request.ngh_available,
            created_at=datetime.utcnow().isoformat() + "Z"
        )
        self._nominations[nomination_id] = nomination
        return nomination
    
    def get_nomination(self, nomination_id: str) -> Optional[NominationResponse]:
        """Get a nomination by ID"""
        return self._nominations.get(nomination_id)
    
    def create_lot(self, window: Window, job_id: Optional[str] = None) -> Lot:
        """Create a new lot"""
        lot_id = str(uuid.uuid4())
        lot = Lot(
            lot_id=lot_id,
            status=LotStatus.PENDING,
            job_id=job_id,
            window=window,
            created_at=datetime.utcnow().isoformat() + "Z",
            prepared_at=None,
            completed_at=None,
            output_root=None,
            item_count=None,
            wall_time_seconds=None,
            raw_gpu_time_seconds=None,
            logs_uri=None
        )
        self._lots[lot_id] = lot
        return lot
    
    def get_lot(self, lot_id: str) -> Optional[Lot]:
        """Get a lot by ID"""
        return self._lots.get(lot_id)
    
    def update_lot_prepare_ready(self, lot_id: str) -> Optional[Lot]:
        """Update lot status to ready after preparation"""
        lot = self._lots.get(lot_id)
        if lot:
            lot.status = LotStatus.READY
            lot.prepared_at = datetime.utcnow().isoformat() + "Z"
        return lot
    
    def update_lot_result(self, lot_id: str, result_data: dict) -> Optional[Lot]:
        """Update lot with result data"""
        lot = self._lots.get(lot_id)
        if lot:
            lot.status = LotStatus.COMPLETED
            lot.completed_at = datetime.utcnow().isoformat() + "Z"
            lot.output_root = result_data.get("output_root")
            lot.item_count = result_data.get("item_count")
            lot.wall_time_seconds = result_data.get("wall_time_seconds")
            lot.raw_gpu_time_seconds = result_data.get("raw_gpu_time_seconds")
            lot.logs_uri = result_data.get("logs_uri")
        return lot


# Global storage instance
storage = JobStorage()
