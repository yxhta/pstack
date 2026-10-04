#!/usr/bin/env python3
import json
import re
import subprocess
import sys
from pathlib import Path

import yaml

from runtime import validate_resources

ROOT = Path(__file__).resolve().parents[2]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def main():
    subprocess.run([sys.executable, str(ROOT / 'tools/portable/prepare.py'), '--check'], check=True)
    validate_resources(ROOT / 'portable/pstack', ROOT / 'pstack')
    manifests = {}
    for name in ('portable/pstack/.claude-plugin/plugin.json', 'portable/pstack/.codex-plugin/plugin.json',
                 '.claude-plugin/marketplace.json', '.agents/plugins/marketplace.json',
                 'tools/portable/upstream.json'):
        manifests[name] = json.loads((ROOT / name).read_text())
    for runtime in ('claude', 'codex'):
        manifest = manifests[f'portable/pstack/.{runtime}-plugin/plugin.json']
        require(manifest['name'] == 'pstack', f'Invalid {runtime} plugin name')
        require((ROOT / 'portable/pstack' / manifest['skills']).resolve() == ROOT / 'portable/pstack/skills',
                f'Invalid {runtime} skills path')
    require(manifests['portable/pstack/.claude-plugin/plugin.json']['version'] ==
            manifests['portable/pstack/.codex-plugin/plugin.json']['version'], 'Native plugin versions differ')
    for agent in manifests['portable/pstack/.claude-plugin/plugin.json']['agents']:
        require((ROOT / 'portable/pstack' / agent).is_file(), f'Missing agent: {agent}')
    require(manifests['.claude-plugin/marketplace.json']['plugins'][0]['source'] == './portable/pstack',
            'Claude marketplace must point to the portable package')
    require(manifests['.agents/plugins/marketplace.json']['plugins'][0]['source']['path'] == './portable/pstack',
            'Codex marketplace must point to the portable package')
    require(re.fullmatch(r'[a-f0-9]{40}', manifests['tools/portable/upstream.json']['last_merged_sha']),
            'Upstream pin must be a full lowercase commit SHA')
    skills = list((ROOT / 'portable/pstack/skills').glob('*/SKILL.md'))
    require(skills, 'No skills discovered')
    for path in skills:
        metadata = yaml.safe_load(path.read_text().split('---\n', 2)[1])
        require(metadata['name'] == path.parent.name, f'Skill name differs: {path}')
        require(isinstance(metadata['description'], str) and metadata['description'].strip(),
                f'Empty or invalid skill description: {path}')
        require((path.parent / '../poteto-mode/references/runtime-adaptation.md').resolve().is_file(),
                f'Missing runtime adaptation: {path}')
    for path in (ROOT / 'portable/pstack/skills').glob('*/evals/*.json'):
        json.loads(path.read_text())
    for path in (ROOT / 'portable/pstack/runtime-agents').glob('*.md'):
        metadata = yaml.safe_load(path.read_text().split('---\n', 2)[1])
        require(metadata['name'] == path.stem, f'Agent name differs: {path}')
    for path in (ROOT / '.github/workflows').glob('*portable*.yml'):
        yaml.safe_load(path.read_text())
    yaml.safe_load((ROOT / '.github/workflows/sync-pstack-upstream.yml').read_text())
    require((ROOT / 'portable/pstack/LICENSE').is_file(), 'Missing package license')
    print(f'Validated {len(skills)} shared skills, both manifests, agents, and sync configuration.')


if __name__ == '__main__':
    main()
