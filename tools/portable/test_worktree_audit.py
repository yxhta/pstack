import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).parent / 'assets/skills/poteto-mode/scripts/portable-worktree-audit.py'


class WorktreeAuditTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='portable audit ')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.repo = self.root / 'repo with spaces'
        self.env = {key: value for key, value in os.environ.items() if not key.startswith('GIT_')}
        self.env.update(HOME=str(self.root), XDG_CONFIG_HOME=str(self.root / '.config'),
                        LC_ALL='C')
        real_git = shutil.which('git', path=self.env.get('PATH'))
        self.assertIsNotNone(real_git, 'Git is required for the audit fixtures')
        self.real_git = str(Path(real_git).resolve())
        self.system_config = self.root / 'system.gitconfig'
        self.system_config.write_text('')
        self.env = self.git_wrapper('')
        self.git('init', '-b', 'trunk', str(self.repo), cwd=self.root)
        self.git('config', 'user.name', 'Audit Test')
        self.git('config', 'user.email', 'audit@example.invalid')
        self.git('config', 'commit.gpgsign', 'false')
        (self.repo / 'tracked').write_text('original\n')
        self.git('add', 'tracked')
        self.git('commit', '-m', 'Initial commit')
        self.head = self.git('rev-parse', 'HEAD').strip()

    def git(self, *args, cwd=None):
        result = subprocess.run(['git', *args], cwd=cwd or self.repo, env=self.env,
                                text=True, capture_output=True, check=True)
        return result.stdout

    def worktree(self, name, *options):
        path = self.root / name
        self.git('worktree', 'add', *options, str(path), 'trunk')
        return path

    def invoke(self, *args, code=0, env=None, cwd=None):
        result = subprocess.run([sys.executable, str(SCRIPT), *map(str, args)],
                                cwd=cwd or self.repo, env=env or self.env,
                                text=True, capture_output=True, timeout=15)
        self.assertEqual(result.returncode, code, result.stderr + result.stdout)
        self.assertEqual(result.stderr, '')
        report = json.loads(result.stdout)
        for row in report['worktrees']:
            self.assertEqual(row['usage'], 'unknown')
            self.assertIn(row['disposition'], ('hold-dirty', 'hold-locked',
                                              'hold-unknown-usage', 'audit-error'))
        return report

    def row(self, report, path):
        return next(row for row in report['worktrees'] if row['path'] == str(path))

    def test_clean_merged_paths_spaces_newlines_and_detached_are_held(self):
        linked = self.worktree('linked with spaces\nand newline\n', '-b', 'merged')
        detached = self.worktree('detached', '--detach')
        report = self.invoke('--repo', self.repo, '--base', 'trunk')
        self.assertEqual(report['base'], {'ref': 'trunk', 'head': self.head,
                                         'source': 'explicit', 'local_only': True})
        self.assertEqual(len(report['worktrees']), 3)
        for path in (self.repo, linked, detached):
            row = self.row(report, path)
            self.assertEqual(row['head'], self.head)
            self.assertEqual(row['tracked_changes'], 0)
            self.assertEqual(row['untracked_files'], 0)
            self.assertIs(row['contained_in_base'], True)
            self.assertEqual(row['disposition'], 'hold-unknown-usage')
            self.assertEqual(row['errors'], [])
        self.assertEqual(self.row(report, linked)['branch'], 'refs/heads/merged')
        self.assertEqual(self.row(report, detached)['branch'], None)
        self.assertIs(self.row(report, detached)['detached'], True)

    def test_dirty_counts_include_untracked_files_and_one_record_per_rename(self):
        (self.repo / 'rename old\nname').write_text('rename me\n')
        self.git('add', '.')
        self.git('commit', '-m', 'Rename source')
        self.git('mv', 'rename old\nname', 'renamed new\nname')
        (self.repo / 'tracked').write_text('modified\n')
        (self.repo / 'untracked\nfile').write_text('scratch')
        (self.repo / 'new folder').mkdir()
        (self.repo / 'new folder' / 'one').write_text('one')
        (self.repo / 'new folder' / 'two').write_text('two')
        report = self.invoke(self.repo, '--base', 'trunk')
        row = self.row(report, self.repo)
        self.assertEqual((row['tracked_changes'], row['untracked_files']), (2, 3))
        self.assertEqual(row['disposition'], 'hold-dirty')

    def test_untracked_only_worktree_is_held_dirty(self):
        (self.repo / 'scratch').write_text('scratch')
        row = self.row(self.invoke('--base', 'trunk'), self.repo)
        self.assertEqual((row['tracked_changes'], row['untracked_files']), (0, 1))
        self.assertEqual(row['disposition'], 'hold-dirty')

    def test_locked_reason_is_preserved(self):
        locked = self.worktree('locked worktree', '-b', 'locked')
        reason = 'keep for review\nincluding this line'
        self.git('worktree', 'lock', '--reason', reason, str(locked))
        row = self.row(self.invoke('--base', 'trunk'), locked)
        self.assertIs(row['locked'], True)
        self.assertEqual(row['lock_reason'], reason)
        self.assertEqual(row['disposition'], 'hold-locked')

    def test_missing_prunable_worktree_has_unknown_counts_and_error(self):
        missing = self.worktree('missing worktree', '-b', 'missing')
        shutil.rmtree(missing)
        row = self.row(self.invoke('--base', 'trunk', code=1), missing)
        self.assertIs(row['prunable'], True)
        self.assertIn('gitdir', row['prune_reason'])
        self.assertIsNone(row['tracked_changes'])
        self.assertIsNone(row['untracked_files'])
        self.assertIsNone(row['contained_in_base'])
        self.assertEqual(row['disposition'], 'audit-error')
        self.assertIn('Cannot inspect directory', row['errors'][0])

    def test_discovers_local_origin_head_without_assuming_main(self):
        self.git('update-ref', 'refs/remotes/origin/release', self.head)
        self.git('symbolic-ref', 'refs/remotes/origin/HEAD', 'refs/remotes/origin/release')
        self.git('remote', 'add', 'origin', 'https://example.invalid/must-not-fetch')
        report = self.invoke(self.repo)
        self.assertEqual(report['base'], {'ref': 'refs/remotes/origin/release',
                                         'head': self.head, 'source': 'origin/HEAD', 'local_only': True})
        self.assertEqual(self.row(report, self.repo)['disposition'], 'hold-unknown-usage')

    def test_missing_discovered_or_explicit_base_fails_closed(self):
        for options in ((), ('--base', 'missing'), ('--base=-not-an-option',)):
            with self.subTest(options=options):
                report = self.invoke(*options, code=1)
                self.assertIsNone(report['base']['head'])
                self.assertEqual(len(report['errors']), 1)
                row = self.row(report, self.repo)
                self.assertEqual((row['tracked_changes'], row['untracked_files']), (0, 0))
                self.assertIsNone(row['contained_in_base'])
                self.assertEqual(row['disposition'], 'audit-error')
                self.assertIn('Base containment unavailable', row['errors'][0])
        self.assertIn('pass --base explicitly', self.invoke(code=1)['errors'][0])

    def test_diverged_head_is_not_contained_and_still_has_unknown_usage(self):
        linked = self.worktree('unmerged', '-b', 'unmerged')
        (linked / 'new tracked').write_text('commit')
        self.git('add', '.', cwd=linked)
        self.git('commit', '-m', 'Unmerged work', cwd=linked)
        row = self.row(self.invoke('--base', 'trunk'), linked)
        self.assertIs(row['contained_in_base'], False)
        self.assertEqual(row['disposition'], 'hold-unknown-usage')

    def test_unborn_repository_is_reported_without_a_traceback(self):
        unborn = self.root / 'unborn'
        self.git('init', '-b', 'new-branch', str(unborn))
        report = self.invoke('--repo', unborn, '--base', 'new-branch', code=1)
        row = self.row(report, unborn)
        self.assertEqual(row['branch'], 'refs/heads/new-branch')
        self.assertIsNone(row['head'])
        self.assertIsNone(row['tracked_changes'])
        self.assertEqual(row['disposition'], 'audit-error')
        self.assertTrue(any('possibly unborn' in error for error in row['errors']))

    def test_worktree_symlink_and_symlink_parent_are_not_followed(self):
        linked = self.worktree('link target', '-b', 'linked')
        destination = self.root / 'moved worktree'
        linked.rename(destination)
        linked.symlink_to(destination, target_is_directory=True)
        row = self.row(self.invoke('--base', 'trunk', code=1), linked)
        self.assertIn('Refusing symlink directory', row['errors'][0])
        self.assertIsNone(row['tracked_changes'])
        alias = self.root / 'alias'
        alias.symlink_to(self.root, target_is_directory=True)
        report = self.invoke('--repo', alias / self.repo.name, '--base', 'trunk', code=1)
        self.assertEqual(report['worktrees'], [])
        self.assertIn('Refusing symlink directory', report['errors'][0])

    def test_symlink_git_metadata_is_not_followed(self):
        linked = self.worktree('metadata link', '-b', 'linked')
        saved = self.root / 'git-pointer'
        (linked / '.git').rename(saved)
        (linked / '.git').symlink_to(saved)
        row = self.row(self.invoke('--base', 'trunk', code=1), linked)
        self.assertIn('Refusing symlink Git metadata', row['errors'][0])
        self.assertIsNone(row['tracked_changes'])

    def git_wrapper(self, body):
        directory = Path(tempfile.mkdtemp(prefix='git bin ', dir=self.root))
        wrapper = directory / 'git'
        # Restore fixture isolation after the audit deliberately strips inherited GIT_*.
        wrapper.write_text(f'#!{sys.executable}\nimport os, sys, time\n{body}\n'
                           'os.environ.pop("GIT_CONFIG_NOSYSTEM", None)\n'
                           f'os.environ["GIT_CONFIG_SYSTEM"] = {str(self.system_config)!r}\n'
                           f'os.execv({self.real_git!r}, ["git", *sys.argv[1:]])\n')
        wrapper.chmod(0o755)
        return self.env | {'PATH': str(directory) + os.pathsep + self.env['PATH']}

    def test_command_failure_is_reported_not_clean(self):
        env = self.git_wrapper('if "status" in sys.argv:\n'
                               '    print("simulated status failure", file=sys.stderr)\n'
                               '    sys.exit(128)')
        report = self.invoke('--base', 'trunk', code=1, env=env)
        row = self.row(report, self.repo)
        self.assertIsNone(row['tracked_changes'])
        self.assertIsNone(row['untracked_files'])
        self.assertEqual(row['disposition'], 'audit-error')
        self.assertIn('simulated status failure', row['errors'][0])

    def test_missing_git_returns_json_error(self):
        report = self.invoke('--base', 'trunk', code=1, env=self.env | {'PATH': ''})
        self.assertEqual(report['worktrees'], [])
        self.assertIn('git worktree failed', report['errors'][0])

    def test_time_budget_and_worktree_limit_leave_explicit_errors(self):
        linked = self.worktree('over limit', '-b', 'linked')
        report = self.invoke('--base', 'trunk', '--max-worktrees', '1', code=1)
        self.assertEqual(self.row(report, self.repo)['disposition'], 'hold-unknown-usage')
        row = self.row(report, linked)
        self.assertEqual(row['disposition'], 'audit-error')
        self.assertIn('inspection limit', row['errors'][0])
        env = self.git_wrapper('if "status" in sys.argv:\n    time.sleep(2)')
        report = self.invoke('--base', 'trunk', '--timeout', '0.5', code=1, env=env)
        self.assertEqual(self.row(report, self.repo)['disposition'], 'audit-error')
        self.assertIsNone(self.row(report, self.repo)['tracked_changes'])
        self.assertTrue(any('timed out' in error for error in self.row(report, self.repo)['errors']))
        self.assertIn('budget exhausted', self.row(report, linked)['errors'][0])

    def test_audit_does_not_refresh_indexes_or_modify_repository_metadata(self):
        linked = self.worktree('read only', '-b', 'linked')
        (self.repo / 'tracked').write_text('original\n')
        (linked / 'tracked').write_text('original\n')
        def metadata():
            return {str(path.relative_to(self.repo)): (path.read_bytes(), path.stat().st_mtime_ns)
                    for path in (self.repo / '.git').rglob('*') if path.is_file()}
        before = metadata()
        env = self.git_wrapper('assert os.environ["GIT_OPTIONAL_LOCKS"] == "0"\n'
                               'assert os.environ["GIT_NO_LAZY_FETCH"] == "1"\n'
                               'assert not {"fetch", "prune", "remove"}.intersection(sys.argv)\n'
                               'assert "config" not in sys.argv or "--get-regexp" in sys.argv')
        report = self.invoke('--base', 'trunk', env=env)
        self.assertEqual(self.row(report, linked)['disposition'], 'hold-unknown-usage')
        self.assertEqual(metadata(), before)

    def test_environment_cannot_redirect_repository_or_enable_fsmonitor(self):
        env = self.env | {'GIT_DIR': str(self.root / 'nonexistent'),
                          'GIT_WORK_TREE': str(self.root / 'nonexistent'),
                          'GIT_INDEX_FILE': str(self.root / 'unwanted-index')}
        hook = self.root / 'fsmonitor'
        marker = self.root / 'fsmonitor-ran'
        hook.write_text(f'#!{sys.executable}\nfrom pathlib import Path\nPath({str(marker)!r}).touch()\n')
        hook.chmod(0o755)
        self.git('config', 'core.fsmonitor', shlex.quote(str(hook)))
        self.git('status', '--porcelain')
        self.assertTrue(marker.exists(), 'Fixture must demonstrate the fsmonitor can execute')
        marker.unlink()
        row = self.row(self.invoke('--base', 'trunk', env=env), self.repo)
        self.assertEqual((row['tracked_changes'], row['untracked_files']), (0, 0))
        self.assertEqual(row['disposition'], 'hold-unknown-usage')
        self.assertFalse(marker.exists())
        self.assertFalse((self.root / 'unwanted-index').exists())

    def test_clean_and_process_filters_are_rejected_before_they_can_execute(self):
        self.assert_filters_rejected()

    def test_system_clean_and_process_filters_are_rejected_before_they_can_execute(self):
        self.assert_filters_rejected('--file', str(self.system_config))

    def assert_filters_rejected(self, *config_options):
        marker = self.root / 'filter-ran'
        executable = self.root / 'unsafe-filter'
        executable.write_text(f'#!{sys.executable}\nfrom pathlib import Path\n'
                              f'Path({str(marker)!r}).touch()\n')
        executable.chmod(0o755)
        (self.repo / '.gitattributes').write_text('tracked filter=audit\n')
        (self.repo / 'tracked').write_text('changed!\n')
        for kind in ('clean', 'process'):
            with self.subTest(kind=kind):
                self.git('config', *config_options, 'filter.audit.' + kind,
                         shlex.quote(str(executable)))
                row = self.row(self.invoke('--base', 'trunk', code=1), self.repo)
                self.assertEqual(row['disposition'], 'audit-error')
                self.assertIsNone(row['tracked_changes'])
                self.assertIsNone(row['untracked_files'])
                self.assertIn('clean/process filters', row['errors'][0])
                self.assertFalse(marker.exists())
                subprocess.run(['git', 'status', '--porcelain'], cwd=self.repo, env=self.env,
                               capture_output=True, timeout=5)
                self.assertTrue(marker.exists(), 'Fixture must demonstrate the filter can execute')
                marker.unlink()
                self.git('config', *config_options, '--unset', 'filter.audit.' + kind)

    def test_submodule_filter_configuration_is_not_executed(self):
        source = self.root / 'submodule source'
        self.git('clone', '--no-local', str(self.repo), str(source))
        self.git('-c', 'protocol.file.allow=always', 'submodule', 'add', str(source), 'module')
        self.git('commit', '-am', 'Add submodule')
        module = self.repo / 'module'
        marker = self.root / 'submodule-filter-ran'
        executable = self.root / 'submodule-filter'
        executable.write_text(f'#!{sys.executable}\nfrom pathlib import Path\n'
                              f'Path({str(marker)!r}).touch()\n')
        executable.chmod(0o755)
        (module / '.gitattributes').write_text('tracked filter=audit\n')
        (module / 'tracked').write_text('changed!\n')
        self.git('config', 'filter.audit.clean', shlex.quote(str(executable)), cwd=module)
        row = self.row(self.invoke('--base', 'trunk', code=1), self.repo)
        self.assertEqual(row['disposition'], 'audit-error')
        self.assertIsNone(row['tracked_changes'])
        self.assertIn('Submodule status is unavailable', row['errors'][0])
        self.assertFalse(marker.exists())
        self.git('status', '--porcelain', '--ignore-submodules=none')
        self.assertTrue(marker.exists(), 'Fixture must demonstrate the nested filter can execute')

    def test_inherited_git_config_and_trace_settings_cannot_execute_or_write(self):
        marker = self.root / 'git-trace'
        env = self.git_wrapper('assert not any(key.startswith("GIT_CONFIG_") '
                               'for key in os.environ)')
        env.update(GIT_CONFIG_COUNT='1', GIT_CONFIG_KEY_0='core.fsmonitor',
                   GIT_CONFIG_VALUE_0='false', GIT_CONFIG_PARAMETERS='invalid config',
                   GIT_CONFIG_SYSTEM=str(self.root / 'untrusted-system-config'),
                   GIT_CONFIG_NOSYSTEM='1', GIT_TRACE=str(marker))
        row = self.row(self.invoke('--base', 'trunk', env=env), self.repo)
        self.assertEqual(row['disposition'], 'hold-unknown-usage')
        self.assertFalse(marker.exists())

    def test_global_trace2_targets_are_disabled_without_losing_global_config(self):
        targets = [self.root / (kind + '-trace') for kind in ('normal', 'event', 'perf')]
        excludes = self.root / 'global-excludes'
        excludes.write_text('ignored-scratch\n')
        (self.repo / 'ignored-scratch').write_text('ignored by the real global configuration\n')
        config = self.root / '.gitconfig'
        config.write_text('[trace2]\n' + ''.join(
            f'\t{kind}Target = "{target}"\n'
            for kind, target in zip(('normal', 'event', 'perf'), targets)) +
            f'[core]\n\texcludesFile = "{excludes}"\n')
        self.git('worktree', 'list', '--porcelain', '-z')
        for target in targets:
            self.assertGreater(target.stat().st_size, 0,
                               'Ordinary Git must demonstrate that this trace target writes')
            target.unlink()
        for existing in (False, True):
            with self.subTest(existing=existing):
                if existing:
                    for target in targets:
                        target.write_bytes(b'preserve existing trace\n')
                before = {target: (target.read_bytes(), target.stat().st_mtime_ns)
                          for target in targets if target.exists()}
                row = self.row(self.invoke('--base', 'trunk'), self.repo)
                self.assertEqual(row['disposition'], 'hold-unknown-usage')
                self.assertEqual(row['untracked_files'], 0,
                                 'Global excludes must remain active')
                after = {target: (target.read_bytes(), target.stat().st_mtime_ns)
                         for target in targets if target.exists()}
                self.assertEqual(after, before)
        with config.open('a') as stream:
            stream.write('[filter "global-audit"]\n\tclean = false\n')
        row = self.row(self.invoke('--base', 'trunk', code=1), self.repo)
        self.assertEqual(row['disposition'], 'audit-error')
        self.assertIsNone(row['tracked_changes'])
        self.assertIn('clean/process filters', row['errors'][0],
                      'Global filter configuration must still cause a fail-closed result')

    @unittest.skipIf(os.name == 'nt', 'Undecodable POSIX filename fixture')
    def test_non_utf8_worktree_path_survives_json(self):
        path = self.worktree(os.fsdecode(b'non-utf8-\xff'), '-b', 'bytes')
        row = self.row(self.invoke('--base', 'trunk'), path)
        self.assertEqual(os.fsencode(row['path']), os.fsencode(path))
        self.assertEqual(row['disposition'], 'hold-unknown-usage')

    def test_no_mutating_or_history_options_exist(self):
        for option in ('--delete', '--fetch', '--history', '--timeout=nan', '--max-worktrees=0'):
            result = subprocess.run([sys.executable, str(SCRIPT), option], env=self.env,
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertIn('error:', result.stderr)


if __name__ == '__main__':
    unittest.main()
