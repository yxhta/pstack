#!/bin/sh
set -eu
case "${1:-}" in
  claude) config_root=${CLAUDE_CONFIG_DIR:-"$HOME/.claude"} ;;
  codex) config_root=${CODEX_HOME:-"$HOME/.codex"} ;;
  *) printf '%s\n' 'pstack: unknown runtime; context skipped' >&2; exit 0 ;;
esac
sheet=$config_root/pstack-models.md
if [ -e "$sheet" ] || [ -L "$sheet" ]; then
  if [ ! -f "$sheet" ] || [ ! -r "$sheet" ]; then
    printf '%s\n' 'pstack: model sheet unreadable; context skipped' >&2
    exit 0
  fi
  if ! directive=$(awk '
    /^[[:space:]]*session hook[[:space:]]*:/ {
      value=$0
      sub(/^[[:space:]]*session hook[[:space:]]*:[[:space:]]*/, "", value)
      sub(/[[:space:]]*$/, "", value)
      if (value != "on" && value != "off") invalid=1
      if (seen && previous != value) invalid=1
      previous=value; seen=1
    }
    END { if (invalid) exit 1; print previous }
  ' "$sheet"); then
    printf '%s\n' 'pstack: conflicting or unreadable hook directive; context skipped' >&2
    exit 0
  fi
  [ "$directive" != off ] || exit 0
fi
context=$(dirname "$0")/session-start-context.md
if [ ! -f "$context" ] || [ ! -r "$context" ]; then
  printf '%s\n' 'pstack: hook context unreadable; context skipped' >&2
  exit 0
fi
cat "$context"
