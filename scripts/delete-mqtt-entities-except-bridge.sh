#!/usr/bin/env bash
#
# Delete all MQTT entities except CyncLAN Bridge
#
# This script provides a convenient wrapper around the Playwright automation
# that deletes all MQTT entities while preserving the CyncLAN Bridge.
#
# Usage:
#   ./scripts/delete-mqtt-entities-except-bridge.sh [options]
#
# Options:
#   --dry-run       Preview what would be deleted without actually deleting
#   --restart       Restart addon after deletion
#   --headed        Run browser in headed mode (visible)
#   --bridge NAME   Specify bridge name (default: "CyncLAN Bridge")
#   --help          Show this help message
#
# Examples:
#   # Preview what would be deleted
#   ./scripts/delete-mqtt-entities-except-bridge.sh --dry-run
#
#   # Delete entities and restart addon
#   ./scripts/delete-mqtt-entities-except-bridge.sh --restart
#
#   # Delete entities with visible browser
#   ./scripts/delete-mqtt-entities-except-bridge.sh --headed

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_ROOT="$(dirname "$SCRIPT_DIR")"

# Default configuration
export HA_BASE_URL="${HA_BASE_URL:-http://localhost:8123}"
export HA_USERNAME="${HA_USERNAME:-dev}"
export HA_PASSWORD="${HA_PASSWORD:-dev}"
export ADDON_SLUG="${ADDON_SLUG:-local_cync-lan}"
export RESTART_ADDON="${RESTART_ADDON:-false}"
export BRIDGE_NAME="${BRIDGE_NAME:-CyncLAN Bridge}"
export DRY_RUN="${DRY_RUN:-false}"

# Parse command line arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --dry-run)
      export DRY_RUN="true"
      shift
      ;;
    --restart)
      export RESTART_ADDON="true"
      shift
      ;;
    --headed)
      export HEADED="1"
      shift
      ;;
    --bridge)
      export BRIDGE_NAME="$2"
      shift 2
      ;;
    --help)
      grep "^#" "$0" | sed 's/^# //' | sed 's/^#//'
      exit 0
      ;;
    *)
      echo "Unknown option: $1"
      echo "Run with --help for usage information"
      exit 1
      ;;
  esac
done

# Load credentials from env file if it exists
if [ -f "$WORKSPACE_ROOT/hass-credentials.env" ]; then
  # shellcheck disable=SC1091
  source "$WORKSPACE_ROOT/hass-credentials.env"
fi

echo "╔═══════════════════════════════════════════════════════════════════════╗"
echo "║     Delete All MQTT Entities (Except Bridge) - Shell Wrapper        ║"
echo "╚═══════════════════════════════════════════════════════════════════════╝"
echo ""
echo "Configuration:"
echo "  Home Assistant URL: $HA_BASE_URL"
echo "  Bridge to preserve: $BRIDGE_NAME"
echo "  Addon slug:         $ADDON_SLUG"
echo "  Restart after:      $RESTART_ADDON"
echo "  Dry run mode:       $DRY_RUN"
echo ""

# Check if TypeScript/Node dependencies are available
if ! command -v npx &> /dev/null; then
  echo "❌ Error: npx not found. Please install Node.js."
  exit 1
fi

# Run the Playwright script
cd "$WORKSPACE_ROOT"
npx ts-node scripts/playwright/delete-all-mqtt-entities-except-bridge.ts

echo ""
echo "✅ Script completed successfully"
