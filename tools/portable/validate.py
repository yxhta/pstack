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


def validate_thermos():
    package = ROOT / 'portable/thermos'
    skills = {'thermos', 'thermo-nuclear-review', 'thermo-nuclear-code-quality-review'}
    for host in ('claude', 'codex'):
        manifest = json.loads((package / f'.{host}-plugin/plugin.json').read_text())
        require(manifest['name'] == 'thermos', f'Invalid {host} Thermos name')
        require((package / manifest['skills']).resolve() == package / 'skills', f'Invalid {host} Thermos skills path')
        marketplace_path = '.claude-plugin/marketplace.json' if host == 'claude' else '.agents/plugins/marketplace.json'
        marketplace = json.loads((ROOT / marketplace_path).read_text())
        entries = [entry for entry in marketplace['plugins'] if entry['name'] == 'thermos']
        require(len(entries) == 1, f'Expected one {host} Thermos marketplace entry')
        source = entries[0]['source'] if host == 'claude' else entries[0]['source']['path']
        require(source == './portable/thermos', f'{host} marketplace must use portable Thermos')
        if host == 'claude':
            expected = {f'./runtime-agents/{role}-subagent.md' for role in skills - {'thermos'}}
            require(set(manifest['agents']) == expected, 'Wrong Thermos native wrappers')
            for name in expected:
                text = (package / name).read_text()
                metadata = yaml.safe_load(text.split('---\n', 2)[1])
                require(metadata['model'] == 'inherit', 'Thermos agents must inherit the model')
                require(metadata['tools'] == 'Read, Grep, Glob', 'Thermos native reviewers must be read-only')
                for target in re.findall(r'\$\{CLAUDE_PLUGIN_ROOT\}([^\s)]+)', text):
                    resolved = (package / target.lstrip('/')).resolve()
                    require(resolved.is_relative_to(package) and resolved.is_file(), f'Invalid Thermos wrapper link: {target}')
    actual = {p.parent.name for p in (package / 'skills').glob('*/SKILL.md')}
    require(actual == skills, 'Thermos skill inventory differs')
    for name in skills:
        skill = package / 'skills' / name
        metadata = yaml.safe_load((skill / 'SKILL.md').read_text().split('---\n', 2)[1])
        require(metadata['name'] == name and metadata['disable-model-invocation'] is True, f'Thermos invocation metadata differs: {name}')
        policy = yaml.safe_load((skill / 'agents/openai.yaml').read_text())
        require(policy['policy']['allow_implicit_invocation'] is False, f'Thermos Codex invocation policy differs: {name}')
        require((skill / '../thermos/references/runtime-adaptation.md').resolve().is_file(), f'Missing Thermos adaptation: {name}')
        require((skill / 'LICENSE').is_file(), f'Missing Thermos skill license: {name}')
    for role in skills - {'thermos'}:
        require((package / f'skills/thermos/references/agents/{role}-subagent.md').is_file(), f'Missing Thermos reviewer: {role}')
    print('Validated 3 Thermos skills, both manifests, marketplaces, and 2 read-only Claude wrappers.')


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
    validate_thermos()


if __name__ == '__main__':
    main()
