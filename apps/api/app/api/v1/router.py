from fastapi import APIRouter

from app.api.v1.endpoints import auth, factoring, jobs, provider, qc


router = APIRouter()

router.include_router(auth.router, tags=["auth"])
router.include_router(factoring.router, tags=["factoring"])
router.include_router(jobs.router, tags=["jobs"])
router.include_router(provider.router, tags=["provider"])
router.include_router(qc.router, tags=["qc"])

