"""Read-only JSON/Markdown access to the active FindIt release for the findit skill.

Run with FindIt's environment (FindIt itself does every calculation):

    uv run --no-sync --project "$FINDIT_ROOT" python findit_query.py <command> [...]

FindIt's location is $FINDIT_ROOT, else the path saved in <skill-dir>/findit_root
by install.sh, else Find_v2 beside the source FindSkill checkout (the bundled `findit`
wrapper script applies the same order). The database is resolved once per run
from real_data/readiness/releases/current.json and opened
read-only, through FindIt's own dashboard app (fastapi TestClient, in-process,
no server) or FindIt's own report/summary/publication functions. Nothing is
written anywhere; output goes to stdout.

Commands: release, report, top, consensus, trend, search, stock, evidence,
history, funds, amcs, fund, digest, calendar, draft, fact, verify, outpath. See references/commands.md.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
from collections import Counter
from contextlib import closing
from pathlib import Path

# FindIt's packages live outside this skill; importing them must not create .pyc files there.
sys.dont_write_bytecode = True

DEFAULT_ROOT = Path(__file__).resolve().parents[4] / "Find_v2"


def _findit_root() -> Path:
    if os.environ.get("FINDIT_ROOT"):
        return Path(os.environ["FINDIT_ROOT"]).expanduser()
    saved = Path(__file__).resolve().parents[1] / "findit_root"
    if saved.is_file():
        saved_root = saved.read_text(encoding="utf-8").strip()
        if saved_root:
            return Path(saved_root).expanduser()
    return Path(DEFAULT_ROOT)


FINDIT_ROOT = _findit_root()
RELEASES = FINDIT_ROOT / "real_data" / "readiness" / "releases"
ISIN_RE = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")
MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")

try:
    from fastapi.testclient import TestClient
    from findit.web import app as web
    from findit.core import consensus_signals, publication
    from findit.store import db as store_db
    from findit.summary import assess
except ImportError as exc:  # pragma: no cover - environment problem
    sys.exit(f"FindIt is not importable ({exc}). Run with: "
             f"uv run --no-sync --project {FINDIT_ROOT} python {Path(__file__).name} ...")


# -- release resolution -------------------------------------------------------

_RELEASE = None


def current_release() -> dict:
    """The active release, read once per process so one command never mixes two releases."""
    global _RELEASE
    if _RELEASE is None:
        _RELEASE = _read_release()
    return dict(_RELEASE)


def _read_release() -> dict:
    pointer = RELEASES / "current.json"
    try:
        data = json.loads(pointer.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        sys.exit(f"Cannot read the active release pointer {pointer}: {exc}")
    release_id = str(data.get("release_id", ""))
    if not re.fullmatch(r"[a-f0-9]{64}", release_id):
        sys.exit(f"{pointer} does not name a valid release_id")
    db_path = RELEASES / f"{release_id}.db"
    if not db_path.is_file():
        sys.exit(f"Active release database is missing: {db_path}")
    return {"release_id": release_id, "report_month": data.get("report_month"), "db": str(db_path)}


_CLIENT = None


def client() -> TestClient:
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = TestClient(web.create_app(current_release()["db"]))
    return _CLIENT


def api(path: str, **params):
    params = {k: v for k, v in params.items() if v is not None}
    response = client().get(path, params=params)
    if response.status_code != 200:
        try:
            detail = response.json().get("detail")
        except ValueError:
            detail = response.text
        raise LookupError(f"{path} -> HTTP {response.status_code}: {detail}")
    return response.json()


def ro_conn():
    """Read-only connection for lookups FindIt has no endpoint for (fund names)."""
    conn = store_db.connect_read_only(current_release()["db"])
    conn.execute("PRAGMA query_only=ON;")
    return conn


# -- small formatting helpers (unit conversion only, never new numbers) ------

def cr(lakhs):
    """₹ lakh -> ₹ crore, 2 decimals. FindIt stores money in lakhs."""
    if lakhs is None or (isinstance(lakhs, float) and not math.isfinite(lakhs)):
        return None
    return round(float(lakhs) / 100, 2)


def add_crore(row: dict) -> dict:
    for key in list(row):
        if key.endswith("_lakhs"):
            row[key[: -len("_lakhs")] + "_cr"] = cr(row[key])
    return row


_MONTHS = None


def _month_lists() -> tuple[list[str], list[str]]:
    """(months FindIt knows, months with holding changes), read once per process."""
    global _MONTHS
    if _MONTHS is None:
        with closing(ro_conn()) as conn:
            known = sorted(web._known_months(conn))
            compared = sorted(str(r[0]) for r in conn.execute(
                "SELECT DISTINCT report_month FROM mf_holding_deltas WHERE report_month IS NOT NULL"))
        _MONTHS = (known, compared)
    return _MONTHS


def months() -> list[str]:
    return _month_lists()[0]


def check_month(month: str | None, compared: bool = True) -> str:
    """A month in this release; with compared=True it must have holding changes to compare."""
    known, with_changes = _month_lists()
    if month is None:
        if not with_changes:
            raise LookupError("No month in this release has holding changes yet")
        return with_changes[-1]
    if not MONTH_RE.match(month):
        raise LookupError(f"Month must be YYYY-MM, got {month!r}")
    if month not in known:
        raise LookupError(f"Month {month} is not in this release (months: {known[0]}..{known[-1]})")
    if compared and month not in with_changes:
        raise LookupError(f"Month {month} has no holding changes to compare (no previous month in this "
                          f"release); comparisons cover {with_changes[0]}..{with_changes[-1]}")
    return month


def prev_months(month: str, n: int) -> list[str]:
    if n < 1:
        raise ValueError('months must be a positive integer')
    with_changes = _month_lists()[1]
    if month not in with_changes:
        return []
    i = with_changes.index(month)
    return with_changes[max(0, i - n + 1): i + 1]


def resolve_stock(query: str) -> tuple[str, list[dict]]:
    """ISIN for a name or ISIN, plus every search match so the choice can be checked."""
    q = query.strip()
    if ISIN_RE.match(q.upper()):
        return q.upper(), []
    found = api("/api/stocks/search", q=q, limit=8)["results"]
    if not found:
        raise LookupError(f"No stock in this release matches {query!r}")
    return found[0]["isin"], found


def resolution(query: str, isin: str, matches: list[dict]) -> dict:
    """What a name resolved to, and the other matches it could have meant."""
    picked = next((m for m in matches if m["isin"] == isin), None)
    return {"query": query, "isin": isin, "name": picked["name"] if picked else None,
            "other_matches": [{"isin": m["isin"], "name": m["name"]} for m in matches if m["isin"] != isin]}


ACTION_LABELS = {"new": "new_position", "added": "added", "trimmed": "trimmed",
                 "exited": "full_exit", "unchanged": "unchanged"}


def stored_actions(isin: str, month: str) -> dict[int, str]:
    """FindIt's own action per scheme for this stock-month (mf_holding_deltas)."""
    with closing(ro_conn()) as conn:
        return {int(sid): action for sid, action in conn.execute(
            "SELECT scheme_id, action FROM mf_holding_deltas WHERE isin = ? AND report_month = ?",
            (isin, month))}


# -- commands -----------------------------------------------------------------

def cmd_release(args):
    info = current_release()
    cov = api("/api/coverage")
    info.update(months=cov["months"], delta_months=cov["delta_months"],
                latest_month=cov["latest_month"], validation_coverage=cov["validation_coverage"],
                quarantined_count=len(cov["quarantined"]), quarantined=cov["quarantined"][:50],
                per_month=cov["per_month"],
                shareholding_latest_quarter=cov["latest_quarter"])
    return info


def cmd_report(args):
    """Exactly `findit report` (same function), as Markdown."""
    from findit.cli import report
    month = check_month(args.month)
    return report.build(current_release()["db"], month)


_KEEP = ("isin", "stock_name", "industry", "universe_status", "amcs_buying", "amcs_selling",
         "amcs_opening", "amcs_exiting", "schemes_buying", "schemes_selling", "net_amc_count",
         "active_amcs_buying", "active_amcs_selling", "net_active_amc_count", "total_flow_lakhs",
         "new_position_flow_lakhs", "accumulation_flow_lakhs", "discretionary_flow_lakhs",
         "total_price_effect_lakhs", "fii_direction", "dii_direction", "fii_pct", "previous_fii_pct",
         "fii_pct_change", "dii_pct", "previous_dii_pct", "dii_pct_change",
         "shareholding_quarter_end", "previous_shareholding_quarter_end", "shareholding_status")


def _slim(row: dict) -> dict:
    return add_crore({k: row.get(k) for k in _KEEP})


def cmd_top(args):
    """Top-N broadest buying and selling: the same ranking and order as `findit report`."""
    import pandas as pd
    month = check_month(args.month)
    payload = api(f"/api/consensus/{month}", equity_only=1, active_only=1)
    rows = payload["results"]
    buying = rows[: args.n]
    selling = consensus_signals.broadest_selling(pd.DataFrame(rows)).head(args.n) if rows else pd.DataFrame()
    for i, r in enumerate(buying, 1):
        r["rank"] = i
    out = {"month": month, "ranked_count": payload["count"],
           "buying": [_slim(r) | {"rank": r["rank"]} for r in buying],
           "selling": [_slim(r) | {"rank": i} for i, r in
                       enumerate(json.loads(selling.to_json(orient="records")), 1)],
           "notes": ["AMCs buying/selling = amcs_buying/amcs_selling; 'Discretionary net' = "
                     "net_active_amc_count; 'Existing-position flow' = accumulation_flow_lakhs "
                     "(report rounds ₹ cr to whole numbers)."]}
    if "message" in payload:
        out["message"] = payload["message"]
    if payload.get("quarantined_schemes"):
        out["quarantined_schemes"] = payload["quarantined_schemes"]
    return out


def cmd_consensus(args):
    month = check_month(args.month)
    payload = api(f"/api/consensus/{month}", equity_only=1, active_only=1)
    rows = payload["results"]
    resolved = [resolution(s, *resolve_stock(s)) for s in args.stock or []]
    wanted = {r["isin"] for r in resolved} or None
    for i, r in enumerate(rows, 1):
        r["rank_buying"] = i
    if wanted:
        picked = [r for r in rows if r["isin"] in wanted]
        missing = sorted(wanted - {r["isin"] for r in picked})
    else:
        picked, missing = rows[: args.n], []
    out = {"month": month, "ranked_count": payload["count"],
           "rows": [_slim(r) | {"rank_buying": r["rank_buying"]} for r in picked]}
    if resolved:
        out["resolved"] = resolved
    if missing:
        out["not_ranked"] = {isin: "no fund bought or sold it this month (or not compared)" for isin in missing}
    for key in ("message", "quarantined_schemes"):
        if payload.get(key):
            out[key] = payload[key]
    return out


def cmd_trend(args):
    """Month-by-month consensus rows for stocks, or which top-N names recur."""
    month = check_month(args.month)
    span = prev_months(month, args.months)
    resolved = [resolution(s, *resolve_stock(s)) for s in args.stock or []]
    isins = [r["isin"] for r in resolved] or None
    out = {"months": span, "stocks": {}, "coverage_by_month": {}}
    if resolved:
        out["resolved"] = resolved
    ranks: dict[str, dict] = {}
    for m in span:
        payload = api(f"/api/consensus/{m}", equity_only=1, active_only=1)
        rows = payload["results"]
        notices = {k: payload[k] for k in ("message", "quarantined_schemes") if payload.get(k)}
        if notices:
            out["coverage_by_month"][m] = notices
        for i, r in enumerate(rows, 1):
            if isins is None and i > args.n:
                break
            if isins is not None and r["isin"] not in isins:
                continue
            entry = ranks.setdefault(r["isin"], {"stock_name": r["stock_name"], "by_month": {}})
            entry["by_month"][m] = {"rank_buying": i, "amcs_buying": r["amcs_buying"],
                                    "amcs_selling": r["amcs_selling"],
                                    "net_active_amc_count": r["net_active_amc_count"],
                                    "accumulation_flow_cr": cr(r["accumulation_flow_lakhs"]),
                                    "total_flow_cr": cr(r["total_flow_lakhs"]),
                                    "fii_direction": r["fii_direction"],
                                    "dii_direction": r["dii_direction"]}
    if isins:
        for isin in isins:
            ranks.setdefault(isin, {"stock_name": None, "by_month": {}})
            ranks[isin]["months_without_activity"] = [m for m in span if m not in ranks[isin]["by_month"]]
    out["stocks"] = ranks
    out["note"] = ("A month missing from by_month means the stock was not in that month's "
                   "ranking (no compared fund bought or sold it)" +
                   ("" if isins else f", or was outside the top {args.n} buying ranks") + ".")
    return out


def cmd_search(args):
    return api("/api/stocks/search", q=args.query, month=args.month, limit=args.limit)


def _compact_evidence(e: dict, full: bool, actions: dict[int, str]) -> dict:
    if full:
        return e
    funds = []
    for f in e.get("funds", []):
        prev, curr = f.get("quantity_prev") or 0, f.get("quantity_curr") or 0
        stored = actions.get(int(f["scheme_id"])) if f.get("scheme_id") is not None else None
        change = ACTION_LABELS.get(stored, "not_in_stored_changes")
        urls = sorted({s["url"] for side in ("previous_source", "current_source")
                       for s in (f.get(side) or {}).get("sources", []) if s.get("url")})
        funds.append(add_crore({
            "change": change, "amc_name": f.get("amc_name"), "scheme_id": f.get("scheme_id"),
            "scheme_name": f.get("scheme_name"), "quantity_prev": prev, "quantity_curr": curr,
            "qty_change": f.get("qty_change"), "split_ratio": f.get("split_ratio"),
            "pct_nav_prev": f.get("pct_nav_prev"), "pct_nav_curr": f.get("pct_nav_curr"),
            "flow_lakhs": f.get("flow_lakhs"), "price_effect_lakhs": f.get("price_effect_lakhs"),
            "value_change_lakhs": f.get("value_change_lakhs"), "source_urls": urls}))
    order = {"new_position": 0, "added": 1, "trimmed": 2, "full_exit": 3, "unchanged": 4,
             "not_in_stored_changes": 5}
    funds.sort(key=lambda f: (order[f["change"]], -abs(f.get("flow_lakhs") or 0)))
    by_change: dict[str, dict] = {}
    for f in funds:
        g = by_change.setdefault(f["change"], {"schemes": 0, "amcs": set()})
        g["schemes"] += 1
        g["amcs"].add(f["amc_name"])
    out = {k: v for k, v in e.items() if k not in ("funds", "coverage")}
    out = add_crore(out)
    out["counts_by_change"] = {k: {"schemes": v["schemes"], "amcs": sorted(v["amcs"])}
                               for k, v in by_change.items()}
    out["coverage_by_amc"] = {amc: {k: c.get(k) for k in ("coverage_state", "loaded", "compared",
                                                            "missing_previous", "withheld_count",
                                                            "not_validated_count")}
                              for amc, c in (e.get("coverage") or {}).items()}
    out["funds"] = funds
    return out


def cmd_evidence(args):
    month = check_month(args.month)
    isin, matches = resolve_stock(args.stock)
    out = _compact_evidence(api(f"/api/evidence/{isin}", month=month, active_only=1), args.full,
                            stored_actions(isin, month))
    out["resolved"] = resolution(args.stock, isin, matches)
    return out


def cmd_history(args):
    isin, matches = resolve_stock(args.stock)
    known = months()
    start = check_month(args.start, compared=False) if args.start else known[0]
    end = check_month(args.end, compared=False) if args.end else known[-1]
    h = api(f"/api/history/{isin}", start=start, end=end, active_only=1)
    h["resolved"] = resolution(args.stock, isin, matches)
    h.pop("cohort", None)
    for p in h.get("points", []):
        p.pop("evidence_url", None)
        p.pop("bar_percent", None)
        add_crore(p)
    return h


def cmd_stock(args):
    """One-stop stock view: consensus row, who bought/sold, holdings, history, filings."""
    month = check_month(args.month)
    isin, matches = resolve_stock(args.stock)
    stock = api(f"/api/stock/{isin}", month=month)
    holdings = [add_crore({k: h.get(k) for k in (
        "amc_name", "scheme_id", "scheme_title", "scheme_name", "quantity", "market_value_lakhs",
        "pct_nav", "action", "qty_change", "flow_lakhs", "comparison_status", "comparison_reason")})
        for h in stock.get("holdings", [])]
    rows = api(f"/api/consensus/{month}", equity_only=1, active_only=1)["results"]
    rank = next((i for i, r in enumerate(rows, 1) if r["isin"] == isin), None)
    out = {
        "isin": isin, "name": stock["name"], "industry": stock["industry"], "month": month,
        "portfolios_public_on": stock.get("portfolios_public_on"),
        "search_matches": [{"isin": m["isin"], "name": m["name"], "schemes_holding": m.get("schemes_holding")}
                           for m in matches],
        "consensus": (_slim(rows[rank - 1]) | {"rank_buying": rank, "ranked_count": len(rows)}) if rank else None,
        "evidence": _compact_evidence(api(f"/api/evidence/{isin}", month=month, active_only=1), False,
                                      stored_actions(isin, month)),
        "history": cmd_history(argparse.Namespace(stock=isin, start=None, end=month)),
        "shareholding": stock.get("shareholding"),
        "shareholding_status": stock.get("shareholding_status"),
        "holdings_all_schemes": {"count": stock.get("holdings_count"),
                                 "withheld_count": stock.get("withheld_count"),
                                 "not_validated_count": stock.get("not_validated_count"),
                                 "rows": holdings if args.holdings else holdings[:20],
                                 "note": "All loaded schemes incl. index/ETF; first 20 by value unless --holdings."},
    }
    if rank is None:
        out["consensus_note"] = (f"Not in the {month} ranking: no compared active fund bought or sold it.")
    return out


def _scheme_rows(conn, query: str | None, month: str | None):
    title = web._scheme_title_sql(conn)
    sql = (f"SELECT DISTINCT sch.scheme_id, sch.amc_name, sch.scheme_name, {title}, sch.is_active_equity "
           "FROM schemes sch")
    params: list = []
    if month:
        sql += " JOIN mf_holdings_monthly h ON h.scheme_id = sch.scheme_id AND h.report_month = ?"
        params.append(month)
    rows = [dict(zip(("scheme_id", "amc_name", "scheme_name", "scheme_title", "is_active_equity"), r))
            for r in conn.execute(sql + " ORDER BY sch.amc_name, sch.scheme_name", params)]
    for r in rows:
        r["label"] = web._scheme_label(r)
    if query:
        words = [w for w in re.split(r"\s+", query.lower()) if w]
        rows = [r for r in rows if all(w in " ".join(str(r[k] or "") for k in
                ("amc_name", "scheme_name", "scheme_title", "label")).lower() for w in words)]
    return rows


def cmd_funds(args):
    month = check_month(args.month, compared=False) if args.month else None
    with closing(ro_conn()) as conn:
        rows = _scheme_rows(conn, args.query, month)
    return {"query": args.query, "month": month, "count": len(rows), "schemes": rows[: args.limit]}


def cmd_amcs(args):
    """Schemes loaded per AMC this month vs the previous month; flags AMCs that dropped out."""
    month = check_month(args.month, compared=False) if args.month else check_month(None)
    known = months()
    prev = known[known.index(month) - 1] if known.index(month) > 0 else None
    with closing(ro_conn()) as conn:
        def counts(m):
            out: dict[str, dict] = {}
            for r in (_scheme_rows(conn, None, m) if m else []):
                c = out.setdefault(r["amc_name"], {"active_equity": 0, "other": 0})
                c["active_equity" if r["is_active_equity"] else "other"] += 1
            return out
        cur, before = counts(month), counts(prev)
    amcs = sorted(set(cur) | set(before))
    rows = [{"amc_name": a, "month": cur.get(a), "previous_month": before.get(a)} for a in amcs]
    return {"month": month, "previous_month": prev, "amcs": rows,
            "not_loaded_this_month": [a for a in amcs if a in before and a not in cur],
            "new_this_month": [a for a in amcs if a in cur and a not in before],
            "note": "An AMC not loaded this month is not compared: its schemes count as neither buying nor selling."}


def cmd_fund(args):
    """A scheme's rule-based summary for a month (and earlier months), plus its change rows."""
    month = check_month(args.month)
    with closing(ro_conn()) as conn:
        if str(args.fund).isdigit():
            scheme_id, candidates = int(args.fund), []
        else:
            candidates = _scheme_rows(conn, args.fund, month)
            if not candidates:
                raise LookupError(f"No scheme loaded for {month} matches {args.fund!r}")
            # Prefer active equity schemes, then the shortest label (the plain fund name).
            candidates.sort(key=lambda r: (not r["is_active_equity"], len(r["label"])))
            scheme_id = candidates[0]["scheme_id"]
        out = {"scheme_id": scheme_id,
               "other_matches": [{"scheme_id": c["scheme_id"], "label": c["label"], "amc_name": c["amc_name"]}
                                 for c in candidates[1:10]],
               "months": {}}
        for m in reversed(prev_months(month, args.months) or [month]):
            summary = api(f"/api/summary/{scheme_id}/{m}")
            entry = {"summary": summary["summary"], "summary_status": summary["summary_status"],
                     "has_data": summary["has_data"], "quarantined": summary["quarantined"]}
            out.setdefault("amc_name", summary["amc_name"])
            out.setdefault("scheme_name", summary["scheme_name"])
            reason = assess(conn, scheme_id, m)["reason"] if m == month else None
            if m == month and reason is None:
                rows = conn.execute(
                    "SELECT s.name, d.isin, d.action, d.qty_change, d.flow_lakhs, d.value_change_lakhs, d.prev_month "
                    "FROM mf_holding_deltas d JOIN stocks s ON s.isin = d.isin "
                    "WHERE d.scheme_id = ? AND d.report_month = ? AND s.instrument_type = 'equity' "
                    "AND d.action != 'unchanged' ORDER BY ABS(d.flow_lakhs) DESC", (scheme_id, m)).fetchall()
                entry["changes"] = [add_crore({"stock": web._stock_label(r[0]), "isin": r[1], "action": r[2],
                                               "qty_change": r[3], "flow_lakhs": r[4],
                                               "value_change_lakhs": r[5], "prev_month": r[6]}) for r in rows]
            elif m == month:
                entry["changes_withheld"] = (f"FindIt's summary gate did not pass this scheme-month "
                                             f"(reason: {reason}); no change rows shown.")
            out["months"][m] = entry
    return out


def cmd_digest(args):
    from findit.cli.digest import build_digest
    month = check_month(args.month)
    try:
        ids = [int(t) for s in args.schemes for t in str(s).split(",") if t.strip()]
    except ValueError:
        raise LookupError("--schemes takes numeric scheme IDs (find them with `funds`), "
                          f"got {' '.join(args.schemes)!r}") from None
    with closing(ro_conn()) as conn:
        return build_digest(conn, ids, month)


def cmd_calendar(args):
    """Disclosure dates from FindIt's publication rules, for 'what to watch'."""
    import datetime as dt
    month = check_month(args.month, compared=False) if args.month else check_month(None)
    y, m = map(int, month.split("-"))
    nxt = f"{y + (m == 12)}-{1 if m == 12 else m + 1:02d}"
    q_end_month = ((m - 1) // 3 + 1) * 3
    quarter_end = publication.month_end(f"{y}-{q_end_month:02d}")
    next_q = publication.month_end(f"{y + (q_end_month == 12)}-{3 if q_end_month == 12 else q_end_month + 3:02d}")
    return {
        "report_month": month,
        "this_month_portfolios_public_by": publication.mf_disclosure_deadline(month).isoformat(),
        "next_month": nxt,
        "next_month_portfolios_public_by": publication.mf_disclosure_deadline(nxt).isoformat(),
        "quarter_end": quarter_end.isoformat(),
        "quarter_shareholding_filing_deadline": publication.shareholding_filing_deadline(quarter_end).isoformat(),
        "next_quarter_end": next_q.isoformat(),
        "next_quarter_shareholding_filing_deadline": publication.shareholding_filing_deadline(next_q).isoformat(),
        "today": dt.date.today().isoformat(),
        "note": "Statutory deadlines per FindIt's publication rules; actual publication can be earlier.",
    }


def _norm_name(name: str) -> str:
    return re.sub(r"^EQ\s*-\s*", "", name.strip(), flags=re.I).strip().upper()


def _table_rows(text: str) -> dict[str, list[str]]:
    rows = {}
    for line in text.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if line.lstrip().startswith("|") and len(cells) == 6 and re.fullmatch(r"\d+ / \d+", cells[1]):
            rows.setdefault(_norm_name(cells[0]), cells[1:])
    return rows


def _report_tables(month: str) -> str:
    """The report's two top-15 tables, rendered by findit report's own functions (no backtest)."""
    from findit.cli import report
    with closing(store_db.connect_read_only(current_release()["db"])) as conn:
        ranked = consensus_signals.ranked_consensus(conn, month)
    selling = consensus_signals.broadest_selling(ranked).head(report.TOP_N)
    return "\n".join(report._table(ranked.head(report.TOP_N)) + report._table(selling))


def _verify_tables(args):
    """Check that a written report's top-15 rows match `findit report` exactly."""
    month = check_month(args.month)
    expected_text = _report_tables(month)
    expected = _table_rows(expected_text)
    expected_counts = Counter(k for line in expected_text.splitlines() for k in _table_rows(line))
    text = Path(args.file).expanduser().read_text(encoding="utf-8")
    written = _table_rows(text)
    # The official buying/selling lists may overlap. Match their multiplicity,
    # while checking every occurrence so a changed duplicate cannot hide.
    occurrences = [_table_rows(line) for line in text.splitlines()]
    written_counts = Counter(k for row in occurrences for k in row)
    duplicates = sorted(k for k in written if written_counts[k] > expected_counts[k])
    # Rows naming a ranked stock that the 6-column parser could not read (reformatted tables).
    unparsed = sorted({_norm_name(line.strip().strip("|").split("|")[0]) for line in text.splitlines()
                       if line.lstrip().startswith("|")
                       and _norm_name(line.strip().strip("|").split("|")[0]) in expected
                       and not _table_rows(line)})
    mismatches = [{"stock": k, "report": expected[k], "written": v}
                  for row in occurrences for k, v in row.items() if k in expected and expected[k] != v]
    unknown = sorted(k for k in written if k not in expected)
    missing = sorted(k for k in expected if written_counts[k] < expected_counts[k])
    checked = sum(count for k, count in written_counts.items() if k in expected)
    return {"month": month, "rows_checked": checked, "mismatches": mismatches,
            "rows_not_in_report_tables": unknown, "unparsed_table_rows": unparsed,
            "report_rows_not_in_file": missing,
            "duplicate_rows": duplicates,
            "ok": checked > 0 and not mismatches and not unknown and not unparsed and not missing and not duplicates,
            "note": ("No report-shaped row was found, so nothing was checked." if checked == 0 else
                     "Checks rows shaped like the report's top-15 tables only.")}


def _note_context(args, sources=None):
    import findit_notes
    return findit_notes.collect(sys.modules[__name__], args.month, args.stock, args.fund, sources=sources)


def cmd_draft(args):
    import findit_notes
    return findit_notes.draft(_note_context(args))


def cmd_fact(args):
    import findit_notes
    ctx = _note_context(args, sources=[args.source])
    return '\n'.join(findit_notes.fact(ctx, args.source, path) for path in args.path)


def cmd_verify(args):
    if args.tables_only:
        return _verify_tables(args)
    import findit_notes
    text = Path(args.file).expanduser().read_text(encoding="utf-8")
    meta = findit_notes.metadata(text)
    if args.month and args.month != meta['month']:
        raise ValueError('Requested month differs from the report metadata')
    ctx = findit_notes.collect(sys.modules[__name__], meta['month'],
                              meta['target'] if meta['scope'] == 'stock' else None,
                              meta['target'] if meta['scope'] == 'fund' else None)
    return findit_notes.verify(text, ctx, stock_context=lambda isin, source: findit_notes.collect(
        sys.modules[__name__], meta['month'], stock=isin, sources=[source]))


def cmd_outpath(args):
    """Where to save a report: never inside the FindIt repo."""
    import datetime as dt
    if os.environ.get("FINDIT_REPORTS_DIR"):
        base = Path(os.environ["FINDIT_REPORTS_DIR"]).expanduser()
    else:
        repo = Path(__file__).resolve().parents[3]
        base = repo / "reports" if (repo / "install.sh").is_file() else Path.home() / "FindIt-reports"
    base = base.resolve()
    if base == FINDIT_ROOT.resolve() or FINDIT_ROOT.resolve() in base.parents:
        raise LookupError(f"Refusing to write reports inside the FindIt repo ({base})")
    month = check_month(args.month, compared=False) if args.month else check_month(None)
    slug = re.sub(r"[^a-z0-9]+", "-", (args.scope or "market").lower()).strip("-")[:60] or "market"
    return {"reports_dir": str(base),
            "path": str(base / f"findit-{month}-{slug}-{dt.date.today().isoformat()}.md")}


# -- CLI ----------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)

    def add(name, fn, help_):
        p = sub.add_parser(name, help=help_)
        p.set_defaults(fn=fn)
        return p

    add("release", cmd_release, "Active release, months, validation coverage")
    p = add("report", cmd_report, "The findit report Markdown (same function)")
    p.add_argument("--month")
    p = add("top", cmd_top, "Top-N broadest buying and selling as JSON")
    p.add_argument("--month")
    p.add_argument("--n", type=int, default=15)
    p = add("consensus", cmd_consensus, "Consensus rows (top N, or named stocks)")
    p.add_argument("--month")
    p.add_argument("--stock", action="append")
    p.add_argument("--n", type=int, default=30)
    p = add("trend", cmd_trend, "Consensus by month for stocks, or recurring top-N names")
    p.add_argument("--month")
    p.add_argument("--months", type=int, default=6)
    p.add_argument("--stock", action="append")
    p.add_argument("--n", type=int, default=15)
    p = add("search", cmd_search, "Find stocks by name or ISIN prefix")
    p.add_argument("query")
    p.add_argument("--month")
    p.add_argument("--limit", type=int, default=8)
    p = add("stock", cmd_stock, "Everything about one stock for a month")
    p.add_argument("stock")
    p.add_argument("--month")
    p.add_argument("--holdings", action="store_true")
    p = add("evidence", cmd_evidence, "Per-fund changes in a stock for a month")
    p.add_argument("stock")
    p.add_argument("--month")
    p.add_argument("--full", action="store_true")
    p = add("history", cmd_history, "Fixed-cohort month-by-month history of a stock")
    p.add_argument("stock")
    p.add_argument("--start")
    p.add_argument("--end")
    p = add("funds", cmd_funds, "Find schemes by AMC/name words")
    p.add_argument("query", nargs="?")
    p.add_argument("--month")
    p.add_argument("--limit", type=int, default=25)
    p = add("amcs", cmd_amcs, "Schemes loaded per AMC, this vs previous month")
    p.add_argument("--month")
    p = add("fund", cmd_fund, "One scheme's summaries and change rows")
    p.add_argument("fund", help="scheme_id or name words")
    p.add_argument("--month")
    p.add_argument("--months", type=int, default=3)
    p = add("digest", cmd_digest, "findit digest text for schemes")
    p.add_argument("--month")
    p.add_argument("--schemes", nargs="+", required=True)
    p = add("calendar", cmd_calendar, "Next disclosure/filing deadlines")
    p.add_argument("--month")
    for name, fn in (("draft", cmd_draft), ("fact", cmd_fact)):
        p = add(name, fn, "Generate a scoped research-note draft" if name == "draft" else "Quote a verifiable field")
        p.add_argument("--month")
        scope = p.add_mutually_exclusive_group()
        scope.add_argument("--stock")
        scope.add_argument("--fund")
        if name == "fact":
            p.add_argument("--source", required=True)
            p.add_argument("--path", required=True, action="append",
                           help="JSON pointer into that source; repeat to quote several fields in one lookup")
    p = add("verify", cmd_verify, "Verify scoped data blocks, numerical claims, sections and source metadata")
    p.add_argument("file")
    p.add_argument("--month")
    p.add_argument("--tables-only", action="store_true", help="Legacy check: requires complete top-15 tables; no prose or citation checks")
    p = add("outpath", cmd_outpath, "Suggested report file path (outside FindIt)")
    p.add_argument("--month")
    p.add_argument("--scope", help="e.g. market, a stock or fund name")
    return ap


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        for field in ('n', 'limit', 'months'):
            value = getattr(args, field, None)
            if value is not None and value < 1:
                raise ValueError(f'--{field} must be a positive integer')
        result = args.fn(args)
    except (LookupError, OSError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return 1
    if isinstance(result, str):
        print(result, end="" if result.endswith("\n") else "\n")
    else:
        print(json.dumps(result, ensure_ascii=False, indent=1, default=str))
    return 2 if args.command == "verify" and not result["ok"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
