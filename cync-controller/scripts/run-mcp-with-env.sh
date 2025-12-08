#!/usr/bin/env bash
# MCP Server Environment Wrapper
# This script loads secrets from .mcp-secrets.env and runs MCP servers

set -Eeuo pipefail
IFS=$'\n\t'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091  # Source path is dynamic via $SCRIPT_DIR
source "$SCRIPT_DIR/shell-common/common-output.sh"

# shellcheck disable=SC2034  # LP used by common-output.sh log functions
LP="[$(basename "$0")]"

# Get the repository root (parent of scripts/)
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
SECRETS_FILE="$REPO_ROOT/.mcp-secrets.env"
LOG_DIR="$REPO_ROOT/tmp"
LOG_FILE="$LOG_DIR/mcp-server.log"

# Create log directory if it doesn't exist
mkdir -p "$LOG_DIR"

# Check if secrets file exists
if [[ ! -f "$SECRETS_FILE" ]]; then
  log_error "Secrets file not found at: $SECRETS_FILE"
  echo "Copy .mcp-secrets.env.example to .mcp-secrets.env and fill in your values." >&2
  exit 1
fi

# Load environment variables from secrets file
set -a # Export all variables
# shellcheck disable=SC1090
source "$SECRETS_FILE"
set +a

# Execute the MCP server command, redirecting stderr to log file
# (MCP servers often output status messages to stderr which Cursor shows as errors)
exec "$@" 2>> "$LOG_FILE"
