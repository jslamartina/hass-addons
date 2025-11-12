#!/usr/bin/env bash
# Run unit tests only (fast, with mocks)

set -e

cd "$(dirname "$0")/.."

echo "=== Running Unit Tests ==="

# Run unit tests (exclude integration tests)
# Note: Coverage must run sequentially due to coverage tool limitations
if [ "$1" = "--verbose" ] || [ "$1" = "-v" ]; then
  poetry run pytest -v -n auto -m "not integration" tests/unit/
elif [ "$1" = "--coverage" ] || [ "$1" = "-c" ]; then
  echo "Running with coverage report (sequential mode required for coverage)..."
  poetry run pytest -m "not integration" \
    --cov=src \
    --cov-report=term-missing \
    --cov-fail-under=90 \
    -n 0 \
    tests/unit/
  echo ""
  echo "✅ Coverage report complete (90% threshold enforced)"
else
  # Quick mode (default) - parallel execution for speed
  poetry run pytest -q -n auto -m "not integration" tests/unit/
fi

echo ""
echo "✅ Unit tests completed"
