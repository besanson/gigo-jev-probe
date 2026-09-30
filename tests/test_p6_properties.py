"""Paper 6 property tests (hypothesis): S1, S2 (nested) and S3 on random models and distributions."""

from __future__ import annotations

import itertools

from hypothesis import given, settings
from hypothesis import strategies as st

from sensed_authority.admission import _binom_cdf, cp_upper, fit_value_thresholds, within_ceiling
from sensed_authority.bound import ContractModel, exposure, is_deny_ward, s1_bound
from sensed_authority.selection import estimated_bound

TOL = 1e-12


@st.composite
def model_and_joint(draw):
    n = draw(st.integers(1, 3))
    fields = tuple(f"f{i}" for i in range(n))
    values = tuple(range(draw(st.integers(2, 3))))
    cube = [dict(zip(fields, v, strict=True)) for v in itertools.product(values, repeat=n)]
    reach = draw(st.lists(st.sampled_from(cube), min_size=1, max_size=len(cube), unique_by=lambda t: tuple(t.values())))
    table = {tuple(t.values()): draw(st.sampled_from(("allow", "deny"))) for t in reach}
    model = ContractModel(fields, reach, lambda t: table[tuple(t.values())], {f: values for f in fields})
    sensed = tuple(f for f in fields if draw(st.booleans()))
    outcomes = [(t, dict(zip(sensed, o, strict=True)))
                for t in reach for o in itertools.product(*((*values, None) for _ in sensed))]
    weights = draw(st.lists(st.floats(0, 1), min_size=len(outcomes), max_size=len(outcomes)))
    total = sum(weights)
    joint = [(w / total, t, o) for w, (t, o) in zip(weights, outcomes, strict=True)] if total > 0 else \
        [(1.0, outcomes[0][0], outcomes[0][1])]
    return model, sensed, joint


@settings(max_examples=300, deadline=None)
@given(model_and_joint())
def test_s1_holds_for_random_distributions(case) -> None:
    model, sensed, joint = case
    ex = exposure(model, sensed, joint)
    b = s1_bound(ex.rates)
    assert ex.change <= b.change + TOL
    assert ex.unsafe <= b.unsafe + TOL


@settings(max_examples=300, deadline=None)
@given(model_and_joint())
def test_s3_deny_ward_means_no_unsafe_change(case) -> None:
    model, sensed, joint = case
    if is_deny_ward(model, sensed):
        assert exposure(model, sensed, joint).unsafe == 0.0


@given(st.dictionaries(st.sampled_from("abcdef"), st.tuples(st.floats(0, 0.5), st.floats(0, 0.5)), min_size=1),
       st.data())
def test_s2_nested_sets_are_monotone(rates, data) -> None:
    larger = data.draw(st.lists(st.sampled_from(sorted(rates)), unique=True))
    smaller = [f for f in larger if data.draw(st.booleans())]
    assert estimated_bound(smaller, rates) <= estimated_bound(larger, rates) + TOL


@given(st.integers(1, 200), st.data())
def test_cp_upper_is_an_upper_bound_and_monotone(n, data) -> None:
    k = data.draw(st.integers(0, n))
    ub = cp_upper(k, n)
    assert k / n <= ub <= 1.0
    if k < n:
        assert cp_upper(k + 1, n) >= ub
        assert _binom_cdf(k, n, ub) <= 0.05 + 1e-9


@given(st.lists(st.tuples(st.one_of(st.none(), st.floats(0, 1)), st.booleans()), max_size=60),
       st.sampled_from([0.0, 0.01, 0.05, 0.2]))
def test_fitted_thresholds_meet_the_ceiling_on_split_a(rows, ceiling) -> None:
    tau_true, tau_false = fit_value_thresholds(rows, ceiling)
    neg = [s for s, y in rows if s is not None and not y]
    pos = [s for s, y in rows if s is not None and y]
    assert within_ceiling(sum(s >= tau_true for s in neg), len(neg), ceiling)
    assert within_ceiling(sum(s <= tau_false for s in pos), len(pos), ceiling)
