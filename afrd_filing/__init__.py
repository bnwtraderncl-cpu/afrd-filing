"""afrd_filing -- filing an AFRD research report: the checks, and the writes.

    from afrd_filing import validate, file_report

    ok, failures = validate(report_text)       # check only, writes nothing
    filed, where = file_report(report_text)    # check, mint, write -- or refuse

`pass_fail_hold_standard.md` §1 divides every rule in that standard into `[C]`
checkable and `[J]` judgement. This package implements the `[C]` rules. The
`[J]` ones are the lead's, and §8 is the standard's own list of what no schema
makes mechanical.

The gate refuses on any failure (§7.1) and reports every failure it found, not
the first.

TWO HALVES, AND WHICH ONE WRITES
--------------------------------
`validate` and everything it uses -- `rules`, `frontmatter`, `vault`, `failures`
-- write nothing, and `tests/test_read_only.py` asserts that against their
source. `filing` is the half that writes: it mints the `artifact_id` through
`afrd-ids`, writes the report's proposed `CONV-` entries to `conventions.md`,
and writes the note. It writes to those two destinations and no other, and only
once every check has passed. See `filing.py` on why the write is staged.
"""

from .failures import Failure, render
from .filing import file_report
from .frontmatter import FrontmatterError, parse, split_frontmatter, yaml_blocks
from .rules import ENUMS, FORBIDDEN, MATRIX, OPTIONAL, REQUIRED
from .validate import validate
from .vault import Vault, VaultError, load

__all__ = [
    "validate",
    "file_report",
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
