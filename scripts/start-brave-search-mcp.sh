#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./shell-common/common-output.sh
source "$SCRIPT_DIR/shell-common/common-output.sh"

# shellcheck disable=SC2034  # LP used by common-output.sh log functions
LP="[$(basename "$0")]"

trap 'cleanup' EXIT
trap 'on_error $LINENO' ERR

cleanup() {
  trap - EXIT ERR
}

on_error() {
  log_error "Error on line $1"
  exit 1
}

# Source credentials file to get BRAVE_SEARCH_FREE_API_KEY
CREDENTIALS_FILE="$SCRIPT_DIR/../hass-credentials.env"
if [[ ! -f "$CREDENTIALS_FILE" ]]; then
  log_error "Credentials file not found: $CREDENTIALS_FILE"
  exit 1
fi

# shellcheck disable=SC1090  # Credentials file path is dynamic
source "$CREDENTIALS_FILE"

# Check if BRAVE_SEARCH_FREE_API_KEY is set
if [[ -z "${BRAVE_SEARCH_FREE_API_KEY:-}" ]]; then
  log_error "BRAVE_SEARCH_FREE_API_KEY not found in credentials file"
  exit 1
fi

# Export as BRAVE_API_KEY (what the MCP server expects)
export BRAVE_API_KEY="$BRAVE_SEARCH_FREE_API_KEY"

log_info "Starting Brave Search MCP server..."

# Run the MCP server
exec npx -y @brave/brave-search-mcp-server --transport stdio
