import types
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT / 'tools/portable/mods-assets/hooks/evidence.py'
evidence = types.ModuleType('mods_evidence')
exec(compile(HELPER.read_text(), str(HELPER), 'exec'), evidence.__dict__)


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='mods evidence ')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.env = {**os.environ, 'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': '/dev/null'}
        self.git('init', '-q')
        self.git('config', 'user.email', 'fixture@example.invalid')
        self.git('config', 'user.name', 'Fixture')
        self.write('code.py', 'value = 1\n')
        self.write('.gitignore', 'build/\n')
        self.git('add', '.')
        self.git('commit', '-qm', 'baseline')

    def git(self, *args):
        return subprocess.check_output(['git', *args], cwd=self.root, env=self.env)

    def write(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def snap(self):
        return evidence.snapshot(self.root)['digest']

    def test_snapshot_detects_content_even_with_preserved_size_and_mtime(self):
        before = self.snap()
        path = self.root / 'code.py'
        info = path.stat()
        path.write_text('value = 2\n')
        os.utime(path, ns=(info.st_atime_ns, info.st_mtime_ns))
        self.assertNotEqual(self.snap(), before)
        self.assertEqual(self.snap(), self.snap())

    def test_index_head_mode_deletion_and_untracked_invalidate(self):
        before = self.snap()
        self.write('new.py', 'new\n')
        untracked = self.snap()
        self.assertNotEqual(untracked, before)
        self.git('add', 'new.py')
        staged = self.snap()
        self.assertNotEqual(staged, untracked)
        self.git('commit', '-qm', 'new')
        committed = self.snap()
        self.assertNotEqual(committed, staged)
        (self.root / 'new.py').chmod(0o755)
        executable = self.snap()
        self.assertNotEqual(executable, committed)
        (self.root / 'new.py').unlink()
        self.assertNotEqual(self.snap(), executable)

    def test_ignored_outputs_do_not_mutate_code_evidence(self):
        before = self.snap()
        self.write('build/result.txt', 'test output')
        self.assertEqual(self.snap(), before)

    def test_symlink_is_not_followed(self):
        (self.root / 'linked.py').symlink_to(self.root / 'code.py')
        with self.assertRaisesRegex(ValueError, 'regular files'):
            self.snap()

    def test_snapshot_rejects_earlier_file_changed_while_later_file_is_hashed(self):
        self.write('z.py', 'other = 1\n')
        self.git('add', 'z.py')
        self.git('commit', '-qm', 'second file')
        original = evidence.hashlib.file_digest

        def change_earlier(stream, algorithm):
            if Path(stream.name).name == 'z.py':
                self.write('code.py', 'value = 2\n')
            return original(stream, algorithm)

        with patch.object(evidence.hashlib, 'file_digest', change_earlier):
            with self.assertRaisesRegex(ValueError, 'File changed during snapshot'):
                self.snap()

    def test_clean_flag_requires_committed_reproduction_fixture(self):
        self.assertTrue(evidence.snapshot(self.root)['clean'])
        self.write('repro.py', 'assert False\n')
        self.assertFalse(evidence.snapshot(self.root)['clean'])
        self.git('add', 'repro.py')
        self.assertFalse(evidence.snapshot(self.root)['clean'])
        self.git('commit', '-qm', 'failing reproduction')
        self.assertTrue(evidence.snapshot(self.root)['clean'])

    def test_argv_is_not_interpreted_as_a_shell_command(self):
        result = evidence.run(self.root, {'argv': [sys.executable, '-c', 'import sys; print(sys.argv[1])', '; touch injection'], 'timeoutMs': 1000})
        self.assertEqual(result['stdout'], '; touch injection\n')
        self.assertFalse((self.root / 'injection').exists())

    def test_hidden_index_flags_are_rejected(self):
        for flag in ('--assume-unchanged', '--skip-worktree'):
            with self.subTest(flag=flag):
                self.git('update-index', flag, 'code.py')
                self.write('code.py', 'value = 9\n')
                with self.assertRaisesRegex(ValueError, 'unsupported'):
                    self.snap()
                self.git('update-index', '--no-assume-unchanged', '--no-skip-worktree', 'code.py')

    def test_raw_clean_check_ignores_core_filemode_and_status_cache(self):
        self.git('config', 'core.filemode', 'false')
        (self.root / 'code.py').chmod(0o755)
        self.assertEqual(self.git('status', '--porcelain'), b'')
        self.assertFalse(evidence.snapshot(self.root)['clean'])

    def test_content_filter_attributes_block_snapshot(self):
        self.write('.gitattributes', '*.py filter=custom\n')
        with self.assertRaisesRegex(ValueError, 'content filters'):
            self.snap()

    def test_process_result_is_observed_and_repeated_commands_really_run(self):
        code = 'from pathlib import Path; p=Path("counter"); n=int(p.read_text()) if p.exists() else 0; p.write_text(str(n+1)); print("expected failure"); raise SystemExit(7)'
        request = {'argv': [sys.executable, '-c', code], 'timeoutMs': 1000}
        for count in (1, 2):
            result = evidence.run(self.root, request)
            self.assertEqual(result['exitCode'], 7)
            self.assertEqual(result['stdout'], 'expected failure\n')
            self.assertEqual((self.root / 'counter').read_text(), str(count))
            self.assertFalse(result['timedOut'])

    def test_signal_and_timeout_are_not_reproduction_failures(self):
        result = evidence.run(self.root, {'argv': [sys.executable, '-c', 'import os,signal; os.kill(os.getpid(), signal.SIGTERM)'], 'timeoutMs': 1000})
        self.assertEqual(result['exitCode'], -signal.SIGTERM)
        result = evidence.run(self.root, {'argv': [sys.executable, '-c', 'import time; time.sleep(20)'], 'timeoutMs': 1000})
        self.assertTrue(result['timedOut'])
        self.assertEqual(result['exitCode'], -signal.SIGKILL)

    def test_terminated_helper_reaps_its_foreground_process_group(self):
        code = 'from pathlib import Path; import time; Path("ready").write_text("yes"); time.sleep(1); Path("late").write_text("bad")'
        request = {'argv': [sys.executable, '-c', code], 'timeoutMs': 5000}
        helper = subprocess.Popen([sys.executable, str(HELPER), 'run', str(self.root), json.dumps(request)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            deadline = time.monotonic() + 3
            while not (self.root / 'ready').exists() and time.monotonic() < deadline:
                time.sleep(0.02)
            self.assertTrue((self.root / 'ready').exists())
            helper.terminate()
            stdout, stderr = helper.communicate(timeout=3)
            self.assertNotEqual(helper.returncode, 0)
            self.assertEqual(stdout, b'')
            self.assertIn(b'interrupted', stderr)
            time.sleep(1.1)
            self.assertFalse((self.root / 'late').exists())
        finally:
            if helper.poll() is None:
                helper.kill()
                helper.wait()

    def test_missing_program_and_malformed_request_do_not_create_results(self):
        with self.assertRaises(OSError):
            evidence.run(self.root, {'argv': ['/nonexistent-program'], 'timeoutMs': 1000})
        with self.assertRaises(ValueError):
            evidence.run(self.root, {'argv': 'echo yes', 'timeoutMs': 1000})

    def test_output_is_bounded_with_explicit_truncation(self):
        result = evidence.run(self.root, {'argv': [sys.executable, '-c', 'print("x"*100000)'], 'timeoutMs': 1000})
        self.assertEqual(len(result['stdout']), 65536)
        self.assertTrue(result['stdoutTruncated'])
        self.assertFalse(result['stderrTruncated'])

    def test_review_diff_honors_mode_changes_even_if_repo_ignores_them(self):
        base = self.git('rev-parse', 'HEAD').decode().strip()
        self.git('config', 'core.filemode', 'false')
        (self.root / 'code.py').chmod(0o755)
        value = json.loads(subprocess.check_output([sys.executable, str(HELPER), 'diff', str(self.root), base], env=self.env))
        self.assertEqual(value['files'], [str(self.root / 'code.py')])
        self.assertIn('new mode 100755', value['diff'])

    def test_review_diff_does_not_trust_git_stat_cache(self):
        self.write('readme', 'old note\n')
        self.git('add', 'readme')
        self.git('commit', '-qm', 'readme')
        self.git('config', 'core.trustctime', 'false')
        self.git('config', 'core.checkStat', 'minimal')
        path = self.root / 'code.py'
        old = time.time_ns() - 5_000_000_000
        os.utime(path, ns=(old, old))
        self.git('update-index', '--refresh')
        info = path.stat()
        base = self.git('rev-parse', 'HEAD').decode().strip()
        self.write('code.py', 'value = 2\n')
        os.utime(path, ns=(info.st_atime_ns, info.st_mtime_ns))
        self.write('readme', 'new note\n')
        self.assertNotIn(b'code.py', self.git('diff', '--name-only', base))
        result = evidence.review_diff(self.root, base)
        self.assertEqual(result['files'], [str(self.root / name) for name in ('code.py', 'readme')])
        self.assertIn('-value = 1', result['diff'])
        self.assertIn('+value = 2', result['diff'])

    def test_raw_review_diff_keeps_binary_deletion_and_mode_changes(self):
        self.write('binary.dat', b'old\x00data'.decode('latin1'))
        self.git('add', 'binary.dat')
        self.git('commit', '-qm', 'binary baseline')
        base = self.git('rev-parse', 'HEAD').decode().strip()
        (self.root / 'binary.dat').write_bytes(b'new\x00data')
        (self.root / 'code.py').unlink()
        (self.root / '.gitignore').chmod(0o755)
        result = evidence.review_diff(self.root, base)
        self.assertEqual(result['files'], [str(self.root / name) for name in ('.gitignore', 'binary.dat')])
        self.assertIn('GIT binary patch', result['diff'])
        self.assertIn('deleted file mode', result['diff'])
        self.assertIn('new mode 100755', result['diff'])

    def test_raw_review_diff_handles_rename_and_file_directory_replacements(self):
        base = self.git('rev-parse', 'HEAD').decode().strip()
        self.git('mv', 'code.py', 'renamed.py')
        (self.root / '.gitignore').unlink()
        self.write('.gitignore/nested', 'new directory\n')
        self.git('add', '-A')
        result = evidence.review_diff(self.root, base)
        self.assertEqual(result['files'], [str(self.root / name) for name in ('.gitignore/nested', 'renamed.py')])
        self.assertIn('a/code.py', result['diff'])
        self.assertIn('b/renamed.py', result['diff'])
        self.assertIn('b/.gitignore/nested', result['diff'])
        self.git('commit', '-qm', 'directory baseline')
        base = self.git('rev-parse', 'HEAD').decode().strip()
        (self.root / '.gitignore/nested').unlink()
        (self.root / '.gitignore').rmdir()
        self.write('.gitignore', 'restored file\n')
        self.git('add', '-A')
        result = evidence.review_diff(self.root, base)
        self.assertEqual(result['files'], [str(self.root / '.gitignore')])
        self.assertIn('a/.gitignore/nested', result['diff'])
        self.assertIn('b/.gitignore', result['diff'])

    def test_raw_review_diff_rejects_concurrent_code_change(self):
        base = self.git('rev-parse', 'HEAD').decode().strip()
        self.write('code.py', 'value = 2\n')
        original = evidence.subprocess.run

        def change_after_diff(command, *args, **kwargs):
            result = original(command, *args, **kwargs)
            if '--no-index' in command:
                self.write('code.py', 'value = 3\n')
            return result

        with patch.object(evidence.subprocess, 'run', change_after_diff):
            with self.assertRaisesRegex(ValueError, 'Code changed while preparing'):
                evidence.review_diff(self.root, base)

    def test_raw_review_diff_disables_configured_color(self):
        base = self.git('rev-parse', 'HEAD').decode().strip()
        self.write('code.py', 'value = 2\n')
        with patch.dict(os.environ, {'GIT_CONFIG_COUNT': '1', 'GIT_CONFIG_KEY_0': 'color.ui', 'GIT_CONFIG_VALUE_0': 'always'}):
            result = evidence.review_diff(self.root, base)
        self.assertNotIn('\x1b[', result['diff'])
        self.assertIn('+value = 2', result['diff'])

    def test_git_replace_cannot_change_the_recorded_review_baseline(self):
        self.write('readme', 'before\n')
        self.git('add', 'readme')
        self.git('commit', '-qm', 'original baseline')
        base = self.git('rev-parse', 'HEAD').decode().strip()
        self.write('code.py', 'value = 2\n')
        self.git('commit', '-qam', 'replacement tree')
        replacement = self.git('rev-parse', 'HEAD').decode().strip()
        self.git('reset', '--mixed', base)
        self.write('readme', 'after\n')
        before = self.snap()
        self.git('replace', base, replacement)
        self.assertEqual(self.snap(), before)
        result = evidence.review_diff(self.root, base)
        self.assertEqual(result['files'], [str(self.root / name) for name in ('code.py', 'readme')])
        self.assertIn('-value = 1', result['diff'])
        self.assertIn('+value = 2', result['diff'])

    def test_diff_covers_committed_staged_unstaged_and_untracked(self):
        base = self.git('rev-parse', 'HEAD').decode().strip()
        self.write('code.py', 'value = 2\n')
        self.git('commit', '-qam', 'fix')
        self.write('new.py', 'new\n')
        self.git('add', 'new.py')
        self.write('code.py', 'value = 3\n')
        self.write('untracked.py', 'other\n')
        result = subprocess.run([sys.executable, str(HELPER), 'diff', str(self.root), base], capture_output=True, text=True, check=True, env=self.env)
        value = json.loads(result.stdout)
        self.assertIn('+value = 3', value['diff'])
        self.assertEqual(value['files'], [str(self.root / name) for name in ('code.py', 'new.py', 'untracked.py')])
        self.assertEqual(value['untracked'], ['untracked.py'])

    def test_repro_then_fix_has_distinct_snapshot_and_actual_exit_evidence(self):
        self.write('repro.py', 'from code import value\nassert value == 2, "wrong value"\n')
        self.git('add', 'repro.py')
        before = self.snap()
        request = {'argv': [sys.executable, '-B', 'repro.py'], 'timeoutMs': 1000}
        failed = evidence.run(self.root, request)
        self.assertEqual(failed['exitCode'], 1)
        self.assertIn('AssertionError: wrong value', failed['stderr'])
        self.assertEqual(self.snap(), before)
        self.write('code.py', 'value = 2\n')
        after = self.snap()
        self.assertNotEqual(after, before)
        passed = evidence.run(self.root, request)
        self.assertEqual(passed['exitCode'], 0)
        self.assertEqual(passed['stderr'], '')
        self.assertEqual(self.snap(), after)
