#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091  # Source path is dynamic via $SCRIPT_DIR
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

CREDENTIALS_FILE="$SCRIPT_DIR/../hass-credentials.env"
if [[ ! -f "$CREDENTIALS_FILE" ]]; then
  log_error "Credentials file not found: $CREDENTIALS_FILE"
  exit 1
fi

# shellcheck disable=SC1090
source "$CREDENTIALS_FILE"

if [[ -z "${GITHUB_MCP_TOKEN:-}" ]]; then
  log_error "GITHUB_MCP_TOKEN not set in $CREDENTIALS_FILE"
  exit 1
fi

DEFAULT_TOOLSETS="context,actions,code_security,dependabot,issues,labels,pull_requests,repos,users"
export GITHUB_PERSONAL_ACCESS_TOKEN="$GITHUB_MCP_TOKEN"
export GITHUB_TOOLSETS="${GITHUB_TOOLSETS:-$DEFAULT_TOOLSETS}"

log_info "Starting GitHub MCP server via Docker..."

exec docker run \
  -i \
  --rm \
  -e GITHUB_PERSONAL_ACCESS_TOKEN \
  -e GITHUB_TOOLSETS \
  ghcr.io/github/github-mcp-server \
  "$@"

