"""What a refusal says.

`pass_fail_hold_standard.md` §7.1: the script refuses on every `[C]` failure,
with no warnings and no filing-with-caveats. A refusal is therefore the only
thing a producer gets back, and it has to be enough to fix the report from.

"Invalid frontmatter" is not enough. Every failure carries four things:

    rule      which rule refused, by section, so it can be looked up
    where     the field, entry or file the problem is at
    expected  what the rule requires
    found     what the report actually carried

The report is refused as a WHOLE. `validate` collects every failure rather than
raising on the first, because a producer fixing one error per round trip across
five round trips is a worse loop than the one this replaces.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Failure:
    rule: str
    where: str
    expected: str
    found: str

    def __str__(self) -> str:
        return "[%s] %s: %s; found %s" % (
            self.rule,
            self.where,
            self.expected,
            self.found,
        )


def render(failures) -> str:
    """The whole refusal, one failure per line, in the order they were found."""
    return "\n".join(str(f) for f in failures)
