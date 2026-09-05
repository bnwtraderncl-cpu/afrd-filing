"""afrd_filing -- the checkable half of filing an AFRD research report.

    from afrd_filing import validate

    ok, failures = validate(report_text)
    if not ok:
        for f in failures:
            print(f)

`pass_fail_hold_standard.md` §1 divides every rule in that standard into `[C]`
checkable and `[J]` judgement. This package implements the `[C]` rules. The
`[J]` ones are the lead's, and §8 is the standard's own list of what no schema
makes mechanical.

The gate refuses on any failure (§7.1) and reports every failure it found, not
the first.

THIS PACKAGE WRITES NOTHING. Filing also writes registry entries and mints an
id; neither is here. See the README.
"""

from .failures import Failure, render
from .frontmatter import FrontmatterError, parse, split_frontmatter, yaml_blocks
from .rules import ENUMS, FORBIDDEN, MATRIX, OPTIONAL, REQUIRED
from .validate import validate
from .vault import Vault, VaultError, load

__all__ = [
    "validate",
    "Failure",
    "render",
    "Vault",
    "VaultError",
    "load",
    "FrontmatterError",
    "parse",
    "split_frontmatter",
    "yaml_blocks",
    "MATRIX",
    "ENUMS",
    "REQUIRED",
    "OPTIONAL",
    "FORBIDDEN",
]
