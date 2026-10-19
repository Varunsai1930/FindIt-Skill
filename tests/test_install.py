"""Install in temporary homes; never touch the user's installed skill or FindIt."""
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='findskill-install-')
        self.base = Path(self.tmp.name).resolve()
        self.repo = self.base / 'FindSkill with spaces'
        self.repo.mkdir()
        shutil.copy(ROOT / 'install.sh', self.repo / 'install.sh')
        shutil.copytree(ROOT / 'skills', self.repo / 'skills', ignore=shutil.ignore_patterns('__pycache__', '*.pyc', 'findit_root'))
        self.root = self.base / 'FindIt with spaces'
        self.root.mkdir()
        self.bin = self.base / 'bin'
        self.bin.mkdir()
        uv = self.bin / 'uv'
        uv.write_text('#!/bin/sh\n[ "${FAIL_PREFLIGHT:-0}" = 0 ]\n')
        uv.chmod(0o755)
        self.config = self.base / 'claude config'
        self.env = dict(os.environ, FINDIT_ROOT=str(self.root), CLAUDE_CONFIG_DIR=str(self.config),
                        PATH=str(self.bin) + os.pathsep + os.environ['PATH'])
        self.dest = self.config / 'skills' / 'findit'

    def tearDown(self):
        self.tmp.cleanup()

    def install(self, *args):
        return subprocess.run(['bash', str(self.repo / 'install.sh'), *args],
                              env=self.env, capture_output=True, text=True, timeout=30)

    def test_symlink_install_is_repeatable_and_saves_root(self):
        first, second = self.install(), self.install()
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertTrue(self.dest.is_symlink())
        self.assertEqual((self.dest / 'findit_root').read_text().strip(), str(self.root))
        self.assertTrue((self.dest / 'scripts' / 'findit_notes.py').is_file())

    def test_copy_contains_helpers_and_does_not_overwrite_existing_install(self):
        result = self.install('--copy')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.dest.is_symlink())
        self.assertTrue((self.dest / 'scripts' / 'findit_notes.py').is_file())
        sentinel = self.dest / 'user-file'
        sentinel.write_text('keep')
        self.assertNotEqual(self.install('--copy').returncode, 0)
        self.assertEqual(sentinel.read_text(), 'keep')

    def test_failed_preflight_leaves_no_install(self):
        self.env['FAIL_PREFLIGHT'] = '1'
        self.assertNotEqual(self.install().returncode, 0)
        self.assertFalse(self.dest.exists())
        self.assertFalse((self.repo / 'skills' / 'findit' / 'findit_root').exists())

    def test_wrapper_uses_saved_root_and_disables_bytecode(self):
        self.assertEqual(self.install().returncode, 0)
        uv = self.bin / 'uv'
        uv.write_text('#!/bin/sh\nprintf "%s\\n" "$FINDIT_ROOT" "$PYTHONDONTWRITEBYTECODE" "$@"\n')
        env = dict(self.env)
        del env['FINDIT_ROOT']
        result = subprocess.run([str(self.dest / 'scripts' / 'findit'), 'release'], env=env,
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0)
        lines = result.stdout.splitlines()
        self.assertEqual(lines[:2], [str(self.root), '1'])
        self.assertIn('--no-sync', lines)
        self.assertEqual(lines[-1], 'release')
