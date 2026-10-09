"""Paper 6 sensed record (prereg/p6-v1.1.md §1, §2; F13): schema, canonical form, stamp checks."""

from __future__ import annotations

import dataclasses
import hashlib
import json

import pytest

from sensed_authority.record import (
    ADMISSIONS,
    SensedRecord,
    admitted_value,
    binding_violation,
    canonical_json,
    parse_utc,
    sha256_text,
)

DOC = "a" * 64
BINDING = {"field": "approval_assertion", "request_id": "req-1", "resource_id": "res-9",
           "sensor_version": "jev-1.13.0", "admission_policy_version": "p6-v1.1/E1/jev"}


def rec(**kw) -> SensedRecord:
    base = dict(field="approval_assertion", value="not_recorded", score=0.25, admission="true",
                sensor_id="jev", sensor_version="jev-1.13.0", source_document_sha256=DOC,
                sensed_at="2026-10-01T12:00:00+00:00", request_id="req-1", resource_id="res-9",
                admission_policy_version="p6-v1.1/E1/jev")
    base.update(kw)
    return SensedRecord(**base)


def test_fields_are_exactly_the_registered_ones() -> None:
    assert [f.name for f in dataclasses.fields(SensedRecord)] == [
        "field", "value", "score", "admission", "sensor_id", "sensor_version", "source_document_sha256",
        "sensed_at", "request_id", "resource_id", "admission_policy_version"]
    assert ADMISSIONS == ("true", "false", "unknown")


def test_record_is_frozen() -> None:
    r = rec()
    with pytest.raises(dataclasses.FrozenInstanceError):
        r.score = 0.9  # type: ignore[misc]


def test_canonical_json_is_sorted_and_compact() -> None:
    assert canonical_json({"b": 1, "a": [1, 2], "é": "ü"}) == '{"a":[1,2],"b":1,"é":"ü"}'
    with pytest.raises(ValueError):
        canonical_json({"x": float("nan")})


def test_sha256_text() -> None:
    assert sha256_text("abc") == hashlib.sha256(b"abc").hexdigest()


def test_record_canonical_json_and_hash() -> None:
    r = rec(score=1 / 3)
    body = json.loads(r.canonical_json())
    assert body["score"] == round(1 / 3, 12)
    assert list(body) == sorted(body)
    assert r.canonical_json() == canonical_json(r.as_dict())
    assert r.content_hash() == hashlib.sha256(r.canonical_json().encode()).hexdigest()
    assert SensedRecord.from_json(r.canonical_json()).canonical_json() == r.canonical_json()


def test_hash_changes_with_every_field() -> None:
    base = rec()
    changes = {"field": "residency", "value": "recorded:2026-06-01", "score": 0.26, "admission": "false",
               "sensor_id": "haiku", "sensor_version": "v2", "source_document_sha256": "b" * 64,
               "sensed_at": "2026-10-01T12:00:01+00:00", "request_id": "req-2", "resource_id": "res-8",
               "admission_policy_version": "other"}
    hashes = {base.content_hash()}
    for k, v in changes.items():
        hashes.add(dataclasses.replace(base, **{k: v}).content_hash())
    assert len(hashes) == len(changes) + 1


@pytest.mark.parametrize("field", ["field", "value", "sensor_id", "sensor_version", "request_id", "resource_id",
                                   "admission_policy_version"])
def test_empty_strings_rejected(field: str) -> None:
    with pytest.raises(ValueError, match=field):
        rec(**{field: ""})


@pytest.mark.parametrize("bad", ["yes", "", "TRUE", "unknown "])
def test_admission_must_be_registered(bad: str) -> None:
    with pytest.raises(ValueError, match="admission"):
        rec(admission=bad)


@pytest.mark.parametrize("admission", ADMISSIONS)
def test_every_admission_accepted(admission: str) -> None:
    assert rec(admission=admission).admission == admission


@pytest.mark.parametrize("score", [-0.0001, 1.0001, float("nan"), float("inf")])
def test_score_range(score: float) -> None:
    with pytest.raises(ValueError, match="score"):
        rec(score=score)


@pytest.mark.parametrize("score", [0, 0.0, 1, 1.0, 0.5])
def test_score_bounds_inclusive(score: float) -> None:
    assert rec(score=score).score == score


@pytest.mark.parametrize("score", [True, "0.5", None])
def test_score_must_be_a_number(score) -> None:
    with pytest.raises(ValueError, match="number"):
        rec(score=score)


@pytest.mark.parametrize("sha", ["A" * 64, "a" * 63, "a" * 65, "g" * 64, ""])
def test_document_hash_format(sha: str) -> None:
    with pytest.raises(ValueError, match="sha256"):
        rec(source_document_sha256=sha)


def test_timestamps_need_an_offset() -> None:
    with pytest.raises(ValueError, match="offset"):
        rec(sensed_at="2026-10-01T12:00:00")
    with pytest.raises(ValueError):
        rec(sensed_at="not a date")
    assert parse_utc("2026-10-01T09:00:00-03:00").utcoffset().total_seconds() == -3 * 3600


def test_dq_metadata_view() -> None:
    meta = rec(sensed_at="2026-10-01T23:30:00+00:00").dq_metadata("2026-10-03T01:00:00+00:00")
    assert meta["source"] == "sensor:jev@jev-1.13.0"
    assert meta["retrieved_day"] - meta["as_of_day"] == 2
    assert meta["version"] == 1
    assert meta["lineage"] == (f"document:{DOC}", "request:req-1", "resource:res-9",
                               "admission-policy:p6-v1.1/E1/jev")


def test_sarc_dq_evidence_record() -> None:
    r = rec(score=0.125, admission="false")
    ev = r.to_sarc_dq("2026-10-02T00:00:00+00:00")
    assert ev.record_id == r.content_hash()
    assert ev.payload == {"approval_assertion": "not_recorded", "score": 0.125, "admission": "false"}
    assert ev.metadata.age_days == 1
    assert ev.metadata.source == "sensor:jev@jev-1.13.0"
    assert ev.metadata.lineage[1] == "request:req-1"


def test_binding_all_match() -> None:
    assert binding_violation(rec(), **BINDING) is None


@pytest.mark.parametrize("name", list(BINDING))
def test_binding_reports_the_mismatched_stamp(name: str) -> None:
    other = dict(BINDING, **{name: "different"})
    assert binding_violation(rec(), **other) == name


def test_admitted_value_exactly_one_true() -> None:
    a = rec(value="recorded:2026-06-01", admission="true")
    b = rec(value="not_recorded", admission="false")
    c = rec(value="recorded:2026-06-15", admission="unknown")
    assert admitted_value([a, b, c], **BINDING) == "recorded:2026-06-01"
    assert admitted_value([b, c], **BINDING) is None
    assert admitted_value([a, dataclasses.replace(b, admission="true")], **BINDING) is None
    assert admitted_value([], **BINDING) is None


@pytest.mark.parametrize("name", list(BINDING))
def test_admitted_value_rejects_any_mismatched_stamp(name: str) -> None:
    good = rec(value="recorded:2026-06-01", admission="true")
    bad = rec(value="not_recorded", admission="false", **({name if name != "field" else "field": "x"}))
    assert admitted_value([good], **BINDING) == "recorded:2026-06-01"
    assert admitted_value([good, bad], **BINDING) is None
    assert admitted_value([good], **dict(BINDING, **{name: "x"})) is None
