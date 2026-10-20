import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from helpers import MONTH, fq, report_table, report_text, run, run_json, top


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
        start = next(i for i, line in enumerate(lines) if line.startswith("## Broadest buying"))
        end = next(i for i, line in enumerate(lines) if line.startswith("## Evidence"))
        self.tables = lines[start:end]

    def tearDown(self):
        self._tmp.cleanup()

    def verify(self, lines: list[str]) -> dict:
        path = self.dir / "note.md"
        path.write_text("# Note\n\n" + "\n".join(lines) + "\n", encoding="utf-8")
        code, data = run_json("verify", str(path), "--month", MONTH, "--tables-only")
        self.assertEqual(code, 0 if data["ok"] else 2)
        return data

    def test_untouched_tables_pass(self):
        data = self.verify(self.tables)
        self.assertTrue(data["ok"], json.dumps(data, ensure_ascii=False))
        self.assertEqual(data["mismatches"], [])
        self.assertEqual(data["report_rows_not_in_file"], [])
        self.assertEqual(data["rows_checked"], 30)

    def test_tampered_cell_is_flagged(self):
        lines = list(self.tables)
        i = next(i for i, line in enumerate(lines) if line.startswith("| ") and not line.startswith("| Stock |"))
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

    def test_missing_row_fails(self):
        lines = list(self.tables)
        index = next(i for i, line in enumerate(lines) if line.startswith("| EQ"))
        lines.pop(index)
        self.assertFalse(self.verify(lines)["ok"])

    def test_changed_duplicate_cannot_hide_behind_correct_first_row(self):
        row = next(line for line in self.tables if line.startswith("| EQ"))
        cells = row.split("|")
        cells[3] = " +999 "
        self.assertFalse(self.verify(self.tables + ["|".join(cells)])["ok"])

    def test_official_buying_selling_overlap_passes(self):
        row = next(line for line in self.tables if line.startswith("| EQ"))
        official = [row, row]
        with patch.object(fq, '_report_tables', return_value='\n'.join(official)):
            result = self.verify(official)
        self.assertTrue(result['ok'], result)
        self.assertEqual(result['rows_checked'], 2)
        self.assertEqual(result['duplicate_rows'], [])

    def test_missing_or_excess_occurrences_of_overlapping_stock_fail(self):
        row = next(line for line in self.tables if line.startswith("| EQ"))
        with patch.object(fq, '_report_tables', return_value='\n'.join([row, row])):
            missing = self.verify([row])
            excess = self.verify([row, row, row])
        self.assertFalse(missing['ok'])
        self.assertTrue(missing['report_rows_not_in_file'])
        self.assertFalse(excess['ok'])
        self.assertTrue(excess['duplicate_rows'])

    def test_changed_second_occurrence_of_official_overlap_fails(self):
        row = next(line for line in self.tables if line.startswith("| EQ"))
        cells = row.split('|')
        cells[4] = ' 999,999 '
        with patch.object(fq, '_report_tables', return_value='\n'.join([row, row])):
            result = self.verify([row, '|'.join(cells)])
        self.assertFalse(result['ok'])
        self.assertEqual(result['duplicate_rows'], [])
        self.assertEqual(len(result['mismatches']), 1)
