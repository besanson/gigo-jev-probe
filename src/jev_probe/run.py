"""Phase B runner: 1,800 calls in registered order, resumable from the cache.

Usage (after `set -a; . ./.env; set +a` or with the variables already exported):

    python -m jev_probe.run            # verify (§3a), then run or resume
    python -m jev_probe.run --limit N  # stop after N new calls (smoke/resume testing)

Status is one of COMPLETE, CAP_TRUNCATED, RETRY_EXHAUSTED, DOCS_MISMATCH, or an
aborting error (ENDPOINT_MISMATCH, ITEM_CONSTRUCTION_FAILED, HTTP_<status>, SDK_ERROR).
"""

from __future__ import annotations

import argparse
import html
import json
import os
import platform
import re
import sys
import time
import tomllib
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx2

import preflight
from jev_probe.adapter import JevAdapter, RunStop
from jev_probe.cache import Cache, sha256_hex, utc_now
from jev_probe.constants import (
    BACKOFF_INITIAL_S,
    BACKOFF_MAX_S,
    CACHE_PATH,
    CAP_INPUT_TOKENS,
    CAP_USD,
    CONDITIONS,
    CONTEXT,
    DOCS_ENDPOINT_STRING,
    DOCS_URL,
    ENDPOINT,
    MANIFEST_PATH,
    MAX_RETRIES,
    MODEL,
    PREREG_COMMIT,
    PREREG_TAG,
    REPEATS,
    ROOT,
    SDK_VERSION,
    USD_PER_INPUT_TOKEN,
    USD_PER_OUTPUT_TOKEN,
)
from jev_probe.items import Item, ItemConstructionError, build_items
from jev_probe.questions import questions_wire


def registered_order(items: list[Item]) -> list[tuple[Item, str, int]]:
    """Item j ascending, then P before PM, then repeat 1 -> 3 (§9)."""
    return [(it, c, r) for it in sorted(items, key=lambda x: x.j) for c in CONDITIONS
            for r in range(1, REPEATS + 1)]


def html_text(raw: bytes) -> str:
    t = raw.decode("utf-8", errors="replace")
    t = re.sub(r"<script.*?</script>|<style.*?</style>", " ", t, flags=re.S | re.I)
    t = html.unescape(re.sub(r"<[^>]+>", " ", t))
    return re.sub(r"\s+", " ", t)


def check_docs(raw: bytes) -> list[str]:
    """Registered strings that do NOT appear on the docs page (raw or as rendered text)."""
    text = html_text(raw)
    src = raw.decode("utf-8", errors="replace")
    return [s for s in (DOCS_ENDPOINT_STRING, MODEL) if s not in src and s not in text]


def fetch_docs() -> bytes:
    with httpx2.Client(timeout=30.0, follow_redirects=True) as c:
        r = c.get(DOCS_URL)
        r.raise_for_status()
        return r.content


def engine_pin() -> dict[str, str]:
    lock = tomllib.loads((ROOT / "engines.lock").read_text(encoding="utf-8"))["dqSarc"]
    return {"url": lock["url"], "commit": lock["commit"]}


def sdk_version() -> str:
    from typesafe_sdk import __version__

    return __version__


def base_manifest() -> dict[str, Any]:
    return {
        "registration": "jev-v1",
        "prereg_tag": PREREG_TAG,
        "prereg_commit": PREREG_COMMIT,
        "engine_pin": engine_pin(),
        "sdk": {"name": "typesafe-sdk", "version": sdk_version(), "registered": SDK_VERSION},
        "endpoint": ENDPOINT,
        "requested_model": MODEL,
        "price": {"usd_per_input_token": USD_PER_INPUT_TOKEN,
                  "usd_per_output_token": USD_PER_OUTPUT_TOKEN,
                  "statement": "USD 42 per 1e9 input tokens, output free (prereg §6)"},
        "cap": {"usd": CAP_USD, "input_tokens": CAP_INPUT_TOKENS},
        "retry": {"initial_s": BACKOFF_INITIAL_S, "max_s": BACKOFF_MAX_S, "max_retries": MAX_RETRIES,
                  "sdk_retry_policy": "RetryPolicy(max_retries=0)"},
        "context": CONTEXT,
        "context_sha256": sha256_hex(CONTEXT.encode("utf-8")),
        "questions_sha256": sha256_hex(json.dumps(questions_wire(), separators=(",", ":")).encode()),
        "python": platform.python_version(),
    }


def write_manifest(manifest: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def done_calls(cache: Cache) -> set[tuple[int, str, int]]:
    return {(r["j"], r["condition"], r["repeat"]) for r in cache.records() if r.get("kind") == "call"}


def run(
    *,
    api_key: str,
    base_url: str,
    cache_path: Path = CACHE_PATH,
    manifest_path: Path = MANIFEST_PATH,
    transport: httpx2.BaseTransport | None = None,
    docs_fetch: Callable[[], bytes] = fetch_docs,
    sleep: Callable[[float], None] | None = None,
    limit: int | None = None,
    cap_usd: float = CAP_USD,
    cap_input_tokens: int = CAP_INPUT_TOKENS,
    items: list[Item] | None = None,
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

    adapter: JevAdapter | None = None

    def finish(status: str, detail: str = "") -> str:
        seg.update({"ended_utc": utc_now(), "status": status, "detail": detail})
        if adapter is not None:
            seg["committed_usd_at_end"] = adapter.spend.usd
            seg["committed_input_tokens_at_end"] = adapter.spend.input_tokens
        models = sorted({r["returned_model"] for r in cache.records() if r.get("kind") == "call"})
        manifest.update({"status": status, "returned_models": models,
                         "model_version_changed": len(models) > 1,
                         "n_calls_cached": len(done_calls(cache))})
        write_manifest(manifest, manifest_path)
        cache.append({"kind": "run_event", "segment": segment, "utc": utc_now(), "status": status,
                      "detail": detail, "manifest": manifest})
        log(f"run: {status} {detail}".rstrip())
        return status

    # §2.5: all items must construct before any model call.
    try:
        items = build_items() if items is None else items
    except ItemConstructionError as exc:
        return finish("ITEM_CONSTRUCTION_FAILED", str(exc))

    try:
        adapter = JevAdapter(cache, api_key=api_key, base_url=base_url, transport=transport,
                             sleep=sleep or time.sleep, cap_usd=cap_usd,
                             cap_input_tokens=cap_input_tokens, segment=segment)
    except RunStop as stop:
        return finish(stop.status, stop.detail)

    try:
        # §3a run-time verification before any inference call.
        docs = docs_fetch()
        missing = check_docs(docs)
        seg["docs_url"] = DOCS_URL
        seg["docs_sha256"] = sha256_hex(docs)
        manifest["docs_sha256"] = seg["docs_sha256"]
        if missing:
            return finish("DOCS_MISMATCH", f"not on {DOCS_URL}: {missing}")
        try:
            models = adapter.list_models()
        except Exception as exc:  # noqa: BLE001 - any failure to list is a mismatch
            return finish("DOCS_MISMATCH", f"GET /v1/models failed: {type(exc).__name__}")
        seg["models_listed"] = models
        if MODEL not in models:
            return finish("DOCS_MISMATCH", f"{MODEL} not in GET /v1/models: {models}")
        seg["committed_usd_at_start"] = adapter.spend.usd
        write_manifest(manifest, manifest_path)  # price etc. recorded before the first call
        cache.append({"kind": "manifest", "segment": segment, "utc": utc_now(), "manifest": manifest})

        done = done_calls(cache)
        new = 0
        seen_models: set[str] = {r["returned_model"] for r in cache.records() if r.get("kind") == "call"}
        for item, cond, rep in registered_order(items):
            if (item.j, cond, rep) in done:
                continue
            if limit is not None and new >= limit:
                return finish("PAUSED", f"limit {limit} reached")
            res = adapter.call(j=item.j, i=item.i, condition=cond, repeat=rep, state=item.state(cond))
            new += 1
            m = res.record["returned_model"]
            if seen_models and m not in seen_models:
                log(f"run: MODEL_VERSION_CHANGED -> {m}")
            seen_models.add(m)
            if new % 60 == 0:
                log(f"run: {len(done) + new}/1800 calls, USD {adapter.spend.usd:.6f}, "
                    f"tokens {adapter.spend.input_tokens}, model {m}")
        return finish("COMPLETE")
    except RunStop as stop:
        return finish(stop.status, stop.detail)
    finally:
        adapter.close()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args(argv)
    env = dict(os.environ)
    if preflight.main(env) != 0:
        return 1
    key = env.get("JEV_API_KEY", "").strip() or env.get("TYPESAFE_API_KEY", "").strip()
    status = run(api_key=key, base_url=env["JEV_BASE_URL"], limit=args.limit)
    return 0 if status in ("COMPLETE", "PAUSED") else 2


if __name__ == "__main__":
    sys.exit(main())
