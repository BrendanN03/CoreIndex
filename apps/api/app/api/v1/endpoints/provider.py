from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.v1.endpoints.auth import get_current_user_optional
from app.repositories.memory.storage import storage
from app.schemas.models import (
    Lot,
    LotCreateRequest,
    NominationRequest,
    NominationResponse,
    MarketplaceGpuListingResponse,
    ProviderSlaSummaryResponse,
    ProviderExecutionMetricsResponse,
    ProviderFleetOverviewResponse,
    PrepareReadyRequest,
    PrepareReadyResponse,
    ResultRequest,
    ResultResponse,
    SessionReadyRequest,
    CollectiveSessionResponse,
)


router = APIRouter()


@router.get("/lots", response_model=List[Lot])
def list_lots(user=Depends(get_current_user_optional)):
    """
    List lots (newest first).
    If the request includes a valid Bearer token, only that user's (provider's) lots are returned.
    Otherwise all lots are returned (for demo/backward compatibility).
    """
    provider_id = user.user_id if user else None
    return storage.list_lots(provider_id=provider_id)


@router.post(
    "/nominations", response_model=NominationResponse, status_code=status.HTTP_201_CREATED
)
def create_nomination(
    request: NominationRequest,
    user=Depends(get_current_user_optional),
):
    """
    Provider endpoint: Declare NGH availability per (region, hour, tier, SLA).
    """
    provider_id = user.user_id if user else None
    nomination = storage.create_nomination_for_provider(request, provider_id=provider_id)
    return nomination


@router.get("/provider/listings", response_model=List[MarketplaceGpuListingResponse])
def list_provider_marketplace_listings():
    """
    Buyer-facing endpoint: live GPU listings sourced from provider nominations.
    """
    return storage.list_marketplace_listings()


@router.post("/lots", response_model=Lot, status_code=status.HTTP_201_CREATED)
def create_lot(request: LotCreateRequest, user=Depends(get_current_user_optional)):
    """
    Provider endpoint: Create a new lot for execution.
    If the request includes a valid Bearer token, the lot is tied to that user (provider_id).
    """
    provider_id = user.user_id if user else None
    lot = storage.create_lot(request.window, request.job_id, provider_id=provider_id)
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


@router.post("/sessions/{session_id}/ready", response_model=CollectiveSessionResponse)
def attest_session_ready(session_id: str, request: SessionReadyRequest):
    try:
        return storage.attest_collective_session_ready(session_id, request.member_id)
    except ValueError as exc:
        msg = str(exc)
        if msg == "session_not_found":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg) from exc
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg) from exc


@router.get("/provider/sla", response_model=ProviderSlaSummaryResponse)
def get_provider_sla(user=Depends(get_current_user_optional)):
    owner_id = user.user_id if user else None
    return storage.get_provider_sla_summary(owner_id)


@router.get("/provider/execution-metrics", response_model=ProviderExecutionMetricsResponse)
def get_provider_execution_metrics(user=Depends(get_current_user_optional)):
    owner_id = user.user_id if user else None
    return storage.get_provider_execution_metrics(owner_id)


@router.get("/provider/fleet", response_model=ProviderFleetOverviewResponse)
def get_provider_fleet(user=Depends(get_current_user_optional)):
    owner_id = user.user_id if user else None
    return storage.get_provider_fleet_overview(owner_id)

