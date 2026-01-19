"""
In-memory storage for jobs. Can be replaced with a database in production.
"""
from typing import Dict, Optional
from app.models import JobCreateRequest, JobResponse, JobStatus, Window, PackageDescriptor
from datetime import datetime


class JobStorage:
    """Simple in-memory job storage"""
    
    def __init__(self):
        self._jobs: Dict[str, JobResponse] = {}
        self._vouchers: Dict[str, float] = {}  # key -> voucher amount in NGH
    
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


# Global storage instance
storage = JobStorage()
