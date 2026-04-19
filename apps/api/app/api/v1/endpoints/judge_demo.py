"""Judge-only demo surfaces (separate from apps/web): voucher / settlement / delivery chain."""

from datetime import datetime, timezone

from fastapi import APIRouter, Query

from app.repositories.memory.storage import storage
from app.schemas.models import JudgeChainLedgerResponse

router = APIRouter()


@router.get("/judge-chain-ledger", response_model=JudgeChainLedgerResponse)
def get_judge_chain_ledger(
    limit_events: int = Query(4000, ge=50, le=20000, description="Tail of chronological events to scan"),
    limit_blocks: int = Query(120, ge=1, le=1000, description="Max chain blocks to return"),
) -> JudgeChainLedgerResponse:
    events = storage.list_events_chronological(limit_events)
    blocks = storage.list_judge_chain_blocks(limit_blocks)
    return JudgeChainLedgerResponse(
        generated_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        event_window=len(events),
        chain_length=len(storage.list_judge_chain_blocks()),
        chain_head_hash=(blocks[-1].block_hash if blocks else None),
        blocks=blocks,
    )
