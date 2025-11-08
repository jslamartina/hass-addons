#!/usr/bin/env bash
# Start MITM proxy in local integration mode (background)
#
# Captures traffic between devices and Home Assistant cync-controller
# for protocol debugging and validation.

set -e

cd "$(dirname "$0")/.."

# Default values
LISTEN_PORT="${LISTEN_PORT:-23779}"
UPSTREAM_HOST="${UPSTREAM_HOST:-homeassistant.local}"
UPSTREAM_PORT="${UPSTREAM_PORT:-23779}"
API_PORT="${API_PORT:-8080}"

# Parse arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --listen-port)
      LISTEN_PORT="$2"
      shift 2
      ;;
    --upstream-host)
      UPSTREAM_HOST="$2"
      shift 2
      ;;
    --upstream-port)
      UPSTREAM_PORT="$2"
      shift 2
      ;;
    --api-port)
      API_PORT="$2"
      shift 2
      ;;
    --help | -h)
      echo "Usage: $0 [options]"
      echo ""
      echo "Start MITM proxy in local integration mode (background)"
      echo ""
      echo "Options:"
      echo "  --listen-port PORT      Listen port (default: 23779)"
      echo "  --upstream-host HOST    Upstream host (default: homeassistant.local)"
      echo "  --upstream-port PORT    Upstream port (default: 23779)"
      echo "  --api-port PORT         REST API port (default: 8080)"
      echo "  --help, -h              Show this help message"
      echo ""
      echo "Environment variables:"
      echo "  LISTEN_PORT, UPSTREAM_HOST, UPSTREAM_PORT, API_PORT"
      echo ""
      echo "To stop: ./scripts/stop-mitm.sh"
      exit 0
      ;;
    *)
      echo "Unknown option: $1"
      echo "Use --help for usage information"
      exit 1
      ;;
  esac
done

# Check if already running
PID_FILE="mitm/mitm.pid"
if [[ -f "$PID_FILE" ]]; then
  OLD_PID=$(cat "$PID_FILE")
  if ps -p "$OLD_PID" > /dev/null 2>&1; then
    echo "❌ MITM proxy already running (PID: $OLD_PID)"
    echo "   Stop it first with: ./scripts/stop-mitm.sh"
    exit 1
  else
    # Stale PID file
    rm -f "$PID_FILE"
  fi
fi

# Ensure captures directory exists
mkdir -p mitm/captures

# Generate timestamped log file
LOG_FILE="mitm/captures/mitm_$(date +%Y%m%d_%H%M%S).log"

echo "=== Starting MITM Proxy (Local Integration Mode) ==="
echo "Configuration:"
echo "  Listen:   0.0.0.0:$LISTEN_PORT (TLS)"
echo "  Upstream: $UPSTREAM_HOST:$UPSTREAM_PORT"
echo "  API:      http://localhost:$API_PORT"
echo ""
echo "Network flow:"
echo "  Devices → MITM (devcontainer) → cync-controller (HA)"
echo ""

# Start MITM proxy in background
nohup poetry run cync-mitm \
  --listen-port "$LISTEN_PORT" \
  --upstream-host "$UPSTREAM_HOST" \
  --upstream-port "$UPSTREAM_PORT" \
  --api-port "$API_PORT" \
  > "$LOG_FILE" 2>&1 &

# Save PID
MITM_PID=$!
echo "$MITM_PID" > "$PID_FILE"

# Wait a moment to check if it started successfully
sleep 2

if ps -p "$MITM_PID" > /dev/null 2>&1; then
  echo "✅ MITM proxy started successfully (PID: $MITM_PID)"
  echo ""
  echo "📝 Logs:     tail -f $LOG_FILE"
  echo "📊 Metrics:  curl http://localhost:$API_PORT/inject"
  echo "🛑 Stop:     ./scripts/stop-mitm.sh"
  echo ""
  echo "Packet captures will be saved to: mitm/captures/"
else
  echo "❌ Failed to start MITM proxy"
  echo "Check logs: $LOG_FILE"
  rm -f "$PID_FILE"
  exit 1
fi
