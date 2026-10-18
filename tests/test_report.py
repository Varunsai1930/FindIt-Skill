import json
import tempfile
import unittest
from pathlib import Path

from helpers import MONTH, report_table, report_text, run, run_json, top


def report_cells(row: dict) -> list[str]:
    """A `top` row as the report's table cells, by the documented mapping."""
    flow = row["accumulation_flow_lakhs"]

    def direction(value):
        return "no filing" if value in (None, "no_data") else str(value)

    return [row["stock_name"],
            f"{row['amcs_buying']} / {row['amcs_selling']}",
            f"{row['net_active_amc_count']:+d}",
            "-" if flow is None else f"{flow / 100:,.0f}",
            direction(row["fii_direction"]),
            direction(row["dii_direction"])]


class ReportTests(unittest.TestCase):
    def test_report_is_findit_report_build(self):
        code, text = run("report", "--month", MONTH)
        self.assertEqual(code, 0)
        self.assertEqual(text, report_text())

    def test_report_defaults_to_latest_month(self):
        code, text = run("report")
        self.assertEqual(code, 0)
        self.assertEqual(text, report_text())


class TopTests(unittest.TestCase):
    def assertRowsMatch(self, side: str, heading: str):
        table = report_table(report_text(), heading)
        rows = top()[side]
        self.assertEqual(len(table), 15)
        self.assertEqual(len(rows), len(table))
        for i, (row, cells) in enumerate(zip(rows, table), 1):
            with self.subTest(side=side, rank=i, stock=row["stock_name"]):
                self.assertEqual(row["rank"], i)
                self.assertEqual(report_cells(row), cells)

    def test_buying_rows_reproduce_report_table(self):
        self.assertRowsMatch("buying", "Broadest buying")

    def test_selling_rows_reproduce_report_table(self):
        self.assertRowsMatch("selling", "Broadest selling")

    def test_top_is_for_requested_month(self):
        self.assertEqual(top()["month"], MONTH)


class VerifyTests(unittest.TestCase):
    """`verify` against a file holding the report's two top-15 tables."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="findskill-test-")
        self.dir = Path(self._tmp.name)
        lines = report_text().splitlines()
        start = next(i for i, l in enumerate(lines) if l.startswith("## Broadest buying"))
        end = next(i for i, l in enumerate(lines) if l.startswith("## Evidence"))
        self.tables = lines[start:end]

    def tearDown(self):
        self._tmp.cleanup()

    def verify(self, lines: list[str]) -> dict:
        path = self.dir / "note.md"
        path.write_text("# Note\n\n" + "\n".join(lines) + "\n", encoding="utf-8")
        code, data = run_json("verify", str(path), "--month", MONTH)
        self.assertEqual(code, 0)
        return data

    def test_untouched_tables_pass(self):
        data = self.verify(self.tables)
        self.assertTrue(data["ok"], json.dumps(data, ensure_ascii=False))
        self.assertEqual(data["mismatches"], [])
        self.assertEqual(data["report_rows_not_in_file"], [])
        self.assertEqual(data["rows_checked"], 30)

    def test_tampered_cell_is_flagged(self):
        lines = list(self.tables)
        i = next(i for i, l in enumerate(lines) if l.startswith("| ") and not l.startswith("| Stock |"))
        cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
        stock = cells[0]
        cells[3] = "999,999" if cells[3] != "999,999" else "1"
        lines[i] = "| " + " | ".join(cells) + " |"
        data = self.verify(lines)
        self.assertFalse(data["ok"])
        self.assertEqual(len(data["mismatches"]), 1)
        self.assertIn(stock.removeprefix("EQ - ").upper(), data["mismatches"][0]["stock"])
        self.assertEqual(data["mismatches"][0]["written"][2], cells[3])

    def test_file_without_tables_fails(self):
        data = self.verify(["No tables here.", "| just | a | pipe |"])
        self.assertFalse(data["ok"])
        self.assertEqual(data["rows_checked"], 0)
        self.assertIn("unparsed_table_rows", data)
