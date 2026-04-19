"""Regression: adversarial suite expectations must match canonical compare semantics."""

from __future__ import annotations

import asyncio
import json
import sys
import unittest
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = API_ROOT.parents[1]
CANON_ROOT = REPO_ROOT / "packages" / "canonicalization"
for p in (CANON_ROOT, API_ROOT):
    sp = str(p)
    if sp not in sys.path:
        sys.path.insert(0, sp)

from app.api.v1.endpoints.qc import (  # noqa: E402
    QcAdversarialSuiteRequest,
    qc_adversarial_suite,
)


def _default_p2_base_rows() -> list[dict]:
    text = '{"i":1,"x":1.0000}\n{"i":2,"x":2.0000}\n'
    return [json.loads(line) for line in text.strip().splitlines() if line.strip()]


class TestQcAdversarialSuite(unittest.TestCase):
    def test_presentation_defaults_pass_bit_exact_and_fp_tolerant(self) -> None:
        rows = _default_p2_base_rows()

        async def _run(mode: str) -> dict:
            return await qc_adversarial_suite(
                QcAdversarialSuiteRequest(
                    schema_id="cado_relations@1",
                    mode=mode,  # type: ignore[arg-type]
                    rel_tol=1e-4,
                    max_ulp=2,
                    variant_mode="relations",
                    base_rows=rows,
                )
            )

        for mode in ("bit_exact", "fp_tolerant"):
            out = asyncio.run(_run(mode))
            metrics = out["metrics"]
            self.assertEqual(metrics["false_accept_count"], 0, msg=f"{mode} false accepts")
            self.assertEqual(metrics["false_reject_count"], 0, msg=f"{mode} false rejects")
            self.assertGreaterEqual(metrics["expectation_pass_rate"], 1.0, msg=f"{mode} pass rate")


if __name__ == "__main__":
    unittest.main()
