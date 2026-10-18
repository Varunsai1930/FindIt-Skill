import unittest

from helpers import MONTH, run_json, top

OPENING = ("new_position",)
EXITING = ("full_exit",)
BUYING = (*OPENING, "added")
SELLING = ("trimmed", *EXITING)


def amcs(counts: dict, changes: tuple[str, ...]) -> set[str]:
    return {a for c in changes for a in counts.get(c, {}).get("amcs", [])}


class EvidenceTests(unittest.TestCase):
    """Per-fund evidence for each top-15 stock adds up to its consensus row."""

    def test_amc_unions_match_consensus_counts(self):
        rows = {r["isin"]: r for side in ("buying", "selling") for r in top()[side]}
        self.assertGreater(len(rows), 15)
        for isin, row in rows.items():
            with self.subTest(stock=row["stock_name"], isin=isin):
                code, e = run_json("evidence", isin, "--month", MONTH)
                self.assertEqual(code, 0, e)
                counts = e["counts_by_change"]
                self.assertEqual(len(amcs(counts, BUYING)), row["amcs_buying"])
                self.assertEqual(len(amcs(counts, SELLING)), row["amcs_selling"])
                self.assertEqual(len(amcs(counts, OPENING)), row["amcs_opening"])
                self.assertEqual(len(amcs(counts, EXITING)), row["amcs_exiting"])

    def test_name_lookup_reports_resolution(self):
        name = top()["buying"][0]["stock_name"].removeprefix("EQ - ")
        code, e = run_json("evidence", name, "--month", MONTH)
        self.assertEqual(code, 0, e)
        self.assertEqual(e["resolved"]["query"], name)
        self.assertEqual(e["resolved"]["isin"], e["isin"])
        self.assertIsInstance(e["resolved"]["other_matches"], list)
