# Claude Mods bug-fix verification

Verified on 2026-10-06 in an isolated Linux cloud checkout of `yxhta/pstack`, based on `5f83e9274167e4e6fa50f48e9e4ab847190a3ec6`. The unchanged upstream pin is `e43c7ee26e0038c6c1fa8380dd34ce86ff94cb2a`.

## Results

- The full Python suite passed **118 tests**, including 18 real-process/snapshot cases and 12 generated-package cases for the adapter.
- The official Claude Code **2.1.289** test harness passed **85 tests** against the generated adapter.
- Strict native plugin validation, TypeScript **5.9.3** with the runtime-generated 2.1.289 declarations, and a real no-inference `/pstack-bugfix status` load all passed.
- Source integrity, normal and optimized Python validation, generation freshness, shell syntax, existing plugin schema validation, and whitespace checks passed.
- The new Claude native plugin installed and enabled in a disposable home. No normal user configuration changed.
- Skills CLI **1.7.0** copy installation verified every skill file and executable mode for both Claude Code and Codex. Its default linked installation also preserved all **55** coexisting pstack and Thermos skills and their shared references.
- Codex CLI **0.159.2** installed the unchanged native pstack and Thermos packages in a disposable home. Its actual `skills/list` loader found all three project Thermos skills and all three namespaced plugin skills without errors. The Mods package is absent from the Codex marketplace.
- `pstack/`, `thermos/`, root `README.md`, existing `portable/pstack/` and `portable/thermos/`, and the Codex marketplace remained byte-for-byte unchanged from the base, including executable modes.

The implementation was reviewed independently for correctness and code quality before publication. Review found ordinary concurrent-edit and cancellation races, a raw-byte baseline gap, and a generated-bytecode packaging issue. Fixes have executable regression coverage.

## What ran for real

The Python fixtures create disposable Git repositories and execute actual child processes. They verify a failing assertion followed by a passing fix, repeated execution, actual exit codes, missing programs, signals, timeouts, bounded output, and process-group cleanup after a terminated helper. They also exercise tracked, staged, untracked, deleted, mode-changed, and committed state; preserved-mtime edits; mid-scan changes; ignored outputs; unsupported index flags and filters; and raw clean-tree checks independent of Git's status cache.

The native load smoke runs a registered command through the actual Claude binary. It prints the inactive status, generates that build's types, and performs no inference. The test script uses a fresh home and removes the temporary plugin copy afterward.

## What was stubbed

The 85 native tests execute the production hooks through Claude's official test harness. Host process results, filesystem reads, agent listings, identities, and completion events are fixtures. They cover opt-in, missing evidence, repeated commands, snapshot invalidation, failures and missing child results, stale or malformed review reports, required whole-file reads, interruption, cancellation during awaited operations, session restart/reload, bounded Stop, and render-tree output on terminal and desktop surfaces.

Claude 2.1.289 has a test-adapter quirk for `agent.spawn`. The fixture supplies both its public result and the internal `result: { agentId, resolvedModel }` envelope expected by that build's adapter. A focused native regression and generated-type check validate this fixture. It is an undocumented, version-pinned testing accommodation. Production code does not fabricate an agent identity or accept this envelope as evidence. Successful native tests establish behavior with simulated host identities and completion events.

## Not established

- A model-driven end-to-end bug fix or actual reviewer spawn inside authenticated Claude Code
- Review quality, actual model effort support, plan capacity, or real-host reviewer latency
- Terminal or desktop pixel layout; the official harness checks render trees, not application painting
- macOS execution; the helper uses Unix APIs, and Linux was the tested platform
- Windows support, hostile-plugin resistance, atomic filesystem isolation, universal write prevention, or guaranteed cancellation of detached descendants or a helper killed with SIGKILL
- Ignored files, changing services, environment variables, dependencies outside the repository, or other external state

No credentials were copied, login grants created, external model APIs called, or real-model fallback purchased. `verified` is a bounded local evidence state, not an absolute correctness or security guarantee. The operational limits and recovery commands are documented in [pstack Mods](pstack-mods.md).

## Reproduce the checks

```sh
python3 tools/portable/prepare.py --check
python3 tools/portable/validate.py
python3 -O tools/portable/validate.py
python3 -m unittest discover -s tools/portable -p 'test_*.py'
CLAUDE_BIN=/path/to/claude-2.1.289 bash tools/portable/check-mods.sh
git diff --check
```

The portable GitHub Actions workflow runs the Python checks, pinned native Mods checks, and separate Skills CLI copy-install checks. Review the workflow results for the PR's exact head commit before treating remote CI as passed.
