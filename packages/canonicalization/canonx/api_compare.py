# canonx/api_compare.py
from typing import Any, BinaryIO, Dict, Literal

from .compare import compare_canonical_streams
from .merkle import merkle_stream

Mode = Literal["bit_exact", "fp_tolerant"]


def compare_canonical_fast(
    a: BinaryIO,
    b: BinaryIO,
    schema_id: str,
    mode: Mode,
    rel_tol: float = 1e-4,
    max_ulp: int = 2,
) -> Dict[str, Any]:
    # Hash both (streaming)
    root_a, _, _, _, _ = merkle_stream(a)
    root_b, _, _, _, _ = merkle_stream(b)
    if root_a == root_b:
        return {
            "equal": True,
            "mode": mode,
            "summary": {
                "schema_id": schema_id,
                "record_count": None,
                "rel_err_max": 0.0,
                "ulp_max": 0,
                "differences": 0,
            },
        }

    # Rewind streams for the full tolerant check
    if a.seekable():
        a.seek(0)
    if b.seekable():
        b.seek(0)
    return compare_canonical_streams(a, b, schema_id, mode, rel_tol, max_ulp)

