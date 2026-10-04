# Portable pstack parity report

## Scope

This change updates the GitHub fork at `cbc4793b6309fb10e5709ff40754e93f376e9edb` to the observed upstream commit `e43c7ee26e0038c6c1fa8380dd34ce86ff94cb2a` (pstack 0.15.9). The user subsequently authorized publication to `yxhta/pstack` on `improve/upstream-parity`. Publication preserves the reviewed Git tree and file modes; the original local merge history is retained in the delivery bundle. No PR, merge, authentication change, or global installation change is included.

The definition of done is separate for each kind of evidence:

1. Pristine source matches the recorded upstream commit, including executable modes.
2. Generated skills preserve upstream bodies and all playbooks, with explicit host translations.
3. Each executable correction has a failing-before regression and passing final checks.
4. Workflow claims name their actual execution evidence or remain unverified.

The [baseline matrix](parity-baseline.md) inventories every upstream skill, principle, playbook, and dependency before the fixes. The [decision log](parity-decisions.tsv) records the accepted changes and verification limits.

## Source and package coverage

- All 161 upstream pstack files are included.
- All 50 upstream skill bodies are preserved after the adaptation notice.
- All 23 playbooks are byte-identical to upstream.
- The 52 portable skills include the 50 originals, bundled deslop, and sync-pstack-upstream.
- Deslop comes from the same upstream pin and retains its license and provenance.
- Upstream 0.15.9 adds correct and updates architecture and performance guidance.

`prepare.py --check` verifies source and generated content against the pinned Git objects. `validate.py` checks registrations, required links, native wrappers, role labels, and skill-body preservation. These are structural checks, not proof that an agent will follow every instruction.

## Corrections and evidence

| Area | Previous failure | Correction | Evidence |
|---|---|---|---|
| Upstream drift | Fork lacked the current correct skill and revised guidance | Merge upstream history and regenerate without patching source | Source integrity and generated-tree checks |
| Comment Sicko | Read-only reviewer could return findings while no actor owned expected comment deletions | Parent applies accepted scoped edits, checks the real diff, and reports actual counts | Native collaboration smoke removed exactly three comment lines after an independent read-only review; CLI plugin integration remains unverified |
| Capacity and nesting | Fixed upstream panels could exceed host capacity or unavailable child nesting | Schedule all seats in waves and relay stages through fresh siblings | Native cloud collaboration completed all ten lanes in two-worker waves and retained an intentional failure in the aggregate |
| Blinding | A fresh full-history fork could see private judge context | Require clean context for blinded candidates independently of model overrides | Explicit Codex and shared contract plus scenario |
| Lifecycle | Interrupt receipts could be mistaken for completed cancellation | Establish terminal state before integrating or cleaning outputs | Explicit lifecycle contract and scenario |
| Transcript evidence | Only a subset of transcript-dependent workflows had portable evidence rules | Apply authorized-evidence limits to every workflow; missing chain evidence remains unverified | Shared contract and denied-evidence scenario |
| Bundled script paths | Source-checkout paths could be interpreted relative to a consuming project | Resolve installed poteto-mode root; record snapshot rather than pretend it is live upstream | Shared resource contract and scenario |
| Script bootstrap | Read-only-looking helpers install dependencies into their own directory | Preflight dependencies and use an authorized writable scripts copy | Dependency installation and suites run in a disposable copy |
| Cleanup discovery | Cursor history, BSD commands, space splitting, assumed main, and closed-PR heuristics could mislead | New local-only JSON audit with conservative holds and unknown usage | Real disposable Git-repository CLI regressions |
| Git startup tracing | Global Trace2 configuration still wrote files before command-line overrides | Disable normal/event/perf trace targets in the child environment before Git starts | Positive controls, unchanged existing trace files, preserved global filters/excludes, and an independent reproduction |
| CI fixture isolation | Production environment sanitization exposed GitHub runner system filters to supposedly clean test repositories | Test-only Git wrappers select a temporary system configuration after sanitization; production behavior is unchanged | Synthetic runner configuration reproduced 18 failing audit assertions; clean fixtures and explicit system-filter refusal are covered |
| Portable plan checks | Honest installed-snapshot and active-session plans failed two Cursor-specific marker checks | Companion validates a scoped runtime contract while running the untouched upstream structural checker | Mutation tests retain lane, evidence, perf, and review gates; changed-plan race and nested examples fail closed |
| Default skills installation | Per-skill Claude symlinks did not share the companion's lexical root | Resolve aliases to the exact same canonical companion and required resources | Actual Skills CLI default layout plus mixed-bundle/escape regressions |
| Install verification | Python optimization removed assertions and falsely verified an empty installation | Explicit errors, complete file/content/mode inventories, and copied-tree symlink rejection | Subprocess tests under PYTHONOPTIMIZE 0, 1, and 2 |
| Generator failure | Failed publication could delete the previous generated bundle | Backup then publish; rollback on error; preserve recovery backup if rollback fails | Fault-injection tests for publish and rollback failures |
| Sync retries | Closed PRs or failed PR creation left a remote branch that broke the next push | Choose an unused suffixed branch without force-push; retain one-open-PR gate | Local bare-origin tests with mocked gh and skills commands |
| Sync cleanup | Failed install checks leaked temporary directories | Install/body cleanup on every exit | Failure-path sync tests |

## Verification record

The cloud integration baseline on Python 3.12.14 with PyYAML 6.0.3 passed 64 Python tests. The publication follow-up passes all 65 tests both normally and under synthetic runner system filters, including the added system-filter regression (10 generator, 6 installation/validator, 6 sync, 5 runtime/hook, 23 worktree-audit tests, and 15 portable-plan tests). Source/generation checks, validate.py under ordinary Python and PYTHONOPTIMIZE=2, shell syntax, and whitespace checks pass. Earlier baseline checks passed 11 Python tests and validated 51 skills.

The first published tree exactly matched the reviewed local tree. Its [GitHub Actions run](https://github.com/yxhta/pstack/actions/runs/37208309606) passed source integrity but exposed the fixture isolation issue above. The correction does not disable system filters in production or alter package contents. The delivery receipt records the final remote commit and CI outcome.

- The actual skills CLI 1.7.0 installed all 52 skills for Claude Code and Codex into an isolated project. File bytes, executable modes, and bundled resources matched. The default per-skill symlink installation was also exercised through the Claude alias root, including companion execution and complete byte/mode comparison.
- Official Claude Code 2.1.289 plugin validation passed without signing in, using an isolated configuration directory.
- The unchanged bundled Orchestrate/watch-pr suites passed 52 tests, with 206 assertions, using Bun 1.4.2. Strict TypeScript checking passed. Forge and Graphite interactions in those suites use fakes; they are not live service verification.
- The existing read-only hook suite exercises both host command definitions, paths with spaces, missing sheets, on/off/conflicting directives, unreadable inputs, and no execution of sheet contents.
- Portable-plan tests also pass on Node 20.20.2, matching the added CI runtime family. They invoke the real pinned upstream checker from an unrelated working directory and installed-layout fixtures.
- Eighteen prompt/expected-output cases specify portable behavior. JSON parsing does not execute these cases or establish a pass rate.

### Native execution limits

The cloud's standalone Codex 0.159.2 reports an existing ChatGPT login, but a read-only ephemeral probe fails before model startup with `failed to initialize in-process app-server client: Read-only file system`. No settings or credentials were changed to work around it. Claude inference and Cursor inference were not run. CLI manifest validation is not an inference run.

A small finite-number sum repair was dispatched through the available native collaboration tools with the generated skills. The implementation passes 16 task tests and 31 separate public-API assertions, including signed zero, sparse and inherited-index arrays, invalid types, non-finite values, overflow, and frozen input. A second native collaboration smoke used no-comments. A read-only reviewer proposed three deletions, the parent applied them, and an independent byte check confirmed that exactly those comments disappeared while every executable byte stayed unchanged. A third native collaboration scenario used ten fresh read-only workers in five two-worker batches. Nine lanes passed; an intentionally seeded negative-zero defect failed the tenth. The coordinator retained an ISSUES aggregate rather than shrinking coverage or reporting a clean result. Separate reruns reproduced the same 9/1 outcome. These are cloud-native smoke cases, not a blinded comparison or proof of native Codex/Claude plugin loading, hook trust, model-family routing, or all playbooks.

Cloud implementation and authorized cloud checks are complete independently of Mac availability. A separate host can supply additional integration evidence later; it is not a prerequisite for this deliverable.

## Remaining boundaries

- No cross-model-family claim. The available model catalog and each host's override rules determine whether genuine model diversity exists.
- No independent-review claim when delegation is unavailable. Sequential self-passes can be useful but do not satisfy an independent gate.
- No automatic permission expansion. Upstream autonomy text does not authorize publishing, merging, messages, installations, credential changes, or deletion outside the user's scope and host policy.
- Native hook execution requires actual host support and trust. Skills-only installation does not register hooks or native agents. Cloud orchestration has separate hook support limits.
- Cursor make-bot-ui, Benny, transcript formats, cloud VM lifecycle, and Cursor-specific tutorial steps remain unsupported.
- Orchestrate's Graphite frontier requires actual `gt` metadata. A gh result is not a substitute frontier implementation.
- The raw upstream plan checker remains unchanged. Use `check-portable-plan.mjs` for portable plans. It adapts only two known marker diagnostics after checking the runtime contract and installed resources. STRUCTURE PASS does not verify declared tool availability, wake receipts, lifetime, operator approval, or actual evidence. Unsupported required lifetime remains BLOCKED.
- Active-session waits do not establish restart or overnight persistence.
- Cleanup evidence stays local and usage stays unknown. Fresh forge state, active-work evidence, and separately authorized removal remain necessary. Repositories with configured clean/process filters or tracked submodules fail closed rather than execute conversion commands. Use physical paths; symlink paths are rejected.
- The shared generator intentionally removes `disable-model-invocation` so routed skills are available to the agent. This changes invocation availability; it is not claimed as identical Cursor discovery behavior.

## Reproduce the checks

```sh
python3 tools/portable/prepare.py --check
python3 tools/portable/validate.py
python3 -m unittest discover -s tools/portable -p 'test_*.py'
PYTHONOPTIMIZE=1 python3 tools/portable/validate.py
bash -n tools/portable/sync-upstream.sh
sh -n portable/pstack/hooks/session-start.sh
git diff --check
```

For the installation smoke check, use a disposable project and install the explicit `portable/pstack` directory with `npx skills add <package> --skill '*' --agent claude-code codex --copy --yes`. Run `check-install.py <project>` afterward. The checker intentionally validates copied installations, not symlink installations.

Run bundled Bun dependencies and tests in a disposable copy of the complete scripts directory. Do not install them into pristine source or an immutable plugin cache.

## Primary host references

Checked on 2026-10-04:

- [Claude subagent configuration](https://code.claude.com/docs/en/sub-agents). Effort variants and model support depend on the actual installed host and selected model.
- [Claude plugin path substitution](https://code.claude.com/docs/en/plugins-reference). Plugin-root paths in Markdown are substituted by Claude; cache state belongs outside the versioned root.
- [OpenAI plugin packaging](https://developers.openai.com/plugins/build/plugins). The Codex compatibility manifest remains supported, and plugin installation does not grant hook trust.
- [Codex hooks](https://learn.chatgpt.com/docs/hooks). SessionStart accepts text context; host support and trust still control actual execution.
