#!/bin/bash
set -e

echo "Configuring VS Code for multi-repository development..."

# Get the workspace parent directory
WORKSPACE_PARENT="$(dirname "${WORKSPACE_DIRECTORY}")"
CYNC_CONTROLLER_DIR="${WORKSPACE_PARENT}/cync-controller"
VSCODE_CONFIG_DIR="${WORKSPACE_PARENT}/.vscode"

# Create a global settings file for the devcontainer
sudo mkdir -p "${VSCODE_CONFIG_DIR}"
sudo tee "${VSCODE_CONFIG_DIR}/settings.json" > /dev/null << EOF
{
  "python.analysis.extraPaths": [
    "${CYNC_CONTROLLER_DIR}",
    "${WORKSPACE_DIRECTORY}"
  ],
  "python.linting.enabled": true,
  "python.linting.pylintEnabled": false,
  "files.exclude": {
    "**/node_modules": true,
    "**/__pycache__": true,
    "**/.pytest_cache": true
  },
  "search.exclude": {
    "**/node_modules": true,
    "**/__pycache__": true,
    "**/.pytest_cache": true
  },
  "editor.formatOnSave": true,
  "editor.codeActionsOnSave": {
    "source.organizeImports": true
  }
}
EOF

# Create a launch configuration for debugging
sudo tee "${VSCODE_CONFIG_DIR}/launch.json" > /dev/null << 'EOF'
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "Debug cync-controller",
      "type": "python",
      "request": "launch",
      "program": "${workspaceFolder:cync-controller}/cync_lan/main.py",
      "args": ["--enable-export"],
      "console": "integratedTerminal",
      "cwd": "${workspaceFolder:cync-controller}",
      "env": {
        "PYTHONPATH": "${workspaceFolder:cync-controller}:${workspaceFolder}"
      }
    }
  ]
}
EOF

# Fix permissions so non-root user can access these files
sudo chmod -R 755 "${VSCODE_CONFIG_DIR}"
sudo chown -R vscode:vscode "${VSCODE_CONFIG_DIR}" 2> /dev/null || true

echo "VS Code configuration complete at ${VSCODE_CONFIG_DIR}"
