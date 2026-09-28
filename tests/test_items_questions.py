"""§2 item frame, §3 views/state and §4 question payload, checked against the registration."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from pydantic_core import to_json
from sarc_dq.taxonomy.classes import TAXONOMY_V0

from jev_probe import analysis
from jev_probe.adapter import request_body
from jev_probe.constants import CONTEXT
from jev_probe.items import build_items, class_for_position, eligible_indices
from jev_probe.questions import QUESTION_IDS, QUESTIONS, noul_questions

PREREG = (Path(__file__).resolve().parents[1] / "prereg" / "jev-v1.md").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def items():
    return build_items()


def test_frame_matches_registration(items) -> None:
    assert eligible_indices() == list(range(0, 900, 3))
    assert [it.i for it in items] == list(range(0, 900, 3))
    assert [it.j for it in items] == list(range(300))
    assert all(it.cls is None for it in items[:100])
    for j in range(100, 300):
        assert items[j].cls == TAXONOMY_V0[(j - 100) % 8].name == class_for_position(j)
    counts = {c.name: sum(it.cls == c.name for it in items) for c in TAXONOMY_V0}
    assert set(counts.values()) == {25}


def test_analysis_class_order_is_taxonomy_order() -> None:
    assert analysis.CLASSES == tuple(c.name for c in TAXONOMY_V0)
    assert all(analysis.class_at(j) == class_for_position(j) for j in range(300))


def test_state_is_registered_and_never_carries_ground_truth(items) -> None:
    m = re.search(r'\{"context": "([^"]+)",', PREREG)
    assert m and m.group(1) == CONTEXT
    for it in items:
        for cond in ("P", "PM"):
            st = it.state(cond)
            assert list(st) == ["context", "evidence"] and st["context"] == CONTEXT
            text = json.dumps(st)
            for leak in ("ground_truth", "corrupt", "true_unit_cost", "role", "observed_unit_cost"):
                assert leak not in text
        assert it.state("P")["evidence"] == [r.payload_view() for r in it.evidence]
        assert it.state("PM")["evidence"] == [r.full_view() for r in it.evidence]


def test_ground_truth_tags_match_assignment(items) -> None:
    for it in items:
        gt = it.evidence[0].ground_truth
        assert gt["corrupted"] is (it.cls is not None)
        assert gt["corruption_class"] == it.cls
        truth = it.truth()
        assert truth["Q0_valid"] is (it.cls is None)
        assert sum(truth.values()) == 1


def test_questions_are_verbatim_and_in_registered_order() -> None:
    rows = re.findall(r"^\| `(Q\w+)` \| (.+?) \| .+ \|$", PREREG, flags=re.M)
    assert tuple(rows) == QUESTIONS
    assert len(QUESTION_IDS) == 9


def test_request_body_shape() -> None:
    body = json.loads(request_body({"context": CONTEXT, "evidence": []}))
    assert list(body) == ["state", "model", "questions"]
    assert body["model"] == "jev-latest"
    assert list(body["questions"]) == list(QUESTION_IDS)
    for qid, text in QUESTIONS:
        assert body["questions"][qid] == {"type": "noul", "instructions": text}  # no criteria
    assert json.loads(to_json(noul_questions())) == body["questions"]
