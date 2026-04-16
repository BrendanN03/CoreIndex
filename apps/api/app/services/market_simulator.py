from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import logging
import random
import threading
import time
from typing import Dict, List

from app.repositories.memory.storage import storage
from app.schemas.models import (
    ExchangeOrderCreateRequest,
    ExchangeOrderSide,
    MarketSimulationStartRequest,
    MarketSimulationStatusResponse,
    NominationRequest,
    ProductKey,
    Region,
    SLA,
    Tier,
    TimeInForce,
)


@dataclass(frozen=True)
class _GpuTemplate:
    gpu_model: str
    base_price: float
    region: Region
    sla: SLA
    tier: Tier

    def product_key(self) -> ProductKey:
        return ProductKey(
            region=self.region,
            iso_hour=datetime.utcnow().hour,
            sla=self.sla,
            tier=self.tier,
        )


class MarketSimulatorEngine:
    def __init__(self):
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._rng = random.Random()
        self._templates: List[_GpuTemplate] = [
            _GpuTemplate("RTX 3090", 1.2, Region.US_WEST, SLA.STANDARD, Tier.BASIC),
            _GpuTemplate("RTX 4090", 2.45, Region.EU_CENTRAL, SLA.STANDARD, Tier.STANDARD),
            _GpuTemplate("A100", 4.8, Region.ASIA_PACIFIC, SLA.PREMIUM, Tier.PREMIUM),
            _GpuTemplate("H100", 8.95, Region.US_EAST, SLA.URGENT, Tier.ENTERPRISE),
        ]
        self._price_anchors: Dict[str, float] = {
            template.gpu_model: template.base_price for template in self._templates
        }
        self._buyers: List[str] = []
        self._sellers: List[str] = []
        self._ticks_per_second = 2.0
        self._started_at: str | None = None
        self._tick_count = 0
        self._synthetic_order_count = 0

    def start(self, request: MarketSimulationStartRequest) -> MarketSimulationStatusResponse:
        """
        Start the tick loop, or no-op if it is already running.

        If a previous stop() left the tick thread alive briefly, wait for it to exit before
        clearing _stop_event; otherwise start() would return early while the event stays set
        and the sim never runs again.
        """
        with self._lock:
            if self._thread and self._thread.is_alive() and not self._stop_event.is_set():
                # Already running: return status without re-entering the same non-reentrant lock.
                return MarketSimulationStatusResponse(
                    running=True,
                    synthetic_buyer_agents=len(self._buyers),
                    synthetic_seller_agents=len(self._sellers),
                    ticks_per_second=self._ticks_per_second,
                    started_at=self._started_at,
                    total_ticks=self._tick_count,
                    total_synthetic_orders=self._synthetic_order_count,
                )
            thread_to_join = self._thread if (self._thread and self._thread.is_alive()) else None
        if thread_to_join is not None:
            self._stop_event.set()
            thread_to_join.join(timeout=12.0)
        with self._lock:
            if self._thread and self._thread.is_alive():
                logging.getLogger("uvicorn.error").warning(
                    "market_simulator: tick thread still alive after join; refusing to start a second loop"
                )
                return MarketSimulationStatusResponse(
                    running=True,
                    synthetic_buyer_agents=len(self._buyers),
                    synthetic_seller_agents=len(self._sellers),
                    ticks_per_second=self._ticks_per_second,
                    started_at=self._started_at,
                    total_ticks=self._tick_count,
                    total_synthetic_orders=self._synthetic_order_count,
                )
            self._stop_event.clear()
            self._buyers = [f"sim-buyer-{idx:03d}" for idx in range(request.synthetic_buyer_agents)]
            self._sellers = [f"sim-seller-{idx:03d}" for idx in range(request.synthetic_seller_agents)]
            self._ticks_per_second = request.ticks_per_second
            self._started_at = datetime.utcnow().isoformat() + "Z"
            self._thread = threading.Thread(target=self._run_loop, daemon=True, name="market-simulator")
            self._thread.start()
        return self.status()

    def stop(self) -> MarketSimulationStatusResponse:
        self._stop_event.set()
        thread = self._thread
        if thread and thread.is_alive():
            thread.join(timeout=5.0)
        return self.status()

    def status(self) -> MarketSimulationStatusResponse:
        with self._lock:
            running = bool(self._thread and self._thread.is_alive() and not self._stop_event.is_set())
            return MarketSimulationStatusResponse(
                running=running,
                synthetic_buyer_agents=len(self._buyers),
                synthetic_seller_agents=len(self._sellers),
                ticks_per_second=self._ticks_per_second,
                started_at=self._started_at,
                total_ticks=self._tick_count,
                total_synthetic_orders=self._synthetic_order_count,
            )

    def product_catalog(self) -> List[tuple[str, ProductKey]]:
        rows: List[tuple[str, ProductKey]] = []
        for template in self._templates:
            rows.append((template.gpu_model, template.product_key()))
        return rows

    def voucher_topup_storage_keys(self) -> List[str]:
        """All region/SLA/tier combos from GPU templates × ISO hours 0–23 (for demo wallet seeding)."""
        keys: List[str] = []
        for template in self._templates:
            for hour in range(24):
                pk = ProductKey(
                    region=template.region,
                    iso_hour=hour,
                    sla=template.sla,
                    tier=template.tier,
                )
                keys.append(pk.as_storage_key())
        return keys

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            started = time.time()
            try:
                self._tick()
            except Exception:
                # Keep simulation alive for demo purposes even if one tick fails.
                pass
            interval = max(0.05, 1.0 / max(self._ticks_per_second, 0.2))
            elapsed = time.time() - started
            if elapsed < interval:
                time.sleep(interval - elapsed)

    def _tick(self) -> None:
        with self._lock:
            self._tick_count += 1
            buyers = list(self._buyers)
            sellers = list(self._sellers)

        if not buyers or not sellers:
            return

        demo_key = storage.get_demo_product_key().as_storage_key()
        for template in self._templates:
            key = template.product_key()
            if key.as_storage_key() == demo_key:
                continue

            # Random walk anchor
            drift = (self._rng.random() - 0.5) * 0.08 * template.base_price
            anchor = max(0.05, self._price_anchors.get(template.gpu_model, template.base_price) + drift)
            self._price_anchors[template.gpu_model] = anchor

            if self._tick_count % 12 == 0:
                provider_id = self._rng.choice(sellers)
                ngh_available = round(self._rng.uniform(15.0, 120.0), 2)
                gpu_count = self._rng.randint(1, 8)
                try:
                    storage.create_nomination_for_provider(
                        NominationRequest(
                            region=key.region,
                            iso_hour=key.iso_hour,
                            tier=key.tier,
                            sla=key.sla,
                            ngh_available=ngh_available,
                            gpu_model=template.gpu_model,
                            gpu_count=gpu_count,
                        ),
                        provider_id=provider_id,
                    )
                except ValueError:
                    pass

            for _ in range(self._rng.randint(2, 6)):
                side = ExchangeOrderSide.BUY if self._rng.random() < 0.5 else ExchangeOrderSide.SELL
                owner_id = self._rng.choice(buyers if side == ExchangeOrderSide.BUY else sellers)
                spread = 0.01 + self._rng.random() * 0.08
                signed_spread = -spread if side == ExchangeOrderSide.BUY else spread
                price = round(max(0.05, anchor * (1 + signed_spread)), 2)
                quantity = round(self._rng.uniform(0.5, 8.0), 2)
                tif = TimeInForce.GTC if self._rng.random() < 0.88 else TimeInForce.IOC
                try:
                    storage.create_exchange_order(
                        ExchangeOrderCreateRequest(
                            product_key=key,
                            side=side,
                            price_per_ngh=price,
                            quantity_ngh=quantity,
                            time_in_force=tif,
                            subaccount_id="sim-main",
                            strategy_tag="sim-flow",
                        ),
                        owner_id=owner_id,
                    )
                    with self._lock:
                        self._synthetic_order_count += 1
                except ValueError:
                    continue


market_simulator = MarketSimulatorEngine()
