#!/bin/bash
# Helper script to restart the MITM server

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_FILE="$SCRIPT_DIR/mitm_proxy.log"

echo "Stopping any running MITM processes..."
pkill -f mitm_with_injection.py 2> /dev/null

echo "Waiting for port 23779 to free up..."
sleep 3

# Check if port is still in use
if lsof -i :23779 > /dev/null 2>&1; then
  echo "⚠️  Warning: Port 23779 still in use!"
  echo "   Attempting forceful cleanup..."
  pkill -9 -f mitm_with_injection.py 2> /dev/null
  sleep 2
fi

# Verify port is free
if lsof -i :23779 > /dev/null 2>&1; then
  echo "❌ Error: Port 23779 is still in use. Cannot start MITM."
  echo "   Check what's using the port: lsof -i :23779"
  exit 1
fi

echo "Clearing old logs..."
> "$LOG_FILE" # Truncate mitm_proxy.log
# Note: mitm.log removed - now only using mitm_proxy.log

echo "Starting MITM server..."
cd "$SCRIPT_DIR"

# Start MITM with fresh log
python3 -u mitm_with_injection.py 2>&1 | tee "$LOG_FILE" &
MITM_PID=$!

# Give it a moment to start
sleep 2

# Verify it's running
if ps -p $MITM_PID > /dev/null 2>&1; then
  echo ""
  echo "✓ MITM server started successfully"
  echo "  PID: $MITM_PID"
  echo "  Log: $LOG_FILE"
  echo ""
  echo "Available commands:"
  echo "  - Inject mode: ./inject_mode.sh smart|traditional"
  echo "  - Inject raw bytes: ./inject_raw.sh '<hex bytes>'"
  echo "  - View logs: tail -f mitm_proxy.log"
  echo "  - Stop MITM: pkill -f mitm_with_injection.py"
  echo ""
  echo "Monitoring startup..."
  tail -5 "$LOG_FILE"
else
  echo "❌ Error: MITM server failed to start"
  echo "Check the log for errors: cat $LOG_FILE"
  exit 1
fi
