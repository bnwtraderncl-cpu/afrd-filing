"""The five sample notes in the real vault, and exactly what they fail on.

They do not pass, and the notes have not been touched. What they fail on is
recorded here rather than argued about, so that:

  * a regression in the gate shows up as a NEW failure on a known note;
  * fixing a sample note shows up as a failure of this test, which is then
    updated to record that it now passes.

The failures are the vault's, not the gate's. See the README, "The five sample
notes", for the reasoning on each.

The `attempt` failure is the one this suite would catch on a report handed back
today. The other two are historical: the sample notes predate the briefs
directory and the data source registry, and cite material that was never in
either.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from afrd_filing import validate
from afrd_filing.failures import render
from afrd_filing import vault as vault_module

# note -> the (rule, where) pairs it is expected to fail on, and nothing else.
EXPECTED = {
    "2026-02-11-es-overnight-high-fade-baseline.md": {
        ("section 7 brief_ref", "frontmatter `brief_ref`"),
        ("section 7 data_sources", "frontmatter `data_sources` entry 1"),
        ("section 7 data_sources", "frontmatter `data_sources` entry 2"),
    },
    "2026-06-03-es-overnight-high-fade-oos-2022-2026.md": {
        ("section 7 brief_ref", "frontmatter `brief_ref`"),
        ("section 7 data_sources", "frontmatter `data_sources` entry 1"),
        ("section 7 data_sources", "frontmatter `data_sources` entry 2"),
        ("section 7 data_sources", "frontmatter `data_sources` entry 3"),
    },
    "2026-07-22-spx-0dte-gamma-pin-scope-hold.md": {
        ("section 7 brief_ref", "frontmatter `brief_ref`"),
        ("section 7 data_sources", "frontmatter `data_sources` entry 1"),
        ("section 7 data_sources", "frontmatter `data_sources` entry 2"),
        ("section 7 data_sources", "frontmatter `data_sources` entry 3"),
    },
    "2026-08-14-high-volume-day-continuation-brief-hold.md": {
        ("section 7 brief_ref", "frontmatter `brief_ref`"),
        ("section 7 data_sources", "frontmatter `data_sources` entry 1"),
    },
    "2026-08-28-quarterly-refunding-front-end-response.md": {
        ("section 5 field presence", "frontmatter `attempt`"),
        ("section 7 brief_ref", "frontmatter `brief_ref`"),
        ("section 7 data_sources", "frontmatter `data_sources` entry 1"),
        ("section 7 data_sources", "frontmatter `data_sources` entry 2"),
        ("section 7 data_sources", "frontmatter `data_sources` entry 3"),
        ("section 7 data_sources", "frontmatter `data_sources` entry 4"),
    },
}


@pytest.fixture(scope="module")
def loaded(real_vault):
    return vault_module.load(real_vault)


def notes(root: Path):
    return sorted((root / "afrd" / "research").glob("*.md"))


def test_the_five_sample_notes_are_where_they_were(real_vault):
    assert [p.name for p in notes(real_vault)] == sorted(EXPECTED)


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_each_sample_note_fails_on_exactly_what_is_recorded(name, real_vault):
    path = real_vault / "afrd" / "research" / name
    ok, failures = validate(path, vault_root=real_vault)
    got = {(f.rule, f.where) for f in failures}
    assert got == EXPECTED[name], render(failures)
    assert not ok


def test_all_five_parse_and_none_fails_on_an_enum_or_the_matrix_beyond_attempt(real_vault):
    """The notes are structurally sound; what they cite is what does not resolve."""
    for path in notes(real_vault):
        _, failures = validate(path, vault_root=real_vault)
        assert not [f for f in failures if f.rule == "frontmatter"], render(failures)
        assert not [f for f in failures if f.rule == "section 7 enum validity"], render(failures)


def test_every_sample_hypothesis_ref_resolves(real_vault, loaded):
    """The one cross-vault reference the samples DO satisfy."""
    for path in notes(real_vault):
        _, failures = validate(path, vault_root=real_vault)
        assert not [f for f in failures if f.rule == "section 7 hypothesis_ref"], (
            "%s: %s" % (path.name, render(failures))
        )


def test_no_sample_note_duplicates_another_notes_id(real_vault):
    for path in notes(real_vault):
        _, failures = validate(path, vault_root=real_vault)
        assert not [f for f in failures if f.rule == "section 7 dedup"], render(failures)


def test_the_real_briefs_and_registries_load(real_vault, loaded):
    assert set(loaded.briefs) == {
        "BRIEF-20260904T223000Z",
        "BRIEF-20260904T224500Z",
    }
    assert "HYP-overnight-high-fade" in loaded.hypotheses
    assert set(loaded.data_sources) == {"vantage-xauusd-h1", "vantage-xauusd-d1"}
    assert len(loaded.artifact_ids) == 5
