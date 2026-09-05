"""Everything the gate has to look up outside the report itself.

Five of the nine checks resolve a ref against something already in the vault, so
this module answers: which briefs exist, which hypotheses are registered, which
data sources are registered and from when, and which `artifact_id`s are taken.

READ ONLY. Nothing here opens a file for writing, and the filing script's
writing half is a separate concern in a separate module that does not exist yet
(see README, "The half that is missing"). Enforced by `tests/test_read_only.py`,
which scans this package's source the way `afrd-ids` scans its own.

WHY THIS DOES NOT CALL `afrd_ids.scan_vault`
--------------------------------------------
`afrd-ids` scans for the LATEST id, to guard ordering on mint. The gate needs
the opposite shape -- a full `artifact_id` -> path map, so a duplicate can name
the note that already holds the id -- and it needs whole frontmatter rather than
two keys. `scan_vault` returns neither and its extraction helpers are private.

The bounded head read below is the one idea genuinely shared, and it is about
twenty lines. `afrd-ids` remains the one place an id is DERIVED; this is a
reader, and it derives nothing.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

from .frontmatter import FrontmatterError, parse, split_frontmatter, yaml_blocks

DEFAULT_VAULT_ROOT = Path(os.environ.get("AFRD_VAULT_ROOT", r"C:\dev\vault"))

# Frontmatter is at the top of a note, so a note costs one bounded head read.
# This is the term that grows with the vault; the registries below do not.
_FRONTMATTER_BYTE_CAP = 8192

_SKIP_DIRS = {".git", ".obsidian", ".trash", "node_modules", "__pycache__", ".venv"}


class VaultError(RuntimeError):
    """The vault is not where it was expected, or a registry cannot be read."""


@dataclass(frozen=True)
class DataSource:
    source_id: str
    granularity: str
    usable_from: datetime
    usable_from_raw: str


@dataclass(frozen=True)
class Brief:
    brief_ref: str
    hypothesis_ref: str
    path: Path


@dataclass(frozen=True)
class Vault:
    """The vault as the gate needs to see it. Built once per validate() call."""

    root: Path
    briefs: dict            # brief_ref -> Brief
    hypotheses: dict        # HYP- ref -> registry entry
    data_sources: dict      # source_id -> DataSource
    artifact_ids: dict      # artifact_id -> Path of the note carrying it

    @property
    def research_dir(self) -> Path:
        return self.root / "afrd" / "research"


def load(vault_root=None, exclude=None) -> Vault:
    """Read the briefs, the registries and the filed ids.

    `exclude` is the path of the report being validated, when it is already a
    file in the vault. It is dropped from the `artifact_id` map so a filed note
    does not collide with itself -- the dedup rule is that no OTHER note holds
    the id. A report supplied as text excludes nothing, which is the normal case:
    the gate runs before filing, so the id should not be in the vault at all.
    """
    root = Path(vault_root) if vault_root is not None else DEFAULT_VAULT_ROOT
    if not root.is_dir():
        raise VaultError(
            "vault root %s does not exist. Set AFRD_VAULT_ROOT or pass "
            "vault_root=." % root
        )
    excluded = Path(exclude).resolve() if exclude is not None else None
    return Vault(
        root=root,
        briefs=_load_briefs(root),
        hypotheses=_load_registry(root / "afrd" / "system" / "hypotheses.md", "ref"),
        data_sources=_load_data_sources(root),
        artifact_ids=_load_artifact_ids(root, excluded),
    )


# ---------------------------------------------------------------- readers


def _read_head(path: Path) -> str:
    """The leading `---` block only, from a bounded head read."""
    out = []
    read = 0
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        first = fh.readline()
        read += len(first)
        if first.strip().lstrip("\ufeff") != "---":
            return ""
        while read < _FRONTMATTER_BYTE_CAP:
            line = fh.readline()
            if not line:
                break
            read += len(line)
            if line.strip() in ("---", "..."):
                return "---\n" + "".join(out) + "---\n"
            out.append(line)
    return ""


def _frontmatter_of(path: Path):
    """Parsed frontmatter, or None for a file that has none. Never raises."""
    try:
        head = _read_head(path)
    except OSError:
        return None
    if not head:
        return None
    try:
        value = parse(split_frontmatter(head))
    except FrontmatterError:
        # A note the gate cannot parse is not a reason to refuse the report
        # being validated. It does mean this file contributes no id and no
        # brief, which is reported where it matters -- an unresolvable
        # `brief_ref` names the directory it looked in.
        return None
    return value if isinstance(value, dict) else None


def _load_briefs(root: Path) -> dict:
    out = {}
    briefs_dir = root / "afrd" / "briefs"
    if not briefs_dir.is_dir():
        return out
    for path in sorted(briefs_dir.glob("*.md")):
        fm = _frontmatter_of(path)
        if not fm:
            continue
        ref = fm.get("brief_ref")
        hyp = fm.get("hypothesis_ref")
        if isinstance(ref, str) and ref:
            out[ref] = Brief(ref, hyp if isinstance(hyp, str) else None, path)
    return out


def _load_registry(path: Path, key: str) -> dict:
    """A registry is fenced ```yaml blocks in the body, each a one-entry list."""
    if not path.is_file():
        raise VaultError("registry %s is missing" % path)
    out = {}
    text = path.read_text(encoding="utf-8", errors="replace")
    for block in yaml_blocks(text):
        try:
            value = parse(block)
        except FrontmatterError:
            # A `yaml` block in a registry that is an illustration of the
            # format rather than an entry. The Fields tables in every registry
            # are markdown, not yaml, so this is rare -- but a block that does
            # not parse is not an entry, and refusing here would take a
            # registry's prose hostage.
            continue
        for entry in value if isinstance(value, list) else [value]:
            if isinstance(entry, dict) and isinstance(entry.get(key), str):
                out[entry[key]] = entry
    return out


def _load_data_sources(root: Path) -> dict:
    raw = _load_registry(root / "afrd" / "system" / "data_sources.md", "source_id")
    out = {}
    for source_id, entry in raw.items():
        stamp = entry.get("usable_from")
        moment = _parse_instant(stamp)
        if moment is None:
            # The registry declares `usable_from` on every row and the field
            # table makes it required. A row without a readable one cannot
            # answer the scope-window check, and that is reported at the check
            # rather than silently treated as "no lower bound".
            continue
        out[source_id] = DataSource(
            source_id=source_id,
            granularity=str(entry.get("granularity", "")),
            usable_from=moment,
            usable_from_raw=str(stamp),
        )
    return out


def _load_artifact_ids(root: Path, excluded) -> dict:
    out = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        here = Path(dirpath)
        for name in sorted(filenames):
            if not name.endswith(".md"):
                continue
            path = here / name
            if excluded is not None and path.resolve() == excluded:
                continue
            fm = _frontmatter_of(path)
            if not fm:
                continue
            value = fm.get("artifact_id")
            if isinstance(value, str) and value:
                out.setdefault(value, path)
    return out


# ---------------------------------------------------------------- instants


def _parse_instant(value):
    """`2018-03-19T00:00:00Z` -> aware UTC datetime, or None."""
    if not isinstance(value, str):
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def parse_scope_window(value):
    """`YYYY-MM-DD/YYYY-MM-DD` -> (start, end) as aware UTC datetimes, or None.

    The schema types `scope_window` as an ISO date range and every note in the
    vault writes it as two dates. A start date is taken as that date's 00:00Z,
    which is the earliest instant the window can be claiming.
    """
    if not isinstance(value, str) or value.count("/") != 1:
        return None
    start_text, end_text = (part.strip() for part in value.split("/"))
    try:
        start = date.fromisoformat(start_text)
        end = date.fromisoformat(end_text)
    except ValueError:
        return None
    to_utc = lambda d: datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
    return to_utc(start), to_utc(end)
