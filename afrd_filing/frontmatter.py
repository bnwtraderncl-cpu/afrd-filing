"""Reading the YAML the vault actually contains, with no YAML library.

`afrd-ids` gets away with a line regex because it reads exactly two keys, both
single-token. The gate reads whole reports: block scalars (`hold_reason`),
sequences of scalars (`data_sources`), and sequences of mappings
(`untested_dependence`, `robustness_tested`). That needs a parser.

PyYAML is not installed and `afrd-ids` is standard-library-only, so this is a
deliberate SUBSET parser rather than a partial YAML implementation. The
distinction is the error behaviour: every construct outside the subset raises
`FrontmatterError` naming the line. Nothing is skipped, nothing is guessed. A
gate that silently misreads a report is worse than one that refuses it, because
a misread produces a confident pass on a field nobody checked.

WHAT IS IN THE SUBSET
---------------------
    key: value                      plain, single- or double-quoted scalars
    key: >-  /  >  /  |  /  |-      block scalars, folded and literal
    key:                            a nested mapping or sequence, indented
    - value                         a sequence of scalars
    - >-                            a sequence of block scalars
    - key: value                    a sequence of mappings
                                    inline `# comment` on a plain scalar
                                    blank lines, full-line comments

WHAT IS NOT, AND RAISES
-----------------------
    key: [a, b]  /  key: {a: b}     non-empty flow collections. `[]` and `{}`
                                    ARE read: the sample notes write
                                    `sources_referenced: []`
    - - nested                      nested sequences
    &anchor  *alias  !tag  ---      anchors, aliases, tags, multi-document

None of these appears anywhere in the vault, and each would otherwise parse as
a string that looks plausible.
"""

from __future__ import annotations

import re

_BLOCK_SCALAR = re.compile(r"^([>|])([+-]?)$")
_KEY = re.compile(r"^(?P<key>[A-Za-z_][A-Za-z0-9_]*)\s*:(?:\s+(?P<value>.*))?$")
_KEY_EMPTY = re.compile(r"^(?P<key>[A-Za-z_][A-Za-z0-9_]*)\s*:$")


class FrontmatterError(ValueError):
    """Text this parser will not read. Always names the line."""


def split_frontmatter(text: str) -> str:
    """Return the leading `---` block of a note, without the fences.

    Raises rather than returning "" for a note with no frontmatter: the caller
    is validating a report, and a report with no frontmatter is not a report
    whose fields happen to be absent -- it is not a report.
    """
    if not isinstance(text, str):
        raise FrontmatterError(
            "expected report text, got %s" % type(text).__name__
        )
    stripped = text.lstrip("﻿")
    lines = stripped.splitlines()
    if not lines or lines[0].strip() != "---":
        raise FrontmatterError(
            "no frontmatter: the report must open with a `---` line, "
            "found %r" % (lines[0][:60] if lines else "")
        )
    for i in range(1, len(lines)):
        if lines[i].strip() in ("---", "..."):
            return "\n".join(lines[1:i])
    raise FrontmatterError(
        "frontmatter is not closed: no `---` line after the opening one"
    )


def parse(text: str):
    """Parse the subset above into dicts, lists and strings."""
    rows = _rows(text)
    if not rows:
        return {}
    value, index = _parse_block(rows, 0, rows[0][0])
    if index != len(rows):
        raise FrontmatterError(
            "line %d: unexpected indentation, %r does not belong to the block "
            "above it" % (rows[index][2], rows[index][1])
        )
    return value


# --------------------------------------------------------------------------
# The parser proper. `rows` is [(indent, content, line_number)], with blank
# lines and full-line comments already dropped -- but block scalars need the
# raw text, so they are re-read from `_RAW` by line number.
# --------------------------------------------------------------------------


def _rows(text: str):
    raw = text.splitlines()
    rows = []
    for number, line in enumerate(raw, start=1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        _reject_unsupported(line, number)
        if line[: len(line) - len(line.lstrip())].count("\t"):
            raise FrontmatterError(
                "line %d: tab in indentation. YAML forbids it, and read as a "
                "space this line would silently join the wrong block: %r"
                % (number, line.strip()[:60])
            )
        indent = len(line) - len(line.lstrip(" "))
        rows.append((indent, line.strip(), number))
    return _Rows(rows, raw)


class _Rows(list):
    """The significant lines, carrying the raw file alongside for block scalars."""

    def __init__(self, rows, raw):
        super().__init__(rows)
        self.raw = raw


def _reject_unsupported(line: str, number: int) -> None:
    body = line.strip()
    if body.startswith(("&", "*", "!", "%")):
        raise FrontmatterError(
            "line %d: anchors, aliases, tags and directives are outside this "
            "parser's subset: %r" % (number, body[:60])
        )
    if body.startswith("- -"):
        raise FrontmatterError(
            "line %d: nested sequences are outside this parser's subset: %r"
            % (number, body[:60])
        )
    m = _KEY.match(body[2:].strip() if body.startswith("- ") else body)
    if m and m.group("value"):
        value = m.group("value").strip()
        if value[:1] in ("&", "*", "!"):
            raise FrontmatterError(
                "line %d: anchors, aliases and tags are outside this parser's "
                "subset -- read as a plain scalar this value would be silently "
                "wrong: %r" % (number, body[:60])
            )
        if value[:1] in ("[", "{") and value not in ("[]", "{}"):
            raise FrontmatterError(
                "line %d: non-empty flow collections (`[a, b]`, `{a: b}`) are "
                "outside this parser's subset; use a block sequence or "
                "mapping: %r" % (number, body[:60])
            )


def _parse_block(rows, start: int, indent: int):
    if rows[start][1].startswith("- ") or rows[start][1] == "-":
        return _parse_sequence(rows, start, indent)
    return _parse_mapping(rows, start, indent)


def _parse_mapping(rows, start: int, indent: int):
    out = {}
    i = start
    while i < len(rows):
        row_indent, content, number = rows[i]
        if row_indent < indent:
            break
        if row_indent > indent:
            raise FrontmatterError(
                "line %d: unexpected indentation inside a mapping: %r"
                % (number, content)
            )
        if content.startswith("- "):
            break
        m = _KEY.match(content)
        if not m:
            raise FrontmatterError(
                "line %d: expected `key: value`, found %r" % (number, content)
            )
        key = m.group("key")
        if key in out:
            raise FrontmatterError(
                "line %d: duplicate key %r. One of the two values is being "
                "silently discarded, so this is refused rather than resolved"
                % (number, key)
            )
        raw_value = (m.group("value") or "").strip()
        out[key], i = _parse_value(rows, i, indent, raw_value, number)
    return out, i


def _parse_sequence(rows, start: int, indent: int):
    out = []
    i = start
    while i < len(rows):
        row_indent, content, number = rows[i]
        if row_indent < indent or not content.startswith("-"):
            break
        if row_indent > indent:
            raise FrontmatterError(
                "line %d: unexpected indentation inside a sequence: %r"
                % (number, content)
            )
        if content == "-":
            raise FrontmatterError(
                "line %d: a bare `-` with its value on the next line is "
                "outside this parser's subset" % number
            )
        item = content[2:].strip()
        block = _BLOCK_SCALAR.match(item)
        m = _KEY.match(item)
        if block:
            # `- >-` with the text below it. Every `completion_criteria` entry
            # in the two briefs is written this way.
            value, i = _block_scalar(rows, i, row_indent, block.group(1), block.group(2))
            out.append(value)
        elif m:
            # `- key: value` opens a mapping whose keys sit at the column the
            # item's text starts in, i.e. two past the dash.
            value, i = _parse_mapping_from_item(rows, i, indent + 2, item, number)
            out.append(value)
        else:
            out.append(_scalar(item, number))
            i += 1
    return out, i


def _parse_mapping_from_item(rows, start: int, indent: int, item: str, number: int):
    """A sequence item that is a mapping: its first key shares the `- ` line."""
    m = _KEY.match(item)
    key = m.group("key")
    raw_value = (m.group("value") or "").strip()
    out = {}
    out[key], i = _parse_value(rows, start, indent, raw_value, number, first_of_item=True)
    if i < len(rows) and rows[i][0] == indent and not rows[i][1].startswith("- "):
        rest, i = _parse_mapping(rows, i, indent)
        for k, v in rest.items():
            if k in out:
                raise FrontmatterError(
                    "line %d: duplicate key %r in one sequence item" % (number, k)
                )
            out[k] = v
    return out, i


def _parse_value(rows, i: int, indent: int, raw_value: str, number: int,
                 first_of_item: bool = False):
    """Resolve one key's value, consuming any indented block that follows it."""
    block = _BLOCK_SCALAR.match(raw_value)
    if block:
        return _block_scalar(rows, i, indent, block.group(1), block.group(2))
    if raw_value:
        return _scalar(raw_value, number), i + 1

    # `key:` with nothing after it -- a nested block, or an explicit empty.
    j = i + 1
    if j >= len(rows):
        return None, j
    child_indent = rows[j][0]
    if child_indent > indent:
        return _parse_block(rows, j, child_indent)
    if child_indent == indent and rows[j][1].startswith("- ") and not first_of_item:
        # A sequence written at the parent key's own column, which is legal
        # YAML and is how `instrument:` is written in the schema's example.
        return _parse_sequence(rows, j, child_indent)
    return None, j


def _block_scalar(rows, i: int, indent: int, style: str, chomp: str):
    """Fold or keep an indented block. Content is literal: no comment stripping."""
    raw = rows.raw
    start_line = rows[i][2]           # 1-based line of the `key: >-` itself
    collected = []
    line_index = start_line           # 0-based index of the NEXT line
    body_indent = None
    while line_index < len(raw):
        line = raw[line_index]
        if line.strip():
            here = len(line) - len(line.lstrip(" "))
            if here <= indent:
                break
            if body_indent is None:
                body_indent = here
            collected.append(line[body_indent:] if len(line) > body_indent else "")
        else:
            collected.append("")
        line_index += 1
    while collected and not collected[-1].strip():
        collected.pop()

    text = _fold(collected) if style == ">" else "\n".join(collected)
    if chomp != "+":
        text = text.rstrip("\n")
    if chomp == "":                       # clip: exactly one trailing newline
        text = text + "\n" if text else text

    # Advance past every row the block consumed.
    j = i + 1
    while j < len(rows) and rows[j][2] <= line_index:
        j += 1
    return text, j


def _fold(lines):
    """YAML folded style: the newline between two non-empty lines becomes a space.

    A blank line survives as a newline, which is how a `>-` block keeps its
    paragraphs -- `hold_reason` on the sample scope hold relies on neither, but
    a producer's report may.
    """
    out = []
    pending_break = False
    for line in lines:
        if not line.strip():
            pending_break = True
            continue
        if not out:
            out.append(line.strip())
        elif pending_break:
            out.append("\n" + line.strip())
        else:
            out.append(" " + line.strip())
        pending_break = False
    return "".join(out)


def _scalar(text: str, number: int):
    """A plain or quoted scalar. Quoting is what protects a literal `#`."""
    text = text.strip()
    if text == "[]":
        return []
    if text == "{}":
        return {}
    if len(text) >= 2 and text[0] == text[-1] and text[0] in ("'", '"'):
        return text[1:-1]
    # A plain scalar ends at ` #`, as in YAML. `usable_from` in the data source
    # registry carries exactly such a comment.
    cut = text.find(" #")
    if cut != -1:
        text = text[:cut].rstrip()
    if text in ("~", "null", "Null", "NULL"):
        return None
    if text in ("true", "True", "false", "False"):
        return text.lower() == "true"
    if re.fullmatch(r"-?\d+", text):
        return int(text)
    return text


def yaml_blocks(text: str):
    """Yield the body of each fenced ```yaml block. Registries live in these."""
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        if re.match(r"^\s*```\s*ya?ml\s*$", lines[i], re.IGNORECASE):
            i += 1
            block = []
            while i < len(lines) and not lines[i].lstrip().startswith("```"):
                block.append(lines[i])
                i += 1
            yield "\n".join(block)
        i += 1
