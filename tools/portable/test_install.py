import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'tools/portable/check-install.py'
spec = importlib.util.spec_from_file_location('check_install', SCRIPT)
check_install = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check_install)


class InstallTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='pstack install audit ')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / 'source'
        files = {
            'example/SKILL.md': '---\nname: example\ndescription: Example\n---\nBody\n',
            'example/run.sh': '#!/bin/sh\nexit 0\n',
            'poteto-mode/SKILL.md': '---\nname: poteto-mode\ndescription: Main\n---\nBody\n',
            'poteto-mode/references/runtime-adaptation.md': 'Runtime adaptation\n',
            'poteto-mode/references/portable-agents/poteto-agent.md': 'Agent\n',
            'poteto-mode/references/portable-agents/comment-sicko.md': 'Reviewer\n',
            'catalog.json': '{}\n',
        }
        for name, data in files.items():
            path = self.source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(data)
        (self.source / 'example/run.sh').chmod(0o755)
        self.project = self.root / 'project'
        for runtime in ('.claude', '.agents'):
            shutil.copytree(self.source, self.project / runtime / 'skills')

    def verify(self):
        return check_install.check_install(self.project, self.source)

    def test_complete_copy_and_top_level_resource_content(self):
        self.assertEqual(self.verify(), 2)
        path = self.project / '.agents/skills/catalog.json'
        path.write_text('broken catalog\n')
        with self.assertRaisesRegex(ValueError, 'catalog.json'):
            self.verify()

    def test_missing_extra_modified_and_mode_changed_files(self):
        root = self.project / '.claude/skills'
        path = root / 'example/run.sh'
        path.chmod(0o644)
        with self.assertRaisesRegex(ValueError, 'run.sh'):
            self.verify()
        path.chmod(0o755)
        path.unlink()
        with self.assertRaisesRegex(ValueError, 'missing='):
            self.verify()
        shutil.copy2(self.source / 'example/run.sh', path)
        (root / 'stale.md').write_text('stale')
        with self.assertRaisesRegex(ValueError, 'unexpected='):
            self.verify()

    def test_external_resource_and_directory_symlinks_rejected(self):
        root = self.project / '.claude/skills'
        path = root / 'example/run.sh'
        path.unlink()
        path.symlink_to(self.source / 'example/run.sh')
        with self.assertRaisesRegex(ValueError, 'symlink'):
            self.verify()
        path.unlink()
        shutil.copy2(self.source / 'example/run.sh', path)
        shutil.rmtree(root / 'example')
        (root / 'example').symlink_to(self.source / 'example', target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            self.verify()

    def test_missing_source_cannot_validate_an_empty_installation(self):
        with self.assertRaisesRegex(ValueError, 'real skills directory'):
            check_install.check_install(self.project, self.root / 'missing')
        empty = self.root / 'empty'
        empty.mkdir()
        with self.assertRaisesRegex(ValueError, 'No source skills'):
            check_install.check_install(self.project, empty)

    def test_optimized_cli_rejects_missing_or_tampered_install(self):
        project = self.root / 'real-package-project'
        for runtime in ('.claude', '.agents'):
            shutil.copytree(ROOT / 'portable/pstack/skills', project / runtime / 'skills')
        for optimization in (None, '1', '2'):
            env = os.environ.copy()
            env.pop('PYTHONOPTIMIZE', None)
            if optimization:
                env['PYTHONOPTIMIZE'] = optimization
            with self.subTest(optimization=optimization):
                for target in (self.root / 'nonexistent', project):
                    if target == project:
                        path = project / '.agents/skills/poteto-mode/SKILL.md'
                        original = path.read_bytes()
                        path.write_bytes(original + b'\nTAMPERED\n')
                    result = subprocess.run([sys.executable, str(SCRIPT), str(target)], env=env,
                                            text=True, capture_output=True)
                    self.assertNotEqual(result.returncode, 0, result.stdout)
                    if target == project:
                        self.assertIn('poteto-mode/SKILL.md', result.stderr)
                        path.write_bytes(original)
                result = subprocess.run([sys.executable, str(SCRIPT), str(project)], env=env,
                                        text=True, capture_output=True)
                self.assertEqual(result.returncode, 0, result.stderr)


class ValidatorTests(unittest.TestCase):
    def test_marketplace_validation_survives_python_optimization(self):
        with tempfile.TemporaryDirectory(prefix='pstack validator ') as temporary:
            root = Path(temporary)
            files = {
                'portable/pstack/.claude-plugin/plugin.json': {'name': 'pstack', 'skills': './skills', 'version': '1', 'agents': []},
                'portable/pstack/.codex-plugin/plugin.json': {'name': 'pstack', 'skills': './skills', 'version': '1'},
                '.claude-plugin/marketplace.json': {'plugins': [{'source': './pstack'}]},
                '.agents/plugins/marketplace.json': {'plugins': [{'source': {'path': './portable/pstack'}}]},
                'tools/portable/upstream.json': {'last_merged_sha': 'a' * 40},
            }
            for name, data in files.items():
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(data))
            code = (
                'from pathlib import Path; from unittest.mock import patch; import validate; '
                f'validate.ROOT = Path({str(root)!r}); '
                'validate.validate_resources = lambda *args: None; '
                'patch("validate.subprocess.run").start(); validate.main()'
            )
            for optimization in ('0', '1', '2'):
                with self.subTest(optimization=optimization):
                    env = os.environ | {'PYTHONOPTIMIZE': optimization}
                    result = subprocess.run([sys.executable, '-c', code], cwd=SCRIPT.parent,
                                            env=env, text=True, capture_output=True)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn('Claude marketplace must point to the portable package', result.stderr)


if __name__ == '__main__':
    unittest.main()
