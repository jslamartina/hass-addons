#!/bin/bash
set -e

echo "Starting complete devcontainer setup..."

# Add Python bin directory to PATH so all child scripts inherit it
PYTHON_BIN_DIR="/usr/local/python/3.12.11/bin"
if [ -d "$PYTHON_BIN_DIR" ]; then
  export PATH="$PYTHON_BIN_DIR:$PATH"
fi

echo "Workspace structure:"
echo "  ${WORKSPACE_DIRECTORY}/     - Home Assistant addon repository (with integrated cync_lan package)"
echo "  ${WORKSPACE_DIRECTORY}/src/cync_lan/ - Python package source (integrated)"

# Make all scripts executable
chmod +x "${WORKSPACE_DIRECTORY}/.devcontainer"/*.sh

# Run setup scripts in order
echo "Running setup scripts in order..."

echo "1/4: Setting up Python environment..."
bash "${WORKSPACE_DIRECTORY}/.devcontainer/01-01-python-env-setup.sh"

echo "2/4: Setting up workspace..."
bash "${WORKSPACE_DIRECTORY}/.devcontainer/01-03-python-workspace-setup.sh"

echo "3/4: Configuring VS Code..."
bash "${WORKSPACE_DIRECTORY}/.devcontainer/01-04-python-vscode-configure.sh"

echo "4/4: Setting up Python virtual environments..."
bash "${WORKSPACE_DIRECTORY}/.devcontainer/01-05-python-venv-setup.sh" "${WORKSPACE_DIRECTORY}"

echo "✅ Complete devcontainer setup finished!"
echo ""
echo "Workspace ready with integrated cync-lan package:"
echo "   - hass-addons (Home Assistant addon with integrated Python package)"
echo "   - Source code: ${WORKSPACE_DIRECTORY}/src/cync_lan/"
echo ""
echo "Available commands:"
echo "  - ha addons rebuild local_cync-lan: Rebuild the add-on"
