# FindSkill — `/findit` for Claude Code

A Claude Code skill that writes research notes on Indian mutual fund holdings changes from the local [FindIt](../Find_v2) release: what changed versus earlier months, possible reasons from cited news, scenarios, and what to watch. Research only; no investment advice.

```bash
./install.sh          # symlink skills/findit into ~/.claude/skills/findit
./install.sh --copy   # copy instead
FINDIT_ROOT=/path/to/Find_v2 ./install.sh   # FindIt elsewhere (saved for the skill)
```

By default, installation looks for `Find_v2` beside this repo, regardless of the current directory. The saved location is used by both symlink and copy installs; `FINDIT_ROOT` overrides it.

Then restart Claude Code and type `/findit`, `/findit 2026-08`, `/findit Hyundai Motor India` or `/findit HDFC Flexi Cap`.

- `skills/findit/SKILL.md` — hard rules and workflow
- `skills/findit/scripts/findit` — wrapper that finds FindIt (`$FINDIT_ROOT`, the path install.sh saved, or the default) and runs the helper in FindIt's environment
- `skills/findit/scripts/findit_query.py` — read-only helper around FindIt's dashboard API and report functions
- `skills/findit/scripts/findit_notes.py` — scoped report drafts, field references and verification
- `skills/findit/references/` — helper commands and report template

Reports are written to `reports/` here (symlink install), `~/FindIt-reports` (copy install), or `$FINDIT_REPORTS_DIR`. The skill never writes to the FindIt repo or database.

## Development

From the repo root, use the adjacent FindIt checkout or set `FINDIT_ROOT` to its location:

```bash
export FINDIT_ROOT="${FINDIT_ROOT:-../Find_v2}"
uv run --no-sync --project "$FINDIT_ROOT" python -B -m pytest tests
```

Installer and notes fixture tests also run independently of FindIt's environment and release:

```bash
python3 -B -m unittest discover -s tests -p test_install.py
python3 -B -m unittest discover -s tests -p test_notes.py
```

Run static checks with `ruff check skills/findit/scripts tests`.

The live tests run `findit_query.py` against the active FindIt release, which they read from `Find_v2/real_data/readiness/releases/current.json`. They contain no release ID. They are read-only: they write nothing to Find_v2, create no `.pyc` files there and add no pytest cache. The tests check that:

- `report` is the same text as `findit.cli.report.build` for the latest month.
- `top` buying/selling rows give the report's top-15 table cells exactly.
- For each top-15 stock, the AMCs in `evidence` counts add up to the stock's AMCs buying, selling, opening and exiting.
- Legacy table verification requires complete market tables and rejects changed, omitted, duplicate or malformed rows.
- Full verification accepts market, stock and fund reports, including unranked stocks and withheld fund comparisons; rejects changed/missing data blocks, altered facts, incomplete sections, release mismatches, unreferenced numerical prose and incomplete citation dates.
- Trends match monthly consensus, history preserves cohort status, fund summaries and digest match FindIt, and calendar dates follow FindIt publication rules.
- Installation in temporary directories supports symlink and copy modes, saved paths with spaces, repeated linking, failed preflight and protection of existing installs.
- `amcs` lists the AMCs loaded last month but not this month (checked against the database for the last three months).
- An unknown or malformed month, and an unknown stock name, give `{"error": ...}` with exit code 1.
- `outpath` refuses report directories inside Find_v2.
- After the commands run, there is no `-wal`, `-shm` or `-journal` file next to the release database, and the release folder is unchanged.

The suite uses the active local release and needs FindIt's existing environment. It includes live data checks and small isolated fixtures for unavailable/withheld data and verification failures. No network access is required for tests.

## Completing and verifying research notes

There are 18 helper commands. Start a report with `draft`; it generates the data sections for the selected scope and leaves TODOs for research and interpretation:

```bash
skills/findit/scripts/findit draft --month 2026-09
skills/findit/scripts/findit draft --stock 'Hyundai Motor India' --month 2026-09
skills/findit/scripts/findit draft --fund 'HDFC Flexi Cap' --month 2026-09
```

Save the draft to the path from `outpath`, preserve its generated data blocks, and finish the authored sections. Use `fact` to quote numerical FindIt fields in prose. Register every web source with its title, publisher, exact publication date and link. Then run:

```bash
skills/findit/scripts/findit verify /path/from/outpath.md --month 2026-09
```

Exit 0 means the mechanical checks passed; exit 2 means the report failed verification; exit 1 means an input or lookup error. Stock and fund reports do not require top-15 rows. Verification checks current-release data and source metadata, but the assistant must still verify article support, field meaning, conditional reasoning and absence of advice. See the [report workflow](skills/findit/references/report-template.md).

Older handwritten market reports can be inspected with `verify --tables-only`; this requires complete ranking tables and does not approve the narrative. Regenerate old notes with `draft` for full verification. The local fund walkthrough is saved under `reports/` (reports remain git-ignored).
