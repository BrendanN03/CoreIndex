## Gold corpus (placeholder)

Put clean, canonical JSONL outputs here.

Suggested layout:

gold/
  table_run_a.jsonl
  table_run_b.jsonl
  vectors_run_a.jsonl
  vectors_run_b.jsonl
  cado_relations_run_a.jsonl
  cado_relations_run_b.jsonl

These should be **two independent runs** of the same package.
They should compare equal under the expected mode:
- `table@1` and `vectors@1`: `fp_tolerant`
- `cado_relations@1`: `bit_exact`

