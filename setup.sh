#!/usr/bin/env bash
set -euo pipefail

# One-command setup for Hermes Secretary.
# Usage:
#   ./setup.sh
#   ./setup.sh --with-node   # also install Node deps for local TS runner (npx tsx join-meet.ts)

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
WITH_NODE=0
for arg in "$@"; do
  case "$arg" in
    --with-node) WITH_NODE=1 ;;
  esac
done

echo "==> Hermes Secretary setup ($ROOT)"

# Prefer Hermes' Python if available, else python3.
PYTHON="${PYTHON:-python3}"
if [ -x "$HOME/.hermes/hermes-agent/.venv/bin/python" ]; then
  PYTHON="$HOME/.hermes/hermes-agent/.venv/bin/python"
elif command -v hermes >/dev/null 2>&1; then
  # try to locate hermes' interpreter
  H="$(command -v hermes)"
  :
fi

echo "==> Using Python: $PYTHON"

echo "==> Installing Python dependencies (playwright)..."
"$PYTHON" -m pip install --upgrade pip >/dev/null 2>&1 || true
"$PYTHON" -m pip install "playwright>=1.40"

echo "==> Installing Playwright Chromium browser..."
"$PYTHON" -m playwright install chromium

if [ "$WITH_NODE" -eq 1 ]; then
  if command -v npm >/dev/null 2>&1; then
    echo "==> Installing Node dependencies (optional TS runner)..."
    npm install
  else
    echo "==> npm not found; skipping Node deps (Hermes/Python capture still works)."
  fi
fi

echo "==> Linking plugin into ~/.hermes/plugins (if Hermes is installed)..."
mkdir -p "$HOME/.hermes/plugins"
TARGET="$HOME/.hermes/plugins/hermes-secretary"
if [ -e "$TARGET" ] && [ ! -L "$TARGET" ]; then
  echo "    Skipping link: $TARGET exists and is not a symlink."
elif [ -L "$TARGET" ]; then
  ln -sfn "$ROOT" "$TARGET"
  echo "    Updated symlink: $TARGET -> $ROOT"
else
  ln -s "$ROOT" "$TARGET"
  echo "    Created symlink: $TARGET -> $ROOT"
fi

echo "==> Ensuring secret dir exists (gitignored)..."
mkdir -p "$ROOT/secret"

echo ""
echo "✅ Setup complete."
echo ""
echo "Next steps:"
echo "  1) Enable in Hermes (if needed): hermes plugins enable hermes-secretary"
echo "  2) Restart Hermes session/gateway so new tools/CLI load."
echo "  3) Add a Google account tag (opens browser for sign-in):"
echo "       hermes secretary add-account work"
echo "     or: python3 secretary_cli.py add-account work"
echo "  4) Join a meeting:"
echo "       npx tsx join-meet.ts hfz-wssx-rpa --account=work"
echo "     or via Hermes tool: secretary_join_meet {\"meet\":\"hfz-wssx-rpa\",\"account\":\"work\",\"headless\":false}"
echo ""
echo "Profiles are stored in: $ROOT/secret/<account>/ (gitignored)."
