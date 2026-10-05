# Install Thermos in Claude Code and Codex

Thermos runs independent correctness and code-quality reviews, then combines their findings. This fork preserves the original [Cursor plugin](../thermos/README.md) and publishes the adapted package at `portable/thermos/`.

## Install the three skills together

From the project where you want to use Thermos:

```sh
npx skills add yxhta/pstack/portable/thermos --skill '*' --agent claude-code codex
```

Add `--global` for a personal installation. Use `/thermos` in Claude Code or `$thermos` in Codex. The single-review entry points are `/thermo-nuclear-review` and `/thermo-nuclear-code-quality-review` on Claude, with `$` in place of `/` on Codex.

All three skills are explicitly invoked, matching upstream. Install them together so both reviewer rubrics and role files remain reachable. Skills-only installation does not register named agents. The adapter dispatches fresh general-purpose workers with exact file paths.

Inspect existing skill names before installation. The older `cursor-team-kit` quality-review skill has the same name and can conflict. Use one version of each skill in a project.

## Install the native plugin

Claude Code:

```text
/plugin marketplace add yxhta/pstack
/plugin install thermos@yxhta-pstack
```

Invoke `/thermos:thermos`. The plugin registers two read-only Claude agents that inherit the current model. Their file-reading tools exclude shell, edits, and nested agent dispatch. The parent supplies authorized shell checks and any required PR discussion after the independent audit.

Codex CLI:

```sh
codex plugin marketplace add yxhta/pstack
codex plugin add thermos@yxhta-pstack
```

Select the installed `thermos:thermos` skill, or explicitly ask to use Thermos. Codex uses its native subagent tools and the bundled reviewer prompts. It does not register the Claude Markdown agents.

The marketplace name remains `yxhta-pstack` to preserve existing installations. Thermos and pstack install independently. Thermos adds no startup hooks or model configuration.

## Review a branch

Ask the agent to run Thermos against an explicit base or PR, for example:

```text
Use thermos to review this branch against origin/main. Report confirmed issues and coverage gaps. Do not edit or post anything.
```

The adapter resolves the actual scope and gives both reviewers identical evidence. It starts both before waiting when the host permits. Limited capacity can run fresh reviewers sequentially with that limit disclosed. A host without subagents cannot complete the independent combined review.

The correctness reviewer first audits without PR-discussion hints. If it finds medium-or-higher issues and a PR exists, it then incorporates accessible discussion with attribution. A failed reviewer or inaccessible evidence stays visible in the final report.

## Verify a local checkout

A local branch works before it is pushed. From a fresh review project, replace the remote Skills CLI source with the absolute path to this checkout's `portable/thermos` directory. For native plugins, add this checkout as a local marketplace instead of `yxhta/pstack`.

Run these checks from the repository root:

```sh
python3 tools/portable/prepare.py --check
python3 tools/portable/validate.py
python3 -m unittest discover -s tools/portable -p 'test_*.py'
claude plugin validate ./portable/thermos
git diff --check
```

To verify copied installation contents:

```sh
mkdir /tmp/thermos-install
cd /tmp/thermos-install
npx skills add /absolute/path/to/pstack/portable/thermos --skill '*' --agent claude-code codex --copy --yes
python3 /absolute/path/to/pstack/tools/portable/check-install.py /tmp/thermos-install --package thermos
```

To check Codex discovery after installation, run `python3 tools/portable/check-codex-discovery.py /path/to/project`. Add `--plugin` for native plugin entry points. This sends no model request.

The copied-installation checker expects a fresh directory containing only that package. It compares every copied file and executable mode, then verifies rubric and role reachability. It does not infer successful model execution from installation.

See the [verification record](thermos-verification.md) for observed runs and host limits.

## Update the package

Run `npx skills update` for a Skills CLI installation. For native plugins, use the host's marketplace and plugin update controls.

The existing upstream sync regenerates and checks both pstack and Thermos. It preserves `thermos/` against the recorded upstream commit. Edit the adapter under `tools/portable/thermos-assets/`, then run `python3 tools/portable/prepare.py`. Do not edit `portable/thermos/` by hand. Added or renamed upstream Thermos skills stop generation for compatibility review.

The generator retains upstream skill text and agent prompts. Native manifests, exact required-reading links, explicit Codex invocation policy, and runtime tool mappings live in the portable package. Adapter changes update the native plugin version automatically.
