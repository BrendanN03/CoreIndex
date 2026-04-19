"""HTTP tests for ``dev_remote_factor_server`` (local factor stand-in for CoreIndex).

Very long digit strings are rejected (demo cap). Run from ``apps/api``::

    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from starlette.testclient import TestClient

from dev_remote_factor_server import _MAX_COMPOSITE_DIGITS, _MAX_TRIAL_DIGITS, app


class TestDevFactorStubHttp(unittest.TestCase):
    def test_factor_143(self) -> None:
        c = TestClient(app)
        r = c.post("/factor", json={"gpu_count": 1, "composite": "143"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["summary"]["final_prime_factors"], [11, 13])

    def test_factor_semiprimes(self) -> None:
        c = TestClient(app)
        cases = [
            ("15", [3, 5]),
            ("77", [7, 11]),
            ("221", [13, 17]),
            ("1000003", [1000003]),
        ]
        for composite, expected in cases:
            with self.subTest(composite=composite):
                r = c.post("/factor", json={"gpu_count": 2, "composite": composite})
                self.assertEqual(r.status_code, 200, r.text)
                got = sorted(int(x) for x in r.json()["summary"]["final_prime_factors"])
                self.assertEqual(sorted(expected), got)

    def test_composite_too_long_returns_400(self) -> None:
        c = TestClient(app)
        self.assertEqual(_MAX_TRIAL_DIGITS, _MAX_COMPOSITE_DIGITS)
        big = "9" * (_MAX_COMPOSITE_DIGITS + 1)
        r = c.post("/factor", json={"gpu_count": 1, "composite": big})
        self.assertEqual(r.status_code, 400)
        body = r.json()
        self.assertIn("detail", body)

    def test_max_width_composite_still_ok(self) -> None:
        c = TestClient(app)
        # Exactly max digits: pure power of ten factors quickly via SymPy.
        s = str(10 ** (_MAX_COMPOSITE_DIGITS - 1))
        self.assertEqual(len(s), _MAX_COMPOSITE_DIGITS)
        r = c.post("/factor", json={"gpu_count": 1, "composite": s})
        self.assertEqual(r.status_code, 200, r.text)
        fac = r.json()["summary"]["final_prime_factors"]
        self.assertIn(2, fac)
        self.assertIn(5, fac)


if __name__ == "__main__":
    unittest.main()
