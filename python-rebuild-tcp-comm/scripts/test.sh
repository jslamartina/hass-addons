#!/usr/bin/env bash
# Run tests with various options

set -e

cd "$(dirname "$0")/.."

echo "=== Running Tests ==="

if [ "$1" = "--verbose" ] || [ "$1" = "-v" ]; then
  poetry run pytest -v tests/
elif [ "$1" = "--coverage" ] || [ "$1" = "-c" ]; then
  echo "Running with coverage report..."
  poetry run pytest --cov=rebuild_tcp_comm --cov-report=term-missing --cov-fail-under=90 tests/
  echo ""
  echo "✅ Coverage report complete (90% threshold enforced)"
elif [ "$1" = "--watch" ] || [ "$1" = "-w" ]; then
  echo "Running in watch mode (requires pytest-watch)..."
  poetry run ptw tests/
else
  # Quick mode (default)
  poetry run pytest -q tests/
fi
