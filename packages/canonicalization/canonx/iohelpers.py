# canonx/iohelpers.py
import gzip
from typing import BinaryIO


def open_maybe_gzip(buf: BinaryIO) -> BinaryIO:
    # Peek first two bytes
    head = buf.read(2)
    buf.seek(0)
    if head == b"\x1f\x8b":  # gzip magic
        return gzip.GzipFile(fileobj=buf, mode="rb")
    return buf

