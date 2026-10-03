# pstack for Claude Code and Codex

This is a fork of [cursor/plugins](https://github.com/cursor/plugins), maintained for the pstack skills only. Upstream's playbooks and principles are shared by both runtimes. The original [pstack README](pstack/README.md) remains the Cursor guide; the instructions here apply to this fork.

## Install

### Skills CLI (Claude Code and Codex)

```sh
npx skills add yxhta/pstack --skill '*' --agent claude-code codex
```

This installs the shared skill bundle for both agents in the current project. Add `--global` for a personal installation. Install all pstack skills together: the entry points share the runtime adaptation and other resources under poteto-mode. The bundle includes the adaptation and agent reference prompts, but it does not register plugin agent types or plugin namespaces. Use `/poteto-mode` on Claude Code and `$poteto-mode` on Codex; the adaptation describes the general-purpose agent fallback.

```sh
npx skills update
```

Upstream synchronization updates this fork through PRs. After merging a sync PR, update the installed skills separately with the command above.

### Native plugins

Claude Code:

```text
/plugin marketplace add yxhta/pstack
/plugin install pstack@yxhta-pstack
```

Codex CLI:

```sh
codex plugin marketplace add yxhta/pstack
codex plugin add pstack@yxhta-pstack
```

Start with `/pstack:poteto-mode` on Claude Code. On Codex, select the installed `pstack:poteto-mode` skill or ask to use poteto-mode. Run setup-pstack to configure roles. Missing roles inherit the session model; multi-model diversity needs models that your runtime actually exposes. No startup hook or automatic routing is installed.

For a skills-only installation, clone this repository and keep it in place, then link each directory under `portable/pstack/skills/` into your runtime's user skill directory. Install all skill directories together so the shared runtime adaptation and other relative references stay reachable. Existing skill names such as `swarm` and `architect` may collide: inspect existing installations before replacing them.

Read [runtime adaptation](tools/portable/assets/skills/poteto-mode/references/runtime-adaptation.md) for the tool mappings, paths, and limitations. Cursor-only `make-bot-ui`, Benny automations, cloud workers, and transcript parsers are not ported. Optional cursor-team-kit dependencies are not included. Installation and structural validation do not establish that every workflow runs correctly; check a real task in each runtime.

## Upstream updates

The **Sync pstack upstream** GitHub Actions workflow checks daily and can be run manually. It merges upstream main into a dedicated branch, records the upstream SHA, regenerates the portable package, validates it, and opens a PR. It never merges into main automatically. The complete repository history is retained because this is a GitHub fork. The PR body separates raw pstack paths from other changed paths, which include generated output, fork tooling, and other upstream plugins.

Enable GitHub Actions in this fork and allow Actions to create pull requests under **Settings → Actions → General**. Scheduled workflows may be disabled by GitHub after prolonged inactivity; run or re-enable the workflow when needed. If Actions is not allowed to create PRs, supply a suitably scoped repository secret `UPSTREAM_SYNC_TOKEN`; do not commit credentials. A PR opened with the default GITHUB_TOKEN does not trigger other PR workflows, so the sync job runs validation itself.

The sync script requires a clean dedicated checkout at the latest `origin` default branch. Only one sync PR is kept open. Review and merge or close it before the next update. A merge conflict or validation failure fails the workflow with logs instead of overwriting the local adaptation. Resolve the conflicting upstream change on a branch and run the checks below. New upstream skills receive the same adaptation automatically.

```sh
python3 tools/portable/prepare.py
python3 tools/portable/validate.py
python3 -m unittest discover -s tools/portable -p 'test_*.py'
git diff --check
claude plugin validate ./portable/pstack
```

The raw `pstack/` tree and root `README.md` match `tools/portable/upstream.json` byte for byte, including executable modes. Do not edit these source paths. The generator copies the complete upstream package to `portable/pstack/`, adds runtime mappings, and normalizes skill names there. It copies agents, licenses, scripts, and references. It rejects input symlinks and overlay collisions instead of overwriting unfamiliar upstream files.

Edit fork-owned inputs under `tools/portable/assets/` and rerun `python3 tools/portable/prepare.py`. Never edit `portable/pstack/` by hand. The generated package is committed intentionally so every installation works without a build. `python3 tools/portable/prepare.py --check` detects missing, stale, modified, or mode-changed output. Root marketplaces point to this single package. Source files remain unpatched when upstream changes a skill header.

Native plugin versions include the upstream pin and a digest of the package contents and executable modes. Adapter-only changes receive a new version without a manual bump. Template version fields are excluded from the digest.

Git whitespace checks apply to fork-owned inputs. `.gitattributes` exempts the upstream source paths and generated package so upstream whitespace remains intact. Source integrity and generation checks cover those paths.

Use `$sync-pstack-upstream` on Codex or `/sync-pstack-upstream` on Claude Code to review and integrate upstream changes from a source checkout. A native Claude plugin exposes `/pstack:sync-pstack-upstream`. The skill reads the recorded pin and full upstream diff, reviews changed runtime assumptions, regenerates, verifies, and prepares a PR. It does not merge automatically. Consumer installation updates still use `npx skills update`.

Mechanical merge conflicts in raw `pstack/` are avoided by keeping it pristine. Conflicts in root marketplaces or fork-owned automation can still occur. Semantic changes to upstream workflows still require review and actual execution on the affected runtime. Automated sync PRs report this review gap rather than claiming complete runtime compatibility.
