#!/usr/bin/env bash
# Script to programmatically configure the Cync Controller add-on via Supervisor API
# This bypasses the UI and configuration persistence issues in devcontainer
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./shell-common/common-output.sh
source "$SCRIPT_DIR/shell-common/common-output.sh"

# shellcheck disable=SC2034  # LP used by common-output.sh log functions
LP="[$(basename "$0")]"

# Get supervisor token from hassio_cli container
SUPERVISOR_TOKEN=$(docker exec hassio_cli env | grep SUPERVISOR_TOKEN | cut -d= -f2)

if [ -z "$SUPERVISOR_TOKEN" ]; then
  log_error "Could not retrieve SUPERVISOR_TOKEN from hassio_cli container"
  exit 1
fi

ADDON_SLUG="local_cync-controller"
API_BASE="http://supervisor/addons/${ADDON_SLUG}"

# Function to get current configuration
get_config() {
  curl -sSL \
    -H "Authorization: Bearer ${SUPERVISOR_TOKEN}" \
    "${API_BASE}/info" | jq '.data.options'
}

# Function to update configuration
update_config() {
  local new_config="$1"

  log_info "Updating add-on configuration..."

  response=$(curl -sSL -w "\n%{http_code}" \
    -X POST \
    -H "Authorization: Bearer ${SUPERVISOR_TOKEN}" \
    -H "Content-Type: application/json" \
    -d "$new_config" \
    "${API_BASE}/options")

  http_code=$(echo "$response" | tail -n1)
  body=$(echo "$response" | sed '$d')

  if [ "$http_code" -eq 200 ]; then
    log_success "Configuration updated successfully"
    return 0
  else
    log_error "Configuration update failed (HTTP $http_code)"
    echo "$body" | jq '.' 2> /dev/null || echo "$body"
    return 1
  fi
}

# Function to restart add-on
restart_addon() {
  log_info "Restarting add-on..."

  curl -sSL -X POST \
    -H "Authorization: Bearer ${SUPERVISOR_TOKEN}" \
    "${API_BASE}/restart" > /dev/null

  log_success "Add-on restart initiated"
  sleep 3
}

# Function to show logs
show_logs() {
  log_info "Fetching add-on logs..."
  ha addons logs local_cync-controller
}

# Main command processing
case "${1:-}" in
  get)
    log_info "Current configuration:"
    get_config
    ;;

  set-cloud-relay)
    enabled="${2:-false}"
    forward="${3:-true}"
    debug_logging="${4:-false}"

    log_info "Configuring cloud relay mode:"
    echo "  - enabled: $enabled"
    echo "  - forward_to_cloud: $forward"
    echo "  - debug_packet_logging: $debug_logging"

    # Get current config and merge changes
    current_config=$(get_config)

    new_config=$(echo "$current_config" | jq \
      --argjson enabled "$enabled" \
      --argjson forward "$forward" \
      --argjson debug_logging "$debug_logging" \
      '.cloud_relay.enabled = $enabled |
             .cloud_relay.forward_to_cloud = $forward |
             .cloud_relay.debug_packet_logging = $debug_logging')

    update_config "$(echo "{\"options\": $new_config}" | jq -c '.')"
    restart_addon
    sleep 5
    show_logs | tail -50
    ;;

  set-debug)
    debug_enabled="${2:-true}"

    log_info "Setting debug_log_level to: $debug_enabled"

    # Get current config and merge changes
    current_config=$(get_config)

    new_config=$(echo "$current_config" | jq \
      --argjson debug "$debug_enabled" \
      '.debug_log_level = $debug')

    update_config "$(echo "{\"options\": $new_config}" | jq -c '.')"
    restart_addon
    sleep 5
    show_logs | tail -50
    ;;

  preset-baseline)
    log_info "Applying preset: Baseline (LAN-only, relay disabled)"
    current_config=$(get_config)
    new_config=$(echo "$current_config" | jq '.cloud_relay.enabled = false')
    update_config "$(echo "{\"options\": $new_config}" | jq -c '.')"
    restart_addon
    sleep 5
    show_logs | tail -50
    ;;

  preset-relay-with-forward)
    log_info "Applying preset: Cloud Relay with Forwarding"
    current_config=$(get_config)
    new_config=$(echo "$current_config" | jq '
            .cloud_relay.enabled = true |
            .cloud_relay.forward_to_cloud = true |
            .cloud_relay.debug_packet_logging = false
        ')
    update_config "$(echo "{\"options\": $new_config}" | jq -c '.')"
    restart_addon
    sleep 5
    show_logs | tail -50
    ;;

  preset-relay-debug)
    log_info "Applying preset: Cloud Relay with Debug Logging"
    current_config=$(get_config)
    new_config=$(echo "$current_config" | jq '
            .cloud_relay.enabled = true |
            .cloud_relay.forward_to_cloud = true |
            .cloud_relay.debug_packet_logging = true
        ')
    update_config "$(echo "{\"options\": $new_config}" | jq -c '.')"
    restart_addon
    sleep 5
    show_logs | tail -50
    ;;

  preset-lan-only)
    log_info "Applying preset: LAN-only Relay (Privacy Mode)"
    current_config=$(get_config)
    new_config=$(echo "$current_config" | jq '
            .cloud_relay.enabled = true |
            .cloud_relay.forward_to_cloud = false |
            .cloud_relay.debug_packet_logging = true
        ')
    update_config "$(echo "{\"options\": $new_config}" | jq -c '.')"
    restart_addon
    sleep 5
    show_logs | tail -50
    ;;

  restart)
    restart_addon
    ;;

  logs)
    show_logs
    ;;

  *)
    cat << EOF
Usage: $0 <command> [args...]

Commands:
  get                           Show current configuration
  set-debug <true|false>        Enable or disable debug log level
  set-cloud-relay <enabled> <forward> <debug>
                                Set cloud relay options (true/false values)
  preset-baseline               Disable cloud relay (backward compatibility test)
  preset-relay-with-forward     Enable relay with cloud forwarding
  preset-relay-debug            Enable relay with debug packet logging
  preset-lan-only               Enable relay in LAN-only mode (no cloud)
  restart                       Restart the add-on
  logs                          Show add-on logs

Examples:
  # Check current config
  $0 get

  # Enable debug logs
  $0 set-debug true

  # Disable debug logs
  $0 set-debug false

  # Enable cloud relay with forwarding
  $0 set-cloud-relay true true false

  # Apply test presets
  $0 preset-baseline
  $0 preset-relay-with-forward
  $0 preset-relay-debug
  $0 preset-lan-only

EOF
    exit 1
    ;;
esac
