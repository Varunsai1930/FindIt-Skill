"""Install in temporary homes; never touch the user's installed skill or FindIt."""
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


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
                              env=self.env, cwd=self.base, capture_output=True, text=True, timeout=30)

    def test_rejected_destination_does_not_change_saved_root(self):
        self.dest.mkdir(parents=True)
        saved = self.repo / 'skills' / 'findit' / 'findit_root'
        for previous in (None, '/previous/FindIt\n'):
            with self.subTest(previous=previous):
                saved.unlink(missing_ok=True)
                if previous is not None:
                    saved.write_text(previous)
                result = self.install()
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertIn('already exists', result.stderr)
                if previous is None:
                    self.assertFalse(saved.exists())
                else:
                    self.assertEqual(saved.read_text(), previous)

    def test_repeat_link_can_update_saved_root(self):
        self.assertEqual(self.install().returncode, 0)
        other = self.base / 'another FindIt'
        other.mkdir()
        self.env['FINDIT_ROOT'] = str(other)
        result = self.install()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.dest.is_symlink())
        self.assertEqual((self.dest / 'findit_root').read_text().strip(), str(other))

    def test_install_defaults_to_sibling_checkout_from_another_directory(self):
        adjacent = self.base / 'Find_v2'
        adjacent.mkdir()
        self.env.pop('FINDIT_ROOT')
        result = self.install()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.dest / 'findit_root').read_text().strip(), str(adjacent))

    def test_unconfigured_wrapper_defaults_to_sibling_checkout(self):
        adjacent = self.base / 'Find_v2'
        adjacent.mkdir()
        self.env.pop('FINDIT_ROOT')
        (self.bin / 'uv').write_text('#!/bin/sh\nprintf "%s\\n" "$FINDIT_ROOT"\n')
        script = self.repo / 'skills' / 'findit' / 'scripts' / 'findit'
        result = subprocess.run([str(script), 'release'], env=self.env, cwd=self.base,
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), str(adjacent))

    def test_copied_wrapper_uses_saved_root(self):
        self.assertEqual(self.install('--copy').returncode, 0)
        self.env.pop('FINDIT_ROOT')
        (self.bin / 'uv').write_text('#!/bin/sh\nprintf "%s\\n" "$FINDIT_ROOT"\n')
        result = subprocess.run([str(self.dest / 'scripts' / 'findit'), 'release'], env=self.env,
                                cwd=self.base, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), str(self.root))

    def test_help_does_not_require_findit_or_create_an_install(self):
        self.env['FINDIT_ROOT'] = str(self.base / 'missing FindIt')
        for option in ('--help', '-h'):
            with self.subTest(option=option):
                result = self.install(option)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn('Install the findit skill', result.stdout)
                self.assertEqual(result.stderr, '')
                self.assertFalse(self.config.exists())
                self.assertFalse((self.repo / 'skills' / 'findit' / 'findit_root').exists())

    def test_unknown_argument_is_reported_before_findit_validation(self):
        self.env['FINDIT_ROOT'] = str(self.base / 'missing FindIt')
        result = self.install('--unknown')
        self.assertEqual(result.returncode, 2)
        self.assertIn('Unknown argument: --unknown', result.stderr)
        self.assertFalse(self.config.exists())
        self.assertFalse((self.repo / 'skills' / 'findit' / 'findit_root').exists())

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

    def test_wrapper_prefers_the_existing_project_interpreter(self):
        self.assertEqual(self.install().returncode, 0)
        python = self.root / '.venv' / 'bin' / 'python'
        python.parent.mkdir(parents=True)
        python.write_text('#!/bin/sh\nprintf "%s\\n" "$FINDIT_ROOT" "$PYTHONDONTWRITEBYTECODE" "$@"\n')
        python.chmod(0o755)
        (self.bin / 'uv').write_text('#!/bin/sh\nexit 79\n')
        env = dict(self.env, PYTHONDONTWRITEBYTECODE='0')
        result = subprocess.run([str(self.dest / 'scripts' / 'findit'), 'release'], env=env,
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines(),
                         [str(self.root), '1', str((self.dest / 'scripts' / 'findit_query.py').resolve()), 'release'])

    def test_uv_fallback_avoids_the_default_user_cache(self):
        self.assertEqual(self.install().returncode, 0)
        (self.bin / 'uv').write_text('#!/bin/sh\nprintf "%s\\n" "$@"\n')
        env = dict(self.env)
        for key in ('UV_CACHE_DIR', 'UV_NO_CACHE'):
            env.pop(key, None)
        result = subprocess.run([str(self.dest / 'scripts' / 'findit'), 'release'], env=env,
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('--no-cache', result.stdout.splitlines())
        self.assertIn('--no-sync', result.stdout.splitlines())

    def test_uv_fallback_preserves_explicit_cache_settings(self):
        self.assertEqual(self.install().returncode, 0)
        (self.bin / 'uv').write_text('#!/bin/sh\nprintf "%s\\n" "${UV_CACHE_DIR:-}" "${UV_NO_CACHE:-}" "$@"\n')
        for override in ({'UV_CACHE_DIR': str(self.base / 'chosen cache')}, {'UV_NO_CACHE': 'false'}):
            with self.subTest(override=override):
                env = dict(self.env)
                for key in ('UV_CACHE_DIR', 'UV_NO_CACHE'):
                    env.pop(key, None)
                env.update(override)
                result = subprocess.run([str(self.dest / 'scripts' / 'findit'), 'release'], env=env,
                                        capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.splitlines()[:2],
                                 [override.get('UV_CACHE_DIR', ''), override.get('UV_NO_CACHE', '')])
                self.assertNotIn('--no-cache', result.stdout.splitlines())

    def test_wrapper_propagates_failures_without_running_the_helper_twice(self):
        self.assertEqual(self.install().returncode, 0)
        script = '#!/bin/sh\nprintf "called\\n" >> "$FINDIT_TEST_LOG"\nexit 23\n'
        log = self.base / 'calls'
        env = dict(self.env, FINDIT_TEST_LOG=str(log))
        for runner in (self.bin / 'uv', self.root / '.venv' / 'bin' / 'python'):
            with self.subTest(runner=runner):
                runner.parent.mkdir(parents=True, exist_ok=True)
                runner.write_text(script)
                runner.chmod(0o755)
                log.write_text('')
                result = subprocess.run([str(self.dest / 'scripts' / 'findit'), 'release'], env=env,
                                        capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, 23, result.stderr)
                self.assertEqual(log.read_text().splitlines(), ['called'])
