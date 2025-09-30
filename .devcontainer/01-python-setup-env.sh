#!/bin/bash
set -e

echo "Setting up Python environment for cync-lan development..."

# Install additional Python packages that might be needed for development
pip install --upgrade pip
pip install pytest pytest-asyncio black isort mypy

# Install development tools
pip install pre-commit

echo "Python development environment setup complete"
