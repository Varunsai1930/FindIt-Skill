import unittest
from contextlib import closing

from findit.store import db as store_db
from helpers import COVERAGE, DB, run_json


def amcs_loaded(conn, month: str) -> set[str]:
    return {r[0] for r in conn.execute(
        "SELECT DISTINCT sch.amc_name FROM schemes sch JOIN mf_holdings_monthly h "
        "ON h.scheme_id = sch.scheme_id WHERE h.report_month = ?", (month,))}


class AmcsTests(unittest.TestCase):
    def test_dropped_out_amcs_match_database(self):
        known = COVERAGE["months"]
        with closing(store_db.connect_read_only(DB)) as conn:
            for month in COVERAGE["delta_months"][-3:]:
                with self.subTest(month=month):
                    prev = known[known.index(month) - 1]
                    before, now = amcs_loaded(conn, prev), amcs_loaded(conn, month)
                    code, data = run_json("amcs", "--month", month)
                    self.assertEqual(code, 0, data)
                    self.assertEqual(data["previous_month"], prev)
                    self.assertEqual(data["not_loaded_this_month"], sorted(before - now))
                    self.assertEqual(data["new_this_month"], sorted(now - before))
                    rows = {r["amc_name"]: r for r in data["amcs"]}
                    for amc in data["not_loaded_this_month"]:
                        self.assertIsNone(rows[amc]["month"])
                        self.assertIsNotNone(rows[amc]["previous_month"])
