## QC Step 4 — Gold Corpus + Adversarial Generator

This folder helps you **measure false-reject / false-accept** behavior of QC.
It does two things:

1) **Gold corpus**: a small set of clean outputs (from two providers) that should match.
2) **Adversarial deltas**: controlled corruptions that should be caught.

### Why this matters
- We need a **defensible claim** that QC catches cheating.
- We also need to **avoid false slashing** when providers are honest.
- The gold + adversarial set lets you test both.

### What to produce
You will create:
- `gold/` — two clean outputs for the same package (provider A / provider B)
- `adversarial/` — corrupted variants of a gold output

### How to run (high level)
1) Put a canonical JSONL file in `gold/` (or pass any path).
2) Run `adversarial_generator.py` to produce variants.
3) Compare with `canonx.compare` to verify:
   - gold vs gold → **equal**
   - gold vs adversarial → **not equal** (for large corruption)

### Example
```bash
python3 adversarial_generator.py \
  --input gold/table_run_a.jsonl \
  --out-dir adversarial/table \
  --mode table
```

### Notes
- This uses simple JSONL transforms so it runs anywhere.
- For larger datasets, you can scale up the input file.
- The generator does not require any GPU dependencies.

