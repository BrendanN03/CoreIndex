from __future__ import annotations

import hmac
import hashlib
import os
import struct
from dataclasses import dataclass
from pathlib import Path
import json
from typing import List, Optional


def _hmac_sha256(key: bytes, msg: bytes) -> bytes:
    return hmac.new(key, msg, hashlib.sha256).digest()


def hmac_drbg(seed: bytes, counter: int) -> int:
    msg = struct.pack(">Q", counter)
    return int.from_bytes(_hmac_sha256(seed, msg), "big")


def derive_job_seed(
    *,
    master_key: bytes,
    job_id: str,
    window: str,
    tier: str,
    secret_epoch: str,
) -> bytes:
    material = f"{job_id}|{window}|{tier}|{secret_epoch}".encode("utf-8")
    return _hmac_sha256(master_key, material)


def derive_pkg_seed(job_seed: bytes, package_id: str) -> bytes:
    return _hmac_sha256(job_seed, package_id.encode("utf-8"))


def choose_indices(seed: bytes, population_size: int, k: int) -> List[int]:
    # Deterministic sampling without replacement.
    seen = set()
    out: List[int] = []
    counter = 0
    while len(out) < k and len(seen) < population_size:
        r = hmac_drbg(seed, counter)
        idx = r % population_size
        if idx not in seen:
            seen.add(idx)
            out.append(idx)
        counter += 1
    return out


def compute_count(n_items: int, rate: float, floor: int) -> int:
    return max(floor, int(round(n_items * rate)))


@dataclass(frozen=True)
class SamplingPlan:
    dup_selected: bool
    canary_indices: List[int]
    spot_indices: List[int]
    canary_count: int
    spot_count: int


def _policy_path() -> Path:
    return Path(__file__).resolve().parent / "policy" / "qc_policy.json"


def load_policy() -> dict:
    path = _policy_path()
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def plan_sampling(
    *,
    job_id: str,
    window: str,
    tier: str,
    package_id: str,
    n_items: int,
    secret_epoch: str,
    job_seed_hex: Optional[str] = None,
    policy: Optional[dict] = None,
) -> SamplingPlan:
    """
    Deterministic, provider-independent sampling plan.

    - dup_selected: whether this package is duplicated.
    - canary_indices: positions of canary items (buyer-prepared).
    - spot_indices: positions of spot-check items (neutral pool).
    """
    if n_items <= 0:
        raise ValueError("n_items must be > 0")

    policy = policy or load_policy()
    defaults = policy["defaults"]

    if job_seed_hex:
        job_seed = bytes.fromhex(job_seed_hex.removeprefix("0x"))
    else:
        master_key = os.environ.get("QC_MASTER_KEY", "dev_master_key").encode("utf-8")
        job_seed = derive_job_seed(
            master_key=master_key,
            job_id=job_id,
            window=window,
            tier=tier,
            secret_epoch=secret_epoch,
        )

    pkg_seed = derive_pkg_seed(job_seed, package_id)

    # Duplication decision: deterministic roll in [0, 1).
    dup_rate = defaults["dup_rate"]
    roll = hmac_drbg(pkg_seed, 0) / float(1 << 256)
    dup_selected = roll < dup_rate

    canary_count = compute_count(
        n_items, defaults["canary_rate"], defaults["min_canaries_per_pkg"]
    )
    spot_count = compute_count(
        n_items, defaults["spot_rate"], defaults["min_spot_items_per_pkg"]
    )

    canary_indices = choose_indices(pkg_seed, n_items, canary_count)
    spot_indices = choose_indices(pkg_seed, n_items, spot_count)

    return SamplingPlan(
        dup_selected=dup_selected,
        canary_indices=canary_indices,
        spot_indices=spot_indices,
        canary_count=canary_count,
        spot_count=spot_count,
    )

