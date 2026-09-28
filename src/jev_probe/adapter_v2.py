"""jev-v2 §6/§10/§11 adapters for the two API arms, over their official SDKs.

As in jev-v1: SDK-internal retries are disabled and every retry passes through the adapter;
every raw response is appended to the cache from the HTTP response hook, before parsing; the
spending cap (shared across arms, USD 40) is checked before every HTTP attempt; no credential,
header or environment value is ever written.
"""

from __future__ import annotations

import json
import logging
import math
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import httpx2
from pydantic_core import to_json

from jev_probe.adapter import RunStop, backoff_delay, is_retryable_status, resolve_root
from jev_probe.cache import Cache, decode_body, returned_model, sha256_hex, usage_tokens, utc_now, valid_noul
from jev_probe.constants import HTTP_TIMEOUT_S, MAX_RETRIES, MODEL as JEV_MODEL
from jev_probe.constants_v2 import (
    CAP_USD,
    JEV_CONTEXT,
    JEV_QID,
    JEV_QUESTION,
    JEV_USD_PER_INPUT_TOKEN,
    JEV_USD_PER_OUTPUT_TOKEN,
    LLM_BASE_URL,
    LLM_MAX_TOKENS,
    LLM_MODEL,
    LLM_PROMPT_PREFIX,
    LLM_TEMPERATURE,
    LLM_USD_PER_INPUT_TOKEN,
    LLM_USD_PER_OUTPUT_TOKEN,
)

logging.getLogger("typesafe_sdk").setLevel(logging.WARNING)
logging.getLogger("anthropic").setLevel(logging.WARNING)

PRICES = {
    "jev": (JEV_USD_PER_INPUT_TOKEN, JEV_USD_PER_OUTPUT_TOKEN),
    "llm": (LLM_USD_PER_INPUT_TOKEN, LLM_USD_PER_OUTPUT_TOKEN),
}


def usd(arm: str, input_tokens: int, output_tokens: int) -> float:
    pin, pout = PRICES[arm]
    return input_tokens * pin + output_tokens * pout


@dataclass
class Spend:
    """Committed spend across all arms (§10)."""

    usd: float = 0.0

    @classmethod
    def from_cache(cls, cache: Cache) -> "Spend":
        s = cls()
        for rec in cache.records():
            if rec.get("kind") == "attempt":
                s.usd += float(rec["charged_usd"])
        return s


@dataclass
class CallResult:
    score: float | None
    status: str  # "ok" | "invalid"
    record: dict[str, Any] = field(default_factory=dict)


# ----------------------------------------------------------------- request bodies


def jev_state(text: str) -> dict[str, str]:
    return {"context": JEV_CONTEXT, "record": text}


def jev_questions() -> dict[str, Any]:
    from typesafe_sdk import Noul

    return {JEV_QID: Noul(instructions=JEV_QUESTION)}


def jev_questions_wire() -> dict[str, dict[str, str]]:
    return {JEV_QID: {"type": "noul", "instructions": JEV_QUESTION}}


def jev_body(text: str) -> bytes:
    """The exact JSON body the TypeSafe SDK sends (same encoder as the SDK)."""
    return to_json({"state": jev_state(text), "model": JEV_MODEL, "questions": jev_questions()})


def llm_prompt(text: str) -> str:
    return LLM_PROMPT_PREFIX + text


def llm_params(text: str) -> dict[str, Any]:
    return {"model": LLM_MODEL, "max_tokens": LLM_MAX_TOKENS, "temperature": LLM_TEMPERATURE,
            "messages": [{"role": "user", "content": llm_prompt(text)}]}


def llm_body_bound(text: str) -> bytes:
    """Worst-case body for the cap check (the SDK's own serialisation is recorded from the hook)."""
    return json.dumps(llm_params(text), ensure_ascii=False).encode("utf-8")


# ----------------------------------------------------------------- answer parsing


def parse_jev(raw: str | None) -> float | None:
    body = decode_body(raw)
    answers = body.get("answers") if isinstance(body, dict) else None
    return valid_noul(answers.get(JEV_QID)) if isinstance(answers, dict) else None


def parse_llm(raw: str | None) -> float | None:
    """§6 B: the reply text must parse as {"p_valid": <number in [0, 1]>}."""
    body = decode_body(raw)
    if not isinstance(body, dict) or body.get("stop_reason") == "refusal":
        return None
    blocks = body.get("content")
    if not isinstance(blocks, list):
        return None
    text = "".join(b.get("text", "") for b in blocks if isinstance(b, dict) and b.get("type") == "text")
    try:
        obj = json.loads(text.strip())
    except ValueError:
        return None
    if not isinstance(obj, dict):
        return None
    v = obj.get("p_valid")
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    v = float(v)
    return v if math.isfinite(v) and 0.0 <= v <= 1.0 else None


# ----------------------------------------------------------------- shared attempt loop


class ArmAdapter:
    arm = ""

    def __init__(self, cache: Cache, spend: Spend, *, sleep: Callable[[float], None], segment: str,
                 cap_usd: float = CAP_USD) -> None:
        self.cache = cache
        self.spend = spend
        self.sleep = sleep
        self.segment = segment
        self.cap_usd = cap_usd
        self._ctx: dict[str, Any] = {}
        self._pending: dict[str, Any] = {}
        self._last: dict[str, Any] | None = None

    def http_client(self, transport: httpx2.BaseTransport | None) -> httpx2.Client:
        return httpx2.Client(timeout=HTTP_TIMEOUT_S, transport=transport,
                             event_hooks={"request": [self._on_request], "response": [self._on_response]})

    # -- subclass interface --------------------------------------------------
    def worst_case_usd(self, body_len: int) -> float:
        raise NotImplementedError

    def send(self, text: str) -> None:
        raise NotImplementedError

    def classify(self, exc: Exception) -> tuple[str, int | None, str]:
        """('422' | 'retry' | 'stop' | 'conn' | 'validation', status, error class)."""
        raise NotImplementedError

    def parse(self, raw: str | None) -> float | None:
        raise NotImplementedError

    def retry_after_s(self, headers: Any) -> float | None:
        raise NotImplementedError

    def body_bound(self, text: str) -> bytes:
        raise NotImplementedError

    requested_model = ""

    # -- hooks: raw response cached before parsing ---------------------------
    def _on_request(self, request: httpx2.Request) -> None:
        self._pending.update({"sent_utc": utc_now(), "t0": time.monotonic(), "body": request.content})

    def _on_response(self, response: httpx2.Response) -> None:
        response.read()
        self._write_attempt(
            http_status=response.status_code, raw=response.text,
            latency=time.monotonic() - self._pending["t0"], received_utc=utc_now(),
            retry_after_s=self.retry_after_s(response.headers) if response.status_code >= 400 else None,
            error_class=None)

    def _write_attempt(self, *, http_status: int | None, raw: str | None, latency: float | None,
                       received_utc: str | None, retry_after_s: float | None, error_class: str | None) -> None:
        body: bytes = self._pending.get("body") or b""
        in_tok, out_tok = usage_tokens(raw)
        inference = self._ctx.get("kind", "attempt") == "attempt"
        if in_tok is not None:
            charged = usd(self.arm, in_tok, out_tok or 0)
        else:  # §10: no usage -> charged at the worst-case bound
            charged = self.worst_case_usd(len(body))
        rec: dict[str, Any] = {
            "kind": self._ctx.get("kind", "attempt"),
            "segment": self.segment,
            "arm": self.arm,
            **{k: self._ctx[k] for k in ("i", "split", "noise", "request_n", "attempt") if k in self._ctx},
            "request_body": decode_body(body.decode("utf-8")) if body else None,
            "request_sha256": sha256_hex(body) if body else None,
            "request_bytes": len(body),
            "sent_utc": self._pending.get("sent_utc"),
            "received_utc": received_utc,
            "latency_s": latency,
            "http_status": http_status,
            "error_class": error_class,
            "retry_after_s": retry_after_s,
            "response_body": raw,
            "requested_model": self.requested_model,
            "returned_model": returned_model(raw) if raw is not None else "unreported",
            "usage_input_tokens": in_tok,
            "usage_output_tokens": out_tok,
            "charged_usd": charged if inference else 0.0,
        }
        self.cache.append(rec)
        if inference:
            self.spend.usd += rec["charged_usd"]
        self._last = rec

    def _key(self) -> dict[str, Any]:
        return {"arm": self.arm, **{k: self._ctx[k] for k in ("i", "split", "noise", "request_n")}}

    def _attempts(self, text: str) -> tuple[str, dict[str, Any] | None]:
        bound = len(self.body_bound(text))
        for attempt in range(1, MAX_RETRIES + 2):
            worst = self.worst_case_usd(bound)
            if self.spend.usd + worst > self.cap_usd:
                raise RunStop("CAP_TRUNCATED", f"USD {self.spend.usd:.6f} + {worst:.6f} > {self.cap_usd}")
            self._ctx["attempt"] = attempt
            self._last = None
            self._pending = {"sent_utc": utc_now(), "t0": time.monotonic(), "body": None}
            retry_after: float | None = None
            try:
                self.send(text)
                return "ok", self._last
            except Exception as exc:  # noqa: BLE001 - mapped by the arm's classify()
                what, status, error_class = self.classify(exc)
                if what == "validation":
                    return "ok", self._last  # 2xx the SDK could not parse; validated from raw
                if what == "422":
                    return "422", self._last
                if what == "stop":
                    raise RunStop(f"HTTP_{status}" if status else "SDK_ERROR", error_class) from None
                if what == "conn":
                    self._write_attempt(http_status=None, raw=None,
                                        latency=time.monotonic() - self._pending["t0"], received_utc=None,
                                        retry_after_s=None, error_class=error_class)
                else:
                    retry_after = self._last.get("retry_after_s") if self._last else None
            if attempt > MAX_RETRIES:
                self.cache.append({"kind": "retry", "segment": self.segment, **self._key(), "attempt": attempt,
                                   "http_status": status, "error_class": error_class, "delay_s": None,
                                   "exhausted": True})
                raise RunStop("RETRY_EXHAUSTED", f"{self._key()} after {MAX_RETRIES} retries")
            delay = backoff_delay(attempt, retry_after)
            self.cache.append({"kind": "retry", "segment": self.segment, **self._key(), "attempt": attempt,
                               "http_status": status, "error_class": error_class, "delay_s": delay,
                               "exhausted": False})
            self.sleep(delay)
        raise AssertionError("unreachable")

    def call(self, *, i: int, split: str, noise: str, perturbation: str, text: str,
             record_sha256: str) -> CallResult:
        t_start = time.monotonic()
        first_sent = utc_now()
        score: float | None = None
        final: dict[str, Any] | None = None
        n_requests = 0
        for request_n in (1, 2):  # one re-request on a malformed answer (or 422 for Jev)
            n_requests = request_n
            self._ctx = {"kind": "attempt", "i": i, "split": split, "noise": noise, "request_n": request_n}
            outcome, final = self._attempts(text)
            score = None if outcome == "422" else self.parse(final["response_body"] if final else None)
            if outcome == "ok" and score is not None:
                break
        call = {
            "kind": "call", "segment": self.segment, "arm": self.arm, "i": i, "split": split,
            "noise": noise, "perturbation": perturbation, "record_sha256": record_sha256,
            "n_requests": n_requests,
            "final_attempt": final["attempt"] if final else None,
            "final_http_status": final["http_status"] if final else None,
            "status": "ok" if score is not None else "invalid",
            "score": score,
            "returned_model": final["returned_model"] if final else "unreported",
            "first_sent_utc": first_sent, "done_utc": utc_now(),
            "latency_total_s": time.monotonic() - t_start,
        }
        self.cache.append(call)
        return CallResult(score, call["status"], call)


# ----------------------------------------------------------------- arm A: Jev


class JevArm(ArmAdapter):
    arm = "jev"
    requested_model = JEV_MODEL

    def __init__(self, cache: Cache, spend: Spend, *, api_key: str, base_url: str,
                 transport: httpx2.BaseTransport | None = None, sleep: Callable[[float], None] = time.sleep,
                 segment: str = "", cap_usd: float = CAP_USD) -> None:
        from typesafe_sdk import RetryPolicy, TypeSafeClient

        super().__init__(cache, spend, sleep=sleep, segment=segment, cap_usd=cap_usd)
        root = resolve_root(base_url)
        self._http = self.http_client(transport)
        self._client = TypeSafeClient(api_key=api_key, base_url=root, model=JEV_MODEL,
                                      retry=RetryPolicy(max_retries=0), http_client=self._http)

    def worst_case_usd(self, body_len: int) -> float:
        return usd("jev", body_len, 0)

    def body_bound(self, text: str) -> bytes:
        return jev_body(text)

    def send(self, text: str) -> None:
        self._client.system_one(state=jev_state(text), questions=jev_questions(), model=JEV_MODEL)

    def parse(self, raw: str | None) -> float | None:
        return parse_jev(raw)

    def retry_after_s(self, headers: Any) -> float | None:
        from typesafe_sdk._core.errors import parse_retry_after

        ms = parse_retry_after(headers)
        return None if ms is None else ms / 1000.0

    def classify(self, exc: Exception) -> tuple[str, int | None, str]:
        from typesafe_sdk import (
            TypeSafeAPIConnectionError,
            TypeSafeAPIError,
            TypeSafeAPIResponseValidationError,
            TypeSafeAPITimeoutError,
        )

        name = type(exc).__name__
        if isinstance(exc, TypeSafeAPIResponseValidationError):
            return "validation", None, name
        if isinstance(exc, TypeSafeAPIError):
            if exc.status == 422:
                return "422", 422, name
            return ("retry" if is_retryable_status(exc.status) else "stop"), exc.status, name
        if isinstance(exc, TypeSafeAPIConnectionError):
            return "conn", None, "timeout" if isinstance(exc, TypeSafeAPITimeoutError) else "connection"
        return "stop", None, name

    def list_models(self) -> list[str]:
        self._ctx = {"kind": "models_list"}
        self._pending = {}
        return [m.name for m in self._client.models.list().models]

    def close(self) -> None:
        self._client.close()


# ----------------------------------------------------------------- arm B: LLM baseline


class LlmArm(ArmAdapter):
    arm = "llm"
    requested_model = LLM_MODEL

    def __init__(self, cache: Cache, spend: Spend, *, api_key: str,
                 transport: httpx2.BaseTransport | None = None, sleep: Callable[[float], None] = time.sleep,
                 segment: str = "", cap_usd: float = CAP_USD) -> None:
        import anthropic

        super().__init__(cache, spend, sleep=sleep, segment=segment, cap_usd=cap_usd)
        self._http = anthropic.DefaultHttpxClient(
            timeout=HTTP_TIMEOUT_S, transport=transport,
            event_hooks={"request": [self._on_request], "response": [self._on_response]})
        self._client = anthropic.Anthropic(api_key=api_key, base_url=LLM_BASE_URL, max_retries=0,
                                           http_client=self._http)

    def worst_case_usd(self, body_len: int) -> float:
        return usd("llm", body_len, LLM_MAX_TOKENS)

    def body_bound(self, text: str) -> bytes:
        return llm_body_bound(text)

    def send(self, text: str) -> None:
        # anthropic 1.x removed the `temperature` keyword; the API still accepts it for this
        # model, so the registered value travels in the request JSON via extra_body.
        params = llm_params(text)
        temperature = params.pop("temperature")
        self._client.messages.create(**params, extra_body={"temperature": temperature})

    def parse(self, raw: str | None) -> float | None:
        return parse_llm(raw)

    def retry_after_s(self, headers: Any) -> float | None:
        v = headers.get("retry-after")
        try:
            return float(v) if v is not None else None
        except ValueError:
            return None

    def classify(self, exc: Exception) -> tuple[str, int | None, str]:
        import anthropic

        name = type(exc).__name__
        if isinstance(exc, anthropic.APIResponseValidationError):
            return "validation", None, name
        if isinstance(exc, anthropic.APIStatusError):
            return ("retry" if is_retryable_status(exc.status_code) else "stop"), exc.status_code, name
        if isinstance(exc, anthropic.APIConnectionError):
            return "conn", None, "timeout" if isinstance(exc, anthropic.APITimeoutError) else "connection"
        return "stop", None, name

    def retrieve_model(self) -> str:
        """GET /v1/models/{id}: confirms the pinned model is served; runs no inference."""
        self._ctx = {"kind": "models_retrieve"}
        self._pending = {}
        return self._client.models.retrieve(LLM_MODEL).id

    def close(self) -> None:
        self._client.close()
