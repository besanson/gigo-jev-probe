"""Preflight for the gigo-jev-probe: checks the environment before any model call.

Reads configuration from the process environment only (load .env into the
environment first, e.g. ``set -a; . ./.env; set +a``). The API key is checked
for presence and never printed, logged, or echoed in any form.

Exit codes: 0 ready · 1 missing or invalid configuration · 2 sibling engine not at
the pin.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REQUIRED_ENV = ("JEV_API_KEY", "JEV_BASE_URL")
# The TypeSafe SDK's own variable is accepted in place of JEV_API_KEY.
KEY_ALIASES = {"JEV_API_KEY": "TYPESAFE_API_KEY"}
SYSTEM_ONE_ENDPOINT = "https://api.typesafe.ai/v1/systemone"


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


def check_pin(lock_path: Path = ROOT / "engines.lock") -> str | None:
    """Return an error message if the sibling engine is not at its pinned commit."""
    lock = tomllib.loads(lock_path.read_text(encoding="utf-8"))["dqSarc"]
    sibling = (lock_path.parent / lock["path"]).resolve()
    if not (sibling / ".git").exists():
        return f"sibling engine not found at {sibling}; clone {lock['url']} there"
    head = subprocess.run(
        ["git", "-C", str(sibling), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    if head != lock["commit"]:
        return f"sibling engine at {head or 'unknown'}, pinned {lock['commit']}"
    return None


def main(env: dict[str, str] | None = None) -> int:
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
    print(f"preflight: ok (API key present, endpoint {endpoint}, engine at pin)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
