"""The five checks that resolve a ref against something already in the vault.

`brief_ref`, `hypothesis_ref` (including the match against the brief's),
`data_sources`, the scope window against `usable_from`, and dedup.
"""

from __future__ import annotations

from conftest import GOOD_REPORT, edit

from afrd_filing import validate
from afrd_filing.failures import render


def only(failures, rule):
    picked = [f for f in failures if f.rule == rule]
    assert picked, "no %s failure in:\n%s" % (rule, render(failures))
    return picked[0]


# ------------------------------------------------------------------ brief_ref


def test_an_unresolvable_brief_ref_names_the_directory_and_what_is_there(vault):
    ok, failures = validate(
        edit(GOOD_REPORT, "BRIEF-20260904T223000Z", "BRIEF-20260101T000000Z"),
        vault_root=vault,
    )
    assert not ok
    f = only(failures, "section 7 brief_ref")
    assert "afrd/briefs" in f.expected
    assert "BRIEF-20260904T223000Z" in f.expected      # what IS there
    assert "BRIEF-20260101T000000Z" in f.found         # what was asked for


def test_a_missing_brief_ref_is_refused(vault):
    ok, failures = validate(
        edit(GOOD_REPORT, "brief_ref: BRIEF-20260904T223000Z\n", ""), vault_root=vault
    )
    assert not ok
    assert only(failures, "section 7 brief_ref").found == "nothing"


# ------------------------------------------------------------- hypothesis_ref


def test_an_unregistered_hypothesis_ref_is_refused(vault):
    ok, failures = validate(
        edit(GOOD_REPORT, "HYP-overnight-high-fade", "HYP-invented-here"),
        vault_root=vault,
    )
    assert not ok
    f = only(failures, "section 7 hypothesis_ref")
    assert "hypotheses.md" in f.expected
    assert "HYP-invented-here" in f.found


def test_a_registered_ref_that_is_not_the_briefs_ref_is_refused(vault):
    """section 7: resolves in `hypotheses.md`, AND matches the brief's.

    `HYP-london-open-push-fade` is registered in the fixture vault, so this
    fails only on the mismatch -- which is the case that matters. A note filed
    under the wrong ref is silently grouped with the wrong history.
    """
    ok, failures = validate(
        edit(GOOD_REPORT, "HYP-overnight-high-fade", "HYP-london-open-push-fade"),
        vault_root=vault,
    )
    assert not ok
    f = only(failures, "section 7 hypothesis_ref")
    assert "the `hypothesis_ref` of the brief it answers" in f.expected
    assert "BRIEF-20260904T223000Z" in f.expected
    assert "HYP-overnight-high-fade" in f.expected     # what the brief carries
    assert "HYP-london-open-push-fade" in f.found


def test_an_unresolvable_brief_does_not_produce_a_second_mismatch_failure(vault):
    """One cause, one failure. The brief_ref refusal already names it."""
    ok, failures = validate(
        edit(GOOD_REPORT, "BRIEF-20260904T223000Z", "BRIEF-20260101T000000Z"),
        vault_root=vault,
    )
    assert not ok
    assert [f.rule for f in failures] == ["section 7 brief_ref"]


# --------------------------------------------------------------- data_sources


def test_a_prose_description_is_not_a_source_id(vault):
    ok, failures = validate(
        edit(
            GOOD_REPORT,
            "  - vantage-xauusd-h1\n",
            "  - Vantage XAUUSD hourly bars, 2018-2026\n",
        ),
        vault_root=vault,
    )
    assert not ok
    f = only(failures, "section 7 data_sources")
    assert "not a description" in f.expected
    assert "vantage-xauusd-h1" in f.expected           # what IS registered
    assert "entry 1" in f.where


def test_every_unresolvable_entry_is_reported_not_just_the_first(vault):
    ok, failures = validate(
        edit(
            GOOD_REPORT,
            "  - vantage-xauusd-h1\n",
            "  - fred-dgs10-d1\n  - cot-gold-w1\n  - vantage-xauusd-h1\n",
        ),
        vault_root=vault,
    )
    assert not ok
    hit = [f for f in failures if f.rule == "section 7 data_sources"]
    assert len(hit) == 2
    assert [f.where for f in hit] == [
        "frontmatter `data_sources` entry 1",
        "frontmatter `data_sources` entry 2",
    ]


# ---------------------------------------------------------------- scope window


def test_a_window_starting_before_usable_from_is_refused(vault):
    """data_sources.md rule 3: nothing looks wrong, which is why it is checked."""
    ok, failures = validate(
        edit(GOOD_REPORT, "scope_window: 2018-03-19/2026-09-03",
             "scope_window: 2010-01-04/2026-09-03"),
        vault_root=vault,
    )
    assert not ok
    f = only(failures, "section 7 scope window")
    assert "2018-03-19T00:00:00Z" in f.expected        # the bound it broke
    assert "vantage-xauusd-h1" in f.where
    assert "starting 2010-01-04" in f.found


def test_a_window_starting_exactly_at_usable_from_is_fine(vault):
    ok, failures = validate(GOOD_REPORT, vault_root=vault)
    assert ok, render(failures)


def test_the_bound_is_per_source(vault):
    """`vantage-xauusd-d1` is usable from 2007, so the same window passes on it."""
    ok, failures = validate(
        edit(
            edit(GOOD_REPORT, "  - vantage-xauusd-h1\n", "  - vantage-xauusd-d1\n"),
            "scope_window: 2018-03-19/2026-09-03",
            "scope_window: 2010-01-04/2026-09-03",
        ),
        vault_root=vault,
    )
    assert ok, render(failures)


def test_an_unreadable_window_is_refused_rather_than_skipped(vault):
    ok, failures = validate(
        edit(GOOD_REPORT, "scope_window: 2018-03-19/2026-09-03",
             "scope_window: since 2018"),
        vault_root=vault,
    )
    assert not ok
    assert "YYYY-MM-DD/YYYY-MM-DD" in only(failures, "section 7 scope window").expected


# ---------------------------------------------------------------------- dedup


def test_an_id_already_in_the_vault_names_the_note_that_holds_it(vault):
    ok, failures = validate(
        edit(GOOD_REPORT, "MARKET_STRUCTURE-20260905T090000Z",
             "MARKET_STRUCTURE-20260905T080000Z"),
        vault_root=vault,
    )
    assert not ok
    f = only(failures, "section 7 dedup")
    assert "2026-09-05-fixture-filed-note.md" in f.found
    assert "afrd-ids" in f.expected                    # where to mint again


def test_a_missing_artifact_id_is_refused(vault):
    ok, failures = validate(
        edit(GOOD_REPORT, "artifact_id: MARKET_STRUCTURE-20260905T090000Z\n", ""),
        vault_root=vault,
    )
    assert not ok
    assert only(failures, "section 7 dedup").found == "nothing"


def test_an_unreadable_window_is_refused_even_with_no_data_sources(vault):
    """The two are independent: a window nothing can read is refused on its own."""
    broken = edit(
        edit(GOOD_REPORT, "scope_window: 2018-03-19/2026-09-03", "scope_window: since 2018"),
        "data_sources:\n  - vantage-xauusd-h1\n",
        "",
    )
    ok, failures = validate(broken, vault_root=vault)
    assert not ok
    assert only(failures, "section 7 scope window")


def test_a_backwards_window_is_refused(vault):
    ok, failures = validate(
        edit(GOOD_REPORT, "scope_window: 2018-03-19/2026-09-03",
             "scope_window: 2026-09-03/2018-03-19"),
        vault_root=vault,
    )
    assert not ok
    assert "start is on or before its end" in only(failures, "section 7 scope window").expected
