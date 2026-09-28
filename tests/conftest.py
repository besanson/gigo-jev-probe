"""Mock System One endpoint (no network) shared by the Phase B tests."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from typing import Any

import httpx2
import pytest

from jev_probe.questions import QUESTION_IDS

SENTINEL_KEY = "sk-SENTINEL-must-never-appear-0123456789"
BASE_URL = "https://api.typesafe.ai"
DOCS_OK = (
    b"<html><body><h2>Evaluation endpoint</h2><p><code>POST</code> "
    b"<span>https://api.typesafe.ai/v1/systemone</span></p><p>model: jev-latest</p></body></html>"
)


def synthetic_p(content: bytes, qid: str) -> float:
    """Deterministic pseudo-answer with some signal, so every analysis branch runs."""
    body = json.loads(content)
    evidence = body["state"]["evidence"]
    text = json.dumps(evidence, sort_keys=True)
    h = int(hashlib.sha256(content + qid.encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
    signal = 0.0
    if qid == "Q_stale_master_data" and '"age_days": 0' not in text and "age_days" in text:
        signal = 0.5
    if qid == "Q_cross_source_contradiction" and len(evidence) > 1:
        signal = 0.4
    if qid == "Q0_valid":
        signal = 0.3 if len(evidence) == 1 else -0.3
    return min(1.0, max(0.0, 0.25 * h + 0.3 + signal))


def ok_body(request: httpx2.Request, *, model: str = "jev-1.13.0", drop: tuple[str, ...] = (),
            override: dict[str, Any] | None = None, usage: bool = True) -> dict[str, Any]:
    answers: dict[str, Any] = {q: {"type": "noul", "noul": synthetic_p(request.content, q)}
                               for q in QUESTION_IDS if q not in drop}
    answers.update(override or {})
    body: dict[str, Any] = {"model": model, "answers": answers}
    if usage:
        body["usage"] = {"input_tokens": len(request.content) // 4, "output_tokens": 9}
    return body


Scripted = Callable[[httpx2.Request], httpx2.Response]


class FakeJev:
    """A stand-in for api.typesafe.ai. `script` supplies the first System One responses."""

    def __init__(self, script: list[Scripted] | None = None, models: tuple[str, ...] = ("jev-latest",),
                 model: str = "jev-1.13.0") -> None:
        self.script = list(script or [])
        self.models = models
        self.model = model
        self.systemone: list[httpx2.Request] = []
        self.auth_headers: list[str] = []

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.auth_headers.append(request.headers.get("authorization", ""))
        if request.url.path == "/v1/models":
            return httpx2.Response(200, json={"models": [
                {"name": m, "description": "d", "release_date": "2026-09-15"} for m in self.models]})
        assert request.url.path == "/v1/systemone"
        self.systemone.append(request)
        if self.script:
            return self.script.pop(0)(request)
        return httpx2.Response(200, json=ok_body(request, model=self.model))

    def transport(self) -> httpx2.MockTransport:
        return httpx2.MockTransport(self)


@pytest.fixture
def fake() -> FakeJev:
    return FakeJev()


@pytest.fixture
def sleeps() -> list[float]:
    return []
