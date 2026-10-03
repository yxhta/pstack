#!/usr/bin/env bash
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"
if [[ -n "$(git status --porcelain)" ]]; then
  echo 'Use a clean isolated checkout for upstream sync.' >&2
  exit 1
fi
python3 tools/portable/validate.py
: "${GH_REPO:?Set GH_REPO to the fork owner/repository}"
base=$(gh repo view "$GH_REPO" --json defaultBranchRef --jq .defaultBranchRef.name)
git fetch --no-tags origin "$base"
if [[ "$(git rev-parse HEAD)" != "$(git rev-parse FETCH_HEAD)" ]]; then
  echo 'Run sync in a dedicated clean worktree at the latest origin default branch.' >&2
  exit 1
fi
open_pr=$(gh pr list --repo "$GH_REPO" --state open --base "$base" --json headRefName --jq '.[] | select(.headRefName | startswith("sync/pstack-upstream-")) | .headRefName')
if [[ -n "$open_pr" ]]; then
  echo "An upstream sync PR is already open: $open_pr. Merge or close it first."
  exit 0
fi
upstream_repository=$(python3 -c "import json; print(json.load(open('tools/portable/upstream.json'))['repository'])")
upstream_branch=$(python3 -c "import json; print(json.load(open('tools/portable/upstream.json'))['branch'])")
git fetch --no-tags "$upstream_repository" "$upstream_branch"
upstream_sha=$(git rev-parse FETCH_HEAD)
if git merge-base --is-ancestor "$upstream_sha" HEAD; then
  echo "Already contains upstream $upstream_sha."
  exit 0
fi
branch="sync/pstack-upstream-${upstream_sha:0:12}"
git switch -c "$branch"
if ! git merge --no-ff --no-commit "$upstream_sha"; then
  echo 'Upstream conflicts with the adaptation. Resolve it manually; no changes were pushed.' >&2
  git diff --name-only --diff-filter=U >&2
  exit 1
fi
UPSTREAM_SHA="$upstream_sha" python3 - <<'PY'
import json
import os
from pathlib import Path
path = Path('tools/portable/upstream.json')
data = json.loads(path.read_text())
data['last_merged_sha'] = os.environ['UPSTREAM_SHA']
path.write_text(json.dumps(data, indent=2) + '\n')
PY
python3 tools/portable/prepare.py
python3 tools/portable/validate.py
python3 -m unittest discover -s tools/portable -p 'test_*.py'
checkout_path=$PWD
install_project=$(mktemp -d)
(cd "$install_project" && npx --yes skills add "$checkout_path" --skill '*' --agent claude-code codex --copy --yes)
python3 tools/portable/check-install.py "$install_project"
git add -A
git diff --cached --check
git commit -m "chore: sync pstack upstream ${upstream_sha:0:12}"
body=$(mktemp)
trap 'rm -f "$body"' EXIT
{
  echo "Merge cursor/plugins at $upstream_sha while preserving the Claude Code/Codex adaptation."
  echo
  echo 'Validation: portable package checks, entry-point preservation tests, and whitespace checks passed in the sync job.'
  echo 'This structural validation does not prove runtime behavior. Review changed workflows in both runtimes before merging.'
  echo
  echo 'Changed pstack paths:'
  echo '```'
  git diff --name-only "origin/$base...HEAD" -- pstack
  echo '```'
  echo
  echo 'Other changed paths (includes the generated package, fork tooling, and other upstream plugins):'
  echo '```'
  git diff --name-only "origin/$base...HEAD" -- . ':!pstack'
  echo '```'
} > "$body"
git push origin "$branch"
gh pr create --repo "$GH_REPO" --base "$base" --head "$branch" \
  --title "chore: sync pstack upstream ${upstream_sha:0:12}" --body-file "$body"
