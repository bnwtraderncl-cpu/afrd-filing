"""`validate(report) -> (ok, failures)` -- the checkable half of filing.

WHAT THIS IS
------------
`pass_fail_hold_standard.md` section 1 splits every rule in that standard into exactly
two kinds: `[C]` checkable, enforced by the filing script, deterministic; and
`[J]` judgement, enforced by a reader. This implements the `[C]` rules and
nothing else. A check that needs an opinion about whether a negative is
well-founded, whether divergence evidence is a demonstration, or whether the
report answers its brief at all is section 8's list of what the script cannot check,
and it stays the lead's.

The gate REFUSES on any failure (section 7.1). There is no warn-and-file. But it
refuses with EVERY failure it found, not the first: a producer fixing one error
per round trip is a worse loop than the one this replaces.

THIS WRITES NOTHING. section 7.1 makes registry writes part of filing, and this is the
checking half only. See README, "The half that is missing".

WHAT IS DELIBERATELY NOT CHECKED HERE
-------------------------------------
Two rows of section 7's table are absent on purpose, and neither is an oversight:

  `conventions_applied` resolving in `conventions.md`
      section 7.1 orders the two operations: filing WRITES the producer's proposed
      entries, and THEN checks that every ref resolves. "The check runs after
      the write, so a proposed entry always resolves." Implemented here, before
      the write exists, it would refuse every report that proposes a convention
      -- which is precisely the failure section 7.1 is written to prevent. It belongs
      with the writing half and is deferred to it.

  `artifact_id` ordering against the vault high-water mark
      Same section: "filing mints through the helper, so `artifact_id` is
      correct by construction rather than checked after the fact." The guard
      already exists in `afrd-ids` and refuses at mint. Re-implementing it as a
      post-hoc check would be a second, weaker copy of a rule that has a home.

The `artifact_id` DEDUP check is here, and is a different rule: section 7's table lists
"Dedup -- no existing note with this `artifact_id`" separately from ordering,
and it needs no minting to perform.
"""

from __future__ import annotations

from pathlib import Path

from .failures import Failure
from .frontmatter import FrontmatterError, parse, split_frontmatter
from .rules import (
    ENUMS,
    FORBIDDEN,
    MATRIX_FIELDS,
    REQUIRED,
    RETRY_BOUND,
    matrix_column,
)
from . import vault as vault_module


def validate(report, vault_root=None, vault=None):
    """Check a research report against the `[C]` rules. Returns (ok, failures).

    `report` is the report TEXT, or a `Path` to a note. Text is the primary
    form: the gate runs on what a producer hands back in conversation, before
    anything is filed, so there is usually no file to point at. The path form
    exists so the gate can be run against notes already in the vault -- and it
    carries one behavioural difference, which is that a note validated from its
    own path does not collide with itself on the dedup check.

    `vault` accepts an already-loaded `vault.Vault`, so a caller checking a
    batch of reports reads the briefs and registries once.
    """
    source_path = None
    if isinstance(report, Path):
        source_path = report
        text = report.read_text(encoding="utf-8")
    elif isinstance(report, str):
        text = report
    else:
        raise TypeError(
            "report must be the report text or a Path to a note, got %s"
            % type(report).__name__
        )

    failures = []
    try:
        fm = parse(split_frontmatter(text))
    except FrontmatterError as exc:
        return False, [
            Failure(
                rule="frontmatter",
                where=_origin(source_path),
                expected="a YAML frontmatter block the gate can read",
                found="`%s`" % exc,
            )
        ]
    if not isinstance(fm, dict):
        return False, [
            Failure(
                rule="frontmatter",
                where=_origin(source_path),
                expected="frontmatter to be a mapping of fields",
                found="a %s" % type(fm).__name__,
            )
        ]

    if vault is None:
        vault = vault_module.load(vault_root, exclude=source_path)

    failures += check_enums(fm)
    failures += check_field_presence(fm)
    failures += check_retry_bound(fm)
    failures += check_status(fm)
    failures += check_brief_ref(fm, vault)
    failures += check_hypothesis_ref(fm, vault)
    failures += check_data_sources(fm, vault)
    failures += check_scope_window(fm, vault)
    failures += check_dedup(fm, vault)
    failures += check_convention_accounting(fm)

    return (not failures), failures


def _origin(source_path):
    return "report frontmatter" if source_path is None else str(source_path)


def _show(value):
    """A value as it should appear in a refusal: short, quoted, never a dump."""
    if value is None:
        return "nothing"
    if isinstance(value, str):
        one_line = " ".join(value.split())
        if len(one_line) > 60:
            one_line = one_line[:57] + "..."
        return "`%s`" % one_line
    if isinstance(value, list):
        return "a list of %d" % len(value)
    if isinstance(value, dict):
        return "a mapping of %d keys" % len(value)
    return "`%r`" % value


# ------------------------------------------------------------------ section 7 checks


def check_enums(fm):
    """Every closed enum value known. Schema rule 1: an unknown value is invalid."""
    out = []
    for field, allowed in ENUMS.items():
        if field not in fm:
            continue
        value = fm[field]
        if value in allowed:
            continue
        out.append(
            Failure(
                rule="section 7 enum validity",
                where="frontmatter `%s`" % field,
                expected="one of %s (closed enum, frontmatter_schema.md rule 1 "
                "-- an agent may not coin a value)"
                % ", ".join("`%s`" % v for v in allowed),
                found=_show(value),
            )
        )
    return out


def check_field_presence(fm):
    """Field presence against the section 5 matrix, exactly.

    A dash in the published matrix is FORBIDDEN, not unspecified. The reasoning
    printed under the table is that a `scope` or `brief` hold reached no
    conclusion, so a `finding` on one asserts a result that does not exist.
    """
    outcome = fm.get("outcome")
    hold_type = fm.get("hold_type")

    if outcome not in ("pass", "hold", "fail"):
        # Without a valid outcome there is no column to check against. The enum
        # check has already refused the value; saying so twice, in two
        # vocabularies, is noise.
        return []

    column, column_name = matrix_column(outcome, hold_type)
    if column is None:
        # `outcome: hold` with an absent or unknown `hold_type`. Which of the
        # three columns applies is undecidable, so the matrix cannot be run --
        # but `hold_type` itself is required on every hold, and that is a
        # failure this check owns rather than leaves to the enum check.
        return [
            Failure(
                rule="section 5 field presence",
                where="frontmatter `hold_type`",
                expected="outcome `hold` must carry `hold_type` as one of "
                "`authority`, `scope`, `brief` (section 5 matrix; it selects "
                "which column applies, so nothing else on the matrix can be "
                "checked without it)",
                found=_show(hold_type),
            )
        ]

    out = []
    for field in MATRIX_FIELDS:
        rule = column[field]
        present = field in fm and fm[field] is not None
        if rule is REQUIRED and not present:
            out.append(
                Failure(
                    rule="section 5 field presence",
                    where="frontmatter `%s`" % field,
                    expected="%s requires `%s` (section 5 matrix)" % (column_name, field),
                    found="nothing"
                    if field not in fm
                    else "`%s:` present but empty" % field,
                )
            )
        elif rule is FORBIDDEN and present:
            out.append(
                Failure(
                    rule="section 5 field presence",
                    where="frontmatter `%s`" % field,
                    expected="%s must not carry `%s` (section 5 matrix)"
                    % (column_name, field),
                    found="`%s: %s`" % (field, _bare(fm[field])),
                )
            )
    return out


def _bare(value):
    shown = _show(value)
    return shown[1:-1] if shown.startswith("`") and shown.endswith("`") else shown


def check_retry_bound(fm):
    """section 4: the bound is 1, and an exhausted fail is the one that reaches the operator.

    Marked `[C]` in section 4 and pulled in by section 7's opening line, "Everything marked
    `[C]`, plus:" -- it is not one of the rows in section 7's table.
    """
    out = []
    attempt = fm.get("attempt")
    if isinstance(attempt, bool) or not isinstance(attempt, int):
        if attempt is not None:
            out.append(
                Failure(
                    rule="section 4 retry bound",
                    where="frontmatter `attempt`",
                    expected="an integer (schema types `attempt` as one; retry "
                    "state lives in this field, rule 8)",
                    found=_show(attempt),
                )
            )
        return out

    if attempt < 1 or attempt > RETRY_BOUND:
        out.append(
            Failure(
                rule="section 4 retry bound",
                where="frontmatter `attempt`",
                expected="1 or 2 -- the bound is 1 re-delegation, then stop (section 4)",
                found="`attempt: %d`" % attempt,
            )
        )
        return out

    if fm.get("outcome") != "fail":
        return out

    status = fm.get("status")
    if attempt == RETRY_BOUND and status != "awaiting_operator":
        out.append(
            Failure(
                rule="section 4 retry bound",
                where="frontmatter `status`",
                expected="an exhausted fail (`attempt: 2`) is `status: "
                "awaiting_operator` -- it is the one that reaches the operator (section 4)",
                found=_show(status),
            )
        )
    elif attempt < RETRY_BOUND and status != "stored":
        out.append(
            Failure(
                rule="section 4 retry bound",
                where="frontmatter `status`",
                expected="a fail at `attempt: 1` returns to RC and is `status: "
                "stored` -- the operator is not needed until the bound is "
                "exhausted (section 4)",
                found=_show(status),
            )
        )
    return out


def check_brief_ref(fm, vault):
    """section 7: `brief_ref` resolves to a brief in `briefs/`."""
    ref = fm.get("brief_ref")
    if ref is None:
        return [
            Failure(
                rule="section 7 brief_ref",
                where="frontmatter `brief_ref`",
                expected="a `BRIEF-` ref naming the brief this report answers "
                "(the brief is the acceptance criteria the gate checks against)",
                found="nothing",
            )
        ]
    if ref in vault.briefs:
        return []
    return [
        Failure(
            rule="section 7 brief_ref",
            where="frontmatter `brief_ref`",
            expected="a ref carried by a brief in %s (%d brief%s there: %s)"
            % (
                (vault.root / "afrd" / "briefs").as_posix(),
                len(vault.briefs),
                "" if len(vault.briefs) == 1 else "s",
                ", ".join("`%s`" % r for r in sorted(vault.briefs)) or "none",
            ),
            found=_show(ref),
        )
    ]


def check_hypothesis_ref(fm, vault):
    """section 7: `hypothesis_ref` resolves in `hypotheses.md`, and matches the brief's."""
    out = []
    ref = fm.get("hypothesis_ref")
    registry = vault.root / "afrd" / "system" / "hypotheses.md"
    if ref is None:
        return [
            Failure(
                rule="section 7 hypothesis_ref",
                where="frontmatter `hypothesis_ref`",
                expected="a `HYP-` ref registered in %s -- it is the only field "
                "that groups tests of one idea (schema rule 4)" % registry,
                found="nothing",
            )
        ]
    if ref not in vault.hypotheses:
        out.append(
            Failure(
                rule="section 7 hypothesis_ref",
                where="frontmatter `hypothesis_ref`",
                expected="a ref registered in %s. Minting a new one is an "
                "operator decision (schema rule 9.5): a ref that resolves to "
                "nothing groups this result with nothing" % registry,
                found=_show(ref),
            )
        )

    brief = vault.briefs.get(fm.get("brief_ref"))
    if brief is None:
        # The brief_ref check has already refused; there is nothing to match
        # against and a second failure would name the same cause twice.
        return out
    if brief.hypothesis_ref != ref:
        out.append(
            Failure(
                rule="section 7 hypothesis_ref",
                where="frontmatter `hypothesis_ref`",
                expected="the `hypothesis_ref` of the brief it answers -- `%s` "
                "carries `%s` (%s)"
                % (brief.brief_ref, brief.hypothesis_ref, brief.path.name),
                found=_show(ref),
            )
        )
    return out


def check_data_sources(fm, vault):
    """section 7: every `data_sources` entry resolves in `data_sources.md`.

    `data_sources.md` rule 2 says what resolving means: "an id that is in this
    file. Not a description, not a symbol, not an intention." Schema rule 3 says
    why -- `data_sources` is what a finding RESTS ON and must be a complete
    enumerable population, and the registry is what makes it enumerable.
    """
    registry = vault.root / "afrd" / "system" / "data_sources.md"
    entries = fm.get("data_sources")
    if entries is None:
        return [
            Failure(
                rule="section 7 data_sources",
                where="frontmatter `data_sources`",
                expected="the sources the finding rests on, each a `source_id` "
                "from %s (schema rule 3)" % registry,
                found="nothing",
            )
        ]
    if not isinstance(entries, list):
        return [
            Failure(
                rule="section 7 data_sources",
                where="frontmatter `data_sources`",
                expected="a list of `source_id`s (the schema types it a list)",
                found=_show(entries),
            )
        ]

    known = ", ".join("`%s`" % s for s in sorted(vault.data_sources)) or "none"
    out = []
    for index, entry in enumerate(entries):
        if isinstance(entry, str) and entry in vault.data_sources:
            continue
        out.append(
            Failure(
                rule="section 7 data_sources",
                where="frontmatter `data_sources` entry %d" % (index + 1),
                expected="a `source_id` from %s, not a description "
                "(data_sources.md rule 2). Registered today: %s"
                % (registry.name, known),
                found=_show(entry),
            )
        )
    return out


def check_scope_window(fm, vault):
    """section 7: the scope window starts no earlier than `usable_from` for that source.

    `data_sources.md` rule 3 is the reason the check is not decorative: a window
    starting before `usable_from` returns rows, fires no gap report, and yields
    an intraday statistic computed over a daily series wearing an H1 label.
    """
    window_raw = fm.get("scope_window")
    entries = fm.get("data_sources")
    if window_raw is None:
        # `scope_window` is not on the section 5 matrix and no rule in the
        # standard makes it required, so its absence is not refused here. What
        # is refused is a window that is present and cannot be read.
        return []

    window = vault_module.parse_scope_window(window_raw)
    if window is None:
        return [
            Failure(
                rule="section 7 scope window",
                where="frontmatter `scope_window`",
                expected="an ISO date range, `YYYY-MM-DD/YYYY-MM-DD` (schema "
                "types it one). The gate cannot compare a window it cannot read "
                "against `usable_from`",
                found=_show(window_raw),
            )
        ]
    start, end = window
    out = []
    if end < start:
        out.append(
            Failure(
                rule="section 7 scope window",
                where="frontmatter `scope_window`",
                expected="a range whose start is on or before its end",
                found=_show(window_raw),
            )
        )
    for entry in entries if isinstance(entries, list) else []:
        source = vault.data_sources.get(entry) if isinstance(entry, str) else None
        if source is None:
            # Unresolvable: already refused by check_data_sources, and there is
            # no `usable_from` to compare against.
            continue
        if start < source.usable_from:
            out.append(
                Failure(
                    rule="section 7 scope window",
                    where="frontmatter `scope_window` against `%s`" % source.source_id,
                    expected="a window starting no earlier than that source's "
                    "`usable_from`, `%s` (%s bars before it are labelled `%s` "
                    "and are not; the series is continuous across the boundary, "
                    "so nothing looks wrong -- data_sources.md rule 3)"
                    % (source.usable_from_raw, source.source_id, source.granularity),
                    found="`scope_window: %s`, starting %s"
                    % (window_raw, start.date().isoformat()),
                )
            )
    return out


def check_dedup(fm, vault):
    """section 7: no existing note carries this `artifact_id`.

    Schema rule 13: equal ids are an identity failure, not an ordering one --
    `minted_by`, `supersedes` and every citation become ambiguous and nothing
    can say which artifact was meant.
    """
    value = fm.get("artifact_id")
    if value is None:
        return [
            Failure(
                rule="section 7 dedup",
                where="frontmatter `artifact_id`",
                expected="an `artifact_id`, minted through the helper in "
                "C:\\dev\\afrd-ids (schema rule 13)",
                found="nothing",
            )
        ]
    holder = vault.artifact_ids.get(value)
    if holder is None:
        return []
    return [
        Failure(
            rule="section 7 dedup",
            where="frontmatter `artifact_id`",
            expected="an id no filed note already carries -- two artifacts "
            "under one id make `minted_by` and every citation ambiguous "
            "(schema rule 13). Mint again through C:\\dev\\afrd-ids",
            found="`%s`, already carried by %s"
            % (value, holder.relative_to(vault.root) if _under(holder, vault.root) else holder),
        )
    ]


def _under(path, root):
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def check_status(fm):
    """section 5: `status` matches the table for the outcome.

    Written down in v0.4 and marked `[C]`. Before that it was a rule every
    sample note followed and nothing could refuse a note for ignoring.

        pass                  stored
        hold, any type        awaiting_operator
        fail, attempt 1       stored              -- check_retry_bound
        fail, exhausted       awaiting_operator   -- check_retry_bound

    The two fail rows stay with `check_retry_bound`, which already owns them and
    can say WHY (the operator is not needed until the bound is exhausted). This
    covers the two rows nothing checked before.

    `superseded` is refused here like any other mismatch. section 5: it "is set
    later, by whatever supersedes the note; a producer never mints one" -- and
    what this gate reads is a report being filed, whose frontmatter its producer
    wrote. The cost is that re-running the gate over an already-superseded note
    on disk refuses it, which is the gate being used outside what it is for.
    """
    outcome = fm.get("outcome")
    if outcome == "pass":
        expected, why = "stored", "a pass is filed and blocks nothing"
    elif outcome == "hold":
        expected, why = (
            "awaiting_operator",
            "a hold is the outcome only the operator can resolve",
        )
    else:
        # `fail` is check_retry_bound's, and an unknown outcome is the enum
        # check's. Neither is restated here.
        return []

    status = fm.get("status")
    if status == expected:
        return []
    return [
        Failure(
            rule="section 5 status",
            where="frontmatter `status`",
            expected="`status: %s` on outcome `%s` -- %s (section 5 table). "
            "`status` is queue membership only (schema rule 8)"
            % (expected, outcome, why),
            found=_show(status),
        )
    ]


def check_convention_accounting(fm):
    """section 6: every applied convention accounted for, in exactly one field.

    Three rules, all `[C]`:

      presence    `untested_dependence` is required whenever `conventions_applied`
                  is non-empty. Presence only -- whether `what_would_change`
                  names a direction of risk is `[J]`.

      accounting  every convention in `conventions_applied` appears in
                  `robustness_tested` or `untested_dependence`, "and not both".

      restatement a `robustness_tested` entry with `held: false` carries
                  `conclusion_now_rests_on`.

    v0.3 had no field for a variation that was performed and HELD, so the
    accounting it called mechanical was not: a convention varied successfully
    lived in the note's body, and the gate had to refuse an honest report or
    check nothing. `robustness_tested` (v0.4 section 6, schema rule 12) records
    both outcomes, and that is what closes it.

    What is still not mechanical, and is section 8's: that a variation was run
    and went unreported.
    """
    applied = fm.get("conventions_applied")
    tested_raw = fm.get("robustness_tested")

    out = _check_robustness_entries(tested_raw)

    if applied is None or (isinstance(applied, list) and not applied):
        return out
    if not isinstance(applied, list):
        return out + [
            Failure(
                rule="section 6 conventions",
                where="frontmatter `conventions_applied`",
                expected="a list of `CONV-` refs (the schema types it a list)",
                found=_show(applied),
            )
        ]

    untested = fm.get("untested_dependence")
    if untested is None:
        out.append(
            Failure(
                rule="section 6 untested_dependence",
                where="frontmatter `untested_dependence`",
                expected="required whenever `conventions_applied` is non-empty "
                "(section 6; schema rule 11). An empty list is valid only if "
                "every applied convention appears in `robustness_tested`",
                found="nothing, alongside `conventions_applied` with %d entr%s"
                % (len(applied), "y" if len(applied) == 1 else "ies"),
            )
        )
        untested = []
    elif not isinstance(untested, list):
        out.append(
            Failure(
                rule="section 6 untested_dependence",
                where="frontmatter `untested_dependence`",
                expected="a list of entries, each naming a `convention` "
                "(schema rule 11)",
                found=_show(untested),
            )
        )
        untested = []

    not_varied = _named_conventions(untested, "untested_dependence")
    varied = _named_conventions(tested_raw, "robustness_tested")
    accounted = not_varied | varied

    for index, ref in enumerate(applied):
        in_untested = isinstance(ref, str) and ref in not_varied
        in_tested = isinstance(ref, str) and ref in varied
        if in_untested and in_tested:
            out.append(
                Failure(
                    rule="section 6 convention accounting",
                    where="frontmatter `conventions_applied` entry %d" % (index + 1),
                    expected="each applied convention in EXACTLY ONE of "
                    "`robustness_tested` or `untested_dependence` -- the two "
                    "partition what was checked from what was not, and a "
                    "convention in both says two contradictory things about one "
                    "choice (section 6; schema rule 11)",
                    found="`%s`, in both" % ref,
                )
            )
        elif not (in_untested or in_tested):
            out.append(
                Failure(
                    rule="section 6 convention accounting",
                    where="frontmatter `conventions_applied` entry %d" % (index + 1),
                    expected="every applied convention accounted for -- named in "
                    "a `robustness_tested` entry if it was varied, whether it "
                    "held or not, or in an `untested_dependence` entry if it was "
                    "not (section 6; schema rule 11). An unlisted dependence "
                    "presents a conclusion as resting on fewer choices than it "
                    "does",
                    found=_show(ref)
                    + (
                        " -- accounted for: none"
                        if not accounted
                        else " -- accounted for: %s"
                        % ", ".join("`%s`" % c for c in sorted(accounted))
                    ),
                )
            )
    return out


def _check_robustness_entries(entries):
    """Schema rule 12: `held` on every entry, `conclusion_now_rests_on` when false.

    Checked whether or not `conventions_applied` is populated: an entry
    recording a variation whose result nobody can read is the defect regardless
    of what else the note carries.
    """
    if entries is None:
        return []
    if not isinstance(entries, list):
        return [
            Failure(
                rule="section 6 robustness_tested",
                where="frontmatter `robustness_tested`",
                expected="a list of entries, each naming a `convention` and "
                "carrying `held` (schema rule 12)",
                found=_show(entries),
            )
        ]

    out = []
    for index, entry in enumerate(entries):
        where = "frontmatter `robustness_tested` entry %d" % (index + 1)
        if not isinstance(entry, dict):
            out.append(
                Failure(
                    rule="section 6 robustness_tested",
                    where=where,
                    expected="a mapping carrying `convention`, `substituted`, "
                    "`held` and `what_happened` (schema rule 12)",
                    found=_show(entry),
                )
            )
            continue
        named = entry.get("convention")
        where = "%s (`%s`)" % (where, named if isinstance(named, str) else "unnamed")
        held = entry.get("held")
        if not isinstance(held, bool):
            out.append(
                Failure(
                    rule="section 6 robustness_tested",
                    where=where,
                    expected="`held: true` or `held: false` -- it is the field "
                    "the section 6 accounting reads, and an entry without it "
                    "records a variation whose result nobody can determine "
                    "(schema rule 12)",
                    found=_show(held),
                )
            )
            continue
        rests_on = entry.get("conclusion_now_rests_on")
        if held is False and not (isinstance(rests_on, str) and rests_on.strip()):
            out.append(
                Failure(
                    rule="section 6 robustness_tested",
                    where=where,
                    expected="`conclusion_now_rests_on` on every `held: false` "
                    "entry -- a broken strand without a restatement leaves the "
                    "reader unable to tell what survives, which looks like a "
                    "disclosure while withholding the thing it is for "
                    "(section 6; schema rule 12)",
                    found=_show(rests_on),
                )
            )
    return out


def _named_conventions(entries, field):
    """The `convention:` of each entry in `untested_dependence` or `robustness_tested`."""
    out = set()
    if not isinstance(entries, list):
        return out
    for entry in entries:
        if isinstance(entry, dict) and isinstance(entry.get("convention"), str):
            out.add(entry["convention"])
        elif isinstance(entry, str):
            # Rule 11's example is a mapping with `convention` and
            # `what_would_change`. A bare ref is not that shape, but it does
            # name the convention, and refusing the accounting on shape alone
            # would report the wrong problem.
            out.add(entry)
    return out
