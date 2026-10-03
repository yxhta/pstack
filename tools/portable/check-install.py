#!/usr/bin/env python3
"""Check a skills-only installation without changing user settings."""
import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('project', type=Path)
    args = parser.parse_args()
    source_root = ROOT / 'pstack/skills'
    source_skills = sorted(source_root.glob('*/SKILL.md'))
    for runtime in ('.claude', '.agents'):
        installed_root = args.project.resolve() / runtime / 'skills'
        assert len(list(installed_root.glob('*/SKILL.md'))) == len(source_skills), runtime
        for skill in source_skills:
            for source in skill.parent.rglob('*'):
                if not source.is_file():
                    continue
                installed = installed_root / source.relative_to(source_root)
                assert installed.is_file(), installed
                assert installed.read_bytes() == source.read_bytes(), installed
            adaptation = installed_root / skill.parent.name / '../poteto-mode/references/runtime-adaptation.md'
            assert adaptation.resolve().is_relative_to(installed_root), adaptation
            assert adaptation.is_file(), adaptation
        for agent in ('poteto-agent.md', 'comment-sicko.md'):
            assert (installed_root / 'poteto-mode/references/portable-agents' / agent).is_file()
        print(f'{runtime}: {len(source_skills)} installed skills and all bundled resources verified.')


if __name__ == '__main__':
    main()
