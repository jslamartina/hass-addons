#!/bin/bash
# Watch wrapper for prettier - always checks all files
# Args: $1 = single changed file from chokidar (triggers scan, but we scan everything)

echo "# Scanning..."

# Always check all files to ensure problems clear correctly
OUTPUT=$(npx prettier --ignore-path .prettierignore --check . 2>&1 \
  | sed 's/\x1b\[[0-9;]*m//g' \
  | grep -vE '^(panic:|Checking formatting|\[warn\] Code style)' \
  | sed -n '/^\[warn\] /s/^\[warn\] \(.*\)$/\1:1:0: Code style issues found. Run npm run format to fix./p')

if [ -n "$OUTPUT" ]; then
  echo "$OUTPUT"
fi

echo "# Done"
