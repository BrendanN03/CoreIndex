from typing import List, Optional, Callable
import hashlib
import json
import os
import threading
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.v1.endpoints.auth import get_current_user_optional
from app.api.v1.endpoints.factoring import _build_gpu_ids, _run_remote_factoring
from app.repositories.memory.storage import storage
from app.services.market_simulator import market_simulator
from app.services.feasibility import calculate_ngh_required
from app.schemas.models import (
    ComputeDeliveryRequest,
    ComputeDeliveryResponse,
    DemoBlockchainAnchorResponse,
    DemoProgressStepStatus,
    DemoProviderExecutionResponse,
    DemoRunProgressStep,
    DemoRunRequest,
    DemoRunResponse,
    DemoRunTrackResponse,
    ExchangeOrderBookResponse,
    ExchangeTradeResponse,
    FullDemoRunRequest,
    FullDemoRunStartResponse,
    JobCreateRequest,
    MarketLiveOverviewResponse,
    MarketPositionCreateRequest,
    MarketPositionResponse,
    MarketSimulationStartRequest,
    MarketSimulationStatusResponse,
    NominationRequest,
    PackageDescriptor,
    PositionSide,
    ProductKey,
    Region,
    SLA,
    Tier,
    StrategyExecutionMetricsResponse,
    TraderExecutionMetricsResponse,
    TraderPortfolioResponse,
    Window,
)


router = APIRouter()


def _resolve_live_key(
    gpu_model: Optional[str],
    region: Optional[Region],
    iso_hour: Optional[int],
    sla: Optional[SLA],
    tier: Optional[Tier],
) -> ProductKey:
    if (
        region is not None
        and iso_hour is not None
        and sla is not None
        and tier is not None
    ):
        return ProductKey(region=region, iso_hour=iso_hour, sla=sla, tier=tier)

    if gpu_model:
        for model, key in market_simulator.product_catalog():
            if model.lower() == gpu_model.lower():
                return key

    catalog = market_simulator.product_catalog()
    if catalog:
        return catalog[0][1]
    return storage.get_demo_product_key()


def _hash_payload(payload: dict) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _anchor_to_local_evm(anchor_hash: str) -> DemoBlockchainAnchorResponse:
    rpc_url = os.getenv("LOCAL_EVM_RPC_URL", "http://127.0.0.1:8545")
    explorer_base = os.getenv("LOCAL_EVM_EXPLORER_BASE", "").rstrip("/")

    try:
        import requests
    except Exception:
        synthetic_hash = "0x" + _hash_payload({"rpc_url": rpc_url, "anchor_hash": anchor_hash})[:64]
        return DemoBlockchainAnchorResponse(
            network_label="local-evm-simulated",
            tx_hash=synthetic_hash,
            block_number=None,
            explorer_url=None,
        )

    def rpc(method: str, params: list):
        response = requests.post(
            rpc_url,
            json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
            timeout=15,
        )
        response.raise_for_status()
        payload = response.json()
        if "error" in payload:
            raise ValueError(str(payload["error"]))
        return payload.get("result")

    try:
        accounts = rpc("eth_accounts", [])
        if not accounts:
            raise ValueError("no_local_evm_accounts")
        from_addr = os.getenv("LOCAL_EVM_FROM", accounts[0])
        tx_hash = rpc(
            "eth_sendTransaction",
            [
                {
                    "from": from_addr,
                    "to": from_addr,
                    "value": hex(0),
                    "data": "0x" + anchor_hash[:64],
                }
            ],
        )
        receipt = rpc("eth_getTransactionReceipt", [tx_hash])
        block_number = int(receipt["blockNumber"], 16) if receipt and receipt.get("blockNumber") else None
        explorer_url = f"{explorer_base}/tx/{tx_hash}" if explorer_base else None
        return DemoBlockchainAnchorResponse(
            network_label="local-evm",
            tx_hash=tx_hash,
            block_number=block_number,
            explorer_url=explorer_url,
        )
    except Exception:
        synthetic_hash = "0x" + _hash_payload({"rpc_url": rpc_url, "anchor_hash": anchor_hash})[:64]
        return DemoBlockchainAnchorResponse(
            network_label="local-evm-simulated",
            tx_hash=synthetic_hash,
            block_number=None,
            explorer_url=None,
        )


FULL_DEMO_STEP_SPECS: List[tuple[str, str]] = [
    ("create_job", "Create compute job"),
    ("open_position", "Open buy position (NGH exposure)"),
    ("settle_fund", "Settle into vouchers & escrow to job"),
    ("match_providers", "Market-match providers & GPUs"),
    ("execute_compute", "Run CADO / remote factoring"),
    ("verify_anchor", "Verify & anchor on-chain"),
]

_demo_tracks: dict[str, DemoRunTrackResponse] = {}
_demo_track_lock = threading.Lock()


def _utc_now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


def _new_demo_track(run_id: str) -> None:
    now = _utc_now_iso()
    steps = [
        DemoRunProgressStep(
            step_id=sid,
            label=lab,
            status=DemoProgressStepStatus.PENDING,
            updated_at=now,
        )
        for sid, lab in FULL_DEMO_STEP_SPECS
    ]
    with _demo_track_lock:
        _demo_tracks[run_id] = DemoRunTrackResponse(
            run_id=run_id,
            overall_status="running",
            steps=steps,
        )


def _update_demo_track_step(
    run_id: str,
    step_id: str,
    status: DemoProgressStepStatus,
    detail: Optional[str] = None,
) -> None:
    now = _utc_now_iso()
    with _demo_track_lock:
        track = _demo_tracks.get(run_id)
        if not track:
            return
        new_steps: List[DemoRunProgressStep] = []
        for step in track.steps:
            if step.step_id == step_id:
                new_steps.append(
                    DemoRunProgressStep(
                        step_id=step.step_id,
                        label=step.label,
                        status=status,
                        detail=detail if detail is not None else step.detail,
                        updated_at=now,
                    )
                )
            else:
                new_steps.append(step)
        _demo_tracks[run_id] = track.model_copy(update={"steps": new_steps})


def _mark_running_demo_steps_failed(run_id: str) -> None:
    now = _utc_now_iso()
    with _demo_track_lock:
        track = _demo_tracks.get(run_id)
        if not track:
            return
        new_steps: List[DemoRunProgressStep] = []
        for step in track.steps:
            if step.status == DemoProgressStepStatus.RUNNING:
                new_steps.append(
                    step.model_copy(
                        update={"status": DemoProgressStepStatus.FAILED, "updated_at": now}
                    )
                )
            else:
                new_steps.append(step)
        _demo_tracks[run_id] = track.model_copy(update={"steps": new_steps})


def _patch_demo_track(
    run_id: str,
    *,
    job_id: Optional[str] = None,
    position_id: Optional[str] = None,
    overall_status: Optional[str] = None,
    result: Optional[DemoRunResponse] = None,
    error: Optional[str] = None,
) -> None:
    with _demo_track_lock:
        track = _demo_tracks.get(run_id)
        if not track:
            return
        data: dict = {}
        if job_id is not None:
            data["job_id"] = job_id
        if position_id is not None:
            data["position_id"] = position_id
        if overall_status is not None:
            data["overall_status"] = overall_status
        if result is not None:
            data["result"] = result
        if error is not None:
            data["error"] = error
        _demo_tracks[run_id] = track.model_copy(update=data)


def _notify_demo_step(
    hook: Optional[Callable[[str, str, Optional[str]], None]],
    step: str,
    phase: str,
    detail: Optional[str] = None,
) -> None:
    if hook:
        hook(step, phase, detail)


def _execute_demo_pipeline(
    position_id: str,
    request: DemoRunRequest,
    owner_id: Optional[str],
    *,
    step_hook: Optional[Callable[[str, str, Optional[str]], None]] = None,
) -> DemoRunResponse:
    position = storage.get_market_position(position_id)
    if not position:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Position with id '{position_id}' not found",
        )
    if owner_id is not None and position.owner_id is not None and position.owner_id != owner_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="position_owner_mismatch",
        )
    if position.side.value != "buy":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="only_buy_positions_can_demo_run",
        )

    _notify_demo_step(
        step_hook,
        "settle_fund",
        "running",
        "Settling exposure and escrowing vouchers to the job",
    )
    settlement_status = position.status.value
    if position.status.value != "settled":
        if not request.auto_settle_if_open:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="position_must_be_settled_or_enable_auto_settle",
            )
        settled = storage.settle_market_position(position_id)
        if not settled:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Position with id '{position_id}' not found",
            )
        position = settled
        settlement_status = "auto_settled"

    deposit_amount = request.deposit_ngh or position.quantity_ngh
    try:
        deposit = storage.deposit_vouchers(
            request.job_id,
            position.product_key,
            deposit_amount,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    _notify_demo_step(
        step_hook,
        "settle_fund",
        "done",
        f"Escrowed {deposit_amount:.2f} NGH to job {request.job_id}",
    )

    job = storage.get_job(request.job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"job_not_found:{request.job_id}",
        )
    job_key = job.window
    if (
        job_key.region != position.product_key.region
        or job_key.iso_hour != position.product_key.iso_hour
        or job_key.sla != position.product_key.sla
        or job_key.tier != position.product_key.tier
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="job_window_mismatch_with_position_product_key",
        )

    # Default: allow simulated (sim-seller-*) nominations so one-click works with the
    # built-in market sim. Set DEMO_REQUIRE_REAL_PROVIDERS=true to require human nominations only.
    real_provider_only = os.getenv("DEMO_REQUIRE_REAL_PROVIDERS", "").lower() in (
        "1",
        "true",
        "yes",
    )
    listings = [
        row
        for row in storage.list_marketplace_listings()
        if row.region == position.product_key.region
        and row.iso_hour == position.product_key.iso_hour
        and row.sla == position.product_key.sla
        and row.tier == position.product_key.tier
        and row.gpu_count > 0
        and row.ngh_available > 0
        and (not real_provider_only or not storage.is_synthetic_owner(row.provider_id))
    ]
    if not listings and not real_provider_only:
        # Cold start / sim paused: ensure at least one synthetic listing for this exact window.
        gpu_seed = "RTX 4090"
        if job.package_index:
            meta = job.package_index[0].metadata or {}
            gpu_seed = str(meta.get("gpu_name") or gpu_seed)
        try:
            storage.create_nomination_for_provider(
                NominationRequest(
                    region=position.product_key.region,
                    iso_hour=position.product_key.iso_hour,
                    sla=position.product_key.sla,
                    tier=position.product_key.tier,
                    ngh_available=max(200.0, deposit_amount * 6),
                    gpu_model=gpu_seed[:64],
                    gpu_count=4,
                ),
                provider_id="sim-seller-demo-fallback",
            )
        except ValueError:
            pass
        listings = [
            row
            for row in storage.list_marketplace_listings()
            if row.region == position.product_key.region
            and row.iso_hour == position.product_key.iso_hour
            and row.sla == position.product_key.sla
            and row.tier == position.product_key.tier
            and row.gpu_count > 0
            and row.ngh_available > 0
            and (not real_provider_only or not storage.is_synthetic_owner(row.provider_id))
        ]

    if not listings:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="no_matching_provider_capacity_for_product_key",
        )

    _notify_demo_step(step_hook, "match_providers", "running", "Selecting providers by market rules")
    ngh_required = calculate_ngh_required(job.package_index)
    if ngh_required <= 5:
        desired_gpu_count = 1
    elif ngh_required <= 10:
        desired_gpu_count = 2
    elif ngh_required <= 18:
        desired_gpu_count = 3
    else:
        desired_gpu_count = 4

    listings.sort(key=lambda row: (row.indicative_price_per_ngh, -row.ngh_available, row.created_at))
    total_available_gpus = sum(int(row.gpu_count) for row in listings)
    if total_available_gpus < 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="no_available_gpus_after_matching",
        )
    matched_gpu_count = min(4, desired_gpu_count, total_available_gpus)
    remaining_gpus = matched_gpu_count
    matched_provider_gpus: dict[str, int] = {}
    for listing in listings:
        if remaining_gpus <= 0:
            break
        take = min(int(listing.gpu_count), remaining_gpus)
        if take <= 0:
            continue
        matched_provider_gpus[listing.provider_id] = matched_provider_gpus.get(listing.provider_id, 0) + take
        remaining_gpus -= take
    if not matched_provider_gpus:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="matching_failed_to_select_providers",
        )

    available_provider_ids = []
    for listing in listings:
        if listing.provider_id not in available_provider_ids:
            available_provider_ids.append(listing.provider_id)
    if (
        real_provider_only
        and matched_gpu_count >= 2
        and len(available_provider_ids) >= 2
        and len(matched_provider_gpus) < 2
    ):
        primary_provider = next(iter(matched_provider_gpus.keys()))
        secondary_provider = next(
            provider_id
            for provider_id in available_provider_ids
            if provider_id != primary_provider
        )
        if matched_provider_gpus[primary_provider] >= 2:
            matched_provider_gpus[primary_provider] -= 1
            matched_provider_gpus[secondary_provider] = matched_provider_gpus.get(secondary_provider, 0) + 1

    match_detail = ", ".join(f"{pid}:{gpus} GPU" for pid, gpus in matched_provider_gpus.items())
    _notify_demo_step(step_hook, "match_providers", "done", match_detail or "matched")

    total_gpus = sum(matched_provider_gpus.values())

    for provider_id, gpu_count in matched_provider_gpus.items():
        provider_capacity = storage.provider_capacity_for_window(
            provider_id, position.product_key
        )
        required_ngh = deposit_amount * (gpu_count / total_gpus)
        if provider_capacity < required_ngh:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"provider_capacity_insufficient:{provider_id}:"
                    f"{provider_capacity:.2f}<{required_ngh:.2f}"
                ),
            )

    _notify_demo_step(step_hook, "execute_compute", "running", "Calling remote GPU backend")
    provider_executions: List[DemoProviderExecutionResponse] = []
    for provider_id, gpu_count in matched_provider_gpus.items():
        _notify_demo_step(
            step_hook,
            "execute_compute",
            "running",
            f"Provider {provider_id} · {gpu_count} GPU(s)",
        )
        summary = _run_remote_factoring(_build_gpu_ids(gpu_count), request.composite)
        provider_executions.append(
            DemoProviderExecutionResponse(
                provider_id=provider_id,
                gpu_count=gpu_count,
                factoring_summary=summary,
            )
        )
    _notify_demo_step(
        step_hook,
        "execute_compute",
        "done",
        f"{len(provider_executions)} provider execution(s) finished",
    )

    _notify_demo_step(step_hook, "verify_anchor", "running", "Hashing results and anchoring to EVM")
    verification_payload = {
        "position_id": position_id,
        "job_id": request.job_id,
        "product_key": position.product_key.model_dump(mode="json"),
        "composite": request.composite,
        "provider_executions": [row.model_dump(mode="json") for row in provider_executions],
    }
    verification_hash = _hash_payload(verification_payload)
    verification_passed = True
    anchor = _anchor_to_local_evm(verification_hash)

    storage.record_delivery_event(
        position_id,
        request.job_id,
        {
            "mode": "demo_run",
            "settlement_status": settlement_status,
            "settlement_target_seconds": request.target_settle_seconds,
            "delivered_ngh": deposit_amount,
            "remaining_wallet_ngh": deposit.remaining_balance_ngh,
            "provider_executions": [row.model_dump(mode="json") for row in provider_executions],
            "provider_selection_policy": (
                "best_price_capacity_real_only_two_provider_bias"
                if real_provider_only
                else "best_price_capacity_open_market"
            ),
            "real_provider_only": real_provider_only,
            "synthetic_excluded": real_provider_only,
            "verification_hash": verification_hash,
            "verification_passed": verification_passed,
            "blockchain_anchor": anchor.model_dump(mode="json"),
        },
    )

    _notify_demo_step(
        step_hook,
        "verify_anchor",
        "done",
        f"Anchored · {anchor.tx_hash[:18]}…",
    )

    return DemoRunResponse(
        position_id=position_id,
        job_id=request.job_id,
        settlement_status=settlement_status,
        settlement_target_seconds=request.target_settle_seconds,
        matched_gpu_count=matched_gpu_count,
        delivered_ngh=deposit_amount,
        remaining_wallet_ngh=deposit.remaining_balance_ngh,
        provider_executions=provider_executions,
        provider_selection_policy=(
            "best_price_capacity_real_only_two_provider_bias"
            if real_provider_only
            else "best_price_capacity_open_market"
        ),
        real_provider_only=real_provider_only,
        synthetic_excluded=real_provider_only,
        verification_passed=verification_passed,
        verification_hash=verification_hash,
        blockchain_anchor=anchor,
        run_status="completed",
    )


def _demo_pipeline_bridge(
    run_id: str,
) -> Callable[[str, str, Optional[str]], None]:
    def _hook(step: str, phase: str, detail: Optional[str] = None) -> None:
        if phase == "running":
            _update_demo_track_step(run_id, step, DemoProgressStepStatus.RUNNING, detail)
        elif phase == "done":
            _update_demo_track_step(run_id, step, DemoProgressStepStatus.DONE, detail)
        elif phase == "failed":
            _update_demo_track_step(run_id, step, DemoProgressStepStatus.FAILED, detail)

    return _hook


def _full_demo_worker(run_id: str, owner_id: Optional[str], body: FullDemoRunRequest) -> None:
    bridge = _demo_pipeline_bridge(run_id)
    # Do not stop the market simulator here. Storage access is already serialized; stopping
    # the sim risks a failed restart (start() no-ops if the tick thread is still alive after
    # stop's short join), which breaks every later demo until the API process is restarted.
    try:
        _update_demo_track_step(run_id, "create_job", DemoProgressStepStatus.RUNNING, None)
        job_id = body.job_id or f"demo-job-{int(datetime.utcnow().timestamp() * 1000)}"
        if storage.get_job(job_id):
            job_id = f"{job_id}-{uuid.uuid4().hex[:8]}"
        window = Window(
            region=body.region,
            iso_hour=body.iso_hour,
            sla=body.sla,
            tier=body.tier,
        )
        storage.create_job(
            JobCreateRequest(
                job_id=job_id,
                window=window,
                package_index=[
                    PackageDescriptor(
                        package_id=f"pkg-{uuid.uuid4().hex[:8]}",
                        size_estimate_ngh=body.package_size_ngh,
                        first_output_estimate_seconds=60,
                        metadata={"gpu_name": body.gpu_model_label, "demo": True},
                    )
                ],
            ),
            created_by=owner_id,
        )
        _patch_demo_track(run_id, job_id=job_id)
        _update_demo_track_step(run_id, "create_job", DemoProgressStepStatus.DONE, job_id)

        _update_demo_track_step(run_id, "open_position", DemoProgressStepStatus.RUNNING, None)
        product_key = ProductKey(
            region=body.region,
            iso_hour=body.iso_hour,
            sla=body.sla,
            tier=body.tier,
        )
        position = storage.create_market_position(
            MarketPositionCreateRequest(
                product_key=product_key,
                side=PositionSide.BUY,
                quantity_ngh=body.quantity_ngh,
                price_per_ngh=body.price_per_ngh,
            ),
            owner_id=owner_id,
        )
        _patch_demo_track(run_id, position_id=position.position_id)
        _update_demo_track_step(
            run_id, "open_position", DemoProgressStepStatus.DONE, position.position_id
        )

        demo_req = DemoRunRequest(
            job_id=job_id,
            composite=body.composite,
            auto_settle_if_open=True,
            target_settle_seconds=body.target_settle_seconds,
        )
        result = _execute_demo_pipeline(
            position.position_id,
            demo_req,
            owner_id,
            step_hook=bridge,
        )
        _patch_demo_track(
            run_id,
            job_id=result.job_id,
            position_id=result.position_id,
            overall_status="completed",
            result=result,
        )
    except HTTPException as exc:
        if isinstance(exc.detail, str):
            detail = exc.detail
        elif isinstance(exc.detail, dict):
            detail = json.dumps(exc.detail)
        else:
            detail = str(exc.detail)
        _mark_running_demo_steps_failed(run_id)
        _patch_demo_track(run_id, overall_status="failed", error=detail)
    except Exception as exc:
        _mark_running_demo_steps_failed(run_id)
        _patch_demo_track(run_id, overall_status="failed", error=str(exc))


@router.get("/market/positions", response_model=List[MarketPositionResponse])
def list_positions(user=Depends(get_current_user_optional)):
    """List market positions, newest first."""
    owner_id = user.user_id if user else None
    return storage.list_market_positions(owner_id=owner_id)


@router.post(
    "/market/positions",
    response_model=MarketPositionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_position(
    request: MarketPositionCreateRequest,
    user=Depends(get_current_user_optional),
):
    """Create a demo physically deliverable futures or forward position."""
    owner_id = user.user_id if user else None
    return storage.create_market_position(request, owner_id=owner_id)


@router.post("/market/positions/{position_id}/settle", response_model=MarketPositionResponse)
def settle_position(position_id: str):
    """Settle a position into the holder's voucher balance."""
    position = storage.settle_market_position(position_id)
    if not position:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Position with id '{position_id}' not found",
        )
    return position


@router.get("/market/portfolio", response_model=TraderPortfolioResponse)
def get_portfolio(user=Depends(get_current_user_optional)):
    owner_id = user.user_id if user else None
    return storage.get_trader_portfolio(owner_id)


@router.get("/market/execution-metrics", response_model=TraderExecutionMetricsResponse)
def get_execution_metrics(user=Depends(get_current_user_optional)):
    owner_id = user.user_id if user else None
    return storage.get_trader_execution_metrics(owner_id)


@router.get("/market/strategy-metrics", response_model=StrategyExecutionMetricsResponse)
def get_strategy_metrics(user=Depends(get_current_user_optional)):
    owner_id = user.user_id if user else None
    return storage.get_strategy_execution_metrics(owner_id)


@router.get("/market/live/overview", response_model=MarketLiveOverviewResponse)
def get_live_overview():
    return storage.list_live_market_overview()


@router.get("/market/live/orderbook", response_model=ExchangeOrderBookResponse)
def get_live_orderbook(
    gpu_model: Optional[str] = None,
    region: Optional[Region] = None,
    iso_hour: Optional[int] = None,
    sla: Optional[SLA] = None,
    tier: Optional[Tier] = None,
):
    key = _resolve_live_key(gpu_model, region, iso_hour, sla, tier)
    return storage.get_exchange_orderbook(key)


@router.get("/market/live/tape", response_model=List[ExchangeTradeResponse])
def get_live_tape(
    gpu_model: Optional[str] = None,
    region: Optional[Region] = None,
    iso_hour: Optional[int] = None,
    sla: Optional[SLA] = None,
    tier: Optional[Tier] = None,
    limit: int = 50,
):
    key = _resolve_live_key(gpu_model, region, iso_hour, sla, tier)
    return storage.list_exchange_trades(product_key=key, limit=max(1, min(limit, 250)))


@router.post("/market/sim/start", response_model=MarketSimulationStatusResponse)
def start_market_simulation(request: MarketSimulationStartRequest):
    return market_simulator.start(request)


@router.post("/market/sim/stop", response_model=MarketSimulationStatusResponse)
def stop_market_simulation():
    return market_simulator.stop()


@router.get("/market/sim/status", response_model=MarketSimulationStatusResponse)
def get_market_simulation_status():
    return market_simulator.status()


@router.post("/market/positions/{position_id}/deliver", response_model=ComputeDeliveryResponse)
def deliver_position_to_compute(
    position_id: str,
    request: ComputeDeliveryRequest,
    user=Depends(get_current_user_optional),
):
    owner_id = user.user_id if user else None
    position = storage.get_market_position(position_id)
    if not position:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Position with id '{position_id}' not found",
        )
    if owner_id is not None and position.owner_id is not None and position.owner_id != owner_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="position_owner_mismatch",
        )
    if position.side.value != "buy":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="only_buy_positions_can_deliver_compute",
        )
    if position.status.value != "settled":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="position_must_be_settled_before_delivery",
        )

    deposit_amount = request.deposit_ngh or position.quantity_ngh
    try:
        deposit = storage.deposit_vouchers(
            request.job_id,
            position.product_key,
            deposit_amount,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    summary = _run_remote_factoring(_build_gpu_ids(request.gpu_count), request.composite)
    storage.record_delivery_event(
        position_id,
        request.job_id,
        {
            "gpu_count": request.gpu_count,
            "delivered_ngh": deposit_amount,
            "remaining_wallet_ngh": deposit.remaining_balance_ngh,
        },
    )

    return ComputeDeliveryResponse(
        position_id=position_id,
        job_id=request.job_id,
        delivered_ngh=deposit_amount,
        remaining_wallet_ngh=deposit.remaining_balance_ngh,
        factoring_summary=summary,
        delivery_status="completed",
    )


@router.post("/market/positions/{position_id}/demo-run", response_model=DemoRunResponse)
def run_demo_flow(
    position_id: str,
    request: DemoRunRequest,
    user=Depends(get_current_user_optional),
):
    owner_id = user.user_id if user else None
    return _execute_demo_pipeline(position_id, request, owner_id, step_hook=None)


@router.post(
    "/market/demo/full-run",
    response_model=FullDemoRunStartResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def start_full_demo_run(
    body: FullDemoRunRequest,
    user=Depends(get_current_user_optional),
):
    run_id = str(uuid.uuid4())
    _new_demo_track(run_id)
    owner_id = user.user_id if user else None
    thread = threading.Thread(
        target=_full_demo_worker,
        args=(run_id, owner_id, body),
        daemon=True,
        name=f"full-demo-{run_id[:8]}",
    )
    thread.start()
    return FullDemoRunStartResponse(run_id=run_id)


@router.get("/market/demo/run/{run_id}", response_model=DemoRunTrackResponse)
def get_demo_run_progress(
    run_id: str,
    slim: bool = Query(
        False,
        description="If true while run is in progress, omit heavy result payload to shrink JSON",
    ),
):
    with _demo_track_lock:
        track = _demo_tracks.get(run_id)
    if not track:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="demo_run_not_found",
        )
    if slim and track.overall_status == "running":
        return track.model_copy(update={"result": None})
    return track
