from __future__ import annotations

import math


def gcd_factor_check(n: int, x: int, y: int) -> int:
    """
    Verify a non-trivial factor of N via gcd(x - y, N).

    Returns the factor if non-trivial, else 1 or N.
    """
    return math.gcd(abs(x - y), n)

