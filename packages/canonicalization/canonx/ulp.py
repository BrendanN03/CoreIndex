# canonx/ulp.py
from __future__ import annotations

import math
import struct


def _float_to_ordered_int(x: float) -> int:
    """
    Map IEEE-754 float64 to a monotonically ordered int so that ulp distance
    is abs(int_repr(a) - int_repr(b)).
    """
    bits = struct.unpack(">q", struct.pack(">d", x))[0]  # signed 64
    # Flip sign bit to make ordering monotonic: negative values first.
    return bits ^ ((bits >> 63) & 0x7FFFFFFFFFFFFFFF)


def ulp_distance(a: float, b: float) -> int:
    # Treat NaNs as infinite distance (caller handles NaN equality policy)
    if math.isnan(a) or math.isnan(b):
        return (1 << 63) - 1
    # Map -0.0 and +0.0 to same value
    if a == 0.0 and b == 0.0:
        return 0
    ia = _float_to_ordered_int(a)
    ib = _float_to_ordered_int(b)
    d = abs(ia - ib)
    return int(d)

