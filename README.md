# afrd-filing

The checkable half of the AFRD filing gate.

```python
from afrd_filing import validate

ok, failures = validate(report_text)      # or validate(Path("note.md"))
for f in failures:
    print(f)
```

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

**This writes nothing.** Not to the vault, not anywhere. See *The half that is
missing*.

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

**The writing half will need `afrd_ids` importable from here.** Neither repo has
packaging, so that will be a path insert or an editable install. Deferred, not
solved.

**Not in the vault.** The vault is notes. `afrd-ids` already treats it as
read-only data, and so does this.

## What it checks

Nine checks, from §7's table and §7's opening line ("Everything marked `[C]`,
plus:").

| Check | Rule |
|---|---|
| Field presence against the §5 matrix, exactly | §5 |
| Every closed enum value known | §7, schema rule 1 |
| `brief_ref` resolves to a brief in `briefs/` | §7 |
| `hypothesis_ref` resolves in `hypotheses.md`, and matches the brief's | §7 |
| Every `data_sources` entry resolves in `data_sources.md` | §7 |
| Scope window starts no earlier than `usable_from` for that source | §7 |
| No existing note carries this `artifact_id` | §7 |
| Every applied convention accounted for | §6 |
| `untested_dependence` present when `conventions_applied` is non-empty | §6 |
| The retry bound, and `status` on a fail | §4 |

The last row is not in §7's table. It is in §7 by way of its first line, and §4
marks all four of its claims `[C]`: the bound is 1, an exhausted fail is
`attempt: 2` with `status: awaiting_operator`, a fail at attempt 1 is `stored`,
and there is no `retrying`. Leaving it out would leave a stated `[C]` rule with
nobody enforcing it, which §1 is explicitly against.

A dash in the §5 matrix is read as **forbidden**, not unspecified. That is the
schema's reading, not an inference: rule 6's prose says `finding: inconclusive`
on a scope hold "asserts a result that does not exist".

## What is deliberately deferred

Two rows of §7's table are absent on purpose.

**`conventions_applied` refs resolving in `conventions.md`.** §7.1 orders the
two operations and says why: filing *writes* the producer's proposed entries and
*then* checks that every ref resolves, so "the check runs after the write, and a
proposed entry always resolves". Implemented here, before the write exists, it
would refuse every report that proposes a convention — which is precisely the
situation §7.1 is written to prevent, the one "that ends with the operator
filing by hand to get around the script". It belongs with the writing half.

**`artifact_id` ordering against the vault high-water mark.** Same section:
"filing mints through the helper, so `artifact_id` is correct by construction
rather than checked after the fact." The guard exists in `afrd-ids` and refuses
at mint. A post-hoc copy here would be a second, weaker implementation of a rule
that has a home.

Dedup is **not** the same rule and is implemented: §7's table lists it
separately, schema rule 13 makes an equal id an identity failure rather than an
ordering one, and it needs no minting to perform.

## The half that is missing

Filing is two halves. This is the first.

The second writes: it mints the `artifact_id` through `afrd-ids`, writes the
producer's proposed registry entries to `conventions.md`, then re-runs the
`CONV-` resolution check, and writes the note. It does not exist. When it does,
it goes in this repo beside this one, and `tests/test_read_only.py` moves to
cover only the checking module rather than the package.

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

**§6's accounting has no field for a variation that HELD.** The rule is that
every applied convention is "either varied with numbers reported, or listed in
`untested_dependence`", and rule 11 calls the accounting "mechanical". But
`robustness_broken` (rule 12) records only variations that *failed*. A variation
that was performed and held is written up in the note body, and no frontmatter
field records it. So the only mechanically visible accounting is
`untested_dependence` ∪ `robustness_broken`, and this takes that narrow reading:
a convention varied successfully and disclosed in prose alone is **refused**.
The refusal says so and names the remedy. The alternative reading — accept
anything, since prose might cover it — checks nothing at all. Resolving it
properly needs either a field for a successful variation or a sentence in §6
saying `untested_dependence` is the only accounting.

**"for that source *and granularity*" (§7) has no second half.** A `source_id`
is `venue-symbol-granularity`, so each registry row already *is* a
(source, granularity) pair and the `usable_from` lookup is per source. Read that
way, "and granularity" is redundant. Read as a second requirement — that a
note's `timeframe` match its source's `granularity` — it is a rule written down
nowhere else, so it is not implemented. If it was meant, it needs stating.

**`status` is in §4's `[C]` claims but not in the §5 matrix.** §4 fixes `status`
on a fail (`stored` at attempt 1, `awaiting_operator` at attempt 2), which is
implemented. Nothing fixes it on a pass or a hold, and the matrix does not list
the field at all — so a pass with no `status` is not refused here. The sample
holds all carry `awaiting_operator` and the passes all carry `stored`, which
looks like a rule nobody wrote down.

**§4's "the bound is 1" is only as checkable as `attempt` is honest.** `attempt`
is written by the producer. A producer on its third run that writes `attempt: 1`
is not caught by anything here, and nothing else in the vault records attempt
count independently.

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

Requires `pytest`. No other dependency; standard library only, which is why the
frontmatter parser is a documented subset rather than PyYAML — `afrd-ids` is
standard-library-only for the same reason and PyYAML is not installed on this
machine.

Constructed malformed reports run against a **fixture** vault built per test, so
"this `brief_ref` does not resolve" stays true when someone writes a new brief.
The five sample notes run against the **real** vault, because what they are is a
statement about the vault as it stands.

`tests/test_read_only.py` asserts the writes-nothing property against this
working tree — an AST scan for write-mode opens and filesystem mutations, plus a
byte-comparison of the fixture vault before and after a run.

## Notes on the parser

`afrd_filing/frontmatter.py` reads a deliberate subset of YAML and **raises on
everything outside it**, naming the line. That is the whole design: a subset
parser that returns a plausible string for a construct it does not understand
hands the gate a field it never checked, and the report passes a check that did
not happen.

Everything the vault actually contains is in the subset, including the two
constructs that are easy to miss — `sources_referenced: []`, and the `- >-`
sequence-of-block-scalars every `completion_criteria` entry uses.
