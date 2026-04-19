"""Unit tests for judge chain ledger grouping (delivery blocks + related voucher/settlement ops)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Optional

API_ROOT = Path(__file__).resolve().parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.schemas.models import PlatformEvent
from app.services.judge_chain_ledger import build_judge_chain_ledger


class TestJudgeChainLedger(unittest.TestCase):
    def test_one_delivery_with_voucher_and_settlement(self) -> None:
        events = [
            PlatformEvent(
                event_id="e1",
                event_type="voucher.deposited",
                created_at="2026-01-01T10:00:00Z",
                entity_type="job",
                entity_id="job-a",
                payload={
                    "product_key": {"region": "us", "iso_hour": 1, "sla": "std", "tier": "basic"},
                    "amount_ngh": 10.0,
                    "remaining_balance_ngh": 90.0,
                },
            ),
            PlatformEvent(
                event_id="e2",
                event_type="voucher.consumed",
                created_at="2026-01-01T10:01:00Z",
                entity_type="job",
                entity_id="job-a",
                payload={
                    "product_key": {"region": "us", "iso_hour": 1, "sla": "std", "tier": "basic"},
                    "amount_ngh": 4.0,
                    "remaining_deposited_ngh": 6.0,
                },
            ),
            PlatformEvent(
                event_id="e3",
                event_type="settlement.anchored",
                created_at="2026-01-01T10:02:00Z",
                entity_type="settlement",
                entity_id="set-1",
                payload={"job_id": "job-a", "receipt_root": "r1", "qc_root": "q1"},
            ),
            PlatformEvent(
                event_id="e4",
                event_type="delivery.compute_run_completed",
                created_at="2026-01-01T10:03:00Z",
                entity_type="position",
                entity_id="pos-1",
                payload={
                    "job_id": "job-a",
                    "delivered_ngh": 4.0,
                    "verification_hash": "vh123",
                    "verification_passed": True,
                    "blockchain_anchor": {"tx_hash": "0xabc", "chain_id": 31337},
                    "mode": "demo_run",
                },
            ),
        ]

        def job_by_settlement(sid: str) -> Optional[str]:
            return {"set-1": "job-a"}.get(sid)

        out = build_judge_chain_ledger(events, job_by_settlement=job_by_settlement, event_window=4)
        self.assertEqual(len(out.blocks), 1)
        b = out.blocks[0]
        self.assertEqual(b.job_id, "job-a")
        self.assertEqual(b.position_id, "pos-1")
        self.assertEqual(len(b.related_ops), 3)
        self.assertEqual(b.related_ops[0].op_kind, "erc1155_escrow_lock")
        self.assertEqual(b.related_ops[1].op_kind, "erc1155_escrow_burn")
        self.assertEqual(b.related_ops[2].op_kind, "settlement_merkle_ready")
        self.assertEqual(b.delivery_op.op_kind, "delivery_commit")
        self.assertEqual(b.verification_hash, "vh123")
        self.assertEqual(b.blockchain_anchor, {"tx_hash": "0xabc", "chain_id": 31337})
        self.assertTrue(b.block_hash.startswith("0x"))
        self.assertIsNone(b.prev_block_hash)
        self.assertEqual(out.chain_length, 1)
        self.assertEqual(out.chain_head_hash, b.block_hash)

    def test_anchor_recorded_resolves_job_via_lookup(self) -> None:
        events = [
            PlatformEvent(
                event_id="e1",
                event_type="settlement.anchor_recorded",
                created_at="2026-01-01T11:00:00Z",
                entity_type="settlement",
                entity_id="set-x",
                payload={
                    "anchor_hash": "0xdead",
                    "blockchain_anchor": {"tx_hash": "0xfeed"},
                },
            ),
            PlatformEvent(
                event_id="e2",
                event_type="delivery.compute_run_completed",
                created_at="2026-01-01T11:01:00Z",
                entity_type="position",
                entity_id="pos-2",
                payload={"job_id": "job-b", "delivered_ngh": 1.0},
            ),
        ]

        def job_by_settlement(sid: str) -> Optional[str]:
            return "job-b" if sid == "set-x" else None

        out = build_judge_chain_ledger(events, job_by_settlement=job_by_settlement, event_window=2)
        self.assertEqual(len(out.blocks), 1)
        self.assertEqual(len(out.blocks[0].related_ops), 1)
        self.assertEqual(out.blocks[0].related_ops[0].op_kind, "settlement_onchain_anchor")

    def test_interleaved_deliveries_keep_job_local_event_context(self) -> None:
        events = [
            PlatformEvent(
                event_id="e1",
                event_type="voucher.deposited",
                created_at="2026-01-01T12:00:00Z",
                entity_type="job",
                entity_id="job-a",
                payload={
                    "product_key": {"region": "us", "iso_hour": 1, "sla": "std", "tier": "basic"},
                    "amount_ngh": 7.0,
                },
            ),
            PlatformEvent(
                event_id="e2",
                event_type="delivery.compute_run_completed",
                created_at="2026-01-01T12:01:00Z",
                entity_type="position",
                entity_id="pos-b",
                payload={"job_id": "job-b", "delivered_ngh": 1.0},
            ),
            PlatformEvent(
                event_id="e3",
                event_type="delivery.compute_run_completed",
                created_at="2026-01-01T12:02:00Z",
                entity_type="position",
                entity_id="pos-a",
                payload={"job_id": "job-a", "delivered_ngh": 2.0},
            ),
        ]

        def job_by_settlement(sid: str) -> Optional[str]:
            return None

        out = build_judge_chain_ledger(events, job_by_settlement=job_by_settlement, event_window=3)
        self.assertEqual(len(out.blocks), 2)
        self.assertEqual(out.blocks[1].job_id, "job-a")
        self.assertEqual(len(out.blocks[1].related_ops), 1)
        self.assertEqual(out.blocks[1].related_ops[0].op_kind, "erc1155_escrow_lock")
        self.assertEqual(out.blocks[1].prev_block_hash, out.blocks[0].block_hash)


if __name__ == "__main__":
    unittest.main()
