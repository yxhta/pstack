#!/usr/bin/env python3
"""Capture local Git snapshots and foreground process results without a shell."""
import hashlib
import json
import os
from pathlib import Path
import signal
import stat
import subprocess
import sys
import tempfile

LIMIT = 65536


def git(cwd, *args, input=None):
    return subprocess.check_output(
        ['git', '-c', 'core.fsmonitor=false', '-c', 'core.untrackedCache=false', '-c', 'core.filemode=true', *args],
        cwd=cwd, env={**os.environ, 'GIT_OPTIONAL_LOCKS': '0', 'GIT_NO_REPLACE_OBJECTS': '1'}, stderr=subprocess.PIPE, input=input)


def inventory(root):
    entries = git(root, 'ls-files', '--stage', '-z')
    others = git(root, 'ls-files', '--others', '--exclude-standard', '-z')
    paths = set(others.split(b'\0')) - {b''}
    for tagged in git(root, 'ls-files', '-v', '-z').split(b'\0'):
        if tagged and (tagged[:1] == b'S' or tagged[:1].islower()):
            raise ValueError('Assume-unchanged, skip-worktree, and sparse entries are unsupported')
    for entry in entries.split(b'\0'):
        if not entry:
            continue
        header, path = entry.split(b'\t', 1)
        mode, _, stage = header.split()
        if mode == b'160000' or stage != b'0':
            raise ValueError('Submodules and unmerged index entries are unsupported')
        paths.add(path)
    if paths:
        attributes = git(root, 'check-attr', '-z', '--stdin', 'filter', 'working-tree-encoding', input=b'\0'.join(sorted(paths)) + b'\0').split(b'\0')[:-1]
        if any(attributes[index] not in (b'unspecified', b'unset') for index in range(2, len(attributes), 3)):
            raise ValueError('Git content filters and working-tree encodings are unsupported')
    return entries, others, sorted(paths)


def snapshot(cwd):
    root = Path(os.fsdecode(git(cwd, 'rev-parse', '--show-toplevel')).removesuffix('\n')).resolve()
    head = git(root, 'rev-parse', '--verify', 'HEAD').strip()
    before = inventory(root)
    digest = hashlib.sha256()
    observed = {}
    head_files = {}
    for entry in git(root, 'ls-tree', '-rz', head.decode()).split(b'\0'):
        if entry:
            header, name = entry.split(b'\t', 1)
            mode, _, oid = header.split()
            head_files[name] = (mode, oid)
    index_files = {}
    for entry in before[0].split(b'\0'):
        if entry:
            header, name = entry.split(b'\t', 1)
            mode, oid, _ = header.split()
            index_files[name] = (mode, oid)
    clean = before[1] == b'' and index_files == head_files
    object_format = git(root, 'rev-parse', '--show-object-format').decode().strip()

    def signature(info):
        return (info.st_dev, info.st_ino, info.st_mode, info.st_size, info.st_mtime_ns, info.st_ctime_ns)

    def add(value):
        digest.update(len(value).to_bytes(8, 'big'))
        digest.update(value)

    for value in (os.fsencode(root), head, before[0], before[1]):
        add(value)
    for name in before[2]:
        path = root / os.fsdecode(name)
        add(name)
        try:
            info = path.lstat()
        except FileNotFoundError:
            add(b'deleted')
            observed[path] = None
            clean = False
            continue
        if not stat.S_ISREG(info.st_mode):
            raise ValueError('Only regular files are supported: ' + os.fsdecode(name))
        if any(parent.is_symlink() for parent in path.parents if parent != root and root in parent.parents):
            raise ValueError('Symlinked parent directory is unsupported')
        add(str(stat.S_IMODE(info.st_mode)).encode())
        with path.open('rb') as stream:
            content = hashlib.file_digest(stream, 'sha256').digest()
            stream.seek(0)
            blob = hashlib.new(object_format)
            blob.update(b'blob ' + str(info.st_size).encode() + b'\0')
            for chunk in iter(lambda: stream.read(1048576), b''):
                blob.update(chunk)
            mode = b'100755' if info.st_mode & 0o111 else b'100644'
            clean = clean and head_files.get(name) == (mode, blob.hexdigest().encode())
        after = path.stat()
        if signature(after) != signature(info):
            raise ValueError('File changed during snapshot: ' + os.fsdecode(name))
        add(content)
        observed[path] = signature(after)
    for path, expected in observed.items():
        try:
            actual = signature(path.lstat())
        except FileNotFoundError:
            actual = None
        if actual != expected:
            raise ValueError('File changed during snapshot: ' + str(path))
    if before != inventory(root) or head != git(root, 'rev-parse', '--verify', 'HEAD').strip():
        raise ValueError('Git state changed during snapshot')
    return {'schema': 1, 'digest': digest.hexdigest(), 'head': head.decode(),
            'root': str(root), 'files': len(before[2]), 'clean': clean}


def run(cwd, request):
    argv, timeout = request['argv'], request['timeoutMs']
    if (not isinstance(argv, list) or not argv or len(argv) > 128
            or not all(isinstance(arg, str) and '\0' not in arg for arg in argv)
            or not argv[0] or not isinstance(timeout, int) or not 1000 <= timeout <= 600000):
        raise ValueError('Invalid process request')
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        process = subprocess.Popen(argv, cwd=cwd, stdin=subprocess.DEVNULL,
                                   stdout=stdout, stderr=stderr, start_new_session=True)
        timed_out = False

        def interrupted(signum, frame):
            raise InterruptedError('Evidence helper interrupted')

        previous = {kind: signal.signal(kind, interrupted) for kind in (signal.SIGTERM, signal.SIGINT)}
        try:
            try:
                process.wait(timeout=timeout / 1000)
            except subprocess.TimeoutExpired:
                timed_out = True
        finally:
            for kind, handler in previous.items():
                signal.signal(kind, handler)
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
        result = {'schema': 1, 'argv': argv, 'exitCode': process.returncode, 'timedOut': timed_out}
        for name, stream in (('stdout', stdout), ('stderr', stderr)):
            stream.seek(0)
            data = stream.read(LIMIT + 1)
            result[name] = data[:LIMIT].decode('utf-8', errors='replace')
            result[name + 'Truncated'] = len(data) > LIMIT
        return result


def review_diff(cwd, base):
    before = snapshot(cwd)
    root = Path(before['root'])
    base_files = {}
    for entry in git(root, 'ls-tree', '-rz', base).split(b'\0'):
        if entry:
            header, name = entry.split(b'\t', 1)
            mode, kind, oid = header.split()
            if kind != b'blob' or mode not in (b'100644', b'100755'):
                raise ValueError('Unsupported review baseline entry')
            base_files[name] = (mode, oid)
    _, others, current_paths = inventory(root)
    current_paths = set(current_paths)
    object_format = git(root, 'rev-parse', '--show-object-format').decode().strip()
    changed = {}
    for name in sorted(set(base_files) | current_paths):
        path = root / os.fsdecode(name)
        current = None
        data = None
        if name in current_paths and path.exists():
            info = path.lstat()
            if not stat.S_ISREG(info.st_mode):
                raise ValueError('Only regular review files are supported')
            data = path.read_bytes()
            blob = hashlib.new(object_format, b'blob ' + str(len(data)).encode() + b'\0' + data)
            mode = b'100755' if info.st_mode & 0o111 else b'100644'
            current = (mode, blob.hexdigest().encode())
        if base_files.get(name) != current:
            changed[name] = (current, data if current else None)
    if len(changed) > 100:
        raise ValueError('Review exceeds the supported 100-file limit')
    with tempfile.TemporaryDirectory(prefix='pstack-review-') as temporary:
        directory = Path(temporary)
        (directory / 'a').mkdir()
        (directory / 'b').mkdir()
        for name, (current, data) in changed.items():
            if name in base_files:
                mode, oid = base_files[name]
                path = directory / 'a' / os.fsdecode(name)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(git(root, 'cat-file', 'blob', oid.decode()))
                path.chmod(0o755 if mode == b'100755' else 0o644)
            if current:
                path = directory / 'b' / os.fsdecode(name)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
                path.chmod(0o755 if current[0] == b'100755' else 0o644)
        result = subprocess.run(
            ['git', '-c', 'core.filemode=true', 'diff', '--no-index', '--binary',
             '--no-ext-diff', '--no-textconv', '--no-renames', '--no-color', '--src-prefix=', '--dst-prefix=', 'a', 'b'],
            cwd=directory, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.returncode not in (0, 1):
            raise ValueError('Raw review diff failed: ' + result.stderr.decode(errors='replace'))
        if len(result.stdout) > 200000:
            raise ValueError('Review diff exceeds the supported 200000-byte limit')
    if snapshot(root)['digest'] != before['digest']:
        raise ValueError('Code changed while preparing the review diff')
    return {'schema': 1, 'diff': result.stdout.decode('utf-8', errors='replace'),
            'files': [str(root / os.fsdecode(name)) for name, (current, _) in changed.items() if current],
            'untracked': [os.fsdecode(name) for name in others.split(b'\0') if name]}


def main():
    action, cwd = sys.argv[1:3]
    if action == 'snapshot':
        result = snapshot(cwd)
    elif action == 'run':
        result = run(cwd, json.loads(sys.argv[3]))
    elif action == 'diff':
        result = review_diff(cwd, sys.argv[3])
    else:
        raise ValueError('Unknown evidence operation')
    print(json.dumps(result, ensure_ascii=True))


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, subprocess.SubprocessError, KeyError, IndexError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
