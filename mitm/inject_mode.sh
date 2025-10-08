#!/bin/bash
# Helper script to inject mode change commands into mitm_with_injection.py

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODE=$1

if [ -z "$MODE" ]; then
  echo "Usage: $0 <mode>"
  echo "  mode: 'smart' or 'traditional'"
  exit 1
fi

if [ "$MODE" != "smart" ] && [ "$MODE" != "traditional" ]; then
  echo "Invalid mode: $MODE. Must be 'smart' or 'traditional'."
  exit 1
fi

# Write the command to the injection file
echo "$MODE" > "$SCRIPT_DIR/inject_command.txt"

echo "✓ Mode injection command sent: $MODE"
echo "  The packet will be injected within 1 second if devices are connected."
