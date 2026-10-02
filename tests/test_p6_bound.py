"""Paper 6 bound, contract evaluation and S3 (prereg/p6-v1.1.md §1, §3; F1)."""

from __future__ import annotations

import pytest

from sensed_authority.bound import (
    Bound,
    ContractModel,
    Exposure,
    deny_ward_witness,
    exposure,
    is_deny_ward,
    s1_bound,
    single_field_deny_ward,
)

BOOL = (False, True)
CUBE = [{"f1": a, "f2": b} for a in BOOL for b in BOOL]


def and_model(reach=CUBE) -> ContractModel:
    return ContractModel(("f1", "f2"), reach, lambda t: "allow" if t["f1"] and t["f2"] else "deny",
                         {"f1": BOOL, "f2": BOOL})


def test_s1_bound_has_no_directional_term() -> None:
    b = s1_bound({"a": (0.1, 0.2), "b": (0.05, 0.0)})
    assert b == Bound(change=pytest.approx(0.35), unsafe=pytest.approx(0.15))
    assert s1_bound({}) == Bound(0.0, 0.0)


def test_s1_bound_uses_exact_summation() -> None:
    rates = {f"f{i}": (0.1, 0.0) for i in range(10)}
    assert s1_bound(rates).unsafe == 1.0
    assert s1_bound(rates).change == 1.0


@pytest.mark.parametrize("e,u", [(-0.1, 0.0), (0.0, -0.1), (1.1, 0.0), (0.0, 1.1), (0.6, 0.6)])
def test_s1_bound_rejects_non_probabilities(e, u) -> None:
    with pytest.raises(ValueError, match="probabilities"):
        s1_bound({"f": (e, u)})


def test_s1_bound_accepts_edges() -> None:
    assert s1_bound({"f": (1.0, 0.0)}).unsafe == 1.0
    assert s1_bound({"f": (0.0, 1.0)}).change == 1.0
    assert s1_bound({"f": (0.4, 0.6)}).change == 1.0


def test_insufficient_contract_rejected() -> None:
    with pytest.raises(ValueError, match="not sufficient"):
        ContractModel(("f1",), CUBE, lambda t: "allow" if t["f1"] and t["f2"] else "deny", {"f1": BOOL})


def test_evaluate_unknown_and_unreachable_deny() -> None:
    m = and_model([{"f1": False, "f2": False}, {"f1": True, "f2": True}])
    assert m.evaluate({"f1": True, "f2": True}) == "allow"
    assert m.evaluate({"f1": True, "f2": None}) == "deny"
    assert m.evaluate({"f1": True}) == "deny"
    assert m.evaluate({"f1": True, "f2": False}) == "deny"  # not reachable
    assert m.table == {(False, False): "deny", (True, True): "allow"}


def test_observe_keeps_recorded_fields_true() -> None:
    m = and_model()
    t = {"f1": True, "f2": False}
    assert m.observe(t, {"f2": True}) == {"f1": True, "f2": True}
    assert m.observe(t, {}) == t


@pytest.mark.parametrize("t,sensed,expected", [
    ({"f1": True, "f2": False}, {"f2": True}, (True, True)),
    ({"f1": True, "f2": True}, {"f2": None}, (True, False)),
    ({"f1": True, "f2": True}, {"f2": True}, (False, False)),
    ({"f1": False, "f2": False}, {"f2": True}, (False, False)),
    ({"f1": True, "f2": True}, {"f1": False}, (True, False)),
])
def test_outcome(t, sensed, expected) -> None:
    assert and_model().outcome(t, sensed) == expected


def test_exposure_exact() -> None:
    m = and_model()
    t = {"f1": True, "f2": False}
    joint = [(0.5, t, {"f2": True}), (0.25, t, {"f2": None}), (0.25, t, {"f2": False})]
    ex = exposure(m, ["f2"], joint)
    assert ex == Exposure(change=0.5, unsafe=0.5, rates={"f2": (0.5, 0.25)})
    b = s1_bound(ex.rates)
    assert ex.change <= b.change and ex.unsafe <= b.unsafe


def test_exposure_counts_fail_closed_as_change_not_unsafe() -> None:
    m = and_model()
    t = {"f1": True, "f2": True}
    ex = exposure(m, ["f1", "f2"], [(1.0, t, {"f1": False, "f2": True})])
    assert ex.change == 1.0 and ex.unsafe == 0.0
    assert ex.rates == {"f1": (1.0, 0.0), "f2": (0.0, 0.0)}


def test_deny_ward_global_versus_field_wise() -> None:
    # Reachable only (F,F) and (T,T): one wrong field lands off R and denies; two wrong fields allow.
    m = and_model([{"f1": False, "f2": False}, {"f1": True, "f2": True}])
    assert single_field_deny_ward(m, ["f1", "f2"])
    assert not is_deny_ward(m, ["f1", "f2"])
    t, sensed = deny_ward_witness(m, ["f1", "f2"])
    assert t == {"f1": False, "f2": False} and sensed == {"f1": True, "f2": True}
    assert is_deny_ward(m, ["f1"]) and is_deny_ward(m, [])


def test_deny_ward_or_contract_and_allow_only() -> None:
    or_model = ContractModel(("f1", "f2"), CUBE, lambda t: "allow" if t["f1"] or t["f2"] else "deny",
                             {"f1": BOOL, "f2": BOOL})
    assert not is_deny_ward(or_model, ["f1"])
    assert deny_ward_witness(or_model, ["f1"]) == ({"f1": False, "f2": False}, {"f1": True})
    always_deny = ContractModel(("f1", "f2"), CUBE, lambda t: "deny", {"f1": BOOL, "f2": BOOL})
    assert is_deny_ward(always_deny, ["f1", "f2"]) and single_field_deny_ward(always_deny, ["f1", "f2"])
    always_allow = ContractModel(("f1", "f2"), CUBE, lambda t: "allow", {"f1": BOOL, "f2": BOOL})
    assert is_deny_ward(always_allow, ["f1", "f2"])  # no deny tuple, nothing to flip


def test_deny_ward_implies_no_unsafe_outcome() -> None:
    m = and_model()
    assert is_deny_ward(m, []) and not is_deny_ward(m, ["f1"])
    assert not single_field_deny_ward(m, ["f1", "f2"])


def test_s2_does_not_imply_verdict_dominance() -> None:  # round-two finding F2
    """Nested sensed sets, identical readings: the smaller set can change a verdict the larger
    keeps. Reachable tuples have z = y; allow iff x = y. {x, z} senses only x; {x, y} senses both."""
    from sensed_authority.bound import ContractModel

    reach = [{"x": x, "y": y, "z": y} for x in (0, 1) for y in (0, 1)]
    verdict = lambda t: "allow" if t["x"] == t["y"] else "deny"  # noqa: E731
    small = ContractModel(("x", "z"), reach, verdict, {"x": (0, 1), "z": (0, 1)})
    large = ContractModel(("x", "y"), reach, verdict, {"x": (0, 1), "y": (0, 1)})
    t = {"x": 0, "y": 0, "z": 0}
    reading = {"x": 1, "y": 1}  # one joint misreading, shared by both contracts
    assert small.outcome(t, {"x": reading["x"]}) == (True, False)  # changes: allow -> deny
    assert large.outcome(t, reading) == (False, False)  # keeps the true verdict
