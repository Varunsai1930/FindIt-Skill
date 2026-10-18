#!/usr/bin/env bash
# Install the findit skill for Claude Code by symlinking (default) or copying.
#   ./install.sh            symlink into ~/.claude/skills/findit
#   ./install.sh --copy     copy files instead of symlinking
#   FINDIT_ROOT=... ./install.sh   use FindIt at another path (default /Users/varun/Downloads/Varun/Find_v2);
#                                  the path is saved in skills/findit/findit_root for the skill to use
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)/skills/findit"
REQUESTED_ROOT="${FINDIT_ROOT:-/Users/varun/Downloads/Varun/Find_v2}"
FINDIT_ROOT="$(cd "$REQUESTED_ROOT" 2>/dev/null && pwd -P)" || {
  echo "FindIt not found at $REQUESTED_ROOT. No skill was installed." >&2; exit 1; }
MODE=link
for arg in "$@"; do
  case "$arg" in
    --copy) MODE=copy ;;
    -h|--help) sed -n '2,6p' "$0"; exit 0 ;;
    *) echo "Unknown argument: $arg" >&2; exit 2 ;;
  esac
done

# The helper runs in FindIt's own environment; check it can read the active release.
if ! command -v uv >/dev/null 2>&1; then
  echo "Install uv (https://docs.astral.sh/uv/) and retry. No skill was installed." >&2
  exit 1
fi
if ! FINDIT_ROOT="$FINDIT_ROOT" "$SRC/scripts/findit" release >/dev/null; then
  echo "The helper could not read FindIt's active release at $FINDIT_ROOT. No skill was installed." >&2
  exit 1
fi

# Remember FindIt's location for the skill (the wrapper and helper read it).
printf '%s\n' "$FINDIT_ROOT" > "$SRC/findit_root"

dir="${CLAUDE_CONFIG_DIR:-$HOME/.claude}/skills"
mkdir -p "$dir"
dest="$dir/findit"
if [ -e "$dest" ] || [ -L "$dest" ]; then
  if [ -L "$dest" ] && [ "$(readlink "$dest")" = "$SRC" ]; then
    echo "✓ claude: already linked at $dest (FindIt: $FINDIT_ROOT)"
    exit 0
  fi
  echo "✗ claude: $dest already exists; remove it first to reinstall" >&2
  exit 1
fi
if [ "$MODE" = copy ]; then
  python3 - "$SRC" "$dest" <<'PY'
import shutil
import sys
shutil.copytree(sys.argv[1], sys.argv[2], ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '.DS_Store'))
PY
else
  ln -s "$SRC" "$dest"
fi
echo "✓ claude: installed at $dest ($MODE; FindIt: $FINDIT_ROOT)"
echo "Restart Claude Code, then type: /findit   (or /findit Hyundai Motor India)"
