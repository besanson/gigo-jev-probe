"""End to end on synthetic responses: run order, resume, verification gates, secrets,
and slot filling from the cache."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from conftest import BASE_URL, DOCS_OK, SENTINEL_KEY, FakeJev
from jev_probe import analysis, run, template
from jev_probe.cache import Cache
from jev_probe.items import build_items

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def items():
    return build_items()


def do_run(tmp: Path, fake: FakeJev, items, **kw) -> str:
    return run.run(api_key=SENTINEL_KEY, base_url=BASE_URL, cache_path=tmp / "responses" / "c.jsonl",
                   manifest_path=tmp / "responses" / "manifest.json", transport=fake.transport(),
                   docs_fetch=lambda: DOCS_OK, sleep=lambda s: None, items=items, log=lambda m: None, **kw)


@pytest.fixture(scope="module")
def full_run(tmp_path_factory, items):
    tmp = tmp_path_factory.mktemp("full")
    fake = FakeJev()
    first = do_run(tmp, fake, items, limit=25)
    second = do_run(tmp, fake, items)
    return tmp, fake, first, second


def test_resume_repeats_nothing_and_keeps_registered_order(full_run) -> None:
    tmp, fake, first, second = full_run
    assert (first, second) == ("PAUSED", "COMPLETE")
    assert len(fake.systemone) == 1800
    calls = [r for r in Cache(tmp / "responses" / "c.jsonl").records() if r["kind"] == "call"]
    order = [(r["j"], r["condition"], r["repeat"]) for r in calls]
    assert order == [(j, c, r) for j in range(300) for c in ("P", "PM") for r in (1, 2, 3)]
    man = json.loads((tmp / "responses" / "manifest.json").read_text())
    assert man["status"] == "COMPLETE" and len(man["segments"]) == 2
    assert man["price"]["usd_per_input_token"] == pytest.approx(42e-9)
    assert man["sdk"]["version"] == "0.7.2" and man["prereg_commit"].startswith("306e701")
    assert man["docs_sha256"] and man["returned_models"] == ["jev-1.13.0"]
    assert man["model_version_changed"] is False


def test_key_is_sent_but_never_written(full_run) -> None:
    tmp, fake, _, _ = full_run
    assert set(fake.auth_headers) == {f"Bearer {SENTINEL_KEY}"}
    for path in [p for p in tmp.rglob("*") if p.is_file()]:
        data = path.read_bytes()
        assert SENTINEL_KEY.encode() not in data, path
        assert b"authorization" not in data.lower(), path


def test_slots_fill_end_to_end(full_run) -> None:
    tmp, _, _, _ = full_run
    slots = analysis.compute(tmp / "responses" / "c.jsonl", bootstrap_b=200)
    filled = analysis.fill(template.build(), slots)
    assert "{{" not in filled
    assert slots["run.status"] == "COMPLETE" and slots["run.hypotheses_evaluated"] == "yes"
    assert slots["run.n_calls"] == "1800" and slots["baseline.predicate.silent_unit_change.Q_silent_unit_change.rate"] == "uncovered"
    assert slots["baseline.predicate.stale_master_data.Q_stale_master_data.rate"] == "1.0000"
    assert slots["baseline.predicate.fpr.Q0_valid.rate"] == "0.0000"
    assert slots["baseline.ladder.opus-4-8.adr"] == "0.6175"
    assert slots["baseline.ladder.endpoint_ci_lo"] == "-0.0551"
    for h in ("H1.PM.pooled", "H2.PM", "H3.meta"):
        assert slots[f"{h}.verdict"] != analysis.NE and slots[f"{h}.p_adj"] != "n/a"
    # Synthetic stale-price signal shows up only where the metadata is visible.
    assert float(slots["detect.PM.stale_master_data.Q_stale_master_data.rate"]) > float(
        slots["detect.P.stale_master_data.Q_stale_master_data.rate"])


def test_committed_template_matches_generator() -> None:
    assert (ROOT / "results" / "jev-v1.template.md").read_text(encoding="utf-8") == template.build()


def test_fill_refuses_unknown_slot() -> None:
    with pytest.raises(KeyError):
        analysis.fill("x {{no.such.slot}}", {})


def test_cap_truncation_reports_hypotheses_not_evaluated(tmp_path: Path, items) -> None:
    fake = FakeJev()
    status = do_run(tmp_path, fake, items, cap_input_tokens=60_000)
    assert status == "CAP_TRUNCATED" and 0 < len(fake.systemone) < 1800
    slots = analysis.compute(tmp_path / "responses" / "c.jsonl", bootstrap_b=50)
    analysis.fill(template.build(), slots)
    assert slots["run.status"] == "CAP_TRUNCATED" and slots["H1.PM.pooled.verdict"] == analysis.NE


@pytest.mark.parametrize("docs,models", [(b"<html>nothing here</html>", ("jev-latest",)),
                                         (DOCS_OK, ("jev-1.13.0",))])
def test_docs_mismatch_stops_before_inference(tmp_path: Path, items, docs, models) -> None:
    fake = FakeJev(models=models)
    status = run.run(api_key=SENTINEL_KEY, base_url=BASE_URL, cache_path=tmp_path / "c.jsonl",
                     manifest_path=tmp_path / "m.json", transport=fake.transport(),
                     docs_fetch=lambda: docs, items=items, log=lambda m: None)
    assert status == "DOCS_MISMATCH" and fake.systemone == []


def test_model_version_change_is_flagged(tmp_path: Path, items) -> None:
    fake = FakeJev()
    do_run(tmp_path, fake, items, limit=6)
    fake.model = "jev-1.14.0"
    do_run(tmp_path, fake, items, limit=6)
    man = json.loads((tmp_path / "responses" / "manifest.json").read_text())
    assert man["model_version_changed"] is True
