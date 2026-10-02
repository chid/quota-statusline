#!/bin/bash
# Install quota-statusline: symlink bin/quota-line to ~/.local/bin and configure Claude Code statusLine.
set -e

REPO_URL="https://github.com/chid/quota-statusline.git"
INSTALL_DIR="${QUOTA_INSTALL_DIR:-$HOME/.local/share/quota-statusline}"
DEST="${1:-$HOME/.local/bin}"

# If running via pipe (e.g. curl ... | bash), clone or update into INSTALL_DIR
if [ ! -f "$(dirname "$0")/bin/quota-line" ]; then
  echo "Installing quota-statusline to $INSTALL_DIR..."
  if [ -d "$INSTALL_DIR/.git" ]; then
    git -C "$INSTALL_DIR" pull --ff-only 2>/dev/null || true
  else
    mkdir -p "$(dirname "$INSTALL_DIR")"
    git clone "$REPO_URL" "$INSTALL_DIR"
  fi
  HERE="$INSTALL_DIR"
else
  HERE="$(cd "$(dirname "$0")" && pwd)"
fi

mkdir -p "$DEST"
ln -sf "$HERE/bin/quota-line" "$DEST/quota-line"
echo "✔ Linked $DEST/quota-line"

command -v codexbar >/dev/null 2>&1 || echo "Note: CodexBar is recommended (https://github.com/steipete/CodexBar or brew install --cask codexbar)" >&2

CLAUDE_SETTINGS="$HOME/.claude/settings.json"
if [ "$1" = "--configure" ] || [ "$2" = "--configure" ]; then
  if [ -f "$CLAUDE_SETTINGS" ]; then
    /usr/bin/python3 -c "
import json
p = '$CLAUDE_SETTINGS'
try:
    with open(p) as f: d = json.load(f)
except Exception: d = {}
d['statusLine'] = {'type': 'command', 'command': '$DEST/quota-line'}
with open(p, 'w') as f: json.dump(d, f, indent=2)
print('✔ Configured statusLine in ' + p)
"
  fi
else
  cat <<EOF

To use as your Claude Code status line, add this to ~/.claude/settings.json:

  "statusLine": {
    "type": "command",
    "command": "$DEST/quota-line"
  }

Or run: ./install.sh --configure
EOF
fi
