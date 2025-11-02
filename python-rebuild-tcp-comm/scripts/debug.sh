#!/usr/bin/env bash
# Run toggler with debug logging and keep metrics server running

set -e

cd "$(dirname "$0")/.."

echo "=== Debug Mode ==="
echo "Starting metrics server on :9400"
echo "Running toggler with DEBUG logging"
echo "Press Ctrl+C to stop"
echo ""

# Run with debug logging
poetry run python -m harness.toggler \
  --device-id="${DEVICE_ID:-DEBUG_DEVICE}" \
  --device-host="${DEVICE_HOST:-127.0.0.1}" \
  --device-port="${DEVICE_PORT:-9000}" \
  --state="${STATE:-on}" \
  --log-level=DEBUG \
  "$@"

echo ""
echo "Check metrics at: http://localhost:9400/metrics"
