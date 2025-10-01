#!/usr/bin/env bash
# 05-python-setup-venv.sh
# When it runs: Invoked by 99-python-setup-all.sh during postCreateCommand after the container is created or rebuilt.
# What it does: Creates venvs for both hass-addons and cync-lan, upgrades pip, installs requirements and common dev tools.
set -euo pipefail

setup_venv() {
  local workspace_path="$1"
  local workspace_name=$(basename "$workspace_path")

  echo "Setting up Python venv for $workspace_name..."

  echo "$workspace_path"
  cd "$workspace_path"

  if [ ! -d ".venv" ]; then
    python -m venv .venv
    echo "  ✓ Created .venv"
  else
    echo "  ✓ .venv already exists"
  fi

  # shellcheck disable=SC1091
  source .venv/bin/activate

  python -m pip install --upgrade pip setuptools wheel > /dev/null
  echo "  ✓ Upgraded pip, setuptools, wheel"

  if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt > /dev/null
    echo "  ✓ Installed requirements.txt"
  fi

  if [ -f "requirements-dev.txt" ]; then
    pip install -r requirements-dev.txt > /dev/null
    echo "  ✓ Installed requirements-dev.txt"
  fi

  pip install black ruff mypy pytest > /dev/null
  echo "  ✓ Installed dev tools (black, ruff, mypy, pytest)"

  deactivate
  echo "  ✓ Python venv ready for $workspace_name"
}

# Setup venvs for both workspaces
# Arguments: $1 = WORKSPACE_DIRECTORY, $2 = CYNC_LAN_DIR
setup_venv "$1" 
echo ""
setup_venv "$2"

echo ""
echo "✅ All Python virtual environments configured!"
