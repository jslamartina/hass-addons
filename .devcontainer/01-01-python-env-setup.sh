#!/bin/bash
set -e

echo "Setting up Python environment for cync-controller development..."

# Install additional Python packages NOT provided by the devcontainer feature
# Note: black, pytest, mypy, isort are already installed by the Python feature
pip install --upgrade pip
pip install pytest-asyncio # Async testing support
pip install pytest-xdist   # Parallel test execution
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

# Install cync-controller in editable mode with test dependencies
# This allows the package to be imported in tests and includes pytest-xdist
WORKSPACE_DIR="${WORKSPACE_DIRECTORY:-/workspaces/hass-addons}"
PYPROJECT_DIR="${WORKSPACE_DIR}"

if [ -f "${PYPROJECT_DIR}/pyproject.toml" ]; then
  echo "Installing hass-addons Python package in editable mode with test dependencies..."
  cd "${PYPROJECT_DIR}"
  pip install -e '.[dev,test]' || {
    echo "WARNING: Failed to install hass-addons package in editable mode"
    echo "Tests may fail with 'ModuleNotFoundError: No module named cync_controller'"
    echo "Run manually: cd \"${PYPROJECT_DIR}\" && pip install -e '.[dev,test]'"
  }
  echo "✓ hass-addons package installed in editable mode"
else
  echo "WARNING: pyproject.toml not found at ${PYPROJECT_DIR}"
  echo "Tests will fail until package is installed: cd \"${PYPROJECT_DIR}\" && pip install -e '.[dev,test]'"
fi

echo "Python development environment setup complete"
