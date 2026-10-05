#!/usr/bin/env python3
"""Check installed Thermos discovery through Codex without starting a model turn."""
import argparse
import json
from pathlib import Path
import queue
import subprocess
import tempfile
import threading
import time

ROLES = {'thermos', 'thermo-nuclear-review', 'thermo-nuclear-code-quality-review'}


def check_discovery(project: Path, plugin: bool = False) -> list[dict]:
    project = project.resolve(strict=True)
    if not project.is_dir():
        raise ValueError(f'Expected a project directory: {project}')
    with tempfile.TemporaryFile(mode='w+') as errors:
        process = subprocess.Popen(['codex', 'app-server', '--stdio'], stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE, stderr=errors, text=True, bufsize=1)
        messages = queue.Queue()

        def read_messages():
            for line in process.stdout:
                messages.put(line)
            messages.put(None)

        reader = threading.Thread(target=read_messages, daemon=True)
        reader.start()

        def request(identifier, method, parameters):
            process.stdin.write(json.dumps({'id': identifier, 'method': method, 'params': parameters}) + '\n')
            process.stdin.flush()
            deadline = time.monotonic() + 30
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError(f'Codex did not finish {method} within 30 seconds')
                try:
                    line = messages.get(timeout=remaining)
                except queue.Empty as error:
                    raise TimeoutError(f'Codex did not finish {method} within 30 seconds') from error
                if line is None:
                    errors.seek(0)
                    raise RuntimeError('Codex app-server stopped: ' + errors.read())
                message = json.loads(line)
                if message.get('id') == identifier:
                    if 'error' in message:
                        raise RuntimeError(json.dumps(message['error']))
                    return message['result']

        try:
            request(0, 'initialize', {'clientInfo': {'name': 'thermos-discovery-check', 'version': '1.0'}})
            process.stdin.write(json.dumps({'method': 'initialized', 'params': {}}) + '\n')
            process.stdin.flush()
            response = request(1, 'skills/list', {'cwds': [str(project.resolve())], 'forceReload': True})
            entry, = response['data']
            if entry['errors']:
                raise ValueError('Skill loader errors: ' + json.dumps(entry['errors']))
            expected = {'thermos:' + name for name in ROLES} if plugin else ROLES
            found = [skill for skill in entry['skills'] if skill['name'] in expected]
            if {skill['name'] for skill in found} != expected or not all(skill['enabled'] for skill in found):
                raise ValueError('Expected all three enabled Thermos entry points: ' + json.dumps(found))
            return [{key: skill.get(key) for key in ('name', 'path', 'enabled', 'pluginId')} for skill in found]
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            reader.join(timeout=5)
            process.stdin.close()
            process.stdout.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('project', type=Path)
    parser.add_argument('--plugin', action='store_true', help='Check namespaced native plugin skills instead of project skills')
    args = parser.parse_args()
    try:
        print(json.dumps(check_discovery(args.project, args.plugin), indent=2))
    except (OSError, ValueError, RuntimeError, queue.Empty) as error:
        parser.exit(1, f'Thermos discovery failed: {error}\n')
