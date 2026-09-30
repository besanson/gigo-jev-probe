"""jev-v3 §3a/§3b: the arm-B request (prefill, no-fence line, max_tokens 32) and parser.

Everything else (attempt loop, retries, raw cache before parsing, cap check before every
attempt, one re-request on an invalid answer) is the jev-v2 adapter unchanged.
"""

from __future__ import annotations

import json
import math
import re
from typing import Any

from jev_probe.adapter_v2 import LlmArm, usd
from jev_probe.cache import decode_body
from jev_probe.constants_v2 import LLM_MODEL, LLM_TEMPERATURE
from jev_probe.constants_v3 import LLM_MAX_TOKENS, LLM_PREFILL, LLM_PROMPT_PREFIX

FENCE_RE = re.compile(r"```[A-Za-z0-9_-]*")


def llm_prompt(text: str) -> str:
    return LLM_PROMPT_PREFIX + text


def llm_params(text: str) -> dict[str, Any]:
    return {"model": LLM_MODEL, "max_tokens": LLM_MAX_TOKENS, "temperature": LLM_TEMPERATURE,
            "messages": [{"role": "user", "content": llm_prompt(text)},
                         {"role": "assistant", "content": LLM_PREFILL}]}


def llm_body_bound(text: str) -> bytes:
    return json.dumps(llm_params(text), ensure_ascii=False).encode("utf-8")


def parse_llm_v3(raw: str | None) -> float | None:
    """§3b: prefill + reply text, fences removed, first JSON object, p_valid in [0, 1]."""
    body = decode_body(raw)
    if not isinstance(body, dict) or body.get("stop_reason") == "refusal":
        return None
    blocks = body.get("content")
    if not isinstance(blocks, list):
        return None
    text = LLM_PREFILL + "".join(b.get("text", "") for b in blocks if isinstance(b, dict) and b.get("type") == "text")
    text = FENCE_RE.sub("", text)
    dec = json.JSONDecoder()
    obj: Any = None
    for m in re.finditer(r"\{", text):
        try:
            obj, _ = dec.raw_decode(text, m.start())
            break
        except ValueError:
            continue
    v = obj.get("p_valid") if isinstance(obj, dict) else None
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    v = float(v)
    return v if math.isfinite(v) and 0.0 <= v <= 1.0 else None


class LlmArmV3(LlmArm):
    def worst_case_usd(self, body_len: int) -> float:
        return usd("llm", body_len, LLM_MAX_TOKENS)

    def body_bound(self, text: str) -> bytes:
        return llm_body_bound(text)

    def send(self, text: str) -> None:
        # As in jev-v2: anthropic 1.x has no `temperature` keyword, so it travels via extra_body.
        params = llm_params(text)
        temperature = params.pop("temperature")
        self._client.messages.create(**params, extra_body={"temperature": temperature})

    def parse(self, raw: str | None) -> float | None:
        return parse_llm_v3(raw)
