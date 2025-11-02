#!/usr/bin/env bash
# Run the toggler with common configurations

set -e

cd "$(dirname "$0")/.."

# Default values
DEVICE_ID="${DEVICE_ID:-DEVICE123}"
DEVICE_HOST="${DEVICE_HOST:-192.168.1.100}"
DEVICE_PORT="${DEVICE_PORT:-9000}"
LOG_LEVEL="${LOG_LEVEL:-INFO}"
STATE="${STATE:-on}"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --device-id)
            DEVICE_ID="$2"
            shift 2
            ;;
        --host)
            DEVICE_HOST="$2"
            shift 2
            ;;
        --port)
            DEVICE_PORT="$2"
            shift 2
            ;;
        --state)
            STATE="$2"
            shift 2
            ;;
        --debug)
            LOG_LEVEL="DEBUG"
            shift
            ;;
        --help|-h)
            echo "Usage: $0 [options]"
            echo ""
            echo "Options:"
            echo "  --device-id ID    Device identifier (default: DEVICE123)"
            echo "  --host HOST       Device host/IP (default: 192.168.1.100)"
            echo "  --port PORT       Device port (default: 9000)"
            echo "  --state STATE     Desired state: on/off (default: on)"
            echo "  --debug           Enable debug logging"
            echo "  --help, -h        Show this help message"
            echo ""
            echo "Environment variables:"
            echo "  DEVICE_ID, DEVICE_HOST, DEVICE_PORT, LOG_LEVEL, STATE"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

echo "=== Running Toggler ==="
echo "Device: $DEVICE_ID @ $DEVICE_HOST:$DEVICE_PORT"
echo "State: $STATE"
echo "Log Level: $LOG_LEVEL"
echo ""

poetry run python -m rebuild_tcp_comm.harness.toggler \
    --device-id="$DEVICE_ID" \
    --device-host="$DEVICE_HOST" \
    --device-port="$DEVICE_PORT" \
    --state="$STATE" \
    --log-level="$LOG_LEVEL"

