# Report template

Write the report in Markdown at the path from `outpath`. Keep the section order. Replace `<…>` with content; drop a subsection only when it does not apply (e.g. "Funds that changed it" for a market-wide report) and never drop sections 1–6 or the disclaimer. Every number must come from the helper or `report` output you ran in this session.

```markdown
# FindIt research note — <market-wide | Stock name | Fund name> — <Month YYYY>

*Research, not investment advice. Generated <today's date> from FindIt release `<first 12 chars of release_id>` (data months <first>–<last>). Portfolios for <M> were public by <portfolios_public_on>.*

> FindIt's own 10-year test found no group of stocks — by mutual fund and FII ownership change — that reliably beats comparable stocks once size is controlled. Read this as a record of what funds did, not a buy or sell list.

## 1. Summary
- <3–6 bullets: the main changes, the strongest possible explanation with its source, the main thing to watch>

## 2. What changed (<prev month> → <M>)

### Coverage and data quality
<Restate the report's coverage bullets: schemes and AMCs compared, left out and why, validation gate. Add any withheld/quarantined/not-validated items and any AMC with missing or incomplete coverage.>

### Broadest buying and selling   <!-- market-wide reports -->
<The report's top-15 tables, copied exactly (you may shorten "EQ - " prefixes in names only).>

Notes on the lists:
- **New positions vs accumulation:** <which leaders are new listings / new positions (amcs_opening, new_position_flow_cr) vs added to existing holdings (accumulation_flow_cr)>
- **Breadth vs conviction:** <names where AMCs buying is high but discretionary net is low (buying in line with inflows), or the reverse>
- **Recurring vs one-off:** <from `trend`: names also in the top lists in earlier months, or reversals>
- **FII/DII direction:** <where funds and FIIs moved in the same/opposite direction; state the filing quarters used>

### <Stock name>: who bought and sold   <!-- stock reports -->
| | AMCs | Schemes | Shares | ₹ cr flow |
|---|---|---|---|---|
| Opened new positions | <n, names> | <n> | <+shares> | <cr> |
| Added | … | … | … | … |
| Trimmed | … | … | … | … |
| Fully exited | … | … | … | … |

<Rank in the month's buying list, AMCs buying/selling, discretionary net, existing-position vs total flow, FII/DII % from the last two filings. Then a table of the individual funds that changed (fund house, scheme, previous → current shares, % of NAV before → after, ₹ cr flow).>

#### Month by month
| Month | Rank (buying) | AMCs buying / selling | Discretionary net | Existing-position flow (₹ cr) | Total flow (₹ cr) |
|---|---|---|---|---|---|
<from `trend --stock … --months 12`; months with no activity say "not ranked">

<Then the fixed-cohort history (`history`): shares held by the <cohort_count> funds tracked in every month, with net flow and houses buying/selling. Say that this cohort is narrower than the monthly ranking.>

### <Fund name>: what it added and cut   <!-- fund reports -->
<FindIt's summary for M, then a table of changes (stock, action, shares, ₹ cr flow) — largest first, then a short comparison with the previous months' summaries. State the summary_status if not available.>

## 3. Why it may have changed (possible explanations)
*These are events reported in the news around <M>. Fund houses do not publish reasons for individual trades; these are possible explanations, not the funds' stated reasons.*

| Data point | Possible explanation | Source (date) | Link strength |
|---|---|---|---|
| <e.g. 7 AMCs opened positions in NSE> | <event> | [<title>, <publisher>](<url>) (<date>) | <direct company event / sector / market backdrop> |

<Short paragraphs on the market backdrop (rates, oil, conflicts, flows) with citations. Say what you looked for and did not find. If no web search tool was available: "No web search was available in this session, so no explanations are given.">

## 4. Possible future impact (scenarios, not predictions)
- **If <condition>:** <what that could mean for fund positioning in these names, grounded in the data above>
- **If instead <condition>:** <…>
- <Note the limits: one month of disclosures, estimated flows, FindIt's evidence test.>

## 5. What to keep an eye on
| When | What | Why it matters here | Source |
|---|---|---|---|
| <next_month_portfolios_public_by> | <next month's> MF portfolio disclosures | Shows whether this month's buying/selling continues | FindIt publication rules |
| <quarter filing deadline> | Quarterly shareholding filings for <quarter_end> | Updates FII/DII direction | FindIt publication rules |
| <date> | <RBI policy / Fed / results / index rebalance / lock-in expiry / data release> | <…> | [<source>](<url>) |

Risks and data caveats: <coverage gaps, withheld schemes, estimated flows, unscored track record months>.

## 6. Sources
1. FindIt release `<release_id>` — `findit report --month <M>` and helper commands <list>.
2. [<title>](<url>) — <publisher>, <date>
<…every web source cited above…>

---
*Research, not investment advice. No buy, sell or hold recommendation is made or implied. Numbers come from FindIt's processing of AMC monthly portfolio disclosures and exchange shareholding filings; flows are estimates (share change × disclosed month-end price), not trade prices.*
```

## Chat summary

After writing the file, reply with:
- 5–8 bullets: the biggest changes, the best-supported possible explanations (with source names), what to watch next;
- the report path;
- one line: "Research, not investment advice; FindIt's 10-year test found no group reliably beats comparable stocks once size is controlled."
