# Helper commands

All commands:

```bash
"<skill-dir>/scripts/findit" <command> [options]
```

- The database is the active release named by `Find_v2/real_data/readiness/releases/current.json` (`<release_id>.db`), opened read-only (`mode=ro`, `immutable=1`) through FindIt's dashboard app (`findit.web.app.create_app`, called in-process with `fastapi.testclient.TestClient`) and FindIt's own `report`, `summary`, `digest`, `consensus_signals` and `publication` functions. Nothing is recomputed in the helper.
- `scripts/findit` is a wrapper: it finds FindIt (`$FINDIT_ROOT`, else `<skill-dir>/findit_root` written by install.sh, else `/Users/varun/Downloads/Varun/Find_v2`) and uses its existing `.venv/bin/python` directly. If that interpreter is unavailable, it uses `uv run --no-sync --project <FindIt> python scripts/findit_query.py`, adding `--no-cache` unless `UV_CACHE_DIR` or `UV_NO_CACHE` is explicitly set. This avoids inaccessible home-directory caches in a sandbox. Failures keep their exit status and are never retried. The release is read once per command, so one command never mixes two releases.
- `--month` is `YYYY-MM`; omitted, it is the latest month with holding changes. Comparison commands (`report`, `top`, `consensus`, `trend`, `stock`, `evidence`, `fund`, `digest`, `draft`, `fact`, `verify`) reject a month without holding changes, such as the release's first month; `funds`, `amcs`, `history --start/--end`, `calendar` and `outpath` accept any loaded month.
- Money: FindIt stores ₹ lakh (`*_lakhs`). The helper adds `*_cr` = lakhs ÷ 100, rounded to 2 decimals. `findit report` rounds ₹ cr to whole numbers; when quoting a report table, copy the report's figure.
- Stocks can be given as an ISIN or a name; names use FindIt's own search (`/api/stocks/search`) and the top match is used. `evidence` and `history` return `resolved` (`query`, `isin`, `name`, `other_matches`), `consensus` and `trend` a `resolved` list, and `stock` `search_matches`. If the top match is wrong, re-run with the ISIN.
- Input/lookup errors print `{"error": "..."}` and exit 1 (unknown month, a month with nothing to compare, unknown stock or fund, non-numeric `--schemes`, HTTP error from FindIt).
- `--n`, `--limit` and `--months` must be positive integers. Zero and negative counts return a structured input error before querying data. Month spans are clipped to loaded comparison months.
- Environment: `FINDIT_ROOT` overrides the FindIt path (and the saved `findit_root`); `FINDIT_REPORTS_DIR` overrides where `outpath` points.

The FindIt CLI equivalents (run from the FindSkill repo root; set `FINDIT_ROOT` for another checkout):

```bash
export FINDIT_ROOT="${FINDIT_ROOT:-../Find_v2}"
uv run --no-sync --project "$FINDIT_ROOT" findit report --db <release db> [--month YYYY-MM]
uv run --no-sync --project "$FINDIT_ROOT" findit digest --db <release db> --month YYYY-MM --schemes <ids>
```

`report` in the helper calls the same `findit.cli.report.build`, so its Markdown is identical (only the DB path inside the price-fetch hints is absolute).

## Commands

| Command | What it returns | FindIt source |
|---|---|---|
| `release` | `release_id`, `report_month`, `db`, `months`, `delta_months`, `validation_coverage`, `quarantined_count`/`quarantined`, `per_month` scheme and holding counts, latest shareholding quarter | `current.json`, `/api/coverage` |
| `report [--month M]` | The monthly overview Markdown: coverage, top 15 broadest buying/selling, 10-year evidence table, track record | `findit.cli.report.build` |
| `top [--month M] [--n 15]` | JSON of the same top-N buying and selling lists as `report`, in the same order, with all consensus fields | `/api/consensus/{M}` + `consensus_signals.broadest_selling` |
| `consensus [--month M] [--stock S ...] [--n 30]` | Consensus rows for named stocks (with `rank_buying`), or the top N; `not_ranked` for named stocks with no activity | `/api/consensus/{M}` |
| `trend [--month M] [--months 6] [--stock S ...] [--n 15]` | Per month: `rank_buying`, AMCs buying/selling, discretionary net, existing-position and total flow (₹ cr), FII/DII. Without `--stock`: the stocks in each month's top N; `coverage_by_month` preserves withheld/quarantine notices | `/api/consensus/{m}` per month |
| `search QUERY [--month M] [--limit 8]` | Matching stocks: ISIN, name, industry, schemes holding | `/api/stocks/search` |
| `stock S [--month M] [--holdings]` | One-stop stock view: `consensus` row (or `consensus_note`), `evidence` (per-fund changes), `history` (fixed cohort), `shareholding` filings, `holdings_all_schemes` (first 20 by value unless `--holdings`) | `/api/stock`, `/api/evidence`, `/api/history`, `/api/consensus` |
| `evidence S [--month M] [--full]` | Per-fund changes in the stock vs the previous month; `--full` returns FindIt's raw payload including source workbook rows | `/api/evidence/{isin}` |
| `history S [--start M0] [--end M1]` | Fixed-cohort month-by-month shares, net flow, houses buying/selling | `/api/history/{isin}` |
| `funds [QUERY] [--month M] [--limit 25]` | Schemes whose AMC/code/title contain all query words: `scheme_id`, `label`, `is_active_equity` | `schemes` table via read-only connection, FindIt's title/label functions |
| `amcs [--month M]` | Schemes loaded per AMC (active equity / other) this month and last; `not_loaded_this_month` lists AMCs that dropped out (their schemes are not compared) | `schemes` + `mf_holdings_monthly` via read-only connection |
| `fund F [--month M] [--months 3]` | For a scheme ID or name: rule-based `summary` per month, and for month M the equity `changes` (new/added/trimmed/exited, largest flow first) if FindIt's summary gate passes; else `changes_withheld` with the reason | `/api/summary/{id}/{m}`, `findit.summary.assess`, `mf_holding_deltas` |
| `digest --schemes ID[,ID] [--month M]` | `findit digest` text for those schemes | `findit.cli.digest.build_digest` |
| `calendar [--month M]` | Statutory deadlines: this and next month's MF portfolio disclosure, quarter-end shareholding filing deadlines | `findit.core.publication` |
| `draft [--month M] [--stock S / --fund F]` | Research-note Markdown with scope-specific data blocks, release metadata, required sections and TODOs for authored analysis; stdout only | FindIt report plus helper stock/fund/trend/AMC/calendar outputs |
| `fact --source SOURCE --path POINTER [--path POINTER ...] [--month M] [--stock S / --fund F]` | Scalar values wrapped in HTML comments identifying each field; repeat `--path` to share one source lookup | Requested structured helper output for this report scope |
| `verify FILE [--month M]` | Checks release identity, every required data block, referenced scalar values, report sections, numeric provenance and dated source metadata. No dependency on a top-15 ranking row for stock/fund reports. Exit 0 on pass, 2 on failed verification, 1 on input errors | Fresh helper outputs against the current active release |
| `verify FILE --tables-only [--month M]` | Legacy market-table check: requires every top-15 row and rejects changed, duplicate, unknown or unparsed rows. Does not check narrative, citations or the full report. Not for final approval | FindIt report table functions |
| `outpath [--month M] [--scope NAME]` | `reports_dir` and a `path` for the report file (refuses any path inside the FindIt repo) | — |

## Field glossary (consensus rows)

| Field | Meaning | Report column |
|---|---|---|
| `amcs_buying` / `amcs_selling` | Fund houses (AMCs) with at least one active equity scheme that raised / cut its share count | AMCs buying / selling |
| `net_amc_count` | `amcs_buying − amcs_selling` (rank order for buying; selling list sorts by it ascending) | — |
| `net_active_amc_count` | AMCs that raised the stock's weight beyond what their inflows explain, net of those that cut it | Discretionary net |
| `amcs_opening` / `amcs_exiting` | AMCs opening a new position / fully exiting | — |
| `schemes_buying` / `schemes_selling` | Same counts at scheme level | — |
| `accumulation_flow_lakhs` | Estimated ₹ flow into positions that already existed last month | Existing-position flow (₹ cr) |
| `new_position_flow_lakhs` | Estimated ₹ flow into new positions | — |
| `total_flow_lakhs` | New-position + existing-position flow | — |
| `discretionary_flow_lakhs` | Flow from the discretionary (weight-raising) part | — |
| `total_price_effect_lakhs` | Value change from price moves, not trading | — |
| `universe_status` | `established`, `new_listing` (new to the disclosed universe), etc. | — |
| `fii_direction` / `dii_direction` | Direction of FII / DII % between the last two quarterly shareholding filings public when the month's portfolios were (`no_data` = no filing; report shows "no filing") | FII / DII |
| `fii_pct`, `previous_fii_pct`, `fii_pct_change` (and DII) | The filing percentages behind the direction, with `shareholding_quarter_end` and `previous_shareholding_quarter_end` | — |

Flows are estimates: share change × month-end price implied by the disclosure (new positions use current value, exits previous value). They are not execution prices or returns.

## Evidence (`stock` → `evidence`, or `evidence`)

- `funds[]`: `change` (`new_position`, `added`, `trimmed`, `full_exit`, `unchanged`: FindIt's stored action for that scheme — `new`, `added`, `trimmed`, `exited`, `unchanged` — renamed; `not_in_stored_changes` if FindIt has no stored row), `amc_name`, `scheme_name`, `quantity_prev`, `quantity_curr`, `qty_change`, `split_ratio`, `pct_nav_prev`/`pct_nav_curr`, `flow_cr`, `price_effect_cr`, `value_change_cr`, `source_urls` (the AMC workbooks).
- `counts_by_change`: schemes and AMCs per change type. The union of AMCs in `new_position` and `added` equals `amcs_buying`; `trimmed` + `full_exit` equals `amcs_selling`.
- Totals: `current_shares`, `net_share_change`, `gross_added_shares`, `gross_reduced_shares`, `net_flow_cr` (= total flow, including new positions).
- `coverage_by_amc`: per AMC, schemes loaded / compared / missing previous / withheld / not validated. `coverage_state: unknown_completeness` means FindIt cannot confirm it has every scheme of that AMC.
- `price_convention`, `ownership_note`, `review_status`: quote these caveats when relevant.

## History (`stock` → `history`, or `history`)

- `points[]`: per month `shares`, `funds`, `status` (`validated_fixed_cohort`, or a withheld/unavailable state), `net_share_change`, `net_flow_cr`, `houses_buying`, `houses_selling`, `adjustments` (splits/bonuses), `source_revision`.
- `cohort_count`, `scope`, `limitation`: the cohort is only the funds validated in every month of the range, so its counts are smaller than the monthly ranking's. Always say "among the N funds tracked in every month".

## Fund (`fund`)

- `months{M}.summary`: FindIt's rule-based text (opened, added, trimmed, fully exited, with the largest of each).
- `summary_status`: `available`, `quarantined`, `nonfinite_or_invalid_data`, `unvalidated`, `unknown_instrument_type`, `no_data` (no comparison for that month, e.g. the first month tracked).
- `changes[]`: `stock`, `action` (`new`, `added`, `trimmed`, `exited`), `qty_change`, `flow_cr`, `value_change_cr`.

## Shareholding (`stock` → `shareholding`)

Quarterly exchange filings: `quarter_end`, `promoter_pct`, `fii_pct`, `dii_pct`, `public_pct`, `published_on`, `source`. FII and DII are part of the public float. Missing filings are "missing", not zero.

## Validation and coverage language

- `report` → Coverage: how many active equity schemes and AMCs were compared, how many were left out and why, and the validation gate result. Restate it in every report.
- Withheld / quarantined / not validated means the numbers failed or skipped FindIt's checks; say "withheld pending validation", never "no change".
- A stock not in a month's ranking had no compared active-fund buying or selling that month.

## Drafts, facts and verification

Use `draft` as the report template; see [report-template.md](report-template.md). Stock and fund targets are mutually exclusive. Resolve ambiguous names before drafting; prefer the chosen ISIN or scheme ID. Metadata pins the report scope, target, month and release. A later active release causes verification to fail until the note is regenerated.

`fact` uses a JSON pointer into a structured output. Available sources are `release`, `amcs`, `calendar` and, depending on scope, `top`/`trend`, `stock`/`trend`, or `fund`. Pointer segments name object keys or zero-based array indexes; escape `~` as `~0` and `/` as `~1`. Lists/objects are not scalar facts. Values use the helper's existing units; use `*_cr` for money.

Examples (use the actual target and month selected for the report):

```bash
"<skill-dir>/scripts/findit" draft --fund 1102 --month 2026-09
"<skill-dir>/scripts/findit" fact --fund 1102 --month 2026-09 --source fund --path /months/2026-09/changes/0/flow_cr
"<skill-dir>/scripts/findit" fact --stock INE0V6F01027 --month 2026-09 --source stock --path /consensus/amcs_buying
"<skill-dir>/scripts/findit" fact --month 2026-09 --source top --path /buying/0/amcs_opening --path /buying/0/new_position_flow_cr
"<skill-dir>/scripts/findit" verify "<report-path>" --month 2026-09
```

The fact command emits the value between `findit-value` comments. Preserve both comments and the value. Verification rereads the field; it does not trust a saved JSON value supplied by the report author. Keep the surrounding sentence accurate about the field's entity, date and scope.

Fact lookups load only the requested source rather than building a complete draft. Repeat `--path` to quote several fields from that source in one command; each fact is returned on its own line in the requested order. Every invocation reads the active release afresh; no saved value cache is trusted. If any path fails, the command returns an error without partial facts.

Stock and stock-trend facts also pin the stock's ISIN, report month and release. Use `fact --stock ISIN` to cite an individual stock's history inside a market or fund report for the same month and release; verification reloads that stock's data directly, including months outside the market's top-15 buying list. Keep all of the emitted reference fields intact. Older references without stock context remain relative to their report's own scope.

Verification returns `block_errors`, `claim_errors`, `citation_errors`, `unverified_numeric_lines`, and `errors` for structure/metadata. Dates and other numerical FindIt prose also need fact references. Numerical external claims must have a registered source link on the same line and appear in `externally_sourced_numeric_lines` for human review. No article is fetched by `verify`; a syntactically valid source entry is not evidence that the page supports the claim. The agent must open sources during research and perform `manual_review` before delivering.

Metadata and fact-reference JSON objects are limited to 16,384 characters each. Duplicate keys, boolean version identifiers and excessive nesting are invalid. Malformed metadata produces a structured input error; malformed fact references produce failed verification with claim errors.
