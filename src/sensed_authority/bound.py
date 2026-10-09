"""Exposure and the S1 bound (prereg/p6-v1.1.md §1, §3; findings F1, F5).

S1, as registered in v1.1, is an instantiation of union-bound reasoning:

    P(verdict change) <= sum_i (e_i + u_i)        P(deny -> allow) <= sum_i e_i

with e_i the probability that sensed field i is admitted with a wrong value and u_i the
probability that it is unknown. There is no directional term. S3's deny-ward condition is
global: it is checked over every reachable deny tuple and every joint combination of sensed
values, not field by field.
"""

from __future__ import annotations

import itertools
import math
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

Tuple_ = Mapping[str, Any]
Verdict = Callable[[Tuple_], str]


@dataclass(frozen=True)
class Bound:
    change: float
    unsafe: float


def s1_bound(rates: Mapping[str, tuple[float, float]]) -> Bound:
    """rates: sensed field -> (e_i, u_i)."""
    for f, (e, u) in rates.items():
        if not (0.0 <= e <= 1.0 and 0.0 <= u <= 1.0 and e + u <= 1.0 + 1e-12):
            raise ValueError(f"rates for {f} are not probabilities: e={e}, u={u}")
    return Bound(change=math.fsum(e + u for e, u in rates.values()),
                 unsafe=math.fsum(e for e, _ in rates.values()))


class ContractModel:
    """A sufficient contract over a finite reachable set, evaluated from observations."""

    def __init__(self, contract: Sequence[str], reachable: Sequence[Tuple_], verdict: Verdict,
                 domains: Mapping[str, Sequence[Any]]) -> None:
        self.contract = tuple(contract)
        self.reachable = [dict(t) for t in reachable]
        self.verdict = verdict
        self.domains = {f: tuple(domains[f]) for f in self.contract}
        table: dict[tuple[Any, ...], str] = {}
        for t in self.reachable:
            key = tuple(t[f] for f in self.contract)
            v = verdict(t)
            if table.setdefault(key, v) != v:
                raise ValueError(f"contract {self.contract} is not sufficient: {key} maps to both verdicts")
        self.table = table

    def evaluate(self, observations: Mapping[str, Any]) -> str:
        """g of any reachable tuple agreeing with the observations on the contract; deny if a
        field is unknown (None) or no reachable tuple agrees."""
        if any(observations.get(f) is None for f in self.contract):
            return "deny"
        return self.table.get(tuple(observations[f] for f in self.contract), "deny")

    def observe(self, t: Tuple_, sensed: Mapping[str, Any]) -> dict[str, Any]:
        """Recorded fields at their true values, sensed fields as admitted (None = unknown)."""
        return {f: (sensed[f] if f in sensed else t[f]) for f in self.contract}

    def outcome(self, t: Tuple_, sensed: Mapping[str, Any]) -> tuple[bool, bool]:
        """(verdict changed, deny -> allow) for true tuple t and admitted sensed values."""
        true_v = self.table[tuple(t[f] for f in self.contract)]
        got = self.evaluate(self.observe(t, sensed))
        return got != true_v, true_v == "deny" and got == "allow"


@dataclass(frozen=True)
class Exposure:
    change: float
    unsafe: float
    rates: dict[str, tuple[float, float]]


def exposure(model: ContractModel, sensed_fields: Sequence[str],
             joint: Iterable[tuple[float, Tuple_, Mapping[str, Any]]]) -> Exposure:
    """Exact exposure and per-field (e_i, u_i) under a joint distribution of
    (probability, true tuple, admitted sensed values)."""
    change, unsafe = [], []
    wrong: dict[str, list[float]] = {f: [] for f in sensed_fields}
    unknown: dict[str, list[float]] = {f: [] for f in sensed_fields}
    for p, t, sensed in joint:
        c, u = model.outcome(t, sensed)
        change.append(p * c)
        unsafe.append(p * u)
        for f in sensed_fields:
            a = sensed[f]
            unknown[f].append(p * (a is None))
            wrong[f].append(p * (a is not None and a != t[f]))
    rates = {f: (math.fsum(wrong[f]), math.fsum(unknown[f])) for f in sensed_fields}
    return Exposure(math.fsum(change), math.fsum(unsafe), rates)


def deny_ward_witness(model: ContractModel, sensed_fields: Sequence[str]) -> tuple[Tuple_, dict[str, Any]] | None:
    """S3's global condition. None if the configuration is deny-ward: for every reachable deny
    tuple and every joint assignment of sensed fields to any declared value, the contract
    evaluates to deny. Otherwise a witness (true tuple, sensed values) that turns deny into allow."""
    sensed_fields = tuple(sensed_fields)
    for t in model.reachable:
        if model.table[tuple(t[f] for f in model.contract)] != "deny":
            continue
        for combo in itertools.product(*(model.domains[f] for f in sensed_fields)):
            sensed = dict(zip(sensed_fields, combo, strict=True))
            if model.evaluate(model.observe(t, sensed)) == "allow":
                return t, sensed
    return None


def is_deny_ward(model: ContractModel, sensed_fields: Sequence[str]) -> bool:
    return deny_ward_witness(model, sensed_fields) is None


def single_field_deny_ward(model: ContractModel, sensed_fields: Sequence[str]) -> bool:
    """The field-by-field reading S3 does NOT use: each sensed field wrong alone, others true.
    Kept so the N6 (b) witness can show it is weaker than the global condition."""
    return all(deny_ward_witness(model, [f]) is None for f in sensed_fields)
