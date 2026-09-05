"""`python -m afrd_filing NOTE.md [NOTE.md ...]` -- run the gate over notes on disk.

This exists for testing and for re-running the suite's sample-note results by
hand. It is not the interface: the gate runs on the report text a producer hands
back in conversation, before there is a file. There are no flags, no scheduling,
no server, and nothing here writes.

Exit status is 1 if any report was refused, so it composes with a shell.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from .failures import render
from .validate import validate
from .vault import DEFAULT_VAULT_ROOT, VaultError, load


def main(argv=None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in ("-h", "--help"):
        print(__doc__.strip())
        return 0

    root = Path(os.environ.get("AFRD_VAULT_ROOT", str(DEFAULT_VAULT_ROOT)))
    refused = 0
    for name in args:
        path = Path(name)
        try:
            # Loaded per report so a note validated from its own path does not
            # collide with itself on dedup.
            ok, failures = validate(path, vault=load(root, exclude=path))
        except (OSError, VaultError) as exc:
            print("ERROR %s: %s" % (path, exc))
            refused += 1
            continue
        print("%s %s" % ("PASS" if ok else "FAIL", path))
        if not ok:
            refused += 1
            print(_indent(render(failures)))
    return 1 if refused else 0


def _indent(text: str) -> str:
    return "\n".join("    " + line for line in text.splitlines())


if __name__ == "__main__":
    raise SystemExit(main())
