"""Paper 6 runner (prereg/p6-v1.1.md §5, §7), resumable from the cache.

    python -m experiments.run_p6 E1            # preflight, verify, then run or resume E1
    python -m experiments.run_p6 E2            # only after E1 is COMPLETE
    python -m experiments.run_p6 E1 --limit N  # stop after N new API calls

Order (§7): all validation records (splits A and B), then the arm health check, then thresholds
fitted on split A and bounds estimated on split B, written to results/p6-<E>.tau.json and
committed (the run stops with TAU_WRITTEN; the operator commits the file), then all test
records. Items ascending; noise 0, 0.10, 0.30; for E2 arm 1 then arm 2; sensors Jev then Haiku;
fields in registered order.

Arm health (§7, as jev-v3 §3c), per sensor and experiment: the first 20 validation calls of the
sensor are the smoke check (more than 2 invalid stops the run); after the validation split, more
than 5% invalid stops it. Both stops are ARM_INVALID, final for the experiment.

Spending cap: USD 60 across E1 to E5, from usage, checked before every attempt (E3 to E5 make
no call). Status: COMPLETE, TAU_WRITTEN, PAUSED, ARM_INVALID, CAP_TRUNCATED, RETRY_EXHAUSTED,
DOCS_MISMATCH, TAU_NOT_COMMITTED, TAU_MISMATCH, DESIGN_MISMATCH, CORPUS_MISMATCH,
ORDER_VIOLATION, or an aborting error (HTTP_<status>, SDK_ERROR).
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import sys
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx2

import preflight
from experiments.constants_p6 import (
    CAP_USD,
    CEILING,
    CP_ALPHA,
    E2_SELECTION_NOISE,
    FIELD_VALUES,
    HEALTH_MAX_INVALID_RATE,
    NOISE_LEVELS,
    PREREG_COMMIT,
    PREREG_TAG,
    REGISTRATION_ID,
    SENSORS,
    SMOKE_CALLS,
    SMOKE_MAX_INVALID,
    cache_path,
    manifest_path,
    tau_path,
)
from experiments.corpus_p6 import (
    DesignMismatch,
    Item,
    assertion_labels,
    build_items,
    design_facts,
    fields_for,
    generator_sha256,
    perturbation,
    record_sha256,
    render,
    sensed_sets,
    truth_values,
)
from experiments.sensors_p6 import P6JevArm, P6LlmArm, jev_questions_wire, llm_prompt
from jev_probe.adapter import RunStop
from jev_probe.adapter_v2 import Spend
from jev_probe.cache import Cache, sha256_hex, utc_now
from jev_probe.constants import DOCS_URL, ENDPOINT
from jev_probe.constants import MODEL as JEV_MODEL
from jev_probe.run import check_docs, fetch_docs
from jev_probe.run_v2 import engine_pins, tau_committed
from sensed_authority.admission import admit, estimate_field, fit_field_thresholds, freeze_policy
from sensed_authority.selection import select

NOISES = tuple(k for k, _ in NOISE_LEVELS)
LLM_KEY_ENV = "ANTHROPIC_API_KEY"


def labels(exp: str) -> tuple[tuple[str, int | None], ...]:
    """(experiment label, arm) in registered order."""
    return (("E1", None),) if exp == "E1" else (("E2.1", 1), ("E2.2", 2))


def registered_order(items: list[Item], exp: str, splits: tuple[str, ...]):
    """(item, noise, label, arm, sensor, field) in registered order for the given splits."""
    for it in sorted((it for it in items if it.split in splits), key=lambda x: x.i):
        for noise in NOISES:
            for label, arm in labels(exp):
                for sensor in SENSORS:
                    for field in fields_for(exp, arm):
                        yield it, noise, label, arm, sensor, field


def call_key(label: str, field: str, sensor: str, i: int, noise: str) -> tuple[str, str, str, int, str]:
    return (label, field, sensor, i, noise)


def cached_calls(cache: Cache) -> dict[tuple[str, str, str, int, str], dict[str, Any]]:
    return {call_key(r["exp"], r["field"], r["arm"], r["i"], r["noise"]): r
            for r in cache.records() if r.get("kind") == "call"}


# ------------------------------------------------------------------ §5.2 policy (shared with the analysis)


def fit_policy(exp: str, items: list[Item], calls: dict, sensor: str, ceiling: float = CEILING) -> dict[str, Any]:
    """Thresholds on split A against the assertion label, pooled over noise levels (and arms);
    split-B upper bounds against the truth label per experiment label, field and noise level."""
    rows: dict[str, dict[str, list[tuple[float | None, bool]]]] = {}
    pairs: dict[str, dict[str, list[tuple[Any, str]]]] = {}
    for it, noise, label, arm, s, field in registered_order(items, exp, ("validation",)):
        if s != sensor or it.part != "A":
            continue
        c = calls.get(call_key(label, field, sensor, it.i, noise))
        if c is None:
            continue
        labs = assertion_labels(it, field, noise, arm)
        for v in FIELD_VALUES[(exp, field)]:
            rows.setdefault(field, {}).setdefault(v, []).append(
                (None if c["score"] is None else c["score"][v], labs[v]))
    thresholds = {f: fit_field_thresholds(r, ceiling) for f, r in sorted(rows.items())}
    for it, noise, label, arm, s, field in registered_order(items, exp, ("validation",)):
        if s != sensor or it.part != "B":
            continue
        c = calls.get(call_key(label, field, sensor, it.i, noise))
        if c is None:
            continue
        admitted = None if c["score"] is None else admit(c["score"], thresholds[field])
        pairs.setdefault(f"{label}|{field}", {}).setdefault(noise, []).append(
            (admitted, truth_values(it, arm)[field]))
    estimates = {k: {lvl: estimate_field(p, CP_ALPHA) for lvl, p in sorted(levels.items())}
                 for k, levels in sorted(pairs.items())}
    return {"thresholds": thresholds, "estimates": estimates, "inputs": {"A": rows}}


def bounds_and_picks(exp: str, estimates: dict) -> dict[str, Any]:
    """E1: per noise level B+ = sum ê_i and B = sum (ê_i + û_i). E2: the reduct picked per arm (§5.5)."""
    out: dict[str, Any] = {}
    if exp == "E1":
        for lvl in NOISES:
            terms = [estimates[f"E1|{f}"][lvl] for f in fields_for("E1") if lvl in estimates.get(f"E1|{f}", {})]
            out[lvl] = {"unsafe_bound": sum(e.e_hat for e in terms), "change_bound": sum(e.e_hat + e.u_hat for e in terms)}
        return {"bounds": out}
    for label, arm in labels(exp):
        est = {f: (estimates[f"{label}|{f}"][E2_SELECTION_NOISE].e_hat, estimates[f"{label}|{f}"][E2_SELECTION_NOISE].u_hat)
               for f in fields_for(exp, arm) if E2_SELECTION_NOISE in estimates.get(f"{label}|{f}", {})}
        sets = sensed_sets(arm)
        out[label] = {"picked": select(sets, est) if all(f in est for s in sets.values() for f in s) else None,
                      "estimated_bounds": {r: sum(est[f][0] + est[f][1] for f in s if f in est) for r, s in sets.items()}}
    return {"picks": out}


def tau_document(exp: str, items: list[Item], calls: dict, ceiling: float = CEILING) -> str:
    sensors: dict[str, Any] = {}
    for sensor in SENSORS:
        pol = fit_policy(exp, items, calls, sensor, ceiling)
        frozen = json.loads(freeze_policy(version=f"{REGISTRATION_ID}/{exp}/{sensor}", ceiling=ceiling,
                                          thresholds=pol["thresholds"], estimates=pol["estimates"],
                                          inputs=pol["inputs"]))
        sensors[sensor] = {"policy": frozen, **_rounded(bounds_and_picks(exp, pol["estimates"]))}
    body = {"registration": REGISTRATION_ID, "prereg_tag": PREREG_TAG, "experiment": exp, "sensors": sensors}
    return json.dumps(body, indent=1, sort_keys=True) + "\n"


def _rounded(x: Any) -> Any:
    if isinstance(x, float):
        return round(x, 12)
    if isinstance(x, dict):
        return {k: _rounded(v) for k, v in x.items()}
    return x


# ------------------------------------------------------------------ manifest


def base_manifest(exp: str) -> dict[str, Any]:
    import anthropic
    from typesafe_sdk import __version__ as ts

    return {
        "registration": REGISTRATION_ID, "prereg_tag": PREREG_TAG, "prereg_commit": PREREG_COMMIT,
        "experiment": exp, "engine_pins": engine_pins(), "sdks": {"typesafe-sdk": ts, "anthropic": anthropic.__version__},
        "generator_sha256": generator_sha256(), "jev": {"endpoint": ENDPOINT, "requested_model": JEV_MODEL},
        "cap": {"usd": CAP_USD, "scope": "E1 to E5"},
        "health_rule": {"smoke_calls": SMOKE_CALLS, "smoke_max_invalid": SMOKE_MAX_INVALID,
                        "validation_max_invalid_rate": HEALTH_MAX_INVALID_RATE},
        "jev_questions_sha256": {f"{label}|{f}": sha256_hex(json.dumps(jev_questions_wire(label, f), sort_keys=True).encode())
                                 for label, arm in labels(exp) for f in fields_for(exp, arm)},
        "llm_prompt_sha256": {f"{label}|{f}": sha256_hex(llm_prompt(label, f, "").encode())
                              for label, arm in labels(exp) for f in fields_for(exp, arm)},
        "python": platform.python_version(), "health": {},
    }


def write_manifest(manifest: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def total_spend(exclude: Path) -> float:
    """Committed spend of the other paper 6 caches, so the cap covers E1 to E5 together."""
    return sum(Spend.from_cache(Cache(cache_path(e))).usd for e in ("E1", "E2") if cache_path(e) != exclude)


# ------------------------------------------------------------------ run


def run(exp: str, *, jev_key: str, jev_base_url: str, llm_key: str, cache: Path | None = None,
        manifest: Path | None = None, tau: Path | None = None, prior_manifest: Path | None = None,
        jev_transport: httpx2.BaseTransport | None = None, llm_transport: httpx2.BaseTransport | None = None,
        docs_fetch: Callable[[], bytes] = fetch_docs, is_committed: Callable[[Path], bool] = tau_committed,
        sleep: Callable[[float], None] | None = None, limit: int | None = None, cap_usd: float = CAP_USD,
        other_spend: float | None = None, items: list[Item] | None = None,
        log: Callable[[str], None] = print) -> str:
    cache_file = cache or cache_path(exp)
    manifest_file = manifest or manifest_path(exp)
    tau_file = tau or tau_path(exp)
    store = Cache(cache_file)
    segment = uuid.uuid4().hex[:12]
    man: dict[str, Any] = (json.loads(manifest_file.read_text(encoding="utf-8")) if manifest_file.exists()
                           else base_manifest(exp))
    man.setdefault("segments", [])
    seg: dict[str, Any] = {"segment": segment, "started_utc": utc_now()}
    man["segments"].append(seg)
    spend = Spend.from_cache(store)
    spend.usd += total_spend(cache_file) if other_spend is None else other_spend
    adapters: dict[tuple[str, str, str], Any] = {}

    def finish(status: str, detail: str = "") -> str:
        seg.update({"ended_utc": utc_now(), "status": status, "detail": detail, "committed_usd_at_end": spend.usd})
        calls = cached_calls(store)
        models = {s: sorted({c["returned_model"] for k, c in calls.items() if k[2] == s}) for s in SENSORS}
        man.update({"status": status, "returned_models": models,
                    "model_version_changed": any(len(m) > 1 for m in models.values()),
                    "n_calls_cached": {s: sum(1 for k in calls if k[2] == s) for s in SENSORS}})
        write_manifest(man, manifest_file)
        store.append({"kind": "run_event", "segment": segment, "utc": utc_now(), "status": status, "detail": detail,
                      "manifest": man})
        log(f"run_p6 {exp}: {status} {detail}".rstrip())
        return status

    if any(s.get("status") == "ARM_INVALID" for s in man["segments"][:-1]):
        return finish("ARM_INVALID", "a previous segment stopped on the arm health rule; not resumable")
    if exp == "E2":
        prior = prior_manifest or manifest_path("E1")
        status = json.loads(prior.read_text(encoding="utf-8")).get("status") if prior.exists() else None
        if status != "COMPLETE":
            return finish("ORDER_VIOLATION", f"E2 runs only after E1 is COMPLETE (E1 status: {status})")
    try:
        items = build_items(exp) if items is None else items
    except DesignMismatch as exc:
        return finish("DESIGN_MISMATCH", str(exc))
    man["design_facts"] = design_facts(items)

    try:
        for label, arm in labels(exp):
            for field in fields_for(exp, arm):
                for sensor in SENSORS:
                    common = {"exp_label": label, "field": field, "sleep": sleep or time.sleep, "segment": segment,
                              "cap_usd": cap_usd}
                    adapters[(sensor, label, field)] = (
                        P6JevArm(store, spend, api_key=jev_key, base_url=jev_base_url, transport=jev_transport, **common)
                        if sensor == "jev" else P6LlmArm(store, spend, api_key=llm_key, transport=llm_transport, **common))
        jev_any = next(a for (s, _, _), a in adapters.items() if s == "jev")
        llm_any = next(a for (s, _, _), a in adapters.items() if s == "llm")
        docs = docs_fetch()
        seg["docs_url"] = DOCS_URL
        seg["docs_sha256"] = man["docs_sha256"] = sha256_hex(docs)
        missing = check_docs(docs)
        if missing:
            return finish("DOCS_MISMATCH", f"not on {DOCS_URL}: {missing}")
        try:
            models = jev_any.list_models()
        except Exception as exc:  # noqa: BLE001
            return finish("DOCS_MISMATCH", f"GET /v1/models failed: {type(exc).__name__}")
        seg["jev_models_listed"] = models
        if JEV_MODEL not in models:
            return finish("DOCS_MISMATCH", f"{JEV_MODEL} not in GET /v1/models: {models}")
        try:
            seg["llm_model_retrieved"] = llm_any.retrieve_model()
        except Exception as exc:  # noqa: BLE001
            return finish("DOCS_MISMATCH", f"model lookup failed: {type(exc).__name__}")
        seg["committed_usd_at_start"] = spend.usd
        write_manifest(man, manifest_file)
        store.append({"kind": "manifest", "segment": segment, "utc": utc_now(), "manifest": man})

        done = cached_calls(store)
        new = 0

        def do_call(it: Item, noise: str, label: str, arm: int | None, sensor: str, field: str) -> dict | None:
            nonlocal new
            text = render(it, noise, arm)
            sha = record_sha256(text)
            key = call_key(label, field, sensor, it.i, noise)
            if key in done:
                if done[key]["record_sha256"] != sha:
                    raise RunStop("CORPUS_MISMATCH", f"{key}")
                return done[key]
            if limit is not None and new >= limit:
                return None
            res = adapters[(sensor, label, field)].call(i=it.i, split=it.split, noise=noise,
                                                        perturbation=perturbation(it, field, noise, arm),
                                                        text=text, record_sha256=sha)
            new += 1
            done[key] = res.record
            return res.record

        statuses: dict[str, list[str]] = {s: [] for s in SENSORS}
        for it, noise, label, arm, sensor, field in registered_order(items, exp, ("validation",)):
            rec = do_call(it, noise, label, arm, sensor, field)
            if rec is None:
                return finish("PAUSED", f"limit {limit} reached")
            statuses[sensor].append(rec["status"])
            if len(statuses[sensor]) == SMOKE_CALLS:
                bad = statuses[sensor].count("invalid")
                man["health"][f"smoke.{sensor}"] = {"invalid": bad, "n": SMOKE_CALLS, "stopped": bad > SMOKE_MAX_INVALID}
                if bad > SMOKE_MAX_INVALID:
                    return finish("ARM_INVALID", f"smoke check, {sensor}: {bad} of {SMOKE_CALLS} invalid")
        for sensor in SENSORS:
            bad, n = statuses[sensor].count("invalid"), len(statuses[sensor])
            if n < SMOKE_CALLS:  # fewer validation calls than the smoke window (test subsets only)
                man["health"][f"smoke.{sensor}"] = {"invalid": bad, "n": n, "stopped": bad > SMOKE_MAX_INVALID}
                if bad > SMOKE_MAX_INVALID:
                    return finish("ARM_INVALID", f"smoke check, {sensor}: {bad} of {n} invalid")
            fired = bad > HEALTH_MAX_INVALID_RATE * n
            man["health"][f"validation.{sensor}"] = {"invalid": bad, "n": n, "stopped": fired}
            if fired:
                return finish("ARM_INVALID", f"validation health check, {sensor}: {bad} of {n} invalid")

        text = tau_document(exp, items, cached_calls(store))
        if not tau_file.exists():
            tau_file.parent.mkdir(parents=True, exist_ok=True)
            tau_file.write_text(text, encoding="utf-8")
            man["tau_sha256"] = sha256_hex(tau_file.read_bytes())
            return finish("TAU_WRITTEN", f"commit {tau_file.name}, then resume for the test split")
        if tau_file.read_text(encoding="utf-8") != text:
            return finish("TAU_MISMATCH", "frozen thresholds differ from the cached validation data")
        if not is_committed(tau_file):
            return finish("TAU_NOT_COMMITTED", f"commit {tau_file.name} before any test-split call")
        man["tau_sha256"] = sha256_hex(tau_file.read_bytes())

        for it, noise, label, arm, sensor, field in registered_order(items, exp, ("test",)):
            if do_call(it, noise, label, arm, sensor, field) is None:
                return finish("PAUSED", f"limit {limit} reached")
            if new and new % 500 == 0:
                log(f"run_p6 {exp}: {new} new calls, USD {spend.usd:.6f}")
        return finish("COMPLETE")
    except RunStop as stop:
        return finish(stop.status, stop.detail)
    finally:
        for a in adapters.values():
            a.close()


def preflight_p6(env: dict[str, str]) -> list[str]:
    """Problems that block the run. Keys are checked for presence only and never printed."""
    problems = [f"missing {n}" for n in preflight.check_env(env)]
    if not env.get(LLM_KEY_ENV, "").strip():
        problems.append(f"missing {LLM_KEY_ENV}")
    if env.get("JEV_BASE_URL", "").strip() and preflight.resolve_endpoint(env["JEV_BASE_URL"]) != ENDPOINT:
        problems.append(f"JEV_BASE_URL does not resolve to {ENDPOINT}")
    pin = preflight.check_pin()
    if pin:
        problems.append(pin)
    return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("experiment", choices=("E1", "E2"))
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args(argv)
    env = dict(os.environ)
    problems = preflight_p6(env)
    if problems:
        print("preflight_p6: " + "; ".join(problems), file=sys.stderr)
        return 1
    print("preflight_p6: ok (both keys present, Jev endpoint, both siblings at pin)")
    jev_key = env.get("JEV_API_KEY", "").strip() or env.get("TYPESAFE_API_KEY", "").strip()
    status = run(args.experiment, jev_key=jev_key, jev_base_url=env["JEV_BASE_URL"],
                 llm_key=env[LLM_KEY_ENV].strip(), limit=args.limit)
    return 0 if status in ("COMPLETE", "PAUSED", "TAU_WRITTEN") else 2


if __name__ == "__main__":
    sys.exit(main())
