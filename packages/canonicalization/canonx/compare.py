# canonx/compare.py
from __future__ import annotations

import json
from typing import Any, BinaryIO, Dict, Literal, Tuple

from .ulp import ulp_distance

Mode = Literal["bit_exact", "fp_tolerant"]


def rel_err(a: float, b: float) -> float:
    return abs(a - b) / max(1e-12, max(abs(a), abs(b)))


def _is_special(v: Any) -> bool:
    return isinstance(v, str) and v in ("NaN", "Inf", "-Inf")


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


def compare_canonical_streams(
    a_stream: BinaryIO,
    b_stream: BinaryIO,
    schema_id: str,
    mode: Mode,
    rel_tol: float = 1e-4,
    max_ulp: int = 2,
) -> Dict[str, Any]:
    """
    Assumes both streams are already canonical JSONL with identical schemas
    and sorted by the schema's primary key(s).
    """
    diffs = 0
    rel_err_max, ulp_max = 0.0, 0
    recs = 0

    def parse_line(line: bytes) -> Dict[str, Any]:
        # JSONL one object per line, UTF-8
        return json.loads(line)

    la = a_stream.readline()
    lb = b_stream.readline()
    while la or lb:
        if not la or not lb:
            # different number of records -> mismatch
            diffs += 1
            break

        ra = parse_line(la)
        rb = parse_line(lb)
        recs += 1

        if mode == "bit_exact":
            # byte-equality already ensured by identical canonicalization + hashing
            # but we still sanity-check field-by-field for diagnostics
            if ra != rb:
                diffs += 1
        else:
            # fp_tolerant: compare field-by-field
            if ra.keys() != rb.keys():
                diffs += 1
            else:
                for k in ra.keys():
                    va, vb = ra[k], rb[k]
                    # Quick path: identical JSON tokens
                    if va == vb:
                        continue
                    # Numeric?
                    if (
                        isinstance(va, (int, float))
                        or isinstance(vb, (int, float))
                        or _is_special(va)
                        or _is_special(vb)
                    ):
                        ok, re, ulp = _same_numeric(va, vb, rel_tol, max_ulp)
                        rel_err_max = max(rel_err_max, re)
                        ulp_max = max(ulp_max, ulp)
                        if not ok:
                            diffs += 1
                    else:
                        # strings/booleans/null must match exactly after canonicalization
                        if va != vb:
                            diffs += 1

        la = a_stream.readline()
        lb = b_stream.readline()

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

