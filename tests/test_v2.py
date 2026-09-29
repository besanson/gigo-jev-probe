"""jev-v2 Phase B on mock endpoints (no network): corpus, thresholds, the τ commit gate,
resume, retries, cap, secrets, and slot filling."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import httpx2
import pytest

from conftest import BASE_URL, DOCS_OK, SENTINEL_KEY
from jev_probe import analysis, analysis_v2, run_v2, template_v2
from jev_probe.adapter import RunStop
from jev_probe.adapter_v2 import LlmArm, Spend, parse_llm
from jev_probe.cache import Cache
from jev_probe.constants_v2 import DESIGN_FACTS, JEV_QID, LLM_MODEL
from jev_probe.corpus_v2 import (
    ABSENT_BANK,
    FILLER_BANK,
    VALID_BANK,
    build_items,
    design_facts,
    keyword_score,
    perturbation,
    render,
)

ROOT = Path(__file__).resolve().parents[1]
LLM_SENTINEL = "sk-ant-SENTINEL-must-never-appear-9876543210"


@pytest.fixture(scope="module")
def items():
    return build_items()


@pytest.fixture(scope="module")
def subset(items):
    val = [it for it in items if it.split == "validation"][:20]
    test = [it for it in items if it.split == "test"][:30]
    return val + test


# ------------------------------------------------------------------ fakes


def fake_p(text: str) -> float:
    """Deterministic pseudo-score with signal: high for valid statements, mid when ambiguous."""
    h = int(hashlib.sha256(text.encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
    return {1.0: 0.85, 0.0: 0.1, 0.5: 0.5}[keyword_score(text)] + 0.1 * h


class FakeAPIs:
    def __init__(self, jev_script=None, llm_script=None, llm_reply=None) -> None:
        self.jev_calls: list[httpx2.Request] = []
        self.llm_calls: list[httpx2.Request] = []
        self.jev_script = list(jev_script or [])
        self.llm_script = list(llm_script or [])
        self.llm_reply = llm_reply
        self.headers: list[str] = []

    def jev(self, request: httpx2.Request) -> httpx2.Response:
        self.headers.append(request.headers.get("authorization", ""))
        if request.url.path == "/v1/models":
            return httpx2.Response(200, json={"models": [
                {"name": "jev-latest", "description": "d", "release_date": "2026-09-15"}]})
        self.jev_calls.append(request)
        if self.jev_script:
            return self.jev_script.pop(0)(request)
        text = json.loads(request.content)["state"]["record"]
        return httpx2.Response(200, json={"model": "jev-1.13.0",
                                          "answers": {JEV_QID: {"type": "noul", "noul": fake_p(text)}},
                                          "usage": {"input_tokens": len(request.content) // 4, "output_tokens": 1}})

    def llm(self, request: httpx2.Request) -> httpx2.Response:
        self.headers.append(request.headers.get("x-api-key", ""))
        if request.method == "GET":
            return httpx2.Response(200, json={"id": LLM_MODEL, "type": "model", "display_name": "Claude Haiku 4.5",
                                              "created_at": "2025-10-01T00:00:00Z"})
        self.llm_calls.append(request)
        if self.llm_script:
            return self.llm_script.pop(0)(request)
        body = json.loads(request.content)
        text = body["messages"][0]["content"].split("Record:\n", 1)[1]
        reply = self.llm_reply if self.llm_reply is not None else json.dumps({"p_valid": round(fake_p(text), 4)})
        return httpx2.Response(200, json={
            "id": "msg_1", "type": "message", "role": "assistant", "model": LLM_MODEL,
            "content": [{"type": "text", "text": reply}], "stop_reason": "end_turn", "stop_sequence": None,
            "usage": {"input_tokens": len(request.content) // 4, "output_tokens": 12}})


def do_run(tmp: Path, fakes: FakeAPIs, items, *, committed: bool = True, **kw) -> str:
    return run_v2.run(jev_key=SENTINEL_KEY, jev_base_url=BASE_URL, llm_key=LLM_SENTINEL,
                      cache_path=tmp / "c.jsonl", manifest_path=tmp / "m.json", tau_path=tmp / "tau.json",
                      jev_transport=httpx2.MockTransport(fakes.jev), llm_transport=httpx2.MockTransport(fakes.llm),
                      docs_fetch=lambda: DOCS_OK, is_committed=lambda p: committed, sleep=lambda s: None,
                      items=items, check_design=False, log=lambda m: None, **kw)


# ------------------------------------------------------------------ corpus


def test_design_facts_match_registration(items) -> None:
    assert design_facts(items) == DESIGN_FACTS


def test_corpus_is_deterministic_nested_and_complete(items) -> None:
    for it in items[:200]:
        assert render(it, "n30") == render(it, "n30")
        kinds = [perturbation(it, n) for n in ("n00", "n10", "n30")]
        assert kinds[0] == "none"
        if kinds[1] != "none":
            assert kinds[2] == kinds[1]  # nested: perturbed at 10% implies perturbed at 30%
        text = render(it, "n00")
        assert keyword_score(text) == (1.0 if it.truth == "valid" else 0.0)
        if kinds[2] == "missing":
            assert keyword_score(render(it, "n30")) == 0.5
        if kinds[2] == "contradictory":
            assert keyword_score(render(it, "n30")) == 0.5
    assert not any("approv" in f.lower() for f in FILLER_BANK)
    assert len(FILLER_BANK) == 8 and len(VALID_BANK) == 3 and len(ABSENT_BANK) == 3


# ------------------------------------------------------------------ thresholds


def test_tau_respects_ceiling_and_maps_unknown() -> None:
    rows = [(0.9, True)] * 50 + [(0.2, False)] * 50 + [(0.6, False)] + [(0.4, True)]
    tau = analysis_v2.set_tau(rows, ceiling=0.01)
    assert tau["tau_true"] > 0.6 and tau["tau_false"] < 0.4
    assert analysis_v2.map_score(0.95, tau) == "true"
    assert analysis_v2.map_score(0.1, tau) == "false"
    assert analysis_v2.map_score(0.5, tau) == "unknown"
    assert analysis_v2.map_score(None, tau) == "unknown"


def test_llm_reply_must_be_the_registered_object() -> None:
    def msg(text: str, stop: str = "end_turn") -> str:
        return json.dumps({"content": [{"type": "text", "text": text}], "stop_reason": stop})

    assert parse_llm(msg('{"p_valid": 0.7}')) == 0.7
    assert parse_llm(msg('```json\n{"p_valid": 0.7}\n```')) is None
    assert parse_llm(msg('{"p_valid": 1.2}')) is None
    assert parse_llm(msg('{"p_valid": true}')) is None
    assert parse_llm(msg('{"p_valid": 0.7}', "refusal")) is None


# ------------------------------------------------------------------ end to end


@pytest.fixture(scope="module")
def full_run(tmp_path_factory, subset):
    tmp = tmp_path_factory.mktemp("v2")
    fakes = FakeAPIs()
    s1 = do_run(tmp, fakes, subset, committed=False)
    n_after_val = len(fakes.jev_calls)
    s2 = do_run(tmp, fakes, subset, committed=False)
    n_after_gate = len(fakes.jev_calls)
    s3 = do_run(tmp, fakes, subset, limit=7)
    s4 = do_run(tmp, fakes, subset)
    s5 = do_run(tmp, fakes, subset)
    return tmp, fakes, (s1, s2, s3, s4, s5), (n_after_val, n_after_gate)


def test_tau_gate_blocks_test_calls_until_committed(full_run, subset) -> None:
    tmp, fakes, statuses, (n_val, n_gate) = full_run
    assert statuses[:2] == ("TAU_WRITTEN", "TAU_NOT_COMMITTED")
    n_val_records = 3 * sum(it.split == "validation" for it in subset)
    assert n_val == n_gate == n_val_records
    assert statuses[2:] == ("PAUSED", "COMPLETE", "COMPLETE")
    assert len(fakes.jev_calls) == len(fakes.llm_calls) == 3 * len(subset)  # resume repeats nothing


def test_registered_order_and_record_hashes(full_run, subset) -> None:
    tmp, *_ = full_run
    calls = [r for r in Cache(tmp / "c.jsonl").records() if r["kind"] == "call"]
    order = [(r["split"] != "validation", r["i"], r["noise"], ("jev", "llm", "kw").index(r["arm"])) for r in calls]
    assert order == sorted(order)
    by_i = {it.i: it for it in subset}
    for r in calls:
        assert r["record_sha256"] == hashlib.sha256(render(by_i[r["i"]], r["noise"]).encode()).hexdigest()


def test_no_secret_is_written(full_run) -> None:
    tmp, fakes, *_ = full_run
    assert f"Bearer {SENTINEL_KEY}" in fakes.headers and LLM_SENTINEL in fakes.headers
    for path in (tmp / "c.jsonl", tmp / "m.json", tmp / "tau.json"):
        data = path.read_bytes()
        assert SENTINEL_KEY.encode() not in data and LLM_SENTINEL.encode() not in data, path


def test_slots_fill_end_to_end(full_run, subset) -> None:
    tmp, *_ = full_run
    slots = analysis_v2.compute(tmp / "c.jsonl", tmp / "tau.json", items=subset, bootstrap_b=200)
    filled = analysis.fill(template_v2.build(), slots)
    assert "{{" not in filled
    assert slots["run.status"] == "COMPLETE" and slots["run.hypotheses_evaluated"] == "yes"
    assert slots["tau.jev.recomputed_match"] == "yes" and slots["tau.llm.recomputed_match"] == "yes"
    assert slots["run.n_calls.kw"] == str(3 * len(subset))
    for h in ("H1", "H2", "H3"):
        assert slots[f"{h}.verdict"] != analysis_v2.NE
    assert slots["H3.verdict"] == "supported: Jev cheaper"


def test_ki1_caveat_absent_when_llm_invalid_rate_is_zero(full_run, subset) -> None:
    tmp, *_ = full_run
    slots = analysis_v2.compute(tmp / "c.jsonl", tmp / "tau.json", items=subset, bootstrap_b=200)
    assert slots["invalid.llm.rate"] == "0.0000"
    assert "CAVEAT" not in analysis.fill(template_v2.build(), slots)


def test_ki1_caveat_present_at_head() -> None:
    results = (ROOT / "results" / "jev-v2.md").read_text(encoding="utf-8")
    slots = json.loads((ROOT / "results" / "jev-v2.slots.json").read_text(encoding="utf-8"))
    assert slots["invalid.llm.rate"] == "1.0000"
    line = ("CAVEAT: LLM arm invalid rate 1.0000; H2 and H3 are uninformative about the LLM sensor. "
            "See DEVIATIONS KI-1.")
    assert f"**{line}**" in results
    rows = [r for r in results.splitlines() if r.startswith(("| H2:", "| H3:"))]
    assert len(rows) == 2 and all(f"<br>{line}" in r for r in rows)


def test_committed_template_matches_generator() -> None:
    assert (ROOT / "results" / "jev-v2.template.md").read_text(encoding="utf-8") == template_v2.build()


# ------------------------------------------------------------------ failure paths


def test_docs_mismatch_stops_before_inference(tmp_path: Path, subset) -> None:
    fakes = FakeAPIs()
    status = run_v2.run(jev_key=SENTINEL_KEY, jev_base_url=BASE_URL, llm_key=LLM_SENTINEL,
                        cache_path=tmp_path / "c.jsonl", manifest_path=tmp_path / "m.json",
                        tau_path=tmp_path / "t.json", jev_transport=httpx2.MockTransport(fakes.jev),
                        llm_transport=httpx2.MockTransport(fakes.llm), docs_fetch=lambda: b"<html>nothing</html>",
                        items=subset, check_design=False, log=lambda m: None)
    assert status == "DOCS_MISMATCH" and fakes.jev_calls == [] and fakes.llm_calls == []


def test_llm_retry_honours_retry_after_and_reparse(tmp_path: Path, subset) -> None:
    overloaded = lambda r: httpx2.Response(529, headers={"retry-after": "3"}, json={"type": "error"})  # noqa: E731
    fakes = FakeAPIs(llm_script=[overloaded], llm_reply="not json")
    sleeps: list[float] = []
    arm = LlmArm(Cache(tmp_path / "c.jsonl"), Spend(), api_key=LLM_SENTINEL,
                 transport=httpx2.MockTransport(fakes.llm), sleep=sleeps.append)
    it = subset[0]
    res = arm.call(i=it.i, split=it.split, noise="n00", perturbation="none", text=render(it, "n00"),
                   record_sha256="x")
    assert sleeps == [3.0]
    assert res.status == "invalid" and res.record["n_requests"] == 2 and len(fakes.llm_calls) == 3


def test_cap_stops_before_the_call(tmp_path: Path, subset) -> None:
    fakes = FakeAPIs()
    arm = LlmArm(Cache(tmp_path / "c.jsonl"), Spend(usd=39.9999), api_key=LLM_SENTINEL,
                 transport=httpx2.MockTransport(fakes.llm))
    it = subset[0]
    with pytest.raises(RunStop) as e:
        arm.call(i=it.i, split=it.split, noise="n00", perturbation="none", text=render(it, "n00"),
                 record_sha256="x")
    assert e.value.status == "CAP_TRUNCATED" and fakes.llm_calls == []


def test_preflight_v2_requires_both_keys() -> None:
    problems = run_v2.preflight_v2({"JEV_API_KEY": "x", "JEV_BASE_URL": BASE_URL})
    assert "missing ANTHROPIC_API_KEY" in problems


def test_wire_bodies_are_the_registered_requests(full_run, subset) -> None:
    from jev_probe.adapter_v2 import jev_body, llm_prompt
    from jev_probe.constants_v2 import JEV_CONTEXT, JEV_QUESTION

    _, fakes, *_ = full_run
    it = sorted((x for x in subset if x.split == "validation"), key=lambda x: x.i)[0]
    jev = fakes.jev_calls[0]
    assert jev.content == jev_body(render(it, "n00"))
    body = json.loads(jev.content)
    assert body["state"] == {"context": JEV_CONTEXT, "record": render(it, "n00")}
    assert body["questions"] == {JEV_QID: {"type": "noul", "instructions": JEV_QUESTION}}
    llm = json.loads(fakes.llm_calls[0].content)
    assert llm == {"model": LLM_MODEL, "max_tokens": 64, "temperature": 0.0,
                   "messages": [{"role": "user", "content": llm_prompt(render(it, "n00"))}]}
