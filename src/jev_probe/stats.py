"""Stdlib statistics used by the §6–§8 analysis."""

from __future__ import annotations

import math
from collections.abc import Sequence


def wilson(k: int, n: int, z: float = 1.959963984540054) -> tuple[float, float]:
    if n == 0:
        return (math.nan, math.nan)
    p = k / n
    den = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return (max(0.0, centre - half), min(1.0, centre + half))


def norm_sf(x: float) -> float:
    return 0.5 * math.erfc(x / math.sqrt(2.0))


def two_sided_normal_p(z: float) -> float:
    return min(1.0, 2.0 * norm_sf(abs(z)))


def binom_cdf(k: int, n: int, p: float = 0.5) -> float:
    return sum(math.comb(n, i) * p**i * (1 - p) ** (n - i) for i in range(0, k + 1))


def mcnemar_exact(b: int, c: int) -> float:
    """Exact two-sided McNemar: binomial test on the discordant pairs."""
    n = b + c
    if n == 0:
        return 1.0
    return min(1.0, 2.0 * binom_cdf(min(b, c), n))


def holm(pvalues: Sequence[float]) -> list[float]:
    m = len(pvalues)
    order = sorted(range(m), key=lambda i: pvalues[i])
    adj = [0.0] * m
    running = 0.0
    for rank, i in enumerate(order):
        running = max(running, min(1.0, (m - rank) * pvalues[i]))
        adj[i] = running
    return adj


def quantile(xs: Sequence[float], q: float) -> float:
    """Linear-interpolation quantile (numpy's default 'linear' method)."""
    if not xs:
        return math.nan
    s = sorted(xs)
    pos = (len(s) - 1) * q
    lo = math.floor(pos)
    hi = math.ceil(pos)
    return s[lo] + (s[hi] - s[lo]) * (pos - lo)


def sd(xs: Sequence[float]) -> float:
    n = len(xs)
    if n < 2:
        return math.nan
    m = sum(xs) / n
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (n - 1))


def bootstrap_p_centered(estimate: float, draws: Sequence[float]) -> float:
    """Two-sided bootstrap p for H0: parameter = 0, from the null-shifted distribution."""
    if estimate == 0:
        return 1.0
    extreme = sum(1 for d in draws if abs(d - estimate) >= abs(estimate))
    return (1 + extreme) / (1 + len(draws))


def fleiss_kappa(table: Sequence[Sequence[int]]) -> float | None:
    """Fleiss' kappa for rows of category counts (equal raters per row). None if undefined."""
    rows = [r for r in table if sum(r) > 1]
    if not rows:
        return None
    n = sum(rows[0])
    big_n = len(rows)
    k = len(rows[0])
    p_j = [sum(r[j] for r in rows) / (big_n * n) for j in range(k)]
    p_i = [(sum(x * x for x in r) - n) / (n * (n - 1)) for r in rows]
    p_bar = sum(p_i) / big_n
    p_e = sum(p * p for p in p_j)
    if p_e >= 1.0:
        return None
    return (p_bar - p_e) / (1 - p_e)
