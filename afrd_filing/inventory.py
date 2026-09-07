"""What the vault contains, read from the vault. Printed, never filed.

WHY THIS PRINTS AND DOES NOT WRITE
----------------------------------
This replaces three sections of `afrd_decision_register.md` that asserted what
existed on disk -- an artifacts table with versions and commit pins, a
"standards written / not written" column, and a set of status rows in the open
questions list. All three had gone stale, and stale state in a confident table
is worse than no table: decision #39, *"a pin that can go stale reads as
verified when it is not."*

A generated file on disk is the same defect with a shorter half-life. So this
writes nothing. Run it, read the output, throw it away. The answer is only ever
as old as the run.

It lives in `afrd_filing` rather than beside it so that
`tests/test_read_only.py` scans it: that suite globs this package and excludes
one module by name, so the no-write property here is asserted by a test rather
than by this docstring. The lookups in `vault.py` and the subset YAML parser in
`frontmatter.py` are reused rather than reimplemented -- a second reader of the
same registries would drift from the gate, and then the two would disagree
about what resolves.

TWO HALVES
----------
**Inventory** answers "what exists": folder shape, the system files with their
`type`/`status`/`version`, registry entry counts, the agents and their `tools:`
lines, the ids carried by `briefs/`, `research/` and `sources/`, and the last
ten commits.

**Reference reconciliation** is the half worth having. Every `CONV-`, `HYP-`,
`BRIEF-`, `EVT-` and producer-prefixed ref in the vault is resolved against the
thing that should carry it. A ref that resolves nowhere is a dangling claim
that some registry entry or filed note exists, and nothing else in the vault
looks for one outside a report being filed -- the gate checks the report in
front of it, so a ref that entered by hand, in a standard or a registry, is
checked by nothing at all. The vault's known instance is `minted_by` on
`CONV-nonpush-sign-preopen`, which names a report that was never filed.

Three things are NOT dangling and are not reported as such: a ref carrying
`EXAMPLE` or a `<` template, a ref `id_adjustments.md` records as superseded
(reported apart, under RETIRED), and anything under `afrd/journal/`, which that
folder's `CLAUDE.md` puts outside resolution entirely. The exclusions are
printed on every run, because an exclusion nobody can see is indistinguishable
from a check that was never written.

RUN IT
------
    python -m afrd_filing.inventory                 # AFRD_VAULT_ROOT or default
    python -m afrd_filing.inventory C:\\dev\\vault
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

from .frontmatter import FrontmatterError, parse, split_frontmatter, yaml_blocks
from .vault import DEFAULT_VAULT_ROOT, VaultError, _frontmatter_of, _load_registry

_SKIP_DIRS = {".git", ".obsidian", ".trash", "node_modules", "__pycache__", ".venv"}

# The four prefixed vocabularies, each with the thing that should carry the ref.
_PREFIXES = ("CONV", "HYP", "BRIEF", "EVT")

_PREFIXED_REF = re.compile(r"\b(CONV|HYP|BRIEF|EVT)-[A-Za-z0-9][A-Za-z0-9_.-]*")

# `MARKET_STRUCTURE-20260905T094157Z` and the minute-precision ids that predate
# schema rule 13's second precision. Producer segment is uppercase with
# underscores, per the schema's producer prefixes.
_ARTIFACT_ID = re.compile(r"\b([A-Z][A-Z_]*)-(\d{8}T\d{4}(?:\d{2})?Z)\b")

# A ref is an illustration, not a claim, when it carries the EXAMPLE marker --
# `afrd/CLAUDE.md`, "Refs must resolve, or carry EXAMPLE". Format templates are
# the other non-claim: `PRODUCER-YYYYMMDDTHHMMSSZ` and `CONV-<slug>` describe a
# shape rather than naming an entry.
_NOT_A_CLAIM = ("EXAMPLE", "YYYY", "<")

# `afrd/journal/CLAUDE.md`: "Nothing resolves against this folder" and "a
# script that needs a value must not read the journal for it." A journal entry
# narrates governance -- what was decided, and what was later found to be
# wrong -- so it quotes ids that were wrong when written and refs that never
# existed. Section 3ag of `obsidian_migration_record.md` quotes two `CONV-`
# refs precisely BECAUSE they resolve nowhere. Reconciling against that folder
# reports the record of a defect as the defect.
_RECONCILE_SKIP = ("afrd/journal",)


def main(argv=None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] in ("-h", "--help"):
        print(__doc__.strip())
        return 0
    root = Path(args[0]) if args else Path(
        os.environ.get("AFRD_VAULT_ROOT", str(DEFAULT_VAULT_ROOT))
    )
    if not root.is_dir():
        print("ERROR: vault root %s does not exist" % root)
        return 2

    notes = _all_notes(root)
    _heading("VAULT")
    print("  root         %s" % root)
    print("  markdown     %d files" % len(notes))

    _folders(root)
    _system_files(root)
    _registries(root)
    _agents(root)
    _folder_ids(root, "briefs", ("brief_ref", "hypothesis_ref", "brief_status"))
    _folder_ids(root, "research", ("artifact_id", "hypothesis_ref", "outcome"))
    _folder_ids(root, "sources", ("event_ref", "type", "published"))
    _commits(root)

    unresolved = _reconcile(root, notes)
    return 1 if unresolved else 0


# ------------------------------------------------------------- inventory


def _folders(root: Path) -> None:
    _heading("FOLDER SHAPE")
    for path in sorted(root.iterdir()):
        if not path.is_dir() or path.name in _SKIP_DIRS:
            continue
        children = sorted(
            p.name for p in path.iterdir() if p.is_dir() and p.name not in _SKIP_DIRS
        )
        count = len([p for p in path.rglob("*.md")])
        print("  %-14s %3d .md%s" % (
            path.name + "/", count,
            "   " + " ".join(c + "/" for c in children) if children else "",
        ))


def _system_files(root: Path) -> None:
    _heading("afrd/system/")
    directory = root / "afrd" / "system"
    if not directory.is_dir():
        print("  MISSING: %s" % directory)
        return
    print("  %-28s %-10s %-10s %s" % ("file", "type", "status", "version"))
    for path in sorted(directory.glob("*.md")):
        fm = _frontmatter_of(path) or {}
        print("  %-28s %-10s %-10s %s" % (
            path.name,
            fm.get("type", "-"),
            fm.get("status", "-"),
            fm.get("version", "-"),
        ))
    others = sorted(p.name for p in directory.iterdir() if p.suffix != ".md")
    if others:
        print("  non-markdown: %s" % ", ".join(others))


def _registries(root: Path) -> None:
    _heading("REGISTRY ENTRIES")
    system = root / "afrd" / "system"
    for name, key in (
        ("conventions.md", "ref"),
        ("hypotheses.md", "ref"),
        ("data_sources.md", "source_id"),
        ("id_adjustments.md", "id"),
        ("events.md", "ref"),
    ):
        path = system / name
        try:
            entries = _load_registry(path, key)
        except VaultError as exc:
            print("  %-22s ERROR %s" % (name, exc))
            continue
        print("  %-22s %2d entries" % (name, len(entries)))
        for ref, entry in sorted(entries.items()):
            status = entry.get("status", "-")
            print("      %-40s %s" % (ref, status))


def _agents(root: Path) -> None:
    _heading(".claude/agents/")
    directory = root / ".claude" / "agents"
    if not directory.is_dir():
        print("  no .claude/agents/ directory")
        return
    paths = sorted(directory.rglob("*.md"))
    if not paths:
        print("  directory exists, no agent definitions")
    for path in paths:
        fm = _frontmatter_of(path) or {}
        tools = fm.get("tools", "- (no tools: line - inherits everything)")
        if isinstance(tools, list):
            tools = ", ".join(str(t) for t in tools)
        print("  %-24s tools: %s" % (path.name, tools))
    settings = root / ".claude" / "settings.json"
    print("  .claude/settings.json  %s"
          % ("present, %d bytes" % settings.stat().st_size
             if settings.is_file() else "ABSENT"))


def _folder_ids(root: Path, folder: str, fields) -> None:
    _heading("afrd/%s/" % folder)
    directory = root / "afrd" / folder
    if not directory.is_dir():
        print("  MISSING: %s" % directory)
        return
    paths = [p for p in sorted(directory.glob("*.md")) if p.name != "CLAUDE.md"]
    print("  %d notes" % len(paths))
    for path in paths:
        fm = _frontmatter_of(path) or {}
        values = "  ".join(
            "%s=%s" % (f, _flat(fm.get(f))) for f in fields if fm.get(f) is not None
        )
        print("      %-58s %s" % (path.name, values or "(no frontmatter read)"))


def _commits(root: Path) -> None:
    _heading("LAST TEN COMMITS")
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "log", "-10", "--format=%h %ad %s",
             "--date=short"],
            capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        print("  git unavailable: %s" % exc)
        return
    if out.returncode != 0:
        print("  git log failed: %s" % out.stderr.strip())
        return
    for line in out.stdout.splitlines():
        print("  " + line)


# ------------------------------------------------- reference reconciliation


def _reconcile(root: Path, notes) -> int:
    _heading("REFERENCE RECONCILIATION")

    system = root / "afrd" / "system"
    conventions = _try_registry(system / "conventions.md", "ref")
    hypotheses = _try_registry(system / "hypotheses.md", "ref")
    adjustments = _try_registry(system / "id_adjustments.md", "id")
    events = _try_registry(system / "events.md", "ref")

    retired = _retired_ids(adjustments)
    notes = _reconciled_notes(root, notes)

    brief_refs, artifact_ids = _ids_carried_by_notes(root)

    # `id_adjustments.md` carries the current value of an adjusted id. A ref
    # pointing at one is resolvable even though no note in that folder is
    # named by it -- the registry is where the id now lives.
    known = {
        "CONV": set(conventions),
        "HYP": set(hypotheses),
        "BRIEF": brief_refs | {k for k in adjustments if k.startswith("BRIEF-")},
        "EVT": set(events),
        "_ARTIFACT": artifact_ids | set(adjustments),
    }

    print("  resolving against")
    print("      CONV-      conventions.md            %3d entries" % len(known["CONV"]))
    print("      HYP-       hypotheses.md             %3d entries" % len(known["HYP"]))
    print("      BRIEF-     briefs/ + id_adjustments  %3d ids" % len(known["BRIEF"]))
    print("      EVT-       events.md                 %3d entries" % len(known["EVT"]))
    print("      PRODUCER-  research/ + id_adjustments%3d ids" % len(known["_ARTIFACT"]))
    print("  excluded: refs carrying EXAMPLE, templates containing YYYY or <,")
    print("            and afrd/journal/ entirely - that folder's CLAUDE.md,")
    print("            \"nothing resolves against this folder\"")
    print("  resolved-as-retired: every superseded_id in id_adjustments.md, at")
    print("            any depth, cited anywhere - listed below, not hidden")

    found = {}   # ref -> [(relative path, line number), ...]
    for path in notes:
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for number, line in enumerate(lines, start=1):
            for ref in _refs_in(line):
                found.setdefault(ref, []).append(
                    (path.relative_to(root).as_posix(), number)
                )

    # Retired is checked BEFORE resolution, and reported apart from it. A value
    # `id_adjustments.md` records as superseded is resolved -- it is accounted
    # for, in the file that exists to account for it -- but it is resolved
    # differently from a ref naming a live entry, and folding the two into one
    # count would say the schema's history tables cite something current. They
    # do not, and that is what makes them correct.
    retired_cited, unresolved = {}, {}
    for ref, sites in found.items():
        if ref in retired:
            retired_cited[ref] = sites
        elif not _resolves(ref, known):
            unresolved[ref] = sites

    print("\n  %d distinct refs cited" % len(found))

    if retired_cited:
        citations = sum(len(sites) for sites in retired_cited.values())
        print("\n  RETIRED - %d refs, %d citations. Superseded in "
              "id_adjustments.md," % (len(retired_cited), citations))
        print("  which is where a replaced id belongs. Cited as history, not as claim.")
        for ref in sorted(retired_cited):
            sites = retired_cited[ref]
            print("      %-40s (%d citation%s)"
                  % (ref, len(sites), "" if len(sites) == 1 else "s"))

    if unresolved:
        print("\n  UNRESOLVED - %d refs" % len(unresolved))
        for ref in sorted(unresolved):
            sites = unresolved[ref]
            print("      %s   (%d citation%s)"
                  % (ref, len(sites), "" if len(sites) == 1 else "s"))
            for relative, number in sites:
                print("          %s:%d" % (relative, number))
    else:
        print("\n  every cited ref resolves")

    dangling = _minted_by(root, conventions, artifact_ids)
    return len(unresolved) + dangling


def _minted_by(root: Path, conventions, artifact_ids) -> int:
    """`minted_by` must name a report in `afrd/research/`, per conventions.md.

    A separate check from ref resolution because the target is different: a
    `CONV-` ref resolves against the REGISTRY, while `minted_by` resolves the
    other way -- the registry entry pointing back at the report that made the
    choice. `conventions.md` calls the failure a dangling reference and makes
    resolving it an operator action.
    """
    print("\n  minted_by - must name a report filed in afrd/research/")
    filed, _ = _research_ids(root)
    dangling = 0
    if not conventions:
        print("      no conventions to check")
        return 0
    for ref in sorted(conventions):
        value = conventions[ref].get("minted_by")
        if not isinstance(value, str) or not value:
            print("      %-34s no minted_by" % ref)
            continue
        if value in filed:
            print("      %-34s %s  OK %s" % (ref, value, filed[value]))
        else:
            dangling += 1
            print("      %-34s %s  DANGLING" % (ref, value))
            print("          no note in afrd/research/ carries this artifact_id")
    return dangling


# `id_adjustments.md` exists to record ids that were REPLACED. Every
# `superseded_id` in it is retired by design and resolves to nothing -- that is
# what the registry means. Counting them as dangling would make the one file
# that documents the problem the largest source of false positives.
#
# The set is built from that registry's PARSED KEYS, and a ref in it is
# resolved-as-retired WHEREVER it is cited. The earlier line-local test -- skip
# the ref only on a line that is itself a `superseded_id:` key -- made the
# schema the second-largest source of false positives: the two "Was -> Now"
# adjustment tables under rule 13 are a correctly sequenced history, and the
# second table's "Now" column matches this registry exactly, yet every cell of
# both read as a stale current claim.
#
# Structural rather than textual is the point. `id_adjustments.md` already
# declares itself "the machine-readable record and ... the authoritative one",
# so a value's retirement is a fact about the registry and not about the line
# a citation happens to sit on. Moving a citation from a table into prose, or
# quoting one in a standard, does not change the answer.
def _retired_ids(adjustments) -> set:
    """Every value `id_adjustments.md` records as superseded, at any depth.

    Read from the parsed registry rather than matched against text, which is
    the whole point: the file declares itself the authoritative machine-
    readable record of retired ids, so membership here is a property of the
    registry and not of the line a citation sits on.

    `prior_adjustments` is walked because a chain retires every link in it. The
    schema's first "Was -> Now" table cites the middle of two such chains --
    values that were current for one day between a -12h correction and a
    precision backfill -- and those are exactly as retired as the most recent
    supersession. A `superseded_id: null` records that there was no earlier
    value at all and contributes nothing.
    """
    out = set()
    for entry in adjustments.values():
        for value in _superseded_in(entry):
            out.add(value)
    return out


def _superseded_in(entry):
    value = entry.get("superseded_id")
    if isinstance(value, str) and value:
        yield value
    prior = entry.get("prior_adjustments")
    for item in prior if isinstance(prior, list) else []:
        if isinstance(item, dict):
            value = item.get("superseded_id")
            if isinstance(value, str) and value:
                yield value


def _reconciled_notes(root: Path, notes):
    """The notes reconciliation reads: everything but `_RECONCILE_SKIP`.

    The inventory half still counts the whole vault -- "markdown N files" is a
    statement about what exists and would be wrong if it quietly meant "what
    the linter reads." Only resolution is scoped.
    """
    out = []
    for path in notes:
        relative = path.relative_to(root).as_posix()
        if any(relative == d or relative.startswith(d + "/")
               for d in _RECONCILE_SKIP):
            continue
        out.append(path)
    return out


def _refs_in(line: str):
    for match in _PREFIXED_REF.finditer(line):
        ref = match.group(0).rstrip(".,;:)`\"'")
        if not _is_a_claim(ref):
            continue
        yield ref
    for match in _ARTIFACT_ID.finditer(line):
        ref = match.group(0)
        if match.group(1) in _PREFIXES or not _is_a_claim(ref):
            continue
        yield ref


def _is_a_claim(ref: str) -> bool:
    return not any(marker in ref for marker in _NOT_A_CLAIM)


def _resolves(ref: str, known) -> bool:
    prefix = ref.split("-", 1)[0]
    if prefix in _PREFIXES:
        return ref in known[prefix]
    return ref in known["_ARTIFACT"]


def _ids_carried_by_notes(root: Path):
    brief_refs = set()
    briefs = root / "afrd" / "briefs"
    if briefs.is_dir():
        for path in sorted(briefs.glob("*.md")):
            fm = _frontmatter_of(path) or {}
            value = fm.get("brief_ref")
            if isinstance(value, str) and value:
                brief_refs.add(value)
    filed, _ = _research_ids(root)
    return brief_refs, set(filed)


def _research_ids(root: Path):
    """`artifact_id` -> filename, for notes in `afrd/research/` only."""
    out = {}
    directory = root / "afrd" / "research"
    if not directory.is_dir():
        return out, directory
    for path in sorted(directory.glob("*.md")):
        fm = _frontmatter_of(path) or {}
        value = fm.get("artifact_id")
        if isinstance(value, str) and value:
            out[value] = path.name
    return out, directory


# ------------------------------------------------------------------ util


def _all_notes(root: Path):
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        here = Path(dirpath)
        for name in sorted(filenames):
            if name.endswith(".md"):
                out.append(here / name)
    return sorted(out)


def _try_registry(path: Path, key: str) -> dict:
    try:
        return _load_registry(path, key)
    except VaultError:
        return {}


def _flat(value) -> str:
    if isinstance(value, list):
        return ",".join(str(v) for v in value)
    text = str(value).replace("\n", " ")
    return text if len(text) <= 40 else text[:37] + "..."


def _heading(text: str) -> None:
    print("\n" + text)
    print("-" * len(text))


if __name__ == "__main__":
    raise SystemExit(main())
