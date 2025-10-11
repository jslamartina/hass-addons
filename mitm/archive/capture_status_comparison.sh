#!/bin/bash
# Capture 0x83 status packets for device 160 before and after mode change

LOG_FILE="status_comparison_$(date +%s).log"
echo "Starting MITM and capturing status packets..."
echo "Logging to: $LOG_FILE"

# Start MITM in background
python3 mitm_with_injection.py > "$LOG_FILE" 2>&1 &
MITM_PID=$!

echo "MITM started (PID: $MITM_PID)"
echo "Waiting 10 seconds for devices to connect and send status..."
sleep 10

echo ""
echo "=== STEP 1: Capturing CURRENT status (should be Traditional mode) ==="
echo "Looking for 0x83 packets containing device 160 (a0 00)..."
grep "DEV->CLOUD: 83 " "$LOG_FILE" | grep "a0 00" | tail -3
echo ""

echo "=== STEP 2: Ready to change mode ==="
echo "When you're ready:"
echo "  1. Change the mode using the Cync app (with Bluetooth OFF)"
echo "  2. Wait 5 seconds"
echo "  3. Press Enter here to capture the NEW status"
echo ""
read -p "Press Enter after changing mode..."

echo ""
echo "=== STEP 3: Capturing NEW status ==="
sleep 2
grep "DEV->CLOUD: 83 " "$LOG_FILE" | grep "a0 00" | tail -3

echo ""
echo "=== STEP 4: Stopping MITM ==="
sudo pkill -9 -f mitm_with_injection.py

echo ""
echo "Full log saved to: $LOG_FILE"
echo "Now let's compare the packets..."
