#!/usr/bin/env bash
# Common output styling functions for all shell scripts
# Provides standardized colors, logging functions, and formatting
#
# Usage:
#   SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
#   source "$SCRIPT_DIR/lib/common-output.sh"
#   LP="[$(basename "$0")]"
#
# Then use: log_info, log_warn, log_error, log_success, log_section, test_result

# Standard 4-color palette
RED='\033[0;31m'    # Errors, failures
GREEN='\033[0;32m'  # Success, pass
YELLOW='\033[1;33m' # Warnings, info
BLUE='\033[0;34m'   # Section headers, neutral info
NC='\033[0m'        # No Color (reset)

# Standard logging functions
# These functions expect LP variable to be set by the calling script
log_info() {
  echo -e "${GREEN}${LP:-[script]}${NC} $1"
}

log_warn() {
  echo -e "${YELLOW}${LP:-[script]}${NC} $1"
}

log_error() {
  echo -e "${RED}${LP:-[script]}${NC} $1" >&2
}

log_success() {
  echo -e "${GREEN}${LP:-[script]} ✅${NC} $1"
}

log_section() {
  echo ""
  echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
  echo -e "${BLUE}  $1${NC}"
  echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
  echo ""
}

# Test result function (for test scripts like test-cloud-relay.sh)
test_result() {
  local name="$1"
  local passed="$2"
  local message="${3:-}"

  if [ "$passed" = "true" ]; then
    echo -e "${GREEN}✅ PASS${NC} - $name"
    [ -n "$message" ] && echo "   $message"
  else
    echo -e "${RED}❌ FAIL${NC} - $name"
    [ -n "$message" ] && echo "   $message"
  fi
}
