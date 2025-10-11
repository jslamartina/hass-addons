#!/bin/bash
# Helper script to inject raw hex bytes into mitm_with_injection.py

if [ -z "$1" ]; then
  echo "Usage: $0 '<hex bytes>'"
  echo ""
  echo "Example:"
  echo " TRADITIONAL - $0 '73 00 00 00 1e 1b dc da 3e 00 3a 00 7e 3d 01 00 00 f8 8e 0c 00 3e 01 00 00 00 a0 00 f7 11 02 01 01 85 7e'"
  echo " SMART - $0 '73 00 00 00 1e 1b dc da 3e 00 29 00 7e 30 01 00 00 f8 8e 0c 00 31 01 00 00 00 a0 00 f7 11 02 01 02 79 7e'"
  echo ""
  echo "The packet will be sent to device 160 via the MITM within 1 second."
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Write the hex bytes to the injection file
echo "$1" > "$SCRIPT_DIR/inject_raw_bytes.txt"

echo "✓ Raw packet injection queued"
echo "  Bytes: $1"
echo "  The packet will be injected within 1 second."
