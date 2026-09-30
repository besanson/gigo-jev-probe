"""jev-v3 on mock endpoints (no network): request shape, parser, arm health stops, carried arm,
τ gate and slot filling."""

from __future__ import annotations

import json
from pathlib import Path

import httpx2
import pytest

from jev_probe import analysis, analysis_v3, run_v3
from jev_probe.adapter_v3 import parse_llm_v3
from jev_probe.cache import Cache
from jev_probe.constants_v2 import LLM_MODEL
from jev_probe.constants_v3 import LLM_MAX_TOKENS, LLM_PROMPT_PREFIX
from jev_probe.corpus_v2 import build_items
from test_v2 import LLM_SENTINEL, FakeAPIs, do_run, fake_p

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def items():
    return build_items()


@pytest.fixture(scope="module")
def subset(items):  # the same subset as test_v2
    val = [it for it in items if it.split == "validation"][:20]
    test = [it for it in items if it.split == "test"][:30]
    return val + test


def _msg(text: str, stop: str = "end_turn") -> str:
    return json.dumps({"type": "message", "content": [{"type": "text", "text": text}], "stop_reason": stop})


class FakeLlm:
    """Arm-B endpoint. reply(i_record, text) -> reply text continuing after the prefill."""

    def __init__(self, reply=None) -> None:
        self.calls: list[httpx2.Request] = []
        self.headers: list[str] = []
        self.reply = reply or (lambda n, text: f'"p_valid": {round(fake_p(text), 4)}}}')

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.headers.append(request.headers.get("x-api-key", ""))
        if request.method == "GET":
            return httpx2.Response(200, json={"id": LLM_MODEL, "type": "model", "display_name": "Claude Haiku 4.5",
                                              "created_at": "2025-10-01T00:00:00Z"})
        self.calls.append(request)
        body = json.loads(request.content)
        text = body["messages"][0]["content"].split("Record:\n", 1)[1]
        return httpx2.Response(200, json={
            "id": "msg_1", "type": "message", "role": "assistant", "model": LLM_MODEL,
            "content": [{"type": "text", "text": self.reply(len(self.calls), text)}], "stop_reason": "end_turn",
            "stop_sequence": None, "usage": {"input_tokens": len(request.content) // 4, "output_tokens": 8}})


@pytest.fixture(scope="module")
def v2(tmp_path_factory, subset):
    """A complete jev-v2 run on the subset (mock endpoints), used as the carried arm-A cache."""
    tmp = tmp_path_factory.mktemp("v2carried")
    fakes = FakeAPIs()
    assert do_run(tmp, fakes, subset, committed=True) == "TAU_WRITTEN"
    assert do_run(tmp, fakes, subset) == "COMPLETE"
    return tmp


def v3_run(tmp: Path, v2dir: Path, llm: FakeLlm, items, *, committed: bool = True, **kw) -> str:
    return run_v3.run(llm_key=LLM_SENTINEL, cache_path=tmp / "c3.jsonl", manifest_path=tmp / "m3.json",
                      tau_path=tmp / "tau3.json", v2_cache_path=v2dir / "c.jsonl",
                      llm_transport=httpx2.MockTransport(llm), is_committed=lambda p: committed,
                      sleep=lambda s: None, items=items, check_design=False, log=lambda m: None, **kw)


def n_val(subset) -> int:
    return 3 * sum(it.split == "validation" for it in subset)


# ------------------------------------------------------------------ request and parser


def test_prompt_is_v2_plus_the_registered_sentence() -> None:
    assert "No code fences. No text after the object.\n\nRecord:\n" in LLM_PROMPT_PREFIX
    assert LLM_MAX_TOKENS == 32


def test_parser_v3() -> None:
    assert parse_llm_v3(_msg('"p_valid": 0.25}')) == 0.25                       # continuation after prefill
    assert parse_llm_v3(_msg('"p_valid": 0.9}\n\nThe record shows')) == 0.9      # trailing text ignored
    assert parse_llm_v3(_msg('\n```json\n{"p_valid": 0.4}\n```')) == 0.4          # fenced object after prefill
    assert parse_llm_v3(_msg('"p_valid": 1}')) == 1.0
    for bad in ('"p_valid": 1.5}', '"p_valid": true}', "no object", '"p_val', '"other": 0.5}'):
        assert parse_llm_v3(_msg(bad)) is None, bad
    assert parse_llm_v3(_msg('"p_valid": 0.5}', "refusal")) is None


# ------------------------------------------------------------------ full run


@pytest.fixture(scope="module")
def full(tmp_path_factory, v2, subset):
    tmp = tmp_path_factory.mktemp("v3")
    llm = FakeLlm()
    s1 = v3_run(tmp, v2, llm, subset, committed=False)
    s2 = v3_run(tmp, v2, llm, subset, committed=False)
    n_gate = len(llm.calls)
    s3 = v3_run(tmp, v2, llm, subset, limit=5)
    s4 = v3_run(tmp, v2, llm, subset)
    return tmp, llm, (s1, s2, s3, s4), n_gate


def test_run_order_gate_and_resume(full, subset) -> None:
    tmp, llm, statuses, n_gate = full
    assert statuses == ("TAU_WRITTEN", "TAU_NOT_COMMITTED", "PAUSED", "COMPLETE")
    assert n_gate == n_val(subset)
    assert len(llm.calls) == 3 * len(subset)  # arm B only, nothing repeated
    m = json.loads((tmp / "m3.json").read_text())
    assert m["health"]["smoke"] == {"invalid": 0, "n": 20, "stopped": False}
    assert m["health"]["validation"]["n"] == n_val(subset) and not m["health"]["validation"]["stopped"]
    assert json.loads((tmp / "tau3.json").read_text()).keys() == {"llm"}


def test_wire_body_is_the_registered_request(full) -> None:
    _, llm, *_ = full
    body = json.loads(llm.calls[0].content)
    assert body["model"] == LLM_MODEL and body["max_tokens"] == 32 and body["temperature"] == 0.0
    assert body["messages"][0]["role"] == "user" and body["messages"][0]["content"].startswith(LLM_PROMPT_PREFIX)
    assert body["messages"][1] == {"role": "assistant", "content": "{"}
    assert "system" not in body


def test_no_secret_is_written(full) -> None:
    tmp, llm, *_ = full
    assert LLM_SENTINEL in llm.headers
    for p in (tmp / "c3.jsonl", tmp / "m3.json", tmp / "tau3.json"):
        assert LLM_SENTINEL.encode() not in p.read_bytes(), p


def test_slots_fill_end_to_end(full, v2, subset) -> None:
    tmp, *_ = full
    slots = analysis_v3.compute(tmp / "c3.jsonl", tmp / "tau3.json", v2_cache_path=v2 / "c.jsonl",
                                v2_tau_path=v2 / "tau.json", items=subset, bootstrap_b=200)
    filled = analysis.fill(analysis_v3.build(), slots)
    assert "{{" not in filled
    assert slots["run.status"] == "COMPLETE" and slots["run.hypotheses_evaluated"] == "yes"
    assert slots["tau.llm.recomputed_match"] == "yes" and slots["invalid.llm"] == "0"
    for h in ("H2", "H3"):
        assert slots[f"{h}.verdict"] != analysis_v3.NE


def test_committed_template_matches_generator() -> None:
    assert (ROOT / "results" / "jev-v3.template.md").read_text(encoding="utf-8") == analysis_v3.build()


# ------------------------------------------------------------------ arm health stops


def test_smoke_check_stops_and_is_final(tmp_path: Path, v2, subset) -> None:
    llm = FakeLlm(reply=lambda n, text: "not json")
    assert v3_run(tmp_path, v2, llm, subset) == "ARM_INVALID"
    assert len(llm.calls) == 2 * 20  # 20 records, one re-request each, then stop
    m = json.loads((tmp_path / "m3.json").read_text())
    assert m["health"]["smoke"] == {"invalid": 20, "n": 20, "stopped": True}
    assert not (tmp_path / "tau3.json").exists()
    assert v3_run(tmp_path, v2, FakeLlm(), subset) == "ARM_INVALID"  # not resumable, no call
    assert len([r for r in Cache(tmp_path / "c3.jsonl").records() if r["kind"] == "attempt"]) == 40


def test_validation_health_check_stops_before_thresholds(tmp_path: Path, v2, subset) -> None:
    # Records 21..24 (after the smoke check) are invalid on both requests: 4 of 60 > 5%.
    def reply(n: int, text: str) -> str:
        return "garbage" if 21 <= n <= 28 else f'"p_valid": {round(fake_p(text), 4)}}}'

    llm = FakeLlm(reply=reply)
    assert v3_run(tmp_path, v2, llm, subset) == "ARM_INVALID"
    m = json.loads((tmp_path / "m3.json").read_text())
    assert m["health"]["smoke"]["stopped"] is False
    assert m["health"]["validation"] == {"invalid": 4, "n": n_val(subset), "stopped": True}
    assert not (tmp_path / "tau3.json").exists()
    assert {r["split"] for r in Cache(tmp_path / "c3.jsonl").records() if r["kind"] == "call"} == {"validation"}


def test_cap_stops_before_the_call(tmp_path: Path, v2, subset) -> None:
    llm = FakeLlm()
    assert v3_run(tmp_path, v2, llm, subset, cap_usd=0.0001) == "CAP_TRUNCATED"
    assert len(llm.calls) == 0


def test_carried_arm_must_be_complete(tmp_path: Path, v2, subset, items) -> None:
    extra = [it for it in items if it.split == "test" and it.i not in {s.i for s in subset}][:1]
    llm = FakeLlm()
    assert v3_run(tmp_path, v2, llm, list(subset) + extra) == "CARRIED_ARM_INCOMPLETE"
    assert len(llm.calls) == 0
