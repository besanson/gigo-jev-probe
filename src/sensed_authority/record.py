"""The sensed observation record (prereg/p6-v1.1.md §1, §2; findings F13).

A sensor writes an observation, never a verdict. One record covers one candidate value of one
field: its score and the admission stamp the frozen policy gave that score, with provenance,
bound to the request, the resource and the admission policy version it was sensed for.
`admitted_value` is the stamp check the gate applies before it uses a field: every record
must match the decision being made, and exactly one value must be admitted `true`; anything
else is `unknown`, which denies.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

ADMISSIONS = ("true", "false", "unknown")
SCORE_DIGITS = 12
_SHA256 = re.compile(r"[0-9a-f]{64}")


def canonical_json(obj: Any) -> str:
    """Sorted keys, no whitespace, UTF-8 text: the one serialisation every hash is taken over."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def parse_utc(stamp: str) -> datetime:
    """An ISO 8601 timestamp that states its offset; naive timestamps are rejected."""
    parsed = datetime.fromisoformat(stamp)
    if parsed.utcoffset() is None:
        raise ValueError(f"timestamp without an offset: {stamp!r}")
    return parsed


@dataclass(frozen=True)
class SensedRecord:
    field: str
    value: str
    score: float
    admission: str
    sensor_id: str
    sensor_version: str
    source_document_sha256: str
    sensed_at: str
    request_id: str
    resource_id: str
    admission_policy_version: str

    def __post_init__(self) -> None:
        for name in ("field", "value", "sensor_id", "sensor_version", "request_id", "resource_id",
                     "admission_policy_version"):
            if not getattr(self, name):
                raise ValueError(f"{name} must be a non-empty string")
        if self.admission not in ADMISSIONS:
            raise ValueError(f"admission must be one of {ADMISSIONS}, got {self.admission!r}")
        if isinstance(self.score, bool) or not isinstance(self.score, (int, float)):
            raise ValueError("score must be a number")
        if not (math.isfinite(self.score) and 0.0 <= self.score <= 1.0):
            raise ValueError(f"score must be in [0, 1], got {self.score!r}")
        if not _SHA256.fullmatch(self.source_document_sha256):
            raise ValueError("source_document_sha256 must be 64 lowercase hex characters")
        parse_utc(self.sensed_at)

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["score"] = round(float(self.score), SCORE_DIGITS)
        return d

    def canonical_json(self) -> str:
        return canonical_json(self.as_dict())

    def content_hash(self) -> str:
        return sha256_text(self.canonical_json())

    @classmethod
    def from_json(cls, text: str) -> SensedRecord:
        return cls(**json.loads(text))

    def dq_metadata(self, retrieved_at: str) -> dict[str, Any]:
        """The record's metadata in the shape of SARC-DQ's `RecordMetadata`, so freshness,
        version-pin and lineage predicates apply to it. Days are proleptic ordinals."""
        return {
            "source": f"sensor:{self.sensor_id}@{self.sensor_version}",
            "as_of_day": parse_utc(self.sensed_at).date().toordinal(),
            "retrieved_day": parse_utc(retrieved_at).date().toordinal(),
            "version": 1,
            "lineage": (
                f"document:{self.source_document_sha256}",
                f"request:{self.request_id}",
                f"resource:{self.resource_id}",
                f"admission-policy:{self.admission_policy_version}",
            ),
        }

    def to_sarc_dq(self, retrieved_at: str) -> Any:
        """A `sarc_dq.records.EvidenceRecord` view; the payload carries the observation only."""
        from sarc_dq.records import EvidenceRecord, RecordMetadata

        payload = {self.field: self.value, "score": self.as_dict()["score"], "admission": self.admission}
        return EvidenceRecord(record_id=self.content_hash(), payload=payload,
                              metadata=RecordMetadata(**self.dq_metadata(retrieved_at)))


def binding_violation(record: SensedRecord, *, field: str, request_id: str, resource_id: str,
                      sensor_version: str, admission_policy_version: str) -> str | None:
    """The first stamp that does not match the decision being made, or None when all match."""
    expected = {"field": field, "request_id": request_id, "resource_id": resource_id,
                "sensor_version": sensor_version, "admission_policy_version": admission_policy_version}
    for name, want in expected.items():
        if getattr(record, name) != want:
            return name
    return None


def admitted_value(records: list[SensedRecord], **binding: str) -> str | None:
    """The field's value the gate may use, or None (unknown, which denies): every record must
    pass the stamp check, and exactly one candidate value must be admitted `true`."""
    if not records or any(binding_violation(r, **binding) is not None for r in records):
        return None
    admitted = [r.value for r in records if r.admission == "true"]
    return admitted[0] if len(admitted) == 1 else None
