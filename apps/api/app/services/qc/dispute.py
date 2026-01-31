from __future__ import annotations

from math import comb


def binom_cdf(k: int, n: int, p: float) -> float:
    # Naive CDF; OK for demo sizes. Replace with scipy for large n.
    if k < 0:
        return 0.0
    if k >= n:
        return 1.0
    return sum(comb(n, i) * (p**i) * ((1 - p) ** (n - i)) for i in range(k + 1))


def accepts(eps0: float, alpha: float, x: int, n: int) -> bool:
    # Accept if we cannot reject H0: eps <= eps0 at significance alpha.
    return binom_cdf(x, n, eps0) >= alpha


def decision(x: int, n: int, eps0: float = 0.01, alpha: float = 0.01) -> str:
    return "reject_slash" if not accepts(eps0, alpha, x, n) else "accept"

