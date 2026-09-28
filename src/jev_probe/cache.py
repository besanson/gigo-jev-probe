"""§10 append-only JSONL raw-response cache and the shared answer validator.

Records never contain a credential, a header, or an environment value.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any

from jev_probe.questions import QUESTION_IDS


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="microseconds")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class Cache:
    """Append-only JSONL store. Each append is flushed and fsynced before returning."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, record: dict[str, Any]) -> None:
        line = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
            fh.flush()
            os.fsync(fh.fileno())

    def records(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        with self.path.open(encoding="utf-8") as fh:
            return [json.loads(line) for line in fh if line.strip()]


def decode_body(raw: str | None) -> Any:
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except ValueError:
        return None


def valid_noul(answer: Any) -> float | None:
    """§4: a Noul answer is valid when typed noul with a finite numeric value in [0, 1]."""
    if not isinstance(answer, dict) or answer.get("type") != "noul":
        return None
    v = answer.get("noul")
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    v = float(v)
    if not math.isfinite(v) or not 0.0 <= v <= 1.0:
        return None
    return v


def parse_answers(raw: str | None) -> dict[str, float | None]:
    """p_yes per registered question id, or None where the answer is malformed."""
    body = decode_body(raw)
    answers = body.get("answers") if isinstance(body, dict) else None
    if not isinstance(answers, dict):
        return {qid: None for qid in QUESTION_IDS}
    return {qid: valid_noul(answers.get(qid)) for qid in QUESTION_IDS}


def returned_model(raw: str | None) -> str:
    body = decode_body(raw)
    m = body.get("model") if isinstance(body, dict) else None
    return m if isinstance(m, str) and m else "unreported"


def usage_tokens(raw: str | None) -> tuple[int | None, int | None]:
    body = decode_body(raw)
    usage = body.get("usage") if isinstance(body, dict) else None
    if not isinstance(usage, dict):
        return None, None

    def _int(v: Any) -> int | None:
        return v if isinstance(v, int) and not isinstance(v, bool) and v >= 0 else None

    return _int(usage.get("input_tokens")), _int(usage.get("output_tokens"))
