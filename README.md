# afrd-filing

The AFRD filing gate: the checks, and the writes.

```python
from afrd_filing import validate, file_report

ok, failures = validate(report_text)      # check only. writes nothing
filed, where = file_report(report_text)   # check, mint, write -- or refuse
```

`file_report` returns `(True, Path)` or `(False, [Failure, ...])`. On a refusal
nothing has been written: not the note, not a registry entry, not a partial one.

```
[section 5 field presence] frontmatter `finding`: outcome `hold` with
`hold_type: scope` must not carry `finding` (section 5 matrix); found
`finding: inconclusive`
```

Over notes on disk, which is what the tests and the sample-note results below
use:

```
python -m afrd_filing C:\dev\vault\afrd\research\*.md
```

`validate` **writes nothing**, and `tests/test_read_only.py` asserts that
against its source. `file_report` writes two files and only two, after every
check has passed. See *The writing half*.

## What it is

`afrd/system/pass_fail_hold_standard.md` §1 divides every rule in that standard
into exactly two kinds:

| Kind | Marked | Enforced by |
|---|---|---|
| CHECKABLE | `[C]` | this package. Deterministic. Pass or fail, no opinion |
| JUDGEMENT | `[J]` | a reader — the lead, or the operator |

This implements the `[C]` rules. The `[J]` ones are not here and will not be:
§8 of the standard is its own list of what no schema makes mechanical, ending
with "whether the report answers the brief at all", which is the whole
substantive check and is the lead's.

**The gate refuses on any failure** (§7.1) — no warnings, no filing with
caveats. But it refuses with **every** failure it found, not the first. A
producer fixing one error per round trip across five round trips is a worse loop
than the one this replaces, and a refusal is the only thing the producer gets
back, so it has to be enough to fix the report from.

Every failure names four things: which rule refused, where, what was expected,
and what was found.

## Where this lives, and why it is a fourth repo

```
C:\dev\vault\          the notes. read-only from here.
C:\dev\afrd-data\      the MT5 harvester.
C:\dev\afrd-ids\       the one place an artifact_id or brief_ref is DERIVED.
C:\dev\afrd-filing\    this. the gate that decides whether a report may be filed.
```

The real alternative was folding this into `afrd-ids`, which already reads the
vault, already knows the schema, and already scans notes. Three reasons it went
here instead, and the cost of that is stated after them.

**1. The other half of filing writes to the vault.** §7.1 makes the registry
write *part of* filing rather than a precondition for it: filing writes the
producer's proposed `CONV-` entries to `conventions.md`, and only then checks
that every ref resolves. So the finished filing script mutates the vault.
`afrd-ids` guarantees the opposite — "This package writes to neither" — and
tests the guarantee against its own source. That guarantee is what makes it safe
to call from anywhere. Putting a vault writer in that repo either breaks it or
forces this split later; doing the split now costs one repo and no rework.

**2. The dependency runs filing → ids, and only that way.** The writing half
mints through `afrd_ids.mint_artifact_id`. A library whose caller lives inside
it is a circle waiting to happen.

**3. The overlap is thinner than it looks.** `afrd-ids` extracts two keys with a
line regex, deliberately, because two keys is all an ordering guard needs. The
gate reads whole reports — block scalars for `hold_reason`, sequences of
mappings for `untested_dependence` — which needs an actual parser that
`afrd-ids` has no reason to carry. And it needs an `artifact_id` → path map,
where `afrd-ids` needs only the maximum; `scan_vault` returns the wrong shape
and its extraction helpers are private. What is genuinely shared is a ~20-line
bounded head read of a note's frontmatter.

### The cost of that call

**Two repos now read vault frontmatter with their own reader.** If the schema
changes how frontmatter is laid out, two places follow it. That is a real cost
and it is the wrong call if the layout starts moving — it is accepted because
the two read for different purposes and at different depths, and because
`afrd-ids`'s reader is deliberately shallow in a way this one cannot be.

**The writing half needs `afrd_ids` importable from here.** Neither repo has
packaging, so `filing.py` inserts `C:\dev\afrd-ids` on `sys.path` when the
import fails, overridable with `AFRD_IDS_ROOT`. It is the path insert this
predicted, and it is the one line of this arrangement that an editable install
would remove.

**Not in the vault.** The vault is notes. `afrd-ids` already treats it as
read-only data, and so does this.

## What it checks

From §7's table and §7's opening line ("Everything marked `[C]`, plus:"). The
last two rows are `file_report`'s; everything above them is `validate`'s and runs
on a report before anything is written.

| Check | Rule |
|---|---|
| Field presence against the §5 matrix, exactly | §5 |
| `status` matches the §5 table for the outcome | §5 |
| Every closed enum value known | §7, schema rule 1 |
| `brief_ref` resolves to a brief in `briefs/` | §7 |
| `hypothesis_ref` resolves in `hypotheses.md`, and matches the brief's | §7 |
| Every `data_sources` entry resolves in `data_sources.md` | §7 |
| Scope window starts no earlier than `usable_from` for that source | §7 |
| No existing note carries this `artifact_id` | §7 |
| Every applied convention in exactly one of `robustness_tested` or `untested_dependence` | §6 |
| `untested_dependence` present when `conventions_applied` is non-empty | §6 |
| `held` on every `robustness_tested` entry, `conclusion_now_rests_on` when it is false | §6, schema rule 12 |
| `attempt` present and within the bound, and `status` on a fail | §4 |
| Every `conventions_applied` ref resolves in `conventions.md` after this filing | §7, §7.1 |
| `artifact_id` sorts after the vault high-water mark | §7, §7.1 |

The `attempt` row is not in §7's table. It is in §7 by way of its first line, and
§5 and §4 between them make three of its four claims `[C]`: an exhausted fail is
`attempt: 2` with `status: awaiting_operator`, a fail at attempt 1 is `stored`,
and there is no `retrying`. The fourth — that the bound was actually respected —
v0.4 corrects to `[J]`, because nothing counts delegations independently of the
producer's own claim. What is checked is that `attempt` is present, an integer,
and no greater than 2.

A dash in the §5 matrix is read as **forbidden**, not unspecified. That is the
schema's reading, not an inference: rule 6's prose says `finding: inconclusive`
on a scope hold "asserts a result that does not exist".

## The two checks that were deferred, and where they went

Both rows of §7's table that `validate` leaves out are now performed by
`file_report`, which is the only place either of them can run.

**`conventions_applied` refs resolving in `conventions.md`.** In `filing.py`,
against the registry *after* this filing -- what it carries now, plus what this
report proposes. Run inside `validate`, before any write exists, it would refuse
every report that proposes a convention, which is the situation §7.1 is written
to prevent.

**`artifact_id` ordering against the vault high-water mark.** At mint, by
`afrd-ids`, which owns the guard. `file_report` turns its refusal into a
`Failure` rather than reimplementing it.

`validate` on its own still performs neither, and still refuses nothing for a
`CONV-` ref it cannot resolve. Checking a report *before* filing it is exactly
the case where an unresolved proposal is correct.

Dedup is **not** the same rule and is implemented: §7's table lists it
separately, schema rule 13 makes an equal id an identity failure rather than an
ordering one, and it needs no minting to perform.

## The writing half

`afrd_filing/filing.py`. It mints the `artifact_id` through `afrd-ids`, writes
the producer's proposed `CONV-` entries to `conventions.md`, runs every check
including the two this package deferred, and writes the note -- or refuses and
writes nothing.

### The order §7.1 fixes, and the problem in it

§7.1 puts the registry write *before* the resolution check, and says why: "The
check runs after the write, so a proposed entry always resolves. The registry
cannot be behind, because filing is what advances it." That is what stops a
proposed convention from ever being a bookkeeping refusal.

But step 2 writes and step 3 can still refuse, so read literally the order
leaves registry entries for a report that was never filed -- a `minted_by`
naming nothing, which `conventions.md` calls a dangling reference and makes an
operator action to resolve. The vault already carries one instance of that.

**The write is staged.** The registry text step 2 would produce is built in
memory, every check runs against the vault *as it would be* after that write,
and the bytes reach the disk only once nothing has refused.

    stage  ->  check against the staged state  ->  commit, or discard

This is §7.1's ordering, not a departure from it: the section's requirement is
about what the **check sees**, and what the check is run against is the staged
registry. What it does not do is require the disk to pass through a state that
only a later success justifies.

**Staged rather than rolled back.** A rollback preserves "nothing is written on
refusal" only if the undo itself runs and succeeds; a crash between the write
and the undo leaves exactly the dangling entry the rule exists to prevent, and
leaves it silently. Staging makes the property hold because nothing was written,
which needs no code to work correctly at the moment things are going wrong.

### What it writes, and nowhere else

| Path | What |
|---|---|
| `afrd/research/<date>-<slug>.md` | the note, body intact, `artifact_id` replaced with the minted one |
| `afrd/system/conventions.md` | new proposed entries, at `status: provisional` |

Every path goes through `_guard_target` before it is opened, so the two
destinations are a property of the code and not a claim in a docstring.
`hypotheses.md` is not written: `hypothesis_ref` is assigned when the brief is
written, not at filing.

The note goes down first and the registry second. Either write can still fail on
the filesystem, and of the two half-states a note citing an unregistered ref is
the recoverable one -- it does not resolve, the gate says so, and re-filing the
entry repairs it. A registry entry naming a note that does not exist is the one
only the operator may resolve.

### What it mints, and what it overwrites

The `artifact_id` is minted here and **replaces** whatever the report carried:
§7.1, "filing mints through the helper, so `artifact_id` is correct by
construction rather than checked after the fact". Nothing in the module formats a
timestamp.

`minted_by` on every proposed entry is rewritten to that minted id, for the same
reason. A producer writes its own `artifact_id` there and cannot know the id
filing will mint, so keeping the producer's value would register a convention
against an id no note carries -- the dangling reference again, created at the
moment of filing.

A ref the registry already carries is **not** written a second time.
`conventions.md`: "A proposed ref that already exists means the system is
correctly noticing this may be the same choice... Reuse the existing entry." An
existing entry is left untouched, including its `minted` date, which is a fact
about the first report to carry the ref.

Two reports filed inside one second collide on the id. The helper refuses that
outright and names the remedy -- ids are second-precision, so mint again in the
next second -- and filing takes it, waiting and re-minting up to three times. The
alternative is refusing a sound report for arriving too soon after another one,
and a producer told to try again in a second is simply re-run, which is the same
wait with a round trip around it. An id that would sort **earlier** than the
high-water mark is a different refusal and has no remedy path (§7.1); it is
passed straight through.

## The five sample notes

`afrd/research/` holds five notes. **None of them passes**, and none has been
modified. What each fails on is recorded in `tests/test_sample_notes.py`, so a
regression in the gate shows up as a *new* failure on a known note.

The failures are the vault's, not the gate's:

**`brief_ref` — all five.** Each cites a brief (`BRIEF-20260209T0930Z` and four
others) that is not in `afrd/briefs/`. That directory holds two briefs, both
minted 2026-09-04. The sample notes are schema demonstrations written before any
brief existed, and their refs were invented alongside their content — the same
status schema rule 13 gives their `artifact_id` timestamps, which it calls
"invented content, not clock readings".

**`data_sources` — all five.** Every entry is a prose description ("CME ES
front-month continuous 5m bars, 2015-01-02 to 2021-12-31…") rather than a
`source_id`. `data_sources.md` rule 2 is explicit: "an id that is in this file.
Not a description, not a symbol, not an intention." The registry holds two
sources, both Vantage XAUUSD; the samples cite CME, CBOE, CBOT and the US
Treasury, and that file already says of them that they "are not here, are not
connected, and are not available to cite."

**`attempt` — `2026-08-28-quarterly-refunding-front-end-response.md` only.** The
note carries no `attempt`. §5 requires it in every column of the matrix, on every
outcome. This is the one failure of the three that a report handed back today
would also produce, and it is a plain omission in the note.

Everything else about the five is sound: all parse, every `hypothesis_ref`
resolves, every enum value is known, no matrix cell beyond that one `attempt` is
wrong, and no id is duplicated.

## What the standard leaves ambiguous

Found while implementing, not resolved here.

Three of the five found against v0.3 were closed by v0.4 and are implemented
rather than listed: `robustness_tested` gives the accounting a field for a
variation that HELD, §5 now fixes `status` on every outcome, and §4's "the bound
is 1" is marked `[J]` rather than claimed checkable. What is left is below.

**§7.1 does not say what happens to the producer's own copy of a proposed
entry.** The producer writes `minted_by: <its own artifact_id>` into the
proposal block in its report, and cannot know the id filing will mint. Filing
rewrites `minted_by` in the entry it registers, so the registry is right. The
report body is filed intact, so the note keeps the producer's guess in its
proposal block, and a reader comparing the two sees them disagree. Filing does
not rewrite a report's prose, which would be a larger authority than filing
should hold. The clean resolution is upstream: a producer should not write
`minted_by` at all, because it is not a field it can know. Until §7.1 or the
specialist instructions say so, the disagreement stands.

**"for that source *and granularity*" (§7) has no second half.** v0.4 removed the
phrase and made it an open question rather than resolving it: a `source_id` is
`venue-symbol-granularity`, so each registry row already *is* a
(source, granularity) pair and the `usable_from` lookup is per source. Read as a
second requirement — that a note's `timeframe` match its source's `granularity`
— it is a rule written down nowhere else, so it is not implemented.

**`status: superseded` has no outcome that permits it.** §5's table gives a
status for every outcome and none of them is `superseded`, which the same
section says is "set later, by whatever supersedes the note". Filing reads a
report a producer wrote, so refusing it there is right. Re-running the gate over
an already-superseded note on disk refuses it too, which is the gate being used
outside what it is for, and is worth knowing before someone runs it over the
vault.

**Nothing says what filing does with a proposed entry for a ref that already
exists but describes something else.** `conventions.md` says a slug collision is
"a feature, not an error" and offers two responses: reuse the existing entry, or
surface the collision to the operator. Filing reuses. Telling the two cases
apart means reading two descriptions and deciding whether they are the same
choice, which is `[J]`.

**An unresolvable `brief_ref` silently skips the `hypothesis_ref` match.** There
is nothing to match against, and a second failure would name one cause twice.
The standard does not say which it wants.

**"No existing note carries this `artifact_id`" — which notes?** §7 says "note".
This scans every `*.md` in the vault for an `artifact_id` key, not just
`afrd/research/`, on the grounds that a broader scan can only refuse more.

## Tests

```
python -m pytest tests -q
```

Requires `pytest`, and `afrd-ids` importable — `filing.py` inserts
`C:\dev\afrd-ids` on `sys.path` if the import fails, overridable with
`AFRD_IDS_ROOT`. Neither repo has packaging, and the README said this would be a
path insert or an editable install; it is the path insert.

No other dependency; standard library only, which is why the frontmatter parser
is a documented subset rather than PyYAML — `afrd-ids` is standard-library-only
for the same reason and PyYAML is not installed on this machine.

The filing tests mint for real, against their own fixture vault, because the
ordering guard and "two filings, two ids" are the parts a stub would fake.

Constructed malformed reports run against a **fixture** vault built per test, so
"this `brief_ref` does not resolve" stays true when someone writes a new brief.
The five sample notes run against the **real** vault, because what they are is a
statement about the vault as it stands.

`tests/test_read_only.py` asserts the writes-nothing property of the CHECKING
half against this working tree — an AST scan for write-mode opens and filesystem
mutations, plus a byte-comparison of the fixture vault before and after a run.
`filing.py` is excluded from that scan **by name**, so a new module joins the
guarded set by default and leaving one out has to be deliberate.
`tests/test_filing.py` covers the writer instead: both destinations, the refusal
of a third, and a byte-comparison of the whole vault after every refusal.

## Notes on the parser

`afrd_filing/frontmatter.py` reads a deliberate subset of YAML and **raises on
everything outside it**, naming the line. That is the whole design: a subset
parser that returns a plausible string for a construct it does not understand
hands the gate a field it never checked, and the report passes a check that did
not happen.

Everything the vault actually contains is in the subset, including the two
constructs that are easy to miss — `sources_referenced: []`, and the `- >-`
sequence-of-block-scalars every `completion_criteria` entry uses.
