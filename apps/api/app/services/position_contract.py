"""Futures-style contract close horizon shared by market, vouchers, and storage."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from app.schemas.models import MarketPositionResponse


LEGACY_MISSING_CLOSES_AT_SECONDS = int(
    os.getenv("COREINDEX_LEGACY_MISSING_CLOSES_AT_SECONDS", "300"),
)


def _parse_iso_utc(value: str) -> datetime:
    dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def seconds_until_contract_close(position) -> int:
    """Seconds until the contract may settle / escrow; 0 means closed for trading purposes."""
    now = datetime.now(timezone.utc)
    close_dt: datetime | None = None
    closes_raw = getattr(position, "closes_at", None)
    if closes_raw and str(closes_raw).strip():
        try:
            close_dt = _parse_iso_utc(str(closes_raw))
        except Exception:
            close_dt = None
    if close_dt is None:
        try:
            created_dt = _parse_iso_utc(str(position.created_at))
        except Exception:
            # Unparseable timestamps — refuse to treat as expired (fail closed).
            return 10**9
        horizon = getattr(position, "close_in_seconds", None)
        if horizon is not None:
            try:
                sec = int(horizon)
            except (TypeError, ValueError):
                sec = LEGACY_MISSING_CLOSES_AT_SECONDS
            if sec < 0:
                sec = LEGACY_MISSING_CLOSES_AT_SECONDS
            close_dt = created_dt + timedelta(seconds=sec)
        else:
            close_dt = created_dt + timedelta(seconds=LEGACY_MISSING_CLOSES_AT_SECONDS)
    return max(0, int((close_dt - now).total_seconds()))


def is_contract_closed(position) -> bool:
    return seconds_until_contract_close(position) <= 0


def assert_contract_closed_for_settlement(position) -> None:
    sec = seconds_until_contract_close(position)
    if sec > 0:
        raise ValueError(f"contract_not_closed_yet:{sec}s_remaining")


def annotate_market_position_countdown(position: MarketPositionResponse) -> MarketPositionResponse:
    """Attach API-only `seconds_until_close` (canonical position in storage stays without this field)."""
    sec = seconds_until_contract_close(position)
    return position.model_copy(update={"seconds_until_close": int(sec)})
