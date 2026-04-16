import io

from canonx.canonicalize import canonicalize_bytes
from canonx.compare import compare_canonical_streams
from canonx.merkle import merkle_stream


def _root(data: bytes) -> str:
    root, _, _, _, _ = merkle_stream(io.BytesIO(data))
    return root


def test_table_csv_vs_jsonl_same_root():
    csv_text = b"id,ts_utc,x,y\nalpha,2026-01-01T00:00:00Z,1.0,2.0\n"
    jsonl_text = b'{"id":"alpha","ts_utc":"2026-01-01T00:00:00Z","x":1.0,"y":2.0}\n'
    a = canonicalize_bytes(schema_id="table@1", input_bytes=csv_text, input_format="csv")
    b = canonicalize_bytes(schema_id="table@1", input_bytes=jsonl_text, input_format="jsonl")
    assert _root(a) == _root(b)


def test_table_row_order_stable_root():
    a = (
        b'{"id":"b","ts":"2026-01-01T00:00:01Z","x":2.0,"y":3.0}\n'
        b'{"id":"a","ts":"2026-01-01T00:00:00Z","x":1.0,"y":2.0}\n'
    )
    b = (
        b'{"id":"a","ts_utc":"2026-01-01T00:00:00Z","x":1.0,"y":2.0}\n'
        b'{"id":"b","ts_utc":"2026-01-01T00:00:01Z","x":2.0,"y":3.0}\n'
    )
    ca = canonicalize_bytes(schema_id="table@1", input_bytes=a, input_format="jsonl")
    cb = canonicalize_bytes(schema_id="table@1", input_bytes=b, input_format="jsonl")
    assert _root(ca) == _root(cb)


def test_vectors_fp_tolerant_accepts_small_jitter():
    a = b'{"id":"v1","vector":[1.0,2.0,3.0]}\n'
    b = b'{"id":"v1","vector":[1.0000000000000002,2.0,3.0]}\n'
    res = compare_canonical_streams(
        io.BytesIO(a),
        io.BytesIO(b),
        "vectors@1",
        "fp_tolerant",
        rel_tol=1e-4,
        max_ulp=2,
    )
    assert res["equal"] is True


def test_vectors_fp_tolerant_rejects_large_drift():
    a = b'{"id":"v1","vector":[1.2,2.0,3.0]}\n'
    b = b'{"id":"v1","vector":[1.5,2.0,3.0]}\n'
    res = compare_canonical_streams(
        io.BytesIO(a),
        io.BytesIO(b),
        "vectors@1",
        "fp_tolerant",
        rel_tol=1e-4,
        max_ulp=2,
    )
    assert res["equal"] is False


def test_cado_relations_int_mismatch_rejected():
    a = b'{"a":1001,"b":2,"p":11,"q":13}\n'
    b = b'{"a":1002,"b":2,"p":11,"q":13}\n'
    res = compare_canonical_streams(io.BytesIO(a), io.BytesIO(b), "cado_relations@1", "bit_exact")
    assert res["equal"] is False


def test_fp_tolerant_nested_payload_jitter_passes():
    a = b'{"id":"a","stats":{"loss":0.123456},"vec":[1.0,2.0]}\n'
    b = b'{"id":"a","stats":{"loss":0.12345600000000001},"vec":[1.0000000000000002,2.0]}\n'
    res = compare_canonical_streams(
        io.BytesIO(a),
        io.BytesIO(b),
        "vectors@1",
        "fp_tolerant",
        rel_tol=1e-4,
        max_ulp=2,
    )
    assert res["equal"] is True
