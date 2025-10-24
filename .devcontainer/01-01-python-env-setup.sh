#!/bin/bash
set -e

echo "Setting up Python environment for cync-controller development..."

# Install additional Python packages NOT provided by the devcontainer feature
# Note: black, pytest, mypy, isort are already installed by the Python feature
pip install --upgrade pip
pip install pytest-asyncio # Async testing support
pip install pre-commit     # Git hooks
pip install uv             # Fast Python package manager (used by MCP servers via uvx)

# Ensure ~/.local/bin is on PATH for uv-installed tools (ruff, etc.)
if ! echo "$PATH" | grep -q "$HOME/.local/bin"; then
  echo "export PATH=\"$HOME/.local/bin:$PATH\"" >> ~/.bashrc
  echo "export PATH=\"$HOME/.local/bin:$PATH\"" >> ~/.zshrc
fi

# Install Ruff CLI via uv (user scope)
uv tool install ruff || true

# Verify ruff installation
if command -v ruff > /dev/null 2>&1; then
  echo "Ruff installed: $(ruff --version)"
else
  echo "WARNING: Ruff not found on PATH after installation"
fi

echo "Python development environment setup complete"
