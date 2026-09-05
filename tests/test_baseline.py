"""The fixture report passes, and passes for the right reason.

Every other test in this suite breaks this report in exactly one place, so if
this one is wrong the rest say nothing.
"""

from __future__ import annotations

from pathlib import Path

from conftest import GOOD_REPORT

from afrd_filing import validate
from afrd_filing.failures import render


def test_the_good_report_passes(vault):
    ok, failures = validate(GOOD_REPORT, vault_root=vault)
    assert ok, render(failures)
    assert failures == []


def test_text_and_path_agree(vault, tmp_path):
    path = tmp_path / "report.md"
    path.write_text(GOOD_REPORT, encoding="utf-8")
    ok_text, _ = validate(GOOD_REPORT, vault_root=vault)
    ok_path, failures = validate(path, vault_root=vault)
    assert ok_text is ok_path is True, render(failures)


def test_a_filed_note_does_not_collide_with_itself(vault):
    """The dedup rule is that no OTHER note carries the id.

    A note validated from its own path excludes that path from the scan. The
    same note's TEXT does collide, and should -- filing it a second time is
    exactly what dedup is for.
    """
    filed = vault / "afrd" / "research" / "2026-09-05-fixture-filed-note.md"

    ok, _ = validate(filed, vault_root=vault)
    assert ok

    ok, failures = validate(filed.read_text(encoding="utf-8"), vault_root=vault)
    assert not ok
    assert [f.rule for f in failures] == ["section 7 dedup"]
    assert "already carried by" in str(failures[0])


def test_every_failure_names_rule_expected_found_and_where(vault):
    """A refusal that does not say all four is not actionable."""
    broken = GOOD_REPORT.replace("outcome: pass", "outcome: hold").replace(
        "finding: negative", "hold_type: scope\nfinding: inconclusive"
    )
    ok, failures = validate(broken, vault_root=vault)
    assert not ok
    for failure in failures:
        assert failure.rule
        assert failure.where
        assert failure.expected
        assert failure.found
        assert str(failure).startswith("[%s] %s:" % (failure.rule, failure.where))


def test_a_report_is_text_or_a_path_and_nothing_else(vault):
    import pytest

    with pytest.raises(TypeError):
        validate(42, vault_root=vault)


def test_no_frontmatter_is_refused_not_crashed(vault):
    ok, failures = validate("# Just a heading\n\nno frontmatter here.", vault_root=vault)
    assert not ok
    assert failures[0].rule == "frontmatter"
    assert "must open with a `---` line" in failures[0].found
