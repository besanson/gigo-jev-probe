"""Run every paper 6 checker into one directory: python -m checkers.run_all [OUT_DIR]."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

from checkers._common import OUT_DIR, write_output

CHECKERS = ("s1_check", "s2_check", "s3_check", "n6_witness")


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    out = Path(args[0]) if args else OUT_DIR
    failed = []
    for name in CHECKERS:
        mod = importlib.import_module(f"checkers.{name}")
        result = mod.run()
        write_output(name, mod.STATEMENT, mod.INPUTS, result, out)
        if not result["holds"]:
            failed.append(name)
        print(f"{name}: {'holds' if result['holds'] else 'FAILS'}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
