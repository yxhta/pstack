import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock

import prepare
from prepare import (MODS_REFERENCE_ROOT, MODS_THERMOS_FILES, PackageLayout,
                     prepare_package, read_tree, render_package)
from validate import validate_mods


ROOT = Path(__file__).resolve().parents[2]
PIN = json.loads((ROOT / 'tools/portable/upstream.json').read_text())['last_merged_sha']


class ModsPackageTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='mods package tests ')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / 'thermos'
        self.assets = self.root / 'tools/portable/mods-assets'
        shutil.copytree(ROOT / 'thermos', self.source)
        self.write(self.assets / '.claude-plugin/plugin.json',
                   '{"name":"pstack-mods","description":"Opt-in Claude Mods"}\n')
        self.write(self.assets / 'hooks/check.sh', '#!/bin/sh\nexit 0\n').chmod(0o755)
        self.write(self.assets / 'mods/review/MOD.md', '# Independent review\n')
        self.layout = PackageLayout(self.source, self.assets,
                                    self.root / 'portable/pstack-mods', package_name='pstack-mods')

    @staticmethod
    def write(path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data if isinstance(data, bytes) else data.encode())
        return path

    def generate(self, check=False, pin=PIN):
        prepare_package(self.layout, pin, check=check)

    def version(self):
        return json.loads((self.layout.published / '.claude-plugin/plugin.json').read_text())['version']

    def test_generation_preserves_all_inputs_and_pristine_thermos_references(self):
        source, assets = read_tree(self.source), read_tree(self.assets)
        self.generate()
        generated = read_tree(self.layout.published)
        expected = set(assets) | {f'{MODS_REFERENCE_ROOT}/{name}' for name in MODS_THERMOS_FILES}
        self.assertEqual(set(generated), expected)
        for name in MODS_THERMOS_FILES:
            self.assertEqual(generated[f'{MODS_REFERENCE_ROOT}/{name}'], source[name])
        for name in assets.keys() - {'.claude-plugin/plugin.json'}:
            self.assertEqual(generated[name], assets[name])
        self.assertEqual(read_tree(self.source), source)
        self.assertEqual(read_tree(self.assets), assets)
        self.assertNotIn('.cursor-plugin/plugin.json', generated)
        self.assertNotIn('.codex-plugin/plugin.json', generated)
        self.assertRegex(self.version(), rf'^0\.1\.0-mods\.g{PIN[:12]}\.a[0-9a-f]{{12}}$')
        self.generate()
        self.generate(check=True)
        self.assertEqual(read_tree(self.layout.published), generated)

    def test_native_type_sidecars_do_not_change_version_or_freshness(self):
        self.generate()
        original = self.version()
        for name in prepare.MODS_TYPE_SIDECARS:
            self.write(self.layout.published / name, 'native declarations')
            self.write(self.assets / name, 'authoring declarations')
        self.generate(check=True)
        self.generate()
        self.assertEqual(self.version(), original)
        self.write(self.layout.published / '.claude-plugin/types/unexpected.js', 'throw new Error()')
        with self.assertRaisesRegex(ValueError, 'Generated package drift'):
            self.generate(check=True)

    def test_native_type_sidecar_symlinks_are_still_rejected(self):
        self.generate()
        path = self.layout.published / '.claude-plugin/types/claude-code/index.d.ts'
        path.parent.mkdir(parents=True)
        path.symlink_to(self.source / 'LICENSE')
        with self.assertRaisesRegex(ValueError, 'Unsupported symlink'):
            self.generate(check=True)

    def test_hash_covers_assets_reference_bytes_modes_and_upstream_pin(self):
        self.generate()
        previous = self.version()
        for path in (self.assets / 'mods/review/MOD.md',
                     self.source / 'skills/thermo-nuclear-review/SKILL.md',
                     self.source / 'agents/thermo-nuclear-code-quality-review-subagent.md',
                     self.source / 'LICENSE'):
            with self.subTest(path=path):
                path.write_bytes(path.read_bytes() + b'\nNew pinned content\n')
                with self.assertRaisesRegex(ValueError, 'Generated package drift'):
                    self.generate(check=True)
                self.generate()
                self.assertNotEqual(self.version(), previous)
                previous = self.version()
                path.chmod(0o755)
                self.generate()
                self.assertNotEqual(self.version(), previous)
                previous = self.version()
        (self.assets / 'hooks/check.sh').chmod(0o644)
        self.generate()
        self.assertNotEqual(self.version(), previous)
        previous = self.version()
        self.generate(pin='b' * 40)
        self.assertNotEqual(self.version(), previous)
        self.assertIn('.gbbbbbbbbbbbb.', self.version())
        self.generate(check=True, pin='b' * 40)

    def test_manifest_input_version_and_key_order_do_not_affect_digest(self):
        self.generate()
        version = self.version()
        path = self.assets / '.claude-plugin/plugin.json'
        manifest = json.loads(path.read_text()) | {'version': 'ignored-input-version'}
        path.write_text(json.dumps(dict(reversed(list(manifest.items())))))
        self.generate()
        self.assertEqual(self.version(), version)
        self.generate(check=True)

    def test_drift_detects_and_repairs_stale_missing_changed_and_mode_only_files(self):
        self.generate()
        original = read_tree(self.layout.published)
        hook = self.layout.published / 'hooks/check.sh'
        for change in (lambda: self.write(self.layout.published / 'stale', 'old'),
                       lambda: hook.unlink(), lambda: hook.write_bytes(b'changed'),
                       lambda: hook.chmod(0o644)):
            with self.subTest(change=change):
                change()
                with self.assertRaisesRegex(ValueError, 'Generated package drift'):
                    self.generate(check=True)
                self.generate()
                self.assertEqual(read_tree(self.layout.published), original)
                self.generate(check=True)
        (self.assets / 'mods/review/MOD.md').rename(self.assets / 'mods/review/renamed.md')
        self.generate()
        self.assertFalse((self.layout.published / 'mods/review/MOD.md').exists())
        self.assertTrue((self.layout.published / 'mods/review/renamed.md').is_file())

    def test_missing_references_and_invalid_manifests_do_not_change_published_output(self):
        self.generate()
        original = read_tree(self.layout.published)
        for name in MODS_THERMOS_FILES:
            with self.subTest(missing=name):
                path = self.source / name
                data = path.read_bytes()
                path.unlink()
                with self.assertRaisesRegex(ValueError, 'Missing Mods Thermos reference'):
                    self.generate()
                self.assertEqual(read_tree(self.layout.published), original)
                path.write_bytes(data)
        manifest = self.assets / '.claude-plugin/plugin.json'
        for data in ('{}', '{"name":"pstack"}', '[]', 'null', '{bad json'):
            with self.subTest(manifest=data):
                manifest.write_text(data)
                with self.assertRaises(ValueError):
                    self.generate()
                self.assertEqual(read_tree(self.layout.published), original)
        manifest.unlink()
        with self.assertRaisesRegex(ValueError, 'Missing Mods Claude plugin manifest'):
            self.generate()

    def test_generated_reference_namespace_and_other_hosts_are_reserved(self):
        self.generate()
        original = read_tree(self.layout.published)
        for name in ('references', 'references/thermos', 'references/thermos/LICENSE',
                     'references/thermos/new-instructions.md', '.codex-plugin/plugin.json',
                     '.cursor-plugin/plugin.json'):
            with self.subTest(collision=name):
                path = self.write(self.assets / name, '{}')
                with self.assertRaisesRegex(ValueError, 'collides|Claude-only'):
                    self.generate()
                self.assertEqual(read_tree(self.layout.published), original)
                path.unlink()
                while path.parent != self.assets and not any(path.parent.iterdir()):
                    path = path.parent
                    path.rmdir()

    def test_symlinked_roots_files_directories_and_publication_parent_are_rejected(self):
        self.generate()
        for root in (self.source, self.assets, self.layout.published):
            for directory in (False, True):
                with self.subTest(root=root, directory=directory):
                    link = root / 'escape'
                    link.symlink_to(self.root if directory else self.source / 'LICENSE',
                                    target_is_directory=directory)
                    try:
                        with self.assertRaisesRegex(ValueError, 'Unsupported symlink'):
                            self.generate()
                    finally:
                        link.unlink()
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
        self.generate(check=True)

    def test_destination_cannot_overwrite_sources_or_other_packages(self):
        for destination in (self.source, self.assets, self.root / 'other',
                            self.root / 'portable/pstack', self.root / 'portable/thermos',
                            self.source / 'portable/pstack-mods'):
            with self.subTest(destination=destination):
                with self.assertRaisesRegex(ValueError, 'Unsafe generated destination'):
                    prepare_package(PackageLayout(self.source, self.assets, destination,
                                                   package_name='pstack-mods'), PIN, check=False)
        with self.assertRaisesRegex(ValueError, 'Unsafe generated destination'):
            prepare_package(PackageLayout(self.root / 'pstack', self.assets, self.layout.published,
                                           package_name='pstack-mods'), PIN, check=False)
        with self.assertRaisesRegex(ValueError, 'overlaps an input'):
            prepare_package(PackageLayout(self.source, self.layout.published, self.layout.published,
                                           package_name='pstack-mods'), PIN, check=False)

    def test_failed_publication_restores_previous_mods_package(self):
        self.generate()
        original = read_tree(self.layout.published)
        self.write(self.assets / 'new.md', 'New adapter resource')
        rename = Path.rename

        def fail_publication(path, destination):
            if path.name == 'package':
                raise OSError('simulated publication failure')
            return rename(path, destination)

        with mock.patch.object(Path, 'rename', fail_publication):
            with self.assertRaisesRegex(OSError, 'simulated publication failure'):
                self.generate()
        self.assertEqual(read_tree(self.layout.published), original)
        self.assertEqual(list(self.layout.published.parent.glob('.pstack-mods-*')), [])
        self.generate()
        self.generate(check=True)

    def test_validator_rejects_other_hosts_bad_registration_and_reference_drift(self):
        self.generate()
        self.write(self.root / 'tools/portable/upstream.json', json.dumps({'last_merged_sha': PIN}))
        marketplace = self.root / '.claude-plugin/marketplace.json'
        codex = self.root / '.agents/plugins/marketplace.json'
        entry = {'name': 'pstack-mods', 'source': './portable/pstack-mods'}
        self.write(marketplace, json.dumps({'plugins': [entry]}))
        self.write(codex, '{"plugins": []}')
        with mock.patch('validate.ROOT', self.root):
            validate_mods()
            for entries in ([], [entry, entry], [entry | {'source': './portable/pstack'}]):
                with self.subTest(marketplace=entries):
                    marketplace.write_text(json.dumps({'plugins': entries}))
                    with self.assertRaisesRegex(ValueError, 'separate Claude Mods marketplace entry'):
                        validate_mods()
            marketplace.write_text(json.dumps({'plugins': [entry]}))
            codex.write_text(json.dumps({'plugins': [entry]}))
            with self.assertRaisesRegex(ValueError, 'must not be advertised to Codex'):
                validate_mods()
            codex.write_text('{"plugins": []}')
            for host in ('codex', 'cursor'):
                path = self.write(self.layout.published / f'.{host}-plugin/plugin.json', '{}')
                with self.assertRaisesRegex(ValueError, 'separate Claude-only plugin'):
                    validate_mods()
                path.unlink()
                path.parent.rmdir()
            manifest = self.layout.published / '.claude-plugin/plugin.json'
            metadata = json.loads(manifest.read_text())
            for key, value, error in (('name', 'pstack', 'plugin name'),
                                      ('version', '0.1.0', 'content-addressed version')):
                manifest.write_text(json.dumps(metadata | {key: value}))
                with self.assertRaisesRegex(ValueError, error):
                    validate_mods()
            manifest.write_text(json.dumps(metadata))
            reference = self.layout.published / MODS_REFERENCE_ROOT / 'LICENSE'
            original = reference.read_bytes()
            for change in (lambda: reference.write_bytes(original + b'altered'),
                           lambda: reference.chmod(0o755),
                           lambda: self.write(reference.parent / 'extra', 'new instructions')):
                with self.subTest(change=change):
                    change()
                    with self.assertRaisesRegex(ValueError, 'exact upstream files and executable modes'):
                        validate_mods()
                    self.generate()
            validate_mods()


class ModsIntegrationTests(unittest.TestCase):
    def test_existing_bundles_remain_identical_with_mods_support(self):
        for name, assets in (('pstack', 'assets'), ('thermos', 'thermos-assets')):
            with self.subTest(package=name):
                layout = PackageLayout(ROOT / name, ROOT / 'tools/portable' / assets, ROOT / 'portable' / name)
                self.assertEqual(render_package(layout, PIN), read_tree(layout.published))
                prepare_package(layout, PIN, check=True)

    def test_main_checks_source_before_rendering_all_three_packages(self):
        calls = mock.Mock()
        with mock.patch('prepare.verify_source') as verify, mock.patch('prepare.prepare_package') as publish:
            calls.attach_mock(verify, 'verify')
            calls.attach_mock(publish, 'publish')
            with mock.patch('sys.argv', ['prepare.py', '--check']):
                prepare.main()
        self.assertEqual(calls.mock_calls[0], mock.call.verify(ROOT, PIN, packages=('pstack', 'thermos')))
        self.assertEqual([call.args[0].name for call in publish.call_args_list], ['pstack', 'thermos', 'pstack-mods'])
        self.assertTrue(all(call.kwargs == {'check': True} for call in publish.call_args_list))
        mods = publish.call_args_list[-1].args[0]
        self.assertEqual(mods.upstream, ROOT / 'thermos')
        self.assertEqual(mods.assets, ROOT / 'tools/portable/mods-assets')
        self.assertEqual(mods.published, ROOT / 'portable/pstack-mods')
        with mock.patch('prepare.verify_source', side_effect=ValueError('Upstream source differs from pin')):
            with mock.patch('prepare.prepare_package') as publish:
                with mock.patch('sys.argv', ['prepare.py']):
                    with self.assertRaisesRegex(ValueError, 'Upstream source differs from pin'):
                        prepare.main()
                publish.assert_not_called()


if __name__ == '__main__':
    unittest.main()
