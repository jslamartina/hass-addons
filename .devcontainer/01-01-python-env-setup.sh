#!/bin/bash
set -e

echo "Setting up Python environment for cync-lan development..."

# Install additional Python packages NOT provided by the devcontainer feature
# Note: black, pytest, mypy, isort are already installed by the Python feature
pip install --upgrade pip
pip install pytest-asyncio # Async testing support
pip install pre-commit     # Git hooks

echo "Python development environment setup complete"
