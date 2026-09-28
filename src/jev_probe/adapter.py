"""§3a/§4/§9/§10 adapter over the official SDK (typesafe-sdk==0.7.2).

- The SDK's own retries are disabled (RetryPolicy(max_retries=0)); every retry passes
  through this adapter, with its status and delay logged to the cache.
- Every raw response is appended to the cache from the HTTP response hook, i.e.
  before the SDK (or this adapter) parses it.
- The spending cap is checked before every HTTP attempt.
- The API key reaches the SDK only as a constructor argument. Nothing here writes a
  header, a credential or an environment value.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import httpx2
from pydantic_core import to_json
from typesafe_sdk import (
    RetryPolicy,
    TypeSafeAPIConnectionError,
    TypeSafeAPIError,
    TypeSafeAPIResponseValidationError,
    TypeSafeAPITimeoutError,
    TypeSafeClient,
    TypeSafeError,
)

import preflight
from jev_probe.cache import (
    Cache,
    decode_body,
    parse_answers,
    returned_model,
    sha256_hex,
    usage_tokens,
    utc_now,
)
from jev_probe.constants import (
    BACKOFF_INITIAL_S,
    BACKOFF_MAX_S,
    CAP_INPUT_TOKENS,
    CAP_USD,
    ENDPOINT,
    HTTP_TIMEOUT_S,
    MAX_RETRIES,
    MODEL,
    USD_PER_INPUT_TOKEN,
)
from jev_probe.questions import QUESTION_IDS, noul_questions

logging.getLogger("typesafe_sdk").setLevel(logging.WARNING)


class RunStop(Exception):
    """Stops the run with a registered status (CAP_TRUNCATED, RETRY_EXHAUSTED, ...)."""

    def __init__(self, status: str, detail: str = "") -> None:
        super().__init__(f"{status}: {detail}" if detail else status)
        self.status = status
        self.detail = detail


def resolve_root(base_url: str) -> str:
    """API root for the SDK; the resolved endpoint must be the registered one (§3a)."""
    endpoint = preflight.resolve_endpoint(base_url)
    if endpoint != ENDPOINT:
        raise RunStop("ENDPOINT_MISMATCH", f"{endpoint} != {ENDPOINT}")
    return endpoint[: -len("/v1/systemone")]


def backoff_delay(retry_number: int, retry_after_s: float | None) -> float:
    """1 s initial, doubling, 60 s max; a Retry-After header is honoured."""
    if retry_after_s is not None:
        return retry_after_s
    return min(BACKOFF_INITIAL_S * 2 ** (retry_number - 1), BACKOFF_MAX_S)


def is_retryable_status(status: int) -> bool:
    return status == 429 or status == 529 or 500 <= status <= 599


def _retry_after_s(headers: Any) -> float | None:
    from typesafe_sdk._core.errors import parse_retry_after

    ms = parse_retry_after(headers)
    return None if ms is None else ms / 1000.0


def request_body(state: dict[str, Any]) -> bytes:
    """The exact JSON body the SDK sends for this state (same encoder as the SDK)."""
    return to_json({"state": state, "model": MODEL, "questions": noul_questions()})


@dataclass
class Spend:
    usd: float = 0.0
    input_tokens: int = 0

    def charge(self, input_tokens: int) -> None:
        self.input_tokens += input_tokens
        self.usd += input_tokens * USD_PER_INPUT_TOKEN


@dataclass
class CallResult:
    answers: dict[str, float | None]
    status: str
    record: dict[str, Any] = field(default_factory=dict)


class JevAdapter:
    def __init__(
        self,
        cache: Cache,
        *,
        api_key: str,
        base_url: str,
        transport: httpx2.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        cap_usd: float = CAP_USD,
        cap_input_tokens: int = CAP_INPUT_TOKENS,
        segment: str = "",
    ) -> None:
        root = resolve_root(base_url)
        self.cache = cache
        self.sleep = sleep
        self.cap_usd = cap_usd
        self.cap_input_tokens = cap_input_tokens
        self.segment = segment
        self.spend = Spend()
        self._ctx: dict[str, Any] = {}
        self._pending: dict[str, Any] = {}
        self._last: dict[str, Any] | None = None
        self._http = httpx2.Client(
            timeout=HTTP_TIMEOUT_S,
            transport=transport,
            event_hooks={"request": [self._on_request], "response": [self._on_response]},
        )
        self._client = TypeSafeClient(
            api_key=api_key,
            base_url=root,
            model=MODEL,
            retry=RetryPolicy(max_retries=0),
            http_client=self._http,
        )
        self._restore_spend()

    # -- cap accounting ------------------------------------------------------

    def _restore_spend(self) -> None:
        """On resume, committed spend is rebuilt from every attempt already cached."""
        for rec in self.cache.records():
            if rec.get("kind") == "attempt":
                self.spend.charge(int(rec["charged_input_tokens"]))

    def _check_cap(self, body_len: int) -> None:
        worst_usd = body_len * USD_PER_INPUT_TOKEN
        if self.spend.usd + worst_usd > self.cap_usd:
            raise RunStop("CAP_TRUNCATED", f"USD {self.spend.usd:.6f} + {worst_usd:.6f} > {self.cap_usd}")
        if self.spend.input_tokens + body_len > self.cap_input_tokens:
            raise RunStop("CAP_TRUNCATED", f"input tokens would exceed {self.cap_input_tokens}")

    # -- HTTP hooks: raw response is cached before parsing -------------------

    def _on_request(self, request: httpx2.Request) -> None:
        self._pending = {"sent_utc": utc_now(), "t0": time.monotonic(), "body": request.content}

    def _on_response(self, response: httpx2.Response) -> None:
        response.read()
        latency = time.monotonic() - self._pending["t0"]
        raw = response.text
        body = self._pending["body"]
        self._write_attempt(
            http_status=response.status_code,
            raw=raw,
            latency=latency,
            received_utc=utc_now(),
            body=body,
            retry_after_s=_retry_after_s(response.headers) if response.status_code >= 400 else None,
            error_class=None,
        )

    def _write_attempt(
        self,
        *,
        http_status: int | None,
        raw: str | None,
        latency: float | None,
        received_utc: str | None,
        body: bytes | None,
        retry_after_s: float | None,
        error_class: str | None,
    ) -> None:
        ctx = self._ctx
        in_tok, out_tok = usage_tokens(raw)
        body_len = len(body or b"")
        # §9: charged from usage.input_tokens; no usage -> charged at the byte-length bound.
        charged = in_tok if in_tok is not None else body_len
        rec: dict[str, Any] = {
            "kind": ctx.get("kind", "attempt"),
            "segment": self.segment,
            **{k: ctx[k] for k in ("j", "i", "condition", "repeat", "request_n", "attempt") if k in ctx},
            "request_body": decode_body(body.decode("utf-8")) if body else None,
            "request_sha256": sha256_hex(body) if body else None,
            "request_bytes": body_len,
            "sent_utc": self._pending.get("sent_utc"),
            "received_utc": received_utc,
            "latency_s": latency,
            "http_status": http_status,
            "error_class": error_class,
            "retry_after_s": retry_after_s,
            "response_body": raw,
            "requested_model": MODEL,
            "returned_model": returned_model(raw) if raw is not None else "unreported",
            "usage_input_tokens": in_tok,
            "usage_output_tokens": out_tok,
            "charged_input_tokens": charged if rec_is_inference(ctx) else 0,
        }
        self.cache.append(rec)
        if rec_is_inference(ctx):
            self.spend.charge(rec["charged_input_tokens"])
        self._last = rec

    # -- verification (no inference) -----------------------------------------

    def list_models(self) -> list[str]:
        self._ctx = {"kind": "models_list"}
        self._pending = {}
        listed = self._client.models.list()
        return [m.name for m in listed.models]

    # -- one registered call ---------------------------------------------------

    def _attempts(self, state: dict[str, Any], body: bytes) -> tuple[str, dict[str, Any] | None]:
        """One request with the adapter's retries. Returns (outcome, final attempt record)."""
        for attempt in range(1, MAX_RETRIES + 2):
            self._check_cap(len(body))
            self._ctx["attempt"] = attempt
            self._last = None
            self._pending = {"sent_utc": utc_now(), "t0": time.monotonic(), "body": body}
            status: int | None
            retry_after: float | None = None
            try:
                self._client.system_one(state=state, questions=noul_questions(), model=MODEL)
                return "ok", self._last
            except TypeSafeAPIResponseValidationError:
                return "ok", self._last  # 2xx the SDK could not parse; validated below from raw
            except TypeSafeAPIError as exc:
                status = exc.status
                if status == 422:
                    return "422", self._last
                if not is_retryable_status(status):
                    raise RunStop(f"HTTP_{status}", type(exc).__name__) from None
                error_class = type(exc).__name__
                retry_after = self._last.get("retry_after_s") if self._last else None
            except TypeSafeAPIConnectionError as exc:
                status = None
                error_class = "timeout" if isinstance(exc, TypeSafeAPITimeoutError) else "connection"
                self._write_attempt(
                    http_status=None,
                    raw=None,
                    latency=time.monotonic() - self._pending["t0"],
                    received_utc=None,
                    body=body,
                    retry_after_s=None,
                    error_class=error_class,
                )
            except TypeSafeError as exc:
                raise RunStop("SDK_ERROR", type(exc).__name__) from None
            if attempt > MAX_RETRIES:
                self.cache.append(
                    {"kind": "retry", "segment": self.segment, **self._key(), "attempt": attempt,
                     "http_status": status, "error_class": error_class, "delay_s": None,
                     "exhausted": True}
                )
                raise RunStop("RETRY_EXHAUSTED", f"{self._key()} after {MAX_RETRIES} retries")
            delay = backoff_delay(attempt, retry_after)
            self.cache.append(
                {"kind": "retry", "segment": self.segment, **self._key(), "attempt": attempt,
                 "http_status": status, "error_class": error_class, "delay_s": delay,
                 "exhausted": False}
            )
            self.sleep(delay)
        raise AssertionError("unreachable")

    def _key(self) -> dict[str, Any]:
        return {k: self._ctx[k] for k in ("j", "i", "condition", "repeat", "request_n")}

    def call(self, *, j: int, i: int, condition: str, repeat: int, state: dict[str, Any]) -> CallResult:
        body = request_body(state)
        t_start = time.monotonic()
        first_sent = utc_now()
        answers: dict[str, float | None] = {qid: None for qid in QUESTION_IDS}
        final: dict[str, Any] | None = None
        outcome = ""
        n_requests = 0
        for request_n in (1, 2):
            n_requests = request_n
            self._ctx = {"kind": "attempt", "j": j, "i": i, "condition": condition,
                         "repeat": repeat, "request_n": request_n}
            outcome, final = self._attempts(state, body)
            if outcome == "422":
                answers = {qid: None for qid in QUESTION_IDS}
            else:
                answers = parse_answers(final["response_body"] if final else None)
            if outcome == "ok" and all(v is not None for v in answers.values()):
                break  # well-formed: no re-request
        n_invalid = sum(v is None for v in answers.values())
        status = "ok" if n_invalid == 0 else ("invalid" if n_invalid == len(answers) else "partial_invalid")
        call = {
            "kind": "call",
            "segment": self.segment,
            "j": j, "i": i, "condition": condition, "repeat": repeat,
            "n_requests": n_requests,
            "final_request_n": n_requests,
            "final_attempt": final["attempt"] if final else None,
            "final_http_status": final["http_status"] if final else None,
            "status": status,
            "n_invalid": n_invalid,
            "answers": answers,
            "returned_model": final["returned_model"] if final else "unreported",
            "request_sha256": sha256_hex(body),
            "first_sent_utc": first_sent,
            "done_utc": utc_now(),
            "latency_total_s": time.monotonic() - t_start,
        }
        self.cache.append(call)
        return CallResult(answers, status, call)

    def close(self) -> None:
        self._client.close()


def rec_is_inference(ctx: dict[str, Any]) -> bool:
    return ctx.get("kind", "attempt") == "attempt"
