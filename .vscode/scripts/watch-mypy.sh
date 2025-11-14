#!/bin/bash
# Watch wrapper for mypy (python-rebuild-tcp-comm) - always does full scan
# Args: $1 = single changed file from chokidar (triggers scan, but we scan everything)

cd "$(dirname "$0")/../.." || exit 1

echo "# Scanning..."

# Always check all files (run from workspace root to match pyproject.toml config)
mypy python-rebuild-tcp-comm/src python-rebuild-tcp-comm/tests --show-error-codes 2>&1 | sed 's/\x1b\[[0-9;]*m//g' || true

echo "# Done"
