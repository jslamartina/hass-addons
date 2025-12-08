#!/usr/bin/env bash
#
# reset-ha-to-fresh-onboarded.sh
#
# Complete factory reset of Home Assistant to fresh state, then immediately runs
# automated onboarding to reach "fresh but onboarded" state.
#
# This is equivalent to rebuilding the devcontainer AND running setup-fresh-ha.sh
# but much faster (~3-4min vs ~10min rebuild + setup).
#
# Usage:
#   ./scripts/reset-ha-to-fresh-onboarded.sh
#
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091  # Source path is dynamic via $SCRIPT_DIR
source "$SCRIPT_DIR/shell-common/common-output.sh"

# shellcheck disable=SC2034  # LP used by common-output.sh log functions
LP="[$(basename "$0")]"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo -e "${BLUE}╔═══════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║   Home Assistant Factory Reset + Onboarding          ║${NC}"
echo -e "${BLUE}╚═══════════════════════════════════════════════════════╝${NC}"
echo ""
echo "This will:"
echo "  1. Reset HA to fresh state (like devcontainer rebuild)"
echo "  2. Automatically run onboarding and setup"
echo ""
read -p "Type 'yes' to proceed: " -r
if [ "$REPLY" != "yes" ]; then
  echo "Cancelled."
  exit 0
fi

# Phase 1: Reset to fresh state
echo ""
echo "Phase 1: Resetting to fresh state..."
"$REPO_ROOT/scripts/reset-ha-to-fresh.sh" <<< "yes"

# Phase 2: Run automated onboarding
echo ""
echo -e "${BLUE}╔═══════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║     Phase 2: Automated Onboarding                     ║${NC}"
echo -e "${BLUE}╚═══════════════════════════════════════════════════════╝${NC}"
echo ""
"$REPO_ROOT/scripts/setup-fresh-ha.sh"

echo ""
echo -e "${GREEN}╔═══════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║    Reset + Onboarding Complete!                       ║${NC}"
echo -e "${GREEN}╚═══════════════════════════════════════════════════════╝${NC}"
echo ""
echo "HA is now in 'fresh but onboarded' state."
echo "All add-ons installed and configured."
