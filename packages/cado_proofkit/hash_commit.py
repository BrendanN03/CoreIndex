from __future__ import annotations

import hashlib
from typing import List


def _hex(b: bytes) -> str:
    return "0x" + b.hex()


def hash_matrix_rows(matrix_rows: List[str]) -> str:
    """
    Canonicalize matrix rows (join with '\n') and hash with SHA-256.

    This is a simple commitment for demo use. For large matrices we will
    switch to a Merkle scheme later.
    """
    data = "\n".join(row.strip() for row in matrix_rows).encode("utf-8")
    return _hex(hashlib.sha256(data).digest())

