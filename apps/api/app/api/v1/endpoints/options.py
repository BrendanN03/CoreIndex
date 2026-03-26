from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.v1.endpoints.auth import get_current_user_optional
from app.repositories.memory.storage import storage
from app.schemas.models import (
    OptionContractCreateRequest,
    OptionContractResponse,
    OptionQuoteRequest,
    OptionQuoteResponse,
    OptionOrderCreateRequest,
    OptionOrderAmendRequest,
    OptionOrderResponse,
    OptionOrderBookResponse,
    OptionTradeResponse,
    RiskSummaryResponse,
    MarginStressResponse,
    LiquidationResponse,
    RiskProfileResponse,
    RiskProfileUpdateRequest,
    KillSwitchUpdateResponse,
    StrategyLimitResponse,
    StrategyLimitUpdateRequest,
    OptionPretradeRequest,
    PretradeCheckResponse,
    TradingSubaccountRiskResponse,
    TradingSubaccountRiskUpdateRequest,
    TradingHierarchyResponse,
    ProductKey,
    Region,
    SLA,
    Tier,
)
from app.services.options_pricing import quote_option


router = APIRouter()


def _build_product_key(
    region: Region, iso_hour: int, sla: SLA, tier: Tier
) -> ProductKey:
    return ProductKey(region=region, iso_hour=iso_hour, sla=sla, tier=tier)


@router.post("/options/quote", response_model=OptionQuoteResponse)
def create_option_quote(request: OptionQuoteRequest):
    return quote_option(request)


@router.post("/options/contracts", response_model=OptionContractResponse)
def create_option_contract(
    request: OptionContractCreateRequest,
    user=Depends(get_current_user_optional),
):
    owner_id = user.user_id if user else None
    try:
        return storage.create_option_contract(request, owner_id=owner_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/options/contracts", response_model=List[OptionContractResponse])
def list_option_contracts(
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
    return storage.list_option_contracts(product_key=product_key, owner_id=owner_id)


@router.post("/options/orders", response_model=OptionOrderResponse)
def create_option_order(
    request: OptionOrderCreateRequest,
    user=Depends(get_current_user_optional),
):
    owner_id = user.user_id if user else None
    try:
        return storage.create_option_order(request, owner_id=owner_id)
    except ValueError as exc:
        detail = str(exc)
        http_status = (
            status.HTTP_404_NOT_FOUND
            if detail == "option_contract_not_found"
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(status_code=http_status, detail=detail) from exc


@router.post("/options/pretrade", response_model=PretradeCheckResponse)
def pretrade_option_order(
    request: OptionPretradeRequest,
    user=Depends(get_current_user_optional),
):
    owner_id = user.user_id if user else None
    return storage.preview_option_pretrade(request, owner_id=owner_id)


@router.get("/options/orders", response_model=List[OptionOrderResponse])
def list_option_orders(
    contract_id: Optional[str] = None,
    user=Depends(get_current_user_optional),
):
    owner_id = user.user_id if user else None
    return storage.list_option_orders(contract_id=contract_id, owner_id=owner_id)


@router.delete("/options/orders/{order_id}", response_model=OptionOrderResponse)
def cancel_option_order(order_id: str, user=Depends(get_current_user_optional)):
    owner_id = user.user_id if user else None
    try:
        order = storage.cancel_option_order(order_id, owner_id=owner_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Order with id '{order_id}' not found",
        )
    return order


@router.put("/options/orders/{order_id}", response_model=OptionOrderResponse)
def amend_option_order(
    order_id: str,
    request: OptionOrderAmendRequest,
    user=Depends(get_current_user_optional),
):
    owner_id = user.user_id if user else None
    try:
        order = storage.amend_option_order(order_id, request, owner_id=owner_id)
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


@router.get("/options/orderbook", response_model=OptionOrderBookResponse)
def get_option_orderbook(contract_id: str):
    try:
        return storage.get_option_orderbook(contract_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/options/trades", response_model=List[OptionTradeResponse])
def list_option_trades(contract_id: str, limit: int = 30):
    return storage.list_option_trades(contract_id=contract_id, limit=max(1, min(limit, 200)))


@router.get("/options/risk", response_model=RiskSummaryResponse)
def get_options_risk_summary(user=Depends(get_current_user_optional)):
    owner_id = user.user_id if user else None
    return storage.get_risk_summary(owner_id)


@router.get("/options/risk/stress", response_model=MarginStressResponse)
def get_options_stress(
    price_shock_pct: float = -0.15,
    option_vol_shock_pct: float = 0.25,
    user=Depends(get_current_user_optional),
):
    owner_id = user.user_id if user else None
    return storage.get_margin_stress(
        owner_id,
        price_shock_pct=price_shock_pct,
        option_vol_shock_pct=option_vol_shock_pct,
    )


@router.post("/options/risk/liquidate", response_model=LiquidationResponse)
def liquidate_account(
    reason: str = "manual_liquidation",
    user=Depends(get_current_user_optional),
):
    owner_id = user.user_id if user else None
    return storage.liquidate_account(owner_id, reason=reason)


@router.get("/options/risk/profile", response_model=RiskProfileResponse)
def get_risk_profile(user=Depends(get_current_user_optional)):
    owner_id = user.user_id if user else None
    return storage.get_risk_profile(owner_id)


@router.put("/options/risk/profile", response_model=RiskProfileResponse)
def update_risk_profile(
    request: RiskProfileUpdateRequest,
    user=Depends(get_current_user_optional),
):
    owner_id = user.user_id if user else None
    return storage.update_risk_profile(owner_id, request)


@router.post("/options/risk/kill-switch", response_model=KillSwitchUpdateResponse)
def set_kill_switch(
    enabled: bool,
    reason: str = "manual_toggle",
    user=Depends(get_current_user_optional),
):
    owner_id = user.user_id if user else None
    return storage.set_kill_switch(owner_id, enabled=enabled, reason=reason)


@router.get("/options/risk/strategies", response_model=List[StrategyLimitResponse])
def list_strategy_limits(user=Depends(get_current_user_optional)):
    owner_id = user.user_id if user else None
    return storage.list_strategy_limits(owner_id)


@router.put("/options/risk/strategies", response_model=StrategyLimitResponse)
def upsert_strategy_limit(
    request: StrategyLimitUpdateRequest,
    user=Depends(get_current_user_optional),
):
    owner_id = user.user_id if user else None
    return storage.upsert_strategy_limit(owner_id, request)


@router.get("/options/risk/subaccounts", response_model=List[TradingSubaccountRiskResponse])
def list_subaccount_limits(user=Depends(get_current_user_optional)):
    owner_id = user.user_id if user else None
    return storage.list_subaccount_limits(owner_id)


@router.put("/options/risk/subaccounts", response_model=TradingSubaccountRiskResponse)
def upsert_subaccount_limit(
    request: TradingSubaccountRiskUpdateRequest,
    user=Depends(get_current_user_optional),
):
    owner_id = user.user_id if user else None
    return storage.upsert_subaccount_limit(owner_id, request)


@router.get("/options/risk/hierarchy", response_model=TradingHierarchyResponse)
def get_trading_hierarchy(user=Depends(get_current_user_optional)):
    owner_id = user.user_id if user else None
    return storage.get_trading_hierarchy(owner_id)
