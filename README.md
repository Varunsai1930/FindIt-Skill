# FindSkill — `/findit` for Claude Code

A Claude Code skill that writes research notes on Indian mutual fund holdings changes from the local [FindIt](../Find_v2) release: what changed versus earlier months, possible reasons from cited news, scenarios, and what to watch. Research only; no investment advice.

```bash
./install.sh          # symlink skills/findit into ~/.claude/skills/findit
./install.sh --copy   # copy instead
FINDIT_ROOT=/path/to/Find_v2 ./install.sh   # FindIt elsewhere (saved for the skill)
```

Then restart Claude Code and type `/findit`, `/findit 2026-08`, `/findit Hyundai Motor India` or `/findit HDFC Flexi Cap`.

- `skills/findit/SKILL.md` — hard rules and workflow
- `skills/findit/scripts/findit` — wrapper that finds FindIt (`$FINDIT_ROOT`, the path install.sh saved, or the default) and runs the helper in FindIt's environment
- `skills/findit/scripts/findit_query.py` — read-only helper around FindIt's dashboard API and report functions
- `skills/findit/references/` — helper commands and report template

Reports are written to `reports/` here (symlink install), `~/FindIt-reports` (copy install), or `$FINDIT_REPORTS_DIR`. The skill never writes to the FindIt repo or database.

## Development

```bash
uv run --no-sync --project /Users/varun/Downloads/Varun/Find_v2 python -m pytest /Users/varun/Downloads/Varun/FindSkill/tests
```

The tests run `findit_query.py` against the active FindIt release, which they read from `Find_v2/real_data/readiness/releases/current.json`. They contain no release ID. They are read-only: they write nothing to Find_v2, create no `.pyc` files there and add no pytest cache. The tests check that:

- `report` is the same text as `findit.cli.report.build` for the latest month.
- `top` buying/selling rows give the report's top-15 table cells exactly.
- For each top-15 stock, the AMCs in `evidence` counts add up to the stock's AMCs buying, selling, opening and exiting.
- `verify` passes the report's own tables and flags one changed cell.
- `amcs` lists the AMCs loaded last month but not this month (checked against the database for the last three months).
- An unknown or malformed month, and an unknown stock name, give `{"error": ...}` with exit code 1.
- `outpath` refuses report directories inside Find_v2.
- After the commands run, there is no `-wal`, `-shm` or `-journal` file next to the release database, and the release folder is unchanged.

A run takes about 1.5 minutes. Most of that time is the 30 `evidence` lookups.
