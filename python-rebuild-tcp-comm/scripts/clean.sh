#!/usr/bin/env bash
# Clean build artifacts and caches

set -e

cd "$(dirname "$0")/.."

echo "=== Cleaning Build Artifacts ==="

# Remove Python cache
echo "Removing Python cache..."
find . -type d -name "__pycache__" -exec rm -rf {} + 2> /dev/null || true
find . -type f -name "*.pyc" -delete 2> /dev/null || true
find . -type f -name "*.pyo" -delete 2> /dev/null || true
find . -type f -name "*.egg-info" -exec rm -rf {} + 2> /dev/null || true

# Remove test/coverage artifacts
echo "Removing test artifacts..."
rm -rf .pytest_cache htmlcov .coverage 2> /dev/null || true

# Remove build artifacts
echo "Removing build artifacts..."
rm -rf dist build 2> /dev/null || true

# Remove mypy cache
echo "Removing mypy cache..."
rm -rf .mypy_cache 2> /dev/null || true

# Remove ruff cache
echo "Removing ruff cache..."
rm -rf .ruff_cache 2> /dev/null || true

echo ""
echo "✓ Cleanup complete!"
