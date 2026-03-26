from typing import List

from fastapi import APIRouter, HTTPException, status

from app.repositories.memory.storage import storage
from app.schemas.models import (
    VoucherBalanceResponse,
    VoucherDepositRequest,
    VoucherDepositResponse,
)


router = APIRouter()


@router.get("/vouchers", response_model=List[VoucherBalanceResponse])
def list_vouchers():
    """List voucher balances by product key."""
    return storage.list_voucher_balances()


@router.post(
    "/vouchers/deposit",
    response_model=VoucherDepositResponse,
    status_code=status.HTTP_201_CREATED,
)
def deposit_vouchers(request: VoucherDepositRequest):
    """Escrow vouchers to a job for the matching product key."""
    if not storage.get_job(request.job_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job with id '{request.job_id}' not found",
        )
    try:
        return storage.deposit_vouchers(
            job_id=request.job_id,
            product_key=request.product_key,
            amount_ngh=request.amount_ngh,
        )
    except ValueError as exc:
        if str(exc) == "insufficient_voucher_balance":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Insufficient voucher balance for the selected product key",
            ) from exc
        raise
