"""Adapter behaviour against a mock endpoint: retries, cap, cache-before-parse, malformed."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import httpx2
import pytest

from conftest import BASE_URL, SENTINEL_KEY, FakeJev, ok_body
from jev_probe.adapter import JevAdapter, RunStop, request_body
from jev_probe.cache import Cache
from jev_probe.constants import CONTEXT
from jev_probe.questions import QUESTION_IDS

STATE = {"context": CONTEXT, "evidence": [{"sku": "SKU-1", "unit_cost": 10.0, "currency": "USD"}]}


def make(tmp_path: Path, fake: FakeJev, sleeps: list[float], **kw) -> JevAdapter:
    return JevAdapter(Cache(tmp_path / "c.jsonl"), api_key=SENTINEL_KEY, base_url=BASE_URL,
                      transport=fake.transport(), sleep=sleeps.append, **kw)


def call(ad: JevAdapter):
    return ad.call(j=0, i=0, condition="P", repeat=1, state=STATE)


def kinds(ad: JevAdapter, kind: str) -> list[dict]:
    return [r for r in ad.cache.records() if r["kind"] == kind]


def status(code: int, headers: dict | None = None, body: object = None):
    return lambda req: httpx2.Response(code, headers=headers or {}, json=body or {"error": "x"})


@pytest.mark.parametrize("base", ["https://api.example.invalid", "https://api.typesafe.ai/v2"])
def test_endpoint_must_resolve_to_registered(tmp_path: Path, fake: FakeJev, sleeps, base: str) -> None:
    with pytest.raises(RunStop) as e:
        JevAdapter(Cache(tmp_path / "c.jsonl"), api_key=SENTINEL_KEY, base_url=base,
                   transport=fake.transport())
    assert e.value.status == "ENDPOINT_MISMATCH"


def test_trailing_v1_is_stripped(tmp_path: Path, fake: FakeJev, sleeps) -> None:
    ad = JevAdapter(Cache(tmp_path / "c.jsonl"), api_key=SENTINEL_KEY,
                    base_url="https://api.typesafe.ai/v1", transport=fake.transport())
    assert call(ad).status == "ok"
    assert str(fake.systemone[0].url) == "https://api.typesafe.ai/v1/systemone"


def test_exact_body_is_sent_and_cached(tmp_path: Path, fake: FakeJev, sleeps) -> None:
    ad = make(tmp_path, fake, sleeps)
    res = call(ad)
    sent = fake.systemone[0].content
    assert sent == request_body(STATE)
    att = kinds(ad, "attempt")[0]
    assert att["request_sha256"] == hashlib.sha256(sent).hexdigest() == res.record["request_sha256"]
    assert att["request_body"] == json.loads(sent)
    assert att["requested_model"] == "jev-latest" and att["returned_model"] == "jev-1.13.0"
    for f in ("sent_utc", "received_utc", "latency_s", "usage_input_tokens", "usage_output_tokens"):
        assert att[f] is not None
    assert set(res.answers) == set(QUESTION_IDS) and res.status == "ok"


def test_retry_backoff_honours_retry_after_and_is_logged(tmp_path: Path, sleeps) -> None:
    fake = FakeJev(script=[status(429, {"Retry-After": "3"}), status(503), status(529)])
    ad = make(tmp_path, fake, sleeps)
    assert call(ad).status == "ok"
    assert sleeps == [3.0, 2.0, 4.0]
    retries = kinds(ad, "retry")
    assert [(r["http_status"], r["delay_s"]) for r in retries] == [(429, 3.0), (503, 2.0), (529, 4.0)]
    assert [r["error_class"] for r in retries] == [
        "TypeSafeRateLimitError", "TypeSafeInternalServerError", "TypeSafeInternalServerError"]
    assert [a["http_status"] for a in kinds(ad, "attempt")] == [429, 503, 529, 200]


def test_connection_errors_and_timeouts_are_retried(tmp_path: Path, sleeps) -> None:
    def boom(req):
        raise httpx2.ConnectError("down", request=req)

    def slow(req):
        raise httpx2.ReadTimeout("slow", request=req)

    fake = FakeJev(script=[boom, slow])
    ad = make(tmp_path, fake, sleeps)
    assert call(ad).status == "ok"
    assert sleeps == [1.0, 2.0]
    assert [r["error_class"] for r in kinds(ad, "retry")] == ["connection", "timeout"]


def test_retry_exhausted_stops_the_run(tmp_path: Path, sleeps) -> None:
    fake = FakeJev(script=[status(500)] * 20)
    ad = make(tmp_path, fake, sleeps)
    with pytest.raises(RunStop) as e:
        call(ad)
    assert e.value.status == "RETRY_EXHAUSTED"
    assert len(fake.systemone) == 9  # 1 + 8 retries
    assert sleeps == [1.0, 2.0, 4.0, 8.0, 16.0, 32.0, 60.0, 60.0]
    assert kinds(ad, "retry")[-1]["exhausted"] is True
    assert kinds(ad, "call") == []  # not cached as done: a resume repeats it


def test_unexpected_client_error_halts(tmp_path: Path, sleeps) -> None:
    ad = make(tmp_path, FakeJev(script=[status(400)]), sleeps)
    with pytest.raises(RunStop) as e:
        call(ad)
    assert e.value.status == "HTTP_400"


def test_malformed_answer_is_rerequested_once(tmp_path: Path, sleeps) -> None:
    fake = FakeJev(script=[lambda r: httpx2.Response(200, json=ok_body(r, drop=("Q_schema_drift",)))])
    ad = make(tmp_path, fake, sleeps)
    res = call(ad)
    assert res.status == "ok" and res.record["n_requests"] == 2
    assert len(fake.systemone) == 2 and fake.systemone[0].content == fake.systemone[1].content


@pytest.mark.parametrize("bad", [
    {"type": "noul", "noul": 1.5}, {"type": "noul", "noul": "0.7"}, {"type": "choice", "noul": 0.2},
    {"type": "noul"}, {"type": "noul", "noul": True}])
def test_twice_malformed_answers_are_invalid(tmp_path: Path, sleeps, bad) -> None:
    mk = lambda r: httpx2.Response(200, json=ok_body(r, override={"Q_plausible_outlier": bad}))  # noqa: E731
    ad = make(tmp_path, FakeJev(script=[mk, mk]), sleeps)
    res = call(ad)
    assert res.status == "partial_invalid" and res.record["n_invalid"] == 1
    assert res.answers["Q_plausible_outlier"] is None
    assert all(res.answers[q] is not None for q in QUESTION_IDS if q != "Q_plausible_outlier")


def test_422_twice_scores_all_invalid(tmp_path: Path, sleeps) -> None:
    ad = make(tmp_path, FakeJev(script=[status(422), status(422)]), sleeps)
    res = call(ad)
    assert res.status == "invalid" and res.record["n_requests"] == 2
    assert all(v is None for v in res.answers.values())


def test_raw_body_cached_before_parse_even_when_unparseable(tmp_path: Path, sleeps) -> None:
    junk = lambda r: httpx2.Response(200, text="<<not json>>")  # noqa: E731
    ad = make(tmp_path, FakeJev(script=[junk, junk]), sleeps)
    res = call(ad)
    assert res.status == "invalid"
    assert [a["response_body"] for a in kinds(ad, "attempt")] == ["<<not json>>"] * 2


def test_cap_refuses_before_any_request(tmp_path: Path, fake: FakeJev, sleeps) -> None:
    ad = make(tmp_path, fake, sleeps, cap_usd=1e-9)
    with pytest.raises(RunStop) as e:
        call(ad)
    assert e.value.status == "CAP_TRUNCATED" and fake.systemone == []


def test_token_cap_and_usage_accounting(tmp_path: Path, sleeps) -> None:
    body_len = len(request_body(STATE))
    fake = FakeJev(script=[lambda r: httpx2.Response(200, json=ok_body(r, usage=False))])
    ad = make(tmp_path, fake, sleeps, cap_input_tokens=2 * body_len + body_len // 4 - 1)
    call(ad)  # no usage field -> charged the byte-length bound
    assert ad.spend.input_tokens == body_len
    call(ad)  # usage reported -> charged usage.input_tokens
    assert ad.spend.input_tokens == body_len + body_len // 4
    assert ad.spend.usd == pytest.approx(ad.spend.input_tokens * 42e-9)
    with pytest.raises(RunStop) as e:
        call(ad)
    assert e.value.status == "CAP_TRUNCATED"
    # A fresh adapter over the same cache restores committed spend (resume).
    ad2 = make(tmp_path, FakeJev(), sleeps)
    assert ad2.spend.input_tokens == ad.spend.input_tokens


def test_retries_count_against_the_cap(tmp_path: Path, sleeps) -> None:
    body_len = len(request_body(STATE))
    ad = make(tmp_path, FakeJev(script=[status(503)] * 5), sleeps, cap_input_tokens=int(2.5 * body_len))
    with pytest.raises(RunStop) as e:
        call(ad)
    assert e.value.status == "CAP_TRUNCATED" and len(kinds(ad, "attempt")) == 2
