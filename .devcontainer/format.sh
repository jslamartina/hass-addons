#!/bin/bash
set -e

echo "🎨 Formatting files with Prettier..."

# Format all files (including shell scripts)
npx prettier --write . --ignore-path .prettierignore

echo "✅ Formatting complete!"
