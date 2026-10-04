#!/usr/bin/env python3
"""Check a copied skills-only installation without changing user settings."""
import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def inventory(root: Path) -> dict[str, tuple[bytes, bool]]:
    if root.is_symlink() or not root.is_dir():
        raise ValueError(f'Expected a real skills directory: {root}')
    files = {}
    for path in sorted(root.rglob('*')):
        if path.is_symlink():
            raise ValueError(f'Unexpected symlink in copied installation: {path}')
        if path.is_file():
            files[path.relative_to(root).as_posix()] = (path.read_bytes(), bool(path.stat().st_mode & 0o111))
        elif not path.is_dir():
            raise ValueError(f'Unsupported installed file type: {path}')
    return files


def check_install(project: Path, source_root: Path) -> int:
    expected = inventory(source_root)
    skills = {name.split('/')[0] for name in expected if len(name.split('/')) == 2 and name.endswith('/SKILL.md')}
    if not skills:
        raise ValueError(f'No source skills found: {source_root}')
    project = project.resolve()
    for runtime in ('.claude', '.agents'):
        runtime_root = project / runtime
        if runtime_root.is_symlink():
            raise ValueError(f'Unexpected symlink in copied installation: {runtime_root}')
        installed_root = runtime_root / 'skills'
        actual = inventory(installed_root)
        missing, extra = sorted(expected.keys() - actual.keys()), sorted(actual.keys() - expected.keys())
        if missing or extra:
            raise ValueError(f'{runtime}: installation file set differs; missing={missing}, unexpected={extra}')
        changed = sorted(name for name in expected if expected[name] != actual[name])
        if changed:
            raise ValueError(f'{runtime}: installed content or executable modes differ: {", ".join(changed)}')
        for skill in skills:
            adaptation = installed_root / skill / '../poteto-mode/references/runtime-adaptation.md'
            if not adaptation.resolve().is_relative_to(installed_root) or not adaptation.is_file():
                raise ValueError(f'Missing or unsafe runtime adaptation: {adaptation}')
        for agent in ('poteto-agent.md', 'comment-sicko.md'):
            path = installed_root / 'poteto-mode/references/portable-agents' / agent
            if not path.is_file():
                raise ValueError(f'Missing agent reference: {path}')
        print(f'{runtime}: {len(skills)} installed skills and all bundled resources verified.')
    return len(skills)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('project', type=Path)
    args = parser.parse_args()
    try:
        check_install(args.project, ROOT / 'portable/pstack/skills')
    except (OSError, ValueError) as error:
        parser.error(str(error))


if __name__ == '__main__':
    main()
