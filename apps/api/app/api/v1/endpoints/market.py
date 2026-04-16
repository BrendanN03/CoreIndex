from typing import List, Optional, Callable
import hashlib
import hmac
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
from app.services.feasibility import calculate_ngh_required, check_milestone_sanity
from app.schemas.models import (
    ComputeDeliveryRequest,
    ComputeDeliveryResponse,
    ExecutionPreflightResponse,
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

# Demo matching: at most four GPUs total and at most four distinct seller providers.
MAX_DEMO_GPUS = 4
MAX_DEMO_MATCHED_PROVIDERS = 4


def _consolidate_prime_factors(rows: List[DemoProviderExecutionResponse]) -> List[int]:
    out: List[int] = []
    for row in rows:
        summary = row.factoring_summary
        if not isinstance(summary, dict):
            continue
        factors = summary.get("final_prime_factors")
        if not isinstance(factors, list):
            continue
        for x in factors:
            try:
                out.append(int(x))
            except (TypeError, ValueError):
                continue
    return out


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


def _provider_reliability_score(provider_id: str) -> float:
    lots = storage.list_lots(provider_id=provider_id)
    if not lots:
        return 0.5
    total = len(lots)
    prepared = sum(1 for lot in lots if getattr(lot, "prepared_at", None))
    completed = sum(1 for lot in lots if str(getattr(lot, "status", "")).lower() == "completed")
    failed = sum(1 for lot in lots if str(getattr(lot, "status", "")).lower() == "failed")
    prepare_rate = prepared / max(1, total)
    completion_rate = completed / max(1, completed + failed)
    # Weighted toward completed-vs-failed outcomes, with prepare discipline as a secondary factor.
    score = 0.65 * completion_rate + 0.35 * prepare_rate
    return max(0.0, min(1.0, score))


def _sign_provider_receipt(payload: dict) -> str:
    secret = os.getenv("COREINDEX_PROVIDER_ATTESTATION_SECRET", "coreindex-dev-attestation-secret")
    msg = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hmac.new(secret.encode("utf-8"), msg, hashlib.sha256).hexdigest()


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


def _build_execution_preflight(
    *,
    position_id: str,
    job_id: str,
    owner_id: Optional[str],
) -> ExecutionPreflightResponse:
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
            detail="only_buy_positions_can_execute",
        )

    reasons: List[str] = []
    product_key_match = False
    required_ngh = 0.0
    deposited_ngh = 0.0
    voucher_gap_ngh = 0.0
    milestone_sanity: dict[str, bool] = {"first_output_ok": False, "size_band_ok": False}
    matching_provider_count = 0
    total_available_gpus = 0

    job = storage.get_job(job_id)
    if not job:
        reasons.append(f"job_not_found:{job_id}")
    else:
        job_key = job.window
        product_key_match = (
            job_key.region == position.product_key.region
            and job_key.iso_hour == position.product_key.iso_hour
            and job_key.sla == position.product_key.sla
            and job_key.tier == position.product_key.tier
        )
        if not product_key_match:
            reasons.append("job_window_mismatch_with_position_product_key")

        required_ngh = float(calculate_ngh_required(job.package_index))
        milestone_sanity = check_milestone_sanity(job.package_index)
        if not milestone_sanity.get("first_output_ok", False):
            reasons.append("milestone_first_output_infeasible")
        if not milestone_sanity.get("size_band_ok", False):
            reasons.append("package_size_outside_5_to_15_ngh")

        deposited_ngh = float(
            storage.get_deposited_voucher_balance(
                job_id, position.product_key.as_storage_key()
            )
        )
        voucher_gap_ngh = max(0.0, required_ngh - deposited_ngh)
        if voucher_gap_ngh > 0:
            reasons.append(f"insufficient_escrowed_vouchers:{voucher_gap_ngh:.3f}")

    if position.status.value != "settled":
        reasons.append("position_must_be_settled_before_execution")

    listings = [
        row
        for row in storage.list_marketplace_listings()
        if row.region == position.product_key.region
        and row.iso_hour == position.product_key.iso_hour
        and row.sla == position.product_key.sla
        and row.tier == position.product_key.tier
        and row.gpu_count > 0
        and row.ngh_available > 0
    ]
    matching_provider_count = len({row.provider_id for row in listings})
    total_available_gpus = sum(int(row.gpu_count) for row in listings)
    if total_available_gpus < 1:
        reasons.append("no_matching_provider_capacity_for_product_key")

    return ExecutionPreflightResponse(
        position_id=position_id,
        job_id=job_id,
        ready_to_execute=(len(reasons) == 0),
        reasons=reasons,
        position_status=position.status.value,
        product_key_match=product_key_match,
        required_ngh=required_ngh,
        deposited_ngh=deposited_ngh,
        voucher_gap_ngh=voucher_gap_ngh,
        milestone_sanity=milestone_sanity,
        matching_provider_count=matching_provider_count,
        total_available_gpus=total_available_gpus,
    )


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

    preflight = _build_execution_preflight(
        position_id=position_id,
        job_id=request.job_id,
        owner_id=owner_id,
    )
    if not preflight.ready_to_execute:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "message": "execution_preflight_failed",
                "reasons": preflight.reasons,
            },
        )
    settlement_status = "pre_deposited"

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

    # Default: allow simulated (sim-seller-*) nominations so local pitch runs can still execute.
    # Set DEMO_REQUIRE_REAL_PROVIDERS=true to require human nominations only.
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
                    ngh_available=max(200.0, preflight.required_ngh * 6),
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

    _notify_demo_step(step_hook, "settle_fund", "running", "Preflight checks + escrow validation")
    deposit_amount = (
        float(request.deposit_ngh)
        if request.deposit_ngh is not None
        else preflight.required_ngh
    )
    if preflight.deposited_ngh < deposit_amount:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"insufficient_escrowed_vouchers:{preflight.deposited_ngh:.3f}"
                f"<{deposit_amount:.3f}"
            ),
        )
    _notify_demo_step(
        step_hook,
        "settle_fund",
        "done",
        f"Using {deposit_amount:.2f} NGH already escrowed to job {request.job_id}",
    )

    _notify_demo_step(step_hook, "match_providers", "running", "Selecting providers by market rules")
    ngh_required = preflight.required_ngh
    try:
        remaining_escrow_ngh = storage.consume_deposited_vouchers(
            request.job_id,
            position.product_key,
            deposit_amount,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    if ngh_required <= 5:
        desired_gpu_count = 1
    elif ngh_required <= 10:
        desired_gpu_count = 2
    elif ngh_required <= 18:
        desired_gpu_count = 3
    else:
        desired_gpu_count = 4

    provider_reliability_scores = {
        row.provider_id: _provider_reliability_score(row.provider_id) for row in listings
    }
    listings.sort(
        key=lambda row: (
            row.indicative_price_per_ngh,
            -provider_reliability_scores.get(row.provider_id, 0.5),
            -row.ngh_available,
            row.created_at,
        )
    )
    total_available_gpus = sum(int(row.gpu_count) for row in listings)
    if total_available_gpus < 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="no_available_gpus_after_matching",
        )
    matched_gpu_count = min(MAX_DEMO_GPUS, desired_gpu_count, total_available_gpus)
    remaining_gpus = matched_gpu_count
    matched_provider_gpus: dict[str, int] = {}
    for listing in listings:
        if remaining_gpus <= 0:
            break
        if (
            listing.provider_id not in matched_provider_gpus
            and len(matched_provider_gpus) >= MAX_DEMO_MATCHED_PROVIDERS
        ):
            continue
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
        price_hint: Optional[float] = None
        for row in listings:
            if row.provider_id == provider_id:
                price_hint = row.indicative_price_per_ngh
                break
        summary = _run_remote_factoring(_build_gpu_ids(gpu_count), request.composite)
        summary_hash = _hash_payload(summary if isinstance(summary, dict) else {"summary": summary})
        receipt_signature = _sign_provider_receipt(
            {
                "position_id": position_id,
                "job_id": request.job_id,
                "provider_id": provider_id,
                "gpu_count": gpu_count,
                "summary_hash": summary_hash,
                "product_key": position.product_key.model_dump(mode="json"),
            }
        )
        provider_executions.append(
            DemoProviderExecutionResponse(
                provider_id=provider_id,
                gpu_count=gpu_count,
                factoring_summary=summary,
                provider_reliability_score=provider_reliability_scores.get(provider_id, 0.5),
                receipt_signature=receipt_signature,
                indicative_price_per_ngh=price_hint,
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
            "remaining_wallet_ngh": remaining_escrow_ngh,
            "provider_executions": [row.model_dump(mode="json") for row in provider_executions],
            "provider_selection_policy": (
                "best_price_reliability_capacity_real_only_two_provider_bias"
                if real_provider_only
                else "best_price_reliability_capacity_open_market"
            ),
            "real_provider_only": real_provider_only,
            "synthetic_excluded": real_provider_only,
            "provider_reliability_scores": provider_reliability_scores,
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
        matched_seller_count=len(matched_provider_gpus),
        delivered_ngh=deposit_amount,
        remaining_wallet_ngh=remaining_escrow_ngh,
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
        buyer_owner_id=position.owner_id,
        composite_to_factor=request.composite,
        futures_contract_notional=float(position.notional),
        futures_price_per_ngh=float(position.price_per_ngh),
        futures_quantity_ngh=float(position.quantity_ngh),
        consolidated_prime_factors=_consolidate_prime_factors(provider_executions),
        futures_product_key=position.product_key.model_dump(mode="json"),
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


@router.get(
    "/market/positions/{position_id}/preflight",
    response_model=ExecutionPreflightResponse,
)
def get_execution_preflight(
    position_id: str,
    job_id: str = Query(..., min_length=1),
    user=Depends(get_current_user_optional),
):
    owner_id = user.user_id if user else None
    return _build_execution_preflight(
        position_id=position_id,
        job_id=job_id.strip(),
        owner_id=owner_id,
    )


@router.post("/market/positions/{position_id}/deliver", response_model=ComputeDeliveryResponse)
def deliver_position_to_compute(
    position_id: str,
    request: ComputeDeliveryRequest,
    user=Depends(get_current_user_optional),
):
    owner_id = user.user_id if user else None
    preflight = _build_execution_preflight(
        position_id=position_id,
        job_id=request.job_id,
        owner_id=owner_id,
    )
    if not preflight.ready_to_execute:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": "execution_preflight_failed", "reasons": preflight.reasons},
        )
    position = storage.get_market_position(position_id)
    if not position:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Position with id '{position_id}' not found",
        )

    deposit_amount = request.deposit_ngh or preflight.required_ngh
    try:
        remaining_escrow = storage.consume_deposited_vouchers(
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
            "remaining_wallet_ngh": remaining_escrow,
        },
    )

    return ComputeDeliveryResponse(
        position_id=position_id,
        job_id=request.job_id,
        delivered_ngh=deposit_amount,
        remaining_wallet_ngh=remaining_escrow,
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
