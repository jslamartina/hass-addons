#!/usr/bin/env bash
# Check metrics endpoint

set -e

METRICS_PORT="${METRICS_PORT:-9400}"
METRICS_URL="http://localhost:${METRICS_PORT}/metrics"

echo "=== Checking Metrics Endpoint ==="
echo "URL: $METRICS_URL"
echo ""

if command -v curl &> /dev/null; then
  curl -s "$METRICS_URL" || echo "Error: Could not connect to metrics endpoint"
else
  echo "Error: curl not found. Install curl or check manually at $METRICS_URL"
  exit 1
fi
