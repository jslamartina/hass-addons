#!/usr/bin/env bash
# Run integration tests with real TCP server

set -e

cd "$(dirname "$0")/.."

echo "=== Running Integration Tests ==="
echo ""
echo "These tests use a real asyncio TCP server and take longer than unit tests."
echo ""

# Run integration tests sequentially (no parallel execution)
# Generate both JUnit XML and HTML reports
if [ "$1" = "--verbose" ] || [ "$1" = "-v" ]; then
  poetry run pytest -v -m integration tests/integration/ \
    --junit-xml=test-reports/integration-junit.xml
elif [ "$1" = "--html" ]; then
  echo "Running with HTML report..."
  poetry run pytest -v -m integration tests/integration/ \
    --junit-xml=test-reports/integration-junit.xml \
    --html=test-reports/integration-report.html --self-contained-html
  echo ""
  echo "HTML report generated in test-reports/integration-report.html"
else
  # Default mode
  poetry run pytest -m integration tests/integration/ \
    --junit-xml=test-reports/integration-junit.xml
fi

echo ""
echo "✅ Integration tests completed"
echo "JUnit XML report: test-reports/integration-junit.xml"
echo ""
echo "Performance Report:"
echo "  - JSON artifact: test-reports/performance-report.json"
echo "  - Thresholds: p95 < 300ms (Phase 0 target)"
echo "  - Note: Performance warnings are informational only"
