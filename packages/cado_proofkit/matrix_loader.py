from __future__ import annotations

import json
from pathlib import Path
from typing import List, Tuple


def load_matrix_json(path: Path) -> Tuple[List[str], str]:
    """
    Load a tiny F2 matrix + vector from JSON.

    JSON format:
    {
      "matrix_rows": ["1010", "0110"],
      "vector_bits": "1100"
    }
    """
    data = json.loads(path.read_text())
    return data["matrix_rows"], data["vector_bits"]

