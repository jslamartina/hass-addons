#!/usr/bin/env bash
# Format code with ruff

set -e

cd "$(dirname "$0")/.."

echo "=== Formatting Code with Ruff ==="
poetry run ruff check --fix .
poetry run ruff format .

echo ""
echo "✓ Code formatted!"

