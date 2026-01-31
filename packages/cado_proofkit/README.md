# CADO Proof‑Kit (v2 demo, RTX 3060 testbed)

This package is the **reference‑grade verifier** for the CADO‑NFS demo in v2.
It is designed to be **small, deterministic, and easy to audit**.

## Why this exists (v2 context)

The v2 spec allows **certificate checks** as a QC signal for collective computations.
For CADO‑NFS, the key certificate is:

> A vector \(v\) such that \( Mv = 0 \) over \( \mathbb{F}_2 \).

Checking \( Mv = 0 \) is much cheaper than re‑running the entire linear‑algebra job.
So QC can validate collective LA results without full duplication.

## What this package provides

1) **F2 certificate verifier**  
   Verifies that a submitted vector satisfies \( Mv = 0 \) over \( \mathbb{F}_2 \).

2) **Final factor check (gcd)**  
   Verifies the factor by checking \( \gcd(x-y, N) \) is a non‑trivial factor.

3) **Matrix commitment helpers**  
   Canonicalize matrix rows and hash them for receipts.

4) **Tiny test vectors**  
   Small matrices + known kernel vectors so you can test correctness fast.

## Why this matches RTX 3060 demo constraints

- The matrix‑vector verifier is **pure CPU**, so it runs anywhere.
- The GPU job only needs to output \(v\); QC checks it cheaply.
- Determinism comes from using **bit‑packed F2 arithmetic** and fixed seeds.

## File layout

```
packages/cado_proofkit/
  README.md
  verifier_f2.py          # Mv = 0 verifier over F2
  gcd_check.py            # gcd verification for factors
  matrix_loader.py        # load tiny matrices from JSON
  hash_commit.py          # canonical hash commitment helpers
  test_vectors/
    tiny_matrix.json      # tiny M and known kernel vector
    tiny_factor.json      # tiny N with known factor
    la_output_sample.json # sample LA output for API verification
```

## How QC uses this

In the QC oracle:
1) Load \(M\) (or its committed hash / shard).
2) Verify \(Mv = 0\) using `verifier_f2.py`.
3) If the job also reports a candidate factorization, verify it with `gcd_check.py`.
4) Record `certificate_verified=true` in the Receipt.

**API note:** The QC API exposes `/qc/cert/verify_la_output` which accepts the full
LA output JSON (including `matrix_hash`, `vector_bits`, `seed`, etc.).

---

**Next steps (later):**
- Add a “real” matrix loader (e.g., from a sparse format).
- Support distributed verification if matrices are too large.
- Extend to block‑Lanczos checkpoints.

