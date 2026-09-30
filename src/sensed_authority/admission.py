"""Admission policy (prereg/p6-v1.1.md §5.2; findings F2, F8, F11).

- Thresholds are fitted per (field, candidate value) on validation split A, against the
  ASSERTION label (what the document shows), at a false-positive ceiling ε. ε is a fitting
  target on split A, not a guarantee.
- A score maps to true / false / unknown. A field is admitted with value v only when exactly one
  candidate value maps to true; otherwise it is unknown, and unknown denies.
- On split B, against the TRUTH label, the wrong-admission rate e_i and the unknown rate u_i
  are estimated as one-sided 95% Clopper-Pearson upper bounds. These are the quantities the
  registered bounds are built from.
- The frozen policy is canonical JSON carrying the SHA-256 of its inputs.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction
from typing import Any

from sensed_authority.record import canonical_json, sha256_text

UNKNOWN_VERDICT = "deny"
DIGITS = 12
CP_ALPHA = 0.05


def within_ceiling(count: int, total: int, ceiling: float) -> bool:
    """count / total <= ceiling, decided exactly (no float rounding at the boundary)."""
    return total == 0 or Fraction(count, total) <= Fraction(str(ceiling))


def fit_value_thresholds(rows: Sequence[tuple[float | None, bool]], ceiling: float) -> tuple[float, float]:
    """(tau_true, tau_false) for one candidate value. rows: (score or None, assertion label).

    tau_true is the smallest candidate such that at most `ceiling` of the rows whose label is
    False score at least it; tau_false is the largest candidate such that at most `ceiling` of
    the rows whose label is True score at most it. Candidates are the distinct scores plus one
    value above the maximum and one below the minimum. Unscored (invalid) rows are excluded.
    """
    scored = [(s, y) for s, y in rows if s is not None]
    if not scored:
        return math.inf, -math.inf
    scores = sorted({s for s, _ in scored})
    negatives = [s for s, y in scored if not y]
    positives = [s for s, y in scored if y]
    tau_true = min(t for t in [*scores, scores[-1] + 1.0]
                   if within_ceiling(sum(s >= t for s in negatives), len(negatives), ceiling))
    tau_false = max(t for t in [scores[0] - 1.0, *scores]
                    if within_ceiling(sum(s <= t for s in positives), len(positives), ceiling))
    return tau_true, tau_false


def fit_field_thresholds(rows_by_value: Mapping[str, Sequence[tuple[float | None, bool]]],
                         ceiling: float) -> dict[str, tuple[float, float]]:
    return {v: fit_value_thresholds(rows, ceiling) for v, rows in sorted(rows_by_value.items())}


def map_score(score: float | None, tau: tuple[float, float]) -> str:
    if score is None:
        return "unknown"
    if score >= tau[0]:
        return "true"
    if score <= tau[1]:
        return "false"
    return "unknown"


def admit(scores: Mapping[str, float | None], taus: Mapping[str, tuple[float, float]]) -> str | None:
    """The admitted value, or None (unknown). Exactly one candidate must map to true."""
    if set(scores) != set(taus):
        raise ValueError(f"scores and thresholds cover different values: {sorted(scores)} vs {sorted(taus)}")
    true_values = [v for v in sorted(scores) if map_score(scores[v], taus[v]) == "true"]
    return true_values[0] if len(true_values) == 1 else None


def _binom_cdf(k: int, n: int, p: float) -> float:
    if p <= 0.0:
        return 1.0
    if p >= 1.0:
        return 1.0 if k >= n else 0.0
    lp, lq = math.log(p), math.log1p(-p)
    terms = [math.exp(math.lgamma(n + 1) - math.lgamma(i + 1) - math.lgamma(n - i + 1) + i * lp + (n - i) * lq)
             for i in range(k + 1)]
    return min(1.0, math.fsum(terms))


def cp_upper(k: int, n: int, alpha: float = CP_ALPHA) -> float:
    """One-sided (1 - alpha) Clopper-Pearson upper bound for k successes in n trials."""
    if not (0 <= k <= n):
        raise ValueError(f"need 0 <= k <= n, got k={k}, n={n}")
    if n == 0 or k == n:
        return 1.0
    if k == 0:
        return 1.0 - alpha ** (1.0 / n)
    lo, hi = k / n, 1.0
    for _ in range(200):
        mid = (lo + hi) / 2
        if _binom_cdf(k, n, mid) > alpha:
            lo = mid
        else:
            hi = mid
    return hi


@dataclass(frozen=True)
class FieldEstimate:
    n: int
    wrong: int
    unknown: int
    e_hat: float
    u_hat: float


def estimate_field(pairs: Sequence[tuple[str | None, str]], alpha: float = CP_ALPHA) -> FieldEstimate:
    """pairs: (admitted value or None, true value) on split B. Upper bounds against the truth."""
    n = len(pairs)
    wrong = sum(1 for admitted, truth in pairs if admitted is not None and admitted != truth)
    unknown = sum(1 for admitted, _ in pairs if admitted is None)
    return FieldEstimate(n, wrong, unknown, cp_upper(wrong, n, alpha), cp_upper(unknown, n, alpha))


def _enc(x: float) -> Any:
    if math.isinf(x):
        return "inf" if x > 0 else "-inf"
    return round(x, DIGITS)


def _dec(x: Any) -> float:
    return float(x)


def freeze_policy(*, version: str, ceiling: float, thresholds: Mapping[str, Mapping[str, tuple[float, float]]],
                  estimates: Mapping[str, Mapping[str, FieldEstimate]], inputs: Any) -> str:
    """Canonical JSON of a frozen policy. thresholds: field -> value -> (tau_true, tau_false);
    estimates: field -> noise level -> FieldEstimate; inputs: whatever the policy was fitted
    from (hashed, not stored)."""
    body = {
        "admission_policy_version": version,
        "ceiling": ceiling,
        "inputs_sha256": sha256_text(canonical_json(inputs)),
        "thresholds": {f: {v: {"tau_true": _enc(t[0]), "tau_false": _enc(t[1])} for v, t in sorted(vals.items())}
                       for f, vals in sorted(thresholds.items())},
        "estimates": {f: {lvl: {"n": e.n, "wrong": e.wrong, "unknown": e.unknown,
                                "e_hat": _enc(e.e_hat), "u_hat": _enc(e.u_hat)} for lvl, e in sorted(levels.items())}
                      for f, levels in sorted(estimates.items())},
    }
    return canonical_json(body) + "\n"


def load_policy(text: str) -> dict[str, Any]:
    body = json.loads(text)
    body["thresholds"] = {f: {v: (_dec(t["tau_true"]), _dec(t["tau_false"])) for v, t in vals.items()}
                          for f, vals in body["thresholds"].items()}
    body["estimates"] = {f: {lvl: FieldEstimate(e["n"], e["wrong"], e["unknown"], _dec(e["e_hat"]), _dec(e["u_hat"]))
                             for lvl, e in levels.items()} for f, levels in body["estimates"].items()}
    return body
