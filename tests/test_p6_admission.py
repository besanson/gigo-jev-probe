"""Paper 6 admission policy (prereg/p6-v1.1.md §5.2; F2, F8, F11)."""

from __future__ import annotations

import json
import math

import pytest

from sensed_authority import admission as ad
from sensed_authority.admission import (
    FieldEstimate,
    _binom_cdf,
    admit,
    cp_upper,
    estimate_field,
    fit_field_thresholds,
    fit_value_thresholds,
    freeze_policy,
    load_policy,
    map_score,
    within_ceiling,
)


def test_constants() -> None:
    assert ad.UNKNOWN_VERDICT == "deny"
    assert ad.CP_ALPHA == 0.05
    assert ad.DIGITS == 12


def test_within_ceiling_is_exact() -> None:
    assert within_ceiling(1, 100, 0.01)
    assert not within_ceiling(2, 100, 0.01)
    assert within_ceiling(0, 0, 0.01)
    assert within_ceiling(3, 300, 0.01) and not within_ceiling(4, 300, 0.01)
    assert within_ceiling(5, 100, 0.05) and not within_ceiling(6, 100, 0.05)


def test_fit_thresholds_on_the_assertion_label() -> None:
    # 100 records not asserting v score 0.00, 0.01, ..., 0.99; 100 asserting v score 0.500, 0.505, ..., 0.995.
    neg = [(i / 100, False) for i in range(100)]
    pos = [(0.5 + i / 200, True) for i in range(100)]
    tau_true, tau_false = fit_value_thresholds(neg + pos, 0.01)
    # at most 1 of 100 negatives may score >= tau_true: candidate 0.985 admits only 0.99; 0.98 admits two
    assert tau_true == 0.985
    # at most 1 of 100 positives may score <= tau_false: 0.5 catches one positive; 0.505 catches two
    assert tau_false == 0.5


def test_fit_thresholds_candidates_beyond_the_range() -> None:
    rows = [(0.2, False), (0.2, True)]
    tau_true, tau_false = fit_value_thresholds(rows, 0.0)
    assert tau_true == pytest.approx(1.2) and tau_false == pytest.approx(-0.8)


def test_fit_thresholds_one_sided_samples() -> None:
    assert fit_value_thresholds([(0.3, True), (0.7, True)], 0.01) == (0.3, -0.7)
    assert fit_value_thresholds([(0.3, False), (0.7, False)], 0.01) == (1.7, 0.7)


def test_invalid_rows_excluded_and_empty() -> None:
    assert fit_value_thresholds([(None, True), (None, False)], 0.01) == (math.inf, -math.inf)
    assert fit_value_thresholds([(None, False), (0.4, True), (0.9, False)], 0.0) == (1.9, -0.6)


def test_fit_field_thresholds_sorted_by_value() -> None:
    got = fit_field_thresholds({"b": [(0.9, True)], "a": [(0.1, False)]}, 0.01)
    assert list(got) == ["a", "b"]
    assert got["b"] == fit_value_thresholds([(0.9, True)], 0.01)


@pytest.mark.parametrize("score,expected", [(None, "unknown"), (0.8, "true"), (0.9, "true"), (0.2, "false"),
                                            (0.1, "false"), (0.5, "unknown")])
def test_map_score(score, expected) -> None:
    assert map_score(score, (0.8, 0.2)) == expected


def test_admit_exactly_one_true() -> None:
    taus = {"a": (0.8, 0.2), "b": (0.8, 0.2), "c": (0.8, 0.2)}
    assert admit({"a": 0.9, "b": 0.1, "c": 0.5}, taus) == "a"
    assert admit({"a": 0.9, "b": 0.85, "c": 0.1}, taus) is None
    assert admit({"a": 0.5, "b": 0.1, "c": None}, taus) is None
    assert admit({"a": None, "b": None, "c": 0.8}, taus) == "c"
    with pytest.raises(ValueError, match="different values"):
        admit({"a": 0.9}, taus)


def test_binom_cdf_edges_and_values() -> None:
    assert _binom_cdf(0, 5, 0.0) == 1.0
    assert _binom_cdf(5, 5, 1.0) == 1.0 and _binom_cdf(4, 5, 1.0) == 0.0
    assert _binom_cdf(0, 3, 0.5) == pytest.approx(0.125)
    assert _binom_cdf(1, 3, 0.5) == pytest.approx(0.5)
    assert _binom_cdf(2, 3, 0.5) == pytest.approx(0.875)
    assert _binom_cdf(1, 4, 0.2) == pytest.approx(0.8 ** 4 + 4 * 0.2 * 0.8 ** 3)


@pytest.mark.parametrize("k,n,expected", [(0, 150, 1 - 0.05 ** (1 / 150)), (1, 10, 0.39416),
                                          (0, 10, 0.25887), (9, 10, 0.99488)])
def test_cp_upper_known_values(k: int, n: int, expected: float) -> None:
    assert cp_upper(k, n) == pytest.approx(expected, abs=5e-5)


@pytest.mark.parametrize("k,n", [(1, 10), (3, 50), (7, 150), (40, 150)])
def test_cp_upper_solves_the_tail_equation(k: int, n: int) -> None:
    ub = cp_upper(k, n)
    assert k / n < ub < 1
    assert _binom_cdf(k, n, ub) == pytest.approx(0.05, abs=1e-9)


def test_cp_upper_edges_and_alpha() -> None:
    assert cp_upper(0, 0) == 1.0 and cp_upper(10, 10) == 1.0
    assert cp_upper(0, 150) == 1 - 0.05 ** (1 / 150)
    assert cp_upper(2, 20, alpha=0.10) < cp_upper(2, 20) < cp_upper(2, 20, alpha=0.01)
    for bad in [(-1, 5), (6, 5)]:
        with pytest.raises(ValueError):
            cp_upper(*bad)


def test_estimate_field_against_truth() -> None:
    pairs = [("eu", "eu")] * 145 + [("us", "eu")] * 2 + [(None, "eu")] * 3
    est = estimate_field(pairs)
    assert (est.n, est.wrong, est.unknown) == (150, 2, 3)
    assert est.e_hat == cp_upper(2, 150) and est.u_hat == cp_upper(3, 150)
    zero = estimate_field([("a", "a")] * 10)
    assert (zero.wrong, zero.unknown) == (0, 0) and zero.e_hat == cp_upper(0, 10)
    alt = estimate_field(pairs, alpha=0.10)
    assert alt.e_hat == cp_upper(2, 150, 0.10)


def test_freeze_and_load_roundtrip() -> None:
    thresholds = {"residency": {"us": (0.9, 0.1), "eu": (math.inf, -math.inf)}}
    estimates = {"residency": {"n30": FieldEstimate(150, 1, 2, 1 / 3, 0.25)}}
    inputs = {"split": "A", "rows": [[0.1, True]]}
    text = freeze_policy(version="p6-v1.1/E1/jev", ceiling=0.01, thresholds=thresholds, estimates=estimates,
                         inputs=inputs)
    assert text.endswith("\n")
    body = json.loads(text)
    assert body["inputs_sha256"] == ad.sha256_text(ad.canonical_json(inputs))
    assert body["thresholds"]["residency"]["eu"] == {"tau_true": "inf", "tau_false": "-inf"}
    assert body["estimates"]["residency"]["n30"]["e_hat"] == round(1 / 3, 12)
    assert list(body["thresholds"]["residency"]) == ["eu", "us"]
    assert text == freeze_policy(version="p6-v1.1/E1/jev", ceiling=0.01, thresholds=thresholds,
                                 estimates=estimates, inputs=inputs)
    back = load_policy(text)
    assert back["thresholds"]["residency"]["eu"] == (math.inf, -math.inf)
    assert back["thresholds"]["residency"]["us"] == (0.9, 0.1)
    assert back["estimates"]["residency"]["n30"] == FieldEstimate(150, 1, 2, round(1 / 3, 12), 0.25)
    assert back["admission_policy_version"] == "p6-v1.1/E1/jev" and back["ceiling"] == 0.01
    other = freeze_policy(version="p6-v1.1/E1/jev", ceiling=0.01, thresholds=thresholds, estimates=estimates,
                          inputs={"split": "B"})
    assert json.loads(other)["inputs_sha256"] != body["inputs_sha256"]
