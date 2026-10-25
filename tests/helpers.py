"""Shared test setup: the helper module, the active release, and report-table parsing.

Run in FindIt's environment (read-only; nothing is written to FindIt):

    export FINDIT_ROOT="${FINDIT_ROOT:-../Find_v2}"
    uv run --no-sync --project "$FINDIT_ROOT" python -B -m pytest tests
"""

import contextlib
import functools
import io
import json
from pathlib import Path

from bootstrap import SCRIPT as SCRIPT
import findit_query as fq

RELEASE = fq.current_release()
DB = Path(RELEASE["db"])
SIDECARS = ("-wal", "-shm", "-journal")


def run(*argv: str):
    """main(argv) in-process: (exit code, stdout text)."""
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = fq.main(list(argv))
    return code, out.getvalue()


def run_json(*argv: str):
    code, text = run(*argv)
    return code, json.loads(text)


def release_files() -> dict[str, tuple[int, int]]:
    """Name -> (size, mtime_ns) for everything next to the release DB."""
    return {p.name: (p.stat().st_size, p.stat().st_mtime_ns) for p in DB.parent.iterdir()}


def sidecars() -> list[str]:
    return [p.name for p in DB.parent.iterdir()
            if p.name.startswith(DB.name) and p.name.endswith(SIDECARS)]


def report_table(text: str, heading: str) -> list[list[str]]:
    """Body rows (cells) of the table under the '## <heading>' section."""
    lines = text.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith(f"## {heading}"))
    rows = []
    for line in lines[start + 1:]:
        if line.startswith("## "):
            break
        if line.startswith("| ") and not line.startswith("| Stock |"):
            rows.append([c.strip() for c in line.strip().strip("|").split("|")])
    return rows


@functools.cache
def report_text() -> str:
    """`findit report` for MONTH, built by FindIt itself (cached; it takes seconds)."""
    from findit.cli import report
    return report.build(str(DB), MONTH)


@functools.cache
def top() -> dict:
    code, data = run_json("top", "--month", MONTH)
    assert code == 0, data
    return data


# Snapshot taken before the first query opens the database.
FILES_AT_START = release_files()
COVERAGE = fq.api("/api/coverage")
MONTH = COVERAGE["delta_months"][-1]
