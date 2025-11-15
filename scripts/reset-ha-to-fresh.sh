#!/usr/bin/env bash
#
# reset-ha-to-fresh.sh
#
# Complete factory reset of Home Assistant to fresh state (like brand new devcontainer).
# Wipes all data, configurations, and state to recreate the conditions of a fresh build.
#
# This is equivalent to rebuilding the devcontainer but much faster (~2-3min vs ~10min)
# and allows quick iteration when debugging initialization errors that only occur on fresh builds.
#
# Usage:
#   ./scripts/reset-ha-to-fresh.sh
#
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./shell-common/common-output.sh
source "$SCRIPT_DIR/shell-common/common-output.sh"

# shellcheck disable=SC2034  # LP used by common-output.sh log functions
LP="[$(basename "$0")]"
HA_URL="${HA_URL:-http://homeassistant.local:8123}"
SUPERVISOR_DATA="/tmp/supervisor_data"

echo -e "${BLUE}╔═══════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║     Home Assistant COMPLETE Factory Reset             ║${NC}"
echo -e "${BLUE}╚═══════════════════════════════════════════════════════╝${NC}"
echo ""
echo "⚠️  WARNING: This will DELETE EVERYTHING:"
echo "   - All users, integrations, entities"
echo "   - All configurations, automations, scenes"
echo "   - All history and state data"
echo ""
echo "ℹ️  Your addon code in addons/local/ will NOT be deleted"
echo ""
read -p "Type 'yes' to proceed with COMPLETE WIPE: " -r
if [ "$REPLY" != "yes" ]; then
  echo "Cancelled."
  exit 0
fi

# Phase 1: Uninstall non-local addons, then stop HA Core
echo ""
echo "🗑️  Phase 1: Uninstalling non-local addons..."

# Get list of installed addons (exclude local addons - those are our dev code)
installed_addons=$(ha addons --raw-json 2> /dev/null | jq -r '.data.addons[] | select(.repository != "local") | .slug' || true)

if [ -n "$installed_addons" ]; then
  echo "$installed_addons" | while IFS= read -r addon_slug; do
    if [ -n "$addon_slug" ]; then
      echo "     - Uninstalling: $addon_slug"
      ha addons uninstall "$addon_slug" > /dev/null 2>&1 || true
    fi
  done
  echo "✅ Non-local addons uninstalled"
  echo "⏳ Waiting for uninstall jobs to complete..."
  sleep 5
else
  echo "     - No non-local addons to uninstall"
fi

echo ""
echo "🛑 Phase 1b: Stopping Home Assistant Core..."
ha core stop
sleep 10

echo "🗑️  Removing homeassistant container to release file locks..."
docker rm -f homeassistant 2> /dev/null || true
sleep 2
echo "✅ HA Core stopped and container removed"

# Phase 2: Complete wipe - EVERYTHING (matching devcontainer rebuild)
echo ""
echo "🗑️  Phase 2: WIPING ALL supervisor data (matching devcontainer rebuild)..."

if [ ! -d "$SUPERVISOR_DATA" ]; then
  echo "❌ ERROR: Supervisor data directory not found: $SUPERVISOR_DATA"
  exit 1
fi

echo "   Emptying ALL DATA directories in /tmp/supervisor_data/..."
echo "   This matches what happens on devcontainer rebuild (fresh /tmp)"

# Empty data directories (delete contents but keep dirs)
# These are the user data dirs that get recreated fresh on devcontainer rebuild
for dir in homeassistant backup media ssl tmp share; do
  if [ -d "$SUPERVISOR_DATA/$dir" ]; then
    echo "     - Emptying: $dir/*"
    sudo rm -rf "${SUPERVISOR_DATA:?}/$dir"/*
    sudo rm -rf "${SUPERVISOR_DATA:?}/$dir"/.[!.]* # Hidden files
  fi
done

# NOTE: Infrastructure dirs (audio, apparmor, dns, etc.) are NOT emptied
# Supervisor needs these to remain intact with their subdirectories

# Delete all JSON config files in root (supervisor state)
echo "     - Deleting: *.json (all supervisor state files)"
sudo rm -f "$SUPERVISOR_DATA"/*.json

# Delete all hidden files/dirs in root
sudo find "$SUPERVISOR_DATA" -maxdepth 1 -name ".*" ! -name "." ! -name ".." -exec rm -rf {} + 2> /dev/null || true

# Within addons, empty git repos and data (keep dirs)
if [ -d "$SUPERVISOR_DATA/addons/git" ]; then
  echo "     - Emptying: addons/git/*"
  sudo rm -rf "$SUPERVISOR_DATA/addons/git"/*
fi
if [ -d "$SUPERVISOR_DATA/addons/data" ]; then
  echo "     - Emptying: addons/data/*"
  sudo rm -rf "$SUPERVISOR_DATA/addons/data"/*
fi

echo "✅ ALL data completely wiped (matching fresh devcontainer /tmp)"
echo "ℹ️  Preserved: addons/local/ (your addon source code - separate mount)"

# Phase 3: Start HA (will create fresh structure)
echo ""
echo "🚀 Phase 3: Starting HA Core in fresh state..."
ha core start

# Wait for HA to initialize and become responsive
wait_for_ha_ready() {
  local retry=0
  local max_retries=60

  echo "⏳ Waiting for HA to start..."

  while [ $retry -lt $max_retries ]; do
    local onboarding_status
    onboarding_status=$(curl -s -o /dev/null -w "%{http_code}" "$HA_URL/api/onboarding" 2> /dev/null || echo "000")

    if [ "$onboarding_status" = "200" ] || [ "$onboarding_status" = "404" ]; then
      # HTTP 200 = onboarding endpoint available (rare, possibly timing-related)
      # HTTP 404 = normal fresh state after reset (no owner user yet)
      # Note: After factory reset, 404 always means fresh (not complete)
      # Both 200 and 404 are valid "HA is ready" states for this context
      echo "✅ HA is running and responsive (HTTP $onboarding_status)"
      return 0
    elif [ "$onboarding_status" = "000" ]; then
      # No response yet - HA still starting
      sleep 5
      retry=$((retry + 1))
      [ $((retry % 6)) -eq 0 ] && echo "  ⏳ Still waiting for HA to respond... ($((retry * 5))s)"
    else
      # Unexpected status code
      echo "  ⚠️  Unexpected HTTP status: $onboarding_status (retrying...)"
      sleep 5
      retry=$((retry + 1))
    fi
  done

  echo ""
  echo "❌ ERROR: HA failed to respond after $((max_retries * 5)) seconds"
  echo "   Try: ha core logs"
  return 1
}

if ! wait_for_ha_ready; then
  exit 1
fi

echo ""
echo -e "${GREEN}╔═════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║    ✅ Factory Reset Complete!                       ║${NC}"
echo -e "${GREEN}╚═════════════════════════════════════════════════════╝${NC}"
echo ""
echo "Home Assistant is now in FRESH state (like new devcontainer)."
echo ""
echo "Next steps:"
echo "  - Run ./scripts/setup-fresh-ha.sh to complete onboarding"
echo "  - Or manually test the fresh install experience"
