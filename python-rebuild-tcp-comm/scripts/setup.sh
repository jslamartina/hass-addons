#!/usr/bin/env bash
# Setup development environment

set -e

cd "$(dirname "$0")/.."

echo "=== Setting Up Development Environment ==="

# Check for Poetry
if ! command -v poetry &> /dev/null; then
  echo "Poetry not found. Installing..."
  pip install poetry==1.8.3
fi

# Install dependencies
echo ""
echo "Installing dependencies..."
poetry install

# Verify installation
echo ""
echo "Verifying installation..."
poetry run python --version
poetry run pytest --version
poetry run ruff --version
poetry run mypy --version

echo ""
echo "✓ Development environment ready!"
echo ""
echo "Available scripts:"
echo "  ./scripts/test-all.sh      - Run tests"
echo "  ./scripts/lint.sh          - Run linting and type checking"
echo "  ./scripts/format.sh        - Format code"
echo "  ./scripts/run.sh           - Run the toggler"
echo "  ./scripts/debug.sh         - Run with debug logging"
echo "  ./scripts/build.sh         - Build and validate project"
echo "  ./scripts/clean.sh         - Clean build artifacts"
