# Codex dispatch

Read `${CODEX_HOME:-$HOME/.codex}/pstack-models.md` immediately before dispatch. Preserve the upstream setup-pstack roles and budget confirmation. Missing roles use `inherit-parent`. Parse `model @level` into model and reasoning effort. `inherit-parent` and `auto` omit model overrides. `default effort: session` inherits session effort; an explicit entry effort takes precedence over a supported default level.

Inspect the actual spawn_agent schema, delegation instructions and the available model list in this session. Supply model or reasoning_effort only when allowed by that schema and when confirmed supported. Claude aliases, Cursor suffixes and Claude effort levels are not a Codex model catalog.

When full-history forks prohibit overrides, use `fork_turns: none` or an allowed partial-history fork with a consolidated brief and file pointers. Do not attach model or effort overrides to a full-history fork. If overrides are forbidden entirely, inherit the model and effort and disclose the unapplied choices. Keep any stricter instruction that requires delegation to stay on the parent model.

A native Codex plugin does not register Claude agent types. Put the adaptation and required upstream skill or bundled agent reading in the child brief. Give each writer a separate worktree. Make reviewer scopes read-only. Use only exposed wait, message and interrupt tools and collect results before declaring completion.

Keep the configured panel count, including alias entries. A missing role does not reduce the participant count required by the upstream playbook; use the inherited selection for each required participant. Prefer distinct confirmed available model families where overrides are permitted. A smaller model catalog and an override prohibition are different limitations. Independent inherited-model agents are not a multi-model comparison. If delegation is disabled, run the independent passes sequentially and disclose that limitation. Preserve the original fresh-agent policy and completion and merge gates.
