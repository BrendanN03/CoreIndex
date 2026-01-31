# canonx (CoreIndex v2) — “Are these two outputs the same?”

`canonx` is the **Quality Control (QC) utility library** for CoreIndex.

CoreIndex v2 runs compute across multiple independent GPU providers. Because providers and GPUs can differ, we need an objective way to answer:

> If we run the “same package” twice (duplication / spot re-execution), **did we get the same result?**

That answer directly affects:
- **accept/reject** decisions (and therefore **pay/slash**)
- what we put in **Receipts** (the output hash / root)
- what we can **audit** later (and anchor on-chain)

---

## How this fits the v2 system (end-to-end)

1. **Buyer** submits sealed **packages**.
2. **Providers** run packages and upload outputs.
3. **QC Oracle** verifies outputs using duplication/canaries/spot re-exec.
4. QC needs two capabilities:
   - **hash** an output in a way anyone can reproduce later
   - **compare** two outputs fairly across small GPU/serializer differences
5. QC produces:
   - an output **Merkle root** (goes into the Receipt)
   - an accept/reject decision (drives settlement)

---

## What “canonicalization” means (plain language)

Two honest providers can output “the same data” with harmless differences:
- records in a different order
- tiny float rounding differences across GPUs
- different file splitting

So we define **canonical bytes**: a stable representation that both sides should reduce to.

### Our canonical on-wire format (v2)
- **JSON Lines (JSONL)**, UTF-8
- one JSON object per line
- keys appear in a fixed order (defined by a schema in `schemas/`)
- lines end with `\n`

Schemas live in `schemas/` (example: `schemas/table@1.json`).

---

## What this library provides today (usable now)

### 1) Merkle hashing (for Receipts / anchoring)
Given canonical bytes, we compute a SHA-256 Merkle root:
- chunk size: **4 MiB**
- leaf hash: `sha256(chunk)`
- parent hash: `sha256(left || right)`
- odd leaf rule: duplicate last leaf

Implementation: `merkle.py` (`merkle_stream`).

### 2) Comparing two outputs (duplication / spot checks)
- **`bit_exact`**: canonical bytes must match exactly.
- **`fp_tolerant`**: allow tiny float differences using BOTH:
  - `rel_tol = 1e-4`
  - `max_ulp = 2`

Non-float fields (strings/ints/bools) must still match exactly.

Implementation: `compare.py` + `ulp.py`.

### 3) Fast path
If Merkle roots match, return `equal = true` immediately (fast common case).

Implementation: `api_compare.py` (`compare_canonical_fast`).

---

## How engineers call this via the API

FastAPI endpoints are exposed at:
`apps/api/app/api/v1/endpoints/qc.py`

Endpoints:
- `POST /qc/hash`
- `POST /qc/canonicalize`
- `POST /qc/compare`

Important current limitation:
- these endpoints **assume the uploaded files are already canonical JSONL** unless you pass `input_format`
- currently supported canonicalizers:
  - `table@1`: `csv` or `jsonl`
  - `vectors@1`: `jsonl`
  - `cado_relations@1`: `jsonl`

---

## Glossary (quick)

- **Package**: a sealed unit of work (atomic for QC + settlement).
- **Receipt**: per-package record including output hash/root and QC flags.
- **Merkle root**: one hash representing a whole output (auditable; anchorable).
- **ULP**: “units in last place” distance between float64 values.
- **bit_exact**: strict equality.
- **fp_tolerant**: bounded float tolerance (v2 defaults: \(rel\_tol = 10^{-4}\), \(max\_ulp = 2\)).

