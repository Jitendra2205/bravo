#!/usr/bin/env bash
# Awaaz - WSL2 (Ubuntu) side setup. Run from the repo root inside Ubuntu:
#   bash setup/wsl-setup.sh [model]
# Safe to re-run.
set -euo pipefail

MODEL="${1:-gemma4:e4b}"
OLLAMA_URL="http://localhost:11434"
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
HERMES_HOME="$HOME/.hermes"

step() { printf '\n==> %s\n' "$1"; }
# Hermes and uv install into these; a shell opened before install won't have them on PATH yet.
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"

step "Checking that WSL can reach Ollama on Windows"
if ! curl -fsS "$OLLAMA_URL/api/tags" >/dev/null; then
  echo "Can't reach $OLLAMA_URL. Make sure Ollama is running on Windows, run 'wsl --shutdown' in PowerShell, reopen Ubuntu and retry."
  exit 1
fi
curl -fsS "$OLLAMA_URL/api/tags" | grep -q "\"${MODEL}\"" || echo "Warning: $MODEL not found in Ollama. Run 'ollama pull $MODEL' on Windows."

step "Installing system packages (audio + tools)"
sudo apt-get update -y
sudo apt-get install -y curl git ffmpeg portaudio19-dev

step "Installing Hermes Agent (official installer)"
if command -v hermes >/dev/null 2>&1; then
  echo "Hermes already installed: $(hermes --version 2>/dev/null || echo unknown version)"
else
  # Official URL from github.com/NousResearch/hermes-agent. Read it first: curl -fsSL <url> | less
  curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash
fi

step "Pointing Hermes at local Ollama"
hermes config set model.provider custom
hermes config set model.base_url "$OLLAMA_URL/v1"
hermes config set model.default "$MODEL"

step "Installing voice support (local Whisper speech-to-text)"
if ! command -v uv >/dev/null 2>&1; then
  # Official uv installer (astral.sh), used by Hermes for its Python packages.
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi
if [ -d "$HERMES_HOME/hermes-agent" ]; then
  (cd "$HERMES_HOME/hermes-agent" && uv pip install -e ".[voice]")
else
  echo "Hermes source dir not found at $HERMES_HOME/hermes-agent; install voice extras per the Hermes voice guide."
fi

step "Installing persona and custom skills"
mkdir -p "$HERMES_HOME/skills"
cp "$REPO_DIR/config/SOUL.md" "$HERMES_HOME/SOUL.md"
cp -r "$REPO_DIR/skills/"* "$HERMES_HOME/skills/"
# shortcut: assumes Hermes loads user skills from ~/.hermes/skills; if `hermes` doesn't list daily-brief, check the Hermes skills docs for the current path.

step "Health check"
hermes doctor || true

cat <<EOF

Done. Next:
  0. Reload your shell so 'hermes' is found:   source ~/.bashrc   (or open a new Ubuntu window)
  1. Start the agent:       hermes
  2. Turn on voice:         /voice on   (then /voice status)
  3. Set speech providers in ~/.hermes/config.yaml: speech-to-text 'local', text-to-speech 'neutts'
     (key names per the Hermes voice guide for your version)
  4. Lock it down:          follow config/SECURITY-PRESET.md
  5. Try the skill:         "run my daily brief"
EOF
