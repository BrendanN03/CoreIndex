from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


def _schema_path(schema_id: str) -> Path:
    return Path(__file__).resolve().parent / "schemas" / f"{schema_id}.json"


def load_schema(schema_id: str) -> dict:
    path = _schema_path(schema_id)
    if not path.exists():
        raise ValueError(f"Unknown schema_id: {schema_id}")
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _normalize_timestamp(ts: str) -> str:
    # Accept RFC3339 with Z or offset; normalize to UTC with millisecond precision.
    txt = ts.strip()
    if txt.endswith("Z"):
        txt = txt[:-1] + "+00:00"
    dt = datetime.fromisoformat(txt)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt = dt.astimezone(timezone.utc)
    # Format with milliseconds
    base = dt.strftime("%Y-%m-%dT%H:%M:%S")
    ms = int(dt.microsecond / 1000)
    return f"{base}.{ms:03d}Z"


def _normalize_float_token(v: Any) -> Any:
    if isinstance(v, str) and v in ("NaN", "Inf", "-Inf"):
        return v
    if isinstance(v, (int, float)):
        val = float(v)
    else:
        # Try parsing numeric strings
        val = float(v)
    # Normalize signed zero
    if val == 0.0:
        return 0.0
    return val


def _format_float_token(v: Any) -> Any:
    # Keep special tokens as strings; keep normal floats as numbers
    if isinstance(v, str) and v in ("NaN", "Inf", "-Inf"):
        return v
    return float(v)


def _write_jsonl(rows: List[Dict[str, Any]]) -> bytes:
    out = []
    for row in rows:
        out.append(json.dumps(row, separators=(",", ":")))
    return ("\n".join(out) + "\n").encode("utf-8")


def _sort_rows(rows: List[Dict[str, Any]], keys: List[str]) -> List[Dict[str, Any]]:
    def key_fn(row: Dict[str, Any]) -> tuple:
        parts = []
        for k in keys:
            v = row.get(k)
            # For missing optional ints, sort earlier using sentinel
            if v is None:
                parts.append(-1)
            else:
                parts.append(v)
        return tuple(parts)

    return sorted(rows, key=key_fn)


def canonicalize_table_jsonl(rows: Iterable[Dict[str, Any]]) -> bytes:
    schema = load_schema("table@1")
    cols = schema["columns"]
    col_names = [c["name"] for c in cols]
    key_cols = schema["primary_key"]

    normalized: List[Dict[str, Any]] = []
    for raw in rows:
        row: Dict[str, Any] = {}
        # allow ts alias in input
        if "ts_utc" not in raw and "ts" in raw:
            raw["ts_utc"] = raw["ts"]

        for col in col_names:
            if col not in raw:
                # optional label can be omitted
                if col == "label":
                    continue
                raise ValueError(f"Missing required column: {col}")
            val = raw[col]
            if col == "ts_utc":
                row[col] = _normalize_timestamp(str(val))
            elif col in ("x", "y"):
                row[col] = _format_float_token(_normalize_float_token(val))
            elif col == "label":
                if val is None or val == "":
                    continue
                row[col] = str(val)
            else:
                row[col] = str(val)
        normalized.append(row)

    normalized = _sort_rows(normalized, key_cols)
    return _write_jsonl(normalized)


def canonicalize_table_csv(text: str) -> bytes:
    reader = csv.DictReader(text.splitlines())
    rows = [row for row in reader]
    return canonicalize_table_jsonl(rows)


def canonicalize_vectors_jsonl(rows: Iterable[Dict[str, Any]]) -> bytes:
    schema = load_schema("vectors@1")
    key_cols = schema["primary_key"]

    normalized: List[Dict[str, Any]] = []
    expected_len: Optional[int] = None
    for raw in rows:
        if "id" not in raw or "vector" not in raw:
            raise ValueError("vectors@1 requires id and vector")
        vec = raw["vector"]
        if not isinstance(vec, list):
            raise ValueError("vector must be a list")
        if expected_len is None:
            expected_len = len(vec)
        if len(vec) != expected_len:
            raise ValueError("vector length mismatch")
        norm_vec = [_format_float_token(_normalize_float_token(v)) for v in vec]
        normalized.append({"id": str(raw["id"]), "vector": norm_vec})

    normalized = _sort_rows(normalized, key_cols)
    return _write_jsonl(normalized)


def canonicalize_cado_relations_jsonl(rows: Iterable[Dict[str, Any]]) -> bytes:
    schema = load_schema("cado_relations@1")
    fields = [f["name"] for f in schema["fields"]]
    key_cols = schema["primary_key"]

    normalized: List[Dict[str, Any]] = []
    for raw in rows:
        row: Dict[str, Any] = {}
        for name in fields:
            if name not in raw:
                if name == "large_prime":
                    continue
                raise ValueError(f"Missing required field: {name}")
            val = raw[name]
            if val is None:
                continue
            row[name] = int(val)
        normalized.append(row)

    normalized = _sort_rows(normalized, key_cols)
    return _write_jsonl(normalized)


def canonicalize_bytes(
    *,
    schema_id: str,
    input_bytes: bytes,
    input_format: str,
) -> bytes:
    """
    Convert raw inputs into canonical JSONL bytes for supported schemas.

    Supported:
    - table@1: jsonl, csv
    - vectors@1: jsonl
    - cado_relations@1: jsonl
    """
    text = input_bytes.decode("utf-8")

    if schema_id == "table@1":
        if input_format == "csv":
            return canonicalize_table_csv(text)
        if input_format == "jsonl":
            rows = [json.loads(line) for line in text.splitlines() if line.strip()]
            return canonicalize_table_jsonl(rows)
        raise ValueError("table@1 supports input_format: csv, jsonl")

    if schema_id == "vectors@1":
        if input_format != "jsonl":
            raise ValueError("vectors@1 supports input_format: jsonl")
        rows = [json.loads(line) for line in text.splitlines() if line.strip()]
        return canonicalize_vectors_jsonl(rows)

    if schema_id == "cado_relations@1":
        if input_format != "jsonl":
            raise ValueError("cado_relations@1 supports input_format: jsonl")
        rows = [json.loads(line) for line in text.splitlines() if line.strip()]
        return canonicalize_cado_relations_jsonl(rows)

    raise ValueError(f"Unsupported schema_id: {schema_id}")

