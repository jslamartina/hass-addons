#!/usr/bin/env bash
# Run linting and type checking

set -e

cd "$(dirname "$0")/.."

echo "=== Running Ruff Linter ==="
poetry run ruff check .

echo ""
echo "=== Running Mypy Type Checker ==="
poetry run mypy src tests

echo ""
echo "✓ All linting and type checks passed!"

