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

Round-three finding R3-1: the document toolchain is declared. Canonical: Pandoc 3.1.3 and
Tectonic 0.17.0. `--paper` prints both versions, and exits 3 with a message naming the
canonical version when Pandoc's major.minor is not 3.1, because other Pandoc writers produce a
different main.tex (release-check runs `preflight.py --paper` first). A different Tectonic
version is reported, not refused. Tectonic also needs its bundle (`default_bundle_v33`) either
cached or reachable over the network.
"""

from __future__ import annotations

import os
import re
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


CANONICAL_PANDOC = "3.1.3"
CANONICAL_TECTONIC = "0.17.0"
TECTONIC_BUNDLE = "default_bundle_v33"


def tool_version(cmd: list[str], run=subprocess.run) -> str | None:
    """The first dotted version number a tool prints for `cmd`, or None if it cannot run."""
    try:
        out = run(cmd, capture_output=True, text=True, check=False).stdout
    except OSError:
        return None
    m = re.search(r"(\d+(?:\.\d+)+)", out or "")
    return m.group(1) if m else None


def pandoc_matches(version: str | None, canonical: str = CANONICAL_PANDOC) -> bool:
    """major.minor must equal the canonical Pandoc's (3.1)."""
    return version is not None and version.split(".")[:2] == canonical.split(".")[:2]


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
        tools = paper_tools()
        lines, ok = paper_report(tools)
        pandoc = tool_version(["pandoc", "--version"]) if tools.get("pandoc") else None
        tectonic = tool_version(["tectonic", "--version"]) if tools.get("tectonic") else None
        lines.append(f"  pandoc version: {pandoc or 'unknown'} (canonical {CANONICAL_PANDOC})")
        lines.append(f"  tectonic version: {tectonic or 'not found'} (canonical {CANONICAL_TECTONIC}; "
                     f"bundle {TECTONIC_BUNDLE}, cached or over the network)")
        if tools.get("pandoc") and not pandoc_matches(pandoc):
            lines.append(f"  ERROR: Pandoc {pandoc} is not {CANONICAL_PANDOC.rsplit('.', 1)[0]}.x; install Pandoc "
                         f"{CANONICAL_PANDOC} (other writers produce a different paper-tex/main.tex, see README)")
            ok = False
        if tectonic and tectonic != CANONICAL_TECTONIC:
            lines.append(f"  note: Tectonic {tectonic} is not the canonical {CANONICAL_TECTONIC}")
        print("preflight --paper: " + ("ok" if ok else "toolchain not ready (see README, Paper 6)"))
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
