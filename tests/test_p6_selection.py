"""Paper 6 selection objective (prereg/p6-v1.1.md §3 S2, §5.5; F6)."""

from __future__ import annotations

import pytest

from sensed_authority.selection import (
    FLOOR,
    SENSED_TO_CONTRACT,
    estimated_bound,
    is_nested,
    lexicographic_floor,
    observation_costs,
    select,
)

EST = {"approval_assertion": (0.03, 0.02), "branch": (0.01, 0.0), "environment": (0.0, 0.04)}


def test_estimated_bound() -> None:
    assert estimated_bound(["approval_assertion", "branch"], EST) == pytest.approx(0.06)
    assert estimated_bound([], EST) == 0.0
    assert estimated_bound(["environment"], EST) == pytest.approx(0.04)


def test_is_nested() -> None:
    assert is_nested(["a"], ["a", "b"]) and is_nested([], ["a"]) and is_nested(["a"], ["a"])
    assert not is_nested(["a", "c"], ["a", "b"])


def test_select_registered_arm_1() -> None:
    picked = select({"R_env": ["approval_assertion"], "R_branch": ["approval_assertion", "branch"]}, EST)
    assert picked == "R_env"


def test_select_by_bound_not_by_count() -> None:
    rates = {"a": (0.2, 0.0), "b": (0.001, 0.0), "c": (0.001, 0.0)}
    assert select({"one": ["a"], "two": ["b", "c"]}, rates) == "two"


def test_select_tie_breaks_fewer_sensed_then_name() -> None:
    rates = {"a": (0.1, 0.0), "b": (0.05, 0.0), "c": (0.05, 0.0), "d": (0.1, 0.0)}
    assert select({"x": ["b", "c"], "y": ["a"]}, rates) == "y"
    assert select({"z": ["a"], "y": ["d"]}, rates) == "y"
    assert select({"y": ["d"], "z": ["a"]}, rates) == "y"


def test_select_needs_candidates() -> None:
    with pytest.raises(ValueError, match="no candidate"):
        select({}, EST)


def test_observation_costs() -> None:
    costs = observation_costs(["repository", "branch", "approval_assertion"], ["approval_assertion", "branch"], EST)
    assert list(costs) == ["approval_assertion", "branch", "repository"]
    assert costs["repository"] == FLOOR
    assert costs["branch"] == pytest.approx(FLOOR + 0.01)
    assert costs["approval_assertion"] == pytest.approx(FLOOR + 0.05)
    assert all(c > 0 for c in costs.values())
    assert FLOOR == 1e-6


def test_observation_costs_floor_must_be_positive() -> None:
    for bad in (0.0, -1e-6):
        with pytest.raises(ValueError, match="strictly positive"):
            observation_costs(["a"], [], EST, floor=bad)
    assert observation_costs(["a"], [], EST, floor=0.5) == {"a": 0.5}


def test_cost_order_matches_the_estimated_bound() -> None:
    props = ["approval_assertion", "branch", "environment", "repository"]
    costs = observation_costs(props, ["approval_assertion", "branch"], EST)
    c1 = sum(costs[p] for p in ["approval_assertion", "repository", "environment"])
    c2 = sum(costs[p] for p in ["approval_assertion", "repository", "branch"])
    assert c1 < c2  # environment recorded costs the floor only


def test_alias_charges_the_contract_property_read_from_the_sensed_field() -> None:  # F6
    assert SENSED_TO_CONTRACT == {"approval_assertion": "approval_token"}
    costs = observation_costs(["approval_token", "branch", "repository"], ["approval_assertion", "branch"], EST)
    assert costs["approval_token"] == pytest.approx(costs["repository"] + 0.05)
    assert costs["branch"] == pytest.approx(costs["repository"] + 0.01)
    assert "approval_assertion" not in costs
    with pytest.raises(ValueError, match="not a candidate property"):
        observation_costs(["branch"], ["approval_assertion"], EST)
    with pytest.raises(ValueError, match="not a candidate property"):
        observation_costs(["branch"], ["approval_assertion"], EST, aliases={})


def test_lexicographic_floor_stays_below_half_the_smallest_gap() -> None:  # F6
    terms = [0.3, 0.3000001, 0.2]
    floor = lexicographic_floor(terms, 10)
    sums = sorted({0.0, 0.3, 0.3000001, 0.2, 0.6000001, 0.5, 0.5000001, 0.8000001})
    gap = min(b - a for a, b in zip(sums, sums[1:]))
    assert 0 < floor * 10 < gap / 2
    assert floor == pytest.approx(gap / 22, rel=1e-6)
    assert lexicographic_floor([], 5) == FLOOR
    assert lexicographic_floor([0.4, 0.4], 3) == min(FLOOR, 0.4 / 8)
    assert lexicographic_floor([0.1], 0) == FLOOR


def test_floor_never_reverses_the_bound_order_across_cardinalities() -> None:  # F6
    # a 2-property contract with the higher bound must still cost more than a 9-property one
    est = {"a": (0.10000001, 0.0), "b": (0.1, 0.0)}
    props = ["a", "b"] + [f"r{i}" for i in range(8)]
    costs = observation_costs(props, ["a", "b"], est)
    small = costs["a"] + costs["r0"]
    large = costs["b"] + sum(costs[f"r{i}"] for i in range(8))
    assert large < small
    tie = observation_costs(props, ["a"], {"a": (0.1, 0.0)})
    assert tie["a"] + tie["r0"] < tie["a"] + tie["r0"] + tie["r1"]  # exact ties go to fewer properties
