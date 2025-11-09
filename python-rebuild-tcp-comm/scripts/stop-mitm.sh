#!/usr/bin/env bash
# Stop MITM proxy running in background

set -e

cd "$(dirname "$0")/.."

PID_FILE="mitm/mitm.pid"

if [[ ! -f "$PID_FILE" ]]; then
  echo "❌ No MITM proxy running (PID file not found)"
  exit 1
fi

MITM_PID=$(cat "$PID_FILE")

if ! ps -p "$MITM_PID" > /dev/null 2>&1; then
  echo "❌ MITM proxy not running (stale PID: $MITM_PID)"
  rm -f "$PID_FILE"
  exit 1
fi

echo "🛑 Stopping MITM proxy (PID: $MITM_PID)..."

# Send SIGTERM for graceful shutdown
kill -TERM "$MITM_PID" 2> /dev/null || true

# Wait up to 5 seconds for graceful shutdown
for _ in {1..5}; do
  if ! ps -p "$MITM_PID" > /dev/null 2>&1; then
    echo "✅ MITM proxy stopped gracefully"
    rm -f "$PID_FILE"
    exit 0
  fi
  sleep 1
done

# Force kill if still running
if ps -p "$MITM_PID" > /dev/null 2>&1; then
  echo "⚠️  Forcing shutdown..."
  kill -KILL "$MITM_PID" 2> /dev/null || true
  sleep 1
fi

if ! ps -p "$MITM_PID" > /dev/null 2>&1; then
  echo "✅ MITM proxy stopped (forced)"
  rm -f "$PID_FILE"
else
  echo "❌ Failed to stop MITM proxy"
  exit 1
fi
