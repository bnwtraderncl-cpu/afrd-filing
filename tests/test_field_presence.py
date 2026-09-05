"""The section 5 matrix, one cell at a time.

The matrix has five columns and eight rows. These cover the cells whose
reasoning the standard bothers to explain -- the ones where getting it wrong
produces a note asserting something that is not there.
"""

from __future__ import annotations

import pytest
from conftest import GOOD_REPORT, edit

from afrd_filing import validate
from afrd_filing.failures import render

PASS = GOOD_REPORT

HOLD_SCOPE = edit(
    edit(
        GOOD_REPORT,
        "outcome: pass\nfinding: negative\n",
        "outcome: hold\nhold_type: scope\nhold_reason: >-\n"
        "  The declared window cannot reach the question.\n",
    ),
    "status: stored",
    "status: awaiting_operator",
)

HOLD_AUTHORITY = edit(
    edit(
        GOOD_REPORT,
        "outcome: pass\nfinding: negative\n",
        "outcome: hold\nhold_type: authority\nhold_reason: >-\n"
        "  Touches capital allocation; operator approves.\nfinding: positive\n",
    ),
    "status: stored",
    "status: awaiting_operator",
)

FAIL = edit(
    GOOD_REPORT,
    "outcome: pass\nfinding: negative\n",
    "outcome: fail\nfail_depth: structural\nfail_reason: >-\n"
    "  The export block was malformed.\n",
)


def only(failures, rule=None, where=None):
    picked = [
        f
        for f in failures
        if (rule is None or f.rule == rule) and (where is None or f.where == where)
    ]
    assert picked, "no failure matched:\n%s" % render(failures)
    return picked[0]


# ---------------------------------------------------------------- the columns


def test_the_three_hold_columns_and_fail_are_each_valid(vault):
    for report in (HOLD_SCOPE, HOLD_AUTHORITY, FAIL):
        ok, failures = validate(report, vault_root=vault)
        assert ok, render(failures)


# ------------------------------------------------------------------- required


def test_pass_requires_finding(vault):
    ok, failures = validate(edit(PASS, "finding: negative\n", ""), vault_root=vault)
    assert not ok
    f = only(failures, "section 5 field presence", "frontmatter `finding`")
    assert "outcome `pass` requires `finding`" in f.expected
    assert f.found == "nothing"


def test_authority_hold_requires_finding(vault):
    """section 3.1: on an authority hold the work is COMPLETE, so the finding survives."""
    ok, failures = validate(
        edit(HOLD_AUTHORITY, "finding: positive\n", ""), vault_root=vault
    )
    assert not ok
    f = only(failures, "section 5 field presence", "frontmatter `finding`")
    assert "hold_type: authority" in f.expected


def test_every_column_requires_attempt(vault):
    for report in (PASS, HOLD_SCOPE, HOLD_AUTHORITY, FAIL):
        ok, failures = validate(edit(report, "attempt: 1\n", ""), vault_root=vault)
        assert not ok
        only(failures, "section 5 field presence", "frontmatter `attempt`")


def test_fail_requires_fail_depth_and_fail_reason(vault):
    ok, failures = validate(
        edit(edit(FAIL, "fail_depth: structural\n", ""),
             "fail_reason: >-\n  The export block was malformed.\n", ""),
        vault_root=vault,
    )
    assert not ok
    only(failures, "section 5 field presence", "frontmatter `fail_depth`")
    only(failures, "section 5 field presence", "frontmatter `fail_reason`")


def test_a_hold_without_hold_type_says_the_matrix_cannot_be_run(vault):
    ok, failures = validate(
        edit(HOLD_SCOPE, "hold_type: scope\n", ""), vault_root=vault
    )
    assert not ok
    f = only(failures, "section 5 field presence", "frontmatter `hold_type`")
    assert "selects which column applies" in f.expected


# ------------------------------------------------------------------ forbidden


def test_a_scope_hold_must_not_carry_a_finding(vault):
    """The standard's own worked example of a useless message made useful."""
    ok, failures = validate(
        edit(HOLD_SCOPE, "hold_type: scope\n", "hold_type: scope\nfinding: inconclusive\n"),
        vault_root=vault,
    )
    assert not ok
    f = only(failures, "section 5 field presence", "frontmatter `finding`")
    assert "hold_type: scope`" in f.expected
    assert "must not carry `finding`" in f.expected
    assert "section 5 matrix" in f.expected
    assert f.found == "`finding: inconclusive`"


def test_a_brief_hold_must_not_carry_review_flag_or_finding_note(vault):
    brief_hold = edit(HOLD_SCOPE, "hold_type: scope", "hold_type: brief")
    ok, failures = validate(
        edit(
            brief_hold,
            "hold_type: brief\n",
            "hold_type: brief\nreview_flag: data_gap\nfinding_note: >-\n"
            "  What it would have concluded.\n",
        ),
        vault_root=vault,
    )
    assert not ok
    only(failures, "section 5 field presence", "frontmatter `review_flag`")
    only(failures, "section 5 field presence", "frontmatter `finding_note`")


def test_a_pass_must_not_carry_hold_or_failure_fields(vault):
    ok, failures = validate(
        edit(PASS, "status: stored\n", "status: stored\nhold_type: scope\nfail_depth: structural\n"),
        vault_root=vault,
    )
    assert not ok
    assert "must not carry `hold_type`" in only(
        failures, "section 5 field presence", "frontmatter `hold_type`"
    ).expected
    assert "must not carry `fail_depth`" in only(
        failures, "section 5 field presence", "frontmatter `fail_depth`"
    ).expected


def test_a_fail_must_not_carry_a_finding(vault):
    ok, failures = validate(
        edit(FAIL, "fail_depth: structural\n", "fail_depth: structural\nfinding: inconclusive\n"),
        vault_root=vault,
    )
    assert not ok
    assert "outcome `fail` must not carry `finding`" in only(
        failures, "section 5 field presence", "frontmatter `finding`"
    ).expected


# ------------------------------------------------------------------- optional


def test_optional_result_fields_are_optional_on_a_pass(vault):
    with_both = edit(
        PASS,
        "finding: negative\n",
        "finding: negative\nreview_flag: revisit\nfinding_note: >-\n"
        "  Decay, not refutation.\n",
    )
    ok, failures = validate(with_both, vault_root=vault)
    assert ok, render(failures)


# --------------------------------------------------------- every failure, not one


def test_the_refusal_carries_every_failure_not_the_first(vault):
    broken = edit(edit(PASS, "finding: negative\n", ""), "attempt: 1\n", "")
    broken = edit(broken, "hypothesis_ref: HYP-overnight-high-fade", "hypothesis_ref: HYP-not-registered")
    ok, failures = validate(broken, vault_root=vault)
    assert not ok
    wheres = {f.where for f in failures}
    assert "frontmatter `finding`" in wheres
    assert "frontmatter `attempt`" in wheres
    assert "frontmatter `hypothesis_ref`" in wheres
