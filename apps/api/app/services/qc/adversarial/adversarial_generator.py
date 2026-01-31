from __future__ import annotations

import argparse
import json
import os
import random
from pathlib import Path
from typing import Any, Dict, List, Tuple


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def _write_jsonl(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, separators=(",", ":")))
            f.write("\n")


def _reorder_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = rows[:]
    random.shuffle(out)
    return out


def _perturb_floats(rows: List[Dict[str, Any]], factor: float) -> List[Dict[str, Any]]:
    out = []
    for row in rows:
        new_row = {}
        for k, v in row.items():
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                new_row[k] = v * (1.0 + factor)
            else:
                new_row[k] = v
        out.append(new_row)
    return out


def _flip_signed_zero(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for row in rows:
        new_row = {}
        for k, v in row.items():
            if isinstance(v, float) and v == 0.0:
                new_row[k] = -0.0
            else:
                new_row[k] = v
        out.append(new_row)
    return out


def _inject_nan(rows: List[Dict[str, Any]], key: str) -> List[Dict[str, Any]]:
    out = []
    for row in rows:
        new_row = dict(row)
        if key in new_row:
            new_row[key] = "NaN"
        out.append(new_row)
    return out


def _truncate_decimals(rows: List[Dict[str, Any]], decimals: int) -> List[Dict[str, Any]]:
    out = []
    for row in rows:
        new_row = {}
        for k, v in row.items():
            if isinstance(v, float):
                fmt = f"{{:.{decimals}f}}"
                new_row[k] = float(fmt.format(v))
            else:
                new_row[k] = v
        out.append(new_row)
    return out


def generate_adversarial_variants(
    *,
    rows: List[Dict[str, Any]],
    out_dir: Path,
    mode: str,
) -> None:
    # 1) reorder
    _write_jsonl(out_dir / "reorder.jsonl", _reorder_rows(rows))

    # 2) small jitter (should usually pass fp_tolerant)
    _write_jsonl(out_dir / "jitter_small.jsonl", _perturb_floats(rows, factor=5e-5))

    # 3) large jitter (should fail fp_tolerant)
    _write_jsonl(out_dir / "jitter_large.jsonl", _perturb_floats(rows, factor=5e-2))

    # 4) signed zero flip
    _write_jsonl(out_dir / "signed_zero.jsonl", _flip_signed_zero(rows))

    # 5) truncate decimals
    _write_jsonl(out_dir / "truncate_3dp.jsonl", _truncate_decimals(rows, decimals=3))

    # 6) NaN injection (only makes sense for schemas that allow NaN)
    if mode in ("table", "vectors"):
        _write_jsonl(out_dir / "nan_inject.jsonl", _inject_nan(rows, key="x"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate adversarial JSONL variants.")
    parser.add_argument("--input", required=True, help="Path to canonical JSONL input")
    parser.add_argument("--out-dir", required=True, help="Output directory for variants")
    parser.add_argument("--mode", choices=["table", "vectors", "relations"], default="table")
    args = parser.parse_args()

    random.seed(1337)
    input_path = Path(args.input)
    out_dir = Path(args.out_dir)

    rows = _read_jsonl(input_path)
    if not rows:
        raise SystemExit("input file is empty")

    generate_adversarial_variants(rows=rows, out_dir=out_dir, mode=args.mode)
    print(f"Wrote variants to {out_dir}")


if __name__ == "__main__":
    main()

