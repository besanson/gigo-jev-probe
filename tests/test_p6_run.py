"""Paper 6 runner and analysis on mock endpoints for both sensors (no network, no calls)."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import httpx2
import pytest

from conftest import BASE_URL, DOCS_OK, SENTINEL_KEY
from experiments import analysis_p6, run_p6
from experiments import constants_p6 as k
from experiments import corpus_p6 as c
from experiments.sensors_p6 import parse_jev_scores, parse_llm_scores
from jev_probe.analysis import SLOT_RE
from jev_probe.cache import Cache
from jev_probe.constants_v2 import LLM_MODEL

LLM_SENTINEL = "sk-ant-SENTINEL-must-never-appear-9876543210"
ROOT = Path(__file__).resolve().parents[1]

KEYWORDS = {
    "not_recorded": ("none recorded", "no approver", "No CAB", "No sign-off", "is empty", "Nobody"),
    "recorded": ("granted by", "approved by", "approval recorded", "Signed off", "recorded an approval",
                 "Approval entry"),
    "us": ("United States", "US data", "region: US"), "eu": ("European Union", "EU data", "region: EU"),
    "apac": ("Asia-Pacific", "APAC"), "main": ("main",), "staging": ("staging",), "feature": ("feature",),
    "production": ("production", "prod"), "development": ("development", "dev "),
}


def fake_score(value: str, record: str) -> float:
    if value.startswith("recorded:"):
        hit = value.split(":", 1)[1] in record
    else:
        hit = any(w in record for w in KEYWORDS[value])
    jitter = int(hashlib.sha256((value + record).encode()).hexdigest()[:6], 16) / 0xFFFFFF
    return round((0.85 if hit else 0.05) + 0.1 * jitter, 4)


QID_TO_VALUE = {qid: value for (_, value), (qid, _) in k.JEV_QUESTIONS.items()}
KEY_TO_VALUE = {k.llm_key(v): v for vals in k.FIELD_VALUES.values() for v in vals}


class Fakes:
    def __init__(self, llm_reply=None, jev_bad=None) -> None:
        self.jev_calls: list[httpx2.Request] = []
        self.llm_calls: list[httpx2.Request] = []
        self.headers: list[str] = []
        self.llm_reply = llm_reply
        self.jev_bad = jev_bad

    def jev(self, request: httpx2.Request) -> httpx2.Response:
        self.headers.append(request.headers.get("authorization", ""))
        if request.url.path == "/v1/models":
            return httpx2.Response(200, json={"models": [
                {"name": "jev-latest", "description": "d", "release_date": "2026-09-15"}]})
        self.jev_calls.append(request)
        body = json.loads(request.content)
        record = body["state"]["record"]
        answers = {qid: {"type": "noul", "noul": fake_score(QID_TO_VALUE[qid], record)} for qid in body["questions"]}
        if self.jev_bad and self.jev_bad(len(self.jev_calls)):
            answers = {}
        return httpx2.Response(200, json={"model": "jev-1.13.0", "answers": answers,
                                          "usage": {"input_tokens": len(request.content) // 4, "output_tokens": 1}})

    def llm(self, request: httpx2.Request) -> httpx2.Response:
        self.headers.append(request.headers.get("x-api-key", ""))
        if request.method == "GET":
            return httpx2.Response(200, json={"id": LLM_MODEL, "type": "model", "display_name": "Claude Haiku 4.5",
                                              "created_at": "2025-10-01T00:00:00Z"})
        self.llm_calls.append(request)
        body = json.loads(request.content)
        prompt = body["messages"][0]["content"]
        record = prompt.split("Record:\n", 1)[1]
        keys = re.findall(r'"(p_[a-z0-9_]+)": <number', prompt)
        reply = ", ".join(f'"{key}": {fake_score(KEY_TO_VALUE[key], record)}' for key in keys) + "}"
        if self.llm_reply:
            reply = self.llm_reply(len(self.llm_calls), reply)
        return httpx2.Response(200, json={
            "id": "msg_1", "type": "message", "role": "assistant", "model": LLM_MODEL,
            "content": [{"type": "text", "text": reply}], "stop_reason": "end_turn", "stop_sequence": None,
            "usage": {"input_tokens": len(request.content) // 4, "output_tokens": 30}})


def subset(items: list[c.Item], n_val: int = 8, n_test: int = 10) -> list[c.Item]:
    a = [it for it in items if it.part == "A"][:n_val]
    b = [it for it in items if it.part == "B"][:n_val]
    t = [it for it in items if it.part == "test"][:n_test]
    return a + b + t


@pytest.fixture(scope="module")
def items():
    return {"E1": subset(c.build_e1_items()), "E2": subset(c.build_e2_items())}


def run(tmp: Path, exp: str, fakes: Fakes, items, *, committed: bool = True, **kw) -> str:
    kw.setdefault("other_spend", 0.0)
    return run_p6.run(exp, jev_key=SENTINEL_KEY, jev_base_url=BASE_URL, llm_key=LLM_SENTINEL,
                      cache=tmp / f"p6-{exp}.jsonl", manifest=tmp / f"manifest-p6-{exp}.json",
                      tau=tmp / f"p6-{exp}.tau.json", prior_manifest=tmp / "manifest-p6-E1.json",
                      jev_transport=httpx2.MockTransport(fakes.jev), llm_transport=httpx2.MockTransport(fakes.llm),
                      docs_fetch=lambda: DOCS_OK, is_committed=lambda p: committed, sleep=lambda s: None,
                      items=items[exp], log=lambda m: None, **kw)


@pytest.fixture(scope="module")
def full(tmp_path_factory, items):
    tmp = tmp_path_factory.mktemp("p6")
    fakes = Fakes()
    statuses = {"E2-early": run(tmp, "E2", fakes, items)}
    n_before = len(fakes.jev_calls)
    statuses["E1"] = [run(tmp, "E1", fakes, items, committed=False), run(tmp, "E1", fakes, items, committed=False),
                      run(tmp, "E1", fakes, items, limit=5), run(tmp, "E1", fakes, items)]
    statuses["E2"] = [run(tmp, "E2", fakes, items), run(tmp, "E2", fakes, items)]
    return tmp, fakes, statuses, n_before


def n_calls(items, exp: str, splits=("validation", "test")) -> int:
    per_record = 2 * (1 if exp == "E1" else 2)  # fields x arms
    return sum(it.split in splits for it in items[exp]) * 3 * per_record


def test_order_gate_and_resume(full, items) -> None:
    tmp, fakes, statuses, n_before = full
    assert statuses["E2-early"] == "ORDER_VIOLATION" and n_before == 0
    assert statuses["E1"] == ["TAU_WRITTEN", "TAU_NOT_COMMITTED", "PAUSED", "COMPLETE"]
    assert statuses["E2"] == ["TAU_WRITTEN", "COMPLETE"]
    total = n_calls(items, "E1") + n_calls(items, "E2")
    assert len(fakes.jev_calls) == len(fakes.llm_calls) == total  # nothing repeated on resume
    man = json.loads((tmp / "manifest-p6-E1.json").read_text())
    assert man["health"]["smoke.jev"] == {"invalid": 0, "n": 20, "stopped": False}
    assert man["health"]["validation.llm"]["n"] == n_calls(items, "E1", ("validation",))  # per sensor
    assert man["design_facts"]["A"]["items"] == 8


def test_registered_call_order(full) -> None:
    tmp, *_ = full
    calls = [r for r in Cache(tmp / "p6-E1.jsonl").records() if r["kind"] == "call"]
    order = [(r["split"] != "validation", r["i"], r["noise"], ("jev", "llm").index(r["arm"]),
              k.E1_FIELDS.index(r["field"])) for r in calls]
    assert order == sorted(order)
    for r in calls:
        assert r["exp"] == "E1"


def test_wire_bodies_are_registered(full) -> None:
    _, fakes, *_ = full
    body = json.loads(fakes.llm_calls[0].content)
    assert body["model"] == LLM_MODEL and body["temperature"] == 0.0 and body["max_tokens"] == 128
    assert body["messages"][1] == {"role": "assistant", "content": "{"} and "system" not in body
    assert body["messages"][0]["content"].startswith(
        "You are reading one change-management record. Report only what the record states: whether it states")
    assert json.loads(fakes.llm_calls[1].content)["max_tokens"] == 64
    jev = json.loads(fakes.jev_calls[0].content)
    assert set(jev["questions"]) == {"Q_appr_none", "Q_appr_20260601", "Q_appr_20260615", "Q_appr_20260701",
                                     "Q_appr_20260715", "Q_appr_20260801", "Q_appr_20260815"}
    assert jev["model"] == "jev-latest"


def test_no_secret_is_written(full) -> None:
    tmp, fakes, *_ = full
    assert f"Bearer {SENTINEL_KEY}" in fakes.headers and LLM_SENTINEL in fakes.headers
    for p in tmp.iterdir():
        data = p.read_bytes()
        assert SENTINEL_KEY.encode() not in data and LLM_SENTINEL.encode() not in data, p


def test_tau_files(full) -> None:
    tmp, *_ = full
    e1 = json.loads((tmp / "p6-E1.tau.json").read_text())
    pol = e1["sensors"]["jev"]["policy"]
    assert set(pol["thresholds"]) == set(k.E1_FIELDS) and pol["ceiling"] == 0.01
    assert set(pol["estimates"]) == {"E1|approval_assertion", "E1|data_residency_region"}
    assert set(e1["sensors"]["llm"]["bounds"]) == {"n00", "n10", "n30"}
    e2 = json.loads((tmp / "p6-E2.tau.json").read_text())
    picks = e2["sensors"]["jev"]["picks"]
    assert picks["E2.1"]["picked"] == "R_env" and picks["E2.2"]["picked"] == "R_branch"


def test_analysis_fills_every_slot(full, items) -> None:
    tmp, *_ = full
    slots = analysis_p6.compute(caches={e: tmp / f"p6-{e}.jsonl" for e in ("E1", "E2")},
                                taus={e: tmp / f"p6-{e}.tau.json" for e in ("E1", "E2")}, items=items,
                                bootstrap_b=200)
    template = analysis_p6.build()
    missing = sorted(set(SLOT_RE.findall(template)) - set(slots))
    assert missing == []
    filled = analysis_p6.fill_all(template, slots)
    assert "{{" not in filled and analysis_p6.NE not in filled
    assert slots["hypotheses_evaluated"] == "yes"
    assert slots["E1.tau_recomputed_match"] == slots["E2.tau_recomputed_match"] == "yes"
    assert slots["E4.check_passes"] == "yes"
    assert slots["H1.verdict"].startswith(("not refuted", "refuted"))
    assert slots["E3.eps1.deny.jev.n00.coverage"] == "1.0000"


def test_committed_template_matches_generator() -> None:
    assert (ROOT / "results" / "p6.template.md").read_text(encoding="utf-8") == analysis_p6.build()


def test_unevaluated_experiments_read_not_evaluated(tmp_path: Path) -> None:
    slots = analysis_p6.compute(caches={e: tmp_path / f"{e}.jsonl" for e in ("E1", "E2")},
                                taus={e: tmp_path / f"{e}.tau.json" for e in ("E1", "E2")}, bootstrap_b=10)
    filled = analysis_p6.fill_all(analysis_p6.build(), slots)
    assert "{{" not in filled and slots["hypotheses_evaluated"] == "no" and slots["E1.status"] == "none"


# ------------------------------------------------------------------ hard stops


def test_smoke_check_stops_jev(tmp_path: Path, items) -> None:
    fakes = Fakes(jev_bad=lambda n: True)
    assert run(tmp_path, "E1", fakes, items) == "ARM_INVALID"
    # 20 Jev calls, each requested twice (one re-request), interleaved with Haiku's calls
    assert len(fakes.jev_calls) == 2 * k.SMOKE_CALLS
    assert run(tmp_path, "E1", Fakes(), items) == "ARM_INVALID"  # final
    assert not (tmp_path / "p6-E1.tau.json").exists()


def test_validation_health_check_stops_haiku(tmp_path: Path, items) -> None:
    # Haiku invalid on both requests of calls 21..32: 6 of the validation calls, above 5% of 96.
    fakes = Fakes(llm_reply=lambda n, r: "garbage" if 41 <= n <= 52 else r)
    assert run(tmp_path, "E1", fakes, items) == "ARM_INVALID"
    man = json.loads((tmp_path / "manifest-p6-E1.json").read_text())
    assert man["health"]["smoke.llm"]["stopped"] is False
    assert man["health"]["validation.llm"]["stopped"] is True
    assert not (tmp_path / "p6-E1.tau.json").exists()


def test_cap_stops_before_the_call(tmp_path: Path, items) -> None:
    fakes = Fakes()
    assert run(tmp_path, "E1", fakes, items, cap_usd=0.0001) == "CAP_TRUNCATED"
    assert fakes.llm_calls == []


def test_cap_counts_other_experiments(tmp_path: Path, items) -> None:
    fakes = Fakes()
    assert run(tmp_path, "E1", fakes, items, other_spend=59.9999999) == "CAP_TRUNCATED"


# ------------------------------------------------------------------ parsers


def test_parsers() -> None:
    def msg(text: str, stop: str = "end_turn") -> str:
        return json.dumps({"type": "message", "stop_reason": stop, "content": [{"type": "text", "text": text}]})

    field = "data_residency_region"
    assert parse_llm_scores(msg('"p_us": 0.9, "p_eu": 0.1, "p_apac": 0}'), "E1", field) == {
        "us": 0.9, "eu": 0.1, "apac": 0.0}
    assert parse_llm_scores(msg('\n```json\n{"p_us": 0.2, "p_eu": 0.7, "p_apac": 0.1}\n```'), "E1", field) == {
        "us": 0.2, "eu": 0.7, "apac": 0.1}
    for bad in ('"p_us": 0.9, "p_eu": 0.1, "p_apac": true}', '"p_us": 0.9, "p_eu": 0.1}',
                '"p_us": 1.5, "p_eu": 0.1, "p_apac": 0}', "no object"):
        assert parse_llm_scores(msg(bad), "E1", field) is None, bad
    assert parse_llm_scores(msg('"p_us": 0.9, "p_eu": 0.1, "p_apac": 0}', "refusal"), "E1", field) is None
    jev = json.dumps({"answers": {"Q_branch_main": {"type": "noul", "noul": 0.7},
                                  "Q_branch_staging": {"type": "noul", "noul": 0.1},
                                  "Q_branch_feature": {"type": "noul", "noul": 0.2}}})
    assert parse_jev_scores(jev, "E2.1", "branch") == {"main": 0.7, "staging": 0.1, "feature": 0.2}
    assert parse_jev_scores(jev.replace('"noul": 0.2', '"noul": 2'), "E2.1", "branch") is None
