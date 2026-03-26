"""
In-memory storage for jobs, nominations, and lots.

This is a dev/test implementation. It is intentionally small and can be replaced with
a DB-backed implementation later.
"""

from __future__ import annotations

from collections import defaultdict
import functools
from itertools import islice
from typing import Dict, List, Optional
from datetime import datetime
from pathlib import Path
import json
import logging
import os
import threading
import uuid

from app.schemas.models import (
    JobCreateRequest,
    JobResponse,
    JobStatus,
    Window,
    ProductKey,
    Region,
    SLA,
    Tier,
    NominationRequest,
    NominationResponse,
    Lot,
    LotStatus,
    MarketPositionCreateRequest,
    MarketPositionResponse,
    MarketPositionStatus,
    VoucherDepositResponse,
    VoucherBalanceResponse,
    ExchangeOrderCreateRequest,
    ExchangeOrderAmendRequest,
    ExchangeOrderResponse,
    ExchangeOrderStatus,
    ExchangeOrderSide,
    ExchangeTradeResponse,
    ExchangeOrderBookLevel,
    ExchangeOrderBookResponse,
    PlatformEvent,
    OptionContractCreateRequest,
    OptionContractResponse,
    OptionContractStatus,
    OptionQuoteRequest,
    OptionOrderCreateRequest,
    OptionOrderAmendRequest,
    OptionOrderResponse,
    OptionOrderSide,
    OptionOrderStatus,
    OptionTradeResponse,
    OptionOrderBookLevel,
    OptionOrderBookResponse,
    RiskSummaryResponse,
    TimeInForce,
    TraderPortfolioResponse,
    FuturesPositionRow,
    OptionPositionRow,
    MarginStressResponse,
    LiquidationResponse,
    ProviderSlaSummaryResponse,
    RiskProfileResponse,
    RiskProfileUpdateRequest,
    KillSwitchUpdateResponse,
    TraderExecutionMetricsResponse,
    ProviderExecutionMetricsResponse,
    StrategyLimitResponse,
    StrategyLimitUpdateRequest,
    StrategyExecutionMetricsResponse,
    StrategyExecutionMetricsRow,
    ProviderFleetOverviewResponse,
    MarketplaceGpuListingResponse,
    ExchangePretradeRequest,
    OptionPretradeRequest,
    PretradeCheckResponse,
    TradingSubaccountRiskResponse,
    TradingSubaccountRiskUpdateRequest,
    TradingHierarchyResponse,
    MarketLiveOverviewResponse,
    MarketLiveOverviewRow,
)
from app.services.options_pricing import quote_option
from app.services.risk import (
    MAX_MARGIN_LIMIT,
    MAX_NOTIONAL_LIMIT,
    compute_option_initial_margin,
)


# Cap persisted platform events so JSON snapshots stay small and writes stay fast (demo UI fans out many requests).
_MAX_PERSISTED_EVENTS = 2500


class JobStorage:
    """Simple in-memory job storage."""

    def __init__(self):
        self._state_file = Path(__file__).resolve().parents[2] / "data" / "storage_state.json"
        self._jobs: Dict[str, JobResponse] = {}
        self._vouchers: Dict[str, float] = {}  # key -> voucher amount in NGH
        self._voucher_deposits: Dict[str, Dict[str, float]] = {}  # job_id -> key -> amount
        self._positions: Dict[str, MarketPositionResponse] = {}
        self._orders: Dict[str, ExchangeOrderResponse] = {}
        self._trades: List[ExchangeTradeResponse] = []
        self._nominations: Dict[str, NominationResponse] = {}
        self._lots: Dict[str, Lot] = {}
        self._events: List[PlatformEvent] = []
        self._option_contracts: Dict[str, OptionContractResponse] = {}
        self._option_orders: Dict[str, OptionOrderResponse] = {}
        self._option_trades: List[OptionTradeResponse] = []
        self._risk_profiles: Dict[str, Dict[str, float]] = {}
        self._kill_switches: Dict[str, bool] = {}
        self._strategy_limits: Dict[str, Dict[str, Dict[str, float | bool]]] = {}
        self._owner_hierarchy: Dict[str, Dict[str, str]] = {}
        self._subaccount_limits: Dict[str, Dict[str, Dict[str, float | bool]]] = {}
        self._demo_product_key = ProductKey(
            region=Region.US_EAST,
            iso_hour=datetime.utcnow().hour,
            sla=SLA.STANDARD,
            tier=Tier.STANDARD,
        )
        # Market simulator thread + FastAPI/demo threads share this store; serialize access.
        self._lock = threading.RLock()
        # Disk snapshots must not run while holding _lock — they were blocking every HTTP reader.
        self._persist_dirty = False
        self._persist_timer: threading.Timer | None = None
        self._persist_sched_lock = threading.Lock()
        self._persist_debounce_s = float(os.getenv("COREINDEX_PERSIST_DEBOUNCE_SECONDS", "0.5"))
        self._load_state()

    def _load_state(self) -> None:
        if not self._state_file.exists():
            return
        try:
            raw = json.loads(self._state_file.read_text())
        except Exception:
            return

        self._jobs = {
            key: JobResponse.model_validate(value)
            for key, value in raw.get("jobs", {}).items()
        }
        self._vouchers = {
            key: float(value) for key, value in raw.get("vouchers", {}).items()
        }
        self._voucher_deposits = {
            job_id: {key: float(amount) for key, amount in deposits.items()}
            for job_id, deposits in raw.get("voucher_deposits", {}).items()
        }
        self._positions = {
            key: MarketPositionResponse.model_validate(value)
            for key, value in raw.get("positions", {}).items()
        }
        self._orders = {
            key: ExchangeOrderResponse.model_validate(value)
            for key, value in raw.get("orders", {}).items()
        }
        self._trades = [
            ExchangeTradeResponse.model_validate(value)
            for value in raw.get("trades", [])
        ]
        self._nominations = {
            key: NominationResponse.model_validate(value)
            for key, value in raw.get("nominations", {}).items()
        }
        self._option_contracts = {
            key: OptionContractResponse.model_validate(value)
            for key, value in raw.get("option_contracts", {}).items()
        }
        self._option_orders = {
            key: OptionOrderResponse.model_validate(value)
            for key, value in raw.get("option_orders", {}).items()
        }
        self._option_trades = [
            OptionTradeResponse.model_validate(value)
            for value in raw.get("option_trades", [])
        ]
        self._risk_profiles = {
            key: {
                "max_notional_limit": float(value.get("max_notional_limit", MAX_NOTIONAL_LIMIT)),
                "max_margin_limit": float(value.get("max_margin_limit", MAX_MARGIN_LIMIT)),
                "max_order_notional": float(value.get("max_order_notional", MAX_NOTIONAL_LIMIT)),
            }
            for key, value in raw.get("risk_profiles", {}).items()
        }
        self._kill_switches = {
            key: bool(value) for key, value in raw.get("kill_switches", {}).items()
        }
        self._strategy_limits = {
            owner_key: {
                strategy_tag: {
                    "max_order_notional": float(limit.get("max_order_notional", MAX_NOTIONAL_LIMIT)),
                    "kill_switch_enabled": bool(limit.get("kill_switch_enabled", False)),
                }
                for strategy_tag, limit in owner_limits.items()
            }
            for owner_key, owner_limits in raw.get("strategy_limits", {}).items()
        }
        self._owner_hierarchy = {
            key: {
                "org_id": str(value.get("org_id", "coreindex-demo-org")),
                "account_id": str(value.get("account_id", f"{key}-acct")),
            }
            for key, value in raw.get("owner_hierarchy", {}).items()
        }
        self._subaccount_limits = {
            owner_key: {
                subaccount_id: {
                    "max_order_notional": float(limit.get("max_order_notional", MAX_NOTIONAL_LIMIT)),
                    "kill_switch_enabled": bool(limit.get("kill_switch_enabled", False)),
                }
                for subaccount_id, limit in owner_limits.items()
            }
            for owner_key, owner_limits in raw.get("subaccount_limits", {}).items()
        }
        self._lots = {
            key: Lot.model_validate(value)
            for key, value in raw.get("lots", {}).items()
        }
        self._events = [PlatformEvent.model_validate(item) for item in raw.get("events", [])]
        if len(self._events) > _MAX_PERSISTED_EVENTS:
            self._events = self._events[-_MAX_PERSISTED_EVENTS:]

    def _build_persist_snapshot_unlocked(self) -> dict:
        """Build JSON-serializable snapshot. Caller must hold self._lock."""
        if len(self._events) > _MAX_PERSISTED_EVENTS:
            self._events = self._events[-_MAX_PERSISTED_EVENTS:]
        return {
            "jobs": {
                key: value.model_dump(mode="json")
                for key, value in list(self._jobs.items())
            },
            "vouchers": dict(self._vouchers),
            "voucher_deposits": {
                jid: dict(deps) for jid, deps in list(self._voucher_deposits.items())
            },
            "positions": {
                key: value.model_dump(mode="json")
                for key, value in list(self._positions.items())
            },
            "orders": {
                key: value.model_dump(mode="json")
                for key, value in list(self._orders.items())
            },
            "trades": [trade.model_dump(mode="json") for trade in list(self._trades)],
            "nominations": {
                key: value.model_dump(mode="json")
                for key, value in list(self._nominations.items())
            },
            "option_contracts": {
                key: value.model_dump(mode="json")
                for key, value in list(self._option_contracts.items())
            },
            "option_orders": {
                key: value.model_dump(mode="json")
                for key, value in list(self._option_orders.items())
            },
            "option_trades": [
                trade.model_dump(mode="json") for trade in list(self._option_trades)
            ],
            "risk_profiles": dict(self._risk_profiles),
            "kill_switches": dict(self._kill_switches),
            "strategy_limits": {
                ok: dict(inner) for ok, inner in list(self._strategy_limits.items())
            },
            "owner_hierarchy": {
                ok: dict(inner) for ok, inner in list(self._owner_hierarchy.items())
            },
            "subaccount_limits": {
                ok: {sk: dict(sv) for sk, sv in list(inner.items())}
                for ok, inner in list(self._subaccount_limits.items())
            },
            "lots": {
                key: value.model_dump(mode="json")
                for key, value in list(self._lots.items())
            },
            "events": [event.model_dump(mode="json") for event in list(self._events)],
        }

    def _persist_state(self) -> None:
        """Mark state dirty and schedule a disk flush (coalesced). Never blocks on I/O."""
        self._persist_dirty = True
        with self._persist_sched_lock:
            if self._persist_timer is not None:
                self._persist_timer.cancel()
                self._persist_timer = None
            timer = threading.Timer(
                self._persist_debounce_s,
                self._timer_flush_persist,
            )
            timer.daemon = True
            self._persist_timer = timer
            timer.start()

    def _timer_flush_persist(self) -> None:
        """Write snapshot to disk without holding storage lock during json.dumps / IO."""
        with self._persist_sched_lock:
            self._persist_timer = None
        payload: dict | None = None
        try:
            with self._lock:
                if not self._persist_dirty:
                    return
                self._persist_dirty = False
                payload = self._build_persist_snapshot_unlocked()
        except Exception:
            logging.getLogger("uvicorn.error").exception("storage persist: snapshot failed")
            with self._lock:
                self._persist_dirty = True
            return
        if payload is None:
            return
        try:
            self._state_file.parent.mkdir(parents=True, exist_ok=True)
            text = json.dumps(payload, separators=(",", ":"))
            tmp = self._state_file.with_suffix(".json.tmp")
            tmp.write_text(text, encoding="utf-8")
            tmp.replace(self._state_file)
        except Exception:
            logging.getLogger("uvicorn.error").exception("storage persist: disk write failed")
            with self._lock:
                self._persist_dirty = True

    def flush_persist_blocking(self) -> None:
        """Synchronous flush for process shutdown. Waits for disk write."""
        with self._persist_sched_lock:
            if self._persist_timer is not None:
                self._persist_timer.cancel()
                self._persist_timer = None
        with self._lock:
            self._persist_dirty = False
            payload = self._build_persist_snapshot_unlocked()
        self._state_file.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(payload, separators=(",", ":"))
        tmp = self._state_file.with_suffix(".json.tmp")
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(self._state_file)

    def _record_event(self, event_type: str, entity_type: str, entity_id: str, payload: dict):
        event = PlatformEvent(
            event_id=str(uuid.uuid4()),
            event_type=event_type,
            created_at=datetime.utcnow().isoformat() + "Z",
            entity_type=entity_type,
            entity_id=entity_id,
            payload=payload,
        )
        self._events.append(event)
        self._persist_state()
        return event

    def list_events(self, limit: Optional[int] = None) -> List[PlatformEvent]:
        """Return recent platform events, newest first."""
        if limit is not None and limit > 0:
            tail = self._events[-limit:]
            return list(reversed(tail))
        return list(reversed(self._events))

    def event_count(self) -> int:
        return len(self._events)

    def record_delivery_event(self, position_id: str, job_id: str, payload: dict) -> None:
        self._record_event(
            "delivery.compute_run_completed",
            "position",
            position_id,
            {"job_id": job_id, **payload},
        )

    def _owner_key(self, owner_id: Optional[str]) -> str:
        return owner_id or "__guest__"

    def is_synthetic_owner(self, owner_id: Optional[str]) -> bool:
        if owner_id is None:
            return False
        return owner_id.startswith("sim-")

    def get_demo_product_key(self) -> ProductKey:
        return self._demo_product_key

    def is_demo_product_key(self, product_key: ProductKey) -> bool:
        return product_key.as_storage_key() == self._demo_product_key.as_storage_key()

    def _assert_demo_isolation_for_synthetic(
        self,
        owner_id: Optional[str],
        product_key: ProductKey,
        *,
        entity: str,
    ) -> None:
        if self.is_synthetic_owner(owner_id) and self.is_demo_product_key(product_key):
            raise ValueError(f"demo_key_rejects_synthetic_{entity}")

    def _parse_iso_ts(self, value: str) -> datetime:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))

    def _infer_gpu_model_for_key(self, product_key: ProductKey) -> str:
        matching = [
            nomination
            for nomination in self._nominations.values()
            if ProductKey(
                region=nomination.region,
                iso_hour=nomination.iso_hour,
                sla=nomination.sla,
                tier=nomination.tier,
            ).as_storage_key()
            == product_key.as_storage_key()
        ]
        if matching:
            matching.sort(key=lambda row: row.created_at, reverse=True)
            return matching[0].gpu_model
        return {
            Tier.BASIC: "RTX 3090",
            Tier.STANDARD: "RTX 4090",
            Tier.PREMIUM: "A100",
            Tier.ENTERPRISE: "H100",
        }.get(product_key.tier, "RTX 4090")

    def _recent_trades_by_storage_key(
        self,
        storage_keys: set[str],
        *,
        per_key_limit: int = 250,
        max_scan: int = 100_000,
    ) -> Dict[str, List[ExchangeTradeResponse]]:
        """Newest-first trades per product key in one reverse scan (avoids O(keys * |trades|))."""
        buckets: Dict[str, List[ExchangeTradeResponse]] = {k: [] for k in storage_keys}
        if not storage_keys:
            return buckets
        scanned = 0
        for trade in reversed(self._trades):
            scanned += 1
            if scanned > max_scan:
                break
            k = trade.product_key.as_storage_key()
            if k not in buckets:
                continue
            b = buckets[k]
            if len(b) >= per_key_limit:
                if all(len(buckets[key]) >= per_key_limit for key in storage_keys):
                    break
                continue
            b.append(trade)
        return buckets

    def _active_exchange_orders_by_storage_key(
        self, storage_keys: set[str]
    ) -> Dict[str, List[ExchangeOrderResponse]]:
        out: Dict[str, List[ExchangeOrderResponse]] = {k: [] for k in storage_keys}
        for order in self._orders.values():
            if order.status not in (
                ExchangeOrderStatus.OPEN,
                ExchangeOrderStatus.PARTIALLY_FILLED,
            ):
                continue
            if order.remaining_ngh <= 0:
                continue
            k = order.product_key.as_storage_key()
            bucket = out.get(k)
            if bucket is not None:
                bucket.append(order)
        return out

    def _orderbook_from_active_orders(
        self, product_key: ProductKey, active: List[ExchangeOrderResponse]
    ) -> ExchangeOrderBookResponse:
        bids: Dict[float, float] = {}
        asks: Dict[float, float] = {}
        for order in active:
            book = bids if order.side == ExchangeOrderSide.BUY else asks
            book[order.price_per_ngh] = book.get(order.price_per_ngh, 0.0) + order.remaining_ngh
        bid_levels = [
            ExchangeOrderBookLevel(price_per_ngh=price, quantity_ngh=qty)
            for price, qty in sorted(bids.items(), key=lambda item: item[0], reverse=True)
        ]
        ask_levels = [
            ExchangeOrderBookLevel(price_per_ngh=price, quantity_ngh=qty)
            for price, qty in sorted(asks.items(), key=lambda item: item[0])
        ]
        best_bid = bid_levels[0].price_per_ngh if bid_levels else None
        best_ask = ask_levels[0].price_per_ngh if ask_levels else None
        spread = (best_ask - best_bid) if (best_bid is not None and best_ask is not None) else None
        return ExchangeOrderBookResponse(
            product_key=product_key,
            bids=bid_levels[:10],
            asks=ask_levels[:10],
            spread=spread,
            best_bid=best_bid,
            best_ask=best_ask,
        )

    def _merge_live_overview_by_gpu_model(
        self, rows: List[MarketLiveOverviewRow]
    ) -> List[MarketLiveOverviewRow]:
        """One card per GPU spec: aggregate venues that map to the same display model."""
        grouped: Dict[str, List[MarketLiveOverviewRow]] = defaultdict(list)
        for row in rows:
            grouped[row.gpu_model].append(row)
        merged: List[MarketLiveOverviewRow] = []
        for gpu_model in sorted(grouped.keys()):
            group = grouped[gpu_model]
            total_vol = sum(r.traded_volume_ngh_5m for r in group)
            bid_vals = [r.best_bid_per_ngh for r in group if r.best_bid_per_ngh is not None]
            ask_vals = [r.best_ask_per_ngh for r in group if r.best_ask_per_ngh is not None]
            best_bid = max(bid_vals) if bid_vals else None
            best_ask = min(ask_vals) if ask_vals else None
            spread = (
                (best_ask - best_bid)
                if (best_bid is not None and best_ask is not None)
                else None
            )
            active_order_count = sum(r.active_order_count for r in group)
            weighted = sum(
                r.last_price_per_ngh * r.traded_volume_ngh_5m
                for r in group
                if r.traded_volume_ngh_5m > 0
            )
            if total_vol > 0:
                last_price = weighted / total_vol
            elif best_bid is not None and best_ask is not None:
                last_price = (best_bid + best_ask) / 2.0
            elif best_bid is not None:
                last_price = best_bid
            elif best_ask is not None:
                last_price = best_ask
            else:
                last_price = max((r.last_price_per_ngh for r in group), default=0.0)
            rep = max(group, key=lambda r: (r.traded_volume_ngh_5m, r.active_order_count))
            merged.append(
                MarketLiveOverviewRow(
                    gpu_model=gpu_model,
                    product_key=rep.product_key,
                    last_price_per_ngh=float(last_price),
                    best_bid_per_ngh=best_bid,
                    best_ask_per_ngh=best_ask,
                    spread_per_ngh=spread,
                    traded_volume_ngh_5m=float(total_vol),
                    active_order_count=active_order_count,
                )
            )
        return merged

    def list_live_market_overview(self) -> MarketLiveOverviewResponse:
        keys: Dict[str, ProductKey] = {}
        for order in self._orders.values():
            keys[order.product_key.as_storage_key()] = order.product_key
        for trade in self._trades:
            keys[trade.product_key.as_storage_key()] = trade.product_key
        for nomination in self._nominations.values():
            key = ProductKey(
                region=nomination.region,
                iso_hour=nomination.iso_hour,
                sla=nomination.sla,
                tier=nomination.tier,
            )
            keys[key.as_storage_key()] = key

        storage_key_set = set(keys.keys())
        trades_by_key = self._recent_trades_by_storage_key(storage_key_set)
        active_by_key = self._active_exchange_orders_by_storage_key(storage_key_set)

        rows: List[MarketLiveOverviewRow] = []
        now = datetime.utcnow()
        for product_key in keys.values():
            k = product_key.as_storage_key()
            active = active_by_key.get(k, [])
            book = self._orderbook_from_active_orders(product_key, active)
            trades = trades_by_key.get(k, [])
            active_order_count = len(active)
            recent_trades = [
                trade
                for trade in trades
                if (now - self._parse_iso_ts(trade.created_at).replace(tzinfo=None)).total_seconds()
                <= 300
            ]
            volume_5m = sum(trade.quantity_ngh for trade in recent_trades)
            last_price = (
                trades[0].price_per_ngh
                if trades
                else (
                    ((book.best_bid or 0.0) + (book.best_ask or 0.0)) / 2.0
                    if (book.best_bid is not None and book.best_ask is not None)
                    else (book.best_bid or book.best_ask or 0.0)
                )
            )
            rows.append(
                MarketLiveOverviewRow(
                    gpu_model=self._infer_gpu_model_for_key(product_key),
                    product_key=product_key,
                    last_price_per_ngh=float(last_price),
                    best_bid_per_ngh=book.best_bid,
                    best_ask_per_ngh=book.best_ask,
                    spread_per_ngh=book.spread,
                    traded_volume_ngh_5m=float(volume_5m),
                    active_order_count=active_order_count,
                )
            )
        merged_rows = self._merge_live_overview_by_gpu_model(rows)
        return MarketLiveOverviewResponse(
            as_of=datetime.utcnow().isoformat() + "Z",
            rows=merged_rows,
        )

    def _get_owner_hierarchy_dict(self, owner_id: Optional[str]) -> Dict[str, str]:
        owner_key = self._owner_key(owner_id)
        row = self._owner_hierarchy.get(owner_key)
        if row is None:
            account_suffix = owner_key.replace("@", "-").replace(".", "-")
            row = {
                "org_id": "coreindex-demo-org",
                "account_id": f"{account_suffix}-acct",
            }
            self._owner_hierarchy[owner_key] = row
        return row

    def _get_subaccount_limit_dict(
        self,
        owner_id: Optional[str],
        subaccount_id: Optional[str],
        *,
        autocreate: bool = False,
    ) -> Optional[Dict[str, float | bool]]:
        if not subaccount_id:
            return None
        owner_key = self._owner_key(owner_id)
        owner_limits = self._subaccount_limits.setdefault(owner_key, {})
        limit = owner_limits.get(subaccount_id)
        if limit is None and autocreate:
            profile = self._get_risk_profile_dict(owner_id)
            limit = {
                "max_order_notional": float(profile["max_order_notional"]),
                "kill_switch_enabled": False,
            }
            owner_limits[subaccount_id] = limit
        return limit

    def get_market_position(self, position_id: str) -> Optional[MarketPositionResponse]:
        return self._positions.get(position_id)

    def _get_risk_profile_dict(self, owner_id: Optional[str]) -> Dict[str, float]:
        owner_key = self._owner_key(owner_id)
        profile = self._risk_profiles.get(owner_key)
        if profile is None:
            profile = {
                "max_notional_limit": MAX_NOTIONAL_LIMIT,
                "max_margin_limit": MAX_MARGIN_LIMIT,
                "max_order_notional": MAX_NOTIONAL_LIMIT,
            }
            self._risk_profiles[owner_key] = profile
        return profile

    def get_risk_profile(self, owner_id: Optional[str]) -> RiskProfileResponse:
        owner_key = self._owner_key(owner_id)
        profile = self._get_risk_profile_dict(owner_id)
        return RiskProfileResponse(
            owner_id=owner_key,
            max_notional_limit=float(profile["max_notional_limit"]),
            max_margin_limit=float(profile["max_margin_limit"]),
            max_order_notional=float(profile["max_order_notional"]),
            kill_switch_enabled=bool(self._kill_switches.get(owner_key, False)),
            updated_at=datetime.utcnow().isoformat() + "Z",
        )

    def update_risk_profile(
        self, owner_id: Optional[str], request: RiskProfileUpdateRequest
    ) -> RiskProfileResponse:
        owner_key = self._owner_key(owner_id)
        profile = self._get_risk_profile_dict(owner_id)
        if request.max_notional_limit is not None:
            profile["max_notional_limit"] = float(request.max_notional_limit)
        if request.max_margin_limit is not None:
            profile["max_margin_limit"] = float(request.max_margin_limit)
        if request.max_order_notional is not None:
            profile["max_order_notional"] = float(request.max_order_notional)
        self._record_event(
            "risk.profile_updated",
            "account",
            owner_key,
            {
                "max_notional_limit": profile["max_notional_limit"],
                "max_margin_limit": profile["max_margin_limit"],
                "max_order_notional": profile["max_order_notional"],
            },
        )
        self._persist_state()
        return self.get_risk_profile(owner_id)

    def set_kill_switch(
        self, owner_id: Optional[str], *, enabled: bool, reason: str
    ) -> KillSwitchUpdateResponse:
        owner_key = self._owner_key(owner_id)
        self._kill_switches[owner_key] = enabled
        self._record_event(
            "risk.kill_switch_updated",
            "account",
            owner_key,
            {"kill_switch_enabled": enabled, "reason": reason},
        )
        self._persist_state()
        return KillSwitchUpdateResponse(
            owner_id=owner_key,
            kill_switch_enabled=enabled,
            reason=reason,
            updated_at=datetime.utcnow().isoformat() + "Z",
        )

    def _assert_trading_enabled(
        self,
        owner_id: Optional[str],
        strategy_tag: Optional[str] = None,
        subaccount_id: Optional[str] = None,
    ) -> None:
        owner_key = self._owner_key(owner_id)
        if self._kill_switches.get(owner_key, False):
            raise ValueError("risk_kill_switch_enabled")
        strategy_limit = self._get_strategy_limit_dict(owner_id, strategy_tag)
        if strategy_limit and bool(strategy_limit.get("kill_switch_enabled", False)):
            raise ValueError("risk_strategy_kill_switch_enabled")
        subaccount_limit = self._get_subaccount_limit_dict(
            owner_id, subaccount_id, autocreate=bool(subaccount_id)
        )
        if subaccount_limit and bool(subaccount_limit.get("kill_switch_enabled", False)):
            raise ValueError("risk_subaccount_kill_switch_enabled")

    def _get_strategy_limit_dict(
        self, owner_id: Optional[str], strategy_tag: Optional[str]
    ) -> Optional[Dict[str, float | bool]]:
        if not strategy_tag:
            return None
        owner_key = self._owner_key(owner_id)
        owner_limits = self._strategy_limits.get(owner_key, {})
        return owner_limits.get(strategy_tag)

    def upsert_strategy_limit(
        self, owner_id: Optional[str], request: StrategyLimitUpdateRequest
    ) -> StrategyLimitResponse:
        owner_key = self._owner_key(owner_id)
        self._strategy_limits.setdefault(owner_key, {})
        self._strategy_limits[owner_key][request.strategy_tag] = {
            "max_order_notional": request.max_order_notional,
            "kill_switch_enabled": request.kill_switch_enabled,
        }
        self._record_event(
            "risk.strategy_limit_updated",
            "account",
            owner_key,
            {
                "strategy_tag": request.strategy_tag,
                "max_order_notional": request.max_order_notional,
                "kill_switch_enabled": request.kill_switch_enabled,
            },
        )
        self._persist_state()
        return StrategyLimitResponse(
            owner_id=owner_key,
            strategy_tag=request.strategy_tag,
            max_order_notional=request.max_order_notional,
            kill_switch_enabled=request.kill_switch_enabled,
            updated_at=datetime.utcnow().isoformat() + "Z",
        )

    def list_strategy_limits(self, owner_id: Optional[str]) -> List[StrategyLimitResponse]:
        owner_key = self._owner_key(owner_id)
        limits = self._strategy_limits.get(owner_key, {})
        rows = [
            StrategyLimitResponse(
                owner_id=owner_key,
                strategy_tag=strategy_tag,
                max_order_notional=float(row.get("max_order_notional", MAX_NOTIONAL_LIMIT)),
                kill_switch_enabled=bool(row.get("kill_switch_enabled", False)),
                updated_at=datetime.utcnow().isoformat() + "Z",
            )
            for strategy_tag, row in sorted(limits.items())
        ]
        return rows

    def list_subaccount_limits(self, owner_id: Optional[str]) -> List[TradingSubaccountRiskResponse]:
        owner_key = self._owner_key(owner_id)
        # Ensure main exists for a realistic desk default.
        self._get_subaccount_limit_dict(owner_id, "main", autocreate=True)
        limits = self._subaccount_limits.get(owner_key, {})
        return [
            TradingSubaccountRiskResponse(
                owner_id=owner_key,
                subaccount_id=subaccount_id,
                max_order_notional=float(row.get("max_order_notional", MAX_NOTIONAL_LIMIT)),
                kill_switch_enabled=bool(row.get("kill_switch_enabled", False)),
                updated_at=datetime.utcnow().isoformat() + "Z",
            )
            for subaccount_id, row in sorted(limits.items())
        ]

    def upsert_subaccount_limit(
        self,
        owner_id: Optional[str],
        request: TradingSubaccountRiskUpdateRequest,
    ) -> TradingSubaccountRiskResponse:
        owner_key = self._owner_key(owner_id)
        self._subaccount_limits.setdefault(owner_key, {})
        self._subaccount_limits[owner_key][request.subaccount_id] = {
            "max_order_notional": request.max_order_notional,
            "kill_switch_enabled": request.kill_switch_enabled,
        }
        self._record_event(
            "risk.subaccount_limit_updated",
            "account",
            owner_key,
            {
                "subaccount_id": request.subaccount_id,
                "max_order_notional": request.max_order_notional,
                "kill_switch_enabled": request.kill_switch_enabled,
            },
        )
        self._persist_state()
        return TradingSubaccountRiskResponse(
            owner_id=owner_key,
            subaccount_id=request.subaccount_id,
            max_order_notional=request.max_order_notional,
            kill_switch_enabled=request.kill_switch_enabled,
            updated_at=datetime.utcnow().isoformat() + "Z",
        )

    def get_trading_hierarchy(self, owner_id: Optional[str]) -> TradingHierarchyResponse:
        owner_key = self._owner_key(owner_id)
        hierarchy = self._get_owner_hierarchy_dict(owner_id)
        subaccounts = self.list_subaccount_limits(owner_id)
        return TradingHierarchyResponse(
            owner_id=owner_key,
            org_id=hierarchy["org_id"],
            account_id=hierarchy["account_id"],
            subaccounts=subaccounts,
            updated_at=datetime.utcnow().isoformat() + "Z",
        )

    def get_risk_summary(self, owner_id: Optional[str]) -> RiskSummaryResponse:
        owner_key = self._owner_key(owner_id)
        profile = self._get_risk_profile_dict(owner_id)
        used_notional = 0.0
        used_margin = 0.0

        for position in self._positions.values():
            if self._owner_key(position.owner_id) != owner_key:
                continue
            if position.status == MarketPositionStatus.OPEN:
                used_notional += position.notional

        for order in self._orders.values():
            if self._owner_key(order.owner_id) != owner_key:
                continue
            if order.status in (ExchangeOrderStatus.OPEN, ExchangeOrderStatus.PARTIALLY_FILLED):
                used_notional += order.remaining_ngh * order.price_per_ngh

        for contract in self._option_contracts.values():
            if self._owner_key(contract.owner_id) != owner_key:
                continue
            if contract.status == OptionContractStatus.OPEN:
                used_notional += contract.forward_price_per_ngh * contract.quantity_ngh
                used_margin += compute_option_initial_margin(contract)

        for order in self._option_orders.values():
            if self._owner_key(order.owner_id) != owner_key:
                continue
            if order.status in (OptionOrderStatus.OPEN, OptionOrderStatus.PARTIALLY_FILLED):
                order_notional = order.remaining_ngh * order.limit_price_per_ngh
                used_notional += order_notional
                used_margin += 0.25 * order_notional

        return RiskSummaryResponse(
            owner_id=owner_key,
            max_notional_limit=float(profile["max_notional_limit"]),
            used_notional=used_notional,
            remaining_notional=max(0.0, float(profile["max_notional_limit"]) - used_notional),
            max_margin_limit=float(profile["max_margin_limit"]),
            used_margin=used_margin,
            remaining_margin=max(0.0, float(profile["max_margin_limit"]) - used_margin),
            updated_at=datetime.utcnow().isoformat() + "Z",
        )

    def preview_exchange_pretrade(
        self, request: ExchangePretradeRequest, owner_id: Optional[str]
    ) -> PretradeCheckResponse:
        reasons: List[str] = []
        order_notional = request.price_per_ngh * request.quantity_ngh
        estimated_margin = 0.1 * order_notional
        hierarchy = self._get_owner_hierarchy_dict(owner_id)
        try:
            self._assert_trading_enabled(
                owner_id, request.strategy_tag, request.subaccount_id
            )
            self._assert_risk_limits(
                owner_id,
                increment_notional=order_notional,
                increment_margin=estimated_margin,
                order_notional=order_notional,
                strategy_tag=request.strategy_tag,
                subaccount_id=request.subaccount_id,
            )
            if request.time_in_force == TimeInForce.FOK and not self._can_fully_fill_exchange_order(
                request.product_key, request.side, request.price_per_ngh, request.quantity_ngh
            ):
                reasons.append("exchange_fok_not_fillable")
            if request.time_in_force == TimeInForce.IOC:
                reasons.append("ioc_may_partially_fill_then_cancel")
        except ValueError as exc:
            reasons.append(str(exc))
        return PretradeCheckResponse(
            approved=len(reasons) == 0,
            reasons=reasons,
            estimated_notional=order_notional,
            estimated_margin=estimated_margin,
            account_scope=hierarchy["account_id"],
            subaccount_scope=request.subaccount_id,
            risk_snapshot=self.get_risk_summary(owner_id),
        )

    def preview_option_pretrade(
        self, request: OptionPretradeRequest, owner_id: Optional[str]
    ) -> PretradeCheckResponse:
        reasons: List[str] = []
        order_notional = request.limit_price_per_ngh * request.quantity_ngh
        estimated_margin = 0.25 * order_notional
        hierarchy = self._get_owner_hierarchy_dict(owner_id)
        if request.contract_id not in self._option_contracts:
            reasons.append("option_contract_not_found")
        try:
            self._assert_trading_enabled(
                owner_id, request.strategy_tag, request.subaccount_id
            )
            self._assert_risk_limits(
                owner_id,
                increment_notional=order_notional,
                increment_margin=estimated_margin,
                order_notional=order_notional,
                strategy_tag=request.strategy_tag,
                subaccount_id=request.subaccount_id,
            )
            if request.time_in_force == TimeInForce.FOK and not self._can_fully_fill_option_order(
                request.contract_id,
                request.side,
                request.limit_price_per_ngh,
                request.quantity_ngh,
            ):
                reasons.append("option_fok_not_fillable")
            if request.time_in_force == TimeInForce.IOC:
                reasons.append("ioc_may_partially_fill_then_cancel")
        except ValueError as exc:
            reasons.append(str(exc))
        return PretradeCheckResponse(
            approved=len(reasons) == 0,
            reasons=reasons,
            estimated_notional=order_notional,
            estimated_margin=estimated_margin,
            account_scope=hierarchy["account_id"],
            subaccount_scope=request.subaccount_id,
            risk_snapshot=self.get_risk_summary(owner_id),
        )

    def get_trader_portfolio(self, owner_id: Optional[str]) -> TraderPortfolioResponse:
        owner_key = self._owner_key(owner_id)

        futures_position_cost: Dict[str, float] = {}
        futures_position_qty: Dict[str, float] = {}
        futures_last_price: Dict[str, float] = {}
        futures_trade_count = 0

        for trade in self._trades:
            buy_order = self._orders.get(trade.buy_order_id)
            sell_order = self._orders.get(trade.sell_order_id)
            key = trade.product_key.as_storage_key()

            if buy_order and self._owner_key(buy_order.owner_id) == owner_key:
                futures_position_qty[key] = futures_position_qty.get(key, 0.0) + trade.quantity_ngh
                futures_position_cost[key] = futures_position_cost.get(key, 0.0) + (
                    trade.quantity_ngh * trade.price_per_ngh
                )
                futures_trade_count += 1
            if sell_order and self._owner_key(sell_order.owner_id) == owner_key:
                futures_position_qty[key] = futures_position_qty.get(key, 0.0) - trade.quantity_ngh
                futures_position_cost[key] = futures_position_cost.get(key, 0.0) - (
                    trade.quantity_ngh * trade.price_per_ngh
                )
                futures_trade_count += 1
            futures_last_price[key] = trade.price_per_ngh

        option_position_cost: Dict[str, float] = {}
        option_position_qty: Dict[str, float] = {}
        option_last_price: Dict[str, float] = {}
        option_trade_count = 0

        for trade in self._option_trades:
            buy_order = self._option_orders.get(trade.buy_order_id)
            sell_order = self._option_orders.get(trade.sell_order_id)
            key = trade.contract_id

            if buy_order and self._owner_key(buy_order.owner_id) == owner_key:
                option_position_qty[key] = option_position_qty.get(key, 0.0) + trade.quantity_ngh
                option_position_cost[key] = option_position_cost.get(key, 0.0) + (
                    trade.quantity_ngh * trade.price_per_ngh
                )
                option_trade_count += 1
            if sell_order and self._owner_key(sell_order.owner_id) == owner_key:
                option_position_qty[key] = option_position_qty.get(key, 0.0) - trade.quantity_ngh
                option_position_cost[key] = option_position_cost.get(key, 0.0) - (
                    trade.quantity_ngh * trade.price_per_ngh
                )
                option_trade_count += 1
            option_last_price[key] = trade.price_per_ngh

        futures_positions: List[FuturesPositionRow] = []
        option_positions: List[OptionPositionRow] = []
        unrealized_total = 0.0

        for key, qty in futures_position_qty.items():
            if abs(qty) < 1e-12:
                continue
            avg_entry = futures_position_cost.get(key, 0.0) / qty
            last_price = futures_last_price.get(key, avg_entry)
            pnl = (last_price - avg_entry) * qty
            futures_positions.append(
                FuturesPositionRow(
                    product_key=self._product_key_from_storage_key(key),
                    net_quantity_ngh=qty,
                    avg_entry_price=avg_entry,
                    last_price=last_price,
                    unrealized_pnl=pnl,
                )
            )
            unrealized_total += pnl

        for contract_id, qty in option_position_qty.items():
            if abs(qty) < 1e-12:
                continue
            contract = self._option_contracts.get(contract_id)
            if contract is None:
                continue
            avg_entry = option_position_cost.get(contract_id, 0.0) / qty
            last_premium = option_last_price.get(contract_id, avg_entry)
            pnl = (last_premium - avg_entry) * qty
            option_positions.append(
                OptionPositionRow(
                    contract_id=contract_id,
                    product_key=contract.product_key,
                    net_quantity_ngh=qty,
                    avg_entry_premium=avg_entry,
                    last_premium=last_premium,
                    unrealized_pnl=pnl,
                )
            )
            unrealized_total += pnl

        open_futures_orders = sum(
            1
            for order in self._orders.values()
            if self._owner_key(order.owner_id) == owner_key
            and order.status in (ExchangeOrderStatus.OPEN, ExchangeOrderStatus.PARTIALLY_FILLED)
            and order.remaining_ngh > 0
        )
        open_option_orders = sum(
            1
            for order in self._option_orders.values()
            if self._owner_key(order.owner_id) == owner_key
            and order.status in (OptionOrderStatus.OPEN, OptionOrderStatus.PARTIALLY_FILLED)
            and order.remaining_ngh > 0
        )

        return TraderPortfolioResponse(
            owner_id=owner_key,
            unrealized_pnl_total=unrealized_total,
            open_futures_order_count=open_futures_orders,
            open_option_order_count=open_option_orders,
            recent_futures_trade_count=futures_trade_count,
            recent_option_trade_count=option_trade_count,
            futures_positions=sorted(
                futures_positions, key=lambda p: abs(p.unrealized_pnl), reverse=True
            ),
            option_positions=sorted(
                option_positions, key=lambda p: abs(p.unrealized_pnl), reverse=True
            ),
            updated_at=datetime.utcnow().isoformat() + "Z",
        )

    def get_margin_stress(
        self,
        owner_id: Optional[str],
        *,
        price_shock_pct: float,
        option_vol_shock_pct: float,
    ) -> MarginStressResponse:
        portfolio = self.get_trader_portfolio(owner_id)
        risk = self.get_risk_summary(owner_id)

        stressed_pnl = 0.0
        for futures_position in portfolio.futures_positions:
            shocked_last = futures_position.last_price * (1.0 + price_shock_pct)
            stressed_pnl += (
                shocked_last - futures_position.avg_entry_price
            ) * futures_position.net_quantity_ngh

        for option_position in portfolio.option_positions:
            shocked_last = option_position.last_premium * (1.0 + option_vol_shock_pct)
            stressed_pnl += (
                shocked_last - option_position.avg_entry_premium
            ) * option_position.net_quantity_ngh

        used_margin = max(risk.used_margin, 1e-9)
        stress_margin_ratio = max(0.0, (risk.max_margin_limit + stressed_pnl) / used_margin)
        margin_call = stress_margin_ratio < 1.1
        return MarginStressResponse(
            owner_id=portfolio.owner_id,
            base_unrealized_pnl=portfolio.unrealized_pnl_total,
            stressed_unrealized_pnl=stressed_pnl,
            used_margin=risk.used_margin,
            stress_margin_ratio=stress_margin_ratio,
            margin_call_triggered=margin_call,
            price_shock_pct=price_shock_pct,
            option_vol_shock_pct=option_vol_shock_pct,
            updated_at=datetime.utcnow().isoformat() + "Z",
        )

    def liquidate_account(
        self, owner_id: Optional[str], *, reason: str = "manual_liquidation"
    ) -> LiquidationResponse:
        owner_key = self._owner_key(owner_id)
        cancelled_futures = 0
        cancelled_options = 0

        for order in self._orders.values():
            if self._owner_key(order.owner_id) != owner_key:
                continue
            if order.status in (ExchangeOrderStatus.OPEN, ExchangeOrderStatus.PARTIALLY_FILLED):
                order.status = ExchangeOrderStatus.CANCELLED
                order.remaining_ngh = 0.0
                cancelled_futures += 1

        for order in self._option_orders.values():
            if self._owner_key(order.owner_id) != owner_key:
                continue
            if order.status in (OptionOrderStatus.OPEN, OptionOrderStatus.PARTIALLY_FILLED):
                order.status = OptionOrderStatus.CANCELLED
                order.remaining_ngh = 0.0
                cancelled_options += 1

        self._record_event(
            "risk.account_liquidated",
            "account",
            owner_key,
            {
                "cancelled_futures_orders": cancelled_futures,
                "cancelled_option_orders": cancelled_options,
                "reason": reason,
            },
        )
        self._persist_state()
        return LiquidationResponse(
            owner_id=owner_key,
            cancelled_futures_orders=cancelled_futures,
            cancelled_option_orders=cancelled_options,
            liquidation_triggered=(cancelled_futures + cancelled_options) > 0,
            reason=reason,
            updated_at=datetime.utcnow().isoformat() + "Z",
        )

    def get_provider_sla_summary(self, owner_id: Optional[str]) -> ProviderSlaSummaryResponse:
        owner_key = self._owner_key(owner_id)
        lots = [
            lot
            for lot in self._lots.values()
            if owner_id is None or self._owner_key(lot.provider_id) == owner_key
        ]
        total = len(lots)
        pending = sum(1 for lot in lots if lot.status == LotStatus.PENDING)
        ready = sum(1 for lot in lots if lot.status == LotStatus.READY)
        completed = sum(1 for lot in lots if lot.status == LotStatus.COMPLETED)
        failed = sum(1 for lot in lots if lot.status == LotStatus.FAILED)
        success_rate = (completed / max(1, completed + failed)) if total else 0.0

        prepare_durations: List[float] = []
        completion_durations: List[float] = []
        for lot in lots:
            created = self._parse_iso_ts(lot.created_at)
            prepared = self._parse_iso_ts(lot.prepared_at)
            completed_ts = self._parse_iso_ts(lot.completed_at)
            if created and prepared:
                prepare_durations.append(max(0.0, (prepared - created).total_seconds()))
            if created and completed_ts:
                completion_durations.append(max(0.0, (completed_ts - created).total_seconds()))

        avg_prepare = sum(prepare_durations) / len(prepare_durations) if prepare_durations else 0.0
        avg_completion = (
            sum(completion_durations) / len(completion_durations) if completion_durations else 0.0
        )
        return ProviderSlaSummaryResponse(
            owner_id=owner_key,
            total_lots=total,
            pending_lots=pending,
            ready_lots=ready,
            completed_lots=completed,
            failed_lots=failed,
            success_rate=success_rate,
            avg_prepare_seconds=avg_prepare,
            avg_completion_seconds=avg_completion,
            updated_at=datetime.utcnow().isoformat() + "Z",
        )

    def get_trader_execution_metrics(
        self, owner_id: Optional[str]
    ) -> TraderExecutionMetricsResponse:
        owner_key = self._owner_key(owner_id)
        futures_orders = [
            order for order in self._orders.values() if self._owner_key(order.owner_id) == owner_key
        ]
        option_orders = [
            order
            for order in self._option_orders.values()
            if self._owner_key(order.owner_id) == owner_key
        ]

        futures_submitted = len(futures_orders)
        option_submitted = len(option_orders)
        futures_total_qty = sum(order.quantity_ngh for order in futures_orders)
        futures_filled_qty = sum(order.quantity_ngh - order.remaining_ngh for order in futures_orders)
        option_total_qty = sum(order.quantity_ngh for order in option_orders)
        option_filled_qty = sum(order.quantity_ngh - order.remaining_ngh for order in option_orders)

        adverse_slippage_bps: List[float] = []
        time_to_fill_seconds: List[float] = []

        for order in futures_orders:
            fills = [
                trade
                for trade in self._trades
                if trade.buy_order_id == order.order_id or trade.sell_order_id == order.order_id
            ]
            if fills:
                first_fill = min(fills, key=lambda trade: trade.created_at)
                order_ts = self._parse_iso_ts(order.created_at)
                fill_ts = self._parse_iso_ts(first_fill.created_at)
                if order_ts and fill_ts:
                    time_to_fill_seconds.append(max(0.0, (fill_ts - order_ts).total_seconds()))
            for fill in fills:
                if order.side == ExchangeOrderSide.BUY:
                    bps = max(0.0, (fill.price_per_ngh - order.price_per_ngh) / order.price_per_ngh * 10000)
                else:
                    bps = max(0.0, (order.price_per_ngh - fill.price_per_ngh) / order.price_per_ngh * 10000)
                adverse_slippage_bps.append(bps)

        for order in option_orders:
            fills = [
                trade
                for trade in self._option_trades
                if trade.buy_order_id == order.order_id or trade.sell_order_id == order.order_id
            ]
            if fills:
                first_fill = min(fills, key=lambda trade: trade.created_at)
                order_ts = self._parse_iso_ts(order.created_at)
                fill_ts = self._parse_iso_ts(first_fill.created_at)
                if order_ts and fill_ts:
                    time_to_fill_seconds.append(max(0.0, (fill_ts - order_ts).total_seconds()))
            for fill in fills:
                if order.side == OptionOrderSide.BUY:
                    bps = max(
                        0.0,
                        (fill.price_per_ngh - order.limit_price_per_ngh)
                        / order.limit_price_per_ngh
                        * 10000,
                    )
                else:
                    bps = max(
                        0.0,
                        (order.limit_price_per_ngh - fill.price_per_ngh)
                        / order.limit_price_per_ngh
                        * 10000,
                    )
                adverse_slippage_bps.append(bps)

        return TraderExecutionMetricsResponse(
            owner_id=owner_key,
            futures_orders_submitted=futures_submitted,
            futures_fill_ratio=(futures_filled_qty / futures_total_qty) if futures_total_qty else 0.0,
            option_orders_submitted=option_submitted,
            option_fill_ratio=(option_filled_qty / option_total_qty) if option_total_qty else 0.0,
            avg_adverse_slippage_bps=(
                sum(adverse_slippage_bps) / len(adverse_slippage_bps)
                if adverse_slippage_bps
                else 0.0
            ),
            avg_time_to_first_fill_seconds=(
                sum(time_to_fill_seconds) / len(time_to_fill_seconds)
                if time_to_fill_seconds
                else 0.0
            ),
            updated_at=datetime.utcnow().isoformat() + "Z",
        )

    def get_strategy_execution_metrics(
        self, owner_id: Optional[str]
    ) -> StrategyExecutionMetricsResponse:
        owner_key = self._owner_key(owner_id)
        strategies: Dict[str, Dict[str, float]] = {}

        def ensure_row(tag: str) -> Dict[str, float]:
            if tag not in strategies:
                strategies[tag] = {
                    "futures_orders_submitted": 0.0,
                    "futures_total_qty": 0.0,
                    "futures_filled_qty": 0.0,
                    "option_orders_submitted": 0.0,
                    "option_total_qty": 0.0,
                    "option_filled_qty": 0.0,
                    "slippage_bps_sum": 0.0,
                    "slippage_count": 0.0,
                }
            return strategies[tag]

        for order in self._orders.values():
            if self._owner_key(order.owner_id) != owner_key:
                continue
            tag = order.strategy_tag or "default"
            row = ensure_row(tag)
            row["futures_orders_submitted"] += 1
            row["futures_total_qty"] += order.quantity_ngh
            row["futures_filled_qty"] += max(0.0, order.quantity_ngh - order.remaining_ngh)
            fills = [
                trade
                for trade in self._trades
                if trade.buy_order_id == order.order_id or trade.sell_order_id == order.order_id
            ]
            for fill in fills:
                if order.side == ExchangeOrderSide.BUY:
                    bps = max(0.0, (fill.price_per_ngh - order.price_per_ngh) / order.price_per_ngh * 10000)
                else:
                    bps = max(0.0, (order.price_per_ngh - fill.price_per_ngh) / order.price_per_ngh * 10000)
                row["slippage_bps_sum"] += bps
                row["slippage_count"] += 1

        for order in self._option_orders.values():
            if self._owner_key(order.owner_id) != owner_key:
                continue
            tag = order.strategy_tag or "default"
            row = ensure_row(tag)
            row["option_orders_submitted"] += 1
            row["option_total_qty"] += order.quantity_ngh
            row["option_filled_qty"] += max(0.0, order.quantity_ngh - order.remaining_ngh)
            fills = [
                trade
                for trade in self._option_trades
                if trade.buy_order_id == order.order_id or trade.sell_order_id == order.order_id
            ]
            for fill in fills:
                if order.side == OptionOrderSide.BUY:
                    bps = max(
                        0.0,
                        (fill.price_per_ngh - order.limit_price_per_ngh)
                        / order.limit_price_per_ngh
                        * 10000,
                    )
                else:
                    bps = max(
                        0.0,
                        (order.limit_price_per_ngh - fill.price_per_ngh)
                        / order.limit_price_per_ngh
                        * 10000,
                    )
                row["slippage_bps_sum"] += bps
                row["slippage_count"] += 1

        result_rows = []
        for tag, row in sorted(strategies.items()):
            result_rows.append(
                StrategyExecutionMetricsRow(
                    strategy_tag=tag,
                    futures_orders_submitted=int(row["futures_orders_submitted"]),
                    option_orders_submitted=int(row["option_orders_submitted"]),
                    futures_fill_ratio=(
                        row["futures_filled_qty"] / row["futures_total_qty"]
                        if row["futures_total_qty"]
                        else 0.0
                    ),
                    option_fill_ratio=(
                        row["option_filled_qty"] / row["option_total_qty"]
                        if row["option_total_qty"]
                        else 0.0
                    ),
                    avg_adverse_slippage_bps=(
                        row["slippage_bps_sum"] / row["slippage_count"]
                        if row["slippage_count"]
                        else 0.0
                    ),
                )
            )

        return StrategyExecutionMetricsResponse(
            owner_id=owner_key,
            rows=result_rows,
            updated_at=datetime.utcnow().isoformat() + "Z",
        )

    def get_provider_execution_metrics(
        self, owner_id: Optional[str]
    ) -> ProviderExecutionMetricsResponse:
        owner_key = self._owner_key(owner_id)
        lots = [
            lot
            for lot in self._lots.values()
            if owner_id is None or self._owner_key(lot.provider_id) == owner_key
        ]
        if not lots:
            return ProviderExecutionMetricsResponse(
                owner_id=owner_key,
                lots_observed=0,
                on_time_prepare_ratio=0.0,
                on_time_completion_ratio=0.0,
                avg_wall_time_seconds=0.0,
                updated_at=datetime.utcnow().isoformat() + "Z",
            )

        prepare_hits = 0
        prepare_total = 0
        completion_hits = 0
        completion_total = 0
        wall_times: List[float] = []
        for lot in lots:
            created_ts = self._parse_iso_ts(lot.created_at)
            prepared_ts = self._parse_iso_ts(lot.prepared_at)
            completed_ts = self._parse_iso_ts(lot.completed_at)
            if lot.wall_time_seconds:
                wall_times.append(float(lot.wall_time_seconds))

            if lot.window.sla.value == "urgent":
                prepare_target = 300.0
                completion_target = 1800.0
            elif lot.window.sla.value == "premium":
                prepare_target = 600.0
                completion_target = 3600.0
            else:
                prepare_target = 900.0
                completion_target = 7200.0

            if created_ts and prepared_ts:
                prepare_total += 1
                prepare_hits += int((prepared_ts - created_ts).total_seconds() <= prepare_target)
            if created_ts and completed_ts:
                completion_total += 1
                completion_hits += int((completed_ts - created_ts).total_seconds() <= completion_target)

        return ProviderExecutionMetricsResponse(
            owner_id=owner_key,
            lots_observed=len(lots),
            on_time_prepare_ratio=(prepare_hits / prepare_total) if prepare_total else 0.0,
            on_time_completion_ratio=(completion_hits / completion_total) if completion_total else 0.0,
            avg_wall_time_seconds=(sum(wall_times) / len(wall_times)) if wall_times else 0.0,
            updated_at=datetime.utcnow().isoformat() + "Z",
        )

    def get_provider_fleet_overview(self, owner_id: Optional[str]) -> ProviderFleetOverviewResponse:
        owner_key = self._owner_key(owner_id)
        nominated_total = sum(n.ngh_available for n in self._nominations.values())
        active_lots = sum(
            1
            for lot in self._lots.values()
            if lot.status in (LotStatus.PENDING, LotStatus.PREPARING, LotStatus.READY, LotStatus.RUNNING)
            and (owner_id is None or self._owner_key(lot.provider_id) == owner_key)
        )
        completed_lots = sum(
            1
            for lot in self._lots.values()
            if lot.status == LotStatus.COMPLETED
            and (owner_id is None or self._owner_key(lot.provider_id) == owner_key)
        )
        utilization = min(1.0, active_lots / max(1.0, nominated_total)) if nominated_total > 0 else 0.0
        return ProviderFleetOverviewResponse(
            owner_id=owner_key,
            nominated_ngh_total=nominated_total,
            lots_active=active_lots,
            lots_completed=completed_lots,
            utilization_ratio=utilization,
            updated_at=datetime.utcnow().isoformat() + "Z",
        )

    def _parse_iso_ts(self, value: Optional[str]) -> Optional[datetime]:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except Exception:
            return None

    def _assert_risk_limits(
        self,
        owner_id: Optional[str],
        *,
        increment_notional: float,
        increment_margin: float,
        order_notional: Optional[float] = None,
        strategy_tag: Optional[str] = None,
        subaccount_id: Optional[str] = None,
    ) -> None:
        if self.is_synthetic_owner(owner_id):
            return
        profile = self._get_risk_profile_dict(owner_id)
        summary = self.get_risk_summary(owner_id)
        check_order_notional = (
            order_notional if order_notional is not None else max(0.0, increment_notional)
        )
        strategy_limit = self._get_strategy_limit_dict(owner_id, strategy_tag)
        if strategy_limit is not None:
            strategy_cap = float(strategy_limit.get("max_order_notional", MAX_NOTIONAL_LIMIT))
            if check_order_notional > strategy_cap:
                raise ValueError(
                    f"risk_limit_strategy_order_notional_exceeded:{check_order_notional:.2f}>{strategy_cap:.2f}"
                )
        subaccount_limit = self._get_subaccount_limit_dict(
            owner_id, subaccount_id, autocreate=bool(subaccount_id)
        )
        if subaccount_limit is not None:
            subaccount_cap = float(subaccount_limit.get("max_order_notional", MAX_NOTIONAL_LIMIT))
            if check_order_notional > subaccount_cap:
                raise ValueError(
                    f"risk_limit_subaccount_order_notional_exceeded:{check_order_notional:.2f}>{subaccount_cap:.2f}"
                )
        if check_order_notional > float(profile["max_order_notional"]):
            raise ValueError(
                f"risk_limit_order_notional_exceeded:{check_order_notional:.2f}>{float(profile['max_order_notional']):.2f}"
            )
        if summary.used_notional + increment_notional > summary.max_notional_limit:
            raise ValueError(
                f"risk_limit_notional_exceeded:{summary.used_notional + increment_notional:.2f}>{summary.max_notional_limit:.2f}"
            )
        if summary.used_margin + increment_margin > summary.max_margin_limit:
            raise ValueError(
                f"risk_limit_margin_exceeded:{summary.used_margin + increment_margin:.2f}>{summary.max_margin_limit:.2f}"
            )

    # ---- jobs ----
    def create_job(
        self, request: JobCreateRequest, created_by: Optional[str] = None
    ) -> JobResponse:
        """Create a new job."""
        job = JobResponse(
            job_id=request.job_id,
            status=JobStatus.PENDING,
            window=request.window,
            package_index=request.package_index,
            created_at=datetime.utcnow().isoformat() + "Z",
            relay_links=None,
            created_by=created_by,
        )
        self._jobs[request.job_id] = job
        self._record_event(
            "job.created",
            "job",
            request.job_id,
            {
                "product_key": ProductKey.from_window(request.window).model_dump(mode="json"),
                "package_count": len(request.package_index),
                "created_by": created_by,
            },
        )
        return job

    def get_job(self, job_id: str) -> Optional[JobResponse]:
        """Get a job by ID."""
        return self._jobs.get(job_id)

    def list_jobs(
        self, created_by: Optional[str] = None, *, limit: Optional[int] = None
    ) -> List[JobResponse]:
        """List jobs, newest first. If created_by is set, only return that user's jobs."""
        jobs = list(self._jobs.values())
        if created_by is not None:
            jobs = [j for j in jobs if getattr(j, "created_by", None) == created_by]
        jobs.sort(key=lambda j: j.created_at or "", reverse=True)
        if limit is not None and limit > 0:
            jobs = jobs[:limit]
        return jobs

    # ---- vouchers (demo) ----
    def get_voucher_balance(self, key: str) -> float:
        """Get voucher balance for a given key."""
        return self._vouchers.get(key, 0.0)

    def get_deposited_voucher_balance(self, job_id: str, key: str) -> float:
        """Get deposited voucher balance for a job and product key."""
        return self._voucher_deposits.get(job_id, {}).get(key, 0.0)

    def set_voucher_balance(self, key: str, amount: float):
        """Set voucher balance for a given key (for testing/demo purposes)."""
        self._vouchers[key] = amount
        self._record_event(
            "voucher.balance_set",
            "voucher_balance",
            key,
            {"balance_ngh": amount},
        )

    def apply_demo_voucher_wallet_topup(
        self, amount_ngh: float, *, fill_template_hours: bool = True
    ) -> None:
        """Set wallet balance to amount_ngh for persisted keys, demo key, live catalog keys, and optionally every template×hour."""
        keys: set[str] = set(self._vouchers.keys())
        keys.add(self.get_demo_product_key().as_storage_key())
        try:
            from app.services.market_simulator import market_simulator

            for _, pk in market_simulator.product_catalog():
                keys.add(pk.as_storage_key())
            if fill_template_hours:
                for sk in market_simulator.voucher_topup_storage_keys():
                    keys.add(sk)
        except Exception:
            pass
        amt = float(amount_ngh)
        for k in keys:
            self._vouchers[k] = amt
        self._persist_state()

    def list_voucher_balances(self) -> List[VoucherBalanceResponse]:
        """List voucher balances with aggregate deposited amounts."""
        balances: List[VoucherBalanceResponse] = []
        for key, amount in sorted(self._vouchers.items()):
            deposited = sum(
                deposits.get(key, 0.0) for deposits in self._voucher_deposits.values()
            )
            balances.append(
                VoucherBalanceResponse(
                    product_key=self._product_key_from_storage_key(key),
                    balance_ngh=amount,
                    deposited_ngh=deposited,
                )
            )
        return balances

    def deposit_vouchers(
        self, job_id: str, product_key: ProductKey, amount_ngh: float
    ) -> VoucherDepositResponse:
        """Deposit vouchers against a job and reduce wallet balance."""
        key = product_key.as_storage_key()
        current_balance = self.get_voucher_balance(key)
        if current_balance < amount_ngh:
            raise ValueError("insufficient_voucher_balance")

        self._vouchers[key] = current_balance - amount_ngh
        self._voucher_deposits.setdefault(job_id, {})
        self._voucher_deposits[job_id][key] = (
            self._voucher_deposits[job_id].get(key, 0.0) + amount_ngh
        )
        self._record_event(
            "voucher.deposited",
            "job",
            job_id,
            {
                "product_key": product_key.model_dump(mode="json"),
                "amount_ngh": amount_ngh,
                "remaining_balance_ngh": self._vouchers[key],
            },
        )
        return VoucherDepositResponse(
            job_id=job_id,
            product_key=product_key,
            deposited_ngh=self._voucher_deposits[job_id][key],
            remaining_balance_ngh=self._vouchers[key],
        )

    # ---- market positions ----
    def create_market_position(
        self,
        request: MarketPositionCreateRequest,
        owner_id: Optional[str] = None,
    ) -> MarketPositionResponse:
        """Create a new physically deliverable demo position."""
        self._assert_trading_enabled(owner_id)
        position_id = str(uuid.uuid4())
        position = MarketPositionResponse(
            position_id=position_id,
            product_key=request.product_key,
            side=request.side,
            quantity_ngh=request.quantity_ngh,
            price_per_ngh=request.price_per_ngh,
            notional=request.quantity_ngh * request.price_per_ngh,
            status=MarketPositionStatus.OPEN,
            created_at=datetime.utcnow().isoformat() + "Z",
            owner_id=owner_id,
        )
        self._positions[position_id] = position
        self._record_event(
            "position.created",
            "position",
            position_id,
            {
                "product_key": request.product_key.model_dump(mode="json"),
                "side": request.side.value,
                "quantity_ngh": request.quantity_ngh,
                "price_per_ngh": request.price_per_ngh,
                "owner_id": owner_id,
            },
        )
        return position

    def list_market_positions(
        self, owner_id: Optional[str] = None, *, limit: Optional[int] = None
    ) -> List[MarketPositionResponse]:
        """List positions, newest first, optionally filtered by owner."""
        positions = list(self._positions.values())
        if owner_id is not None:
            positions = [p for p in positions if p.owner_id == owner_id]
        positions.sort(key=lambda p: p.created_at, reverse=True)
        if limit is not None and limit > 0:
            positions = positions[:limit]
        return positions

    def settle_market_position(self, position_id: str) -> Optional[MarketPositionResponse]:
        """Settle a market position into voucher balance."""
        position = self._positions.get(position_id)
        if not position:
            return None
        if position.status == MarketPositionStatus.SETTLED:
            return position

        position.status = MarketPositionStatus.SETTLED
        position.settled_at = datetime.utcnow().isoformat() + "Z"
        key = position.product_key.as_storage_key()
        if position.side.value == "buy":
            self._vouchers[key] = self.get_voucher_balance(key) + position.quantity_ngh
        else:
            self._vouchers[key] = max(0.0, self.get_voucher_balance(key) - position.quantity_ngh)
        self._record_event(
            "position.settled",
            "position",
            position_id,
            {
                "product_key": position.product_key.model_dump(mode="json"),
                "quantity_ngh": position.quantity_ngh,
                "voucher_balance_ngh": self._vouchers[key],
            },
        )
        return position

    # ---- exchange ----
    def list_exchange_orders(
        self,
        *,
        product_key: Optional[ProductKey] = None,
        owner_id: Optional[str] = None,
    ) -> List[ExchangeOrderResponse]:
        orders = list(self._orders.values())
        if product_key is not None:
            key = product_key.as_storage_key()
            orders = [o for o in orders if o.product_key.as_storage_key() == key]
        if owner_id is not None:
            orders = [o for o in orders if o.owner_id == owner_id]
        orders.sort(key=lambda o: o.created_at, reverse=True)
        return orders

    def list_exchange_trades(
        self, *, product_key: Optional[ProductKey] = None, limit: int = 30
    ) -> List[ExchangeTradeResponse]:
        if product_key is None:
            return list(islice(reversed(self._trades), max(0, limit)))
        key = product_key.as_storage_key()
        out: List[ExchangeTradeResponse] = []
        for trade in reversed(self._trades):
            if trade.product_key.as_storage_key() == key:
                out.append(trade)
                if len(out) >= limit:
                    break
        return out

    def create_exchange_order(
        self, request: ExchangeOrderCreateRequest, owner_id: Optional[str] = None
    ) -> ExchangeOrderResponse:
        self._assert_demo_isolation_for_synthetic(
            owner_id,
            request.product_key,
            entity="exchange_order",
        )
        self._assert_trading_enabled(owner_id, request.strategy_tag, request.subaccount_id)
        order_notional = request.price_per_ngh * request.quantity_ngh
        self._assert_risk_limits(
            owner_id,
            increment_notional=order_notional,
            increment_margin=0.1 * order_notional,
            order_notional=order_notional,
            strategy_tag=request.strategy_tag,
            subaccount_id=request.subaccount_id,
        )
        if request.time_in_force == TimeInForce.FOK and not self._can_fully_fill_exchange_order(
            request.product_key, request.side, request.price_per_ngh, request.quantity_ngh
        ):
            raise ValueError("exchange_fok_not_fillable")

        order_id = str(uuid.uuid4())
        order = ExchangeOrderResponse(
            order_id=order_id,
            product_key=request.product_key,
            side=request.side,
            price_per_ngh=request.price_per_ngh,
            quantity_ngh=request.quantity_ngh,
            remaining_ngh=request.quantity_ngh,
            time_in_force=request.time_in_force,
            status=ExchangeOrderStatus.OPEN,
            created_at=datetime.utcnow().isoformat() + "Z",
            owner_id=owner_id,
            subaccount_id=request.subaccount_id,
            strategy_tag=request.strategy_tag,
        )
        self._orders[order_id] = order
        self._record_event(
            "exchange.order_created",
            "exchange_order",
            order_id,
            {
                "product_key": request.product_key.model_dump(mode="json"),
                "side": request.side.value,
                "price_per_ngh": request.price_per_ngh,
                "quantity_ngh": request.quantity_ngh,
                "time_in_force": request.time_in_force.value,
                "owner_id": owner_id,
                "subaccount_id": request.subaccount_id,
                "strategy_tag": request.strategy_tag,
            },
        )
        self._match_exchange_order(order)
        if order.remaining_ngh > 0 and order.time_in_force == TimeInForce.IOC:
            order.status = ExchangeOrderStatus.CANCELLED
            order.remaining_ngh = 0.0
            self._record_event(
                "exchange.order_ioc_expired",
                "exchange_order",
                order_id,
                {"owner_id": owner_id},
            )
        self._persist_state()
        return self._orders[order_id]

    def amend_exchange_order(
        self,
        order_id: str,
        request: ExchangeOrderAmendRequest,
        owner_id: Optional[str] = None,
    ) -> Optional[ExchangeOrderResponse]:
        order = self._orders.get(order_id)
        if order is None:
            return None
        self._assert_trading_enabled(owner_id, order.strategy_tag, order.subaccount_id)
        if owner_id is not None and self._owner_key(order.owner_id) != self._owner_key(owner_id):
            raise ValueError("exchange_order_owner_mismatch")
        if order.status in (ExchangeOrderStatus.FILLED, ExchangeOrderStatus.CANCELLED):
            raise ValueError("exchange_order_not_amendable")

        filled_qty = order.quantity_ngh - order.remaining_ngh
        next_qty = request.quantity_ngh if request.quantity_ngh is not None else order.quantity_ngh
        next_price = (
            request.price_per_ngh if request.price_per_ngh is not None else order.price_per_ngh
        )
        if next_qty < filled_qty:
            raise ValueError("exchange_order_quantity_below_filled")

        order.quantity_ngh = next_qty
        order.price_per_ngh = next_price
        order.remaining_ngh = max(0.0, next_qty - filled_qty)
        self._assert_risk_limits(
            owner_id,
            increment_notional=0.0,
            increment_margin=0.0,
            order_notional=next_price * max(order.remaining_ngh, 0.0),
            strategy_tag=order.strategy_tag,
            subaccount_id=order.subaccount_id,
        )
        order.status = (
            ExchangeOrderStatus.FILLED
            if order.remaining_ngh <= 0
            else (
                ExchangeOrderStatus.PARTIALLY_FILLED
                if filled_qty > 0
                else ExchangeOrderStatus.OPEN
            )
        )

        self._record_event(
            "exchange.order_amended",
            "exchange_order",
            order_id,
            {
                "owner_id": owner_id,
                "price_per_ngh": order.price_per_ngh,
                "quantity_ngh": order.quantity_ngh,
                "remaining_ngh": order.remaining_ngh,
            },
        )
        if order.remaining_ngh > 0:
            self._match_exchange_order(order)
        if order.remaining_ngh > 0 and order.time_in_force == TimeInForce.IOC:
            order.status = ExchangeOrderStatus.CANCELLED
            order.remaining_ngh = 0.0
        self._persist_state()
        return order

    def cancel_exchange_order(
        self, order_id: str, owner_id: Optional[str] = None
    ) -> Optional[ExchangeOrderResponse]:
        order = self._orders.get(order_id)
        if order is None:
            return None
        if owner_id is not None and self._owner_key(order.owner_id) != self._owner_key(owner_id):
            raise ValueError("exchange_order_owner_mismatch")
        if order.status in (ExchangeOrderStatus.FILLED, ExchangeOrderStatus.CANCELLED):
            return order
        order.status = ExchangeOrderStatus.CANCELLED
        order.remaining_ngh = 0.0
        self._record_event(
            "exchange.order_cancelled",
            "exchange_order",
            order_id,
            {"owner_id": owner_id},
        )
        self._persist_state()
        return order

    def get_exchange_orderbook(self, product_key: ProductKey) -> ExchangeOrderBookResponse:
        key = product_key.as_storage_key()
        active = [
            order
            for order in self._orders.values()
            if order.product_key.as_storage_key() == key
            and order.status in (ExchangeOrderStatus.OPEN, ExchangeOrderStatus.PARTIALLY_FILLED)
            and order.remaining_ngh > 0
        ]
        bids: Dict[float, float] = {}
        asks: Dict[float, float] = {}
        for order in active:
            book = bids if order.side == ExchangeOrderSide.BUY else asks
            book[order.price_per_ngh] = book.get(order.price_per_ngh, 0.0) + order.remaining_ngh

        bid_levels = [
            ExchangeOrderBookLevel(price_per_ngh=price, quantity_ngh=qty)
            for price, qty in sorted(bids.items(), key=lambda item: item[0], reverse=True)
        ]
        ask_levels = [
            ExchangeOrderBookLevel(price_per_ngh=price, quantity_ngh=qty)
            for price, qty in sorted(asks.items(), key=lambda item: item[0])
        ]
        best_bid = bid_levels[0].price_per_ngh if bid_levels else None
        best_ask = ask_levels[0].price_per_ngh if ask_levels else None
        spread = (best_ask - best_bid) if (best_bid is not None and best_ask is not None) else None
        return ExchangeOrderBookResponse(
            product_key=product_key,
            bids=bid_levels[:10],
            asks=ask_levels[:10],
            spread=spread,
            best_bid=best_bid,
            best_ask=best_ask,
        )

    def _match_exchange_order(self, incoming: ExchangeOrderResponse) -> None:
        if incoming.remaining_ngh <= 0:
            return

        key = incoming.product_key.as_storage_key()
        opposite_side = (
            ExchangeOrderSide.SELL
            if incoming.side == ExchangeOrderSide.BUY
            else ExchangeOrderSide.BUY
        )
        candidates = [
            order
            for order in self._orders.values()
            if order.order_id != incoming.order_id
            and order.product_key.as_storage_key() == key
            and order.side == opposite_side
            and order.status in (ExchangeOrderStatus.OPEN, ExchangeOrderStatus.PARTIALLY_FILLED)
            and order.remaining_ngh > 0
        ]

        if incoming.side == ExchangeOrderSide.BUY:
            candidates = [c for c in candidates if c.price_per_ngh <= incoming.price_per_ngh]
            candidates.sort(key=lambda c: (c.price_per_ngh, c.created_at))
        else:
            candidates = [c for c in candidates if c.price_per_ngh >= incoming.price_per_ngh]
            candidates.sort(key=lambda c: (-c.price_per_ngh, c.created_at))

        for resting in candidates:
            if incoming.remaining_ngh <= 0:
                break
            fill_qty = min(incoming.remaining_ngh, resting.remaining_ngh)
            if fill_qty <= 0:
                continue

            # Price-time priority: trade at resting order's price.
            trade_price = resting.price_per_ngh
            incoming.remaining_ngh -= fill_qty
            resting.remaining_ngh -= fill_qty
            incoming.status = (
                ExchangeOrderStatus.FILLED
                if incoming.remaining_ngh <= 0
                else ExchangeOrderStatus.PARTIALLY_FILLED
            )
            resting.status = (
                ExchangeOrderStatus.FILLED
                if resting.remaining_ngh <= 0
                else ExchangeOrderStatus.PARTIALLY_FILLED
            )

            buy_id = incoming.order_id if incoming.side == ExchangeOrderSide.BUY else resting.order_id
            sell_id = incoming.order_id if incoming.side == ExchangeOrderSide.SELL else resting.order_id
            trade = ExchangeTradeResponse(
                trade_id=str(uuid.uuid4()),
                product_key=incoming.product_key,
                buy_order_id=buy_id,
                sell_order_id=sell_id,
                price_per_ngh=trade_price,
                quantity_ngh=fill_qty,
                notional=fill_qty * trade_price,
                created_at=datetime.utcnow().isoformat() + "Z",
            )
            self._trades.append(trade)
            self._record_event(
                "exchange.trade_executed",
                "exchange_trade",
                trade.trade_id,
                {
                    "product_key": incoming.product_key.model_dump(mode="json"),
                    "price_per_ngh": trade_price,
                    "quantity_ngh": fill_qty,
                    "buy_order_id": buy_id,
                    "sell_order_id": sell_id,
                },
            )

        if incoming.remaining_ngh <= 0:
            incoming.status = ExchangeOrderStatus.FILLED
        elif incoming.status == ExchangeOrderStatus.OPEN and incoming.quantity_ngh != incoming.remaining_ngh:
            incoming.status = ExchangeOrderStatus.PARTIALLY_FILLED

    def _can_fully_fill_exchange_order(
        self,
        product_key: ProductKey,
        side: ExchangeOrderSide,
        price_per_ngh: float,
        quantity_ngh: float,
    ) -> bool:
        key = product_key.as_storage_key()
        opposite = ExchangeOrderSide.SELL if side == ExchangeOrderSide.BUY else ExchangeOrderSide.BUY
        candidates = [
            order
            for order in self._orders.values()
            if order.product_key.as_storage_key() == key
            and order.side == opposite
            and order.status in (ExchangeOrderStatus.OPEN, ExchangeOrderStatus.PARTIALLY_FILLED)
            and order.remaining_ngh > 0
        ]
        if side == ExchangeOrderSide.BUY:
            candidates = [c for c in candidates if c.price_per_ngh <= price_per_ngh]
            candidates.sort(key=lambda c: (c.price_per_ngh, c.created_at))
        else:
            candidates = [c for c in candidates if c.price_per_ngh >= price_per_ngh]
            candidates.sort(key=lambda c: (-c.price_per_ngh, c.created_at))
        available = sum(c.remaining_ngh for c in candidates)
        return available >= quantity_ngh

    # ---- nominations ----
    def create_nomination(self, request: NominationRequest) -> NominationResponse:
        """Create a new nomination."""
        return self.create_nomination_for_provider(request, provider_id=None)

    def create_nomination_for_provider(
        self, request: NominationRequest, provider_id: Optional[str]
    ) -> NominationResponse:
        """Create a new nomination with optional provider ownership."""
        self._assert_demo_isolation_for_synthetic(
            provider_id,
            ProductKey(
                region=request.region,
                iso_hour=request.iso_hour,
                sla=request.sla,
                tier=request.tier,
            ),
            entity="nomination",
        )
        nomination_id = str(uuid.uuid4())
        nomination = NominationResponse(
            nomination_id=nomination_id,
            region=request.region,
            iso_hour=request.iso_hour,
            tier=request.tier,
            sla=request.sla,
            ngh_available=request.ngh_available,
            gpu_model=request.gpu_model,
            gpu_count=request.gpu_count,
            provider_id=provider_id,
            created_at=datetime.utcnow().isoformat() + "Z",
        )
        self._nominations[nomination_id] = nomination
        self._record_event(
            "nomination.created",
            "nomination",
            nomination_id,
            {
                "product_key": ProductKey(
                    region=request.region,
                    iso_hour=request.iso_hour,
                    sla=request.sla,
                    tier=request.tier,
                ).model_dump(mode="json"),
                "ngh_available": request.ngh_available,
                "gpu_model": request.gpu_model,
                "gpu_count": request.gpu_count,
                "provider_id": provider_id,
            },
        )
        return nomination

    def list_nominations(self) -> List[NominationResponse]:
        rows = list(self._nominations.values())
        rows.sort(key=lambda row: row.created_at, reverse=True)
        return rows

    def list_marketplace_listings(self) -> List[MarketplaceGpuListingResponse]:
        rows: List[MarketplaceGpuListingResponse] = []
        for nomination in self._nominations.values():
            provider_id = nomination.provider_id or "unassigned-provider"
            base_price = {
                "RTX 3090": 1.2,
                "RTX 4090": 2.45,
                "A100": 4.8,
                "H100": 8.95,
            }.get(nomination.gpu_model, 2.45)
            multiplier = 1.0
            if nomination.sla.value == "premium":
                multiplier = 1.2
            elif nomination.sla.value == "urgent":
                multiplier = 1.35
            rows.append(
                MarketplaceGpuListingResponse(
                    listing_id=nomination.nomination_id,
                    provider_id=provider_id,
                    gpu_model=nomination.gpu_model,
                    gpu_count=nomination.gpu_count,
                    region=nomination.region,
                    iso_hour=nomination.iso_hour,
                    tier=nomination.tier,
                    sla=nomination.sla,
                    ngh_available=nomination.ngh_available,
                    indicative_price_per_ngh=base_price * multiplier,
                    created_at=nomination.created_at,
                )
            )
        rows.sort(key=lambda row: (row.indicative_price_per_ngh, -row.ngh_available))
        return rows

    def provider_capacity_for_window(
        self,
        provider_id: str,
        product_key: ProductKey,
    ) -> float:
        target = product_key.as_storage_key()
        return sum(
            nomination.ngh_available
            for nomination in self._nominations.values()
            if (nomination.provider_id or "") == provider_id
            and ProductKey(
                region=nomination.region,
                iso_hour=nomination.iso_hour,
                sla=nomination.sla,
                tier=nomination.tier,
            ).as_storage_key()
            == target
        )

    def get_nomination(self, nomination_id: str) -> Optional[NominationResponse]:
        """Get a nomination by ID."""
        return self._nominations.get(nomination_id)

    # ---- options ----
    def list_option_contracts(
        self,
        *,
        product_key: Optional[ProductKey] = None,
        owner_id: Optional[str] = None,
    ) -> List[OptionContractResponse]:
        contracts = list(self._option_contracts.values())
        if product_key is not None:
            key = product_key.as_storage_key()
            contracts = [c for c in contracts if c.product_key.as_storage_key() == key]
        if owner_id is not None:
            contracts = [c for c in contracts if c.owner_id == owner_id]
        contracts.sort(key=lambda c: c.created_at, reverse=True)
        return contracts

    def create_option_contract(
        self, request: OptionContractCreateRequest, owner_id: Optional[str] = None
    ) -> OptionContractResponse:
        self._assert_trading_enabled(owner_id)
        contract_id = str(uuid.uuid4())
        quote = quote_option(
            OptionQuoteRequest(
                option_type=request.option_type,
                forward_price_per_ngh=request.forward_price_per_ngh,
                strike_price_per_ngh=request.strike_price_per_ngh,
                time_to_expiry_years=request.time_to_expiry_years,
                implied_volatility=request.implied_volatility,
                risk_free_rate=request.risk_free_rate,
                quantity_ngh=request.quantity_ngh,
            )
        )
        underlying_notional = request.forward_price_per_ngh * request.quantity_ngh
        initial_margin = 0.2 * quote.premium_notional + 0.1 * underlying_notional
        self._assert_risk_limits(
            owner_id,
            increment_notional=underlying_notional,
            increment_margin=initial_margin,
        )
        contract = OptionContractResponse(
            contract_id=contract_id,
            product_key=request.product_key,
            side=request.side,
            option_type=request.option_type,
            forward_price_per_ngh=request.forward_price_per_ngh,
            strike_price_per_ngh=request.strike_price_per_ngh,
            time_to_expiry_years=request.time_to_expiry_years,
            implied_volatility=request.implied_volatility,
            risk_free_rate=request.risk_free_rate,
            quantity_ngh=request.quantity_ngh,
            status=OptionContractStatus.OPEN,
            premium_per_ngh=quote.premium_per_ngh,
            premium_notional=quote.premium_notional,
            created_at=datetime.utcnow().isoformat() + "Z",
            owner_id=owner_id,
        )
        self._option_contracts[contract_id] = contract
        self._record_event(
            "options.contract_created",
            "option_contract",
            contract_id,
            {
                "product_key": request.product_key.model_dump(mode="json"),
                "side": request.side.value,
                "option_type": request.option_type.value,
                "quantity_ngh": request.quantity_ngh,
                "premium_per_ngh": quote.premium_per_ngh,
                "owner_id": owner_id,
            },
        )
        self._persist_state()
        return contract

    def list_option_orders(
        self, *, contract_id: Optional[str] = None, owner_id: Optional[str] = None
    ) -> List[OptionOrderResponse]:
        orders = list(self._option_orders.values())
        if contract_id is not None:
            orders = [o for o in orders if o.contract_id == contract_id]
        if owner_id is not None:
            owner_key = self._owner_key(owner_id)
            orders = [o for o in orders if self._owner_key(o.owner_id) == owner_key]
        orders.sort(key=lambda o: o.created_at, reverse=True)
        return orders

    def list_option_trades(
        self, *, contract_id: Optional[str] = None, limit: int = 30
    ) -> List[OptionTradeResponse]:
        trades = list(reversed(self._option_trades))
        if contract_id is not None:
            trades = [t for t in trades if t.contract_id == contract_id]
        return trades[:limit]

    def create_option_order(
        self, request: OptionOrderCreateRequest, owner_id: Optional[str] = None
    ) -> OptionOrderResponse:
        self._assert_trading_enabled(owner_id, request.strategy_tag, request.subaccount_id)
        contract = self._option_contracts.get(request.contract_id)
        if contract is None:
            raise ValueError("option_contract_not_found")
        if request.time_in_force == TimeInForce.FOK and not self._can_fully_fill_option_order(
            request.contract_id,
            request.side,
            request.limit_price_per_ngh,
            request.quantity_ngh,
        ):
            raise ValueError("option_fok_not_fillable")

        notional = request.limit_price_per_ngh * request.quantity_ngh
        self._assert_risk_limits(
            owner_id,
            increment_notional=notional,
            increment_margin=0.25 * notional,
            strategy_tag=request.strategy_tag,
            subaccount_id=request.subaccount_id,
        )

        order_id = str(uuid.uuid4())
        order = OptionOrderResponse(
            order_id=order_id,
            contract_id=request.contract_id,
            product_key=contract.product_key,
            side=request.side,
            limit_price_per_ngh=request.limit_price_per_ngh,
            quantity_ngh=request.quantity_ngh,
            remaining_ngh=request.quantity_ngh,
            time_in_force=request.time_in_force,
            status=OptionOrderStatus.OPEN,
            created_at=datetime.utcnow().isoformat() + "Z",
            owner_id=owner_id,
            subaccount_id=request.subaccount_id,
            strategy_tag=request.strategy_tag,
        )
        self._option_orders[order_id] = order
        self._record_event(
            "options.order_created",
            "option_order",
            order_id,
            {
                "contract_id": request.contract_id,
                "side": request.side.value,
                "limit_price_per_ngh": request.limit_price_per_ngh,
                "quantity_ngh": request.quantity_ngh,
                "time_in_force": request.time_in_force.value,
                "owner_id": owner_id,
                "subaccount_id": request.subaccount_id,
                "strategy_tag": request.strategy_tag,
            },
        )
        self._match_option_order(order)
        if order.remaining_ngh > 0 and order.time_in_force == TimeInForce.IOC:
            order.status = OptionOrderStatus.CANCELLED
            order.remaining_ngh = 0.0
            self._record_event(
                "options.order_ioc_expired",
                "option_order",
                order_id,
                {"owner_id": owner_id},
            )
        self._persist_state()
        return self._option_orders[order_id]

    def amend_option_order(
        self,
        order_id: str,
        request: OptionOrderAmendRequest,
        owner_id: Optional[str] = None,
    ) -> Optional[OptionOrderResponse]:
        order = self._option_orders.get(order_id)
        if order is None:
            return None
        self._assert_trading_enabled(owner_id, order.strategy_tag, order.subaccount_id)
        if owner_id is not None and self._owner_key(order.owner_id) != self._owner_key(owner_id):
            raise ValueError("option_order_owner_mismatch")
        if order.status in (OptionOrderStatus.FILLED, OptionOrderStatus.CANCELLED):
            raise ValueError("option_order_not_amendable")

        filled_qty = order.quantity_ngh - order.remaining_ngh
        next_qty = request.quantity_ngh if request.quantity_ngh is not None else order.quantity_ngh
        next_price = (
            request.limit_price_per_ngh
            if request.limit_price_per_ngh is not None
            else order.limit_price_per_ngh
        )
        if next_qty < filled_qty:
            raise ValueError("option_order_quantity_below_filled")

        order.quantity_ngh = next_qty
        order.limit_price_per_ngh = next_price
        order.remaining_ngh = max(0.0, next_qty - filled_qty)
        self._assert_risk_limits(
            owner_id,
            increment_notional=0.0,
            increment_margin=0.0,
            order_notional=next_price * max(order.remaining_ngh, 0.0),
            strategy_tag=order.strategy_tag,
            subaccount_id=order.subaccount_id,
        )
        order.status = (
            OptionOrderStatus.FILLED
            if order.remaining_ngh <= 0
            else (OptionOrderStatus.PARTIALLY_FILLED if filled_qty > 0 else OptionOrderStatus.OPEN)
        )

        self._record_event(
            "options.order_amended",
            "option_order",
            order_id,
            {
                "owner_id": owner_id,
                "limit_price_per_ngh": order.limit_price_per_ngh,
                "quantity_ngh": order.quantity_ngh,
                "remaining_ngh": order.remaining_ngh,
            },
        )
        if order.remaining_ngh > 0:
            self._match_option_order(order)
        if order.remaining_ngh > 0 and order.time_in_force == TimeInForce.IOC:
            order.status = OptionOrderStatus.CANCELLED
            order.remaining_ngh = 0.0
        self._persist_state()
        return order

    def cancel_option_order(
        self, order_id: str, owner_id: Optional[str] = None
    ) -> Optional[OptionOrderResponse]:
        order = self._option_orders.get(order_id)
        if order is None:
            return None
        if owner_id is not None and self._owner_key(order.owner_id) != self._owner_key(owner_id):
            raise ValueError("option_order_owner_mismatch")
        if order.status in (OptionOrderStatus.FILLED, OptionOrderStatus.CANCELLED):
            return order
        order.status = OptionOrderStatus.CANCELLED
        order.remaining_ngh = 0.0
        self._record_event(
            "options.order_cancelled",
            "option_order",
            order_id,
            {"owner_id": owner_id},
        )
        self._persist_state()
        return order

    def get_option_orderbook(self, contract_id: str) -> OptionOrderBookResponse:
        contract = self._option_contracts.get(contract_id)
        if contract is None:
            raise ValueError("option_contract_not_found")
        active = [
            order
            for order in self._option_orders.values()
            if order.contract_id == contract_id
            and order.status in (OptionOrderStatus.OPEN, OptionOrderStatus.PARTIALLY_FILLED)
            and order.remaining_ngh > 0
        ]
        bids: Dict[float, float] = {}
        asks: Dict[float, float] = {}
        for order in active:
            book = bids if order.side == OptionOrderSide.BUY else asks
            book[order.limit_price_per_ngh] = (
                book.get(order.limit_price_per_ngh, 0.0) + order.remaining_ngh
            )
        bid_levels = [
            OptionOrderBookLevel(price_per_ngh=price, quantity_ngh=qty)
            for price, qty in sorted(bids.items(), key=lambda item: item[0], reverse=True)
        ]
        ask_levels = [
            OptionOrderBookLevel(price_per_ngh=price, quantity_ngh=qty)
            for price, qty in sorted(asks.items(), key=lambda item: item[0])
        ]
        best_bid = bid_levels[0].price_per_ngh if bid_levels else None
        best_ask = ask_levels[0].price_per_ngh if ask_levels else None
        spread = (best_ask - best_bid) if (best_bid is not None and best_ask is not None) else None
        return OptionOrderBookResponse(
            contract_id=contract_id,
            product_key=contract.product_key,
            bids=bid_levels[:10],
            asks=ask_levels[:10],
            spread=spread,
            best_bid=best_bid,
            best_ask=best_ask,
        )

    def _match_option_order(self, incoming: OptionOrderResponse) -> None:
        if incoming.remaining_ngh <= 0:
            return
        opposite_side = (
            OptionOrderSide.SELL if incoming.side == OptionOrderSide.BUY else OptionOrderSide.BUY
        )
        candidates = [
            order
            for order in self._option_orders.values()
            if order.order_id != incoming.order_id
            and order.contract_id == incoming.contract_id
            and order.side == opposite_side
            and order.status in (OptionOrderStatus.OPEN, OptionOrderStatus.PARTIALLY_FILLED)
            and order.remaining_ngh > 0
        ]
        if incoming.side == OptionOrderSide.BUY:
            candidates = [c for c in candidates if c.limit_price_per_ngh <= incoming.limit_price_per_ngh]
            candidates.sort(key=lambda c: (c.limit_price_per_ngh, c.created_at))
        else:
            candidates = [c for c in candidates if c.limit_price_per_ngh >= incoming.limit_price_per_ngh]
            candidates.sort(key=lambda c: (-c.limit_price_per_ngh, c.created_at))

        for resting in candidates:
            if incoming.remaining_ngh <= 0:
                break
            fill_qty = min(incoming.remaining_ngh, resting.remaining_ngh)
            if fill_qty <= 0:
                continue
            trade_price = resting.limit_price_per_ngh
            incoming.remaining_ngh -= fill_qty
            resting.remaining_ngh -= fill_qty
            incoming.status = (
                OptionOrderStatus.FILLED
                if incoming.remaining_ngh <= 0
                else OptionOrderStatus.PARTIALLY_FILLED
            )
            resting.status = (
                OptionOrderStatus.FILLED
                if resting.remaining_ngh <= 0
                else OptionOrderStatus.PARTIALLY_FILLED
            )
            buy_id = incoming.order_id if incoming.side == OptionOrderSide.BUY else resting.order_id
            sell_id = incoming.order_id if incoming.side == OptionOrderSide.SELL else resting.order_id
            contract = self._option_contracts[incoming.contract_id]
            trade = OptionTradeResponse(
                trade_id=str(uuid.uuid4()),
                contract_id=incoming.contract_id,
                product_key=contract.product_key,
                buy_order_id=buy_id,
                sell_order_id=sell_id,
                price_per_ngh=trade_price,
                quantity_ngh=fill_qty,
                notional=trade_price * fill_qty,
                created_at=datetime.utcnow().isoformat() + "Z",
            )
            self._option_trades.append(trade)
            self._record_event(
                "options.trade_executed",
                "option_trade",
                trade.trade_id,
                {
                    "contract_id": incoming.contract_id,
                    "price_per_ngh": trade_price,
                    "quantity_ngh": fill_qty,
                    "buy_order_id": buy_id,
                    "sell_order_id": sell_id,
                },
            )

        if incoming.remaining_ngh <= 0:
            incoming.status = OptionOrderStatus.FILLED
        elif incoming.status == OptionOrderStatus.OPEN and incoming.quantity_ngh != incoming.remaining_ngh:
            incoming.status = OptionOrderStatus.PARTIALLY_FILLED

    def _can_fully_fill_option_order(
        self,
        contract_id: str,
        side: OptionOrderSide,
        limit_price_per_ngh: float,
        quantity_ngh: float,
    ) -> bool:
        opposite = OptionOrderSide.SELL if side == OptionOrderSide.BUY else OptionOrderSide.BUY
        candidates = [
            order
            for order in self._option_orders.values()
            if order.contract_id == contract_id
            and order.side == opposite
            and order.status in (OptionOrderStatus.OPEN, OptionOrderStatus.PARTIALLY_FILLED)
            and order.remaining_ngh > 0
        ]
        if side == OptionOrderSide.BUY:
            candidates = [c for c in candidates if c.limit_price_per_ngh <= limit_price_per_ngh]
            candidates.sort(key=lambda c: (c.limit_price_per_ngh, c.created_at))
        else:
            candidates = [c for c in candidates if c.limit_price_per_ngh >= limit_price_per_ngh]
            candidates.sort(key=lambda c: (-c.limit_price_per_ngh, c.created_at))
        available = sum(c.remaining_ngh for c in candidates)
        return available >= quantity_ngh

    # ---- lots ----
    def create_lot(
        self,
        window: Window,
        job_id: Optional[str] = None,
        provider_id: Optional[str] = None,
    ) -> Lot:
        """Create a new lot."""
        lot_id = str(uuid.uuid4())
        lot = Lot(
            lot_id=lot_id,
            status=LotStatus.PENDING,
            job_id=job_id,
            window=window,
            created_at=datetime.utcnow().isoformat() + "Z",
            prepared_at=None,
            completed_at=None,
            output_root=None,
            item_count=None,
            wall_time_seconds=None,
            raw_gpu_time_seconds=None,
            logs_uri=None,
            provider_id=provider_id,
        )
        self._lots[lot_id] = lot
        self._record_event(
            "lot.created",
            "lot",
            lot_id,
            {
                "job_id": job_id,
                "provider_id": provider_id,
                "product_key": ProductKey.from_window(window).model_dump(mode="json"),
            },
        )
        return lot

    def get_lot(self, lot_id: str) -> Optional[Lot]:
        """Get a lot by ID."""
        return self._lots.get(lot_id)

    def list_lots(self, provider_id: Optional[str] = None) -> List[Lot]:
        """List lots, newest first. If provider_id is set, only return that provider's lots."""
        lots = list(self._lots.values())
        if provider_id is not None:
            lots = [l for l in lots if getattr(l, "provider_id", None) == provider_id]
        lots.sort(key=lambda l: l.created_at or "", reverse=True)
        return lots

    def update_lot_prepare_ready(self, lot_id: str) -> Optional[Lot]:
        """Update lot status to ready after preparation."""
        lot = self._lots.get(lot_id)
        if lot:
            lot.status = LotStatus.READY
            lot.prepared_at = datetime.utcnow().isoformat() + "Z"
            self._record_event(
                "lot.ready",
                "lot",
                lot_id,
                {
                    "job_id": lot.job_id,
                    "provider_id": lot.provider_id,
                    "prepared_at": lot.prepared_at,
                },
            )
        return lot

    def _product_key_from_storage_key(self, key: str) -> ProductKey:
        region, iso_hour, sla, tier = key.split(":")
        return ProductKey(
            region=region,  # type: ignore[arg-type]
            iso_hour=int(iso_hour),
            sla=sla,  # type: ignore[arg-type]
            tier=tier,  # type: ignore[arg-type]
        )

    def update_lot_result(self, lot_id: str, result_data: dict) -> Optional[Lot]:
        """Update lot with result data."""
        lot = self._lots.get(lot_id)
        if lot:
            lot.status = LotStatus.COMPLETED
            lot.completed_at = datetime.utcnow().isoformat() + "Z"
            lot.output_root = result_data.get("output_root")
            lot.item_count = result_data.get("item_count")
            lot.wall_time_seconds = result_data.get("wall_time_seconds")
            lot.raw_gpu_time_seconds = result_data.get("raw_gpu_time_seconds")
            lot.logs_uri = result_data.get("logs_uri")
            self._record_event(
                "lot.completed",
                "lot",
                lot_id,
                {
                    "job_id": lot.job_id,
                    "provider_id": lot.provider_id,
                    "output_root": lot.output_root,
                    "item_count": lot.item_count,
                    "wall_time_seconds": lot.wall_time_seconds,
                    "raw_gpu_time_seconds": lot.raw_gpu_time_seconds,
                },
            )
        return lot


def _make_locked_storage_method(meth):
    """Bind one method to a per-instance RLock (must not be defined inside a for-loop)."""

    @functools.wraps(meth)
    def wrapper(self, *args, **kwargs):
        with self._lock:
            return meth(self, *args, **kwargs)

    return wrapper


def _synchronize_job_storage(cls: type) -> type:
    """Serialize all JobStorage methods so background market sim cannot race demo/HTTP."""
    skip = frozenset({
        "__init__",
        "_load_state",
        # These manage their own locking; wrapping would hold _lock across disk I/O.
        "_timer_flush_persist",
        "flush_persist_blocking",
    })
    for name, attr in list(cls.__dict__.items()):
        if name in skip:
            continue
        if not callable(attr):
            continue
        setattr(cls, name, _make_locked_storage_method(attr))
    return cls


JobStorage = _synchronize_job_storage(JobStorage)

# Global storage instance (kept for parity with previous layout)
storage = JobStorage()

