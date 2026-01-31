## How to use the gold + adversarial set

1) Put gold outputs in `gold/` (canonical JSONL).
2) Generate adversarial variants:

```bash
python3 adversarial_generator.py \
  --input gold/table_run_a.jsonl \
  --out-dir adversarial/table \
  --mode table
```

3) Compare using canonx (examples):

```bash
# gold vs gold (should pass)
python3 -c "from canonx.compare import compare_canonical_streams; import io; 
a=open('gold/table_run_a.jsonl','rb'); b=open('gold/table_run_b.jsonl','rb');
print(compare_canonical_streams(a,b,'table@1','fp_tolerant'))"

# gold vs adversarial (most should fail in fp_tolerant)
python3 -c "from canonx.compare import compare_canonical_streams; import io; 
a=open('gold/table_run_a.jsonl','rb'); b=open('adversarial/table/jitter_large.jsonl','rb');
print(compare_canonical_streams(a,b,'table@1','fp_tolerant'))"
```

4) Record which cases **pass** and **fail** to build a simple ROC table.

