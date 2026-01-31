from __future__ import annotations

from math import exp
from typing import Dict, Iterable, Tuple

from app.services.qc.sampling import load_policy, compute_count


def detect_prob_spot(eps: float, n_spot: int) -> float:
    # P(detect) = 1 - (1 - eps) ** n_spot
    return 1.0 - (1.0 - eps) ** n_spot


def detect_prob_canary(eps: float, n_can: int) -> float:
    return 1.0 - (1.0 - eps) ** n_can


def detect_prob_total(eps: float, n_spot: int, n_can: int, dup_rate: float) -> float:
    """
    Approx detection probability for a single package.

    Assumptions (fine for demo slides):
    - Duplication catches any mismatch (prob ~ 1 if eps > 0).
    - Spot + canary checks are independent.
    """
    p_spot = detect_prob_spot(eps, n_spot)
    p_can = detect_prob_canary(eps, n_can)
    p_nondup = 1.0 - (1.0 - p_spot) * (1.0 - p_can)
    return dup_rate + (1.0 - dup_rate) * p_nondup


def detection_table(
    *,
    eps_values: Iterable[float],
    n_items: int,
    policy: Dict,
) -> Tuple[Dict[float, float], Dict[str, int]]:
    defaults = policy["defaults"]
    dup_rate = defaults["dup_rate"]
    n_can = compute_count(n_items, defaults["canary_rate"], defaults["min_canaries_per_pkg"])
    n_spot = compute_count(n_items, defaults["spot_rate"], defaults["min_spot_items_per_pkg"])

    table = {}
    for eps in eps_values:
        table[eps] = detect_prob_total(eps, n_spot, n_can, dup_rate)

    counts = {"n_items": n_items, "n_can": n_can, "n_spot": n_spot, "dup_rate": dup_rate}
    return table, counts


def main() -> None:
    policy = load_policy()
    eps_values = [0.005, 0.01, 0.02]
    n_items = 100_000

    table, counts = detection_table(
        eps_values=eps_values,
        n_items=n_items,
        policy=policy,
    )

    print("QC Detection Power Table")
    print(f"Assumptions: n_items={counts['n_items']}, n_can={counts['n_can']}, n_spot={counts['n_spot']}, dup_rate={counts['dup_rate']}")
    print("")
    for eps, p in table.items():
        print(f"eps={eps:.3%}  ->  P(detect) ≈ {p:.3%}")


if __name__ == "__main__":
    main()

