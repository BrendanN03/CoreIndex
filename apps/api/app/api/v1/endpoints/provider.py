from fastapi import APIRouter, HTTPException, status

from app.repositories.memory.storage import storage
from app.schemas.models import (
    Lot,
    LotCreateRequest,
    NominationRequest,
    NominationResponse,
    PrepareReadyRequest,
    PrepareReadyResponse,
    ResultRequest,
    ResultResponse,
)


router = APIRouter()


@router.post(
    "/nominations", response_model=NominationResponse, status_code=status.HTTP_201_CREATED
)
def create_nomination(request: NominationRequest):
    """
    Provider endpoint: Declare NGH availability per (region, hour, tier, SLA).
    """
    nomination = storage.create_nomination(request)
    return nomination


@router.post("/lots", response_model=Lot, status_code=status.HTTP_201_CREATED)
def create_lot(request: LotCreateRequest):
    """
    Provider endpoint: Create a new lot for execution.
    """
    lot = storage.create_lot(request.window, request.job_id)
    return lot


@router.post("/lots/{lot_id}/prepare_ready", response_model=PrepareReadyResponse)
def attest_prepare_ready(lot_id: str, request: PrepareReadyRequest):
    """
    Provider endpoint: Attest readiness for a lot.
    """
    lot = storage.get_lot(lot_id)
    if not lot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Lot with id '{lot_id}' not found",
        )

    if not all(
        [
            request.device_ok,
            request.driver_ok,
            request.image_pulled,
            request.inputs_prefetched,
        ]
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="All readiness checks must be true",
        )

    updated_lot = storage.update_lot_prepare_ready(lot_id)
    if not updated_lot:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update lot status",
        )

    return PrepareReadyResponse(
        lot_id=lot_id,
        status=updated_lot.status,
        prepared_at=updated_lot.prepared_at or "",
    )


@router.post("/lots/{lot_id}/result", response_model=ResultResponse)
def submit_result(lot_id: str, request: ResultRequest):
    """
    Provider endpoint: Submit execution results for a lot.
    """
    lot = storage.get_lot(lot_id)
    if not lot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Lot with id '{lot_id}' not found",
        )

    result_data = {
        "output_root": request.output_root,
        "item_count": request.item_count,
        "wall_time_seconds": request.wall_time_seconds,
        "raw_gpu_time_seconds": request.raw_gpu_time_seconds,
        "logs_uri": request.logs_uri,
    }
    updated_lot = storage.update_lot_result(lot_id, result_data)
    if not updated_lot:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update lot with result",
        )

    return ResultResponse(
        lot_id=lot_id,
        status=updated_lot.status,
        output_root=request.output_root,
        item_count=request.item_count,
        wall_time_seconds=request.wall_time_seconds,
        raw_gpu_time_seconds=request.raw_gpu_time_seconds,
        logs_uri=request.logs_uri,
        completed_at=updated_lot.completed_at or "",
    )

