#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "$0")/../.." && pwd)
claude_bin=${CLAUDE_BIN:-claude}
case "$("$claude_bin" --version)" in
  '2.1.289 (Claude Code)') ;;
  *) echo 'This check is pinned to Claude Code 2.1.289.' >&2; exit 1 ;;
esac
scratch=$(mktemp -d)
trap 'rm -rf "$scratch"' EXIT
mkdir -p "$scratch/home" "$scratch/project"
cp -R "$root/portable/pstack-mods" "$scratch/plugin"
export HOME="$scratch/home"
export CLAUDE_CONFIG_DIR="$scratch/home/.claude"
export DISABLE_AUTOUPDATER=1 CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1
unset ANTHROPIC_API_KEY CLAUDE_CODE_OAUTH_TOKEN CLAUDE_CODE_PLUGIN_DIRS
"$claude_bin" plugin validate --strict "$scratch/plugin"
"$claude_bin" plugin test "$scratch/plugin"
(
  cd "$scratch/project"
  "$claude_bin" --plugin-dir "$scratch/plugin" -p '/pstack-bugfix status' --no-session-persistence
) | tee "$scratch/load.txt"
python3 - "$scratch/load.txt" "$scratch/plugin/.claude-plugin/types/claude-code/index.d.ts" <<'PY'
import json
from pathlib import Path
import sys
lines = Path(sys.argv[1]).read_text().splitlines()
rows = [json.loads(line.removeprefix('pstack-mods: ')) for line in lines if line.startswith('pstack-mods: {')]
if len(rows) != 1 or rows[0]['stage'] != 'off' or rows[0]['evidence']['reproduction'] is not None:
    raise SystemExit('No-inference load did not produce the expected inactive state')
if not Path(sys.argv[2]).read_text().startswith('// Written by Claude Code 2.1.289.'):
    raise SystemExit('Wrong generated native type version')
PY
python3 - "$root" "$scratch/plugin" <<'PYTHON'
from pathlib import Path
import sys
root, loaded = map(Path, sys.argv[1:])
sys.path.insert(0, str(root / 'tools/portable'))
from prepare import read_mods_tree
if read_mods_tree(root / 'portable/pstack-mods') != read_mods_tree(loaded):
    raise SystemExit('Native loading changed package content beyond generated type declarations')
PYTHON
if [[ -n "${TSC_BIN:-}" ]]; then
  "$TSC_BIN" --noEmit -p "$scratch/plugin"
else
  npm_config_cache="${npm_config_cache:-$scratch/npm-cache}" npx --yes --package typescript@5.9.3 tsc --noEmit -p "$scratch/plugin"
fi
printf '%s\n' 'Mods strict validation, native tests, generated typecheck, and no-inference load passed.'
