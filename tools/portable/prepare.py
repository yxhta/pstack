#!/usr/bin/env python3
"""Keep a small, repeatable adaptation on every upstream skill entry point."""
import argparse
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NOTICE = ('On Claude Code or Codex, first read [the runtime adaptation]'
          '(../poteto-mode/references/runtime-adaptation.md). Apply its substitutions to this skill.\n\n')


def prepare(text, name):
    parts = text.split('---\n', 2)
    if len(parts) != 3 or parts[0]:
        raise ValueError('Expected YAML frontmatter')
    front = re.sub(r'^name:.*$', f'name: {name}', parts[1], count=1, flags=re.M)
    body = parts[2].lstrip('\n')
    legacy = ('On Claude Code or Codex, first read [the runtime adaptation]'
              '(../../compatibility.md). Apply its substitutions to this skill.\n\n')
    if body.startswith(legacy):
        body = body[len(legacy):]
    if not body.startswith(NOTICE):
        body = NOTICE + body
    return f'---\n{front}---\n\n{body}'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    changed = []
    for path in sorted((ROOT / 'pstack/skills').glob('*/SKILL.md')):
        before = path.read_text()
        after = prepare(before, path.parent.name)
        if before != after:
            changed.append(str(path.relative_to(ROOT)))
            if not args.check:
                path.write_text(after)
    for source in sorted((ROOT / 'pstack/agents').glob('*.md')):
        target = ROOT / 'pstack/skills/poteto-mode/references/portable-agents' / source.name
        if not target.exists() or target.read_text() != source.read_text():
            changed.append(str(target.relative_to(ROOT)))
            if not args.check:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(source.read_text())
    if changed:
        print('\n'.join(changed))
    if args.check and changed:
        raise SystemExit('Run python3 tools/portable/prepare.py')


if __name__ == '__main__':
    main()
