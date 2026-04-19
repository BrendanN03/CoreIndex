"""Build a judge-facing ERC-1155-style ledger + append-only delivery chain blocks."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Callable, Dict, Iterable, List, Optional

from app.schemas.models import (
    JudgeChainBlock,
    JudgeChainLedgerResponse,
    JudgeLedgerOp,
    PlatformEvent,
)


def _token_id_for_product_key(product_key: dict) -> str:
    raw = json.dumps(product_key, sort_keys=True, separators=(",", ":")).encode()
    return "0x" + hashlib.sha256(raw).hexdigest()[:16]


def _settlement_job_id(
    event: PlatformEvent, job_by_settlement: Callable[[str], Optional[str]]
) -> Optional[str]:
    if event.event_type == "settlement.anchored":
        return str(event.payload.get("job_id") or "") or None
    if event.event_type == "settlement.paid":
        return str(event.payload.get("job_id") or "") or None
    if event.event_type == "settlement.anchor_recorded":
        return job_by_settlement(event.entity_id)
    return None


def _voucher_op(event: PlatformEvent) -> JudgeLedgerOp:
    pk = event.payload.get("product_key")
    token = _token_id_for_product_key(pk) if isinstance(pk, dict) else "0xunknown"
    if event.event_type == "voucher.deposited":
        amt = float(event.payload.get("amount_ngh") or 0.0)
        return JudgeLedgerOp(
            op_kind="erc1155_escrow_lock",
            title="Voucher escrow (job-scoped)",
            detail=f"Moved {amt:.4g} NGH of token {token} from wallet into job escrow.",
            event_type=event.event_type,
            event_id=event.event_id,
            created_at=event.created_at,
            metadata={
                "token_id": token,
                "job_id": event.entity_id,
                "amount_ngh": amt,
                "remaining_balance_ngh": event.payload.get("remaining_balance_ngh"),
            },
        )
    amt = float(event.payload.get("amount_ngh") or 0.0)
    return JudgeLedgerOp(
        op_kind="erc1155_escrow_burn",
        title="Voucher burn on delivery (consumed from escrow)",
        detail=f"Burned {amt:.4g} NGH of token {token} against accepted execution.",
        event_type=event.event_type,
        event_id=event.event_id,
        created_at=event.created_at,
        metadata={
            "token_id": token,
            "job_id": event.entity_id,
            "amount_ngh": amt,
            "remaining_deposited_ngh": event.payload.get("remaining_deposited_ngh"),
        },
    )


def _settlement_op(
    event: PlatformEvent, job_id: str, job_by_settlement: Callable[[str], Optional[str]]
) -> JudgeLedgerOp:
    if event.event_type == "settlement.anchored":
        return JudgeLedgerOp(
            op_kind="settlement_merkle_ready",
            title="Settlement run anchored (receipt + QC roots)",
            detail=f"Settlement {event.entity_id} prepared for on-chain anchor.",
            event_type=event.event_type,
            event_id=event.event_id,
            created_at=event.created_at,
            metadata={
                "settlement_id": event.entity_id,
                "job_id": job_id,
                "receipt_root": event.payload.get("receipt_root"),
                "qc_root": event.payload.get("qc_root"),
            },
        )
    if event.event_type == "settlement.anchor_recorded":
        anchor = event.payload.get("blockchain_anchor")
        ah = event.payload.get("anchor_hash")
        return JudgeLedgerOp(
            op_kind="settlement_onchain_anchor",
            title="Settlement anchor recorded on local EVM (demo)",
            detail=f"Anchor hash {str(ah)[:24]}… written with settlement tx.",
            event_type=event.event_type,
            event_id=event.event_id,
            created_at=event.created_at,
            metadata={
                "settlement_id": event.entity_id,
                "job_id": job_id,
                "anchor_hash": ah,
                "blockchain_anchor": anchor if isinstance(anchor, dict) else None,
            },
        )
    return JudgeLedgerOp(
        op_kind="settlement_paid",
        title="Settlement paid (accepted / rejected NGH)",
        detail="Payout state finalized for this settlement run.",
        event_type=event.event_type,
        event_id=event.event_id,
        created_at=event.created_at,
        metadata={
            "settlement_id": event.entity_id,
            "job_id": job_id,
            "accepted_ngh": event.payload.get("accepted_ngh"),
            "rejected_ngh": event.payload.get("rejected_ngh"),
        },
    )


def _delivery_op(event: PlatformEvent, job_id: str, position_id: str) -> JudgeLedgerOp:
    pk = event.payload.get("product_key")
    token = _token_id_for_product_key(pk) if isinstance(pk, dict) else None
    vh = event.payload.get("verification_hash")
    anchor = event.payload.get("blockchain_anchor")
    detail_parts = [
        f"Job {job_id} · position {position_id}",
        f"delivered {event.payload.get('delivered_ngh')} NGH",
    ]
    if vh:
        detail_parts.append(f"verification {str(vh)[:20]}…")
    if isinstance(anchor, dict) and anchor.get("tx_hash"):
        detail_parts.append(f"tx {anchor.get('tx_hash')}")
    return JudgeLedgerOp(
        op_kind="delivery_commit",
        title="Accepted delivery + verification bundle",
        detail=" · ".join(detail_parts),
        event_type=event.event_type,
        event_id=event.event_id,
        created_at=event.created_at,
        metadata={
            "job_id": job_id,
            "position_id": position_id,
            "token_id": token,
            "delivered_ngh": event.payload.get("delivered_ngh"),
            "verification_hash": vh,
            "verification_passed": event.payload.get("verification_passed"),
            "blockchain_anchor": anchor if isinstance(anchor, dict) else None,
            "mode": event.payload.get("mode"),
            "provider_executions_count": len(event.payload.get("provider_executions") or [])
            if isinstance(event.payload.get("provider_executions"), list)
            else None,
        },
    )


def _parse_job_id_from_delivery(event: PlatformEvent) -> str:
    job_id = str(event.payload.get("job_id") or event.payload.get("jobId") or "").strip()
    return job_id or "unknown"


def extract_related_ops(
    events_before_delivery: Iterable[PlatformEvent],
    *,
    job_id: str,
    job_by_settlement: Callable[[str], Optional[str]],
) -> List[JudgeLedgerOp]:
    """Map prior voucher + settlement events for this job into judge ledger operations."""
    related: List[JudgeLedgerOp] = []
    for event in events_before_delivery:
        if event.event_type in ("voucher.deposited", "voucher.consumed") and event.entity_id == job_id:
            related.append(_voucher_op(event))
            continue
        if event.event_type.startswith("settlement."):
            sj = _settlement_job_id(event, job_by_settlement)
            if sj == job_id:
                related.append(_settlement_op(event, job_id, job_by_settlement))
    return related


def _block_hash_payload(block: JudgeChainBlock) -> Dict[str, object]:
    return {
        "chain_height": block.chain_height,
        "prev_block_hash": block.prev_block_hash,
        "job_id": block.job_id,
        "position_id": block.position_id,
        "delivery_event_id": block.delivery_event_id,
        "delivery_created_at": block.delivery_created_at,
        "delivered_ngh": block.delivered_ngh,
        "verification_hash": block.verification_hash,
        "verification_passed": block.verification_passed,
        "blockchain_anchor": block.blockchain_anchor,
        "demo_mode": block.demo_mode,
        "related_ops": [op.model_dump(mode="json") for op in block.related_ops],
        "delivery_op": block.delivery_op.model_dump(mode="json"),
    }


def _chain_hash(data: Dict[str, object]) -> str:
    raw = json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "0x" + hashlib.sha256(raw).hexdigest()


def build_chain_block_for_delivery(
    delivery_event: PlatformEvent,
    *,
    related_ops: List[JudgeLedgerOp],
    block_index: int,
    prev_block_hash: Optional[str],
) -> JudgeChainBlock:
    """Construct one append-only chain block from a completed delivery event."""
    job_id = _parse_job_id_from_delivery(delivery_event)
    position_id = delivery_event.entity_id
    demo_mode = (
        delivery_event.payload.get("mode")
        if isinstance(delivery_event.payload.get("mode"), str)
        else None
    )
    skeleton = JudgeChainBlock(
        block_index=block_index,
        chain_height=block_index,
        prev_block_hash=prev_block_hash,
        block_hash="0xpending",
        appended_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        job_id=job_id,
        position_id=position_id,
        delivery_event_id=delivery_event.event_id,
        delivery_created_at=delivery_event.created_at,
        delivered_ngh=_float_or_none(delivery_event.payload.get("delivered_ngh")),
        verification_hash=(
            str(delivery_event.payload["verification_hash"])
            if delivery_event.payload.get("verification_hash") is not None
            else None
        ),
        verification_passed=(
            bool(delivery_event.payload["verification_passed"])
            if delivery_event.payload.get("verification_passed") is not None
            else None
        ),
        blockchain_anchor=(
            delivery_event.payload["blockchain_anchor"]
            if isinstance(delivery_event.payload.get("blockchain_anchor"), dict)
            else None
        ),
        demo_mode=demo_mode,
        related_ops=related_ops,
        delivery_op=_delivery_op(delivery_event, job_id, position_id),
    )
    block_hash = _chain_hash(_block_hash_payload(skeleton))
    return skeleton.model_copy(update={"block_hash": block_hash})


def build_judge_chain_ledger(
    events_chronological: List[PlatformEvent],
    *,
    job_by_settlement: Callable[[str], Optional[str]],
    event_window: int,
) -> JudgeChainLedgerResponse:
    """Group voucher + settlement operations into append-only chain blocks per delivery."""
    delivery_idxs = [
        i for i, event in enumerate(events_chronological) if event.event_type == "delivery.compute_run_completed"
    ]
    blocks: List[JudgeChainBlock] = []
    job_cursors: Dict[str, int] = {}
    prev_block_hash: Optional[str] = None
    for d_idx in delivery_idxs:
        delivery_event = events_chronological[d_idx]
        job_id = _parse_job_id_from_delivery(delivery_event)
        start_idx = max(0, job_cursors.get(job_id, 0))
        related = extract_related_ops(
            events_chronological[start_idx:d_idx],
            job_id=job_id,
            job_by_settlement=job_by_settlement,
        )
        block = build_chain_block_for_delivery(
            delivery_event,
            related_ops=related,
            block_index=len(blocks) + 1,
            prev_block_hash=prev_block_hash,
        )
        blocks.append(block)
        prev_block_hash = block.block_hash
        job_cursors[job_id] = d_idx
    return JudgeChainLedgerResponse(
        generated_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        event_window=event_window,
        chain_length=len(blocks),
        chain_head_hash=(blocks[-1].block_hash if blocks else None),
        blocks=blocks,
    )


def _float_or_none(v: object) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
