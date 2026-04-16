# canonx/compare.py
from __future__ import annotations

import json
from typing import Any, BinaryIO, Dict, Literal, Tuple

from .ulp import ulp_distance

Mode = Literal["bit_exact", "fp_tolerant"]
_ALIGNMENT_KEY_CANDIDATES = (
    "id",
    "item_id",
    "package_id",
    "rank",
    "index",
    "i",
)


def rel_err(a: float, b: float) -> float:
    return abs(a - b) / max(1e-12, max(abs(a), abs(b)))


def _is_special(v: Any) -> bool:
    return isinstance(v, str) and v in ("NaN", "Inf", "-Inf")


def _is_numeric_string(v: Any) -> bool:
    if not isinstance(v, str):
        return False
    if _is_special(v):
        return True
    try:
        float(v)
    except (TypeError, ValueError):
        return False
    return True


def _coerce_json_number(x: Any) -> float:
    if isinstance(x, (int, float)):
        return float(x)
    # if strings like "1.2" leak in, try to parse; otherwise raise
    return float(x)


def _same_numeric(a: Any, b: Any, rel_tol: float, max_ulp: int) -> Tuple[bool, float, int]:
    # Handle special tokens
    if _is_special(a) or _is_special(b):
        return (_is_special(a) and _is_special(b) and a == b, 0.0, 0)
    fa, fb = _coerce_json_number(a), _coerce_json_number(b)
    # Treat signed zeros as equal
    if fa == 0.0 and fb == 0.0:
        return (True, 0.0, 0)
    re = rel_err(fa, fb)
    ulp = ulp_distance(fa, fb)
    ok = (re <= rel_tol) and (ulp <= max_ulp)
    return ok, re, ulp


def _is_numeric_like(v: Any) -> bool:
    return isinstance(v, (int, float)) or _is_special(v) or _is_numeric_string(v)


def _is_hashable_scalar(v: Any) -> bool:
    return isinstance(v, (str, int, float, bool)) or v is None


def _record_sort_key(record: Dict[str, Any]) -> str:
    # Deterministic serializer variability guard (field ordering, whitespace).
    return json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _infer_alignment_key(a_records: list[Dict[str, Any]], b_records: list[Dict[str, Any]]) -> str | None:
    if not a_records or not b_records:
        return None
    shared = set(a_records[0].keys()) & set(b_records[0].keys())
    for key in _ALIGNMENT_KEY_CANDIDATES:
        if key not in shared:
            continue
        if all(key in rec for rec in a_records) and all(key in rec for rec in b_records):
            a_vals = [rec[key] for rec in a_records]
            b_vals = [rec[key] for rec in b_records]
            if all(_is_hashable_scalar(v) for v in a_vals + b_vals) and len(set(a_vals)) == len(
                a_vals
            ) and len(set(b_vals)) == len(b_vals):
                return key
    return None


def _align_records(
    a_records: list[Dict[str, Any]], b_records: list[Dict[str, Any]]
) -> list[Tuple[Dict[str, Any], Dict[str, Any]]]:
    key = _infer_alignment_key(a_records, b_records)
    if key is not None:
        a_map = {rec[key]: rec for rec in a_records}
        b_map = {rec[key]: rec for rec in b_records}
        if set(a_map.keys()) == set(b_map.keys()):
            return [(a_map[k], b_map[k]) for k in sorted(a_map.keys(), key=lambda v: str(v))]
    # Fallback: deterministic ordering by canonical JSON payload.
    a_sorted = sorted(a_records, key=_record_sort_key)
    b_sorted = sorted(b_records, key=_record_sort_key)
    return list(zip(a_sorted, b_sorted))


def _compare_value(
    a: Any,
    b: Any,
    *,
    rel_tol: float,
    max_ulp: int,
) -> Tuple[int, float, int]:
    """
    Compare possibly nested canonical JSON values.

    Returns:
      (diff_count, rel_err_max, ulp_max)
    """
    # Fast path.
    if a == b:
        return 0, 0.0, 0

    # Numeric tolerance path.
    if _is_numeric_like(a) or _is_numeric_like(b):
        ok, re, ulp = _same_numeric(a, b, rel_tol, max_ulp)
        return (0, re, ulp) if ok else (1, re, ulp)

    # Dict recursion.
    if isinstance(a, dict) and isinstance(b, dict):
        if a.keys() != b.keys():
            return 1, 0.0, 0
        diffs = 0
        rel_err_max, ulp_max = 0.0, 0
        for key in a.keys():
            d, re, ulp = _compare_value(a[key], b[key], rel_tol=rel_tol, max_ulp=max_ulp)
            diffs += d
            rel_err_max = max(rel_err_max, re)
            ulp_max = max(ulp_max, ulp)
        return diffs, rel_err_max, ulp_max

    # List recursion.
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return 1, 0.0, 0
        diffs = 0
        rel_err_max, ulp_max = 0.0, 0
        for va, vb in zip(a, b):
            d, re, ulp = _compare_value(va, vb, rel_tol=rel_tol, max_ulp=max_ulp)
            diffs += d
            rel_err_max = max(rel_err_max, re)
            ulp_max = max(ulp_max, ulp)
        return diffs, rel_err_max, ulp_max

    # Non-numeric scalar mismatch.
    return 1, 0.0, 0


def compare_canonical_streams(
    a_stream: BinaryIO,
    b_stream: BinaryIO,
    schema_id: str,
    mode: Mode,
    rel_tol: float = 1e-4,
    max_ulp: int = 2,
) -> Dict[str, Any]:
    """
    Compares canonical JSONL streams and is resilient to row-order drift by:
    - aligning on common unique keys (id/package_id/rank/...), then
    - falling back to canonical JSON lexical ordering.
    """
    diffs = 0
    rel_err_max, ulp_max = 0.0, 0
    recs = 0

    def parse_line(line: bytes) -> Dict[str, Any]:
        # JSONL one object per line, UTF-8
        return json.loads(line)
    a_records = [parse_line(line) for line in a_stream.readlines() if line.strip()]
    b_records = [parse_line(line) for line in b_stream.readlines() if line.strip()]
    recs = min(len(a_records), len(b_records))
    if len(a_records) != len(b_records):
        diffs += 1

    for ra, rb in _align_records(a_records, b_records):
        if mode == "bit_exact":
            if ra != rb:
                diffs += 1
        else:
            d, re, ulp = _compare_value(ra, rb, rel_tol=rel_tol, max_ulp=max_ulp)
            diffs += d
            rel_err_max = max(rel_err_max, re)
            ulp_max = max(ulp_max, ulp)

    equal = diffs == 0
    return {
        "equal": equal,
        "mode": mode,
        "summary": {
            "schema_id": schema_id,
            "record_count": recs,
            "rel_err_max": rel_err_max,
            "ulp_max": ulp_max,
            "differences": diffs,
        },
    }

