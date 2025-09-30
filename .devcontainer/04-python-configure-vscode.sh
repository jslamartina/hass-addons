#!/bin/bash
set -e

echo "Configuring VS Code for multi-repository development..."

# Create a global settings file for the devcontainer
mkdir -p /workspaces/.vscode
cat > /workspaces/.vscode/settings.json << 'EOF'
{
  "python.defaultInterpreterPath": "/usr/local/bin/python3",
  "python.analysis.extraPaths": [
    "/workspaces/cync-lan",
    "/workspaces/hass-addons"
  ],
  "python.linting.enabled": true,
  "python.linting.pylintEnabled": true,
  "python.formatting.provider": "black",
  "python.sortImports.args": ["--profile", "black"],
  "files.exclude": {
    "**/node_modules": true,
    "**/__pycache__": true,
    "**/.pytest_cache": true,
    "**/.mypy_cache": true
  },
  "search.exclude": {
    "**/node_modules": true,
    "**/__pycache__": true,
    "**/.pytest_cache": true,
    "**/.mypy_cache": true
  },
  "editor.formatOnSave": true,
  "editor.codeActionsOnSave": {
    "source.organizeImports": true
  }
}
EOF

# Create a launch configuration for debugging
mkdir -p /workspaces/.vscode
cat > /workspaces/.vscode/launch.json << 'EOF'
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "Debug cync-lan",
      "type": "python",
      "request": "launch",
      "program": "${workspaceFolder}/cync-lan-source/cync_lan/main.py",
      "args": ["--enable-export"],
      "console": "integratedTerminal",
      "cwd": "${workspaceFolder}/cync-lan-source",
      "env": {
        "PYTHONPATH": "${workspaceFolder}/cync-lan-source:${workspaceFolder}"
      }
    }
  ]
}
EOF

echo "VS Code configuration complete"
