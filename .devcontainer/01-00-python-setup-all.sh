#!/bin/bash
set -e

echo "Starting complete devcontainer setup..."

# Add Python bin directory to PATH so all child scripts inherit it
PYTHON_BIN_DIR="/usr/local/python/3.12.11/bin"
if [ -d "$PYTHON_BIN_DIR" ]; then
  export PATH="$PYTHON_BIN_DIR:$PATH"
fi

# Get workspace parent directory
WORKSPACE_PARENT="$(dirname "${WORKSPACE_DIRECTORY}")"
CYNC_LAN_DIR="${WORKSPACE_PARENT}/cync-lan"

echo "Workspace structure:"
echo "  ${WORKSPACE_DIRECTORY}/     - Home Assistant addon repository"
echo "  ${CYNC_LAN_DIR}/             - Python package repository"
echo "  ${WORKSPACE_PARENT}/.vscode/ - Global VS Code settings"

# Make all scripts executable
chmod +x "${WORKSPACE_DIRECTORY}/.devcontainer"/*.sh

# Run setup scripts in order
echo "Running setup scripts in order..."

echo "1/5: Setting up Python environment..."
bash "${WORKSPACE_DIRECTORY}/.devcontainer/01-01-python-env-setup.sh"

echo "2/5: Cloning cync-lan repository..."
bash "${WORKSPACE_DIRECTORY}/.devcontainer/01-02-python-clone-repo.sh"

echo "3/5: Setting up workspace..."
bash "${WORKSPACE_DIRECTORY}/.devcontainer/01-03-python-workspace-setup.sh"

echo "4/5: Configuring VS Code..."
bash "${WORKSPACE_DIRECTORY}/.devcontainer/01-04-python-vscode-configure.sh"

echo "5/5: Setting up Python virtual environments..."
bash "${WORKSPACE_DIRECTORY}/.devcontainer/01-05-python-venv-setup.sh" "${WORKSPACE_DIRECTORY}" "${CYNC_LAN_DIR}"

echo "✅ Complete devcontainer setup finished!"
echo ""
echo "📦 NEXT STEP: Load the multi-repository workspace"
echo "   Run this command in your terminal:"
echo "   cursor hass-cync-dev.code-workspace"
echo ""
echo "   Or manually: File → Open Workspace from File → hass-cync-dev.code-workspace"
echo ""
echo "   This will give you both repositories:"
echo "   - hass-addons (Home Assistant addon)"
echo "   - cync-lan (Python package)"
echo ""
echo "Available commands:"
echo "  - test-cync-lan.sh: Test the cync-lan package"
echo "  - cync-lan-source: Symlink to the cync-lan repository"
