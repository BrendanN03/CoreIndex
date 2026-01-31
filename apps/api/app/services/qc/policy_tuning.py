from __future__ import annotations

import argparse
from typing import Dict, Iterable, List, Tuple

from app.services.qc.sampling import load_policy, compute_count


def detect_prob_spot(eps: float, n_spot: int) -> float:
    return 1.0 - (1.0 - eps) ** n_spot


def detect_prob_canary(eps: float, n_can: int) -> float:
    return 1.0 - (1.0 - eps) ** n_can


def detect_prob_total(eps: float, n_spot: int, n_can: int, dup_rate: float) -> float:
    p_spot = detect_prob_spot(eps, n_spot)
    p_can = detect_prob_canary(eps, n_can)
    p_nondup = 1.0 - (1.0 - p_spot) * (1.0 - p_can)
    return dup_rate + (1.0 - dup_rate) * p_nondup


def parse_floats(txt: str) -> List[float]:
    return [float(x.strip()) for x in txt.split(",") if x.strip()]


def compute_counts(n_items: int, canary_rate: float, spot_rate: float, policy: Dict) -> Tuple[int, int]:
    defaults = policy["defaults"]
    n_can = compute_count(n_items, canary_rate, defaults["min_canaries_per_pkg"])
    n_spot = compute_count(n_items, spot_rate, defaults["min_spot_items_per_pkg"])
    return n_can, n_spot


def main() -> None:
    parser = argparse.ArgumentParser(description="QC policy tuning table")
    parser.add_argument("--n-items", type=int, default=100_000)
    parser.add_argument("--eps", default="0.005,0.01,0.02")
    parser.add_argument("--dup-rates", default="0.02,0.05,0.10")
    parser.add_argument("--spot-rates", default="0.002,0.005,0.01")
    parser.add_argument("--canary-rate", type=float, default=None)
    args = parser.parse_args()

    policy = load_policy()
    defaults = policy["defaults"]

    eps_values = parse_floats(args.eps)
    dup_rates = parse_floats(args.dup_rates)
    spot_rates = parse_floats(args.spot_rates)
    canary_rate = args.canary_rate if args.canary_rate is not None else defaults["canary_rate"]

    print("QC Policy Tuning Table")
    print(f"n_items={args.n_items}, canary_rate={canary_rate}")
    print("")

    for dup_rate in dup_rates:
        for spot_rate in spot_rates:
            n_can, n_spot = compute_counts(args.n_items, canary_rate, spot_rate, policy)
            label = f"dup={dup_rate:.3f} spot={spot_rate:.3f} (n_can={n_can}, n_spot={n_spot})"
            print(label)
            for eps in eps_values:
                p = detect_prob_total(eps, n_spot, n_can, dup_rate)
                print(f"  eps={eps:.3%} -> P(detect) ≈ {p:.3%}")
            print("")


if __name__ == "__main__":
    main()

