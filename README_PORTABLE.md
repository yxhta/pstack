# pstack for Claude Code and Codex

This is a fork of [cursor/plugins](https://github.com/cursor/plugins), maintained for the pstack skills only. Upstream's playbooks and principles are shared by both runtimes. The original [pstack README](pstack/README.md) remains the Cursor guide; the instructions here apply to this fork.

## Install

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

For a skills-only installation, clone this repository and keep it in place, then link each directory under `pstack/skills/` into your runtime's user skill directory. Symlink whole directories so the runtime adaptation and other relative references stay reachable. Existing skill names such as `swarm` and `architect` may collide: inspect existing installations before replacing them.

Read [compatibility.md](pstack/compatibility.md) for the tool mappings, paths, and limitations. Cursor-only `make-bot-ui`, Benny automations, cloud workers, and transcript parsers are not ported. Optional cursor-team-kit dependencies are not included. Installation and structural validation do not establish that every workflow runs correctly; check a real task in each runtime.

## Upstream updates

The **Sync pstack upstream** GitHub Actions workflow checks daily and can be run manually. It merges upstream main into a dedicated branch, reapplies the small entry-point adaptation, records the upstream SHA, validates it, and opens a PR. It never merges into main automatically. The complete repository history is retained because this is a GitHub fork, but the PR body distinguishes pstack changes from unrelated upstream plugin changes.

Enable GitHub Actions in this fork and allow Actions to create pull requests under **Settings → Actions → General**. Scheduled workflows may be disabled by GitHub after prolonged inactivity; run or re-enable the workflow when needed. If Actions is not allowed to create PRs, supply a suitably scoped repository secret `UPSTREAM_SYNC_TOKEN`; do not commit credentials. A PR opened with the default GITHUB_TOKEN does not trigger other PR workflows, so the sync job runs validation itself.

Only one sync PR is kept open. Review and merge or close it before the next update. A merge conflict or validation failure fails the workflow with logs instead of overwriting the local adaptation. Resolve the conflicting upstream change on a branch and run the checks below. New upstream skills receive the same adaptation automatically.

```sh
python3 tools/portable/prepare.py
python3 tools/portable/validate.py
python3 -m unittest discover -s tools/portable -p 'test_*.py'
git diff --check
claude plugin validate ./pstack
```

Upstream-owned files receive only a runtime-adaptation link after their frontmatter and normalized skill names. Runtime-specific manifests, agents, scripts, this guide, and compatibility.md are maintained separately. Change behavior in compatibility.md only to adapt the runtime; keep policy changes explicit and separate. Preserve the upstream MIT license and attribution.
