#!/usr/bin/env bash
# Automated setup script for fresh Home Assistant installation
# Creates user, installs EMQX and Cync Controller add-ons with configuration
set -e

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
    auth_token=$(echo "$body" | jq -r '.access_token // empty' 2> /dev/null)
    if [ -n "$auth_token" ]; then
      log_info "Auth token received from user creation"
      echo "$auth_token"
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

  local response
  response=$(curl -sf -w "\n%{http_code}" -X POST \
    "$HA_URL/api/onboarding/core_config" \
    -H "Content-Type: application/json" \
    -d "{}" 2>&1)

  local http_code
  http_code=$(echo "$response" | tail -n1)

  if [ "$http_code" = "200" ] || [ "$http_code" = "201" ]; then
    log_success "Onboarding completed"
    return 0
  else
    log_warn "Onboarding completion returned HTTP $http_code (may already be complete)"
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
    healthy=$(curl -sf -H "Authorization: Bearer ${SUPERVISOR_TOKEN}" \
      "http://supervisor/supervisor/info" 2> /dev/null \
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
  repos=$(curl -sf -H "Authorization: Bearer ${SUPERVISOR_TOKEN}" \
    "http://supervisor/store/repositories" 2> /dev/null \
    | jq -r '.data.repositories[]' 2> /dev/null || echo "")

  if echo "$repos" | grep -q "$HASSIO_ADDONS_REPO"; then
    log_info "Repository already added, skipping"
    return 0
  fi

  log_info "Adding hassio-addons repository..."

  local response
  response=$(curl -sf -w "\n%{http_code}" -X POST \
    -H "Authorization: Bearer ${SUPERVISOR_TOKEN}" \
    -H "Content-Type: application/json" \
    "http://supervisor/store/repositories" \
    -d "{\"repository\": \"$HASSIO_ADDONS_REPO\"}" 2>&1)

  local http_code
  http_code=$(echo "$response" | tail -n1)
  local body
  body=$(echo "$response" | sed '$d')

  if [ "$http_code" = "200" ]; then
    log_success "Repository added successfully"

    # Reload store to refresh add-on list
    log_info "Reloading add-on store..."
    curl -sf -X POST \
      -H "Authorization: Bearer ${SUPERVISOR_TOKEN}" \
      "http://supervisor/store/reload" > /dev/null 2>&1

    # Wait for store to refresh
    sleep 5

    log_success "Add-on store reloaded"
    return 0
  else
    log_error "Failed to add repository (HTTP $http_code)"
    echo "$body" | jq '.' 2> /dev/null || echo "$body"
    return 1
  fi
}

# Install EMQX add-on
install_emqx() {
  log_info "Checking if EMQX add-on is already installed..."

  # Check if already installed
  local state
  state=$(curl -sf -H "Authorization: Bearer ${SUPERVISOR_TOKEN}" \
    "http://supervisor/addons/$EMQX_SLUG/info" 2> /dev/null \
    | jq -r '.data.state // "not_installed"' 2> /dev/null)

  if [ "$state" != "not_installed" ] && [ "$state" != "null" ]; then
    log_info "EMQX already installed (state: $state)"
    return 0
  fi

  log_info "Installing EMQX add-on..."

  local response
  response=$(curl -sf -w "\n%{http_code}" -X POST \
    -H "Authorization: Bearer ${SUPERVISOR_TOKEN}" \
    "http://supervisor/addons/$EMQX_SLUG/install" 2>&1)

  local http_code
  http_code=$(echo "$response" | tail -n1)

  if [ "$http_code" = "200" ]; then
    log_info "EMQX installation started, waiting for completion..."

    # Wait for installation to complete
    local retry_count=0
    local max_retries=60

    while [ $retry_count -lt $max_retries ]; do
      state=$(curl -sf -H "Authorization: Bearer ${SUPERVISOR_TOKEN}" \
        "http://supervisor/addons/$EMQX_SLUG/info" 2> /dev/null \
        | jq -r '.data.state // "unknown"' 2> /dev/null)

      if [ "$state" = "stopped" ] || [ "$state" = "started" ]; then
        log_success "EMQX installed successfully"
        return 0
      fi

      retry_count=$((retry_count + 1))
      log_info "Installation in progress... ($retry_count/$max_retries)"
      sleep 5
    done

    log_error "EMQX installation timed out"
    return 1
  else
    log_error "Failed to install EMQX (HTTP $http_code)"
    echo "$response" | sed '$d' | jq '.' 2> /dev/null || echo "$response" | sed '$d'
    return 1
  fi
}

# Configure EMQX add-on with credentials
configure_emqx() {
  log_info "Configuring EMQX with credentials..."

  # EMQX configuration with MQTT credentials
  local config
  config=$(
    cat << EOF
{
    "options": {
        "log_level": "info"
    }
}
EOF
  )

  local response
  response=$(curl -sf -w "\n%{http_code}" -X POST \
    -H "Authorization: Bearer ${SUPERVISOR_TOKEN}" \
    -H "Content-Type: application/json" \
    "http://supervisor/addons/$EMQX_SLUG/options" \
    -d "$config" 2>&1)

  local http_code
  http_code=$(echo "$response" | tail -n1)

  if [ "$http_code" = "200" ]; then
    log_success "EMQX configured successfully"
    return 0
  else
    log_warn "EMQX configuration returned HTTP $http_code (may use defaults)"
    return 0
  fi
}

# Start EMQX add-on
start_emqx() {
  log_info "Starting EMQX add-on..."

  local response
  response=$(curl -sf -w "\n%{http_code}" -X POST \
    -H "Authorization: Bearer ${SUPERVISOR_TOKEN}" \
    "http://supervisor/addons/$EMQX_SLUG/start" 2>&1)

  local http_code
  http_code=$(echo "$response" | tail -n1)

  if [ "$http_code" = "200" ]; then
    log_info "EMQX start initiated, waiting for it to be running..."

    # Wait for EMQX to be fully started
    local retry_count=0
    local max_retries=30

    while [ $retry_count -lt $max_retries ]; do
      local state
      state=$(curl -sf -H "Authorization: Bearer ${SUPERVISOR_TOKEN}" \
        "http://supervisor/addons/$EMQX_SLUG/info" 2> /dev/null \
        | jq -r '.data.state // "unknown"' 2> /dev/null)

      if [ "$state" = "started" ]; then
        log_success "EMQX is running"
        return 0
      fi

      retry_count=$((retry_count + 1))
      log_info "Waiting for EMQX to start... ($retry_count/$max_retries)"
      sleep 5
    done

    log_error "EMQX failed to start within timeout"
    return 1
  else
    log_error "Failed to start EMQX (HTTP $http_code)"
    echo "$response" | sed '$d' | jq '.' 2> /dev/null || echo "$response" | sed '$d'
    return 1
  fi
}

# Install Cync Controller add-on
install_cync_lan() {
  log_info "Checking if Cync Controller add-on is already installed..."

  # Check if already installed
  local state
  state=$(curl -sf -H "Authorization: Bearer ${SUPERVISOR_TOKEN}" \
    "http://supervisor/addons/$CYNC_SLUG/info" 2> /dev/null \
    | jq -r '.data.state // "not_installed"' 2> /dev/null)

  if [ "$state" != "not_installed" ] && [ "$state" != "null" ]; then
    log_info "Cync Controller already installed (state: $state)"
    return 0
  fi

  log_info "Installing Cync Controller add-on..."

  local response
  response=$(curl -sf -w "\n%{http_code}" -X POST \
    -H "Authorization: Bearer ${SUPERVISOR_TOKEN}" \
    "http://supervisor/addons/$CYNC_SLUG/install" 2>&1)

  local http_code
  http_code=$(echo "$response" | tail -n1)

  if [ "$http_code" = "200" ]; then
    log_info "Cync Controller installation started, waiting for completion..."

    # Wait for installation to complete
    local retry_count=0
    local max_retries=60

    while [ $retry_count -lt $max_retries ]; do
      state=$(curl -sf -H "Authorization: Bearer ${SUPERVISOR_TOKEN}" \
        "http://supervisor/addons/$CYNC_SLUG/info" 2> /dev/null \
        | jq -r '.data.state // "unknown"' 2> /dev/null)

      if [ "$state" = "stopped" ] || [ "$state" = "started" ]; then
        log_success "Cync Controller installed successfully"
        return 0
      fi

      retry_count=$((retry_count + 1))
      log_info "Installation in progress... ($retry_count/$max_retries)"
      sleep 5
    done

    log_error "Cync Controller installation timed out"
    return 1
  else
    log_error "Failed to install Cync Controller (HTTP $http_code)"
    echo "$response" | sed '$d' | jq '.' 2> /dev/null || echo "$response" | sed '$d'
    return 1
  fi
}

# Configure Cync Controller add-on with test credentials
configure_cync_lan() {
  log_info "Configuring Cync Controller with test credentials..."

  # Cync Controller configuration with test Cync credentials and EMQX connection
  local config
  config=$(
    cat << EOF
{
    "options": {
        "account_username": "test@example.com",
        "account_password": "testpassword123",
        "debug_log_level": true,
        "mqtt_host": "localhost",
        "mqtt_port": 1883,
        "mqtt_user": "$HASS_USERNAME",
        "mqtt_pass": "$HASS_PASSWORD",
        "mqtt_topic": "cync_lan_addon",
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

  local response
  response=$(curl -sf -w "\n%{http_code}" -X POST \
    -H "Authorization: Bearer ${SUPERVISOR_TOKEN}" \
    -H "Content-Type: application/json" \
    "http://supervisor/addons/$CYNC_SLUG/options" \
    -d "$config" 2>&1)

  local http_code
  http_code=$(echo "$response" | tail -n1)

  if [ "$http_code" = "200" ]; then
    log_success "Cync Controller configured successfully"
    log_info "Note: Cync account credentials are test values - update manually with real credentials"
    return 0
  else
    log_error "Failed to configure Cync Controller (HTTP $http_code)"
    echo "$response" | sed '$d' | jq '.' 2> /dev/null || echo "$response" | sed '$d'
    return 1
  fi
}

# Start Cync Controller add-on
start_cync_lan() {
  log_info "Starting Cync Controller add-on..."

  local response
  response=$(curl -sf -w "\n%{http_code}" -X POST \
    -H "Authorization: Bearer ${SUPERVISOR_TOKEN}" \
    "http://supervisor/addons/$CYNC_SLUG/start" 2>&1)

  local http_code
  http_code=$(echo "$response" | tail -n1)

  if [ "$http_code" = "200" ]; then
    log_info "Cync Controller start initiated, waiting for it to be running..."

    # Wait for Cync Controller to be fully started
    local retry_count=0
    local max_retries=30

    while [ $retry_count -lt $max_retries ]; do
      local state
      state=$(curl -sf -H "Authorization: Bearer ${SUPERVISOR_TOKEN}" \
        "http://supervisor/addons/$CYNC_SLUG/info" 2> /dev/null \
        | jq -r '.data.state // "unknown"' 2> /dev/null)

      if [ "$state" = "started" ]; then
        log_success "Cync Controller is running"
        return 0
      fi

      retry_count=$((retry_count + 1))
      log_info "Waiting for Cync Controller to start... ($retry_count/$max_retries)"
      sleep 5
    done

    log_error "Cync Controller failed to start within timeout"
    return 1
  else
    log_error "Failed to start Cync Controller (HTTP $http_code)"
    echo "$response" | sed '$d' | jq '.' 2> /dev/null || echo "$response" | sed '$d'
    return 1
  fi
}

# Verify all services are running
verify_setup() {
  log_info "Verifying setup..."

  local all_good=true

  # Check EMQX status
  local emqx_state
  emqx_state=$(curl -sf -H "Authorization: Bearer ${SUPERVISOR_TOKEN}" \
    "http://supervisor/addons/$EMQX_SLUG/info" 2> /dev/null \
    | jq -r '.data.state // "unknown"' 2> /dev/null)

  if [ "$emqx_state" = "started" ]; then
    log_success "EMQX: Running"
  else
    log_error "EMQX: Not running (state: $emqx_state)"
    all_good=false
  fi

  # Check Cync Controller status
  local cync_state
  cync_state=$(curl -sf -H "Authorization: Bearer ${SUPERVISOR_TOKEN}" \
    "http://supervisor/addons/$CYNC_SLUG/info" 2> /dev/null \
    | jq -r '.data.state // "unknown"' 2> /dev/null)

  if [ "$cync_state" = "started" ]; then
    log_success "Cync Controller: Running"
  else
    log_error "Cync Controller: Not running (state: $cync_state)"
    all_good=false
  fi

  if [ "$all_good" = true ]; then
    log_success "All services verified successfully"
    return 0
  else
    log_error "Some services failed verification"
    return 1
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

  # Step 3: Check if onboarding is needed and perform it
  if check_onboarding_status; then
    create_first_user
    complete_onboarding
    log_info "Waiting for Home Assistant to initialize after onboarding..."
    sleep 10
  else
    log_info "Skipping onboarding (already completed)"
  fi

  # Step 4: Get supervisor token for add-on management
  get_supervisor_token
  wait_for_supervisor

  # Step 5: Add EMQX repository
  add_emqx_repository

  # Step 6: Install and configure EMQX
  install_emqx
  configure_emqx
  start_emqx

  # Step 7: Install and configure Cync Controller
  install_cync_lan
  configure_cync_lan
  start_cync_lan

  # Step 8: Verify everything is running
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
