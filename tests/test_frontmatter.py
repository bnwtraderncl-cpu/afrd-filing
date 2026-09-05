"""The parser reads what the vault contains, and refuses what it does not read.

The second half matters more than the first. A subset parser that silently
returns a plausible string for a construct it does not understand hands the
gate a field it never checked, and the report passes on a check that did not
happen.
"""

from __future__ import annotations

import pytest

from afrd_filing.frontmatter import (
    FrontmatterError,
    parse,
    split_frontmatter,
    yaml_blocks,
)


def test_scalars_lists_and_types():
    got = parse(
        "outcome: pass\n"
        "attempt: 1\n"
        "instrument:\n"
        "  - ES\n"
        "  - NQ\n"
        "sources_referenced: []\n"
    )
    assert got == {
        "outcome": "pass",
        "attempt": 1,
        "instrument": ["ES", "NQ"],
        "sources_referenced": [],
    }


def test_a_folded_block_scalar_becomes_one_line():
    got = parse(
        "hold_reason: >-\n"
        "  The declared window cannot reach\n"
        "  the question.\n"
        "status: awaiting_operator\n"
    )
    assert got["hold_reason"] == "The declared window cannot reach the question."
    assert got["status"] == "awaiting_operator"


def test_a_literal_block_scalar_keeps_its_newlines():
    got = parse("note: |-\n  one\n  two\n")
    assert got["note"] == "one\ntwo"


def test_a_sequence_of_block_scalars():
    """How every `completion_criteria` entry in both briefs is written."""
    got = parse(
        "completion_criteria:\n"
        "  - >-\n"
        "    Minimum 150 qualifying instances.\n"
        "  - Breakdown by calendar year.\n"
    )
    assert got["completion_criteria"] == [
        "Minimum 150 qualifying instances.",
        "Breakdown by calendar year.",
    ]


def test_a_sequence_of_mappings_with_block_scalars():
    """The shape schema rule 11 prints for `untested_dependence`."""
    got = parse(
        "untested_dependence:\n"
        "  - convention: CONV-push-net-close-change\n"
        "    what_would_change: >-\n"
        "      The divergence may narrow or disappear.\n"
        "  - convention: CONV-push-window-three-hours\n"
        "    what_would_change: >-\n"
        "      The qualifying population changes.\n"
    )
    assert [e["convention"] for e in got["untested_dependence"]] == [
        "CONV-push-net-close-change",
        "CONV-push-window-three-hours",
    ]
    assert got["untested_dependence"][0]["what_would_change"] == (
        "The divergence may narrow or disappear."
    )


def test_a_nested_mapping():
    got = parse(
        "scope_assumptions:\n"
        "  timeframe: H1\n"
        "  window: 2018-03-19/2026-09-03\n"
        "  data_sources:\n"
        "    - vantage-xauusd-h1\n"
    )
    assert got["scope_assumptions"]["window"] == "2018-03-19/2026-09-03"
    assert got["scope_assumptions"]["data_sources"] == ["vantage-xauusd-h1"]


def test_an_inline_comment_is_stripped_from_a_plain_scalar():
    """`usable_from` in the data source registry carries exactly one."""
    got = parse("usable_from: 2007-06-21T21:00:00Z    # same as earliest\n")
    assert got["usable_from"] == "2007-06-21T21:00:00Z"


def test_a_quoted_scalar_keeps_its_hash():
    got = parse('tag: "#trend-day"\n')
    assert got["tag"] == "#trend-day"


def test_a_block_scalar_keeps_its_hash():
    """Block scalar content is literal. A `#` in a hold_reason is not a comment."""
    got = parse("hold_reason: >-\n  Filed under #trend-day and nothing else.\n")
    assert got["hold_reason"] == "Filed under #trend-day and nothing else."


# ------------------------------------------------------------------- refusals


@pytest.mark.parametrize(
    "text, fragment",
    [
        ("instrument: [ES, NQ]\n", "flow collections"),
        ("scope: {window: 2018}\n", "flow collections"),
        ("base: &anchor value\n", "anchors"),
        ("tags:\n  - - nested\n", "nested sequences"),
        ("outcome pass\n", "expected `key: value`"),
        ("outcome: pass\noutcome: hold\n", "duplicate key"),
        ("outcome: pass\n\tattempt: 1\n", "tab in indentation"),
    ],
)
def test_constructs_outside_the_subset_raise_rather_than_guess(text, fragment):
    with pytest.raises(FrontmatterError) as exc:
        parse(text)
    assert fragment in str(exc.value)


def test_split_refuses_a_document_with_no_frontmatter():
    with pytest.raises(FrontmatterError) as exc:
        split_frontmatter("# Heading\n\nbody\n")
    assert "must open with a `---` line" in str(exc.value)


def test_split_refuses_unclosed_frontmatter():
    with pytest.raises(FrontmatterError) as exc:
        split_frontmatter("---\noutcome: pass\n\n# body\n")
    assert "not closed" in str(exc.value)


def test_split_returns_the_block_without_its_fences():
    assert split_frontmatter("---\noutcome: pass\n---\n\nbody\n") == "outcome: pass"


# --------------------------------------------------------------- yaml_blocks


def test_yaml_blocks_yields_only_fenced_yaml():
    text = (
        "prose\n\n```yaml\n- ref: HYP-one\n```\n\n"
        "```sql\nSELECT 1;\n```\n\n```yaml\n- ref: HYP-two\n```\n"
    )
    assert [parse(b)[0]["ref"] for b in yaml_blocks(text)] == ["HYP-one", "HYP-two"]
