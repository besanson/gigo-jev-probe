"""jev-v2 Phase B runner (prereg/jev-v2.md §10), resumable from the cache.

    python -m jev_probe.run_v2            # preflight, verify, then run or resume
    python -m jev_probe.run_v2 --limit N  # stop after N new API calls (smoke/resume testing)

Two stages, in registered order (validation items, then test items; noise 0 → 10 → 30; arm
A → B → C within a record):

1. Validation. When every validation record is cached, the thresholds τ are computed per arm
   and written to results/jev-v2.tau.json, and the run stops with status TAU_WRITTEN. The
   operator commits that file.
2. Test. The run refuses to make any test-split call unless the τ file is committed (tracked
   and unmodified in git) and equals the thresholds recomputed from the cached validation data.

Status is one of COMPLETE, TAU_WRITTEN, PAUSED, CAP_TRUNCATED, RETRY_EXHAUSTED, DOCS_MISMATCH,
TAU_NOT_COMMITTED, TAU_MISMATCH, DESIGN_MISMATCH, PREFLIGHT_FAILED, or an aborting error
(ENDPOINT_MISMATCH, HTTP_<status>, SDK_ERROR).
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
import time
import tomllib
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx2

import preflight
from jev_probe.adapter import RunStop
from jev_probe.adapter_v2 import JevArm, LlmArm, Spend, jev_questions_wire, llm_prompt
from jev_probe.analysis_v2 import NOISES, set_tau, tau_from_json, tau_to_json, validation_rows
from jev_probe.cache import Cache, sha256_hex, utc_now
from jev_probe.constants import DOCS_URL, ENDPOINT, MODEL as JEV_MODEL, ROOT, SDK_VERSION
from jev_probe.constants_v2 import (
    CACHE_PATH,
    CAP_USD,
    DESIGN_FACTS,
    FP_CEILING,
    JEV_CONTEXT,
    JEV_USD_PER_INPUT_TOKEN,
    JEV_USD_PER_OUTPUT_TOKEN,
    LLM_BASE_URL,
    LLM_MAX_TOKENS,
    LLM_MODEL,
    LLM_PRICE_STATEMENT,
    LLM_SDK_VERSION,
    LLM_TEMPERATURE,
    LLM_USD_PER_INPUT_TOKEN,
    LLM_USD_PER_OUTPUT_TOKEN,
    MANIFEST_PATH,
    PREREG_COMMIT,
    PREREG_TAG,
    SIBLING,
    TAU_PATH,
)
from jev_probe.corpus_v2 import (
    DesignMismatch,
    Item,
    build_items,
    design_facts,
    generator_sha256,
    keyword_score,
    perturbation,
    record_sha256,
    render,
)
from jev_probe.run import check_docs, fetch_docs

LLM_KEY_ENV = "ANTHROPIC_API_KEY"


# ------------------------------------------------------------------ preflight (§12.2)


def check_named_pin(name: str, lock_path: Path = ROOT / "engines.lock") -> str | None:
    lock = tomllib.loads(lock_path.read_text(encoding="utf-8"))[name]
    sibling = (lock_path.parent / lock["path"]).resolve()
    if not (sibling / ".git").exists():
        return f"{name} not found at {sibling}; clone {lock['url']} there"
    head = subprocess.run(["git", "-C", str(sibling), "rev-parse", "HEAD"], capture_output=True, text=True,
                          check=False).stdout.strip()
    if head != lock["commit"]:
        return f"{name} at {head or 'unknown'}, pinned {lock['commit']}"
    return None


def preflight_v2(env: dict[str, str]) -> list[str]:
    """Problems that block the run. Keys are checked for presence only and never printed."""
    problems = [f"missing {n}" for n in preflight.check_env(env)]
    if not env.get(LLM_KEY_ENV, "").strip():
        problems.append(f"missing {LLM_KEY_ENV}")
    if env.get("JEV_BASE_URL", "").strip() and preflight.resolve_endpoint(env["JEV_BASE_URL"]) != ENDPOINT:
        problems.append(f"JEV_BASE_URL does not resolve to {ENDPOINT}")
    pin = check_named_pin(SIBLING)
    if pin:
        problems.append(pin)
    return problems


# ------------------------------------------------------------------ manifest


def engine_pins() -> dict[str, str]:
    lock = tomllib.loads((ROOT / "engines.lock").read_text(encoding="utf-8"))
    return {name: sec["commit"] for name, sec in lock.items()}


def sdk_versions() -> dict[str, str]:
    import anthropic
    from typesafe_sdk import __version__ as ts

    return {"typesafe-sdk": ts, "anthropic": anthropic.__version__}


def base_manifest() -> dict[str, Any]:
    return {
        "registration": "jev-v2",
        "prereg_tag": PREREG_TAG,
        "prereg_commit": PREREG_COMMIT,
        "engine_pins": engine_pins(),
        "sdks": sdk_versions(),
        "sdks_registered": {"typesafe-sdk": SDK_VERSION, "anthropic": LLM_SDK_VERSION},
        "generator_sha256": generator_sha256(),
        "jev": {"endpoint": ENDPOINT, "requested_model": JEV_MODEL},
        "llm": {"base_url": LLM_BASE_URL, "requested_model": LLM_MODEL, "temperature": LLM_TEMPERATURE,
                "max_tokens": LLM_MAX_TOKENS},
        "price": {
            "jev": {"usd_per_input_token": JEV_USD_PER_INPUT_TOKEN, "usd_per_output_token": JEV_USD_PER_OUTPUT_TOKEN,
                    "statement": "USD 42 per 1e9 input tokens, output free (jev-v1 §6)"},
            "llm": {"usd_per_input_token": LLM_USD_PER_INPUT_TOKEN, "usd_per_output_token": LLM_USD_PER_OUTPUT_TOKEN,
                    "statement": LLM_PRICE_STATEMENT},
        },
        "cap": {"usd": CAP_USD},
        "fp_ceiling": FP_CEILING,
        "jev_context_sha256": sha256_hex(JEV_CONTEXT.encode("utf-8")),
        "jev_question_sha256": sha256_hex(json.dumps(jev_questions_wire(), separators=(",", ":")).encode()),
        "llm_prompt_sha256": sha256_hex(llm_prompt("").encode("utf-8")),
        "python": platform.python_version(),
    }


def write_manifest(manifest: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


# ------------------------------------------------------------------ τ gate (§7)


def tau_committed(path: Path = TAU_PATH) -> bool:
    """Tracked in git and identical to HEAD."""
    rel = str(path.resolve().relative_to(ROOT))
    tracked = subprocess.run(["git", "-C", str(ROOT), "ls-files", "--error-unmatch", rel],
                             capture_output=True, check=False).returncode == 0
    clean = subprocess.run(["git", "-C", str(ROOT), "diff", "--quiet", "HEAD", "--", rel],
                           capture_output=True, check=False).returncode == 0
    return tracked and clean


def registered_order(items: list[Item], split: str) -> list[tuple[Item, str]]:
    return [(it, n) for it in sorted(items, key=lambda x: x.i) if it.split == split for n in NOISES]


def cached_calls(cache: Cache) -> dict[tuple[str, int, str], dict[str, Any]]:
    return {(r["arm"], r["i"], r["noise"]): r for r in cache.records() if r.get("kind") == "call"}


# ------------------------------------------------------------------ run


def run(
    *,
    jev_key: str,
    jev_base_url: str,
    llm_key: str,
    cache_path: Path = CACHE_PATH,
    manifest_path: Path = MANIFEST_PATH,
    tau_path: Path = TAU_PATH,
    jev_transport: httpx2.BaseTransport | None = None,
    llm_transport: httpx2.BaseTransport | None = None,
    docs_fetch: Callable[[], bytes] = fetch_docs,
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
    arms: dict[str, Any] = {}

    def finish(status: str, detail: str = "") -> str:
        seg.update({"ended_utc": utc_now(), "status": status, "detail": detail, "committed_usd_at_end": spend.usd})
        calls = cached_calls(cache)
        models = {arm: sorted({c["returned_model"] for (a, _, _), c in calls.items() if a == arm})
                  for arm in ("jev", "llm")}
        manifest.update({"status": status, "returned_models": models,
                         "model_version_changed": any(len(m) > 1 for m in models.values()),
                         "n_calls_cached": {arm: sum(1 for (a, _, _) in calls if a == arm)
                                            for arm in ("jev", "llm", "kw")}})
        write_manifest(manifest, manifest_path)
        cache.append({"kind": "run_event", "segment": segment, "utc": utc_now(), "status": status,
                      "detail": detail, "manifest": manifest})
        log(f"run_v2: {status} {detail}".rstrip())
        return status

    # §3.5: population and design facts must match before any model call.
    try:
        items = build_items() if items is None else items
        if check_design:
            facts = design_facts(items)
            if facts != DESIGN_FACTS:
                return finish("DESIGN_MISMATCH", json.dumps(facts))
    except DesignMismatch as exc:
        return finish("DESIGN_MISMATCH", str(exc))

    try:
        arms["jev"] = JevArm(cache, spend, api_key=jev_key, base_url=jev_base_url, transport=jev_transport,
                             sleep=sleep or time.sleep, segment=segment, cap_usd=cap_usd)
        arms["llm"] = LlmArm(cache, spend, api_key=llm_key, transport=llm_transport,
                             sleep=sleep or time.sleep, segment=segment, cap_usd=cap_usd)
    except RunStop as stop:
        return finish(stop.status, stop.detail)

    try:
        # Run-time verification before any inference call (jev-v1 §3a for Jev; model lookup for B).
        docs = docs_fetch()
        seg["docs_url"] = DOCS_URL
        seg["docs_sha256"] = manifest["docs_sha256"] = sha256_hex(docs)
        missing = check_docs(docs)
        if missing:
            return finish("DOCS_MISMATCH", f"not on {DOCS_URL}: {missing}")
        try:
            models = arms["jev"].list_models()
        except Exception as exc:  # noqa: BLE001
            return finish("DOCS_MISMATCH", f"GET /v1/models failed: {type(exc).__name__}")
        seg["jev_models_listed"] = models
        if JEV_MODEL not in models:
            return finish("DOCS_MISMATCH", f"{JEV_MODEL} not in GET /v1/models: {models}")
        try:
            seg["llm_model_retrieved"] = arms["llm"].retrieve_model()
        except Exception as exc:  # noqa: BLE001
            return finish("DOCS_MISMATCH", f"GET /v1/models/{LLM_MODEL} failed: {type(exc).__name__}")
        seg["committed_usd_at_start"] = spend.usd
        write_manifest(manifest, manifest_path)  # prices etc. recorded before the first call
        cache.append({"kind": "manifest", "segment": segment, "utc": utc_now(), "manifest": manifest})

        done = cached_calls(cache)
        new = 0

        def do_record(it: Item, noise: str) -> str | None:
            nonlocal new
            text = render(it, noise)
            meta = {"i": it.i, "split": it.split, "noise": noise, "perturbation": perturbation(it, noise),
                    "text": text, "record_sha256": record_sha256(text)}
            for arm in ("jev", "llm"):
                if (arm, it.i, noise) in done:
                    if done[(arm, it.i, noise)]["record_sha256"] != meta["record_sha256"]:
                        raise RunStop("CORPUS_MISMATCH", f"{arm} i={it.i} {noise}")
                    continue
                if limit is not None and new >= limit:
                    return "PAUSED"
                arms[arm].call(**meta)
                new += 1
            if ("kw", it.i, noise) not in done:
                cache.append({"kind": "call", "segment": segment, "arm": "kw", "i": it.i, "split": it.split,
                              "noise": noise, "perturbation": meta["perturbation"],
                              "record_sha256": meta["record_sha256"], "n_requests": 0, "status": "ok",
                              "score": keyword_score(text), "returned_model": "n/a", "latency_total_s": 0.0,
                              "done_utc": utc_now()})
            return None

        for it, noise in registered_order(items, "validation"):
            if do_record(it, noise):
                return finish("PAUSED", f"limit {limit} reached")

        # §7: thresholds from the validation split, frozen and committed before any test call.
        calls = cached_calls(cache)
        taus = {arm: set_tau(validation_rows(calls, items, arm)) for arm in ("jev", "llm", "kw")}
        if not tau_path.exists():
            tau_path.parent.mkdir(parents=True, exist_ok=True)
            tau_path.write_text(json.dumps(tau_to_json(taus), indent=1, sort_keys=True) + "\n", encoding="utf-8")
            manifest["tau_sha256"] = sha256_hex(tau_path.read_bytes())
            return finish("TAU_WRITTEN", f"commit {tau_path.name}, then resume for the test split")
        frozen = tau_from_json(json.loads(tau_path.read_text(encoding="utf-8")))
        if frozen != taus:
            return finish("TAU_MISMATCH", "frozen thresholds differ from the cached validation data")
        if not is_committed(tau_path):
            return finish("TAU_NOT_COMMITTED", f"commit {tau_path.name} before any test-split call")
        manifest["tau_sha256"] = sha256_hex(tau_path.read_bytes())

        for it, noise in registered_order(items, "test"):
            if do_record(it, noise):
                return finish("PAUSED", f"limit {limit} reached")
            if new and new % 150 == 0:
                log(f"run_v2: {new} new calls, USD {spend.usd:.6f}")
        return finish("COMPLETE")
    except RunStop as stop:
        return finish(stop.status, stop.detail)
    finally:
        for a in arms.values():
            a.close()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args(argv)
    env = dict(os.environ)
    problems = preflight_v2(env)
    if problems:
        print("preflight_v2: " + "; ".join(problems), file=sys.stderr)
        return 1
    print("preflight_v2: ok (both keys present, Jev endpoint, sibling at pin)")
    jev_key = env.get("JEV_API_KEY", "").strip() or env.get("TYPESAFE_API_KEY", "").strip()
    status = run(jev_key=jev_key, jev_base_url=env["JEV_BASE_URL"], llm_key=env[LLM_KEY_ENV].strip(),
                 limit=args.limit)
    return 0 if status in ("COMPLETE", "PAUSED", "TAU_WRITTEN") else 2


if __name__ == "__main__":
    sys.exit(main())
