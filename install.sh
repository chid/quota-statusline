#!/bin/bash
# Symlink quota-line onto PATH and print the Claude Code statusLine snippet. Changes nothing else.
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
DEST="${1:-$HOME/.local/bin}"
command -v codexbar >/dev/null || echo "warning: codexbar not found on PATH (https://github.com/steipete/CodexBar)" >&2
mkdir -p "$DEST"
ln -sf "$HERE/bin/quota-line" "$DEST/quota-line"
echo "linked $DEST/quota-line"
cat <<JSON

Add to ~/.claude/settings.json to use it as the Claude Code status line:

  "statusLine": { "type": "command", "command": "$HERE/scripts/quota.sh --line" }
JSON
