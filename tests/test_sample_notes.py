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

**`EXPECTED` is the known-failure corpus, not an inventory of the folder.** It
was both until the gate filed its first real note, at which point asserting the
folder held exactly these five turned a working system into a red suite: every
successful filing broke a test about five notes it has nothing to do with.

The corpus is now a floor rather than an equality. The five must still be
present and must still fail on exactly what is recorded -- that is the
regression signal, and it is unchanged. Notes beyond them are real output, and
`test_every_note_outside_the_corpus_validates` states the other half: anything
in `research/` that is NOT a known sample is expected to PASS. A newly filed
note going red there is a genuine failure and should be read as one.
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


# The ids the five sample notes carry. Pinned so that "the loader still finds
# every sample" is checkable without also pinning how many notes exist.
SAMPLE_IDS = {
    "PATTERN_DISCOVERY-20260211T1418Z",
    "STATISTICIAN-20260603T0947Z",
    "MARKET_STRUCTURE-20260722T1633Z",
    "PATTERN_DISCOVERY-20260814T1105Z",
    "MACRO-20260828T1352Z",
}


@pytest.fixture(scope="module")
def loaded(real_vault):
    return vault_module.load(real_vault)


def notes(root: Path):
    return sorted((root / "afrd" / "research").glob("*.md"))


def test_the_five_sample_notes_are_where_they_were(real_vault):
    """The corpus is a floor: all five present. Filed notes may sit beside them."""
    on_disk = {p.name for p in notes(real_vault)}
    assert set(EXPECTED) <= on_disk, (
        "a sample note has been moved or deleted: %s"
        % sorted(set(EXPECTED) - on_disk)
    )


def test_every_note_outside_the_corpus_validates(real_vault):
    """The other half of the floor, and the reason it is safe to be one.

    An equality assertion on the folder caught a new note by accident, and
    reported it as "the five sample notes moved" -- which is not what happened
    and not what anyone should be told. This catches it on purpose, and says
    the useful thing instead: a note the gate filed must still validate.

    Path form, not text: the dedup check refuses a note whose id is already on
    disk, and every filed note's id is. `validate(path)` excludes the note
    itself, which is what makes re-validating a filed note meaningful at all.
    """
    for path in notes(real_vault):
        if path.name in EXPECTED:
            continue
        ok, failures = validate(path, vault_root=real_vault)
        assert ok, "%s no longer validates: %s" % (path.name, render(failures))


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_each_sample_note_fails_on_exactly_what_is_recorded(name, real_vault):
    path = real_vault / "afrd" / "research" / name
    ok, failures = validate(path, vault_root=real_vault)
    got = {(f.rule, f.where) for f in failures}
    assert got == EXPECTED[name], render(failures)
    assert not ok


def test_every_note_parses_and_none_fails_on_an_enum(real_vault):
    """Every note in the folder, sample and filed alike: structurally sound.

    What the samples cite is what does not resolve; none of them is malformed.
    """
    for path in notes(real_vault):
        _, failures = validate(path, vault_root=real_vault)
        assert not [f for f in failures if f.rule == "frontmatter"], render(failures)
        assert not [f for f in failures if f.rule == "section 7 enum validity"], render(failures)


def test_every_hypothesis_ref_resolves(real_vault, loaded):
    """The one cross-vault reference the samples DO satisfy, and filed notes must."""
    for path in notes(real_vault):
        _, failures = validate(path, vault_root=real_vault)
        assert not [f for f in failures if f.rule == "section 7 hypothesis_ref"], (
            "%s: %s" % (path.name, render(failures))
        )


def test_no_note_duplicates_another_notes_id(real_vault):
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

    # One id per note, sample and filed alike -- the property worth asserting is
    # that the loader finds every note, not that the vault has stopped growing.
    assert len(loaded.artifact_ids) == len(notes(real_vault))
    assert SAMPLE_IDS <= set(loaded.artifact_ids), (
        "a sample note's id is no longer being loaded: %s"
        % sorted(SAMPLE_IDS - set(loaded.artifact_ids))
    )
