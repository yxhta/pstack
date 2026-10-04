#!/usr/bin/env python3
"""Report local Git evidence, without inferring usage or recommending removal."""

import argparse
from dataclasses import asdict, dataclass, field
import json
import math
import os
from pathlib import Path
import re
import stat
import subprocess
import time


@dataclass
class WorktreeAudit:
    path: str
    branch: str | None = None
    detached: bool = False
    head: str | None = None
    bare: bool = False
    locked: bool = False
    lock_reason: str | None = None
    prunable: bool = False
    prune_reason: str | None = None
    tracked_changes: int | None = None
    untracked_files: int | None = None
    contained_in_base: bool | None = None
    usage: str = 'unknown'
    disposition: str = 'audit-error'
    errors: list[str] = field(default_factory=list)


class AuditError(Exception):
    pass


def checked_directory(path):
    path = Path(os.path.abspath(path))
    for component in (*reversed(path.parents), path):
        try:
            mode = component.lstat().st_mode
        except OSError as error:
            raise AuditError(f'Cannot inspect directory {component}: {error}') from error
        if stat.S_ISLNK(mode):
            raise AuditError(f'Refusing symlink directory: {component}')
        if not stat.S_ISDIR(mode):
            raise AuditError(f'Not a directory: {component}')
    if (path / '.git').is_symlink():
        raise AuditError(f'Refusing symlink Git metadata: {path / ".git"}')
    return path


class LocalGit:
    def __init__(self, timeout):
        self.deadline = time.monotonic() + timeout
        self.env = {key: value for key, value in os.environ.items() if not key.startswith('GIT_')}
        self.env.update(GIT_OPTIONAL_LOCKS='0', GIT_NO_LAZY_FETCH='1',
                        GIT_TERMINAL_PROMPT='0', LC_ALL='C')
        # Trace2 reads global/system targets before command-line -c overrides.
        self.env.update(GIT_TRACE2='0', GIT_TRACE2_EVENT='0', GIT_TRACE2_PERF='0')

    def run(self, path, *args, allowed=(0,)):
        checked_directory(path)
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise AuditError('Audit time budget exhausted')
        command = ['git', '-c', 'core.fsmonitor=false', '-c', 'core.untrackedCache=false',
                   '-C', str(path), *args]
        try:
            result = subprocess.run(command, capture_output=True, env=self.env,
                                    timeout=min(10, remaining))
        except (OSError, subprocess.TimeoutExpired) as error:
            raise AuditError(f'git {args[0]} failed: {error}') from error
        if result.returncode not in allowed:
            detail = os.fsdecode(result.stderr).strip()
            raise AuditError(f'git {args[0]} exited {result.returncode}: {detail}')
        return result


def parse_worktrees(data):
    if not data or not data.endswith(b'\0\0'):
        raise AuditError('Invalid NUL-delimited worktree listing')
    rows = []
    for record in data[:-2].split(b'\0\0'):
        fields = {}
        for item in record.split(b'\0'):
            key, _, value = item.partition(b' ')
            if key in fields or key not in (b'worktree', b'HEAD', b'branch', b'detached',
                                             b'bare', b'locked', b'prunable'):
                raise AuditError('Unrecognized or repeated worktree field')
            fields[key] = os.fsdecode(value)
        path = fields.get(b'worktree')
        if not path or not os.path.isabs(path):
            raise AuditError('Worktree listing lacks an absolute path')
        row = WorktreeAudit(path=path, branch=fields.get(b'branch'),
                            detached=b'detached' in fields, head=fields.get(b'HEAD'),
                            bare=b'bare' in fields, locked=b'locked' in fields,
                            lock_reason=fields.get(b'locked'), prunable=b'prunable' in fields,
                            prune_reason=fields.get(b'prunable'))
        if row.head and not re.fullmatch(r'[0-9a-f]{40}|[0-9a-f]{64}', row.head):
            row.errors.append('Invalid worktree HEAD')
            row.head = None
        if row.head and set(row.head) == {'0'}:
            row.head = None
        if row.detached == bool(row.branch) and not row.bare:
            row.errors.append('Missing or conflicting branch/detached state')
        rows.append(row)
    if len({row.path for row in rows}) != len(rows):
        raise AuditError('Duplicate worktree paths')
    return rows


def status_counts(data):
    if data and not data.endswith(b'\0'):
        raise AuditError('Invalid NUL-delimited status')
    entries = data.split(b'\0')[:-1]
    tracked = untracked = index = 0
    while index < len(entries):
        entry = entries[index]
        if len(entry) < 4 or entry[2:3] != b' ' or not entry[3:]:
            raise AuditError('Invalid status entry')
        state = entry[:2]
        if state == b'??':
            untracked += 1
        elif state == b'!!' or any(char not in b' MADRCUT?' for char in state):
            raise AuditError('Unexpected status state')
        else:
            tracked += 1
            if b'R' in state or b'C' in state:
                index += 1
                if index >= len(entries) or not entries[index]:
                    raise AuditError('Status rename lacks its original path')
        index += 1
    return tracked, untracked


def audit(repo, base, timeout, max_worktrees):
    repo = os.path.abspath(repo)
    git = LocalGit(timeout)
    report = {'repo': repo, 'base': {'ref': base, 'head': None,
              'source': 'explicit' if base is not None else 'origin/HEAD', 'local_only': True},
              'worktrees': [], 'errors': []}
    try:
        rows = parse_worktrees(git.run(repo, 'worktree', 'list', '--porcelain', '-z').stdout)
    except AuditError as error:
        report['errors'].append(str(error))
        return report
    base_error = None
    try:
        if base is None:
            result = git.run(repo, 'symbolic-ref', '--quiet', 'refs/remotes/origin/HEAD', allowed=(0, 1))
            if result.returncode:
                raise AuditError('No local refs/remotes/origin/HEAD; pass --base explicitly')
            base = os.fsdecode(result.stdout).rstrip('\n')
            report['base']['ref'] = base
        result = git.run(repo, 'rev-parse', '--verify', '--end-of-options', base + '^{commit}')
        report['base']['head'] = result.stdout.decode('ascii').strip()
    except AuditError as error:
        base_error = str(error)
        report['errors'].append(base_error)
    for index, row in enumerate(rows):
        if base_error:
            row.errors.append('Base containment unavailable: ' + base_error)
        try:
            if index >= max_worktrees:
                raise AuditError(f'Worktree inspection limit ({max_worktrees}) exceeded')
            if row.bare:
                raise AuditError('Bare repository has no working-tree status')
            checked_directory(row.path)
            if row.head is None:
                raise AuditError('Worktree has no valid commit HEAD (possibly unborn)')
            root = os.fsdecode(git.run(row.path, 'rev-parse', '--show-toplevel').stdout[:-1])
            if os.path.normpath(root) != os.path.normpath(row.path):
                raise AuditError('Worktree path no longer matches its Git root')
            head = git.run(row.path, 'rev-parse', '--verify', 'HEAD^{commit}').stdout.decode('ascii').strip()
            if head != row.head:
                raise AuditError('Worktree HEAD changed since listing')
            filters = git.run(row.path, 'config', '--null', '--get-regexp',
                              r'^filter\..*\.(clean|process)$', allowed=(0, 1))
            if filters.returncode == 0:
                raise AuditError('Configured clean/process filters prevent read-only status inspection')
            index_entries = git.run(row.path, 'ls-files', '--stage', '-z').stdout.split(b'\0')
            if any(entry.startswith(b'160000 ') for entry in index_entries):
                raise AuditError('Submodule status is unavailable without inspecting nested configuration')
            row.tracked_changes, row.untracked_files = status_counts(git.run(
                row.path, 'status', '--porcelain=v1', '-z', '--untracked-files=all',
                '--ignore-submodules=all').stdout)
            if not base_error:
                result = git.run(repo, 'merge-base', '--is-ancestor', row.head,
                                 report['base']['head'], allowed=(0, 1))
                row.contained_in_base = result.returncode == 0
        except (AuditError, UnicodeError) as error:
            row.errors.append(str(error))
        if row.errors:
            row.disposition = 'audit-error'
        elif row.locked:
            row.disposition = 'hold-locked'
        elif row.tracked_changes or row.untracked_files:
            row.disposition = 'hold-dirty'
        else:
            row.disposition = 'hold-unknown-usage'
        report['worktrees'].append(asdict(row))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__, epilog=(
        'Uses existing local refs only. Usage is always unknown. No fetch, history scans, '
        'size traversal, or removal. Use physical paths without symlink components (for example, '
        'pwd -P on macOS). Configured clean/process filters and submodules leave status unknown. '
        'Inherited GIT_* overrides are ignored. Exit 1 means incomplete evidence; holds exit 0.'))
    parser.add_argument('path', nargs='?', help='Repository path (defaults to current directory)')
    parser.add_argument('--repo', help='Repository path, as an alternative to the positional path')
    parser.add_argument('--base', help='Local base ref; otherwise use local refs/remotes/origin/HEAD')
    parser.add_argument('--timeout', type=float, default=30, help='Total Git time budget in seconds (default 30)')
    parser.add_argument('--max-worktrees', type=int, default=100, help='Maximum worktrees to inspect (default 100)')
    args = parser.parse_args()
    if args.path is not None and args.repo is not None:
        parser.error('use either the positional path or --repo')
    if not math.isfinite(args.timeout) or args.timeout <= 0 or args.max_worktrees < 1:
        parser.error('--timeout and --max-worktrees must be positive and finite')
    report = audit(args.repo or args.path or '.', args.base, args.timeout, args.max_worktrees)
    print(json.dumps(report, indent=2, ensure_ascii=True))
    return int(bool(report['errors'] or any(row['errors'] for row in report['worktrees'])))


if __name__ == '__main__':
    raise SystemExit(main())
