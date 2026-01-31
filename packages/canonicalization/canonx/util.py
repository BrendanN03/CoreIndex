# canonx/util.py
from typing import BinaryIO


def count_jsonl_records(stream: BinaryIO) -> int:
    n = 0
    for _ in stream:
        n += 1
    return n

