"""Paper 6 sensors (prereg/p6-v1.1.md §5.1): one call per record and field, one score per
candidate value. Built on the jev-v2 adapters, unchanged: SDK retries off, every retry through
the adapter, raw responses cached before parsing, the spending cap checked before every
attempt, no credential ever written.

Each cache record is tagged with its experiment label (`E1`, `E2.1`, `E2.2`) and field by a
thin cache wrapper, so the jev-v2 attempt loop is reused as it is.
"""

from __future__ import annotations

import json
import math
import re
import time
from collections.abc import Callable
from typing import Any

import httpx2
from pydantic_core import to_json

from experiments.constants_p6 import (
    FIELD_VALUES,
    JEV_QUESTIONS,
    LLM_MAX_TOKENS,
    LLM_MAX_TOKENS_E1_APPROVAL,
    LLM_PREFILL,
    LLM_PROMPT,
    LLM_TASKS,
    llm_key,
    llm_keys,
)
from jev_probe.adapter_v2 import JevArm, LlmArm, Spend, jev_state, usd
from jev_probe.adapter_v3 import FENCE_RE
from jev_probe.cache import Cache, decode_body, valid_noul
from jev_probe.constants import MODEL as JEV_MODEL
from jev_probe.constants_v2 import LLM_MODEL, LLM_TEMPERATURE


class TaggedCache:
    """Appends to a shared cache, adding the experiment label and field to every record."""

    def __init__(self, cache: Cache, **tags: str) -> None:
        self._cache = cache
        self._tags = tags

    def append(self, record: dict[str, Any]) -> None:
        self._cache.append({**record, **self._tags})

    def records(self) -> list[dict[str, Any]]:
        return self._cache.records()


def domain(exp_label: str) -> str:
    return exp_label.split(".", 1)[0]


# ------------------------------------------------------------------ Jev


def jev_questions_wire(exp_label: str, field: str) -> dict[str, dict[str, str]]:
    return {JEV_QUESTIONS[(field, v)][0]: {"type": "noul", "instructions": JEV_QUESTIONS[(field, v)][1]}
            for v in FIELD_VALUES[(domain(exp_label), field)]}


def parse_jev_scores(raw: str | None, exp_label: str, field: str) -> dict[str, float] | None:
    """One noul per candidate value, every one present and in [0, 1]; else invalid (None)."""
    body = decode_body(raw)
    answers = body.get("answers") if isinstance(body, dict) else None
    if not isinstance(answers, dict):
        return None
    scores = {}
    for v in FIELD_VALUES[(domain(exp_label), field)]:
        s = valid_noul(answers.get(JEV_QUESTIONS[(field, v)][0]))
        if s is None:
            return None
        scores[v] = s
    return scores


class P6JevArm(JevArm):
    def __init__(self, cache: Cache, spend: Spend, *, exp_label: str, field: str, api_key: str, base_url: str,
                 transport: httpx2.BaseTransport | None = None, sleep: Callable[[float], None] = time.sleep,
                 segment: str = "", cap_usd: float) -> None:
        super().__init__(TaggedCache(cache, exp=exp_label, field=field), spend, api_key=api_key,
                         base_url=base_url, transport=transport, sleep=sleep, segment=segment, cap_usd=cap_usd)
        self.exp_label, self.field = exp_label, field

    def _questions(self) -> dict[str, Any]:
        from typesafe_sdk import Noul

        return {qid: Noul(instructions=q["instructions"]) for qid, q in jev_questions_wire(self.exp_label,
                                                                                            self.field).items()}

    def body_bound(self, text: str) -> bytes:
        return to_json({"state": jev_state(text), "model": JEV_MODEL, "questions": self._questions()})

    def send(self, text: str) -> None:
        self._client.system_one(state=jev_state(text), questions=self._questions(), model=JEV_MODEL)

    def parse(self, raw: str | None) -> dict[str, float] | None:  # type: ignore[override]
        return parse_jev_scores(raw, self.exp_label, self.field)


# ------------------------------------------------------------------ Haiku


def llm_object(exp_label: str, field: str) -> str:
    """§5.1: the {object} part, each key mapped to the literal text <number between 0 and 1>."""
    return "{" + ", ".join(f'"{k}": <number between 0 and 1>' for k in llm_keys(domain(exp_label), field)) + "}"


def llm_prompt(exp_label: str, field: str, text: str) -> str:
    task = LLM_TASKS[(domain(exp_label), field)]
    return LLM_PROMPT.replace("{task}", task).replace("{object}", llm_object(exp_label, field)) + text


def llm_max_tokens(exp_label: str, field: str) -> int:
    return LLM_MAX_TOKENS_E1_APPROVAL if (domain(exp_label), field) == ("E1", "approval_assertion") else LLM_MAX_TOKENS


def llm_params(exp_label: str, field: str, text: str) -> dict[str, Any]:
    return {"model": LLM_MODEL, "max_tokens": llm_max_tokens(exp_label, field), "temperature": LLM_TEMPERATURE,
            "messages": [{"role": "user", "content": llm_prompt(exp_label, field, text)},
                         {"role": "assistant", "content": LLM_PREFILL}]}


def parse_llm_scores(raw: str | None, exp_label: str, field: str) -> dict[str, float] | None:
    """jev-v3 §3b parser: prefill prepended, fences removed, first JSON object; every key a number
    (not a boolean) in [0, 1]; else invalid (None)."""
    body = decode_body(raw)
    if not isinstance(body, dict) or body.get("stop_reason") == "refusal":
        return None
    blocks = body.get("content")
    if not isinstance(blocks, list):
        return None
    text = LLM_PREFILL + "".join(b.get("text", "") for b in blocks if isinstance(b, dict) and b.get("type") == "text")
    text = FENCE_RE.sub("", text)
    obj: Any = None
    for m in re.finditer(r"\{", text):
        try:
            obj, _ = json.JSONDecoder().raw_decode(text, m.start())
            break
        except ValueError:
            continue
    if not isinstance(obj, dict):
        return None
    scores = {}
    for v in FIELD_VALUES[(domain(exp_label), field)]:
        x = obj.get(llm_key(v))
        if isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) or not 0 <= x <= 1:
            return None
        scores[v] = float(x)
    return scores


class P6LlmArm(LlmArm):
    def __init__(self, cache: Cache, spend: Spend, *, exp_label: str, field: str, api_key: str,
                 transport: httpx2.BaseTransport | None = None, sleep: Callable[[float], None] = time.sleep,
                 segment: str = "", cap_usd: float) -> None:
        super().__init__(TaggedCache(cache, exp=exp_label, field=field), spend, api_key=api_key,
                         transport=transport, sleep=sleep, segment=segment, cap_usd=cap_usd)
        self.exp_label, self.field = exp_label, field

    def worst_case_usd(self, body_len: int) -> float:
        return usd("llm", body_len, llm_max_tokens(self.exp_label, self.field))

    def body_bound(self, text: str) -> bytes:
        return json.dumps(llm_params(self.exp_label, self.field, text), ensure_ascii=False).encode("utf-8")

    def send(self, text: str) -> None:
        params = llm_params(self.exp_label, self.field, text)
        temperature = params.pop("temperature")
        self._client.messages.create(**params, extra_body={"temperature": temperature})

    def parse(self, raw: str | None) -> dict[str, float] | None:  # type: ignore[override]
        return parse_llm_scores(raw, self.exp_label, self.field)
