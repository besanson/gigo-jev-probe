"""Round-two guard: registered slot values never change; new slots may be added.

The registered slot set is results/p6.slots.json at commit 5b4fc02 (manuscript v0.1.1, the state
the round-two review read). Every slot there keeps its exact value, except the per-cell s3_held
slots that round-two finding F3 removes (a zero-flip proxy, replaced by the exhaustive deny-ward
slots). Also checked: the F1 record path admits exactly what direct admission admits.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
REGISTERED_AT = "5b4fc02"
REMOVED_BY_F3 = {f"E1.{s}.{n}.s3_held" for s in ("jev", "llm") for n in ("n00", "n10", "n30")}


@pytest.fixture(scope="module")
def registered() -> dict[str, str]:
    out = subprocess.run(["git", "show", f"{REGISTERED_AT}:results/p6.slots.json"], cwd=ROOT,
                         capture_output=True, text=True, check=True).stdout
    return json.loads(out)


@pytest.fixture(scope="module")
def current() -> dict[str, str]:
    return json.loads((ROOT / "results" / "p6.slots.json").read_text(encoding="utf-8"))


def test_registered_slot_values_are_unchanged(registered, current) -> None:
    changed = {k: (v, current.get(k)) for k, v in registered.items() if k not in REMOVED_BY_F3 and current.get(k) != v}
    assert changed == {}


def test_only_the_f3_proxy_slots_are_removed(registered, current) -> None:
    assert set(registered) - set(current) == REMOVED_BY_F3
    assert REMOVED_BY_F3 <= set(registered)


def test_new_slots_cover_the_round_two_findings(registered, current) -> None:
    added = set(current) - set(registered)
    for prefix in ("denyward.", "E4.per_item_match", "E2.paper5_pick", "E2.pick_changed.",
                   "E1.jev.n00.unsafe_bound_simul"):
        assert any(k.startswith(prefix) for k in added), prefix
    assert any(".posthoc." in k for k in added)


@pytest.mark.parametrize("exp", ["E1", "E2"])
def test_record_path_admits_what_direct_admission_admits(exp) -> None:  # F1
    from experiments import analysis_p6 as a
    from experiments.constants_p6 import SENSORS, cache_path, tau_path
    from experiments.corpus_p6 import build_items
    from experiments.run_p6 import cached_calls, registered_order
    from jev_probe.cache import Cache

    items = build_items(exp)
    calls = cached_calls(Cache(cache_path(exp)))
    pol = a.load_policies(tau_path(exp))
    thresholds = {s: pol[s]["policy"]["thresholds"] for s in SENSORS}
    for split in ("validation", "test"):
        via_records = a.readings(exp, items, calls, thresholds, split)
        for it, noise, label, _, sensor, field in registered_order(items, exp, (split,)):
            direct = a.admitted(calls.get((label, field, sensor, it.i, noise)), thresholds[sensor][field])
            assert via_records[(sensor, label, it.i, noise)][field] == direct


def test_binding_mismatch_makes_the_field_unknown() -> None:  # F1
    from experiments import analysis_p6 as a
    from sensed_authority.record import admitted_value

    call = {"exp": "E1", "i": 7, "noise": "n00", "field": "data_residency_region", "arm": "jev",
            "returned_model": "jev-1.13.0", "record_sha256": "a" * 64, "done_utc": "2026-10-01T00:00:00+00:00",
            "score": {"us": 0.9, "eu": 0.01, "apac": 0.02}}
    taus = {"us": (0.5, 0.1), "eu": (0.5, 0.1), "apac": (0.5, 0.1)}
    version = a.policy_version("E1", "jev")
    records = a.sensed_records(call, taus, version)
    request_id, resource_id = a.request_binding("E1", 7, "n00")
    ok = dict(field="data_residency_region", request_id=request_id, resource_id=resource_id,
              sensor_version="jev-1.13.0", admission_policy_version=version)
    assert admitted_value(records, **ok) == "us"
    for key, bad in (("request_id", "p6:E1:8:n00"), ("resource_id", "p6:E1:item:8"),
                     ("sensor_version", "jev-1.14.0"), ("admission_policy_version", version + "/eps5")):
        assert admitted_value(records, **{**ok, key: bad}) is None


def test_denyward_slots_match_the_module_and_the_witness_semantics() -> None:  # F3
    from checkers import n6_witness as w
    from experiments.denyward_p6 import evaluate
    from sensed_authority.bound import is_deny_ward

    model = w.and_model()
    r = evaluate(model, ("f1", "f2"))
    assert r["deny_ward"] is False and r["deny_ward"] == is_deny_ward(model, ("f1", "f2"))
    assert r["deny_tuples"] == 3 and r["witness_tuples"] == 3
    slots = json.loads((ROOT / "results" / "p6.slots.json").read_text(encoding="utf-8"))
    assert slots["denyward.K.approval_residency"] == "no"
