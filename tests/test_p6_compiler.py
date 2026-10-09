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
from experiments.constants_p6 import E2_REDUCTS  # imported before the sibling joins sys.path
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


@pytest.fixture(scope="module")
def ch_b1():
    """Paper 5's own CH-B1 inputs at the pin: candidate properties, reachable tuples, losses."""
    for path in (str(SIBLING / "src"), str(SIBLING)):
        if path not in sys.path:
            sys.path.append(path)
    from domain_v4 import CANDIDATE_PROPERTIES_V4, executable_reachable_tuples_v4
    from losses_v4 import load_loss_registry_v4
    from synthesis import find_minimum_cost_contract

    return CANDIDATE_PROPERTIES_V4, executable_reachable_tuples_v4(), load_loss_registry_v4(), find_minimum_cost_contract


@pytest.mark.parametrize("sensor", ["jev", "llm"])
@pytest.mark.parametrize("label, second", [("E2.1", "branch"), ("E2.2", "environment")])
def test_compiler_pick_equals_direct_pick_on_ch_b1(ch_b1, sensor, label, second) -> None:  # F6
    import json

    props, reachable, losses, find_min_cost = ch_b1
    tau = json.loads((ROOT / "results" / "p6-E2.tau.json").read_text(encoding="utf-8"))["sensors"][sensor]
    est = {f: (tau["policy"]["estimates"][f"{label}|{f}"]["n30"]["e_hat"],
               tau["policy"]["estimates"][f"{label}|{f}"]["n30"]["u_hat"]) for f in ("approval_assertion", second)}
    costs = observation_costs(props, ["approval_assertion", second], est)
    chosen = set(find_min_cost(props, reachable, losses, costs))
    compiler_pick = next(r for r, fields in E2_REDUCTS.items() if set(fields) == chosen)
    assert compiler_pick == tau["picks"][label]["picked"]
