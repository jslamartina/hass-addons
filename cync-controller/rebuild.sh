#!/bin/bash
set -e

# ========================================================================
# Cync Controller Add-on Rebuild Script
# ========================================================================
# Rebuilds the Cync Controller Home Assistant add-on with the latest source code
# changes from this directory.
# ========================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CREDENTIALS_FILE="${CREDENTIALS_FILE:-$REPO_ROOT/hass-credentials.env}"
CYNC_SLUG="local_cync-controller"

# Run Linting, Formatting, and Unit Tests
npm run lint:python:fix && npm run format:python
npm run test:unit

# Load credentials from hass-credentials.env
load_credentials() {
  if [ ! -f "$CREDENTIALS_FILE" ]; then
    echo "⚠️  Credentials file not found: $CREDENTIALS_FILE"
    echo "⚠️  Addon will need manual configuration"
    return 1
  fi

  # Source the file to load environment variables
  set -a
  # shellcheck source=/dev/null
  source "$CREDENTIALS_FILE"
  set +a

  if [ -z "$CYNC_USERNAME" ] || [ -z "$CYNC_PASSWORD" ]; then
    echo "⚠️  CYNC_USERNAME or CYNC_PASSWORD not found in credentials file"
    echo "⚠️  Addon will need manual configuration"
    return 1
  fi

  echo "✓ Loaded credentials (Cync: $CYNC_USERNAME, MQTT: ${MQTT_USER:-none})"
  return 0
}

# Get supervisor token
get_supervisor_token() {
  SUPERVISOR_TOKEN=$(docker exec hassio_cli env 2> /dev/null | grep SUPERVISOR_TOKEN | cut -d= -f2 || echo "")

  if [ -z "$SUPERVISOR_TOKEN" ]; then
    echo "⚠️  Could not retrieve SUPERVISOR_TOKEN"
    return 1
  fi

  return 0
}

# Configure addon with credentials
configure_addon() {
  if ! get_supervisor_token; then
    echo "⚠️  Cannot configure addon without supervisor token"
    return 1
  fi

  echo "Configuring addon with credentials from $CREDENTIALS_FILE..."

  local config
  config=$(
    cat << EOF
{
  "options": {
    "account_username": "$CYNC_USERNAME",
    "account_password": "$CYNC_PASSWORD",
    "debug_log_level": true,
    "mqtt_host": "localhost",
    "mqtt_port": 1883,
    "mqtt_user": ${MQTT_USER:+\"$MQTT_USER\"},
    "mqtt_pass": ${MQTT_PASS:+\"$MQTT_PASS\"},
    "mqtt_topic": "cync_controller_addon",
    "tuning": {
      "tcp_whitelist": "",
      "command_targets": 2,
      "max_clients": 8
    },
    "cloud_relay": {
      "enabled": false,
      "forward_to_cloud": true,
      "cloud_server": "35.196.85.236",
      "cloud_port": 23779,
      "debug_packet_logging": false,
      "disable_ssl_verification": false
    },
    "features": {
      "expose_device_lights": true
    }
  }
}
EOF
  )

  # Use curl via hassio_cli for configuration
  local response
  response=$(timeout 30 docker exec hassio_cli curl -sf -w "\n%{http_code}" -X POST \
    -H "Authorization: Bearer ${SUPERVISOR_TOKEN}" \
    -H "Content-Type: application/json" \
    "http://supervisor/addons/$CYNC_SLUG/options" \
    -d "$config" 2>&1) || {
    echo "⚠️  Configuration request failed or timed out"
    return 1
  }

  local http_code
  http_code=$(echo "$response" | tail -n1)

  if [ "$http_code" = "200" ]; then
    echo "✓ Addon configured successfully"
    echo "  Cync account: $CYNC_USERNAME"
    echo "  MQTT broker: localhost:1883"
    return 0
  else
    echo "⚠️  Configuration returned HTTP $http_code"
    echo "$response" | head -n -1
    return 1
  fi
}

# Enable "Show in Sidebar" for Cync Controller add-on
enable_sidebar() {
  if ! get_supervisor_token; then
    echo "⚠️  Cannot enable sidebar without supervisor token"
    return 1
  fi

  echo "Enabling 'Show in Sidebar'..."

  local response
  response=$(timeout 30 docker exec hassio_cli curl -sf -w "\n%{http_code}" -X POST \
    -H "Authorization: Bearer ${SUPERVISOR_TOKEN}" \
    -H "Content-Type: application/json" \
    "http://supervisor/addons/$CYNC_SLUG/options" \
    -d '{"ingress_panel": true}' 2>&1) || {
    echo "⚠️  Failed to enable sidebar"
    return 1
  }

  local http_code
  http_code=$(echo "$response" | tail -n1)

  if [ "$http_code" = "200" ]; then
    echo "✓ Sidebar enabled"
    return 0
  else
    echo "⚠️  Sidebar configuration returned HTTP $http_code"
    return 1
  fi
}

echo "========================================="
echo "Rebuilding Cync Controller addon..."
echo "========================================="

# Workaround for "Can't rebuild image based add-on" error
# Uninstall and reinstall to force a rebuild from source
echo "Uninstalling addon to clear cache..."
ha addons uninstall local_cync-controller || true

echo ""
echo "Reinstalling addon (this will build from source)..."
ha addons install local_cync-controller

echo ""
# Load and apply configuration
if load_credentials; then
  configure_addon || echo "⚠️  Continuing without configuration..."
  enable_sidebar || echo "⚠️  Continuing without sidebar..."
else
  echo "⚠️  Skipping automatic configuration"
fi

echo ""
echo "Starting addon..."
if ha addons start local_cync-controller; then
  echo "✓ Addon started successfully"
else
  echo "⚠️  Addon start failed (may need manual configuration)"
  echo "   Configure via: Settings → Add-ons → Cync Controller → Configuration"
fi

echo ""
echo "========================================="
ha addons info local_cync-controller
echo "========================================="
echo "✓ Rebuild complete!"
