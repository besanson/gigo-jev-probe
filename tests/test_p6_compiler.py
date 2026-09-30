"""The selection objective drives the pinned paper 5 compiler unchanged (prereg/p6-v1.1.md §3 S2).

`observation_costs` is passed to `authority_compiler.derive_authority_contract` from
sarc-authority-derivation at its engines.lock pin; the compiler's minimum-cost reduct must agree
with `select`. Not part of the mutation run (it needs the sibling checkout beside the repo).
"""

from __future__ import annotations

import itertools
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

import pytest

import preflight
from sensed_authority.selection import observation_costs, select

ROOT = Path(__file__).resolve().parents[1]
LOCK = tomllib.loads((ROOT / "engines.lock").read_text(encoding="utf-8"))["sarc-authority-derivation"]
SIBLING = (ROOT / LOCK["path"]).resolve()


@dataclass(frozen=True)
class T:
    approval_assertion: str
    branch: str
    environment: str
    operation: str


PAIRING = {"main": "production", "staging": "staging", "feature": "development"}
REACHABLE = [T(a, b, PAIRING[b], op) for a in ("recorded", "not_recorded") for b in PAIRING for op in ("read", "deploy")]
LOSSES = {
    "production_deploy_without_approval": lambda t: t.operation == "deploy" and t.environment == "production"
    and t.approval_assertion == "not_recorded",
}
CONTEXT = {"approval_assertion": ["recorded", "not_recorded"], "branch": list(PAIRING),
           "environment": list(PAIRING.values()), "operation": ["read", "deploy"]}


@pytest.fixture(scope="module")
def compiler():
    assert preflight.check_pin(names=("sarc-authority-derivation",)) is None, "sibling not at its pin"
    for p in (str(SIBLING / "src"), str(SIBLING)):
        if p not in sys.path:
            sys.path.insert(0, p)
    from authority_compiler import derive_authority_contract

    return derive_authority_contract


@pytest.mark.parametrize("sensed_second,expected", [("branch", "R_env"), ("environment", "R_branch")])
def test_compiler_minimum_cost_reduct_matches_select(compiler, sensed_second, expected) -> None:
    estimates = {"approval_assertion": (0.03, 0.02), sensed_second: (0.02, 0.01)}
    sensed = ["approval_assertion", sensed_second]
    costs = observation_costs(CONTEXT, sensed, estimates)
    contract = compiler(LOSSES, REACHABLE, CONTEXT, costs)
    candidates = {"R_branch": [f for f in ("approval_assertion", "branch") if f in sensed],
                  "R_env": [f for f in ("approval_assertion", "environment") if f in sensed]}
    picked = select(candidates, estimates)
    assert picked == expected
    chosen = set(contract.minimum_cost_reduct)
    assert chosen == {"approval_assertion", "operation", "branch" if picked == "R_branch" else "environment"}


def test_both_reducts_are_sufficient_in_the_toy_domain(compiler) -> None:
    contract = compiler(LOSSES, REACHABLE, CONTEXT)
    reducts = {frozenset(r) for r in contract.minimal_reducts}
    assert reducts == {frozenset({"approval_assertion", "operation", "branch"}),
                       frozenset({"approval_assertion", "operation", "environment"})}
    assert len(list(itertools.product(*CONTEXT.values()))) > len(REACHABLE)
