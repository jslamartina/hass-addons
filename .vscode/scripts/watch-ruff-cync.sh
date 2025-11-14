#!/usr/bin/env bash
# Watch wrapper for ruff (cync-controller) - always does full scan
# Args: $1 = single changed file from chokidar (triggers scan, but we scan everything)

set -Eeuo pipefail
IFS=$'\n\t'

cd cync-controller || exit 1

echo "# Scanning..."

# Always check all files
ruff check . --output-format=concise 2>&1 | sed 's/\x1b\[[0-9;]*m//g' || true

echo "# Done"
