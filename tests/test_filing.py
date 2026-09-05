"""The writing half: what it writes, what it refuses, and what it leaves alone.

Every test here runs against the FIXTURE vault. It mints for real -- through
`afrd_ids`, against that vault's own high-water mark -- because the ordering
guard and the "two filings, two ids" property are the parts a stub would fake.

The fixture vault's ids are dated 2026-02-11, comfortably behind any clock this
runs on, so the guard has something to compare against and passes.
"""

from __future__ import annotations

import textwrap

import pytest

from conftest import GOOD_REPORT, edit

from afrd_filing import file_report, validate
from afrd_filing.failures import render
from afrd_filing.filing import _guard_target
from afrd_filing.frontmatter import parse, split_frontmatter, yaml_blocks


# The fixture vault carries one filed note at MARKET_STRUCTURE-20260905T080000Z,
# which is AHEAD of the clock for most of the day and would trip the ordering
# guard on every mint. Filing tests move it back: what is being tested here is
# what filing writes, not what the guard does about a vault from the future.
PAST_ID = "MARKET_STRUCTURE-20260211T141800Z"


@pytest.fixture
def filing_vault(vault):
    note = vault / "afrd" / "research" / "2026-09-05-fixture-filed-note.md"
    note.write_text(
        note.read_text(encoding="utf-8").replace(
            "MARKET_STRUCTURE-20260905T080000Z", PAST_ID
        ),
        encoding="utf-8",
    )
    return vault


REPORT = GOOD_REPORT

PROPOSAL = """
## Proposed registry entries

```yaml
- ref: CONV-london-open-first-bar
  description: >-
    The London open is taken as the first H1 bar opening at or after 07:00 UTC.
  minted_because: >-
    BRIEF-20260904T223000Z says "the London open" without fixing a bar.
  minted: 2026-09-05
  status: provisional
```
"""

APPLIED_NEW = """\
conventions_applied:
  - CONV-london-open-first-bar
untested_dependence:
  - convention: CONV-london-open-first-bar
    what_would_change: >-
      Under an 08:00 open the qualifying population shrinks and the divergence
      may narrow.
"""

APPLIED_EXISTING = """\
conventions_applied:
  - CONV-nonpush-sign-preopen
untested_dependence:
  - convention: CONV-nonpush-sign-preopen
    what_would_change: >-
      Under an unsigned comparator the divergence may narrow or disappear.
"""


def with_fields(block, report=REPORT):
    return edit(report, "tags:\n", block + "tags:\n")


def snapshot(root):
    return {p: p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


def registry_refs(root):
    text = (root / "afrd" / "system" / "conventions.md").read_text(encoding="utf-8")
    refs = []
    for block in yaml_blocks(text):
        value = parse(block)
        for entry in value if isinstance(value, list) else [value]:
            if isinstance(entry, dict) and isinstance(entry.get("ref"), str):
                refs.append(entry["ref"])
    return refs


def frontmatter_of(path):
    return parse(split_frontmatter(path.read_text(encoding="utf-8")))


# ------------------------------------------------------------- a valid report


def test_a_valid_report_is_filed_and_reads_back(filing_vault):
    filed, path = file_report(REPORT, vault_root=filing_vault)
    assert filed, render(path) if isinstance(path, list) else path

    assert path.parent == filing_vault / "afrd" / "research"
    assert path.exists()

    fm = frontmatter_of(path)
    assert fm["outcome"] == "pass"
    assert fm["artifact_id"].startswith("MARKET_STRUCTURE-2026")
    assert fm["artifact_id"] != "MARKET_STRUCTURE-20260905T090000Z", (
        "filing must mint the id rather than keep the one the report carried"
    )

    ok, failures = validate(path, vault_root=filing_vault)
    assert ok, render(failures)


def test_the_filename_is_readable_and_is_not_the_id(filing_vault):
    """Schema rule 7: date-prefixed, human-readable, deliberately not the id."""
    filed, path = file_report(REPORT, vault_root=filing_vault)
    assert filed
    assert path.name == "2026-09-05-fixture-report.md"
    assert frontmatter_of(path)["artifact_id"] not in path.name


def test_the_body_is_filed_intact(filing_vault):
    filed, path = file_report(REPORT, vault_root=filing_vault)
    assert filed
    body = path.read_text(encoding="utf-8")
    assert "A clean negative, which is a PASS." in body
    # One line differs from what the producer handed back, and only one.
    handed_back = REPORT.splitlines()
    written = body.splitlines()
    assert len(handed_back) == len(written)
    differing = [a for a, b in zip(handed_back, written) if a != b]
    assert len(differing) == 1 and differing[0].startswith("artifact_id:")


# ------------------------------------------------------------------ refusal


def test_a_report_failing_one_check_is_refused_and_nothing_is_written(filing_vault):
    """Section 7.1: refuse on every `[C]` failure. No warnings, no caveats."""
    before = snapshot(filing_vault)
    filed, failures = file_report(
        edit(REPORT, "attempt: 1", "attempt: 3"), vault_root=filing_vault
    )
    assert not filed
    assert [f.rule for f in failures] == ["section 4 retry bound"]
    assert snapshot(filing_vault) == before


def test_a_refused_report_proposing_a_convention_writes_no_registry_entry(filing_vault):
    """The whole reason the write is staged: no entry for a note that never filed."""
    before = snapshot(filing_vault)
    refused = with_fields(APPLIED_NEW, edit(REPORT, "outcome: pass", "outcome: hold"))
    filed, failures = file_report(refused + PROPOSAL, vault_root=filing_vault)

    assert not filed
    assert failures
    assert snapshot(filing_vault) == before
    assert "CONV-london-open-first-bar" not in registry_refs(filing_vault)


def test_every_failure_is_reported_not_the_first(filing_vault):
    broken = edit(
        edit(REPORT, "producer: market_structure", "producer: quant"),
        "stage: research",
        "stage: backtest",
    )
    filed, failures = file_report(broken, vault_root=filing_vault)
    assert not filed
    assert len(failures) > 1


# ------------------------------------------------------------- the registry


def test_a_proposed_convention_lands_and_the_ref_resolves(filing_vault):
    report = with_fields(APPLIED_NEW) + PROPOSAL
    filed, path = file_report(report, vault_root=filing_vault)
    assert filed, render(path) if isinstance(path, list) else path

    refs = registry_refs(filing_vault)
    assert refs.count("CONV-london-open-first-bar") == 1

    entry = [
        e
        for block in yaml_blocks(
            (filing_vault / "afrd" / "system" / "conventions.md").read_text(
                encoding="utf-8"
            )
        )
        for e in (lambda v: v if isinstance(v, list) else [v])(parse(block))
        if isinstance(e, dict) and e.get("ref") == "CONV-london-open-first-bar"
    ][0]

    assert entry["status"] == "provisional"
    assert entry["minted"] == "2026-09-05"
    assert entry["minted_by"] == frontmatter_of(path)["artifact_id"], (
        "minted_by must name the id filing minted. The producer does not write "
        "the field at all (section 7.0); filing supplies it, and a registry "
        "entry without it is a dangling reference"
    )
    assert "07:00 UTC" in entry["description"]

    # The check section 7.1 defers to the writing half: the ref resolves, and it
    # resolves because filing wrote it.
    ok, failures = validate(path, vault_root=filing_vault)
    assert ok, render(failures)


def test_reusing_an_existing_convention_creates_no_second_entry(filing_vault):
    """conventions.md: reuse the existing entry. Never auto-suffix, never fork."""
    before = registry_refs(filing_vault)
    assert before.count("CONV-nonpush-sign-preopen") == 1

    report = with_fields(APPLIED_EXISTING)
    filed, path = file_report(report, vault_root=filing_vault)
    assert filed, render(path) if isinstance(path, list) else path
    assert registry_refs(filing_vault) == before


def test_re_proposing_an_existing_convention_leaves_the_entry_untouched(filing_vault):
    """`minted` is the date of the FIRST report to carry the ref. It does not move."""
    registry = filing_vault / "afrd" / "system" / "conventions.md"
    before = registry.read_bytes()

    reproposal = PROPOSAL.replace(
        "CONV-london-open-first-bar", "CONV-nonpush-sign-preopen"
    )
    filed, path = file_report(
        with_fields(APPLIED_EXISTING) + reproposal, vault_root=filing_vault
    )
    assert filed, render(path) if isinstance(path, list) else path
    assert registry.read_bytes() == before


def test_an_applied_convention_that_is_neither_registered_nor_proposed_is_refused(
    filing_vault,
):
    before = snapshot(filing_vault)
    filed, failures = file_report(with_fields(APPLIED_NEW), vault_root=filing_vault)
    assert not filed
    assert [f.rule for f in failures] == ["section 7 conventions_applied"]
    assert "CONV-london-open-first-bar" in failures[0].found
    assert snapshot(filing_vault) == before


def test_a_proposal_at_a_status_an_agent_may_not_set_is_refused(filing_vault):
    before = snapshot(filing_vault)
    filed, failures = file_report(
        with_fields(APPLIED_NEW) + PROPOSAL.replace("provisional", "accepted"),
        vault_root=filing_vault,
    )
    assert not filed
    assert any("only status an agent may propose" in f.expected for f in failures)
    assert snapshot(filing_vault) == before


def test_a_proposal_carrying_minted_by_is_refused(filing_vault):
    """Section 7.0: the producer cannot know the id filing will mint, so it
    may not write the field. The guess is refused rather than silently
    overwritten -- a value nobody reads is a value nobody notices is wrong."""
    before = snapshot(filing_vault)
    guessed = PROPOSAL.replace(
        "- ref: CONV-london-open-first-bar\n",
        "- ref: CONV-london-open-first-bar\n"
        "  minted_by: MARKET_STRUCTURE-20260905T000000Z\n",
    )
    filed, failures = file_report(
        with_fields(APPLIED_NEW) + guessed, vault_root=filing_vault
    )
    assert not filed
    assert any(f.where.endswith("`minted_by`") for f in failures), render(failures)
    assert snapshot(filing_vault) == before


def test_a_proposal_without_its_gap_is_refused(filing_vault):
    stripped = PROPOSAL.replace(
        '  minted_because: >-\n'
        '    BRIEF-20260904T223000Z says "the London open" without fixing a bar.\n',
        "",
    )
    filed, failures = file_report(
        with_fields(APPLIED_NEW) + stripped, vault_root=filing_vault
    )
    assert not filed
    assert any(f.where.endswith("`minted_because`") for f in failures)


def test_an_example_ref_is_never_registered(filing_vault):
    """A ref carrying EXAMPLE is an illustration and must never be minted."""
    example = PROPOSAL.replace(
        "CONV-london-open-first-bar", "CONV-EXAMPLE-london-open-first-bar"
    )
    applied = APPLIED_NEW.replace(
        "CONV-london-open-first-bar", "CONV-EXAMPLE-london-open-first-bar"
    )
    filed, failures = file_report(with_fields(applied) + example, vault_root=filing_vault)
    assert not filed
    assert any("illustration" in f.expected for f in failures)
    assert "CONV-EXAMPLE-london-open-first-bar" not in registry_refs(filing_vault)


# ----------------------------------------------------------------------- ids


def test_filing_twice_mints_two_ids_and_does_not_collide(filing_vault):
    first_filed, first = file_report(REPORT, vault_root=filing_vault)
    assert first_filed, render(first) if isinstance(first, list) else first
    second_filed, second = file_report(REPORT, vault_root=filing_vault)
    assert second_filed, render(second) if isinstance(second, list) else second

    assert first != second, "the same filename was written twice"
    ids = [frontmatter_of(p)["artifact_id"] for p in (first, second)]
    assert ids[0] != ids[1]
    assert ids[1] > ids[0], "the second id must sort after the first"

    for path in (first, second):
        ok, failures = validate(path, vault_root=filing_vault)
        assert ok, render(failures)


def test_the_minted_id_sorts_after_the_vault_high_water_mark(filing_vault):
    filed, path = file_report(REPORT, vault_root=filing_vault)
    assert filed
    assert frontmatter_of(path)["artifact_id"] > PAST_ID


def test_a_report_with_no_artifact_id_gets_the_minted_one(filing_vault):
    without = edit(REPORT, "artifact_id: MARKET_STRUCTURE-20260905T090000Z\n", "")
    filed, path = file_report(without, vault_root=filing_vault)
    assert filed, render(path) if isinstance(path, list) else path
    assert frontmatter_of(path)["artifact_id"].startswith("MARKET_STRUCTURE-")


# --------------------------------------------------------------- what it writes


def test_it_writes_nowhere_but_the_two_destinations(filing_vault):
    research = filing_vault / "afrd" / "research"
    registry = filing_vault / "afrd" / "system" / "conventions.md"

    assert _guard_target(research / "2026-09-05-a-note.md", filing_vault)
    assert _guard_target(registry, filing_vault)

    for forbidden in (
        filing_vault / "afrd" / "system" / "hypotheses.md",
        filing_vault / "afrd" / "system" / "frontmatter_schema.md",
        filing_vault / "afrd" / "briefs" / "2026-09-04-fixture-brief.md",
        research / "nested" / "2026-09-05-a-note.md",
        filing_vault / "2026-09-05-a-note.md",
    ):
        with pytest.raises(ValueError):
            _guard_target(forbidden, filing_vault)


def test_hypotheses_and_briefs_are_untouched_by_a_successful_filing(filing_vault):
    """hypothesis_ref is assigned at brief-writing time, not at filing."""
    watched = [
        filing_vault / "afrd" / "system" / "hypotheses.md",
        filing_vault / "afrd" / "system" / "data_sources.md",
        filing_vault / "afrd" / "briefs" / "2026-09-04-fixture-brief.md",
    ]
    before = {p: p.read_bytes() for p in watched}
    filed, path = file_report(with_fields(APPLIED_NEW) + PROPOSAL, vault_root=filing_vault)
    assert filed, render(path) if isinstance(path, list) else path
    assert {p: p.read_bytes() for p in watched} == before


def test_a_report_with_no_frontmatter_is_refused_before_anything_else(filing_vault):
    before = snapshot(filing_vault)
    filed, failures = file_report("Not a report.\n", vault_root=filing_vault)
    assert not filed
    assert [f.rule for f in failures] == ["frontmatter"]
    assert snapshot(filing_vault) == before


def test_the_registry_stays_parseable_after_several_filings(filing_vault):
    """A registry the gate can no longer read is a registry nothing resolves in."""
    for n, ref in enumerate(
        ("CONV-london-open-first-bar", "CONV-asian-range-high"), start=1
    ):
        proposal = PROPOSAL.replace("CONV-london-open-first-bar", ref)
        applied = APPLIED_NEW.replace("CONV-london-open-first-bar", ref)
        filed, path = file_report(with_fields(applied) + proposal, vault_root=filing_vault)
        assert filed, render(path) if isinstance(path, list) else path
        assert len(registry_refs(filing_vault)) == n + 1

    refs = registry_refs(filing_vault)
    assert refs == sorted(refs, key=refs.index)   # nothing was reordered
    assert "CONV-nonpush-sign-preopen" in refs


def test_a_note_filed_with_a_break_records_what_the_conclusion_now_rests_on(
    filing_vault,
):
    """v0.4 section 6, end to end: a variation that failed files, and reads back."""
    tested = textwrap.dedent(
        """\
        conventions_applied:
          - CONV-london-open-first-bar
        untested_dependence: []
        robustness_tested:
          - convention: CONV-london-open-first-bar
            substituted: the 08:00 UTC bar
            held: false
            what_happened: >-
              The divergence does not survive the later open.
            extent: >-
              Holds in 3 of 24 cells.
            conclusion_now_rests_on: >-
              The textual defect alone.
        """
    )
    filed, path = file_report(with_fields(tested) + PROPOSAL, vault_root=filing_vault)
    assert filed, render(path) if isinstance(path, list) else path

    fm = frontmatter_of(path)
    assert fm["robustness_tested"][0]["held"] is False
    assert "textual defect" in fm["robustness_tested"][0]["conclusion_now_rests_on"]

    ok, failures = validate(path, vault_root=filing_vault)
    assert ok, render(failures)
