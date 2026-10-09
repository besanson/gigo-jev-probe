"""Paper 6 corpora against the registration text (prereg/p6-v1.1.md §5.1, §5.2, §5.4, §5.5)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from experiments import constants_p6 as k
from experiments import corpus_p6 as c
from experiments.sensors_p6 import llm_object, llm_prompt

ROOT = Path(__file__).resolve().parents[1]
PREREG = (ROOT / "prereg" / "p6-v1.1.md").read_text(encoding="utf-8")


def section(start: str, end: str) -> str:
    return PREREG[PREREG.index(start):PREREG.index(end)]


def bank_rows(text: str) -> dict[tuple[str, str], tuple[list[str], list[str]]]:
    rows = {}
    for line in text.splitlines():
        cells = [x.strip() for x in line.strip().strip("|").split("|")]
        if len(cells) == 4 and cells[0].startswith("`") and "/" in cells[2]:
            field, value = cells[0].strip("`"), cells[1].strip("`")
            rows[(field, value)] = (re.findall(r"`([^`]+)`", cells[2]), re.findall(r"`([^`]+)`", cells[3]))
    return rows


@pytest.fixture(scope="module")
def e1_items():
    return c.build_e1_items()


@pytest.fixture(scope="module")
def e2_items():
    return c.build_e2_items()


def test_e1_banks_verbatim() -> None:
    reg = bank_rows(section("**Statement banks `[F12]`.**", "**Noise.**"))
    assert len(reg) == 5
    for (field, value), (val, test) in reg.items():
        key = (field, "recorded" if value.startswith("recorded") else value)
        assert list(k.E1_BANKS[key][0]) == val and list(k.E1_BANKS[key][1]) == test


def test_e2_banks_verbatim() -> None:
    reg = bank_rows(section("sensed statement. `[F12]` Validation and test banks are disjoint", "Noise and labels as E1"))
    assert len(reg) == 8
    for key, (val, test) in reg.items():
        assert list(k.E2_BANKS[key][0]) == val and list(k.E2_BANKS[key][1]) == test


@pytest.mark.parametrize("banks", [k.E1_BANKS, k.E2_BANKS])
def test_validation_and_test_banks_are_disjoint(banks) -> None:
    val = {p for v, _ in banks.values() for p in v}
    test = {p for _, t in banks.values() for p in t}
    assert not val & test


def test_jev_questions_verbatim() -> None:
    table = section("| field | value | question id | instructions (verbatim) |", "`<d>` is written as an ISO date")
    for (field, value), (qid, text) in k.JEV_QUESTIONS.items():
        if value.startswith("recorded:"):
            d = value.split(":", 1)[1]
            generic = "Does this record state that an approval for this change was recorded on `<d>`?"
            assert generic in table and text == generic.replace("`<d>`", d)
            assert qid == "Q_appr_" + d.replace("-", "")
        else:
            assert f"`{qid}` | {text} |" in table
    assert len([q for q in k.JEV_QUESTIONS if q[0] == "approval_assertion"]) == 8


def test_llm_prompt_and_tasks_verbatim() -> None:
    block = section("**Claude Haiku 4.5.**", "`{object}` is rendered")
    assert k.LLM_PROMPT.replace("\n\nRecord:\n", "") in block.replace("\n\nRecord:\n<rendered record text>", "")
    for task in k.LLM_TASKS.values():
        assert f"| {task} |" in block
    assert k.llm_keys("E1", "approval_assertion") == ("p_not_recorded", "p_2026_06_01", "p_2026_06_15",
                                                      "p_2026_07_01", "p_2026_07_15", "p_2026_08_01", "p_2026_08_15")
    assert k.llm_keys("E2", "approval_assertion") == ("p_recorded", "p_not_recorded")
    assert llm_object("E1", "data_residency_region") == (
        '{"p_us": <number between 0 and 1>, "p_eu": <number between 0 and 1>, "p_apac": <number between 0 and 1>}')
    prompt = llm_prompt("E2.1", "branch", "TEXT")
    assert prompt.startswith("You are reading one change-management record. Report only what the record states: which")
    assert prompt.endswith("No code fences. No text after the object.\n\nRecord:\nTEXT")


def test_registered_seeds_and_dates() -> None:
    for seed in ("20261101", "20261102", "20261103", "20261104", "20261106", "20261107"):
        assert seed in PREREG
    assert (k.E1_SAMPLE_SEED, k.E1_SPLIT_SEED, k.E1_CORPUS_SEED, k.BOOTSTRAP_SEED, k.E2_CORPUS_SEED,
            k.SPLIT_AB_SEED) == (20261101, 20261102, 20261103, 20261104, 20261106, 20261107)
    assert "`D = {2026-06-01, 2026-06-15, 2026-07-01, 2026-07-15, 2026-08-01, 2026-08-15}`" in PREREG
    assert [k.iso(d) for d in k.APPROVAL_DATES] == ["2026-06-01", "2026-06-15", "2026-07-01", "2026-07-15",
                                                    "2026-08-01", "2026-08-15"]
    assert k.CAP_USD == 60.0 and k.CEILING == 0.01 and k.CEILING_E3 == 0.05


def test_e1_items_and_splits(e1_items) -> None:
    assert len(e1_items) == 1000
    parts = {p: [it for it in e1_items if it.part == p] for p in ("A", "B", "test")}
    assert [len(parts[p]) for p in ("A", "B", "test")] == [150, 150, 700]
    assert all(it.split == "validation" for p in "AB" for it in parts[p])
    assert c.e1_model().contract == k.E1_CONTRACT


def test_e2_items_reuse_jev_v2(e2_items) -> None:
    from jev_probe.corpus_v2 import build_items

    v2 = build_items()
    assert [(it.i, it.split) for it in e2_items] == [(it.i, it.split) for it in v2]
    assert sum(it.part == "A" for it in e2_items) == 150


def test_e1_assertion_derives_the_true_token(e1_items) -> None:
    for it in e1_items:
        assertion, request_date = c.e1_truth(it)
        assert c.approval_token_from_assertion(assertion, request_date) == it.t.approval_token


def test_token_derivation_rules() -> None:
    from datetime import date

    assert c.approval_token_from_assertion(None, date(2026, 7, 1)) is None
    assert c.approval_token_from_assertion("not_recorded", date(2026, 7, 1)) == "absent"
    assert c.approval_token_from_assertion("recorded:2026-06-01", date(2026, 7, 1)) == "valid"
    assert c.approval_token_from_assertion("recorded:2026-06-01", date(2026, 7, 2)) == "expired"
    assert c.approval_token_from_assertion("recorded:2026-06-01", date(2026, 5, 31)) == "expired"


def test_documents_use_the_split_bank_and_carry_no_property_value(e1_items) -> None:
    for it in e1_items[:200]:
        text = c.render(it, "n00")
        lines = text.splitlines()
        assert lines[0].startswith("Change request CR-") and lines[1].startswith("Submitted: 2026-05-")
        own = [p for b in k.E1_BANKS.values() for p in b[0 if it.split == "validation" else 1]]
        other = [p for b in k.E1_BANKS.values() for p in b[1 if it.split == "validation" else 0]]

        def matches(line: str, templates: list[str]) -> bool:
            pats = [re.escape(t).replace(r"\{", "{").replace(r"\}", "}") for t in templates]
            return any(re.fullmatch(re.sub(r"\{[a-z]+\}", ".+", pat), line) for pat in pats)

        assert len(lines) == 5
        assert all(matches(line, own) and not matches(line, other) for line in lines[3:])
        # recorded contract fields with distinctive values ("approved" and "standard" also occur as ordinary words
        # in the registered phrases and filler, so workflow_stage and evidence_retention_class are not checked)
        for prop in ("delegated_role", "network_zone", "destination_endpoint_class"):
            assert getattr(it.t, prop) not in text


def test_noise_is_nested_and_labels_follow_the_text(e1_items) -> None:
    for it in e1_items[:300]:
        for f in k.E1_FIELDS:
            kinds = [c.perturbation(it, f, n, None) for n in ("n00", "n10", "n30")]
            assert kinds[0] == "none"
            if kinds[1] != "none":
                assert kinds[2] == kinds[1]
            labs = c.assertion_labels(it, f, "n30")
            truth = c.truth_values(it)[f]
            if kinds[2] == "none":
                assert [v for v, y in labs.items() if y] == [truth]
            elif kinds[2] == "missing":
                assert not any(labs.values())
            else:
                assert labs[truth] and sum(labs.values()) == 2
                assert c.draws(it)["noise"][f]["comment"] in c.render(it, "n30")


def test_e2_documents_and_truth(e2_items) -> None:
    it = next(x for x in e2_items if x.split == "test")
    for arm in (1, 2):
        truth = c.truth_values(it, arm)
        assert set(truth) == {"approval_assertion", k.E2_ARMS[arm]["sensed"]}
        text = c.render(it, "n00", arm)
        assert len(text.splitlines()) == 5
    assert c.sensed_sets(1) == {"R_branch": ["approval_assertion", "branch"], "R_env": ["approval_assertion"]}
    assert c.sensed_sets(2) == {"R_branch": ["approval_assertion"], "R_env": ["approval_assertion", "environment"]}


def test_outcomes_agree_with_the_true_verdict(e1_items, e2_items) -> None:
    for it in e1_items[:50]:
        assert c.e1_outcome(it, c.truth_values(it)) == (False, False)
        assert c.e1_outcome(it, {"approval_assertion": None, "data_residency_region": "us"})[1] is False
    for it in e2_items[:50]:
        for arm in (1, 2):
            for r in k.E2_REDUCTS:
                assert c.e2_outcome(it, r, c.truth_values(it, arm)) == (False, False)


def test_generation_is_deterministic(e1_items) -> None:
    it = e1_items[5]
    c._draw_e1_cached.cache_clear()
    first = c.render(it, "n30")
    c._draw_e1_cached.cache_clear()
    assert c.render(it, "n30") == first
