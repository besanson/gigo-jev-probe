"""jev-v3 runner (prereg/jev-v3.md §4): arm B only, resumable from the cache.

    python -m jev_probe.run_v3            # preflight, verify, then run or resume
    python -m jev_probe.run_v3 --limit N  # stop after N new API calls

Order: smoke check (first 20 validation records), the rest of the validation split, health
check, thresholds written (TAU_WRITTEN; the operator commits them), then the test split behind
the same commit gate as jev-v2. Arm A is read from the jev-v2 cache and never called.

Status is one of COMPLETE, TAU_WRITTEN, PAUSED, ARM_INVALID, CAP_TRUNCATED, RETRY_EXHAUSTED,
DOCS_MISMATCH, TAU_NOT_COMMITTED, TAU_MISMATCH, DESIGN_MISMATCH, CORPUS_MISMATCH,
CARRIED_ARM_INCOMPLETE, or an aborting error (HTTP_<status>, SDK_ERROR). ARM_INVALID is final:
a later invocation returns it again without any call (§3c).
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

from jev_probe.adapter import RunStop
from jev_probe.adapter_v2 import Spend
from jev_probe.adapter_v3 import LlmArmV3, llm_prompt
from jev_probe.analysis_v2 import set_tau, tau_from_json, tau_to_json, validation_rows
from jev_probe.cache import Cache, sha256_hex, utc_now
from jev_probe.constants_v2 import (
    CACHE_PATH as V2_CACHE_PATH,
    DESIGN_FACTS,
    FP_CEILING,
    LLM_BASE_URL,
    LLM_MODEL,
    LLM_PRICE_STATEMENT,
    LLM_SDK_VERSION,
    LLM_TEMPERATURE,
    LLM_USD_PER_INPUT_TOKEN,
    LLM_USD_PER_OUTPUT_TOKEN,
    SIBLING,
)
from jev_probe.constants_v3 import (
    CACHE_PATH,
    CAP_USD,
    HEALTH_MAX_INVALID_RATE,
    LLM_MAX_TOKENS,
    LLM_PREFILL,
    MANIFEST_PATH,
    PREREG_COMMIT,
    PREREG_TAG,
    REGISTRATION_ID,
    SMOKE_MAX_INVALID,
    SMOKE_N,
    TAU_PATH,
)
from jev_probe.corpus_v2 import (
    DesignMismatch,
    Item,
    build_items,
    design_facts,
    generator_sha256,
    perturbation,
    record_sha256,
    render,
)
from jev_probe.run_v2 import cached_calls, check_named_pin, engine_pins, registered_order, tau_committed

LLM_KEY_ENV = "ANTHROPIC_API_KEY"
ARM = "llm"


def preflight_v3(env: dict[str, str]) -> list[str]:
    """Problems that block the run. The key is checked for presence only and never printed."""
    problems = []
    if not env.get(LLM_KEY_ENV, "").strip():
        problems.append(f"missing {LLM_KEY_ENV}")
    pin = check_named_pin(SIBLING)
    if pin:
        problems.append(pin)
    if not V2_CACHE_PATH.exists():
        problems.append(f"jev-v2 cache missing at {V2_CACHE_PATH}")
    return problems


def base_manifest() -> dict[str, Any]:
    import anthropic

    return {
        "registration": REGISTRATION_ID,
        "prereg_tag": PREREG_TAG,
        "prereg_commit": PREREG_COMMIT,
        "engine_pins": engine_pins(),
        "sdks": {"anthropic": anthropic.__version__},
        "sdks_registered": {"anthropic": LLM_SDK_VERSION},
        "generator_sha256": generator_sha256(),
        "llm": {"base_url": LLM_BASE_URL, "requested_model": LLM_MODEL, "temperature": LLM_TEMPERATURE,
                "max_tokens": LLM_MAX_TOKENS, "prefill": LLM_PREFILL},
        "price": {"llm": {"usd_per_input_token": LLM_USD_PER_INPUT_TOKEN,
                          "usd_per_output_token": LLM_USD_PER_OUTPUT_TOKEN, "statement": LLM_PRICE_STATEMENT}},
        "cap": {"usd": CAP_USD},
        "fp_ceiling": FP_CEILING,
        "health_rule": {"smoke_n": SMOKE_N, "smoke_max_invalid": SMOKE_MAX_INVALID,
                        "validation_max_invalid_rate": HEALTH_MAX_INVALID_RATE},
        "llm_prompt_sha256": sha256_hex(llm_prompt("").encode("utf-8")),
        "carried_arm": {"arm": "jev", "cache": "responses/jev-v2.jsonl", "thresholds": "results/jev-v2.tau.json"},
        "python": platform.python_version(),
        "health": {},
    }


def write_manifest(manifest: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def check_carried(v2_calls: dict[tuple[str, int, str], dict[str, Any]], items: list[Item]) -> str | None:
    """Arm A must be complete in the jev-v2 cache, on byte-identical records."""
    for it in items:
        for noise in ("n00", "n10", "n30"):
            c = v2_calls.get(("jev", it.i, noise))
            if c is None:
                return f"CARRIED_ARM_INCOMPLETE: jev i={it.i} {noise} not in the jev-v2 cache"
            if c["record_sha256"] != record_sha256(render(it, noise)):
                return f"CORPUS_MISMATCH: i={it.i} {noise} differs from the jev-v2 cache"
    return None


def run(
    *,
    llm_key: str,
    cache_path: Path = CACHE_PATH,
    manifest_path: Path = MANIFEST_PATH,
    tau_path: Path = TAU_PATH,
    v2_cache_path: Path = V2_CACHE_PATH,
    llm_transport: httpx2.BaseTransport | None = None,
    is_committed: Callable[[Path], bool] = tau_committed,
    sleep: Callable[[float], None] | None = None,
    limit: int | None = None,
    cap_usd: float = CAP_USD,
    items: list[Item] | None = None,
    check_design: bool = True,
    log: Callable[[str], None] = print,
) -> str:
    cache = Cache(cache_path)
    segment = uuid.uuid4().hex[:12]
    manifest: dict[str, Any] = (
        json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else base_manifest()
    )
    manifest.setdefault("segments", [])
    seg: dict[str, Any] = {"segment": segment, "started_utc": utc_now()}
    manifest["segments"].append(seg)
    spend = Spend.from_cache(cache)
    arm: LlmArmV3 | None = None

    def finish(status: str, detail: str = "") -> str:
        seg.update({"ended_utc": utc_now(), "status": status, "detail": detail, "committed_usd_at_end": spend.usd})
        calls = cached_calls(cache)
        models = sorted({c["returned_model"] for (a, _, _), c in calls.items() if a == ARM})
        manifest.update({"status": status, "returned_models": {ARM: models},
                         "model_version_changed": len(models) > 1,
                         "n_calls_cached": {ARM: sum(1 for (a, _, _) in calls if a == ARM)}})
        write_manifest(manifest, manifest_path)
        cache.append({"kind": "run_event", "segment": segment, "utc": utc_now(), "status": status,
                      "detail": detail, "manifest": manifest})
        log(f"run_v3: {status} {detail}".rstrip())
        return status

    # §3c: ARM_INVALID ends jev-v3; no later invocation makes a call.
    if any(s.get("status") == "ARM_INVALID" for s in manifest["segments"][:-1]):
        return finish("ARM_INVALID", "a previous segment stopped on the arm health rule; not resumable")

    try:
        items = build_items() if items is None else items
        if check_design:
            facts = design_facts(items)
            if facts != DESIGN_FACTS:
                return finish("DESIGN_MISMATCH", json.dumps(facts))
    except DesignMismatch as exc:
        return finish("DESIGN_MISMATCH", str(exc))

    problem = check_carried(cached_calls(Cache(v2_cache_path)), items)
    if problem:
        status, _, detail = problem.partition(": ")
        return finish(status, detail)

    try:
        arm = LlmArmV3(cache, spend, api_key=llm_key, transport=llm_transport, sleep=sleep or time.sleep,
                       segment=segment, cap_usd=cap_usd)
        try:
            seg["llm_model_retrieved"] = arm.retrieve_model()
        except Exception as exc:  # noqa: BLE001
            return finish("DOCS_MISMATCH", f"GET /v1/models/{LLM_MODEL} failed: {type(exc).__name__}")
        seg["committed_usd_at_start"] = spend.usd
        write_manifest(manifest, manifest_path)  # prices, prompt hash and health rule before the first call
        cache.append({"kind": "manifest", "segment": segment, "utc": utc_now(), "manifest": manifest})

        done = cached_calls(cache)
        new = 0

        def do_record(it: Item, noise: str) -> dict[str, Any] | None:
            """The arm-B call record for (item, noise), cached or new; None when paused."""
            nonlocal new
            text = render(it, noise)
            sha = record_sha256(text)
            key = (ARM, it.i, noise)
            if key in done:
                if done[key]["record_sha256"] != sha:
                    raise RunStop("CORPUS_MISMATCH", f"{ARM} i={it.i} {noise}")
                return done[key]
            if limit is not None and new >= limit:
                return None
            res = arm.call(i=it.i, split=it.split, noise=noise, perturbation=perturbation(it, noise), text=text,
                           record_sha256=sha)
            new += 1
            done[key] = res.record
            return res.record

        def health(check: str, recs: list[dict[str, Any]], fired: bool) -> None:
            k = sum(r["status"] == "invalid" for r in recs)
            manifest["health"][check] = {"invalid": k, "n": len(recs), "stopped": fired}

        validation = registered_order(items, "validation")
        seen: list[dict[str, Any]] = []
        for idx, (it, noise) in enumerate(validation):
            rec = do_record(it, noise)
            if rec is None:
                return finish("PAUSED", f"limit {limit} reached")
            seen.append(rec)
            if idx + 1 == min(SMOKE_N, len(validation)):
                bad = sum(r["status"] == "invalid" for r in seen)
                health("smoke", seen, bad > SMOKE_MAX_INVALID)
                if bad > SMOKE_MAX_INVALID:
                    return finish("ARM_INVALID", f"smoke check: {bad} of {len(seen)} invalid (max {SMOKE_MAX_INVALID})")

        bad = sum(r["status"] == "invalid" for r in seen)
        fired = bad > HEALTH_MAX_INVALID_RATE * len(seen)
        health("validation", seen, fired)
        if fired:
            return finish("ARM_INVALID", f"validation health check: {bad} of {len(seen)} invalid "
                                         f"(max {HEALTH_MAX_INVALID_RATE:.0%})")

        calls = cached_calls(cache)
        taus = {ARM: set_tau(validation_rows(calls, items, ARM))}
        if not tau_path.exists():
            tau_path.parent.mkdir(parents=True, exist_ok=True)
            tau_path.write_text(json.dumps(tau_to_json(taus), indent=1, sort_keys=True) + "\n", encoding="utf-8")
            manifest["tau_sha256"] = sha256_hex(tau_path.read_bytes())
            return finish("TAU_WRITTEN", f"commit {tau_path.name}, then resume for the test split")
        if tau_from_json(json.loads(tau_path.read_text(encoding="utf-8"))) != taus:
            return finish("TAU_MISMATCH", "frozen thresholds differ from the cached validation data")
        if not is_committed(tau_path):
            return finish("TAU_NOT_COMMITTED", f"commit {tau_path.name} before any test-split call")
        manifest["tau_sha256"] = sha256_hex(tau_path.read_bytes())

        for it, noise in registered_order(items, "test"):
            if do_record(it, noise) is None:
                return finish("PAUSED", f"limit {limit} reached")
            if new and new % 300 == 0:
                log(f"run_v3: {new} new calls, USD {spend.usd:.6f}")
        return finish("COMPLETE")
    except RunStop as stop:
        return finish(stop.status, stop.detail)
    finally:
        if arm is not None:
            arm.close()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args(argv)
    env = dict(os.environ)
    problems = preflight_v3(env)
    if problems:
        print("preflight_v3: " + "; ".join(problems), file=sys.stderr)
        return 1
    print("preflight_v3: ok (Anthropic key present, sibling at pin, jev-v2 cache present)")
    status = run(llm_key=env[LLM_KEY_ENV].strip(), limit=args.limit)
    return 0 if status in ("COMPLETE", "PAUSED", "TAU_WRITTEN") else 2


if __name__ == "__main__":
    sys.exit(main())
