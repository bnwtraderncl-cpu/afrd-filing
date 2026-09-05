"""A vault built for the test, and the real one.

Constructed malformed variants run against a FIXTURE vault, so a test asserting
"`brief_ref` does not resolve" stays true when someone writes a new brief. The
five sample notes run against the REAL vault, because what they are is a
statement about the vault as it stands, and running them anywhere else would
say nothing.
"""

from __future__ import annotations

import os
import sys
import textwrap
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

REAL_VAULT = Path(os.environ.get("AFRD_VAULT_ROOT", r"C:\dev\vault"))


@pytest.fixture(scope="session")
def real_vault() -> Path:
    if not (REAL_VAULT / "afrd" / "research").is_dir():
        pytest.skip("the real vault is not at %s" % REAL_VAULT)
    return REAL_VAULT


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    """A minimal vault: one brief, two hypotheses, two data sources, one note."""
    root = tmp_path / "vault"
    (root / "afrd" / "briefs").mkdir(parents=True)
    (root / "afrd" / "research").mkdir(parents=True)
    (root / "afrd" / "system").mkdir(parents=True)

    (root / "afrd" / "briefs" / "2026-09-04-fixture-brief.md").write_text(
        textwrap.dedent(
            """\
            ---
            brief_ref: BRIEF-20260904T223000Z
            hypothesis_ref: HYP-overnight-high-fade
            author: operator
            created: 2026-09-04
            brief_status: open
            question: >-
              Fixture.
            ---

            # Fixture brief
            """
        ),
        encoding="utf-8",
    )

    (root / "afrd" / "system" / "hypotheses.md").write_text(
        textwrap.dedent(
            """\
            ---
            type: system
            status: draft
            ---

            # Fixture hypothesis registry

            ```yaml
            - ref: HYP-overnight-high-fade
              description: >-
                Fixture.
              minted: 2026-02-11
              status: active
            ```

            ```yaml
            - ref: HYP-london-open-push-fade
              description: >-
                Fixture.
              minted: 2026-09-05
              status: active
            ```
            """
        ),
        encoding="utf-8",
    )

    (root / "afrd" / "system" / "data_sources.md").write_text(
        textwrap.dedent(
            """\
            ---
            type: system
            status: draft
            ---

            # Fixture data source registry

            ```yaml
            - source_id: vantage-xauusd-h1
              granularity: H1
              earliest: 2007-06-22T00:00:00Z
              usable_from: 2018-03-19T00:00:00Z
              timezone: UTC
            ```

            ```yaml
            - source_id: vantage-xauusd-d1
              granularity: D1
              earliest: 2007-06-21T21:00:00Z
              usable_from: 2007-06-21T21:00:00Z    # same as earliest
              timezone: UTC
            ```
            """
        ),
        encoding="utf-8",
    )

    (root / "afrd" / "research" / "2026-09-05-fixture-filed-note.md").write_text(
        GOOD_REPORT.replace(
            "MARKET_STRUCTURE-20260905T090000Z",
            "MARKET_STRUCTURE-20260905T080000Z",
        ),
        encoding="utf-8",
    )
    return root


# A report that passes every `[C]` check against the fixture vault. Variants in
# the tests are made by editing exactly one thing in it, so a failure is
# attributable to that edit and to nothing else.
GOOD_REPORT = """\
---
artifact_id: MARKET_STRUCTURE-20260905T090000Z
hypothesis_ref: HYP-overnight-high-fade
brief_ref: BRIEF-20260904T223000Z
outcome: pass
finding: negative
status: stored
producer: market_structure
stage: research
instrument:
  - XAUUSD
timeframe: H1
scope_window: 2018-03-19/2026-09-03
data_sources:
  - vantage-xauusd-h1
sources_referenced: []
attempt: 1
tags:
  - session-boundary
---

# Fixture report

## Result

A clean negative, which is a PASS.
"""


def edit(report: str, old: str, new: str) -> str:
    """Replace exactly one fragment, and fail loudly if it was not there."""
    assert old in report, "fixture drifted: %r not in the report" % old
    return report.replace(old, new, 1)


def rules_hit(failures):
    """The rule labels of a refusal, for asserting what fired without the prose."""
    return sorted({f.rule for f in failures})


def fields_hit(failures):
    return sorted({f.where for f in failures})
