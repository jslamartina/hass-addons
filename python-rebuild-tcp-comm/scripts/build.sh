#!/usr/bin/env bash
# Build and validate the project

set -e

cd "$(dirname "$0")/.."

echo "=== Building Project ==="

# Install dependencies
echo "1. Installing dependencies..."
poetry install

# Run linting
echo ""
echo "2. Linting..."
./scripts/lint.sh

# Run tests
echo ""
echo "3. Running tests..."
./scripts/test-all.sh

# Build package
echo ""
echo "4. Building package..."
poetry build

echo ""
echo "✓ Build complete!"
echo ""
echo "Artifacts:"
ls -lh dist/
