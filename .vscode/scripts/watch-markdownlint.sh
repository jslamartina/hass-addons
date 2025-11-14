#!/bin/bash
# Watch wrapper for markdownlint - always does full scan
# Args: $1 = single changed file from chokidar (triggers scan, but we scan everything)

echo "# Scanning..."

# Always lint all files to ensure problems clear correctly
# Note: Using markdownlint-cli2 without --fix to only report issues, not modify files
# Background watch tasks should not automatically modify source files
find . \( -name "*.md" -o -name "*.mdc" \) -not -path "*/node_modules/*" -print0 \
  | xargs -0 npx markdownlint-cli2 2>&1 \
  | sed 's/\x1b\[[0-9;]*m//g' \
  | grep -E '^[^:]+:[0-9]+(:[0-9]+)? ' \
  | sed -E 's/^([^:]+):([0-9]+):([0-9]+) ([A-Z0-9]+)\/([^ ]+) (.+)$/\1:\2:\3:\4:\6/' \
  | sed -E 's/^([^:]+):([0-9]+) ([A-Z0-9]+)\/([^ ]+) (.+)$/\1:\2:0:\3:\5/' \
  | sed -E 's/ \[Context:.*\]$//' \
  | sed "s|^|${WORKSPACE_FOLDER}/|" || true

echo "# Done"
