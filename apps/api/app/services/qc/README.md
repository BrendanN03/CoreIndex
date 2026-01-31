## QC Step 3 — Sampling + Dispute (teachable notes)

This folder turns the **canonical comparator** (Step 2) into a **credible QC policy**
that the rest of the system can implement and defend.

### Big picture (v2 flow)
1) We run packages on providers.
2) QC needs to decide **accept vs reject**.
3) QC uses **sampling** to keep costs low but still catch cheating.
4) If sampling finds a mismatch, QC runs a **dispute re-exec** and makes a final decision.

### What we ship here
- `policy/qc_policy.json`: the default rates + dispute parameters.
- `sampling.py`: deterministic, provider-independent sampling (replayable for audits).
- `dispute.py`: a simple statistical decision rule for disputes.
- `detection_power.py`: a script to print a “detection power table” for slides.
- `policy_tuning.py`: a script to compare detection power across policy settings.

### 1) Sampling (why it matters)
We must choose which items to check in a way that:
- providers cannot predict,
- auditors can reproduce,
- the scheduler can justify later.

We use **HMAC-SHA256** to derive deterministic seeds:
- `job_seed = HMAC(master_key, job_id|window|tier|secret_epoch)`
- `pkg_seed = HMAC(job_seed, package_id)`

Then we select canaries + spot indices deterministically from `pkg_seed`.

### 2) Dispute (why it matters)
If duplication or spot checks find a mismatch:
- we re-execute a larger fraction (default 10%),
- run a one-sided binomial test,
- and decide **accept** or **reject+slash**.

This makes the policy explainable in plain language:
> “We only slash if a neutral 10% re-exec shows enough mismatches to reject the hypothesis that error rate ≤ 1% at 99% confidence.”

### 3) Detection power (why we show it)
Judges and teammates often ask:
> “How likely is it that cheating gets caught?”

The `detection_power.py` script prints a small table for ε = 0.5%, 1%, 2% under your current policy.
This is an easy slide or README artifact that makes your QC policy feel grounded.

