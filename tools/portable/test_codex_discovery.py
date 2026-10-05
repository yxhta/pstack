import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).with_name('check-codex-discovery.py')
spec = importlib.util.spec_from_file_location('codex_discovery', SCRIPT)
discovery = importlib.util.module_from_spec(spec)
spec.loader.exec_module(discovery)


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='thermos discovery tests ')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.project = self.root / 'project'
        self.project.mkdir()
        self.fake = self.root / 'fake_app_server.py'
        self.log = self.root / 'requests.jsonl'
        self.response = {'data': [{'cwd': str(self.project), 'skills': [
            {'name': name, 'path': str(self.project / name / 'SKILL.md'), 'enabled': True, 'pluginId': None}
            for name in sorted(discovery.ROLES)
        ], 'errors': []}]}
        self.popen = subprocess.Popen

    def server(self):
        self.fake.write_text(f'''import json, sys
from pathlib import Path
for line in sys.stdin:
    request = json.loads(line)
    with Path({str(self.log)!r}).open('a') as log:
        log.write(line)
    method = request['method']
    if method == 'initialize':
        result = {{'userAgent': 'test transport'}}
    elif method == 'initialized':
        continue
    elif method == 'skills/list':
        result = {self.response!r}
    else:
        sys.exit('Unexpected request: ' + method)
    print(json.dumps({{'id': request['id'], 'result': result}}), flush=True)
''')
        return patch.object(discovery.subprocess, 'Popen',
                            side_effect=lambda args, **kwargs: self.popen([sys.executable, str(self.fake)], **kwargs))

    def test_missing_directory_and_file_are_rejected_before_process_start(self):
        file = self.project / 'plain-file'
        file.write_text('not a directory')
        for path in (self.project / 'missing-child', file):
            with self.subTest(path=path), patch.object(discovery.subprocess, 'Popen') as process:
                with self.assertRaises((OSError, ValueError)):
                    discovery.check_discovery(path)
                process.assert_not_called()

    def test_only_discovery_requests_are_sent_and_all_entries_returned(self):
        with self.server():
            result = discovery.check_discovery(self.project)
        self.assertEqual({entry['name'] for entry in result}, discovery.ROLES)
        messages = [json.loads(line) for line in self.log.read_text().splitlines()]
        self.assertEqual([entry['method'] for entry in messages], ['initialize', 'initialized', 'skills/list'])
        self.assertEqual(messages[-1]['params'], {'cwds': [str(self.project)], 'forceReload': True})

    def test_plugin_names_are_distinct_from_project_names(self):
        for entry in self.response['data'][0]['skills']:
            entry['name'] = 'thermos:' + entry['name']
            entry['pluginId'] = 'thermos@yxhta-pstack'
        with self.server():
            result = discovery.check_discovery(self.project, plugin=True)
        self.assertEqual({entry['name'] for entry in result}, {'thermos:' + role for role in discovery.ROLES})
        with self.server(), self.assertRaisesRegex(ValueError, 'all three enabled'):
            discovery.check_discovery(self.project)

    def test_loader_errors_disabled_and_missing_entries_fail(self):
        self.response['data'][0]['errors'] = [{'message': 'bad skill'}]
        with self.server(), self.assertRaisesRegex(ValueError, 'loader errors'):
            discovery.check_discovery(self.project)
        self.response['data'][0]['errors'] = []
        self.response['data'][0]['skills'][0]['enabled'] = False
        with self.server(), self.assertRaisesRegex(ValueError, 'all three enabled'):
            discovery.check_discovery(self.project)
        self.response['data'][0]['skills'].pop(0)
        with self.server(), self.assertRaisesRegex(ValueError, 'all three enabled'):
            discovery.check_discovery(self.project)

    def test_request_has_a_deadline_independent_of_notifications(self):
        with self.server(), patch.object(discovery.time, 'monotonic', side_effect=[0, 31]):
            with self.assertRaisesRegex(TimeoutError, 'initialize within 30 seconds'):
                discovery.check_discovery(self.project)


if __name__ == '__main__':
    unittest.main()
