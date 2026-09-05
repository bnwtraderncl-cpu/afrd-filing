"""Convention accounting (section 6), the closed enums, and the retry bound (section 4)."""

from __future__ import annotations

from conftest import GOOD_REPORT, edit

from afrd_filing import validate
from afrd_filing.failures import render

APPLIED = """\
conventions_applied:
  - CONV-nonpush-sign-preopen
"""

UNTESTED = """\
untested_dependence:
  - convention: CONV-nonpush-sign-preopen
    what_would_change: >-
      Under an unsigned comparator the divergence may narrow or disappear.
"""

BROKEN = """\
robustness_broken:
  - convention: CONV-nonpush-sign-preopen
    substituted: unsigned comparator
    what_failed: >-
      The split does not hold.
    extent: >-
      Holds in 10 of 48 cells.
    conclusion_now_rests_on: >-
      The population divergence alone.
"""


def only(failures, rule):
    picked = [f for f in failures if f.rule == rule]
    assert picked, "no %s failure in:\n%s" % (rule, render(failures))
    return picked[0]


def with_blocks(*blocks):
    return edit(GOOD_REPORT, "tags:\n", "".join(blocks) + "tags:\n")


# ------------------------------------------------------- untested_dependence


def test_conventions_applied_without_untested_dependence_fails(vault):
    """The case the standard is most explicit about, and the cheapest to get wrong."""
    ok, failures = validate(with_blocks(APPLIED), vault_root=vault)
    assert not ok
    f = only(failures, "section 6 untested_dependence")
    assert "required whenever `conventions_applied` is non-empty" in f.expected
    assert f.found.startswith("nothing, alongside `conventions_applied` with 1 entry")


def test_conventions_applied_with_untested_dependence_passes(vault):
    ok, failures = validate(with_blocks(APPLIED, UNTESTED), vault_root=vault)
    assert ok, render(failures)


def test_no_conventions_needs_no_untested_dependence(vault):
    ok, failures = validate(GOOD_REPORT, vault_root=vault)
    assert ok, render(failures)


def test_an_empty_conventions_list_needs_no_untested_dependence(vault):
    ok, failures = validate(with_blocks("conventions_applied: []\n"), vault_root=vault)
    assert ok, render(failures)


# ----------------------------------------------------------------- accounting


def test_an_applied_convention_accounted_for_nowhere_is_refused(vault):
    """section 6: every applied convention is varied, or listed. Nothing unaccounted for."""
    two = APPLIED + "  - CONV-london-open-bar\n"
    ok, failures = validate(with_blocks(two, UNTESTED), vault_root=vault)
    assert not ok
    f = only(failures, "section 6 convention accounting")
    assert "entry 2" in f.where
    assert "CONV-london-open-bar" in f.found
    assert "CONV-nonpush-sign-preopen" in f.found      # what IS accounted for


def test_a_convention_accounted_for_by_robustness_broken_is_enough(vault):
    """rule 12 records what WAS varied and failed. That is an accounting too."""
    body = edit(
        with_blocks(APPLIED, "untested_dependence: []\n", BROKEN),
        "untested_dependence: []\n",
        "untested_dependence: []\n",
    )
    ok, failures = validate(body, vault_root=vault)
    assert ok, render(failures)


def test_an_empty_untested_dependence_is_present_but_accounts_for_nothing(vault):
    """rule 11: an empty list is valid ONLY if every convention was varied."""
    ok, failures = validate(
        with_blocks(APPLIED, "untested_dependence: []\n"), vault_root=vault
    )
    assert not ok
    assert [f.rule for f in failures] == ["section 6 convention accounting"]


# ---------------------------------------------------------------------- enums


def test_an_unknown_enum_value_is_refused_with_the_permitted_set(vault):
    ok, failures = validate(
        edit(GOOD_REPORT, "outcome: pass", "outcome: partial"), vault_root=vault
    )
    assert not ok
    f = only(failures, "section 7 enum validity")
    assert "`pass`, `hold`, `fail`" in f.expected
    assert "may not coin a value" in f.expected
    assert f.found == "`partial`"


def test_the_retrying_status_the_schema_forbids_is_refused(vault):
    """schema rule 8 / section 4: there is no `retrying`; retry state lives in `attempt`."""
    ok, failures = validate(
        edit(GOOD_REPORT, "status: stored", "status: retrying"), vault_root=vault
    )
    assert not ok
    assert only(failures, "section 7 enum validity").found == "`retrying`"


def test_an_unknown_producer_or_stage_is_refused(vault):
    ok, failures = validate(
        edit(edit(GOOD_REPORT, "producer: market_structure", "producer: quant"),
             "stage: research", "stage: backtest"),
        vault_root=vault,
    )
    assert not ok
    wheres = {f.where for f in failures if f.rule == "section 7 enum validity"}
    assert wheres == {"frontmatter `producer`", "frontmatter `stage`"}


def test_an_unknown_outcome_does_not_also_produce_matrix_noise(vault):
    ok, failures = validate(
        edit(GOOD_REPORT, "outcome: pass", "outcome: partial"), vault_root=vault
    )
    assert not ok
    assert [f.rule for f in failures] == ["section 7 enum validity"]


# ---------------------------------------------------------------- retry bound


def test_a_third_attempt_is_past_the_bound(vault):
    ok, failures = validate(edit(GOOD_REPORT, "attempt: 1", "attempt: 3"), vault_root=vault)
    assert not ok
    f = only(failures, "section 4 retry bound")
    assert "1 re-delegation, then stop" in f.expected
    assert f.found == "`attempt: 3`"


def test_an_exhausted_fail_must_reach_the_operator(vault):
    exhausted = edit(
        edit(
            GOOD_REPORT,
            "outcome: pass\nfinding: negative\n",
            "outcome: fail\nfail_depth: substantive\nfail_reason: >-\n"
            "  Answered a narrower question than asked.\n",
        ),
        "attempt: 1",
        "attempt: 2",
    )
    ok, failures = validate(exhausted, vault_root=vault)
    assert not ok
    f = only(failures, "section 4 retry bound")
    assert "awaiting_operator" in f.expected
    assert f.found == "`stored`"

    ok, failures = validate(
        edit(exhausted, "status: stored", "status: awaiting_operator"), vault_root=vault
    )
    assert ok, render(failures)


def test_a_first_attempt_fail_returns_to_rc_and_stays_stored(vault):
    first = edit(
        GOOD_REPORT,
        "outcome: pass\nfinding: negative\n",
        "outcome: fail\nfail_depth: structural\nfail_reason: >-\n"
        "  The export block was malformed.\n",
    )
    ok, failures = validate(
        edit(first, "status: stored", "status: awaiting_operator"), vault_root=vault
    )
    assert not ok
    assert "the operator is not needed" in only(failures, "section 4 retry bound").expected

    ok, failures = validate(first, vault_root=vault)
    assert ok, render(failures)


def test_a_non_integer_attempt_is_refused(vault):
    ok, failures = validate(edit(GOOD_REPORT, "attempt: 1", "attempt: first"), vault_root=vault)
    assert not ok
    assert only(failures, "section 4 retry bound").found == "`first`"
