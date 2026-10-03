---
name: sync-pstack-upstream
description: Review or integrate cursor/plugins updates into the yxhta/pstack source fork and prepare a sync PR. Use for fork maintenance, not consumer installation updates.
---

# Sync pstack upstream

Use this in a source checkout of `yxhta/pstack`, not an installed plugin cache. If only installed skills are available, locate an existing source checkout or clone the fork into an isolated workspace. Inspect local changes before choosing a worktree; preserve unrelated work.

For a check-only request, complete only the review below and return findings. Do not create a branch, edit files, commit, or push.

## Review the update

1. Read `tools/portable/upstream.json`, `README_PORTABLE.md`, the generator, and the sync script in the checkout. Use the recorded repository, branch, and last merged SHA rather than remembered revisions.
2. Fetch the recorded upstream branch. If its head is already an ancestor of the fork's main, report that there is no pending update.
3. Read the commit range and the full pstack diff and the `cursor-team-kit/skills/deslop/SKILL.md` and `cursor-team-kit/LICENSE` dependency diffs from the recorded SHA to the fetched head. Separate changes to engineering procedures from Cursor-specific tools, model settings, dispatch fields, dependencies, and transcript formats. Report unrelated upstream repository changes separately.
4. Trace every changed runtime assumption to the relevant adaptation or generator behavior. Keep upstream's engineering choices unless the user explicitly asks to change policy. Do not describe a model name or tool as supported without checking the current harness.

## Integrate in a worktree

1. Create a sync branch from the current fork main in a dedicated worktree. Check for an existing sync PR before creating another.
2. Merge the fetched upstream revision. If Git reports a conflict, inspect both intents and the merge base. Resolve fork-owned adapters and packaging without editing the final upstream-owned source tree. Stop and report any conflict whose intended result remains unknown. Never force-push or silently choose one side for the entire repository.
3. Record the exact merged upstream SHA. Update only fork-owned compatibility instructions, packaging, and generator behavior where the changed runtime requires it.
4. Regenerate the complete portable package. Do not edit generated files by hand. A removed or renamed upstream skill must disappear from the generated package.

## Verify and prepare the PR

Run these commands from the checkout. The generator checks raw source integrity against the recorded pin before writing.

```sh
python3 tools/portable/prepare.py
python3 tools/portable/prepare.py --check
python3 tools/portable/validate.py
python3 -m unittest discover -s tools/portable -p 'test_*.py'
git diff --check
```

Install into an isolated project with `npx skills add <checkout-path> --skill '*' --agent claude-code codex --copy --yes`. Run `python3 <checkout-path>/tools/portable/check-install.py <project-path>`. If available, run `claude plugin validate <checkout-path>/portable/pstack`.

The unattended script requires a clean dedicated checkout at the latest `origin` default branch. For unattended sync, `GH_REPO=yxhta/pstack bash tools/portable/sync-upstream.sh` checks for an open sync PR, merges, generates, validates, and opens a PR. It stops before push on conflicts or failed checks. Verify both Claude Code and Codex installations against the generated bundle. For changed executable workflows, run the affected behavior on its real surface where available. Treat an unavailable tool or untested runtime as a named gap, not a pass.

Read the final diff. Require the upstream-owned source paths to match the recorded upstream revision exactly. Include added and removed files and executable modes in this check. The portable package must regenerate without a diff.

Commit and open or update a sync PR when the user's request authorizes integration. For a check-only request, return the findings without pushing changes. Keep the PR merge as the operator's decision unless explicitly authorized. Summarize the upstream behavior changes, adaptation changes, validation evidence, and unresolved compatibility gaps. A green structural check does not establish semantic compatibility.
