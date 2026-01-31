from __future__ import annotations

from typing import List


def _parse_bitstring(bitstr: str) -> List[int]:
    return [1 if ch == "1" else 0 for ch in bitstr.strip()]


def verify_f2_matrix_vector(matrix_rows: List[str], vector_bits: str) -> bool:
    """
    Verify Mv = 0 over F2.

    Inputs:
    - matrix_rows: list of bitstrings, one per row (e.g., "101001")
    - vector_bits: bitstring for v (e.g., "110001")

    Returns True if every row dot v == 0 (mod 2).
    """
    v = _parse_bitstring(vector_bits)
    n = len(v)
    for row in matrix_rows:
        r = _parse_bitstring(row)
        if len(r) != n:
            raise ValueError("Row length mismatch in matrix")
        # dot product mod 2
        acc = 0
        for a, b in zip(r, v):
            acc ^= (a & b)
        if acc != 0:
            return False
    return True

