#!/bin/bash
# MITM capture script for Cync devices
# Usage: ./mitm_capture.sh [output_filename]

set -e

OUTPUT_FILE="${1:-mitm_capture.txt}"
CERT_PATH="certs/server.pem"

# Cync cloud servers
CLOUD_SERVER_NEW="35.196.85.236:23779" # Newer firmware
# CLOUD_SERVER_OLD="34.73.130.191:23779"  # Older firmware

echo "========================================"
echo "  Cync MITM Capture Starting"
echo "========================================"
echo ""

# Prerequisites check
echo "Checking prerequisites..."
ERRORS=0

# Check socat
if ! command -v socat &> /dev/null; then
  echo "❌ socat not found. Install: sudo apt-get install socat"
  ERRORS=$((ERRORS + 1))
else
  echo "✓ socat installed"
fi

# Check openssl
if ! command -v openssl &> /dev/null; then
  echo "❌ openssl not found"
  ERRORS=$((ERRORS + 1))
else
  echo "✓ openssl installed"
fi

# Check certificates
if [ ! -f "$CERT_PATH" ]; then
  echo "❌ Certificate not found: $CERT_PATH"
  echo "   Run: ./create_certs.sh"
  ERRORS=$((ERRORS + 1))
else
  echo "✓ Certificate exists"
fi

# Check if port 23779 is available
if command -v netstat &> /dev/null; then
  if netstat -tuln 2> /dev/null | grep -q ":23779 "; then
    echo "⚠️  Warning: Port 23779 already in use"
    echo "   Stop cync-lan addon if running"
  else
    echo "✓ Port 23779 available"
  fi
fi

if [ $ERRORS -gt 0 ]; then
  echo ""
  echo "❌ Prerequisites check failed. Please fix the errors above."
  exit 1
fi

echo ""
echo "========================================"
echo "Output file: $OUTPUT_FILE"
echo "Certificate: $CERT_PATH"
echo ""
echo "IMPORTANT STEPS:"
echo "1. Make sure DNS is redirecting Cync domains to this machine"
echo "2. Turn OFF Bluetooth on your phone (force TCP/HTTP)"
echo "3. Make ONE configuration change in Cync app"
echo "4. Press Ctrl+C to stop capture"
echo ""
echo "Cloud server: $CLOUD_SERVER_NEW (trying newer firmware first)"
echo "========================================"
echo ""
sleep 2

# Try newer firmware server
sudo socat -d -d -lf /dev/stdout -x -v \
  ssl-l:23779,reuseaddr,fork,cert="$CERT_PATH",verify=0 \
  openssl:"$CLOUD_SERVER_NEW",verify=0 2> "$OUTPUT_FILE"

echo ""
echo "✓ Capture saved to: $OUTPUT_FILE"
echo ""
echo "To view: cat $OUTPUT_FILE"
echo "To search: grep '>' $OUTPUT_FILE  (device to cloud)"
echo "           grep '<' $OUTPUT_FILE  (cloud to device)"
