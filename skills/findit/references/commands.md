# Helper commands

All commands:

```bash
"<skill-dir>/scripts/findit" <command> [options]
```

- The database is the active release named by `Find_v2/real_data/readiness/releases/current.json` (`<release_id>.db`), opened read-only (`mode=ro`, `immutable=1`) through FindIt's dashboard app (`findit.web.app.create_app`, called in-process with `fastapi.testclient.TestClient`) and FindIt's own `report`, `summary`, `digest`, `consensus_signals` and `publication` functions. Nothing is recomputed in the helper.
- `scripts/findit` is a wrapper: it finds FindIt (`$FINDIT_ROOT`, else `<skill-dir>/findit_root` written by install.sh, else `/Users/varun/Downloads/Varun/Find_v2`) and runs `uv run --no-sync --project <FindIt> python scripts/findit_query.py`. The release is read once per command, so one command never mixes two releases.
- `--month` is `YYYY-MM`; omitted, it is the latest month with holding changes. Comparison commands (`report`, `top`, `consensus`, `trend`, `stock`, `evidence`, `fund`, `digest`, `verify`) reject a month without holding changes, such as the release's first month; `funds`, `amcs`, `history --start/--end`, `calendar` and `outpath` accept any loaded month.
- Money: FindIt stores ₹ lakh (`*_lakhs`). The helper adds `*_cr` = lakhs ÷ 100, rounded to 2 decimals. `findit report` rounds ₹ cr to whole numbers; when quoting a report table, copy the report's figure.
- Stocks can be given as an ISIN or a name; names use FindIt's own search (`/api/stocks/search`) and the top match is used. `evidence` and `history` return `resolved` (`query`, `isin`, `name`, `other_matches`), `consensus` and `trend` a `resolved` list, and `stock` `search_matches`. If the top match is wrong, re-run with the ISIN.
- Errors print `{"error": "..."}` and exit 1 (unknown month, a month with nothing to compare, unknown stock or fund, non-numeric `--schemes`, HTTP error from FindIt).
- Environment: `FINDIT_ROOT` overrides the FindIt path (and the saved `findit_root`); `FINDIT_REPORTS_DIR` overrides where `outpath` points.

The FindIt CLI equivalents (run from `/Users/varun/Downloads/Varun/Find_v2`):

```bash
uv run --no-sync findit report --db <release db> [--month YYYY-MM]
uv run --no-sync findit digest --db <release db> --month YYYY-MM --schemes <ids>
```

`report` in the helper calls the same `findit.cli.report.build`, so its Markdown is identical (only the DB path inside the price-fetch hints is absolute).

## Commands

| Command | What it returns | FindIt source |
|---|---|---|
| `release` | `release_id`, `report_month`, `db`, `months`, `delta_months`, `validation_coverage`, `quarantined_count`/`quarantined`, `per_month` scheme and holding counts, latest shareholding quarter | `current.json`, `/api/coverage` |
| `report [--month M]` | The monthly overview Markdown: coverage, top 15 broadest buying/selling, 10-year evidence table, track record | `findit.cli.report.build` |
| `top [--month M] [--n 15]` | JSON of the same top-N buying and selling lists as `report`, in the same order, with all consensus fields | `/api/consensus/{M}` + `consensus_signals.broadest_selling` |
| `consensus [--month M] [--stock S ...] [--n 30]` | Consensus rows for named stocks (with `rank_buying`), or the top N; `not_ranked` for named stocks with no activity | `/api/consensus/{M}` |
| `trend [--month M] [--months 6] [--stock S ...] [--n 15]` | Per month: `rank_buying`, AMCs buying/selling, discretionary net, existing-position and total flow (₹ cr), FII/DII. Without `--stock`: the stocks in each month's top N | `/api/consensus/{m}` per month |
| `search QUERY [--month M] [--limit 8]` | Matching stocks: ISIN, name, industry, schemes holding | `/api/stocks/search` |
| `stock S [--month M] [--holdings]` | One-stop stock view: `consensus` row (or `consensus_note`), `evidence` (per-fund changes), `history` (fixed cohort), `shareholding` filings, `holdings_all_schemes` (first 20 by value unless `--holdings`) | `/api/stock`, `/api/evidence`, `/api/history`, `/api/consensus` |
| `evidence S [--month M] [--full]` | Per-fund changes in the stock vs the previous month; `--full` returns FindIt's raw payload including source workbook rows | `/api/evidence/{isin}` |
| `history S [--start M0] [--end M1]` | Fixed-cohort month-by-month shares, net flow, houses buying/selling | `/api/history/{isin}` |
| `funds [QUERY] [--month M] [--limit 25]` | Schemes whose AMC/code/title contain all query words: `scheme_id`, `label`, `is_active_equity` | `schemes` table via read-only connection, FindIt's title/label functions |
| `amcs [--month M]` | Schemes loaded per AMC (active equity / other) this month and last; `not_loaded_this_month` lists AMCs that dropped out (their schemes are not compared) | `schemes` + `mf_holdings_monthly` via read-only connection |
| `fund F [--month M] [--months 3]` | For a scheme ID or name: rule-based `summary` per month, and for month M the equity `changes` (new/added/trimmed/exited, largest flow first) if FindIt's summary gate passes; else `changes_withheld` with the reason | `/api/summary/{id}/{m}`, `findit.summary.assess`, `mf_holding_deltas` |
| `digest --schemes ID[,ID] [--month M]` | `findit digest` text for those schemes | `findit.cli.digest.build_digest` |
| `calendar [--month M]` | Statutory deadlines: this and next month's MF portfolio disclosure, quarter-end shareholding filing deadlines | `findit.core.publication` |
| `verify FILE [--month M]` | Checks every table row in FILE shaped like the report's top-15 tables (`Stock \| AMCs buying / selling \| Discretionary net \| Existing-position flow \| FII \| DII`) against the report's tables; `ok` is false on any mismatch, a row for a stock not in the report's tables, a row naming a ranked stock that could not be parsed (`unparsed_table_rows`, e.g. an added column), or when no row was checked at all. Names may drop the `EQ - ` prefix | `consensus_signals.ranked_consensus` + `broadest_selling` + `findit.cli.report._table` (the same functions `findit report` uses, without rerunning the backtest) |
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
