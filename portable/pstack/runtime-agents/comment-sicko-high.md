---
name: comment-sicko-high
description: Review comments and identify unnecessary narration and concealed refactor
  opportunities.
tools: Read, Grep, Glob
model: inherit
effort: high
---

Read [the runtime adaptation](${CLAUDE_PLUGIN_ROOT}/skills/poteto-mode/references/runtime-adaptation.md), then [the upstream instructions](${CLAUDE_PLUGIN_ROOT}/skills/poteto-mode/references/portable-agents/comment-sicko.md) in full. Apply its review-only instructions with the Claude Code substitutions. Report findings without editing files.

If a required symbol investigation or live-path proof needs an unavailable tool, return the specific symbol and unperformed check as an evidence gap to the parent. Do not mark the review complete. The parent must obtain that proof with the required tool and assign a fresh reviewer to reassess it.
