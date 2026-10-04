import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().with_name('sync-upstream.sh')


class SyncTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='pstack sync tests ')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.upstream = self.root / 'upstream'
        self.origin = self.root / 'origin.git'
        self.checkout = self.root / 'checkout'
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        self.log = self.root / 'calls.jsonl'
        self.command('git', 'init', '-b', 'main', str(self.upstream))
        self.identity(self.upstream)
        (self.upstream / 'source.txt').write_text('upstream base\n')
        self.git(self.upstream, 'add', '.')
        self.git(self.upstream, 'commit', '-m', 'upstream base')
        base = self.git(self.upstream, 'rev-parse', 'HEAD').strip()
        self.command('git', 'clone', '--bare', str(self.upstream), str(self.origin))
        self.clone(self.checkout)
        pin = self.checkout / 'tools/portable/upstream.json'
        pin.parent.mkdir(parents=True)
        pin.write_text(json.dumps({'repository': str(self.upstream), 'branch': 'main', 'last_merged_sha': base}))
        self.git(self.checkout, 'add', '.')
        self.git(self.checkout, 'commit', '-m', 'fork tooling')
        self.git(self.checkout, 'push', 'origin', 'main')
        (self.upstream / 'source.txt').write_text('upstream incoming\n')
        self.git(self.upstream, 'add', '.')
        self.git(self.upstream, 'commit', '-m', 'upstream incoming')
        self.incoming = self.git(self.upstream, 'rev-parse', 'HEAD').strip()
        logger = """import json, os, sys
from pathlib import Path
with open(os.environ['SYNC_TEST_LOG'], 'a') as stream:
    stream.write(json.dumps({'tool': Path(sys.argv[0]).name, 'args': sys.argv[1:], 'cwd': os.getcwd()}) + '\\n')
"""
        self.wrapper('gh', logger + """
if sys.argv[1:3] == ['repo', 'view']:
    print('main')
elif sys.argv[1:3] == ['pr', 'list']:
    print(os.environ.get('OPEN_SYNC_PR', ''))
elif sys.argv[1:3] == ['pr', 'create']:
    if os.environ.get('FAIL_PR_CREATE') == '1':
        sys.exit('simulated PR creation failure')
    print('Created test PR')
else:
    sys.exit('unexpected gh command')
""")
        self.wrapper('python3', logger + f"""
if sys.argv[1] in ('-c', '-'):
    os.execv({sys.executable!r}, [{sys.executable!r}, *sys.argv[1:]])
if os.environ.get('FAIL_STEP') == sys.argv[1]:
    sys.exit('simulated check failure')
""")
        self.wrapper('npx', logger)
        self.environment = os.environ.copy()
        for name in ('GIT_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE', 'GIT_COMMON_DIR', 'PYTHONOPTIMIZE'):
            self.environment.pop(name, None)
        self.environment.update(PATH=str(self.bin) + os.pathsep + os.environ['PATH'],
                                GH_REPO='test/fork', SYNC_TEST_LOG=str(self.log),
                                GIT_AUTHOR_DATE='2026-01-01T00:00:00+0000',
                                GIT_COMMITTER_DATE='2026-01-01T00:00:00+0000')

    @staticmethod
    def command(*args, cwd=None, env=None, check=True):
        return subprocess.run(args, cwd=cwd, env=env, text=True, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, check=check)

    def git(self, directory, *args):
        return self.command('git', *args, cwd=directory).stdout

    def identity(self, directory):
        for key, value in [('user.name', 'Test'), ('user.email', 'test@example.invalid'), ('commit.gpgsign', 'false')]:
            self.git(directory, 'config', key, value)

    def clone(self, destination):
        self.command('git', 'clone', str(self.origin), str(destination))
        self.identity(destination)

    def wrapper(self, name, body):
        path = self.bin / name
        path.write_text(f'#!{sys.executable}\n' + body)
        path.chmod(0o755)

    def sync(self, checkout=None, **environment):
        return self.command('bash', str(SCRIPT), cwd=checkout or self.checkout,
                        env=self.environment | environment, check=False)

    def branches(self):
        return dict(line.split() for line in self.git(self.origin, 'for-each-ref',
                    '--format=%(refname:short) %(objectname)', 'refs/heads/sync/').splitlines())

    def calls(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()]

    def assert_temporary_installs_removed(self):
        installs = [call for call in self.calls() if call['tool'] == 'npx']
        self.assertTrue(installs)
        for install in installs:
            self.assertFalse(Path(install['cwd']).exists(), install)
            self.assertTrue(install['args'][3].endswith('/portable/pstack'), install)

    def test_closed_pr_retry_uses_new_branch_without_overwriting_previous(self):
        first = self.sync()
        self.assertEqual(first.returncode, 0, first.stdout)
        previous = self.branches()
        self.assertEqual(len(previous), 1)
        retry = self.root / 'fresh retry'
        self.clone(retry)
        second = self.sync(retry, GIT_AUTHOR_DATE='2026-01-02T00:00:00+0000',
                           GIT_COMMITTER_DATE='2026-01-02T00:00:00+0000')
        self.assertEqual(second.returncode, 0, second.stdout)
        current = self.branches()
        self.assertEqual(len(current), 2)
        for branch, commit in previous.items():
            self.assertEqual(current[branch], commit)
        for call in self.calls():
            if call['tool'] == 'gh' and call['args'][:2] == ['pr', 'create']:
                self.assertIn('--draft', call['args'])
        self.assert_temporary_installs_removed()

    def test_pr_creation_failure_can_retry_after_successful_push(self):
        first = self.sync(FAIL_PR_CREATE='1')
        self.assertNotEqual(first.returncode, 0)
        self.assertIn('simulated PR creation failure', first.stdout)
        previous = self.branches()
        self.assertEqual(len(previous), 1)
        self.assert_temporary_installs_removed()
        retry = self.root / 'fresh retry'
        self.clone(retry)
        second = self.sync(retry)
        self.assertEqual(second.returncode, 0, second.stdout)
        current = self.branches()
        self.assertEqual(len(current), 2)
        for branch, commit in previous.items():
            self.assertEqual(current[branch], commit)

    def test_open_pr_gate_leaves_checkout_unchanged(self):
        before = self.git(self.checkout, 'rev-parse', 'HEAD')
        result = self.sync(OPEN_SYNC_PR='sync/pstack-upstream-existing')
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn('already open', result.stdout)
        self.assertEqual(self.git(self.checkout, 'rev-parse', 'HEAD'), before)
        self.assertEqual(self.git(self.checkout, 'branch', '--show-current').strip(), 'main')
        self.assertEqual(self.branches(), {})
        self.assertFalse(any(call['tool'] == 'npx' for call in self.calls()))

    def test_install_validation_failure_does_not_push_and_cleans_temp(self):
        result = self.sync(FAIL_STEP='tools/portable/check-install.py')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('simulated check failure', result.stdout)
        self.assertEqual(self.branches(), {})
        self.assertFalse(any(call['args'][:2] == ['pr', 'create'] for call in self.calls()))
        self.assert_temporary_installs_removed()

    def test_merge_conflict_never_pushes_or_runs_install(self):
        (self.checkout / 'source.txt').write_text('conflicting fork edit\n')
        self.git(self.checkout, 'add', '.')
        self.git(self.checkout, 'commit', '-m', 'fork conflicting edit')
        self.git(self.checkout, 'push', 'origin', 'main')
        result = self.sync()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('no changes were pushed', result.stdout)
        self.assertEqual(self.branches(), {})
        self.assertFalse(any(call['tool'] == 'npx' for call in self.calls()))

    def test_dirty_checkout_is_rejected_before_service_calls(self):
        (self.checkout / 'untracked.txt').write_text('keep this work')
        result = self.sync()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('clean isolated checkout', result.stdout)
        self.assertFalse(self.log.exists())
        self.assertEqual((self.checkout / 'untracked.txt').read_text(), 'keep this work')


if __name__ == '__main__':
    unittest.main()
