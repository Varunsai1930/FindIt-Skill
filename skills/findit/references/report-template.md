# Research-note template and completion

Start with `draft --month M`, adding `--stock ISIN` or `--fund SCHEME_ID` for the chosen scope. Write its stdout to the path returned by `outpath`. This generates the actual tables and required sections directly from the active release. Do not hand-build a replacement template.

## Generated content

Keep the `findit-report` metadata and each `findit-data` block intact. The comments are hidden in rendered Markdown. Verification compares every block with current FindIt output and rejects missing, duplicated or changed blocks. Add your analysis between blocks; regenerate data through the helper if the release changes.

- Every scope includes provenance, coverage (including AMCs missing this month), the report's evidence section, disclosure deadlines and the disclaimer.
- Market reports include the complete buying/selling tables and recent top-rank history.
- Stock reports include the stock's consensus or explicit not-ranked status, per-fund changes, AMC coverage, trends, fixed-cohort history and quarterly filings. A stock does not need to be in the top 15.
- Fund reports include the selected scheme's summaries and available change rows. Withheld comparisons retain their reason and omit unavailable rows. No market ranking row is required.

## Finish the authored sections

Keep sections 1–6 in order and remove every TODO:

1. **Summary:** Give the main changes, important coverage limitations, strongest possible explanation and what to watch. Use company/fund names.
2. **What changed:** Add interpretation after the generated data. Distinguish new positions from accumulation and monthly ranking scope from fixed-cohort history. Explain recurring activity or reversals where supported.
3. **Why it may have changed:** Tie each possible explanation to a specific observation, cite the source beside it, and state whether it is company-specific, sector context or broad market context. Never describe it as the fund's confirmed reason. If no web tool was available or it failed, use the exact no-web sentence in SKILL.md. If searches worked but no dated sources were usable, use the exact no-usable-sources sentence instead.
4. **Possible future impact:** Write conditional scenarios and their limits, grounded in the observed positioning and cited events. Keep the generated evidence block. No predictions, ratings, targets or advice.
5. **What to keep an eye on:** Keep the generated deadlines; add sourced upcoming events and data caveats. Do not invent event dates.
6. **Sources:** Replace the source TODO line with a Markdown table row for every external link. Keep the rows directly below the generated header without a blank line. If no external sources were retained, remove the unused table and explain the research limitation.

## Numerical prose

For each FindIt number outside a generated data block, run `fact` with the report's month and target and the path to the scalar field you need. Paste its entire output inline, including both comments. For example, a sentence may render as “The fund added ₹235.4 cr to PB Fintech”; the underlying Markdown includes the field reference around `235.4`.

For an individual stock's history in a market or fund note, use `fact --stock ISIN` with the report's month and a `stock` or `trend` path. Its reference includes the stock, month and release so verification can reload the exact stock context, even when it is absent from the market's ranked buying rows.

Use the original helper JSON to find the path and identify the matching company or fund. Never choose a field only because it has the desired number. Facts cannot add, sum, divide or otherwise compute new measures. Qualitative prose needs no annotations. For literal dates from FindIt, use a fact from `calendar` or the relevant data field.

Keep signs and number formatting inside the fact exactly as emitted. Do not add a sign, exponent or decimal/thousands fragment outside the marker, or join two facts into one displayed number. Ordinary emphasis, sentence punctuation and whitespace between facts are supported. Verification checks decoded character entities and invisible formatting as well as the literal Markdown.

Paste metadata, generated data blocks and facts as Markdown comments, outside code spans and fenced code blocks. Authored content supports Markdown and escaped literal text; raw HTML outside the generated data blocks fails verification because it can hide or alter the displayed report.

External business figures require a registered web citation on the same line. These are surfaced for manual review, not verified against FindIt. Do not cite news as evidence for portfolio numbers. All numerical prose without either provenance form fails verification.

## Source table

Keep these four columns; use one row per distinct URL:

```markdown
| Title | Publisher | Published | Link |
|---|---|---|---|
| Exact article title | Publisher name | YYYY-MM-DD | [Read article](https://example.com/article) |
```

Read the source page to confirm the title, publisher, publication date and supporting passage. Use the actual publication date, not an event date, crawl date, URL date or an invented day within a month. Exclude sources whose exact date is unavailable. Future publication dates, invalid dates, missing metadata and unregistered links fail verification. Cite these same URLs beside the claims they support.

## Delivery check

Run `verify "<report-path>" --month M`; require `ok: true` and exit 0. Fix every reported error. Review the returned manual-review items: actual source support, correct field/entity/month/scope in prose, conditional reasoning and no investment advice. The verifier checks data fidelity and citation metadata; it cannot establish why a fund traded.

Legacy handwritten reports need regeneration through `draft` for full verification. `verify --tables-only` can inspect their complete market tables but cannot approve an entire note.

In chat, give 5–8 concise bullets, name missing AMCs, link the report, and state: “Research, not investment advice; FindIt's 10-year test found no group reliably beats comparable stocks once size is controlled.”
