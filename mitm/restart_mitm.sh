#!/bin/bash
# Helper script to restart the MITM server

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Stopping any running MITM processes..."
sudo pkill -9 -f mitm_with_injection.py

echo "Waiting for cleanup..."
sleep 2

echo "Starting MITM server..."
cd "$SCRIPT_DIR"
python3 -u mitm_with_injection.py 2>&1 | tee -a mitm.log &
MITM_PID=$!

echo ""
echo "✓ MITM server started (PID: $MITM_PID)"
echo "  Logging to: $SCRIPT_DIR/mitm.log"
echo ""
echo "Available commands:"
echo "  - Inject mode: ./inject_mode.sh smart|traditional"
echo "  - Inject raw bytes: ./inject_raw.sh '<hex bytes>'"
echo "  - View logs: tail -f mitm.log"
echo "  - Stop MITM: sudo pkill -9 -f mitm_with_injection.py"
