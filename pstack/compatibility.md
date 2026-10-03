# Claude Code and Codex adaptation

Read this before following any pstack skill on Claude Code or Codex. These runtime substitutions override Cursor-specific mechanics, not the upstream engineering principles or playbook outcomes. On Cursor, follow the upstream instructions unchanged.

## Shared rules

- Use the tools actually exposed in this session. Do not invent a tool, model, background flag, or cloud environment.
- Resolve another pstack skill by its directory name in this plugin's `skills/`. Claude Code may invoke `pstack:<name>`; Codex may load the installed skill or read its `SKILL.md`.
- Read the model sheet at `${CLAUDE_CONFIG_DIR:-~/.claude}/pstack-models.md` on Claude Code or `${CODEX_HOME:-~/.codex}/pstack-models.md` on Codex. This replaces every reference to `~/.cursor/rules/pstack-models.mdc`. Read it explicitly; it is not an always-applied Cursor rule.
- An absent role defaults to `inherit-parent`, replacing upstream's Cursor model slugs. Use only models and reasoning levels confirmed available in the current harness. Do not send Claude or Grok model IDs to Codex. A Cursor effort suffix is not part of a portable model ID.
- For multi-model panels, use distinct configured models when the tools support them. Otherwise use independent agents on the inherited model and disclose the reduced model diversity. If delegation is unavailable, perform the passes sequentially and disclose the limitation.
- Writers need separate worktrees or output directories. Local subagents do not acquire isolation merely by being spawned. Review their output before integrating it.
- Include a pointer to this file in every subagent brief. When a brief requests `poteto-agent`, require the child to read this file and `skills/poteto-mode/SKILL.md` in full before work. When it requests `Comment Sicko`, require `agents/comment-sicko.md` instead.
- A missing optional dependency is a limitation to report, not permission to install another plugin, edit its cache, contact people, or publish an upstream PR. If it prevents the requested result, state the blocker. Preserve the user's authorization and the harness's approval rules.

## Claude Code

| Cursor instruction | Claude Code action |
| --- | --- |
| `Task`, `generalPurpose` | Available `Agent` or `Task` tool, `general-purpose` agent |
| `poteto-agent` | Plugin agent `pstack:poteto-agent` |
| `Comment Sicko` | Plugin agent `pstack:comment-sicko` |
| `AskQuestion` | `AskUserQuestion` when available, otherwise a concise question |
| todolist | Available task tools or a local checklist |
| `environment: cloud`, `cloud_base_branch` | Local agent in its own worktree, checked out at the requested branch |
| `readonly` | Explicit read-only scope in the brief; use an enforceable restriction when available |

Use background execution only if the tool supports it, and collect the result before reporting completion. Preserve plugin namespacing when invoking skills.

## Codex

| Cursor instruction | Codex action |
| --- | --- |
| `Task` | Available `spawn_agent` tool |
| `subagent_type` | A brief instructing the child to read the corresponding skill or agent file |
| `run_in_background` | Spawned agents already run concurrently; omit unsupported flags |
| wait / message / stop | Available agent wait, message, and interrupt tools |
| `AskQuestion` | Available user-input tool, otherwise a concise question |
| todolist | Available plan tool or a local checklist |
| `readonly` | Explicit read-only scope in the brief; do not pass unsupported fields |
| cloud worker | Local subagent with a separate worktree |

If subagents are disabled, explain the sequential fallback; enabling a feature is not required to read or use the ordinary skills. Model overrides and reasoning effort must match the actual `spawn_agent` schema, including any restrictions on inherited context.

## Setup, paths, and dependencies

For `setup-pstack`, keep the upstream role labels but write the runtime's Markdown model sheet instead of an `.mdc` rule. Start with inherited models; ask about budget and confirm the concrete role choices as upstream requests. Store effort separately as `model @level` only when supported. If available models cannot be enumerated, offer `inherit-parent` rather than requiring invented slugs. Read this sheet at each dispatch.

Generated project skills go under `.claude/skills/` on Claude Code or `.agents/skills/` on Codex. Personal skills go under the corresponding runtime's supported user skill directory. Preserve a user's existing destination when updating a skill. `CLAUDE.md` and `AGENTS.md` replace Cursor-specific instruction files on their respective runtimes.

Cursor's `create-skill` means the available native skill-authoring guidance (`skill-creator` on Codex), or direct authoring with valid `name` and `description` frontmatter when no equivalent is installed. Do not assume `plugin-dev` is installed.

`deslop`, `control-cli`, and `control-ui` from `cursor-team-kit` are not bundled by this fork. Use an installed equivalent if available. Otherwise inspect the diff directly for deslopping, run CLI commands and observe their output, or drive a UI with the available browser/computer tools. Report any verification you could not perform.

Use only the active session's supplied transcript or a user-provided digest for `reflect`, `automate-me`, and `recall`. Do not search unrelated runtime histories or treat Cursor's transcript format as Claude Code/Codex format. Cursor chat URLs, `/goal`, `/loop`, and wake-up mechanisms have equivalents only when the session exposes them; never claim background persistence that does not exist.

`make-bot-ui`, the Benny automation pack, and Cursor-specific tutorial steps require Cursor and are not supported here. Shared scripts can be used only when their dependencies and data formats are available; this mapping does not port their transcript parsers.
