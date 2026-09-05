"""`file_report(report) -> (filed, path_or_failures)` -- the writing half of filing.

WHAT THIS IS
------------
`pass_fail_hold_standard.md` section 7.1 makes the registry write part of filing
rather than a precondition for it, and fixes the order:

    1. the producer proposes registry entries in its report
    2. filing writes those entries to `conventions.md`
    3. filing checks that every ref in `conventions_applied` resolves

"The check runs after the write, so a proposed entry always resolves. The
registry cannot be behind, because filing is what advances it." That ordering is
the whole reason a `CONV-` ref proposed in a report is never a bookkeeping
refusal -- the case section 7.1 says "ends with the operator filing by hand to
get around the script".

THE ORDERING PROBLEM, AND WHAT IS DONE ABOUT IT
-----------------------------------------------
Step 2 writes and step 3 can still refuse. Taken literally, a refusal at step 3
leaves `conventions.md` carrying entries for a report that was never filed --
`minted_by` pointing at nothing. That is the dangling-`minted_by` failure
`conventions.md` describes at length, whose resolution it makes an operator
action, and the vault already has one instance of it. Filing must not
manufacture more.

So the write is STAGED: the registry text that step 2 would produce is built in
memory, every check runs against the vault as it WOULD BE after that write, and
the bytes reach the disk only once nothing has refused.

    stage -> check against the staged state -> commit, or discard

This satisfies section 7.1 exactly. The section's requirement is about what the
CHECK SEES -- a proposed entry must resolve when the resolution check runs -- and
the staged registry is what the check is run against. What it does not do is
require the disk to pass through a state that only a later success justifies.

Staging over rollback, deliberately. A rollback preserves "nothing is written on
refusal" only if the undo itself runs and succeeds: a crash, a full disk or a
lost lock between the write and the undo leaves precisely the dangling entry the
rule exists to prevent, and the failure is silent. Staging makes the property
hold because nothing was written, which needs no code to work correctly at the
moment things are going wrong. It is also cheaper: one write instead of a write,
a read-back and a restore.

WHAT ORDER THE TWO FILES ARE WRITTEN IN
---------------------------------------
The note first, then the registry.

Both writes are guarded and either can still fail on the filesystem. Of the two
half-states, a note citing a `CONV-` ref the registry does not yet carry is the
recoverable one: the ref does not resolve, that is visible to the next run of the
gate, and re-filing the registry entry repairs it. The other half-state is a
registry entry whose `minted_by` names a note that does not exist, which
`conventions.md` says only the operator may resolve. Write the recoverable one
first.

WHAT IT MINTS, AND WHAT IT OVERWRITES
-------------------------------------
The `artifact_id` is minted here, through `afrd_ids.mint_artifact_id`, and
REPLACES whatever the report carried. Section 7.1: "filing mints through the
helper, so `artifact_id` is correct by construction rather than checked after the
fact." Nothing in this module formats a timestamp.

`minted_by` on every proposed entry is rewritten to that minted id, for the same
reason. A producer writes its own `artifact_id` there, and cannot know the id
filing will mint; leaving the producer's value would register a convention
against an id no note carries, which is the dangling reference again, minted at
the moment of filing.

WHAT IT WRITES, AND NOWHERE ELSE
--------------------------------
    afrd/research/<date>-<slug>.md          the note
    afrd/system/conventions.md              new provisional entries

Every path goes through `_guard_target` before it is opened. There is no third
destination and no flag that adds one.
"""

from __future__ import annotations

import os
import re
import sys
import time
from pathlib import Path

from .failures import Failure
from .frontmatter import FrontmatterError, parse, split_frontmatter, yaml_blocks
from .validate import validate
from . import vault as vault_module

# `afrd-ids` has no packaging, so importing it is a path insert -- the README
# said it would be, and this is it. The env var is for a test host or a checkout
# somewhere else; the default is where the repo lives.
DEFAULT_IDS_ROOT = Path(os.environ.get("AFRD_IDS_ROOT", r"C:\dev\afrd-ids"))


def _afrd_ids():
    """The minting helper, imported once, from the repo that owns id derivation."""
    try:
        import afrd_ids
    except ImportError:
        root = str(DEFAULT_IDS_ROOT)
        if root not in sys.path:
            sys.path.insert(0, root)
        import afrd_ids
    return afrd_ids


# A `CONV-` ref as `conventions.md` defines it: the `hypothesis_ref` rules with a
# `CONV-` prefix -- lowercase, hyphenated, two to four readable words.
CONV_REF = re.compile(r"^CONV-[a-z0-9]+(?:-[a-z0-9]+){1,3}$")

# Where a new entry goes in `conventions.md`: the end of the `## Registry`
# section, which is the rule and heading that close it.
_REGISTRY_ANCHOR = "\n---\n\n## Fields\n"

# The registry's own status rule: agents mint at `provisional` and may set no
# other value. Only the operator promotes one.
_PROPOSED_STATUS = "provisional"

_MAX_SLUG_WORDS = 8


def file_report(report, vault_root=None):
    """File a research report. Returns `(True, Path)` or `(False, [Failure, ...])`.

    `report` is the report TEXT, as the producer handed it back, or a `Path` to
    one. Nothing is written unless every check passes: section 7.1 refuses on
    every `[C]` failure, with no warnings and no filing-with-caveats.

    The refusal carries every failure found, not the first, because a refusal is
    the only thing the producer gets back and it has to be enough to fix the
    report from.
    """
    root = Path(vault_root) if vault_root is not None else vault_module.DEFAULT_VAULT_ROOT

    if isinstance(report, Path):
        text = report.read_text(encoding="utf-8")
    elif isinstance(report, str):
        text = report
    else:
        raise TypeError(
            "report must be the report text or a Path to a note, got %s"
            % type(report).__name__
        )

    try:
        fm = parse(split_frontmatter(text))
    except FrontmatterError as exc:
        return False, [
            Failure(
                rule="frontmatter",
                where="report frontmatter",
                expected="a YAML frontmatter block filing can read",
                found="`%s`" % exc,
            )
        ]
    if not isinstance(fm, dict):
        return False, [
            Failure(
                rule="frontmatter",
                where="report frontmatter",
                expected="frontmatter to be a mapping of fields",
                found="a %s" % type(fm).__name__,
            )
        ]

    try:
        vault = vault_module.load(root)
    except vault_module.VaultError as exc:
        return False, [
            Failure(
                rule="vault",
                where=str(root),
                expected="a vault filing can read",
                found="`%s`" % exc,
            )
        ]

    failures = []

    # ---- step 1: the producer's proposed entries -------------------------
    proposed, proposal_failures = _proposed_entries(text)
    failures += proposal_failures

    # ---- step 2: mint ----------------------------------------------------
    minted, mint_failures = _mint(fm.get("producer"), root)
    failures += mint_failures

    staged_text = _with_artifact_id(text, minted) if minted else text

    # ---- step 3: the staged registry, and every check against it ---------
    staged_registry, new_entries, registry_failures = _staged_registry(
        vault, [] if proposal_failures else proposed, minted
    )
    failures += registry_failures

    ok, check_failures = validate(staged_text, vault_root=root, vault=vault)
    failures += check_failures
    failures += _check_conventions_resolve(fm, vault, proposed)

    # ---- step 4: refuse, having written nothing --------------------------
    if failures:
        return False, failures

    # ---- step 5: commit --------------------------------------------------
    note_path = _note_path(root, fm, staged_text, minted)
    _write(note_path, staged_text, root)
    if new_entries:
        _write(vault.conventions_registry, staged_registry, root)
    return True, note_path


# --------------------------------------------------------------- step 1


def _proposed_entries(text):
    """The `CONV-` entries the report proposes, and what is wrong with them.

    A proposal is a fenced ```yaml block in the report body carrying a `ref` that
    starts `CONV-` -- the "PROPOSED REGISTRY ENTRY" block the specialists are
    told to write. Anything else in a yaml block is left alone: a report may
    quote its own frontmatter or show an example, and neither is a proposal.
    """
    entries = []
    failures = []
    for block in yaml_blocks(text):
        try:
            value = parse(block)
        except FrontmatterError:
            # Prose, an illustration, or a block this parser's subset does not
            # cover. It is not a proposal, and taking a report's example block
            # hostage would refuse reports for their formatting.
            continue
        for entry in value if isinstance(value, list) else [value]:
            if not isinstance(entry, dict):
                continue
            ref = entry.get("ref")
            if not (isinstance(ref, str) and ref.startswith("CONV-")):
                continue
            entries.append(entry)
            failures += _check_proposal(entry, ref)

    seen = {}
    counts = {}
    for entry in entries:
        ref = entry["ref"]
        counts[ref] = counts.get(ref, 0) + 1
        seen.setdefault(ref, entry)
    for ref, count in counts.items():
        if count > 1:
            failures.append(
                Failure(
                    rule="conventions.md proposal",
                    where="proposed entry `%s`" % ref,
                    expected="one proposed entry per ref -- two entries for one "
                    "ref describe one choice twice and filing cannot tell which "
                    "the report meant",
                    found="`%s` proposed %d times" % (ref, count),
                )
            )
    return list(seen.values()), failures


def _check_proposal(entry, ref):
    """A proposed entry's shape, against `conventions.md`'s own field rules."""
    out = []
    where = "proposed entry `%s`" % ref

    if "EXAMPLE" in ref:
        out.append(
            Failure(
                rule="conventions.md proposal",
                where=where,
                expected="a real ref. A ref carrying `EXAMPLE` after its prefix "
                "is an illustration -- deliberately malformed, resolving to "
                "nothing, and never to be minted or registered (conventions.md, "
                "ref format)",
                found="`%s`" % ref,
            )
        )
    elif not CONV_REF.match(ref):
        out.append(
            Failure(
                rule="conventions.md proposal",
                where=where,
                expected="`CONV-` then two to four lowercase hyphenated words, "
                "readable aloud (conventions.md, ref format; schema rule 9). The "
                "operator reads this ref by eye when deciding whether a result "
                "survives the assumption behind it",
                found="`%s`" % ref,
            )
        )

    for field, why in (
        ("description", "the choice that was made, in plain English"),
        (
            "minted_because",
            "the gap that forced it, naming the brief and the undefined term. "
            "It is the part that is easy to skip and most worth having: a "
            "convention without its gap reads as house preference",
        ),
    ):
        value = entry.get(field)
        if not (isinstance(value, str) and value.strip()):
            out.append(
                Failure(
                    rule="conventions.md proposal",
                    where="%s, `%s`" % (where, field),
                    expected="%s (conventions.md, Fields)" % why,
                    found="nothing" if value is None else "`%s`" % value,
                )
            )

    status = entry.get("status")
    if status is not None and status != _PROPOSED_STATUS:
        out.append(
            Failure(
                rule="conventions.md proposal",
                where="%s, `status`" % where,
                expected="`status: provisional`, the only status an agent may "
                "propose. `accepted` is an operator decision and no count of "
                "reports, elapsed time or agent judgement reaches it "
                "(conventions.md, What the statuses mean)",
                found="`%s`" % status,
            )
        )
    return out


# --------------------------------------------------------------- step 2


def _mint(producer, root, attempts=3):
    """Mint the `artifact_id` through the helper. Never formats a stamp here.

    Two refusals come back from the helper and they are not the same refusal.

    `OrderingGuardError` -- the id would sort EARLIER than one already in the
    vault. Section 7.1: "One refusal is absolute and has no remedy path." It is
    passed straight through.

    `DuplicateIdError` -- the id would EQUAL one already in the vault, which
    happens when two reports are filed inside one second. The helper states the
    remedy in its own docstring: ids are second-precision, so mint again in the
    next second. Filing takes it, because the alternative is refusing a sound
    report for arriving too soon after another one -- and a producer told to
    "try again in a second" will simply be re-run, which is the same wait with
    a round trip around it. The wait is bounded by `attempts` and by one second
    each; nothing here reads or formats a clock to do it.
    """
    ids = _afrd_ids()
    if not isinstance(producer, str) or not producer.strip():
        # The matrix and enum checks own `producer` itself. This says why no id
        # was minted, so the dedup refusal that follows is not the only trace.
        return None, [
            Failure(
                rule="section 7.1 mint",
                where="frontmatter `producer`",
                expected="a producer to mint an `artifact_id` for -- the id is "
                "`PRODUCER-YYYYMMDDTHHMMSSZ`, so filing cannot mint without one",
                found="nothing" if producer is None else "`%s`" % producer,
            )
        ]
    last = None
    for remaining in range(attempts - 1, -1, -1):
        try:
            return ids.mint_artifact_id(producer, vault_root=root), []
        except ids.DuplicateIdError as exc:
            # Equal, not earlier. The remedy is one second of patience.
            last = exc
            if remaining:
                time.sleep(1.0)
        except ids.OrderingGuardError as exc:
            # Section 7.1: "One refusal is absolute and has no remedy path" -- an
            # id that does not sort after the high-water mark. Letting it through
            # with a warning means the vault quietly stops being ordered, which is
            # the one property timestamp ids were chosen for. The helper's message
            # says what to look at; it is passed through rather than summarised.
            return None, [
                Failure(
                    rule="section 7.1 artifact_id ordering",
                    where="the id filing would mint for `%s`" % producer,
                    expected="an id sorting after the vault high-water mark. "
                    "This refusal has no remedy path: something is wrong with "
                    "the clock or the helper and it needs looking at rather "
                    "than working around (section 7.1)",
                    found="`%s`" % exc,
                )
            ]
        except ids.IdFormatError as exc:
            return None, [
                Failure(
                    rule="section 7.1 mint",
                    where="frontmatter `producer`",
                    expected="a producer prefix the helper will mint for",
                    found="`%s`" % exc,
                )
            ]
    return None, [
        Failure(
            rule="section 7.1 artifact_id identity",
            where="the id filing would mint for `%s`" % producer,
            expected="an id no artifact in the vault already carries. Filing "
            "waited for the next second and re-minted %d times and still "
            "collided, which is not two reports arriving together -- the clock "
            "is not advancing, or the vault carries an id from the future "
            "(schema rule 13)" % attempts,
            found="`%s`" % last,
        )
    ]


def _with_artifact_id(text, minted):
    """The report with `artifact_id` set to the minted id, and nothing else moved.

    Line endings are preserved as they were found: the note that lands on disk
    differs from what the producer handed back in exactly one line.
    """
    lines = text.splitlines(keepends=True)
    fences = [i for i, line in enumerate(lines) if line.strip().lstrip("\ufeff") == "---"]
    open_at, close_at = fences[0], fences[1]
    eol = _eol(lines[open_at])

    for i in range(open_at + 1, close_at):
        if re.match(r"^artifact_id\s*:", lines[i]):
            lines[i] = "artifact_id: %s%s" % (minted, eol)
            return "".join(lines)

    lines.insert(open_at + 1, "artifact_id: %s%s" % (minted, eol))
    return "".join(lines)


def _eol(line):
    if line.endswith("\r\n"):
        return "\r\n"
    return "\n" if line.endswith("\n") else ""


# --------------------------------------------------------------- step 3


def _staged_registry(vault, proposed, minted):
    """`conventions.md` as it would be after this filing. Returns text and new refs.

    A ref the registry already carries is NOT written again. `conventions.md`:
    "A proposed ref that already exists means the system is correctly noticing
    this may be the same choice... Reuse the existing entry." Reuse is what the
    registry asks for, and an existing entry's `minted` date is a historical fact
    about the FIRST report to carry the ref, so nothing here touches it.

    Called with no proposals at all when the proposals themselves were refused:
    a half-formed entry has nothing to stage, and the refusal already says so.
    """
    path = vault.conventions_registry
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return None, [], [
            Failure(
                rule="section 7.1 registry write",
                where=str(path),
                expected="a conventions registry filing can read and extend",
                found="`%s`" % exc,
            )
        ]

    new = [e for e in proposed if e["ref"] not in vault.conventions]
    if not new:
        return text, [], []
    if minted is None:
        # Nothing to attribute the entries to. The mint failure is already in
        # the refusal; adding a second one here would name one cause twice.
        return text, new, []

    if _REGISTRY_ANCHOR not in text:
        return None, new, [
            Failure(
                rule="section 7.1 registry write",
                where=str(path),
                expected="a `## Registry` section closed by a `---` rule and "
                "`## Fields`, which is where a new entry goes. Filing refuses "
                "rather than guessing a position: an entry written into the "
                "wrong section is a registry nobody can read by eye",
                found="neither",
            )
        ]

    minted_on = _minted_date(minted)
    blocks = "".join(_render_entry(entry, minted, minted_on) for entry in new)
    at = text.index(_REGISTRY_ANCHOR)
    return text[:at] + "\n" + blocks.rstrip("\n") + "\n" + text[at:], new, []


def _minted_date(minted):
    """The `minted` date, read back off the minted id rather than off the clock.

    `minted` is "the date of the first report to carry the ref". Reading a second
    clock here could disagree with the one the id was minted from and date an
    entry to a different day than the report it attributes.
    """
    ids = _afrd_ids()
    return ids.parse_id(str(minted))[1].date().isoformat()


def _render_entry(entry, minted, minted_on):
    """One registry entry, in the shape the registry already uses.

    `minted_by` and `status` are filing's, not the producer's: the id because the
    producer cannot know it, the status because the registry permits an agent no
    other one.
    """
    out = ["```yaml\n", "- ref: %s\n" % entry["ref"]]
    out.append(_folded("description", entry["description"], "  "))
    out.append("  minted_by: %s\n" % minted)
    out.append(_folded("minted_because", entry["minted_because"], "  "))
    out.append("  minted: %s\n" % minted_on)
    out.append("  status: %s\n" % _PROPOSED_STATUS)
    out.append("```\n\n")
    return "".join(out)


def _folded(key, value, indent, width=76):
    """A `>-` block scalar, wrapped, in the registry's layout."""
    words = " ".join(str(value).split()).split(" ")
    body_indent = indent + "  "
    lines = []
    current = body_indent
    for word in words:
        if current.strip() and len(current) + 1 + len(word) > width:
            lines.append(current)
            current = body_indent + word
        else:
            current = current + (" " if current.strip() else "") + word
    if current.strip():
        lines.append(current)
    return "%s%s: >-\n%s\n" % (indent, key, "\n".join(lines))


def _check_conventions_resolve(fm, vault, proposed):
    """Section 7: every `conventions_applied` ref resolves in `conventions.md`.

    Deferred out of the checking half, and this is where it belongs: section 7.1
    puts the write before the check so "a proposed entry always resolves". The
    set below is the registry AFTER this filing -- what it carries now, plus what
    this report proposes -- which is the state the section describes the check
    running against.
    """
    applied = fm.get("conventions_applied")
    if not isinstance(applied, list) or not applied:
        return []

    after = set(vault.conventions) | {e["ref"] for e in proposed}
    out = []
    for index, ref in enumerate(applied):
        if isinstance(ref, str) and ref in after:
            continue
        out.append(
            Failure(
                rule="section 7 conventions_applied",
                where="frontmatter `conventions_applied` entry %d" % (index + 1),
                expected="a ref that resolves in %s after this filing -- either "
                "already registered, or proposed in this report as a PROPOSED "
                "REGISTRY ENTRY block, which filing writes (section 7.1). "
                "Registered today: %s"
                % (
                    vault.conventions_registry.name,
                    ", ".join("`%s`" % r for r in sorted(vault.conventions)) or "none",
                ),
                found="`%s`" % ref if isinstance(ref, str) else repr(ref),
            )
        )
    return out


# --------------------------------------------------------------- step 5


def _note_path(root, fm, text, minted):
    """`afrd/research/<date>-<slug>.md` -- human-readable, and NOT the id.

    Schema rule 7: filenames are date-prefixed and readable because Obsidian
    wikilinks and the graph view use them, and `[[MARKET_STRUCTURE-2026...]]`
    tells a reader nothing. The id lives in the frontmatter.

    Two filings of the same report carry two ids and want one filename, so a
    taken name gets a numeric tail. That is safe precisely because the filename
    carries no identity: nothing resolves against it.
    """
    stem = "%s-%s" % (_minted_date(minted), _slug(fm, text))
    directory = root / "afrd" / "research"
    path = directory / ("%s.md" % stem)
    n = 2
    while path.exists():
        path = directory / ("%s-%d.md" % (stem, n))
        n += 1
    return path


def _slug(fm, text):
    """The note's name: its first heading, or the idea it tests."""
    source = _first_heading(text)
    if not source:
        ref = fm.get("hypothesis_ref")
        source = ref[len("HYP-"):] if isinstance(ref, str) and ref.startswith("HYP-") else ref
    words = re.sub(r"[^a-z0-9]+", " ", str(source or "report").lower()).split()
    return "-".join(words[:_MAX_SLUG_WORDS]) or "report"


def _first_heading(text):
    for line in text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return ""


def _guard_target(path, root):
    """The two destinations, and no third one.

    Section 7.1 gives filing write access for exactly two purposes. This is what
    makes "never writes outside `afrd/research/` and `afrd/system/conventions.md`"
    a property of the code rather than a claim in a docstring.
    """
    target = Path(path).resolve()
    research = (Path(root) / "afrd" / "research").resolve()
    registry = (Path(root) / "afrd" / "system" / "conventions.md").resolve()
    if target == registry:
        return target
    if target.parent == research and target.suffix == ".md":
        return target
    raise ValueError(
        "filing refuses to write %s. It writes the note into %s and new "
        "provisional entries into %s, and nowhere else." % (target, research, registry)
    )


def _write(path, text, root):
    """The only write in this package. Goes through the guard, always."""
    target = _guard_target(path, root)
    with open(target, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)
    return target
