#!/usr/bin/env python3
"""Render the committed portable package without modifying upstream files."""
import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

import yaml

ROOT = Path(__file__).resolve().parents[2]
NOTICE = ('On Claude Code or Codex, first read [the runtime adaptation]'
          '(../poteto-mode/references/runtime-adaptation.md). Apply its substitutions to this skill.\n\n')


@dataclass(frozen=True)
class PackageLayout:
    upstream: Path
    assets: Path
    published: Path


@dataclass(frozen=True)
class Artifact:
    data: bytes
    mode: int


ArtifactTree = dict[str, Artifact]


def read_tree(root: Path) -> ArtifactTree:
    tree = {}
    for path in sorted(root.rglob('*')):
        if path.is_symlink():
            raise ValueError(f'Unsupported symlink in package input or output: {path}')
        if path.is_file():
            tree[path.relative_to(root).as_posix()] = Artifact(path.read_bytes(), 0o755 if path.stat().st_mode & 0o111 else 0o644)
        elif not path.is_dir():
            raise ValueError(f'Unsupported file type: {path}')
    return tree


def prepare(text, name):
    match = re.match(r'\A---\n(.*?)\n---\n(.*)\Z', text, re.S)
    if not match:
        raise ValueError('Expected LF-delimited YAML frontmatter')
    front, body = match.groups()
    metadata = yaml.safe_load(front)
    if not isinstance(metadata, dict) or not isinstance(metadata.get('name'), str) or not isinstance(metadata.get('description'), str):
        raise ValueError('Expected string name and description in frontmatter')
    if len(re.findall(r'^name: .+$', front, re.M)) != 1:
        raise ValueError('Expected one single-line name field')
    front = re.sub(r'^name: .+$', f'name: {name}', front, flags=re.M)
    body = body.lstrip('\n')
    if body.startswith(NOTICE):
        body = body[len(NOTICE):]
    return f'---\n{front}\n---\n\n{NOTICE}{body}'


def render_package(layout: PackageLayout, upstream_commit: str) -> ArtifactTree:
    tree = read_tree(layout.upstream)
    for name, artifact in list(tree.items()):
        if re.fullmatch(r'skills/[^/]+/SKILL.md', name):
            skill = name.split('/')[1]
            if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', skill):
                raise ValueError(f'Unsupported skill directory: {skill}')
            tree[name] = Artifact(prepare(artifact.data.decode(), skill).encode(), artifact.mode)
    overlay = read_tree(layout.assets)
    maintenance = overlay.pop('sync-pstack-upstream.md')
    overlay['skills/sync-pstack-upstream/SKILL.md'] = Artifact(prepare(maintenance.data.decode(), 'sync-pstack-upstream').encode(), maintenance.mode)
    for name in list(overlay):
        if name.startswith('sync-pstack-upstream/'):
            overlay['skills/' + name] = overlay.pop(name)
    for name, artifact in list(tree.items()):
        if re.fullmatch(r'agents/[^/]+\.md', name):
            target = 'skills/poteto-mode/references/portable-agents/' + Path(name).name
            if target in overlay:
                raise ValueError(f'Portable asset collides with generated agent: {target}')
            overlay[target] = artifact
    version = json.loads(tree['.cursor-plugin/plugin.json'].data)['version']
    digest = hashlib.sha256()
    for name, artifact in sorted((tree | overlay).items()):
        data = artifact.data
        if name in ('.claude-plugin/plugin.json', '.codex-plugin/plugin.json'):
            metadata = json.loads(data)
            metadata.pop('version', None)
            data = json.dumps(metadata, sort_keys=True).encode()
        for value in (name.encode(), str(artifact.mode).encode(), data):
            digest.update(len(value).to_bytes(8, 'big'))
            digest.update(value)
    package_version = version + '-portable.g' + upstream_commit[:12] + '.a' + digest.hexdigest()[:12]
    for runtime in ('claude', 'codex'):
        name = f'.{runtime}-plugin/plugin.json'
        manifest = json.loads(overlay[name].data)
        manifest['version'] = package_version
        overlay[name] = Artifact((json.dumps(manifest, indent=2) + '\n').encode(), overlay[name].mode)
    for name, artifact in overlay.items():
        if name in tree or any(name.startswith(p + '/') or p.startswith(name + '/') for p in tree):
            raise ValueError(f'Portable overlay collides with upstream: {name}')
        tree[name] = artifact
    return tree


def verify_source(root: Path, upstream_commit: str) -> None:
    entries = subprocess.check_output(['git', 'ls-tree', '-rz', upstream_commit, '--', 'pstack', 'README.md'], cwd=root).split(b'\0')
    if (root / 'pstack').is_symlink():
        raise ValueError('Upstream source root must not be a symlink')
    expected = {}
    for entry in entries:
        if not entry:
            continue
        header, name = entry.split(b'\t', 1)
        mode, kind, oid = header.split()
        if kind != b'blob':
            raise ValueError(f'Unsupported upstream Git object: {name.decode()}')
        expected[name.decode()] = (mode.decode(), subprocess.check_output(['git', 'cat-file', 'blob', oid.decode()], cwd=root))
    if 'README.md' not in expected or not any(p.startswith('pstack/') for p in expected):
        raise ValueError('Pin must contain root README.md and pstack files')
    actual = {}
    paths = list((root / 'pstack').rglob('*')) + [root / 'README.md']
    for path in paths:
        if path.is_symlink():
            actual[path.relative_to(root).as_posix()] = ('120000', path.readlink().as_posix().encode())
        elif path.is_file():
            actual[path.relative_to(root).as_posix()] = ('100755' if path.stat().st_mode & 0o111 else '100644', path.read_bytes())
        elif not path.is_dir():
            raise ValueError(f'Unsupported source file type: {path}')
    changed = sorted(name for name in expected.keys() | actual.keys() if expected.get(name) != actual.get(name))
    if changed:
        raise ValueError('Upstream source differs from pin: ' + ', '.join(changed))


def prepare_package(layout: PackageLayout, upstream_commit: str, *, check: bool) -> None:
    destination = layout.published
    if destination.absolute() != layout.upstream.parent.absolute() / 'portable/pstack' or destination.is_symlink() or destination.parent.is_symlink():
        raise ValueError(f'Unsafe generated destination: {destination}')
    resolved = destination.resolve()
    for source in (layout.upstream.resolve(), layout.assets.resolve()):
        if resolved == source or resolved.is_relative_to(source) or source.is_relative_to(resolved):
            raise ValueError('Generated destination overlaps an input')
    desired = render_package(layout, upstream_commit)
    actual = read_tree(destination) if destination.exists() else {}
    changed = sorted(name for name in desired.keys() | actual.keys() if desired.get(name) != actual.get(name))
    if check:
        if changed:
            raise ValueError('Generated package drift: ' + ', '.join(changed))
        return
    if not changed:
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.pstack-', dir=destination.parent) as temporary:
        staged = Path(temporary) / 'package'
        staged.mkdir()
        for name, artifact in desired.items():
            path = staged / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(artifact.data)
            path.chmod(artifact.mode)
        if destination.exists():
            shutil.rmtree(destination)
        staged.rename(destination)
    print(f'Regenerated {destination}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    pin = json.loads((ROOT / 'tools/portable/upstream.json').read_text())['last_merged_sha']
    verify_source(ROOT, pin)
    prepare_package(PackageLayout(ROOT / 'pstack', ROOT / 'tools/portable/assets', ROOT / 'portable/pstack'), pin, check=args.check)


if __name__ == '__main__':
    main()
