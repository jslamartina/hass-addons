#!/usr/bin/env bash
# Automated setup script for fresh Home Assistant installation
# Creates user, installs EMQX and Cync Controller add-ons with configuration
set -e

# Error handling - show better error messages when script fails
trap 'echo "ERROR: Script failed at line $LINENO with exit code $?"; echo "Last command that failed: $BASH_COMMAND"; echo "Stack trace:"; caller; exit 1' ERR

# Also trap EXIT to catch any unexpected exits
trap 'if [ $? -ne 0 ]; then echo "ERROR: Script exited with code $?"; fi' EXIT

LP="[setup-fresh-ha.sh]"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Default values
# Auto-detect HA IP from ha core info if not specified
if [ -z "$HA_URL" ]; then
  HA_IP=$(ha core info 2> /dev/null | grep 'ip_address:' | awk '{print $2}')
  HA_URL="http://${HA_IP:-homeassistant.local}:8123"
fi
CREDENTIALS_FILE="${CREDENTIALS_FILE:-$REPO_ROOT/hass-credentials.env}"
SUPERVISOR_TOKEN=""

# MQTT integration defaults
MQTT_BROKER_HOST_DEFAULT="a0d7b954-emqx"
MQTT_BROKER_HOST_FALLBACK="localhost"
MQTT_BROKER_PORT=1883
MQTT_ACTIVE_HOST=""
MQTT_LAST_ABORT_REASON=""

# Add-on slugs
EMQX_SLUG="a0d7b954_emqx"
CYNC_SLUG="local_cync-controller"
HASSIO_ADDONS_REPO="https://github.com/hassio-addons/repository"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
  echo -e "${GREEN}$LP${NC} $1"
}

log_warn() {
  echo -e "${YELLOW}$LP${NC} $1"
}

log_error() {
  echo -e "${RED}$LP${NC} $1"
}

log_success() {
  echo -e "${GREEN}$LP ✅${NC} $1"
}

# Load credentials from .hass-credentials file
load_credentials() {
  log_info "Loading credentials from $CREDENTIALS_FILE..."

  if [ ! -f "$CREDENTIALS_FILE" ]; then
    log_error "Credentials file not found: $CREDENTIALS_FILE"
    exit 1
  fi

  # Source the file to load environment variables
  set -a
  # shellcheck source=/dev/null
  source "$CREDENTIALS_FILE"
  set +a

  if [ -z "$HASS_USERNAME" ] || [ -z "$HASS_PASSWORD" ]; then
    log_error "HASS_USERNAME or HASS_PASSWORD not found in credentials file"
    exit 1
  fi

  log_success "Credentials loaded (username: $HASS_USERNAME)"
  if [ -n "$CYNC_USERNAME" ]; then
    log_info "Cync credentials found (username: $CYNC_USERNAME)"
  fi
  if [ -n "$MQTT_USER" ]; then
    log_info "MQTT credentials found (username: $MQTT_USER)"
  fi
}

# Wait for Home Assistant API to be responsive
wait_for_ha() {
  log_info "Waiting for Home Assistant to be ready..."

  local retry_count=0
  local max_retries=60
  local retry_delay=5

  while [ $retry_count -lt $max_retries ]; do
    # Check if onboarding endpoint responds (doesn't require auth)
    if curl -sf "$HA_URL/api/onboarding" > /dev/null 2>&1; then
      log_success "Home Assistant API is responsive"
      return 0
    fi

    retry_count=$((retry_count + 1))
    log_info "Waiting for HA API... ($retry_count/$max_retries, sleeping ${retry_delay}s)"
    sleep $retry_delay
  done

  log_error "Home Assistant API not responsive after $max_retries attempts"
  exit 1
}

# Check if onboarding is needed (no users exist)
check_onboarding_status() {
  log_info "Checking onboarding status..."

  # Try to access onboarding endpoint
  local response
  response=$(curl -sf "$HA_URL/api/onboarding" 2> /dev/null || echo "")

  if [ -z "$response" ]; then
    log_info "Onboarding API not available, checking if users exist..."
    # Try to get a token - if this fails, onboarding is needed
    return 0
  fi

  # Check if user step is done
  local user_done
  user_done=$(echo "$response" | jq -r '.[] | select(.step == "user") | .done' 2> /dev/null)

  if [ "$user_done" = "true" ]; then
    log_info "User already created (onboarding in progress or complete)"
    return 1
  fi

  log_info "Home Assistant needs onboarding"
  return 0
}

# Create the first user via onboarding API
create_first_user() {
  log_info "Creating first user: $HASS_USERNAME..."

  # Note: ha CLI doesn't have onboarding commands, so we'll use curl for this specific API
  local response
  response=$(curl -sf -w "\n%{http_code}" -X POST \
    "$HA_URL/api/onboarding/users" \
    -H "Content-Type: application/json" \
    -d "{
            \"name\": \"$HASS_USERNAME\",
            \"username\": \"$HASS_USERNAME\",
            \"password\": \"$HASS_PASSWORD\",
            \"language\": \"en\",
            \"client_id\": \"$HA_URL/\"
        }" 2>&1)

  local http_code
  http_code=$(echo "$response" | tail -n1)
  local body
  body=$(echo "$response" | sed '$d')

  if [ "$http_code" = "200" ] || [ "$http_code" = "201" ]; then
    log_success "User created successfully"

    # Try to extract auth token from response
    local auth_token
    auth_token=$(echo "$body" | jq -r '.access_token // .auth_code // empty' 2> /dev/null)
    if [ -n "$auth_token" ]; then
      log_info "Auth token received from user creation"
      echo "$auth_token"
    else
      log_warn "No auth token found in response"
      log_warn "Response body: $body"
    fi
    return 0
  else
    log_error "Failed to create user (HTTP $http_code)"
    echo "$body" | jq '.' 2> /dev/null || echo "$body"
    return 1
  fi
}

# Complete onboarding by setting up core config
complete_onboarding() {
  log_info "Completing onboarding (core config)..."

  # Note: ha CLI doesn't have onboarding commands, so we'll use curl for this specific API
  local response
  local http_code

  # Capture full response including errors
  response=$(curl -sf -w "\n%{http_code}" -X POST \
    "$HA_URL/api/onboarding/core_config" \
    -H "Content-Type: application/json" \
    -d "{}" 2>&1) || true # Don't exit on curl failure

  http_code=$(echo "$response" | tail -n1)
  local body
  body=$(echo "$response" | sed '$d')

  if [ "$http_code" = "200" ] || [ "$http_code" = "201" ]; then
    log_success "Onboarding completed"
    return 0
  elif [ "$http_code" = "404" ]; then
    log_info "Onboarding already completed (endpoint no longer available)"
    return 0
  else
    log_warn "Onboarding completion returned HTTP $http_code (may already be complete)"
    if [ -n "$body" ]; then
      echo "Response: $body"
    fi
    return 0
  fi
}

# Get supervisor token from hassio_cli container
get_supervisor_token() {
  log_info "Extracting Supervisor token..."

  SUPERVISOR_TOKEN=$(docker exec hassio_cli env 2> /dev/null | grep SUPERVISOR_TOKEN | cut -d= -f2 || echo "")

  if [ -z "$SUPERVISOR_TOKEN" ]; then
    log_error "Could not retrieve SUPERVISOR_TOKEN from hassio_cli container"
    exit 1
  fi

  log_success "Supervisor token retrieved"
}

# Wait for supervisor to be healthy
wait_for_supervisor() {
  log_info "Waiting for Supervisor to be healthy..."

  local retry_count=0
  local max_retries=30
  local retry_delay=5

  while [ $retry_count -lt $max_retries ]; do
    local healthy
    healthy=$(ha supervisor info --raw-json 2> /dev/null \
      | jq -r '.data.healthy // false' 2> /dev/null)

    if [ "$healthy" = "true" ]; then
      log_success "Supervisor is healthy"
      return 0
    fi

    retry_count=$((retry_count + 1))
    log_info "Waiting for Supervisor... ($retry_count/$max_retries)"
    sleep $retry_delay
  done

  log_error "Supervisor not healthy after $max_retries attempts"
  exit 1
}

# Add hassio-addons repository for EMQX
add_emqx_repository() {
  log_info "Checking if hassio-addons repository is already added..."

  # Get list of repositories
  local repos
  repos=$(ha store --raw-json 2> /dev/null \
    | jq -r '.data.repositories[].source' 2> /dev/null || echo "")

  if echo "$repos" | grep -q "$HASSIO_ADDONS_REPO"; then
    log_info "Repository already added, skipping"
    return 0
  fi

  log_info "Adding hassio-addons repository..."

  local response
  # Add repository using ha CLI
  if ha store add "$HASSIO_ADDONS_REPO" > /dev/null 2>&1; then
    response="200"
  else
    response="400"
  fi

  if [ "$response" = "200" ]; then
    log_success "Repository added successfully"

    # Reload store to refresh add-on list
    log_info "Reloading add-on store..."
    ha store reload > /dev/null 2>&1

    # Wait for store to refresh
    sleep 5

    log_success "Add-on store reloaded"
    return 0
  else
    log_error "Failed to add repository"
    return 1
  fi
}

# Install EMQX add-on
install_emqx() {
  log_info "Checking if EMQX add-on is already installed..."

  # Check if already installed
  local installed
  installed=$(ha addons info "$EMQX_SLUG" --raw-json 2> /dev/null \
    | jq -r '.data.version // null' 2> /dev/null)

  if [ "$installed" != "null" ] && [ "$installed" != "" ]; then
    log_info "EMQX already installed"
    return 0
  fi

  log_info "Installing EMQX add-on..."
  if ha addons install "$EMQX_SLUG" > /dev/null 2>&1; then
    log_success "EMQX installed successfully"
    return 0
  else
    log_error "Failed to install EMQX"
    return 1
  fi
}

# Configure EMQX add-on with credentials
configure_emqx() {
  log_info "Configuring EMQX with required settings..."

  # EMQX requires node.cookie to be set via environment variable
  # Also disable authentication for development (no auth needed in dev environment)
  local config
  config=$(
    cat << EOF
{
  "options": {
    "env_vars": [
      {
        "name": "EMQX_NODE__COOKIE",
        "value": "emqxsecretcookie"
      },
      {
        "name": "EMQX_LISTENERS__TCP__DEFAULT__ENABLE_AUTHN",
        "value": "false"
      }
    ]
  }
}
EOF
  )

  # Use curl for configuration since ha CLI doesn't support options
  local response
  response=$(timeout 30 docker exec hassio_cli curl -sf -w "\n%{http_code}" -X POST \
    -H "Authorization: Bearer ${SUPERVISOR_TOKEN}" \
    -H "Content-Type: application/json" \
    "http://supervisor/addons/$EMQX_SLUG/options" \
    -d "$config" 2>&1) || {
    log_warn "EMQX configuration timed out or failed"
    return 0
  }

  local http_code
  http_code=$(echo "$response" | tail -n1)

  if [ "$http_code" = "200" ]; then
    log_success "EMQX configured successfully"
  else
    log_warn "EMQX configuration returned HTTP $http_code"
  fi
}

# Enable "Add to Sidebar" for EMQX add-on
enable_emqx_sidebar() {
  log_info "Enabling 'Add to Sidebar' for EMQX..."

  local response
  response=$(timeout 30 docker exec hassio_cli curl -sf -w "\n%{http_code}" -X POST \
    -H "Authorization: Bearer ${SUPERVISOR_TOKEN}" \
    -H "Content-Type: application/json" \
    "http://supervisor/addons/$EMQX_SLUG/options" \
    -d '{"ingress_panel": true}' 2>&1) || {
    log_warn "Failed to enable sidebar for EMQX"
    return 0
  }

  local http_code
  http_code=$(echo "$response" | tail -n1)

  if [ "$http_code" = "200" ]; then
    log_success "EMQX sidebar enabled"
    return 0
  else
    log_warn "EMQX sidebar configuration returned HTTP $http_code"
    return 0
  fi
}

# Start EMQX add-on
start_emqx() {
  log_info "Starting EMQX add-on..."

  # Check current state
  local current_state
  current_state=$(ha addons info "$EMQX_SLUG" --raw-json 2> /dev/null \
    | jq -r '.data.state // "unknown"' 2> /dev/null)

  log_info "Current EMQX state: $current_state"

  if [ "$current_state" = "started" ]; then
    log_success "EMQX already running"
    return 0
  fi

  # Start the addon asynchronously (ha addons start can hang, so we poll instead)
  log_info "Issuing start command..."
  ha addons start "$EMQX_SLUG" > /dev/null 2>&1 &
  local start_pid=$!

  # Give the command a moment to process
  sleep 2

  # Check if the background process is still running or has failed immediately
  if ! kill -0 $start_pid 2> /dev/null; then
    # Process already exited - check if it succeeded
    wait $start_pid 2> /dev/null
    local exit_code=$?
    if [ $exit_code -ne 0 ]; then
      log_error "Start command failed immediately (exit code: $exit_code)"
      return 1
    fi
  fi

  log_info "Start command issued, waiting for addon to become ready..."

  # Wait for EMQX to actually start (up to 120 seconds)
  local max_attempts=24
  local attempt=0
  while [ $attempt -lt $max_attempts ]; do
    attempt=$((attempt + 1))
    current_state=$(ha addons info "$EMQX_SLUG" --raw-json 2> /dev/null \
      | jq -r '.data.state // "unknown"' 2> /dev/null)

    if [ "$current_state" = "started" ]; then
      # Kill the background process if it's still running
      kill $start_pid 2> /dev/null || true
      log_success "EMQX started successfully"
      return 0
    fi

    log_info "Waiting for EMQX to start... ($attempt/$max_attempts, state: $current_state)"
    sleep 5
  done

  # Kill the background process if it's still running
  kill $start_pid 2> /dev/null || true

  log_error "Failed to start EMQX (state: $current_state after ${max_attempts} attempts)"
  log_info "Check logs with: ha addons logs $EMQX_SLUG"
  return 1
}

# Install Cync Controller add-on
install_cync_lan() {
  log_info "Checking if Cync Controller add-on is already installed..."

  # Check if already installed
  local installed
  installed=$(ha addons info "$CYNC_SLUG" --raw-json 2> /dev/null \
    | jq -r '.data.version // null' 2> /dev/null)

  if [ "$installed" != "null" ] && [ "$installed" != "" ]; then
    log_info "Cync Controller already installed"
    return 0
  fi

  log_info "Installing Cync Controller add-on..."

  if ha addons install "$CYNC_SLUG" > /dev/null 2>&1; then
    log_success "Cync Controller installed successfully"
    return 0
  else
    log_error "Failed to install Cync Controller"
    return 1
  fi
}

# Configure Cync Controller add-on with credentials
configure_cync_lan() {
  # Check if we have Cync credentials
  if [ -z "$CYNC_USERNAME" ] || [ -z "$CYNC_PASSWORD" ]; then
    log_warn "Cync credentials not found in credentials file"
    log_info "Skipping configuration - configure manually via Home Assistant UI"
    log_info "Go to Settings > Add-ons > Cync Controller > Configuration"
    return 0
  fi

  log_info "Configuring Cync Controller with credentials from $CREDENTIALS_FILE..."

  # Cync Controller configuration with actual Cync credentials and EMQX connection
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
    "mqtt_user": "$MQTT_USER",
    "mqtt_pass": "$MQTT_PASS",
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
    }
  }
}
EOF
  )

  # Use curl for configuration since ha CLI doesn't support options
  local response
  response=$(timeout 30 docker exec hassio_cli curl -sf -w "\n%{http_code}" -X POST \
    -H "Authorization: Bearer ${SUPERVISOR_TOKEN}" \
    -H "Content-Type: application/json" \
    "http://supervisor/addons/$CYNC_SLUG/options" \
    -d "$config" 2>&1) || {
    log_warn "Cync Controller configuration timed out or failed"
    log_info "You may need to configure it manually via Home Assistant UI"
    return 0
  }

  local http_code
  http_code=$(echo "$response" | tail -n1)

  if [ "$http_code" = "200" ]; then
    log_success "Cync Controller configured successfully"
    log_info "Using Cync account: $CYNC_USERNAME"
  else
    log_warn "Cync Controller configuration returned HTTP $http_code"
    log_info "You may need to configure it manually via Home Assistant UI"
  fi
}

# Enable "Add to Sidebar" for Cync Controller add-on
enable_cync_sidebar() {
  log_info "Enabling 'Add to Sidebar' for Cync Controller..."

  local response
  response=$(timeout 30 docker exec hassio_cli curl -sf -w "\n%{http_code}" -X POST \
    -H "Authorization: Bearer ${SUPERVISOR_TOKEN}" \
    -H "Content-Type: application/json" \
    "http://supervisor/addons/$CYNC_SLUG/options" \
    -d '{"ingress_panel": true}' 2>&1) || {
    log_warn "Failed to enable sidebar for Cync Controller"
    return 0
  }

  local http_code
  http_code=$(echo "$response" | tail -n1)

  if [ "$http_code" = "200" ]; then
    log_success "Cync Controller sidebar enabled"
    return 0
  else
    log_warn "Cync Controller sidebar configuration returned HTTP $http_code"
    return 0
  fi
}

# Start Cync Controller add-on
start_cync_lan() {
  log_info "Starting Cync Controller add-on..."

  # Check current state
  local current_state
  current_state=$(ha addons info "$CYNC_SLUG" --raw-json 2> /dev/null \
    | jq -r '.data.state // "unknown"' 2> /dev/null)

  log_info "Current Cync Controller state: $current_state"

  if [ "$current_state" = "started" ]; then
    log_success "Cync Controller already running"
    return 0
  fi

  # Start the addon asynchronously (ha addons start can hang, so we poll instead)
  log_info "Issuing start command..."
  ha addons start "$CYNC_SLUG" > /dev/null 2>&1 &
  local start_pid=$!

  # Give the command a moment to process
  sleep 2

  # Check if the background process is still running or has failed immediately
  if ! kill -0 $start_pid 2> /dev/null; then
    # Process already exited - check if it succeeded
    wait $start_pid 2> /dev/null
    local exit_code=$?
    if [ $exit_code -ne 0 ]; then
      log_warn "Start command failed (exit code: $exit_code, addon may need manual configuration)"
      log_info "This is expected - configure the addon via Home Assistant UI and start it manually"
      return 0
    fi
  fi

  log_info "Start command issued, waiting for addon to become ready..."

  # Wait for Cync Controller to start (up to 60 seconds)
  local max_attempts=12
  local attempt=0
  while [ $attempt -lt $max_attempts ]; do
    attempt=$((attempt + 1))
    current_state=$(ha addons info "$CYNC_SLUG" --raw-json 2> /dev/null \
      | jq -r '.data.state // "unknown"' 2> /dev/null)

    if [ "$current_state" = "started" ]; then
      # Kill the background process if it's still running
      kill $start_pid 2> /dev/null || true
      log_success "Cync Controller started successfully"
      return 0
    fi

    log_info "Waiting for Cync Controller to start... ($attempt/$max_attempts, state: $current_state)"
    sleep 5
  done

  # Kill the background process if it's still running
  kill $start_pid 2> /dev/null || true

  log_warn "Failed to start Cync Controller (addon may need manual configuration)"
  log_info "This is expected - configure the addon via Home Assistant UI and start it manually"
  return 0
}

# Wait for MQTT broker to accept TCP connections and pick the active host
wait_for_mqtt_broker() {
  log_info "Waiting for MQTT broker to be reachable..."

  local hosts=("$MQTT_BROKER_HOST_DEFAULT" "$MQTT_BROKER_HOST_FALLBACK")
  local selected_host=""
  local host

  for host in "${hosts[@]}"; do
    if [ -z "$host" ]; then
      continue
    fi

    log_info "Checking MQTT broker at $host:$MQTT_BROKER_PORT..."

    local attempt=0
    local max_attempts=24
    local retry_delay=5

    while [ $attempt -lt $max_attempts ]; do
      attempt=$((attempt + 1))

      if docker exec hassio_cli sh -c "nc -z $host $MQTT_BROKER_PORT >/dev/null 2>&1"; then
        selected_host="$host"
        break
      fi

      log_info "MQTT broker not reachable yet (host: $host, attempt $attempt/$max_attempts)"
      sleep $retry_delay
    done

    if [ -n "$selected_host" ]; then
      break
    fi
  done

  if [ -z "$selected_host" ]; then
    log_warn "Could not reach MQTT broker on $MQTT_BROKER_HOST_DEFAULT or $MQTT_BROKER_HOST_FALLBACK"
    return 1
  fi

  MQTT_ACTIVE_HOST="$selected_host"
  log_success "MQTT broker reachable at $MQTT_ACTIVE_HOST:$MQTT_BROKER_PORT"
  return 0
}

# Build the user_input payload for the current MQTT config flow step
mqtt_build_user_input() {
  local step_json="$1"

  echo "$step_json" | jq -c \
    --arg broker "$MQTT_ACTIVE_HOST" \
    --arg port "$MQTT_BROKER_PORT" \
    --arg username "${MQTT_USERNAME:-}" \
    --arg password "${MQTT_PASSWORD:-}" \
    --arg client_id "cync-controller-setup" \
    'reduce (.data_schema // [])[] as $field ({};
      if $field.name == "broker" then . + {"broker": $broker}
      elif $field.name == "port" then . + {"port": ($port | tonumber)}
      elif $field.name == "username" then
        if ($username | length) > 0 then . + {"username": $username} else . end
      elif $field.name == "password" then
        if ($password | length) > 0 then . + {"password": $password} else . end
      elif $field.name == "client_id" then . + {"client_id": $client_id}
      elif $field.name == "next_step_id" then . + {"next_step_id": "broker"}
      elif $field.name == "discovery" then . + {"discovery": true}
      elif $field.name == "discovery_prefix" then . + {"discovery_prefix": "homeassistant"}
      elif $field.name == "protocol" then . + {"protocol": "3.1.1"}
      elif $field.name == "transport" then . + {"transport": "tcp"}
      elif $field.name == "tls" then . + {"tls": false}
      elif $field.name == "tls_insecure" then . + {"tls_insecure": false}
      else .
      end)'
}

# Execute the MQTT config flow via Home Assistant REST API
mqtt_run_config_flow() {
  MQTT_LAST_ABORT_REASON=""

  local auth_token="$LONG_LIVED_ACCESS_TOKEN"

  if [ -z "$auth_token" ]; then
    log_error "Missing long-lived access token; cannot configure MQTT integration"
    return 1
  fi

  local start_payload='{"handler":"mqtt","show_advanced_options":true}'
  local response

  if ! response=$(curl -sf -X POST "$HA_URL/api/config/config_entries/flow" \
    -H "Authorization: Bearer $auth_token" \
    -H "Content-Type: application/json" \
    -d "$start_payload" 2>&1); then
    log_error "Failed to start MQTT config flow via REST API"
    log_error "curl output: $response"
    return 1
  fi

  local step_json="$response"
  local step_type
  step_type=$(echo "$step_json" | jq -r '.type // empty' 2> /dev/null || echo "")

  if [ -z "$step_type" ]; then
    log_error "Unexpected response when starting MQTT config flow"
    echo "$step_json" | jq '.' 2> /dev/null || echo "$step_json"
    return 1
  fi

  if [ "$step_type" = "abort" ]; then
    MQTT_LAST_ABORT_REASON=$(echo "$step_json" | jq -r '.reason // empty' 2> /dev/null || echo "")

    if [ "$MQTT_LAST_ABORT_REASON" = "already_configured" ] || [ "$MQTT_LAST_ABORT_REASON" = "single_instance_allowed" ]; then
      log_success "MQTT integration already configured"
      return 0
    fi

    log_warn "MQTT config flow aborted (reason: ${MQTT_LAST_ABORT_REASON:-unknown})"
    return 1
  fi

  if [ "$step_type" = "create_entry" ]; then
    log_success "MQTT integration created during initial flow step"
    return 0
  fi

  if [ "$step_type" != "form" ] && [ "$step_type" != "menu" ]; then
    log_warn "Unexpected MQTT flow step type: $step_type"
    echo "$step_json" | jq '.' 2> /dev/null || echo "$step_json"
    return 1
  fi

  while true; do
    local flow_id
    flow_id=$(echo "$step_json" | jq -r '.flow_id // empty' 2> /dev/null || echo "")

    if [ -z "$flow_id" ]; then
      log_error "Missing flow_id in MQTT config flow response"
      echo "$step_json" | jq '.' 2> /dev/null || echo "$step_json"
      return 1
    fi

    local user_input
    user_input=$(mqtt_build_user_input "$step_json")

    if [ -z "$user_input" ]; then
      log_warn "Unable to build MQTT config user_input payload"
      echo "$step_json" | jq '.' 2> /dev/null || echo "$step_json"
      return 1
    fi

    local request_body
    if [ "$step_type" = "menu" ]; then
      # For menu steps, Home Assistant expects a top-level next_step_id
      request_body='{"next_step_id":"broker"}'
    else
      # For form steps, submit fields at the top level (not under user_input)
      request_body="$user_input"
    fi

    if [ "$step_type" = "menu" ]; then
      # Try top-level selector first
      if ! response=$(curl -sf -X POST "$HA_URL/api/config/config_entries/flow/$flow_id" \
        -H "Authorization: Bearer $auth_token" \
        -H "Content-Type: application/json" \
        -d '{"next_step_id":"broker"}' 2>&1); then
        # Fallback to user_input wrapper
        if ! response=$(curl -sf -X POST "$HA_URL/api/config/config_entries/flow/$flow_id" \
          -H "Authorization: Bearer $auth_token" \
          -H "Content-Type: application/json" \
          -d '{"user_input":{"next_step_id":"broker"}}' 2>&1); then
          log_error "Failed to submit MQTT config flow step (menu)"
          log_error "curl output: $response"
          return 1
        fi
      fi
    else
      if ! response=$(curl -sf -X POST "$HA_URL/api/config/config_entries/flow/$flow_id" \
        -H "Authorization: Bearer $auth_token" \
        -H "Content-Type: application/json" \
        -d "$request_body" 2>&1); then
        log_error "Failed to submit MQTT config flow step"
        log_error "curl output: $response"
        return 1
      fi
    fi

    step_json="$response"
    step_type=$(echo "$step_json" | jq -r '.type // empty' 2> /dev/null || echo "")

    if [ "$step_type" = "create_entry" ]; then
      log_success "MQTT integration configured successfully"
      return 0
    fi

    if [ "$step_type" = "abort" ]; then
      MQTT_LAST_ABORT_REASON=$(echo "$step_json" | jq -r '.reason // empty' 2> /dev/null || echo "")

      log_warn "MQTT config flow aborted during submission (reason: ${MQTT_LAST_ABORT_REASON:-unknown})"
      return 1
    fi

    if [ "$step_type" != "form" ] && [ "$step_type" != "menu" ]; then
      log_warn "Unexpected MQTT flow step type encountered: $step_type"
      echo "$step_json" | jq '.' 2> /dev/null || echo "$step_json"
      return 1
    fi
  done
}

# Publish a test MQTT message via Home Assistant service call to verify integration
mqtt_verify_publish() {
  local auth_token="$LONG_LIVED_ACCESS_TOKEN"

  if [ -z "$auth_token" ]; then
    log_warn "Skipping MQTT publish verification (missing long-lived access token)"
    return
  fi

  local payload='{ "topic": "cync_controller_addon/test", "payload": "ok", "qos": 0, "retain": false }'
  local tmp_file
  tmp_file=$(mktemp)

  local http_code
  http_code=$(curl -s -o "$tmp_file" -w "%{http_code}" -X POST "$HA_URL/api/services/mqtt/publish" \
    -H "Authorization: Bearer $auth_token" \
    -H "Content-Type: application/json" \
    -d "$payload")

  if [ "$http_code" = "200" ]; then
    log_success "Verified MQTT integration by publishing test message"
  elif [ "$http_code" = "404" ]; then
    log_warn "MQTT publish service not available yet (HTTP 404)"
    cat "$tmp_file" 2> /dev/null || true
  else
    log_warn "Unexpected response from MQTT publish service (HTTP $http_code)"
    cat "$tmp_file" 2> /dev/null || true
  fi

  rm -f "$tmp_file"
}

# High-level orchestration for configuring the MQTT integration
setup_mqtt_integration() {
  log_info "Setting up Home Assistant MQTT integration via REST API..."

  if [ -z "${MQTT_USER:-}" ] || [ -z "${MQTT_PASS:-}" ]; then
    log_warn "MQTT credentials missing from $CREDENTIALS_FILE (MQTT_USER/MQTT_PASS); skipping MQTT integration setup"
    return 0
  fi

  if ! wait_for_mqtt_broker; then
    log_warn "Skipping MQTT integration setup because broker is unreachable"
    return 0
  fi

  MQTT_USERNAME="$MQTT_USER"
  MQTT_PASSWORD="$MQTT_PASS"
  MQTT_ACTIVE_HOST="${MQTT_ACTIVE_HOST:-$MQTT_BROKER_HOST_DEFAULT}"

  if ! command -v jq > /dev/null 2>&1 && ! docker exec hassio_cli sh -c "command -v jq >/dev/null 2>&1"; then
    log_warn "jq not available; skipping automated MQTT integration setup"
    return 0
  fi

  local attempt=0
  local max_attempts=2

  while [ $attempt -lt $max_attempts ]; do
    attempt=$((attempt + 1))

    if mqtt_run_config_flow; then
      mqtt_verify_publish
      return 0
    fi

    if [ "$MQTT_LAST_ABORT_REASON" = "cannot_connect" ] && [ $attempt -lt $max_attempts ]; then
      log_warn "MQTT config flow reported cannot_connect; retrying in 5 seconds..."
      sleep 5
      continue
    fi

    break
  done

  log_warn "MQTT integration setup did not complete successfully; manual intervention may be required"
  return 0
}

# Verify all services are running
verify_setup() {
  log_info "Verifying setup..."

  local all_good=true

  # Check EMQX status
  local emqx_state
  emqx_state=$(ha addons info "$EMQX_SLUG" --raw-json 2> /dev/null \
    | jq -r '.data.state // "unknown"' 2> /dev/null)

  if [ "$emqx_state" = "started" ]; then
    log_success "EMQX: Running"
  else
    log_error "EMQX: Not running (state: $emqx_state)"
    all_good=false
  fi

  # Check Cync Controller status
  local cync_state
  cync_state=$(ha addons info "$CYNC_SLUG" --raw-json 2> /dev/null \
    | jq -r '.data.state // "unknown"' 2> /dev/null)

  if [ "$cync_state" = "started" ]; then
    log_success "Cync Controller: Running"
  else
    log_warn "Cync Controller: Not running (state: $cync_state)"
    log_info "Configure via Home Assistant UI and start manually"
  fi

  if [ "$all_good" = true ]; then
    log_success "Setup completed successfully"
    log_info "EMQX is running, Cync Controller needs manual configuration"
    return 0
  else
    log_warn "Setup completed with warnings"
    log_info "Please check the services status and configure as needed"
    return 0
  fi
}

# Main execution
main() {
  echo "========================================="
  echo "$LP Automated Fresh HA Setup"
  echo "========================================="

  # Step 1: Load credentials
  load_credentials

  # Step 2: Wait for HA to be ready
  wait_for_ha

  # Step 3: Handle onboarding if needed
  if check_onboarding_status; then
    log_info "Home Assistant needs onboarding, creating first user..."

    local auth_token
    auth_token=$(create_first_user)

    if [ -z "$auth_token" ]; then
      log_error "Failed to create first user during onboarding"
      exit 1
    fi

    log_success "First user created successfully"
    complete_onboarding
    log_info "Waiting for Home Assistant to initialize after onboarding..."
    sleep 10
  else
    log_info "Onboarding already completed, proceeding with token creation"
  fi

  # Step 4: Create fresh long-lived access token using WebSocket script
  log_info "Creating fresh long-lived access token using WebSocket script..."

  # Use the WebSocket token creation script that works with just username/password
  local token_script="$REPO_ROOT/scripts/create-token-websocket.js"

  if [ -f "$token_script" ]; then
    log_info "Running WebSocket token creation script..."

    # Run the token creation script with proper environment variables
    local token_output
    token_output=$(HA_URL="$HA_URL" HASS_USERNAME="$HASS_USERNAME" HASS_PASSWORD="$HASS_PASSWORD" node "$token_script" 2>&1) || {
      log_error "Failed to create token using WebSocket script"
      log_error "Output: $token_output"
      exit 1
    }

    # Extract the token from the output (look for JWT pattern)
    local new_token
    new_token=$(echo "$token_output" | grep -oE "eyJ[A-Za-z0-9_-]*\.[A-Za-z0-9_-]*\.[A-Za-z0-9_-]*" | head -n1)

    if [ -n "$new_token" ]; then
      log_success "Successfully created fresh long-lived token using WebSocket script"

      LONG_LIVED_ACCESS_TOKEN="$new_token"

      # Save the long-lived access token
      if grep -q "LONG_LIVED_ACCESS_TOKEN=" "$CREDENTIALS_FILE" 2> /dev/null; then
        sed -i "s|^LONG_LIVED_ACCESS_TOKEN=.*|LONG_LIVED_ACCESS_TOKEN=$new_token|" "$CREDENTIALS_FILE"
      else
        echo "LONG_LIVED_ACCESS_TOKEN=$new_token" >> "$CREDENTIALS_FILE"
      fi

      log_success "Updated credentials file with fresh long-lived access token"
    else
      log_error "Failed to extract token from WebSocket script output"
      log_error "Output: $token_output"
      exit 1
    fi
  else
    log_error "WebSocket token creation script not found: $token_script"
    exit 1
  fi

  # Step 5: Get supervisor token for add-on management
  get_supervisor_token
  wait_for_supervisor

  # Step 6: Add EMQX repository
  add_emqx_repository

  # Step 7: Install and configure EMQX
  install_emqx
  configure_emqx
  enable_emqx_sidebar
  start_emqx
  setup_mqtt_integration

  # Step 8: Install and configure Cync Controller
  install_cync_lan
  configure_cync_lan
  enable_cync_sidebar
  start_cync_lan

  # Step 9: Verify everything is running
  verify_setup

  echo "========================================="
  log_success "Setup completed successfully!"
  echo "========================================="
  echo ""
  echo "Next steps:"
  echo "  1. Log in to Home Assistant at $HA_URL"
  echo "     Username: $HASS_USERNAME"
  echo "     Password: (from $CREDENTIALS_FILE)"
  echo ""
  echo "  2. Access EMQX WebUI via Add-ons page to test MQTT"
  echo ""
  echo "  3. Update Cync Controller configuration with your real Cync credentials:"
  echo "     - account_username: Your Cync email"
  echo "     - account_password: Your Cync password"
  echo ""
  echo "  4. Restart Cync Controller add-on after updating credentials"
  echo ""
}

# Run main function
main "$@"
