#!/bin/bash
set -e

echo "Starting complete devcontainer setup..."

# Make all scripts executable
chmod +x /workspaces/hass-addons/.devcontainer/*.sh

# Run setup scripts in order
echo "Running setup scripts in order..."

echo "1/5: Setting up Python environment..."
bash /workspaces/hass-addons/.devcontainer/01-python-setup-env.sh

echo "2/5: Cloning cync-lan repository..."
bash /workspaces/hass-addons/.devcontainer/02-python-clone-repo.sh

echo "3/5: Setting up workspace..."
bash /workspaces/hass-addons/.devcontainer/03-python-setup-workspace.sh

echo "4/5: Configuring VS Code..."
bash /workspaces/hass-addons/.devcontainer/04-python-configure-vscode.sh

echo "5/5: Setting up Python virtual environments..."
bash /workspaces/hass-addons/.devcontainer/05-python-setup-venv.sh

echo "✅ Complete devcontainer setup finished!"
echo ""
echo "Available commands:"
echo "  - test-cync-lan.sh: Test the cync-lan package"
echo "  - cync-lan-source: Symlink to the cync-lan repository"
echo ""
echo "Workspace structure:"
echo "  /workspaces/hass-addons/     - Home Assistant addon repository"
echo "  /workspaces/cync-lan/        - Python package repository"
echo "  /workspaces/.vscode/         - Global VS Code settings"
