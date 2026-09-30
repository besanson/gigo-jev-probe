"""Sensing-aware selection (prereg/p6-v1.1.md §3 S2, §5.5; finding F6).

The objective is the estimated S1 bound, sum over sensed fields of (ê_i + û_i), with the
split-B Clopper-Pearson upper bounds as estimates. S2 guarantees it does not increase when a
sensed field is removed from a nested set; nothing is claimed for non-nested sets.

`observation_costs` expresses the same objective as the per-property cost mapping that the
pinned paper 5 compiler (`authority_compiler.derive_authority_contract`) accepts, so no new
solver and no change to the sibling are needed. The compiler requires every cost to be
strictly positive, so each property carries a floor `FLOOR`; the floor adds `FLOOR * |C|` to
a contract's cost and is far below any estimated bound (a one-sided 95% upper bound on 150
items is at least 0.0198). The registered tie-breaks (fewer sensed fields, then name) are
applied by `select`, not by the solver.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence

FLOOR = 1e-6


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


def observation_costs(candidate_properties: Iterable[str], sensed_fields: Iterable[str],
                      estimates: Mapping[str, tuple[float, float]], floor: float = FLOOR) -> dict[str, float]:
    """Per-property costs for the paper 5 compiler: floor + (ê_i + û_i) for a sensed field,
    floor for a recorded one."""
    if not floor > 0:
        raise ValueError("the compiler requires strictly positive costs")
    sensed = set(sensed_fields)
    return {p: floor + (estimated_bound([p], estimates) if p in sensed else 0.0)
            for p in sorted(set(candidate_properties))}
