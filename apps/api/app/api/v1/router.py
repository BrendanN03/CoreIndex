from fastapi import APIRouter

from app.api.v1.endpoints import (
    auth,
    exchange,
    factoring,
    jobs,
    judge_demo,
    market,
    options,
    platform,
    provider,
    qc,
    sessions,
    settlement,
    vouchers,
)


router = APIRouter()

router.include_router(auth.router, tags=["auth"])
router.include_router(factoring.router, tags=["factoring"])
router.include_router(exchange.router, tags=["exchange"])
router.include_router(market.router, tags=["market"])
router.include_router(options.router, tags=["options"])
router.include_router(jobs.router, tags=["jobs"])
router.include_router(provider.router, tags=["provider"])
router.include_router(qc.router, tags=["qc"])
router.include_router(sessions.router, tags=["sessions"])
router.include_router(settlement.router, tags=["settlement"])
router.include_router(vouchers.router, tags=["vouchers"])
router.include_router(platform.router, tags=["platform"])
router.include_router(judge_demo.router, prefix="/demo", tags=["judge-demo"])
