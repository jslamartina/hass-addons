#!/usr/bin/env bash
# Run unit tests only (fast, with mocks)

set -e

cd "$(dirname "$0")/.."

echo "=== Running Unit Tests ==="

# Run unit tests (exclude integration tests)
if [ "$1" = "--verbose" ] || [ "$1" = "-v" ]; then
  poetry run pytest -v -m "not integration" tests/unit/
elif [ "$1" = "--coverage" ] || [ "$1" = "-c" ]; then
  echo "Running with coverage report..."
  poetry run pytest -m "not integration" \
    --cov=src \
    --cov-report=term-missing \
    --cov-fail-under=90 \
    tests/unit/
  echo ""
  echo "✅ Coverage report complete (90% threshold enforced)"
else
  # Quick mode (default)
  poetry run pytest -q -m "not integration" tests/unit/
fi

echo ""
echo "✅ Unit tests completed"
