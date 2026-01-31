# canonx/merkle.py
from __future__ import annotations

import hashlib
from typing import BinaryIO, List, Tuple

CHUNK_SIZE = 4 * 1024 * 1024  # 4 MiB


def sha256(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()


def _hex(b: bytes) -> str:
    return "0x" + b.hex()


def merkle_from_chunks(leaf_hashes: List[bytes]) -> bytes:
    if not leaf_hashes:
        # Empty stream root = sha256 of empty string (conventional)
        return sha256(b"")
    level = leaf_hashes
    while len(level) > 1:
        nxt: List[bytes] = []
        it = iter(range(0, len(level), 2))
        for i in it:
            left = level[i]
            right = level[i + 1] if i + 1 < len(level) else left
            nxt.append(sha256(left + right))
        level = nxt
    return level[0]


def merkle_stream(
    in_stream: BinaryIO, chunk_size: int = CHUNK_SIZE
) -> Tuple[str, List[str], int, int, int]:
    """
    Returns (root_hex, leaf_hexes, num_bytes, num_chunks, chunk_size).
    """
    leaf_hashes: List[bytes] = []
    total = 0
    while True:
        chunk = in_stream.read(chunk_size)
        if not chunk:
            break
        total += len(chunk)
        leaf_hashes.append(sha256(chunk))
    root = merkle_from_chunks(leaf_hashes)
    return _hex(root), [_hex(h) for h in leaf_hashes], total, len(leaf_hashes), chunk_size

