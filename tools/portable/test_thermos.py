import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

import yaml

from prepare import (PackageLayout, THERMOS_NOTICE, frontmatter,
                     prepare_package, read_tree, render_package, verify_source)


ROOT = Path(__file__).resolve().parents[2]
PIN = json.loads((ROOT / 'tools/portable/upstream.json').read_text())['last_merged_sha']
ROLES = ('thermo-nuclear-review', 'thermo-nuclear-code-quality-review')
SKILLS = {'thermos', *ROLES}


class ThermosPackageTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='thermos package tests ')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / 'thermos'
        self.assets = self.root / 'tools/portable/thermos-assets'
        shutil.copytree(ROOT / 'thermos', self.source)
        shutil.copytree(ROOT / 'tools/portable/thermos-assets', self.assets)
        self.layout = PackageLayout(self.source, self.assets, self.root / 'portable/thermos')

    def generate(self, check=False):
        prepare_package(self.layout, PIN, check=check)

    @staticmethod
    def write(path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data if isinstance(data, bytes) else data.encode())
        return path

    def version(self):
        manifests = [json.loads((self.layout.published / f'.{host}-plugin/plugin.json').read_text())
                     for host in ('claude', 'codex')]
        self.assertEqual(manifests[0]['version'], manifests[1]['version'])
        return manifests[0]['version']

    def assert_rejected_without_changes(self, pattern):
        source, assets = read_tree(self.source), read_tree(self.assets)
        published = read_tree(self.layout.published)
        with self.assertRaisesRegex(ValueError, pattern):
            self.generate()
        self.assertEqual(read_tree(self.source), source)
        self.assertEqual(read_tree(self.assets), assets)
        self.assertEqual(read_tree(self.layout.published), published)

    def test_all_source_bytes_modes_and_inputs_are_preserved(self):
        for skill in SKILLS:
            path = self.source / f'skills/{skill}/SKILL.md'
            path.write_bytes(path.read_bytes() + '\n## New upstream section\n\n```text\nα <scope>\n```\n'.encode())
        executable = self.write(self.source / 'skills/thermos/references/inspect.sh', '#!/bin/sh\nexit 0\n')
        executable.chmod(0o755)
        self.write(self.source / 'skills/thermos/references/evidence.bin', b'\x00\xff\n')
        source, assets = read_tree(self.source), read_tree(self.assets)
        self.generate()
        generated = read_tree(self.layout.published)
        self.assertEqual({p.parent.name for p in self.layout.published.glob('skills/*/SKILL.md')}, SKILLS)
        for name, original in source.items():
            with self.subTest(file=name):
                actual = generated[name]
                if re.fullmatch(r'skills/[^/]+/SKILL.md', name):
                    self.assertEqual(actual.data.count(THERMOS_NOTICE.encode()), 1)
                    self.assertEqual(actual.data.replace(THERMOS_NOTICE.encode(), b'', 1), original.data)
                    self.assertEqual(actual.mode, original.mode)
                else:
                    self.assertEqual(actual, original)
        for role in ROLES:
            self.assertEqual(generated[f'skills/thermos/references/agents/{role}-subagent.md'],
                             source[f'agents/{role}-subagent.md'])
        self.assertEqual(read_tree(self.source), source)
        self.assertEqual(read_tree(self.assets), assets)
        self.generate()
        self.generate(check=True)
        self.assertEqual(read_tree(self.layout.published), generated)

    def test_skills_only_copy_resolves_both_full_rubrics_and_roles(self):
        self.generate()
        for host in ('.claude', '.agents'):
            with self.subTest(host=host):
                installed = self.root / 'unrelated project' / host / 'skills'
                shutil.copytree(self.layout.published / 'skills', installed)
                self.assertEqual({p.name for p in installed.iterdir()}, SKILLS)
                adaptation = installed / 'thermos/references/runtime-adaptation.md'
                for skill in SKILLS:
                    path = installed / skill / 'SKILL.md'
                    links = re.findall(r'\[the runtime adaptation\]\(([^)]+)\)', path.read_text())
                    self.assertEqual(len(links), 1)
                    self.assertEqual((path.parent / links[0]).resolve(), adaptation.resolve())
                    self.assertTrue(adaptation.is_file())
                    self.assertEqual((path.parent / 'LICENSE').read_bytes(), (self.source / 'LICENSE').read_bytes())
                references = re.findall(r'`([^`\n]+\.md)`', adaptation.read_text())
                targets = {(adaptation.parent / relative).resolve() for relative in references}
                expected = {installed / role / 'SKILL.md' for role in ROLES}
                expected |= {installed / f'thermos/references/agents/{role}-subagent.md' for role in ROLES}
                self.assertEqual(targets, {p.resolve() for p in expected})
                for target in targets:
                    self.assertTrue(target.is_relative_to(installed.resolve()), target)
                    self.assertTrue(target.is_file(), target)
                for role in ROLES:
                    rubric = installed / role / 'SKILL.md'
                    self.assertEqual(rubric.read_bytes().replace(THERMOS_NOTICE.encode(), b'', 1),
                                     (self.source / f'skills/{role}/SKILL.md').read_bytes())
                    self.assertEqual((installed / f'thermos/references/agents/{role}-subagent.md').read_bytes(),
                                     (self.source / f'agents/{role}-subagent.md').read_bytes())

    def test_source_body_whitespace_is_preserved_exactly(self):
        path = self.source / 'skills/thermos/SKILL.md'
        header, delimiter, body = path.read_bytes().partition(b'\n---\n')
        for whitespace in (b'', b'\n', b'\n\n\n'):
            with self.subTest(leading_blank_lines=len(whitespace)):
                original = header + delimiter + whitespace + body.lstrip(b'\n')
                path.write_bytes(original)
                self.generate()
                generated = (self.layout.published / 'skills/thermos/SKILL.md').read_bytes()
                self.assertEqual(generated.replace(THERMOS_NOTICE.encode(), b'', 1), original)

    def test_real_install_checker_detects_missing_and_tampered_resources_under_optimization(self):
        self.generate()
        script = self.root / 'tools/portable/check-install.py'
        shutil.copy2(ROOT / 'tools/portable/check-install.py', script)
        project = self.root / 'isolated installed project'
        for host in ('.claude', '.agents'):
            shutil.copytree(self.layout.published / 'skills', project / host / 'skills')
        cases = [('.agents', f'{role}/SKILL.md', 'missing') for role in ROLES]
        cases += [('.claude', f'thermos/references/agents/{role}-subagent.md', 'tampered') for role in ROLES]
        cases += [('.claude', 'thermos/references/runtime-adaptation.md', 'missing'),
                  ('.agents', 'thermos/agents/openai.yaml', 'tampered')]
        for optimization in ('0', '1', '2'):
            env = os.environ | {'PYTHONOPTIMIZE': optimization}

            def check():
                return subprocess.run([sys.executable, str(script), str(project), '--package', 'thermos'],
                                      env=env, text=True, capture_output=True)

            with self.subTest(optimization=optimization, installation='complete'):
                result = check()
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn('.claude: 3 installed skills', result.stdout)
                self.assertIn('.agents: 3 installed skills', result.stdout)
            for host, name, change in cases:
                with self.subTest(optimization=optimization, host=host, name=name, change=change):
                    path = project / host / 'skills' / name
                    original = path.read_bytes()
                    if change == 'missing':
                        path.unlink()
                    else:
                        path.write_bytes(original + b'\nTAMPERED\n')
                    try:
                        result = check()
                        self.assertNotEqual(result.returncode, 0, result.stdout)
                        self.assertIn(name, result.stderr)
                    finally:
                        path.write_bytes(original)

    def test_each_skill_remains_explicit_only_on_both_hosts(self):
        self.generate()
        for skill in SKILLS:
            with self.subTest(skill=skill):
                root = self.layout.published / 'skills' / skill
                metadata, _ = frontmatter((root / 'SKILL.md').read_text())
                self.assertEqual(metadata['name'], skill)
                self.assertIs(metadata['disable-model-invocation'], True)
                policy = yaml.safe_load((root / 'agents/openai.yaml').read_text())
                self.assertIs(policy['policy']['allow_implicit_invocation'], False)

    def test_native_manifests_register_existing_wrappers_and_exact_prompt_paths(self):
        self.generate()
        package = self.layout.published
        for host in ('claude', 'codex'):
            manifest = json.loads((package / f'.{host}-plugin/plugin.json').read_text())
            self.assertEqual(manifest['name'], 'thermos')
            self.assertEqual((package / manifest['skills']).resolve(), package / 'skills')
            self.assertEqual({p.parent.name for p in (package / manifest['skills']).glob('*/SKILL.md')}, SKILLS)
            self.assertNotIn('hooks', manifest)
            if host == 'codex':
                self.assertNotIn('agents', manifest)
                continue
            self.assertEqual(set(manifest['agents']), {f'./runtime-agents/{role}-subagent.md' for role in ROLES})
            for relative in manifest['agents']:
                path = (package / relative).resolve()
                self.assertTrue(path.is_relative_to(package))
                metadata, body = frontmatter(path.read_text())
                self.assertEqual(metadata['name'], path.stem)
                self.assertEqual(metadata['model'], 'inherit')
                self.assertEqual(metadata['tools'], 'Read, Grep, Glob')
                role = path.stem.removesuffix('-subagent')
                links = re.findall(r'\[[^\]]+\]\(([^)]+)\)', body)
                self.assertEqual(len(links), 3)
                resolved = set()
                for link in links:
                    self.assertTrue(link.startswith('${CLAUDE_PLUGIN_ROOT}/'), link)
                    target = Path(link.replace('${CLAUDE_PLUGIN_ROOT}', str(package))).resolve()
                    self.assertTrue(target.is_relative_to(package), target)
                    self.assertTrue(target.is_file(), target)
                    resolved.add(target)
                self.assertEqual(resolved, {
                    package / 'skills/thermos/references/runtime-adaptation.md',
                    package / f'skills/thermos/references/agents/{role}-subagent.md',
                    package / f'skills/{role}/SKILL.md',
                })
        upstream_version = json.loads((self.source / '.cursor-plugin/plugin.json').read_text())['version']
        self.assertRegex(self.version(), rf'^{re.escape(upstream_version)}-portable\.g{PIN[:12]}\.a[0-9a-f]{{12}}$')

    def test_adapter_bytes_modes_and_pin_invalidate_versions_deterministically(self):
        self.generate()
        previous = self.version()
        for name in ('skills/thermos/references/runtime-adaptation.md',
                     'runtime-agents/thermo-nuclear-review-subagent.md'):
            with self.subTest(asset=name):
                path = self.assets / name
                path.write_bytes(path.read_bytes() + b'\nAdditional adapter instruction.\n')
                with self.assertRaisesRegex(ValueError, 'drift'):
                    self.generate(check=True)
                self.generate()
                self.assertNotEqual(self.version(), previous)
                previous = self.version()
                self.generate()
                self.assertEqual(self.version(), previous)
        (self.assets / name).chmod(0o755)
        self.generate()
        self.assertNotEqual(self.version(), previous)
        previous = self.version()
        prepare_package(self.layout, 'b' * 40, check=False)
        self.assertNotEqual(self.version(), previous)
        self.assertIn('.gbbbbbbbbbbbb.', self.version())

    def test_manifest_input_versions_and_json_key_order_do_not_change_version(self):
        self.generate()
        version = self.version()
        for host in ('claude', 'codex'):
            path = self.assets / f'.{host}-plugin/plugin.json'
            manifest = json.loads(path.read_text())
            manifest['version'] = 'ignored-input-version'
            path.write_text(json.dumps(dict(reversed(list(manifest.items())))))
        self.generate()
        self.assertEqual(self.version(), version)
        self.generate(check=True)

    def test_missing_extra_and_renamed_skills_fail_closed(self):
        self.generate()
        for skill in SKILLS:
            with self.subTest(missing=skill):
                path = self.source / f'skills/{skill}/SKILL.md'
                original = path.read_bytes()
                path.unlink()
                self.assert_rejected_without_changes('inventory changed')
                path.write_bytes(original)
        path = self.write(self.source / 'skills/unreviewed/SKILL.md',
                          '---\nname: unreviewed\ndescription: New upstream skill\n---\nBody\n')
        self.assert_rejected_without_changes('inventory changed')
        shutil.rmtree(path.parent)
        (self.source / 'skills/thermos').rename(self.source / 'skills/renamed')
        self.assert_rejected_without_changes('inventory changed')

    def test_wrong_name_and_malformed_frontmatter_fail_closed(self):
        self.generate()
        path = self.source / 'skills/thermos/SKILL.md'
        for content in ('---\nname: renamed\ndescription: Review\n---\nBody\n',
                        '---\nname: thermos\nname: thermos\ndescription: Review\n---\nBody\n',
                        '---\nname: thermos\ndescription: [not, a, string]\n---\nBody\n',
                        '# No frontmatter\n'):
            with self.subTest(content=content):
                path.write_text(content)
                self.assert_rejected_without_changes('Thermos skill name differs|Duplicate YAML key|Expected')

    def test_missing_source_reviewer_fails_closed(self):
        self.generate()
        for role in ROLES:
            with self.subTest(role=role):
                path = self.source / f'agents/{role}-subagent.md'
                original = path.read_bytes()
                path.unlink()
                self.assert_rejected_without_changes('Missing Thermos source agent')
                path.write_bytes(original)

    def test_generated_policy_license_role_and_overlay_collisions_fail_closed(self):
        self.generate()
        collisions = (
            (self.assets, 'skills/thermos/agents/openai.yaml'),
            (self.assets, 'skills/thermos/LICENSE'),
            (self.assets, 'skills/thermos/references/agents/thermo-nuclear-review-subagent.md'),
            (self.assets, 'skills/thermos/SKILL.md'),
            (self.source, '.claude-plugin/plugin.json'),
            (self.source, 'skills/thermos/agents/openai.yaml'),
            (self.source, 'skills/thermos/LICENSE'),
            (self.source, 'skills/thermos/references/agents/thermo-nuclear-review-subagent.md'),
            (self.source, 'runtime-agents'),
        )
        for root, name in collisions:
            with self.subTest(root=root.name, name=name):
                path = self.write(root / name, 'collision')
                self.assert_rejected_without_changes('collides')
                path.unlink()

    def test_file_and_directory_symlinks_in_inputs_or_output_are_rejected(self):
        self.generate()
        original = read_tree(self.layout.published)
        for root in (self.source, self.assets, self.layout.published):
            for is_directory in (False, True):
                with self.subTest(root=root, is_directory=is_directory):
                    link = root / 'escape'
                    target = self.source if is_directory else self.source / 'LICENSE'
                    link.symlink_to(target, target_is_directory=is_directory)
                    with self.assertRaisesRegex(ValueError, 'Unsupported symlink'):
                        self.generate()
                    link.unlink()
                    self.assertEqual(read_tree(self.layout.published), original)

    def test_symlinked_input_roots_and_publication_locations_are_rejected(self):
        self.generate()
        for root in (self.source, self.assets, self.layout.published, self.layout.published.parent):
            with self.subTest(root=root):
                saved = root.with_name(root.name + '-real')
                root.rename(saved)
                root.symlink_to(saved, target_is_directory=True)
                try:
                    with self.assertRaisesRegex(ValueError, 'real package directory|Unsafe generated destination'):
                        self.generate()
                finally:
                    root.unlink()
                    saved.rename(root)

    def test_destination_must_be_isolated_from_inputs(self):
        for destination in (self.source, self.source / 'portable/thermos', self.root / 'other'):
            with self.subTest(destination=destination):
                with self.assertRaisesRegex(ValueError, 'Unsafe generated destination'):
                    prepare_package(PackageLayout(self.source, self.assets, destination), PIN, check=False)
        self.layout.published.mkdir(parents=True)
        with self.assertRaisesRegex(ValueError, 'overlaps an input'):
            prepare_package(PackageLayout(self.source, self.layout.published, self.layout.published), PIN, check=False)

    def test_drift_check_detects_extra_missing_modified_files_and_executable_modes(self):
        executable = self.write(self.source / 'skills/thermos/references/inspect.sh', '#!/bin/sh\nexit 0\n')
        executable.chmod(0o755)
        self.generate()
        original = read_tree(self.layout.published)
        path = self.layout.published / 'skills/thermos/references/inspect.sh'
        changes = (lambda: path.chmod(0o644), lambda: path.unlink(),
                   lambda: path.write_text('tampered'),
                   lambda: (self.layout.published / 'stale').write_text('stale'))
        for change in changes:
            with self.subTest(change=change):
                change()
                with self.assertRaisesRegex(ValueError, 'Generated package drift'):
                    self.generate(check=True)
                self.generate()
                self.assertEqual(read_tree(self.layout.published), original)
                self.generate(check=True)

    def test_pin_verification_covers_thermos_content_inventory_and_modes(self):
        self.write(self.root / 'README.md', 'Upstream root\n')
        self.write(self.root / 'pstack/source.txt', 'Other package\n')
        self.write(self.root / 'cursor-team-kit/skills/deslop/SKILL.md', 'Dependency\n')
        self.write(self.root / 'cursor-team-kit/LICENSE', 'License\n')
        env = {k: v for k, v in os.environ.items()
               if k not in {'GIT_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE', 'GIT_COMMON_DIR'}}

        def git(*args):
            return subprocess.run(['git', *args], cwd=self.root, env=env, check=True,
                                  text=True, capture_output=True).stdout.strip()

        git('init', '-b', 'main')
        git('config', 'user.name', 'Test')
        git('config', 'user.email', 'test@example.invalid')
        git('config', 'commit.gpgsign', 'false')
        git('add', 'README.md', 'pstack', 'thermos', 'cursor-team-kit')
        git('commit', '-m', 'Pinned source fixture')
        pin = git('rev-parse', 'HEAD')
        verify_source(self.root, pin, packages=('pstack', 'thermos'))
        path = self.source / 'skills/thermos/SKILL.md'
        original = path.read_bytes()
        for change in (lambda: path.write_bytes(original + b'\nChanged upstream body\n'),
                       lambda: path.chmod(0o755), lambda: path.unlink()):
            change()
            with self.assertRaisesRegex(ValueError, 'thermos/skills/thermos/SKILL.md'):
                verify_source(self.root, pin, packages=('pstack', 'thermos'))
            path.write_bytes(original)
            path.chmod(0o644)
        extra = self.write(self.source / 'untracked.md', 'Unpinned source\n')
        with self.assertRaisesRegex(ValueError, 'thermos/untracked.md'):
            verify_source(self.root, pin, packages=('pstack', 'thermos'))
        extra.unlink()
        path.unlink()
        path.symlink_to(self.source / 'LICENSE')
        with self.assertRaisesRegex(ValueError, 'thermos/skills/thermos/SKILL.md'):
            verify_source(self.root, pin, packages=('pstack', 'thermos'))


class ExistingPstackRegressionTests(unittest.TestCase):
    def test_adding_thermos_leaves_committed_pstack_bundle_unchanged(self):
        layout = PackageLayout(ROOT / 'pstack', ROOT / 'tools/portable/assets', ROOT / 'portable/pstack')
        self.assertEqual(render_package(layout, PIN), read_tree(layout.published))
        prepare_package(layout, PIN, check=True)


if __name__ == '__main__':
    unittest.main()
