#!/bin/bash
# MCP Server Environment Wrapper
# This script loads secrets from .mcp-secrets.env and runs MCP servers

set -euo pipefail

# Get the repository root (parent of scripts/)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
SECRETS_FILE="$REPO_ROOT/.mcp-secrets.env"
LOG_DIR="$REPO_ROOT/tmp"
LOG_FILE="$LOG_DIR/mcp-server.log"

# Create log directory if it doesn't exist
mkdir -p "$LOG_DIR"

# Check if secrets file exists
if [[ ! -f "$SECRETS_FILE" ]]; then
    echo "ERROR: Secrets file not found at: $SECRETS_FILE" >&2
    echo "Copy .mcp-secrets.env.example to .mcp-secrets.env and fill in your values." >&2
    exit 1
fi

# Load environment variables from secrets file
# shellcheck disable=SC1090
set -a  # Export all variables
source "$SECRETS_FILE"
set +a

# Execute the MCP server command, redirecting stderr to log file
# (MCP servers often output status messages to stderr which Cursor shows as errors)
exec "$@" 2>>"$LOG_FILE"

