# Opt-in bug-fix gates for Claude Code

`pstack-mods` is a separate, optional Claude Code plugin. It tracks a bug fix through reproduction, a changed code snapshot, verification, and two independent Thermos reviews. It never marks a pipeline verified from the parent model's claim that tests or reviews passed.

The existing pstack and Thermos packages and Codex behavior are unchanged. This early-access adapter requires Claude Code **2.1.289**, Python **3.11 or newer**, and Git on Linux or macOS. Windows is not supported by this version. Later Claude versions should be checked against their own generated declarations before relying on the adapter.

## Try it without a persistent installation

From a clone of this repository, launch Claude Code in the repository being fixed:

```sh
claude --plugin-dir /absolute/path/to/pstack/portable/pstack-mods
```

For a persistent installation that you choose yourself:

```text
/plugin marketplace add yxhta/pstack
/plugin install pstack-mods@yxhta-pstack
```

Loading the plugin registers its command and tool. Gates remain off until you start a recipe. This adapter does not enable itself through the existing pstack plugin, Codex, or the Skills CLI.

## Start a bug fix

First identify a reproducible failure and the project's verification commands. Enter this command yourself, adapting its argv arrays and failure text:

```text
/pstack-bugfix start {"repro":["python3","-B","tests/repro.py"],"expectedExit":1,"contains":"AssertionError: wrong value","verify":[["python3","-B","-m","unittest","discover"]],"timeoutMs":120000}
```

The command records the recipe. It does not immediately run a process or a model. Starting a recipe authorizes the adapter to run those exact commands when its pipeline tool is called and to start the two reviewer agents. Reviewers use the session's model and plan. No alternate API, authentication, or paid fallback is configured.

Commands run in the Git repository root with no shell and no interactive stdin. They have the host user's filesystem and network access. Choose local tests whose side effects you intend. Shell expansions, pipes, and redirections are not interpreted, although explicitly configuring an interpreter or shell still runs that program. Keep test output and build artifacts ignored by Git so they do not change the checked snapshot. The reproduction must start from a clean committed working tree. Commit a newly added regression test first on your working branch. This keeps the reproduced baseline and review diff aligned; dirty-start baselines are deliberately unsupported.

Tell Claude to use `mcp__pstack-mods__bugfix` for each stage:

1. `reproduce` runs the configured reproduction. Its actual exit code must equal `expectedExit`, and stdout or stderr must contain `contains`. A missing program, timeout, signal, malformed helper result, or code change during the check cannot count. Edit, Write, and NotebookEdit are gated until this evidence exists.
2. Apply the fix. The current code snapshot must differ from the reproduced snapshot. This is a mechanical change check, not proof that a particular edit fixes the cause.
3. `verify` reruns the original reproduction and every verification command. Every process must exit zero, and the snapshot must remain unchanged. A command that claims success in text but exits unsuccessfully cannot pass.
4. `review` starts two fresh read-only agents, one for correctness and one for code quality. They read the bundled upstream Thermos roles and complete rubrics, plus every surviving changed or untracked file in full. The adapter observes successful full-file Read results, checks the host's child identity, and accepts only matching final `turn.complete` reports. Both must report clean local coverage for the exact verified snapshot.
5. The status becomes `verified` only after all of those gates pass. Publication, merge, and deployment are separate actions and are never performed by this adapter.

Repeated successful tool actions reuse current evidence; repeated `start` with the same recipe does not reset it or resume a paused pipeline. Cancel first to replace a recipe.

## Inspect, pause, and recover

```text
/pstack-bugfix status
/pstack-bugfix pause
/pstack-bugfix resume
/pstack-bugfix cancel
```

The line below the prompt and the band above it show the current stage, missing evidence, and failure reason. `status` provides the captured exits, output, snapshot IDs, and reviewer identities. Stages are `off`, `repro`, `fix`, `verification`, `independent review`, `verified`, `paused`, and `blocked`.

A source change invalidates passing verification and both reviews. The original failing reproduction stays as the baseline. The adapter checks before evidence-producing actions and normal completion, after checks, and every five seconds while active and idle. Known edits invalidate immediately, even if an edit fails. Changes to Git HEAD, the index, file names, bytes, or executable modes also invalidate evidence.

An interrupted parent turn pauses the pipeline. Failed checks or incomplete reviews block it with a reason. `resume` keeps only live reproduction evidence and requires fresh verification and reviews. If a process is still finishing, wait before resuming. Pausing or canceling discards its result; it does not promise to terminate every descendant process or already spawned read-only reviewer. A reviewer has five minutes to return a final report.

A reload, session restart, `/clear`, or `/resume` never restores successful evidence from disk. The plugin stores only a session-scoped reminder that a pipeline existed. Any stored value, including a tampered one, can at most produce `paused`; supply a new recipe and reproduce again. A new session does not inherit another session's pipeline.

## What the gates do and do not prove

- The snapshot covers tracked files, index state, HEAD, and non-ignored untracked regular files. Ignored files, environment variables, external services, dependency caches, databases, and other repositories are outside it. Changes there require you to rerun or restart appropriately. Symlinks, submodules, unresolved merges, assume-unchanged/skip-worktree index flags, content filters, and working-tree encoding attributes are deliberately unsupported. Raw baseline bytes and Git modes are compared with the committed tree rather than trusting cached Git status. Review paths and patches also use raw before-and-after file contents and ignore Git replacement refs. A preserved modification time cannot hide a fix from the reviewers.
- Checks run against the working directory, not an atomic filesystem snapshot. Changes observed between checks invalidate evidence. A malicious edit-and-restore race, altered host, or hostile plugin is outside this workflow's trust model.
- Configured exit codes and failure text identify an observed test execution. They do not prove that the selected command is a meaningful test, that a suite covered every case, or that the test itself is honest.
- Fresh child identity and observed reads establish independent execution and reading coverage. A clean model verdict remains a review judgment, not proof of bug absence. The reviews are local and pre-PR; PR discussion and external integration checks require separate work.
- Reviews larger than 100 changed files or a 200,000-byte diff block. A token-truncated or partial Read does not count as a complete file read. Reduce the review scope or use the ordinary portable workflow; do not label the incomplete gate verified.
- Process output is retained up to 64 KiB per stream with explicit truncation flags. A child signal is distinguished from a test's nonzero exit.
- Mods are early-access middleware. Unhandled errors, hook timeouts, other plugins, unloading the mod, or disabled Mods can bypass hooks. Catch handlers improve the normal failure path; they do not turn this into an enforceable security policy.
- `Stop` only observes normal completion. It requests at most one continuation when evidence is missing, then pauses. It allows a wait for pending reviewers without claiming verification. It does not intercept every interruption or prevent a model from writing inaccurate prose.
- The edit guard covers named editor tools. Bash, arbitrary MCP tools, and other channels can change files. No Bash-string parser or universal write/push/deploy guarantee is claimed. Snapshot invalidation is the safeguard for changes the adapter observes.

## Maintain and verify

Edit `tools/portable/mods-assets/`, then regenerate. Never edit `portable/pstack-mods/` directly. Its version hashes content and executable modes. Native-generated declarations under `.claude-plugin/types/` are excluded from that hash and the freshness check. The committed TypeScript config stays checked. Required Thermos source files and their license are copied unchanged from the repository's recorded upstream pin.

```sh
python3 tools/portable/prepare.py
python3 tools/portable/validate.py
python3 -m unittest discover -s tools/portable -p 'test_*.py'
CLAUDE_BIN=/path/to/claude-2.1.289 bash tools/portable/check-mods.sh
git diff --check
```

`check-mods.sh` uses a disposable copy and isolated Claude home. It runs strict validation, the official native test harness, a real no-inference command load, and TypeScript 5.9.3 against declarations generated by that binary. It never runs an authenticated model task or changes your normal Claude settings. The test harness stubs model/host responses; it is not evidence of a completed real-model bug fix.

The implementation follows the official [creation guide](https://code.claude.com/docs/en/plugins/mods/create), [API guide](https://code.claude.com/docs/en/plugins/mods/api), [event guide](https://code.claude.com/docs/en/plugins/mods/events), [reference](https://code.claude.com/docs/en/plugins/mods/reference), and [test guide](https://code.claude.com/docs/en/plugins/mods/test), checked against native 2.1.289 declarations. [Verification results](pstack-mods-verification.md) distinguish executable checks from unverified real-model behavior.
