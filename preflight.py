"""Preflight for the gigo-jev-probe: checks the environment before any model call.

Reads configuration from the process environment only (load .env into the
environment first, e.g. ``set -a; . ./.env; set +a``). The API key is checked
for presence and never printed, logged, or echoed in any form.

Exit codes: 0 ready · 1 missing or invalid configuration · 2 a sibling engine (dqSarc or
sarc-authority-derivation) missing or not at its pin.

    python preflight.py --paper   # report the paper 6 build toolchain; no key needed, no call made

The paper report (round-one finding F2) lists the tools `make paper` and `make release-check`
need: a TeX engine (tectonic, the canonical one, or latexmk), lmodern.sty as kpsewhich finds it
(a TeX Live install; Tectonic fetches lmodern from its own bundle instead), pandoc and pdftotext
(with pdfinfo, from poppler-utils). It exits 3 if the engine, pandoc or pdftotext is missing.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REQUIRED_ENV = ("JEV_API_KEY", "JEV_BASE_URL")
# The TypeSafe SDK's own variable is accepted in place of JEV_API_KEY.
KEY_ALIASES = {"JEV_API_KEY": "TYPESAFE_API_KEY"}
SYSTEM_ONE_ENDPOINT = "https://api.typesafe.ai/v1/systemone"
# Both siblings are required: dqSarc for jev-v1, sarc-authority-derivation for jev-v2/v3 and the tests.
SIBLINGS = ("dqSarc", "sarc-authority-derivation")


def check_env(env: dict[str, str]) -> list[str]:
    """Return the names of required variables that are missing or blank."""
    return [
        name
        for name in REQUIRED_ENV
        if not env.get(name, "").strip() and not env.get(KEY_ALIASES.get(name, ""), "").strip()
    ]


def resolve_endpoint(base_url: str) -> str:
    """The System One endpoint the SDK will call for ``base_url`` (a trailing /v1 is stripped)."""
    root = base_url.strip().rstrip("/")
    if root.endswith("/v1"):
        root = root[: -len("/v1")]
    return root + "/v1/systemone"


def check_pin(lock_path: Path = ROOT / "engines.lock", names: tuple[str, ...] = SIBLINGS) -> str | None:
    """Return an error message if a sibling engine is missing or not at its pinned commit."""
    locks = tomllib.loads(lock_path.read_text(encoding="utf-8"))
    for name in names:
        if name not in locks:
            return f"{name} has no entry in {lock_path.name}"
        lock = locks[name]
        sibling = (lock_path.parent / lock["path"]).resolve()
        if not (sibling / ".git").exists():
            return f"sibling engine {name} not found at {sibling}; clone {lock['url']} there"
        head = subprocess.run(
            ["git", "-C", str(sibling), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        ).stdout.strip()
        if head != lock["commit"]:
            return f"sibling engine {name} at {head or 'unknown'}, pinned {lock['commit']}"
    return None


def paper_tools(which=shutil.which, run=subprocess.run) -> dict[str, str | None]:
    """Where each paper build tool is found (None if absent). lmodern.sty is looked up with
    kpsewhich, which only a TeX Live style installation has."""
    found: dict[str, str | None] = {name: which(name) for name in ("tectonic", "latexmk", "pandoc", "pdftotext", "pdfinfo")}
    lmodern = None
    if which("kpsewhich"):
        out = run(["kpsewhich", "lmodern.sty"], capture_output=True, text=True, check=False).stdout.strip()
        lmodern = out or None
    found["lmodern.sty"] = lmodern
    return found


def paper_report(tools: dict[str, str | None]) -> tuple[list[str], bool]:
    engine = tools.get("tectonic") or tools.get("latexmk")
    lines = [f"  {name}: {path or 'not found'}" for name, path in tools.items()]
    if tools.get("lmodern.sty") is None and tools.get("tectonic"):
        lines.append("  (lmodern.sty not on a TeX Live path; Tectonic supplies it from its bundle)")
    ok = bool(engine) and bool(tools.get("pandoc")) and bool(tools.get("pdftotext"))
    if tools.get("latexmk") and not tools.get("tectonic") and tools.get("lmodern.sty") is None:
        ok = False
    return lines, ok


def main(env: dict[str, str] | None = None, argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if "--paper" in argv:
        lines, ok = paper_report(paper_tools())
        print("preflight --paper: " + ("ok" if ok else "missing tools (see README, Paper 6)"))
        print("\n".join(lines))
        return 0 if ok else 3
    env = dict(os.environ) if env is None else env
    missing = check_env(env)
    if missing:
        print(
            f"preflight: missing {', '.join(missing)}. Set the missing values in .env "
            "(see .env.example) and load it into the environment before running.",
            file=sys.stderr,
        )
        return 1
    endpoint = resolve_endpoint(env["JEV_BASE_URL"])
    if endpoint != SYSTEM_ONE_ENDPOINT:
        print(
            f"preflight: JEV_BASE_URL resolves to {endpoint}, expected {SYSTEM_ONE_ENDPOINT}",
            file=sys.stderr,
        )
        return 1
    pin_error = check_pin()
    if pin_error:
        print(f"preflight: {pin_error}", file=sys.stderr)
        return 2
    print(f"preflight: ok (API key present, endpoint {endpoint}, both sibling engines at their pins)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
