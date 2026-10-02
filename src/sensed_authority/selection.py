"""Sensing-aware selection (prereg/p6-v1.1.md §3 S2, §5.5; finding F6).

The objective is the estimated S1 bound, sum over sensed fields of (ê_i + û_i), with the
split-B Clopper-Pearson upper bounds as estimates. S2 guarantees it does not increase when a
sensed field is removed from a nested set; nothing is claimed for non-nested sets.

`observation_costs` expresses the same objective as the per-property cost mapping that the
pinned paper 5 compiler accepts (`authority_compiler.derive_authority_contract`, or its
`synthesis.find_minimum_cost_contract`), so no new solver and no change to the sibling are
needed. Two details make that mapping exact (round-two finding F6):

- Names. A sensed field and the contract property it feeds can differ: the sensor reads the
  assertion `approval_assertion`, and the contract reads `approval_token`, derived from it.
  `SENSED_TO_CONTRACT` maps each sensed field to its contract property, so the property is
  charged the field's (ê + û). Without the map the property would carry no sensing cost.
- Tie-break. The compiler requires strictly positive costs, so every property also carries a
  floor. The floor is not a fixed constant: `lexicographic_floor` sets it below half the
  smallest positive gap between any two sums of the sensed-field terms, divided by the number
  of properties. A contract's compiler cost is then  B̂(C) + floor * |C|  with
  floor * |C| < gap / 2, so the compiler orders contracts by estimated bound first and, only
  among contracts with exactly equal estimated bounds, by fewer properties. The floor can
  never reverse an order set by the estimated bound. The registered tie-breaks of §5.5
  (fewer sensed fields, then name) are applied by `select`, not by the solver.
"""

from __future__ import annotations

import itertools
import math
from collections.abc import Iterable, Mapping, Sequence

FLOOR = 1e-6  # used only when every sum of sensed-field terms is equal (no gap to stay under)
SENSED_TO_CONTRACT: dict[str, str] = {"approval_assertion": "approval_token"}

def estimated_bound(sensed_fields: Iterable[str], estimates: Mapping[str, tuple[float, float]]) -> float:
    """sum over sensed fields of (ê_i + û_i). estimates: field -> (ê_i, û_i)."""
    return math.fsum(estimates[f][0] + estimates[f][1] for f in sensed_fields)


def is_nested(smaller: Iterable[str], larger: Iterable[str]) -> bool:
    return set(smaller) <= set(larger)


def select(candidates: Mapping[str, Sequence[str]], estimates: Mapping[str, tuple[float, float]]) -> str:
    """The registered rule: the candidate (name -> sensed fields) with the smallest estimated
    bound; ties go to fewer sensed fields, then to the name in ascending order."""
    if not candidates:
        raise ValueError("no candidate contracts")
    return min(candidates, key=lambda name: (estimated_bound(candidates[name], estimates),
                                              len(set(candidates[name])), name))


def lexicographic_floor(terms: Iterable[float], n_properties: int, default: float = FLOOR) -> float:
    """A floor small enough that floor * n_properties stays below half the smallest positive
    difference between any two subset sums of `terms` (the sensed-field costs), so it only
    breaks exact ties of the estimated bound."""
    terms = list(terms)
    sums = sorted({math.fsum(c) for r in range(len(terms) + 1) for c in itertools.combinations(terms, r)})
    gaps = [b - a for a, b in zip(sums, sums[1:]) if b - a > 0]
    if not gaps or n_properties <= 0:
        return default
    return min(default, min(gaps) / (2.0 * (n_properties + 1)))


def observation_costs(candidate_properties: Iterable[str], sensed_fields: Iterable[str],
                      estimates: Mapping[str, tuple[float, float]], floor: float | None = None,
                      aliases: Mapping[str, str] | None = None) -> dict[str, float]:
    """Per-property costs for the paper 5 compiler: (ê_i + û_i) of the sensed field a property is
    read from, plus the lexicographic floor; the floor alone for a recorded property.
    `aliases` maps a sensed field to its contract property (default `SENSED_TO_CONTRACT`)."""
    properties = sorted(set(candidate_properties))
    aliases = SENSED_TO_CONTRACT if aliases is None else aliases
    term: dict[str, float] = {}
    for f in sorted(set(sensed_fields)):
        target = f if f in properties else aliases.get(f, f)
        if target not in properties:
            raise ValueError(f"sensed field {f!r} maps to {target!r}, which is not a candidate property")
        term[target] = term.get(target, 0.0) + estimated_bound([f], estimates)
    if floor is None:
        floor = lexicographic_floor(term.values(), len(properties))
    if not floor > 0:
        raise ValueError("the compiler requires strictly positive costs")
    return {p: floor + term.get(p, 0.0) for p in properties}
