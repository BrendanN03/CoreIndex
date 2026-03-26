from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.v1.endpoints.auth import get_current_user_optional
from app.repositories.memory.storage import storage
from app.schemas.models import (
    ExchangeOrderBookResponse,
    ExchangeOrderAmendRequest,
    ExchangeOrderCreateRequest,
    ExchangeOrderResponse,
    ExchangeTradeResponse,
    ExchangePretradeRequest,
    PretradeCheckResponse,
    ProductKey,
    Region,
    SLA,
    Tier,
)


router = APIRouter()


def _build_product_key(
    region: Region, iso_hour: int, sla: SLA, tier: Tier
) -> ProductKey:
    return ProductKey(region=region, iso_hour=iso_hour, sla=sla, tier=tier)


@router.post("/exchange/orders", response_model=ExchangeOrderResponse)
def create_exchange_order(
    request: ExchangeOrderCreateRequest,
    user=Depends(get_current_user_optional),
):
    owner_id = user.user_id if user else None
    try:
        return storage.create_exchange_order(request, owner_id=owner_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/exchange/pretrade", response_model=PretradeCheckResponse)
def pretrade_exchange_order(
    request: ExchangePretradeRequest,
    user=Depends(get_current_user_optional),
):
    owner_id = user.user_id if user else None
    return storage.preview_exchange_pretrade(request, owner_id=owner_id)


@router.get("/exchange/orders", response_model=List[ExchangeOrderResponse])
def list_exchange_orders(
    region: Optional[Region] = None,
    iso_hour: Optional[int] = None,
    sla: Optional[SLA] = None,
    tier: Optional[Tier] = None,
    user=Depends(get_current_user_optional),
):
    product_key = None
    if region is not None and iso_hour is not None and sla is not None and tier is not None:
        product_key = _build_product_key(region, iso_hour, sla, tier)
    owner_id = user.user_id if user else None
    return storage.list_exchange_orders(product_key=product_key, owner_id=owner_id)


@router.get("/exchange/orderbook", response_model=ExchangeOrderBookResponse)
def get_exchange_orderbook(
    region: Region,
    iso_hour: int,
    sla: SLA,
    tier: Tier,
):
    return storage.get_exchange_orderbook(_build_product_key(region, iso_hour, sla, tier))


@router.get("/exchange/trades", response_model=List[ExchangeTradeResponse])
def list_exchange_trades(
    region: Region,
    iso_hour: int,
    sla: SLA,
    tier: Tier,
    limit: int = 30,
):
    key = _build_product_key(region, iso_hour, sla, tier)
    return storage.list_exchange_trades(product_key=key, limit=max(1, min(limit, 200)))


@router.delete("/exchange/orders/{order_id}", response_model=ExchangeOrderResponse)
def cancel_exchange_order(order_id: str, user=Depends(get_current_user_optional)):
    owner_id = user.user_id if user else None
    try:
        order = storage.cancel_exchange_order(order_id, owner_id=owner_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Order with id '{order_id}' not found",
        )
    return order


@router.put("/exchange/orders/{order_id}", response_model=ExchangeOrderResponse)
def amend_exchange_order(
    order_id: str,
    request: ExchangeOrderAmendRequest,
    user=Depends(get_current_user_optional),
):
    owner_id = user.user_id if user else None
    try:
        order = storage.amend_exchange_order(order_id, request, owner_id=owner_id)
    except ValueError as exc:
        detail = str(exc)
        http_status = (
            status.HTTP_403_FORBIDDEN
            if "owner_mismatch" in detail
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(status_code=http_status, detail=detail) from exc
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Order with id '{order_id}' not found",
        )
    return order
