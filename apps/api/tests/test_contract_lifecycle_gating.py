from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

API_ROOT = Path(__file__).resolve().parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.api.v1.endpoints.market import (  # noqa: E402
    _build_execution_preflight,
    deliver_position_to_compute,
    settle_position,
)
from app.repositories.memory.storage import storage  # noqa: E402
from app.services.position_contract import seconds_until_contract_close  # noqa: E402
from app.schemas.models import (  # noqa: E402
    ComputeDeliveryRequest,
    JobCreateRequest,
    MarketPositionCreateRequest,
    PackageDescriptor,
    PositionSide,
    ProductKey,
    Region,
    SLA,
    Tier,
    Window,
)


def _pk() -> ProductKey:
    return ProductKey(region=Region.US_EAST, iso_hour=3, sla=SLA.STANDARD, tier=Tier.STANDARD)


def _window() -> Window:
    return Window(region=Region.US_EAST, iso_hour=3, sla=SLA.STANDARD, tier=Tier.STANDARD)


class TestContractLifecycleGating(unittest.TestCase):
    def setUp(self) -> None:
        # Isolate test state from persisted workspace snapshots.
        storage._jobs.clear()
        storage._vouchers.clear()
        storage._voucher_deposits.clear()
        storage._positions.clear()
        storage._nominations.clear()

    def _seed_job(self, job_id: str) -> None:
        storage.create_job(
            JobCreateRequest(
                job_id=job_id,
                window=_window(),
                package_index=[
                    PackageDescriptor(
                        package_id="pkg-a",
                        size_estimate_ngh=10,
                        first_output_estimate_seconds=60,
                        metadata={},
                    )
                ],
            ),
            created_by=None,
        )

    def _seed_listing(self) -> None:
        from app.schemas.models import NominationRequest

        storage.create_nomination_for_provider(
            NominationRequest(
                region=Region.US_EAST,
                iso_hour=3,
                sla=SLA.STANDARD,
                tier=Tier.STANDARD,
                ngh_available=1000,
                gpu_model="RTX 4090",
                gpu_count=4,
            ),
            provider_id="provider-lifecycle-test",
        )

    def test_settle_blocked_before_close(self) -> None:
        p = storage.create_market_position(
            MarketPositionCreateRequest(
                product_key=_pk(),
                side=PositionSide.BUY,
                quantity_ngh=10,
                price_per_ngh=2.0,
                close_in_seconds=3600,
            ),
            owner_id=None,
        )
        with self.assertRaises(HTTPException) as ctx:
            settle_position(p.position_id)
        self.assertEqual(ctx.exception.status_code, 409)
        self.assertIn("contract_not_closed_yet", str(ctx.exception.detail))

    def test_position_respects_requested_close_horizon(self) -> None:
        p = storage.create_market_position(
            MarketPositionCreateRequest(
                product_key=_pk(),
                side=PositionSide.BUY,
                quantity_ngh=10,
                price_per_ngh=2.0,
                close_in_seconds=7200,
            ),
            owner_id=None,
        )
        self.assertEqual(p.close_in_seconds, 7200)
        self.assertIsNotNone(p.closes_at)
        self.assertIsNotNone(p.seconds_until_close)
        self.assertGreater(p.seconds_until_close or 0, 7000)
        sec = seconds_until_contract_close(p)
        self.assertGreater(sec, 7050, sec)
        self.assertLess(sec, 7250, sec)
        stripped = p.model_copy(update={"closes_at": None})
        sec2 = seconds_until_contract_close(stripped)
        self.assertGreater(sec2, 7050, sec2)
        self.assertLess(sec2, 7250, sec2)

    def test_create_request_coerces_float_close_in_seconds(self) -> None:
        raw = {
            "product_key": {
                "region": "us-east",
                "iso_hour": 3,
                "sla": "standard",
                "tier": "standard",
            },
            "side": "buy",
            "quantity_ngh": 10.0,
            "price_per_ngh": 2.0,
            "close_in_seconds": 5400.7,
        }
        req = MarketPositionCreateRequest.model_validate(raw)
        self.assertEqual(req.close_in_seconds, 5400)

    def test_legacy_missing_closes_at_still_blocks_settle(self) -> None:
        """Rows without closes_at must use created_at + legacy window, not 'already closed'."""
        p = storage.create_market_position(
            MarketPositionCreateRequest(
                product_key=_pk(),
                side=PositionSide.BUY,
                quantity_ngh=10,
                price_per_ngh=2.0,
                close_in_seconds=3600,
            ),
            owner_id=None,
        )
        storage._positions[p.position_id] = p.model_copy(update={"closes_at": None})
        with self.assertRaises(HTTPException) as ctx:
            settle_position(p.position_id)
        self.assertEqual(ctx.exception.status_code, 409)
        self.assertIn("contract_not_closed_yet", str(ctx.exception.detail))
        with self.assertRaises(ValueError) as ve:
            storage.settle_market_position(p.position_id)
        self.assertIn("contract_not_closed_yet", str(ve.exception))

    def test_preflight_reports_contract_not_closed(self) -> None:
        self._seed_job("job-preflight-open")
        p = storage.create_market_position(
            MarketPositionCreateRequest(
                product_key=_pk(),
                side=PositionSide.BUY,
                quantity_ngh=10,
                price_per_ngh=2.0,
                close_in_seconds=120,
            ),
            owner_id=None,
        )
        report = _build_execution_preflight(
            position_id=p.position_id,
            job_id="job-preflight-open",
            owner_id=None,
        )
        self.assertFalse(report.ready_to_execute)
        self.assertFalse(report.contract_closed)
        self.assertGreater(report.seconds_until_close, 0)
        self.assertTrue(any(r.startswith("contract_not_closed_yet:") for r in report.reasons))

    @patch(
        "app.api.v1.endpoints.market._run_remote_factoring",
        return_value={"method": "test_stub", "final_prime_factors": [11, 13]},
    )
    def test_closed_position_can_settle_preflight_and_deliver(self, _mock_factor) -> None:
        self._seed_job("job-closed-flow")
        self._seed_listing()
        p = storage.create_market_position(
            MarketPositionCreateRequest(
                product_key=_pk(),
                side=PositionSide.BUY,
                quantity_ngh=20,
                price_per_ngh=2.0,
                close_in_seconds=0,
            ),
            owner_id=None,
        )
        settled = settle_position(p.position_id)
        self.assertEqual(settled.status.value, "settled")
        key = _pk().as_storage_key()
        storage.deposit_vouchers(job_id="job-closed-flow", product_key=_pk(), amount_ngh=10)
        report = _build_execution_preflight(
            position_id=p.position_id,
            job_id="job-closed-flow",
            owner_id=None,
        )
        self.assertTrue(report.contract_closed)
        self.assertEqual(report.seconds_until_close, 0)
        self.assertTrue(report.ready_to_execute, report.reasons)
        out = deliver_position_to_compute(
            p.position_id,
            ComputeDeliveryRequest(
                job_id="job-closed-flow",
                gpu_count=1,
                composite="143",
                deposit_ngh=10,
            ),
            user=None,
        )
        self.assertEqual(out.delivery_status, "completed")
        self.assertGreaterEqual(out.delivered_ngh, 10)
        self.assertGreaterEqual(storage.get_voucher_balance(key), 0.0)

    def test_stress_many_positions_preflight_settle(self) -> None:
        self._seed_job("job-stress")
        positions = []
        for i in range(120):
            positions.append(
                storage.create_market_position(
                    MarketPositionCreateRequest(
                        product_key=_pk(),
                        side=PositionSide.BUY,
                        quantity_ngh=5 + (i % 5),
                        price_per_ngh=1.0 + (i % 3),
                        close_in_seconds=0 if i % 2 == 0 else 90,
                    ),
                    owner_id=None,
                )
            )
        blocked = 0
        closed = 0
        for p in positions:
            pre = _build_execution_preflight(position_id=p.position_id, job_id="job-stress", owner_id=None)
            if pre.contract_closed:
                closed += 1
            else:
                blocked += 1
            if pre.contract_closed:
                settle_position(p.position_id)
            else:
                with self.assertRaises(HTTPException):
                    settle_position(p.position_id)
        self.assertGreater(blocked, 0)
        self.assertGreater(closed, 0)


if __name__ == "__main__":
    unittest.main()

