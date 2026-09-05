"""The CHECKING half writes nothing, asserted against this working tree.

`pass_fail_hold_standard.md` section 7.1 makes registry writes part of filing,
so this package now contains a module that writes. That is exactly why the
property is still worth asserting on the rest: the writing half exists, and the
checking half must not grow one by accident or by importing its way into one.
`afrd-ids` asserts its own no-local-time property the same way, by scanning its
source rather than trusting that nobody added one.

`filing.py` is excluded BY NAME below, not by a pattern, so a new module joins
the guarded set by default and leaving it out has to be deliberate. Its own
writes are guarded differently -- every path goes through `_guard_target`, and
`test_filing.py` asserts both destinations and the refusal of a third.

This is a source scan, so it catches the shape of a write, not a write reached
through a name it cannot see. That is the same bound `afrd-ids` accepts, and it
is worth having: the failure being guarded against is someone adding an obvious
`open(..., "w")` while extending a check, not someone hiding one.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parents[1] / "afrd_filing"

# The one module allowed to write, and the reason this list is a list.
WRITING_MODULES = {"filing.py"}

_WRITING_MODES = ("w", "a", "x", "+")

# Method names that are a filesystem mutation whatever the receiver is. The
# generic ones -- `replace`, `remove`, `copy`, `move` -- are deliberately NOT
# here: `datetime.replace(tzinfo=...)` and `str.replace` are neither writes nor
# rare, and a guard that cries wolf on those gets deleted. They are caught
# below instead, where the receiver says which `replace` it is.
_WRITING_METHODS = {
    "write_text",
    "write_bytes",
    "writelines",
    "mkdir",
    "touch",
    "unlink",
    "rmdir",
    "rename",
    "symlink_to",
    "hardlink_to",
    "chmod",
}

# Everything on `os` and `shutil` is assumed to mutate unless it is here.
_READ_ONLY_OS = {"walk", "environ", "getenv", "fspath", "sep", "path", "listdir",
                 "scandir", "stat", "getcwd"}


def sources():
    return sorted(p for p in PACKAGE.glob("*.py") if p.name not in WRITING_MODULES)


def test_the_writing_module_is_where_it_is_expected():
    """If `filing.py` is renamed, the exclusion above must follow it."""
    assert (PACKAGE / "filing.py").is_file(), (
        "filing.py has moved, and the read-only guard is now excluding a module "
        "that does not exist while scanning nothing that writes"
    )


def test_the_package_has_sources_to_scan():
    assert sources(), "nothing to scan: the package moved"


@pytest.mark.parametrize("path", sources(), ids=lambda p: p.name)
def test_no_file_is_opened_for_writing(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _callee(node)
        if name in ("open", "Path.open"):
            mode = _mode_argument(node)
            assert not any(m in mode for m in _WRITING_MODES), (
                "%s:%d opens a file with mode %r. The gate reads the vault and "
                "writes nothing." % (path.name, node.lineno, mode)
            )


@pytest.mark.parametrize("path", sources(), ids=lambda p: p.name)
def test_no_filesystem_mutation_is_called(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        attr = node.func.attr
        receiver = node.func.value
        module = receiver.id if isinstance(receiver, ast.Name) else None

        assert attr not in _WRITING_METHODS, (
            "%s:%d calls %s(). The gate reads the vault and writes nothing; the "
            "writing half of filing is a separate module that does not exist "
            "yet." % (path.name, node.lineno, attr)
        )
        if module in ("os", "shutil"):
            assert attr in _READ_ONLY_OS, (
                "%s:%d calls %s.%s(), which is not one of the read-only calls "
                "this package is allowed. The gate writes nothing."
                % (path.name, node.lineno, module, attr)
            )


def test_validate_leaves_the_vault_byte_identical(vault):
    """The property itself, not just its shape in the source."""
    from afrd_filing import validate
    from conftest import GOOD_REPORT

    before = {p: p.read_bytes() for p in sorted(vault.rglob("*")) if p.is_file()}
    validate(GOOD_REPORT, vault_root=vault)
    validate(GOOD_REPORT.replace("outcome: pass", "outcome: nonsense"), vault_root=vault)
    after = {p: p.read_bytes() for p in sorted(vault.rglob("*")) if p.is_file()}
    assert before == after


def _callee(node: ast.Call) -> str:
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return "Path.open" if func.attr == "open" else func.attr
    return ""


def _mode_argument(node: ast.Call) -> str:
    for index, arg in enumerate(node.args):
        if index == 1 and isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            return arg.value
    for keyword in node.keywords:
        if keyword.arg == "mode" and isinstance(keyword.value, ast.Constant):
            return str(keyword.value.value)
    return "r"
