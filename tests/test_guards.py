import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import COVERAGE, DB, FILES_AT_START, MONTH, SCRIPT, fq, release_files, run, run_json, sidecars


class ErrorTests(unittest.TestCase):
    def assertError(self, *argv: str):
        code, text = run(*argv)
        self.assertEqual(code, 1, text)
        data = json.loads(text)
        self.assertEqual(list(data), ["error"])
        return data["error"]

    def test_unknown_month(self):
        self.assertIn("not in this release", self.assertError("top", "--month", "1999-01"))
        self.assertIn("not in this release", self.assertError("report", "--month", "1999-01"))

    def test_malformed_month(self):
        self.assertIn("YYYY-MM", self.assertError("amcs", "--month", "2026-13"))

    def test_unknown_stock(self):
        self.assertIn("No stock", self.assertError("evidence", "zzqx no such stock"))
        self.assertIn("No stock", self.assertError("stock", "zzqx no such stock"))

    def test_month_without_changes_rejected_for_comparisons(self):
        first = COVERAGE["months"][0]
        self.assertNotIn(first, COVERAGE["delta_months"])
        for command in ("top", "report", "evidence"):
            with self.subTest(command=command):
                argv = (command, "--month", first) if command != "evidence" else (
                    command, "reliance", "--month", first)
                self.assertError(*argv)
        code, data = run_json("amcs", "--month", first)
        self.assertEqual(code, 0, data)
        code, data = run_json("funds", "--month", first, "--limit", "1")
        self.assertEqual(code, 0, data)

    def test_bad_digest_scheme_ids(self):
        self.assertError("digest", "--schemes", "abc")

    def test_process_exit_code(self):
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        proc = subprocess.run([sys.executable, str(SCRIPT), "evidence", "zzqx no such stock"],
                              capture_output=True, text=True, env=env, timeout=120)
        self.assertEqual(proc.returncode, 1, proc.stderr)
        self.assertIn("error", json.loads(proc.stdout))


class OutpathTests(unittest.TestCase):
    def setUp(self):
        self._old = os.environ.get("FINDIT_REPORTS_DIR")

    def tearDown(self):
        if self._old is None:
            os.environ.pop("FINDIT_REPORTS_DIR", None)
        else:
            os.environ["FINDIT_REPORTS_DIR"] = self._old

    def outpath(self, reports_dir: Path):
        os.environ["FINDIT_REPORTS_DIR"] = str(reports_dir)
        return run_json("outpath", "--month", MONTH, "--scope", "Hyundai Motor India")

    def test_refuses_findit_root_and_subdirs(self):
        for target in (fq.FINDIT_ROOT, fq.FINDIT_ROOT / "reports", fq.RELEASES):
            with self.subTest(target=str(target)):
                code, data = self.outpath(target)
                self.assertEqual(code, 1)
                self.assertIn("Refusing", data["error"])
                self.assertFalse((fq.FINDIT_ROOT / "reports").exists())

    def test_allows_other_directory(self):
        with tempfile.TemporaryDirectory(prefix="findskill-test-") as tmp:
            code, data = self.outpath(Path(tmp))
            self.assertEqual(code, 0, data)
            path = Path(data["path"])
            self.assertEqual(path.parent, Path(tmp).resolve())
            self.assertTrue(path.name.startswith(f"findit-{MONTH}-hyundai-motor-india-"))
            self.assertFalse(path.exists())


class ReadOnlyTests(unittest.TestCase):
    def test_no_sidecar_files_and_release_unchanged(self):
        for argv in (("release",), ("top",), ("report",), ("amcs",), ("funds", "flexi cap"),
                     ("search", "reliance"), ("calendar",)):
            code, _ = run(*argv)
            self.assertEqual(code, 0, argv)
        self.assertEqual(sidecars(), [])
        self.assertEqual(release_files(), FILES_AT_START)
        self.assertTrue(DB.is_file())
