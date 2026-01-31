## Quickstart (local verification)

```bash
python3 - <<'PY'
import json
from pathlib import Path
from verifier_f2 import verify_f2_matrix_vector
from gcd_check import gcd_factor_check
from matrix_loader import load_matrix_json
from hash_commit import hash_matrix_rows

base = Path("packages/cado_proofkit/test_vectors")

rows, vbits = load_matrix_json(base / "tiny_matrix.json")
print("Mv=0?", verify_f2_matrix_vector(rows, vbits))
print("matrix hash:", hash_matrix_rows(rows))

tf = json.loads((base / "tiny_factor.json").read_text())
print("gcd factor:", gcd_factor_check(tf["N"], tf["x"], tf["y"]))
PY
```

