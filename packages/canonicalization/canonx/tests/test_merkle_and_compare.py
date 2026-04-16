import io

from canonx.compare import compare_canonical_streams
from canonx.merkle import merkle_stream


def test_merkle_empty():
    root, leaves, nbytes, nchunks, csize = merkle_stream(io.BytesIO(b""))
    assert nbytes == 0
    assert nchunks == 0
    assert root.startswith("0x")


def test_merkle_two_chunks():
    data = b"A" * (4 * 1024 * 1024) + b"B" * (4 * 1024 * 1024)
    root, leaves, nbytes, nchunks, csize = merkle_stream(io.BytesIO(data))
    assert nchunks == 2
    assert len(leaves) == 2
    assert root.startswith("0x")


def test_compare_bit_exact_equal():
    a = b'{"id":"a","x":1.2}\n{"id":"b","x":2.3}\n'
    b = b'{"id":"a","x":1.2}\n{"id":"b","x":2.3}\n'
    res = compare_canonical_streams(io.BytesIO(a), io.BytesIO(b), "table@1", "bit_exact")
    assert res["equal"] is True


def test_compare_fp_tolerant_small_jitter():
    a = b'{"id":"a","x":1.0}\n'
    b = b'{"id":"a","x":1.0000000000000002}\n'
    res = compare_canonical_streams(
        io.BytesIO(a),
        io.BytesIO(b),
        "table@1",
        "fp_tolerant",
        rel_tol=1e-4,
        max_ulp=2,
    )
    assert res["equal"] is True


def test_compare_fp_tolerant_reject():
    a = b'{"id":"a","x":1.2}\n'
    b = b'{"id":"a","x":1.25}\n'
    res = compare_canonical_streams(
        io.BytesIO(a),
        io.BytesIO(b),
        "table@1",
        "fp_tolerant",
        rel_tol=1e-4,
        max_ulp=2,
    )
    assert res["equal"] is False


def test_signed_zero():
    a = b'{"id":"a","x":0.0}\n'
    b = b'{"id":"a","x":-0.0}\n'
    res = compare_canonical_streams(io.BytesIO(a), io.BytesIO(b), "table@1", "fp_tolerant")
    assert res["equal"]


def test_nan_inf_policy():
    a = b'{"id":"a","x":"NaN"}\n'
    b = b'{"id":"a","x":"NaN"}\n'
    ok = compare_canonical_streams(io.BytesIO(a), io.BytesIO(b), "vectors@1", "fp_tolerant")
    assert ok["equal"]

    # Comparator treats identical special tokens as equal; schema-level NaN/Inf
    # rejection is enforced during canonicalization, not raw compare.
    bad = compare_canonical_streams(io.BytesIO(a), io.BytesIO(b), "table@1", "fp_tolerant")
    assert bad["equal"] is True


def test_compare_order_drift_with_id_alignment():
    a = b'{"id":"b","x":2.0}\n{"id":"a","x":1.0}\n'
    b = b'{"id":"a","x":1.0}\n{"id":"b","x":2.0}\n'
    res = compare_canonical_streams(io.BytesIO(a), io.BytesIO(b), "table@1", "bit_exact")
    assert res["equal"] is True


def test_compare_numeric_string_vs_number_fp_tolerant():
    a = b'{"id":"a","x":"1.0000000"}\n'
    b = b'{"id":"a","x":1.0}\n'
    res = compare_canonical_streams(
        io.BytesIO(a),
        io.BytesIO(b),
        "table@1",
        "fp_tolerant",
        rel_tol=1e-4,
        max_ulp=2,
    )
    assert res["equal"] is True

