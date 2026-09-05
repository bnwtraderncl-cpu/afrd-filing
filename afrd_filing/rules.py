"""The §5 matrix and the closed enums, transcribed rather than paraphrased.

Both tables exist twice in the vault -- `pass_fail_hold_standard.md` §5 and
`frontmatter_schema.md` rule 6 carry the same matrix, and the schema's field
tables carry the enums. They agree today. This module transcribes the STANDARD's
copy, because §7 is what the gate implements, and names the schema as the place
the enum values are defined.

`REQUIRED` / `OPTIONAL` / `FORBIDDEN` are the three states the matrix has. A dash
in the published table means FORBIDDEN, not "unspecified": the reasoning under
the table is that a `scope` hold reached no conclusion, so `finding: inconclusive`
on one "asserts a result that does not exist". A field the matrix does not list
at all -- `producer`, `tags`, `conventions_applied` -- is not governed by it and
is not touched here.
"""

from __future__ import annotations

REQUIRED = "required"
OPTIONAL = "optional"
FORBIDDEN = "forbidden"

# The columns of the §5 table. A hold splits by `hold_type`, so the key is the
# pair, which is why the outcome alone is not enough to look a report up.
MATRIX_FIELDS = (
    "finding",
    "review_flag",
    "finding_note",
    "hold_type",
    "hold_reason",
    "fail_depth",
    "fail_reason",
    "attempt",
)

MATRIX = {
    "pass": {
        "finding": REQUIRED,
        "review_flag": OPTIONAL,
        "finding_note": OPTIONAL,
        "hold_type": FORBIDDEN,
        "hold_reason": FORBIDDEN,
        "fail_depth": FORBIDDEN,
        "fail_reason": FORBIDDEN,
        "attempt": REQUIRED,
    },
    ("hold", "authority"): {
        "finding": REQUIRED,
        "review_flag": OPTIONAL,
        "finding_note": OPTIONAL,
        "hold_type": REQUIRED,
        "hold_reason": REQUIRED,
        "fail_depth": FORBIDDEN,
        "fail_reason": FORBIDDEN,
        "attempt": REQUIRED,
    },
    ("hold", "scope"): {
        "finding": FORBIDDEN,
        "review_flag": FORBIDDEN,
        "finding_note": FORBIDDEN,
        "hold_type": REQUIRED,
        "hold_reason": REQUIRED,
        "fail_depth": FORBIDDEN,
        "fail_reason": FORBIDDEN,
        "attempt": REQUIRED,
    },
    ("hold", "brief"): {
        "finding": FORBIDDEN,
        "review_flag": FORBIDDEN,
        "finding_note": FORBIDDEN,
        "hold_type": REQUIRED,
        "hold_reason": REQUIRED,
        "fail_depth": FORBIDDEN,
        "fail_reason": FORBIDDEN,
        "attempt": REQUIRED,
    },
    "fail": {
        "finding": FORBIDDEN,
        "review_flag": FORBIDDEN,
        "finding_note": FORBIDDEN,
        "hold_type": FORBIDDEN,
        "hold_reason": FORBIDDEN,
        "fail_depth": REQUIRED,
        "fail_reason": REQUIRED,
        "attempt": REQUIRED,
    },
}


def matrix_column(outcome, hold_type):
    """The §5 column for a report, and the human name of that column."""
    if outcome == "hold":
        key = ("hold", hold_type)
        return MATRIX.get(key), "outcome `hold` with `hold_type: %s`" % hold_type
    return MATRIX.get(outcome), "outcome `%s`" % outcome


# The closed enums, from `frontmatter_schema.md`'s research-note field tables.
# Schema rule 1: a value outside the set is invalid, not merely unusual, and an
# agent may not coin one. `status` is the research-note enum -- a brief's
# `brief_status` is a different field on a different class (schema, "Artifact
# classes are distinct field sets").
ENUMS = {
    "outcome": ("pass", "hold", "fail"),
    "finding": ("positive", "negative", "inconclusive"),
    "review_flag": ("revisit", "anomaly", "data_gap", "contradicts"),
    "status": ("stored", "awaiting_operator", "superseded"),
    "hold_type": ("authority", "scope", "brief"),
    "fail_depth": ("structural", "substantive"),
    "producer": (
        "macro",
        "market_structure",
        "pattern_discovery",
        "statistician",
        "strategy_architect",
        "alpha_forge",
        "research_coordinator",
        "synthesis",
    ),
    "stage": ("research", "validation", "risk", "execution", "coaching"),
}

# §4: "The bound is 1. One re-delegation, then stop."
RETRY_BOUND = 2
