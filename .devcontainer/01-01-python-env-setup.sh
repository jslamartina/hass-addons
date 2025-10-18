#!/bin/bash
set -e

echo "Setting up Python environment for cync-controller development..."

# Install additional Python packages NOT provided by the devcontainer feature
# Note: black, pytest, mypy, isort are already installed by the Python feature
pip install --upgrade pip
pip install pytest-asyncio # Async testing support
pip install pre-commit     # Git hooks
pip install uv             # Fast Python package manager (used by MCP servers via uvx)

echo "Python development environment setup complete"
