#!/usr/bin/env bash
# Automated setup script for fresh Home Assistant installation
# Creates user, installs EMQX and Cync Controller add-ons with configuration
set -Eeuo pipefail
IFS=$'\n\t'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091  # Source path is dynamic via $SCRIPT_DIR
source "$SCRIPT_DIR/shell-common/common-output.sh"

# shellcheck disable=SC2034  # LP used by common-output.sh log functions
LP="[$(basename "$0")]"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Default values
# Auto-detect HA IP from ha core info if not specified
HA_IP=$(ha core info 2> /dev/null | grep 'ip_address:' | awk '{print $2}' || echo "")
HA_URL="${HA_URL:-http://${HA_IP:-homeassistant.local}:8123}"
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

# Error handling function
on_error() {
  local exit_code=$?
  log_error "Script failed at line $1 with exit code $exit_code"
  log_error "Failed command: $BASH_COMMAND"
  log_error "Stack trace:"
  caller >&2
  trap - EXIT ERR
  exit $exit_code
}

# Set up error traps
trap 'on_error $LINENO' ERR
trap 'if [ $? -ne 0 ]; then log_error "Script exited with code $?"; fi' EXIT

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

  if [ -z "${HASS_USERNAME:-}" ] || [ -z "${HASS_PASSWORD:-}" ]; then
    log_error "HASS_USERNAME or HASS_PASSWORD not found in credentials file"
    exit 1
  fi

  log_success "Credentials loaded (username: $HASS_USERNAME)"
  if [ -n "${CYNC_USERNAME:-}" ]; then
    log_info "Cync credentials found (username: $CYNC_USERNAME)"
  fi
  if [ -n "${MQTT_USER:-}" ]; then
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
    # Check if onboarding endpoint responds (for fresh HA - doesn't require auth)
    if curl -sf "$HA_URL/api/onboarding" > /dev/null 2>&1; then
      log_success "Home Assistant API is responsive (onboarding available)"
      return 0
    fi

    # Fallback check for already-onboarded HA: check /api/ endpoint
    # HTTP 401 (Unauthorized) = HA is running but requires auth (onboarded)
    # HTTP 200 (OK) = HA is running and accessible
    local api_check
    api_check=$(curl -s -o /dev/null -w "%{http_code}" "$HA_URL/api/" 2>&1) || true
    if [ "$api_check" = "401" ] || [ "$api_check" = "200" ]; then
      log_success "Home Assistant API is responsive (already onboarded)"
      return 0
    fi

    retry_count=$((retry_count + 1))
    log_info "Waiting for HA API... ($retry_count/$max_retries, sleeping ${retry_delay}s)"
    sleep $retry_delay
  done

  log_error "Home Assistant API not responsive after $max_retries attempts"
  exit 1
}

# Wait for Home Assistant Core service to be ready (not just API responding)
wait_for_ha_core_ready() {
  log_info "Checking Home Assistant Core service readiness..."

  local retry_count=0
  local max_retries=30
  local retry_delay=5

  while [ $retry_count -lt $max_retries ]; do
    # Check if Core service is running and has a version (indicates it's initialized)
    local core_version
    core_version=$(ha core info --raw-json 2> /dev/null | jq -r '.data.version // empty' 2> /dev/null || echo "")

    # Reject "landingpage" version as it indicates HA is not fully initialized
    if [ -n "$core_version" ] && [ "$core_version" != "null" ] && [ "$core_version" != "" ] && [ "$core_version" != "landingpage" ]; then
      log_success "Home Assistant Core is ready (version: $core_version)"
      return 0
    elif [ "$core_version" = "landingpage" ]; then
      log_info "HA Core is still in landingpage state (initializing)..."
    fi

    retry_count=$((retry_count + 1))
    log_info "Waiting for HA Core service... ($retry_count/$max_retries, sleeping ${retry_delay}s)"
    sleep $retry_delay
  done

  log_warn "Home Assistant Core service not fully ready after $max_retries attempts"
  log_info "Continuing anyway - Core may initialize during onboarding"
  return 0 # Don't fail, just warn - Core may become ready during onboarding
}

# Wait for Home Assistant HTTP API to be ready for Python requests
wait_for_ha_api_ready() {
  log_info "Verifying Home Assistant HTTP API connectivity..."

  local retry_count=0
  local max_retries=20
  local retry_delay=3

  while [ $retry_count -lt $max_retries ]; do
    # Test actual HTTP connectivity using Python requests (same library as onboarding script)
    if python3 -c "import requests; requests.get('$HA_URL/api/', timeout=5)" 2> /dev/null; then
      log_success "Home Assistant HTTP API is ready for connections"
      return 0
    fi

    retry_count=$((retry_count + 1))
    log_info "Waiting for HA HTTP API connectivity... ($retry_count/$max_retries, sleeping ${retry_delay}s)"
    sleep $retry_delay
  done

  log_error "Home Assistant HTTP API not ready after $max_retries attempts"
  exit 1
}

# Check if onboarding is needed (no users exist)
check_onboarding_status() {
  log_info "Checking onboarding status..."

  # Try to access onboarding endpoint and capture HTTP status code
  # Use -f flag to fail on errors, but capture status code separately
  local http_code
  local response
  http_code=$(curl -s -o /dev/null -w "%{http_code}" "$HA_URL/api/onboarding" 2> /dev/null || echo "000")

  # Onboarding API endpoint returns 404 in two scenarios:
  #   1) Fresh install - no owner user created yet (needs onboarding)
  #   2) Already complete - endpoint removed after owner creation (skip)
  # Delegate to Python automation to disambiguate via idempotent user creation attempt
  if [ "$http_code" = "404" ]; then
    log_info "Onboarding API returns 404 (no owner user OR already complete)"
    log_info "Delegating detection to onboarding automation (will try user creation)"
    return 0 # Let Python script disambiguate via user creation attempt
  fi

  # If not 404, try to get the response body (will work for 200 or other codes)
  response=$(curl -sf "$HA_URL/api/onboarding" 2> /dev/null || echo "")

  if [ -z "$response" ]; then
    log_info "Onboarding API returned HTTP $http_code - attempting onboarding"
    return 0
  fi

  # Check if user step is done
  local user_done
  user_done=$(echo "$response" | jq -r '.[] | select(.step == "user") | .done' 2> /dev/null || echo "")

  # Check if there are any incomplete steps
  local incomplete_steps
  incomplete_steps=$(echo "$response" | jq -r '.[] | select(.done == false) | .step' 2> /dev/null || echo "")

  if [ "$user_done" = "true" ]; then
    if [ -z "$incomplete_steps" ]; then
      log_info "User already created and all onboarding steps completed"
      return 1
    else
      log_info "User already created, but onboarding incomplete (remaining steps: $(echo "$incomplete_steps" | tr '\n' ',' | sed 's/,$//'))"
      return 0 # Return true to indicate onboarding is needed
    fi
  fi

  log_info "Home Assistant needs onboarding"
  return 0
}

# Create the first user via onboarding API
# Run onboarding automation using Python script
# This replaces the manual user creation and onboarding step completion
# Returns 0 on success, 1 on failure
# Outputs the auth token if successful
run_onboarding_automation() {
  local onboarding_script="$REPO_ROOT/scripts/automate_onboarding.py"

  if [ ! -f "$onboarding_script" ]; then
    log_error "Onboarding automation script not found: $onboarding_script"
    return 1
  fi

  log_info "Running onboarding automation script..."
  log_info "This will create user (if needed) and complete all onboarding steps..."

  # Run the Python script with proper environment variables
  # Also log to file for persistence
  local log_file="/tmp/onboarding-automation.log"
  local script_output
  script_output=$(HA_URL="$HA_URL" \
    HASS_USERNAME="$HASS_USERNAME" \
    HASS_PASSWORD="$HASS_PASSWORD" \
    python3 "$onboarding_script" 2>&1 | tee "$log_file")
  local script_exit_code=$?

  # Check for restart indicators in output (even if script succeeded)
  local needs_restart=false
  if echo "$script_output" | grep -qiE "restart needed|restart_code.*2|consider restarting|💡.*restart"; then
    needs_restart=true
    log_warn "Onboarding script indicates HA Core restart may be needed"
  fi

  if [ $script_exit_code -eq 0 ]; then
    log_success "Onboarding automation completed successfully"

    # Extract token from credentials file (prefer LONG_LIVED_ACCESS_TOKEN, fallback to ONBOARDING_TOKEN)
    local auth_token=""
    if [ -f "$CREDENTIALS_FILE" ]; then
      # First, try to get LONG_LIVED_ACCESS_TOKEN (preferred - long-lived)
      auth_token=$(grep "^LONG_LIVED_ACCESS_TOKEN=" "$CREDENTIALS_FILE" | cut -d'=' -f2 | tr -d '"' || echo "")

      # If no long-lived token, try ONBOARDING_TOKEN (short-lived, but usable)
      if [ -z "$auth_token" ]; then
        local onboarding_token
        onboarding_token=$(grep "^ONBOARDING_TOKEN=" "$CREDENTIALS_FILE" | cut -d'=' -f2 | tr -d '"' || echo "")
        if [ -n "$onboarding_token" ]; then
          log_info "Found ONBOARDING_TOKEN, creating long-lived token..."
          # Try to create long-lived token from onboarding token
          local token_script="$REPO_ROOT/scripts/create-token-from-existing.js"
          if [ -f "$token_script" ]; then
            local token_output
            token_output=$(HA_URL="$HA_URL" EXISTING_TOKEN="$onboarding_token" ONBOARDING_TOKEN="$onboarding_token" node "$token_script" 2>&1) || {
              log_warn "Failed to create long-lived token from onboarding token"
              log_warn "Will use onboarding token (may be short-lived)"
              auth_token="$onboarding_token"
            }

            # Extract the long-lived token from output
            local new_token
            new_token=$(echo "$token_output" | grep -oE "eyJ[A-Za-z0-9_-]*\.[A-Za-z0-9_-]*\.[A-Za-z0-9_-]*" | head -n1)
            if [ -n "$new_token" ]; then
              log_success "Successfully created long-lived token from onboarding token"
              auth_token="$new_token"
              # Save the long-lived token to credentials file
              if grep -q "LONG_LIVED_ACCESS_TOKEN=" "$CREDENTIALS_FILE" 2> /dev/null; then
                sed -i "s|^LONG_LIVED_ACCESS_TOKEN=.*|LONG_LIVED_ACCESS_TOKEN=$new_token|" "$CREDENTIALS_FILE"
              else
                echo "LONG_LIVED_ACCESS_TOKEN=$new_token" >> "$CREDENTIALS_FILE"
              fi
            else
              log_warn "Failed to extract long-lived token, using onboarding token"
              auth_token="$onboarding_token"
            fi
          else
            log_warn "Token bootstrap script not found, using onboarding token"
            auth_token="$onboarding_token"
          fi
        fi
      fi
    fi

    # Check if restart is needed (but script completed)
    if [ "$needs_restart" = "true" ]; then
      log_info "Script completed but restart recommended - returning restart code"
      if [ -n "$auth_token" ]; then
        log_info "Token extracted from credentials file"
        echo "$auth_token"
        return 2 # Return restart code
      fi
      return 2 # Return restart code even without token
    fi

    # Return token if we found one
    if [ -n "$auth_token" ]; then
      log_info "Token extracted from credentials file"
      echo "$auth_token"
      return 0
    fi

    # Try to extract token from script output as fallback
    auth_token=$(echo "$script_output" | grep -oE "eyJ[A-Za-z0-9_-]*\.[A-Za-z0-9_-]*\.[A-Za-z0-9_-]*" | head -n1)
    if [ -n "$auth_token" ]; then
      log_info "Token extracted from script output"
      echo "$auth_token"
      return 0
    fi

    log_warn "Onboarding completed but could not extract token"
    log_warn "You may need to create a token manually"
    return 0 # Still success, token can be created separately
  else
    log_error "Onboarding automation script failed with exit code $script_exit_code"
    log_error "Script output (full log: $log_file):"
    echo "$script_output" | while IFS= read -r line; do
      log_error "  $line"
    done

    # If script failed AND restart is needed, return restart code
    if [ "$needs_restart" = "true" ]; then
      log_warn "Script failed but restart may help - returning restart code"
      return 2
    fi

    return 1
  fi
}

# Legacy function kept for backwards compatibility
# Deprecated: Use run_onboarding_automation() instead
create_first_user() {
  log_info "Using new onboarding automation instead of legacy create_first_user..."
  run_onboarding_automation
}

# Discover available onboarding steps and their status
discover_onboarding_steps() {
  local auth_token="$1"
  local log_output="${2:-true}"

  if [ -z "$auth_token" ]; then
    if [ "$log_output" = "true" ]; then
      log_error "Missing auth token for onboarding discovery"
    fi
    return 1
  fi

  if [ "$log_output" = "true" ]; then
    log_info "Discovering available onboarding steps..."
  fi

  # Check HTTP status code first to handle 404 gracefully
  local http_code
  http_code=$(curl -s -o /dev/null -w "%{http_code}" -X GET \
    "$HA_URL/api/onboarding" \
    -H "Authorization: Bearer $auth_token" \
    -H "Content-Type: application/json" 2> /dev/null || echo "000")

  # 404 here means onboarding complete - endpoint removed after owner user created
  # (This function is only called AFTER user creation has already been attempted)
  if [ "$http_code" = "404" ]; then
    if [ "$log_output" = "true" ]; then
      log_info "Onboarding API returned HTTP 404 - onboarding complete"
    fi
    # Return 0 (success) with empty output - no incomplete steps
    return 0
  fi

  # If we get 401, token may be invalid/expired - return error
  # Don't try to get response body with curl -sf as it will fail on 401
  if [ "$http_code" = "401" ]; then
    if [ "$log_output" = "true" ]; then
      log_warn "Onboarding API returned HTTP 401 - token may be invalid or expired"
      log_warn "Cannot check onboarding status with invalid token"
    fi
    return 1
  fi

  # Get response body (should be 200 at this point)
  # Use curl -s without -f to get response even if HTTP error (we already checked status)
  local response
  response=$(curl -s -X GET \
    "$HA_URL/api/onboarding" \
    -H "Authorization: Bearer $auth_token" \
    -H "Content-Type: application/json" 2>&1)

  # Check if we got a valid response (should be JSON array)
  if [ -z "$response" ] || [ "$response" = "null" ]; then
    if [ "$log_output" = "true" ]; then
      log_warn "Failed to retrieve onboarding steps (HTTP $http_code, empty response)"
    fi
    return 1
  fi

  # Verify we got JSON (starts with [ or {)
  if ! echo "$response" | jq . > /dev/null 2>&1; then
    if [ "$log_output" = "true" ]; then
      log_warn "Failed to parse onboarding response as JSON (HTTP $http_code)"
      log_warn "Response: $response"
    fi
    return 1
  fi

  # Log the full response for debugging if requested
  if [ "$log_output" = "true" ]; then
    log_info "Onboarding API response: $response"
  fi

  # Parse steps and extract incomplete ones
  local incomplete_steps
  incomplete_steps=$(echo "$response" | jq -r '.[] | select(.done == false) | .step' 2> /dev/null || echo "")

  if [ -z "$incomplete_steps" ]; then
    if [ "$log_output" = "true" ]; then
      log_info "All onboarding steps already completed"
    fi
    return 0
  fi

  if [ "$log_output" = "true" ]; then
    log_info "Incomplete onboarding steps:"
    echo "$incomplete_steps" | while IFS= read -r step; do
      [ -n "$step" ] && log_info "  - $step"
    done
  fi

  # Return the list of incomplete steps (one per line) to stdout
  echo "$incomplete_steps"
}

# Generic function to complete an onboarding step
complete_onboarding_step() {
  local step_name="$1"
  local payload_data="$2"
  local auth_token="$3"
  local max_retries="${4:-3}"

  if [ -z "$step_name" ]; then
    log_error "Missing required parameter: step_name"
    return 1
  fi

  local endpoint="$HA_URL/api/onboarding/$step_name"
  log_info "Attempting to complete onboarding step: $step_name"

  local attempt=0
  local retry_delay=10

  while [ $attempt -lt "$max_retries" ]; do
    attempt=$((attempt + 1))

    local response
    # Try with auth token if provided, otherwise try without (onboarding endpoints may not require auth)
    if [ -n "$auth_token" ]; then
      response=$(curl -s -w "\n%{http_code}" -X POST \
        "$endpoint" \
        -H "Authorization: Bearer $auth_token" \
        -H "Content-Type: application/json" \
        -d "$payload_data" 2>&1)
    else
      response=$(curl -s -w "\n%{http_code}" -X POST \
        "$endpoint" \
        -H "Content-Type: application/json" \
        -d "$payload_data" 2>&1)
    fi

    local http_code
    http_code=$(echo "$response" | tail -n1)
    local body
    body=$(echo "$response" | sed '$d')

    case "$http_code" in
      200 | 201)
        log_success "Step '$step_name' completed successfully"
        return 0
        ;;
      400)
        if [ $attempt -lt "$max_retries" ]; then
          log_warn "Step '$step_name' returned HTTP 400 (initialization issue), retrying in ${retry_delay}s... (attempt $attempt/$max_retries)"
          sleep $retry_delay
          retry_delay=$((retry_delay * 2)) # Exponential backoff
          continue
        else
          log_warn "Step '$step_name' returned HTTP 400 after $max_retries attempts"
          log_info "Response body: $body"
          return 1
        fi
        ;;
      403)
        log_info "Step '$step_name' already completed (HTTP 403)"
        return 0
        ;;
      404)
        log_info "Step '$step_name' not found or onboarding complete (HTTP 404)"
        return 0
        ;;
      401)
        # If we got 401 with auth token, try without token on next attempt (onboarding endpoints may work without auth)
        if [ -n "$auth_token" ] && [ $attempt -eq 1 ]; then
          log_warn "Step '$step_name' returned HTTP 401 with auth token - trying without auth on next attempt"
          auth_token="" # Clear token to try without auth
          sleep $retry_delay
          continue
        else
          log_warn "Step '$step_name' returned HTTP 401 (unauthorized)"
          log_info "Response body: $body"
          if [ $attempt -lt "$max_retries" ]; then
            log_info "Retrying in ${retry_delay}s... (attempt $attempt/$max_retries)"
            sleep $retry_delay
            retry_delay=$((retry_delay * 2))
            continue
          else
            return 1
          fi
        fi
        ;;
      *)
        log_warn "Step '$step_name' returned unexpected HTTP $http_code"
        log_info "Response body: $body"
        if [ $attempt -lt "$max_retries" ]; then
          log_info "Retrying in ${retry_delay}s... (attempt $attempt/$max_retries)"
          sleep $retry_delay
          retry_delay=$((retry_delay * 2))
          continue
        else
          return 1
        fi
        ;;
    esac
  done

  return 1
}

# Complete core_config step with Chicago location
complete_core_config_step() {
  local auth_token="${1:-}"

  log_info "Completing core_config step with Chicago location..."

  # Try full payload first
  local payload
  payload=$(jq -n \
    --arg lat "41.8781" \
    --arg lon "-87.6298" \
    --arg elev "181" \
    --arg units "imperial" \
    --arg tz "America/Chicago" \
    '{
      "latitude": ($lat | tonumber),
      "longitude": ($lon | tonumber),
      "elevation": ($elev | tonumber),
      "unit_system": $units,
      "time_zone": $tz
    }' 2> /dev/null)

  if [ -z "$payload" ]; then
    # Fallback if jq fails
    payload='{"latitude": 41.8781, "longitude": -87.6298, "elevation": 181, "unit_system": "imperial", "time_zone": "America/Chicago"}'
  fi

  log_info "Using payload: $payload"

  # Try with full payload
  if complete_onboarding_step "core_config" "$payload" "$auth_token"; then
    return 0
  fi

  # If that fails, try minimal payload
  log_info "Full payload failed, trying minimal payload..."
  local minimal_payload
  minimal_payload='{"latitude": 41.8781, "longitude": -87.6298}'

  if complete_onboarding_step "core_config" "$minimal_payload" "$auth_token"; then
    return 0
  fi

  log_warn "Failed to complete core_config step after all attempts"
  return 1
}

# Complete analytics step with opt-out preferences
complete_analytics_step() {
  local auth_token="${1:-}"

  log_info "Completing analytics step with opt-out preferences..."

  # Try different payload structures
  local payload_attempts=(
    '{"base": false, "usage": false, "statistics": false}'
    '{"preferences": {"base": false, "usage": false, "statistics": false}}'
    '{"analytics": false}'
    '{}'
  )

  local attempt=0
  for payload in "${payload_attempts[@]}"; do
    attempt=$((attempt + 1))
    log_info "Trying analytics payload attempt $attempt: $payload"

    if complete_onboarding_step "analytics" "$payload" "$auth_token" 2; then
      return 0
    fi

    if [ $attempt -lt ${#payload_attempts[@]} ]; then
      log_info "Payload attempt $attempt failed, trying next..."
      sleep 2
    fi
  done

  log_warn "Failed to complete analytics step after all payload attempts"
  return 1
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
      | jq -r '.data.healthy // false' 2> /dev/null || echo "false")

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

  # Check if sidebar is already enabled
  local current_options
  current_options=$(ha addons info "$EMQX_SLUG" --raw-json 2> /dev/null \
    | jq -r '.data.options.ingress_panel // false' 2> /dev/null || echo "false")

  if [ "$current_options" = "true" ]; then
    log_success "EMQX sidebar already enabled, skipping"
    return 0
  fi

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
    wait $start_pid 2> /dev/null || true
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
  if [ -z "${CYNC_USERNAME:-}" ] || [ -z "${CYNC_PASSWORD:-}" ]; then
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
    "account_username": "${CYNC_USERNAME:-}",
    "account_password": "${CYNC_PASSWORD:-}",
    "debug_log_level": true,
    "mqtt_host": "localhost",
    "mqtt_port": 1883,
    "mqtt_user": "${MQTT_USER:-}",
    "mqtt_pass": "${MQTT_PASS:-}",
    "mqtt_topic": "cync_controller_addon",
    "tuning": {
      "tcp_whitelist": "",
      "command_targets": 1,
      "max_clients": 64
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
    wait $start_pid 2> /dev/null || true
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

# Validate and refresh token if expired or near expiry
validate_and_refresh_token() {
  local token="${1:-$LONG_LIVED_ACCESS_TOKEN}"

  if [ -z "$token" ]; then
    log_error "No token provided for validation"
    return 1
  fi

  # Check if jq is available for JSON parsing
  if ! command -v jq > /dev/null 2>&1 && ! docker exec hassio_cli sh -c "command -v jq >/dev/null 2>&1"; then
    log_warn "jq not available; cannot validate token expiration"
    return 0
  fi

  # Decode JWT token (payload is second part, split by dots)
  # JWT format: header.payload.signature
  local payload
  payload=$(echo "$token" | cut -d'.' -f2)

  # JWT base64 padding may be missing, add it if needed
  case $((${#payload} % 4)) in
    2) payload="${payload}==" ;;
    3) payload="${payload}=" ;;
  esac

  # Decode base64 and extract exp claim
  local exp_claim
  if command -v jq > /dev/null 2>&1; then
    exp_claim=$(echo "$payload" | base64 -d 2> /dev/null | jq -r '.exp // empty' 2> /dev/null || echo "")
  else
    # Try using hassio_cli if jq is not available locally
    exp_claim=$(docker exec hassio_cli sh -c "echo '$payload' | base64 -d 2>/dev/null | jq -r '.exp // empty' 2>/dev/null || echo ''" 2> /dev/null || echo "")
  fi

  # If we couldn't extract expiration, assume token is invalid and refresh
  if [ -z "$exp_claim" ] || [ "$exp_claim" = "null" ]; then
    log_warn "Could not parse token expiration; will refresh token to be safe"
    # Fall through to refresh logic below
  else
    # Get current timestamp
    local current_time
    current_time=$(date +%s)

    # Check if token is expired (exp < current time) or will expire in 5 minutes
    local time_until_expiry=$((exp_claim - current_time))
    local min_valid_time=$((5 * 60)) # 5 minutes in seconds

    if [ $time_until_expiry -gt $min_valid_time ]; then
      log_info "Token is valid (expires in $((time_until_expiry / 60)) minutes)"
      return 0
    else
      log_warn "Token expired or expires soon (exp: $exp_claim, current: $current_time)"
      log_info "Refreshing token..."
      # Fall through to refresh logic below
    fi
  fi

  # Regenerate token using WebSocket script
  log_info "Creating fresh long-lived access token using WebSocket script..."

  local token_script="$REPO_ROOT/scripts/create-token-websocket.js"

  if [ ! -f "$token_script" ]; then
    log_error "WebSocket token creation script not found: $token_script"
    return 1
  fi

  # Run the token creation script with proper environment variables
  local token_output
  token_output=$(HA_URL="$HA_URL" HASS_USERNAME="$HASS_USERNAME" HASS_PASSWORD="$HASS_PASSWORD" node "$token_script" 2>&1) || {
    log_error "Failed to create token using WebSocket script"
    log_error "Output: $token_output"
    return 1
  }

  # Extract the token from the output (look for JWT pattern)
  local new_token
  new_token=$(echo "$token_output" | grep -oE "eyJ[A-Za-z0-9_-]*\.[A-Za-z0-9_-]*\.[A-Za-z0-9_-]*" | head -n1)

  if [ -z "$new_token" ]; then
    log_error "Failed to extract token from WebSocket script output"
    log_error "Output: $token_output"
    return 1
  fi

  log_success "Successfully created fresh long-lived token"

  # Update the global variable
  LONG_LIVED_ACCESS_TOKEN="$new_token"

  # Save the long-lived access token to credentials file
  if grep -q "LONG_LIVED_ACCESS_TOKEN=" "$CREDENTIALS_FILE" 2> /dev/null; then
    sed -i "s|^LONG_LIVED_ACCESS_TOKEN=.*|LONG_LIVED_ACCESS_TOKEN=$new_token|" "$CREDENTIALS_FILE"
  else
    echo "LONG_LIVED_ACCESS_TOKEN=$new_token" >> "$CREDENTIALS_FILE"
  fi

  log_success "Updated credentials file with fresh long-lived access token"
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

  local auth_token="${LONG_LIVED_ACCESS_TOKEN:-}"

  if [ -z "$auth_token" ]; then
    log_error "Missing long-lived access token; cannot configure MQTT integration"
    return 1
  fi

  local start_payload='{"handler":"mqtt","show_advanced_options":true}'
  local response
  local http_code
  local response_body

  # Make curl request and capture both response body and HTTP status code
  response=$(curl -s -w "\n%{http_code}" -X POST "$HA_URL/api/config/config_entries/flow" \
    -H "Authorization: Bearer $auth_token" \
    -H "Content-Type: application/json" \
    -d "$start_payload" 2>&1)

  # Extract HTTP status code (last line) and response body (everything else)
  http_code=$(echo "$response" | tail -n1)
  response_body=$(echo "$response" | sed '$d')

  # Check if HTTP status code indicates an error
  if [ "$http_code" -lt 200 ] || [ "$http_code" -ge 300 ]; then
    log_error "Failed to start MQTT config flow via REST API"
    log_error "HTTP Status: $http_code"
    log_error "Endpoint: $HA_URL/api/config/config_entries/flow"
    log_error "Response: $response_body"

    # Provide helpful error messages for common status codes
    case "$http_code" in
      401)
        log_error "Authentication failed - token may be invalid or expired"

        # Try to refresh token and retry once
        log_info "Attempting to refresh token and retry..."
        if validate_and_refresh_token; then
          log_info "Token refreshed, retrying MQTT config flow..."
          # Retry the request with refreshed token
          auth_token="$LONG_LIVED_ACCESS_TOKEN"
          response=$(curl -s -w "\n%{http_code}" -X POST "$HA_URL/api/config/config_entries/flow" \
            -H "Authorization: Bearer $auth_token" \
            -H "Content-Type: application/json" \
            -d "$start_payload" 2>&1)

          http_code=$(echo "$response" | tail -n1)
          response_body=$(echo "$response" | sed '$d')

          if [ "$http_code" -lt 200 ] || [ "$http_code" -ge 300 ]; then
            log_error "Retry after token refresh also failed with HTTP $http_code"
            return 1
          else
            log_success "Successfully started MQTT config flow after token refresh"
          fi
        else
          log_error "Failed to refresh token, cannot proceed"
          return 1
        fi
        ;;
      403) log_error "Access forbidden - check token permissions" ;;
      404) log_error "Endpoint not found - may need to wait for HA to fully initialize" ;;
      500) log_error "Server error - check Home Assistant logs" ;;
    esac

    # If we didn't handle it above, return error
    if [ "$http_code" -lt 200 ] || [ "$http_code" -ge 300 ]; then
      return 1
    fi
  fi

  local step_json="$response_body"
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
      local menu_response
      menu_response=$(curl -s -w "\n%{http_code}" -X POST "$HA_URL/api/config/config_entries/flow/$flow_id" \
        -H "Authorization: Bearer $auth_token" \
        -H "Content-Type: application/json" \
        -d '{"next_step_id":"broker"}' 2>&1)

      local menu_http_code
      menu_http_code=$(echo "$menu_response" | tail -n1)
      local menu_response_body
      menu_response_body=$(echo "$menu_response" | sed '$d')

      # If first attempt failed, try fallback
      if [ "$menu_http_code" -lt 200 ] || [ "$menu_http_code" -ge 300 ]; then
        # Fallback to user_input wrapper
        menu_response=$(curl -s -w "\n%{http_code}" -X POST "$HA_URL/api/config/config_entries/flow/$flow_id" \
          -H "Authorization: Bearer $auth_token" \
          -H "Content-Type: application/json" \
          -d '{"user_input":{"next_step_id":"broker"}}' 2>&1)

        menu_http_code=$(echo "$menu_response" | tail -n1)
        menu_response_body=$(echo "$menu_response" | sed '$d')

        # If fallback also failed, report error
        if [ "$menu_http_code" -lt 200 ] || [ "$menu_http_code" -ge 300 ]; then
          log_error "Failed to submit MQTT config flow step (menu)"
          log_error "HTTP Status: $menu_http_code"
          log_error "Endpoint: $HA_URL/api/config/config_entries/flow/$flow_id"
          log_error "Response: $menu_response_body"

          case "$menu_http_code" in
            401) log_error "Authentication failed - token may be invalid or expired" ;;
            403) log_error "Access forbidden - check token permissions" ;;
            404) log_error "Endpoint not found - flow may have expired" ;;
            500) log_error "Server error - check Home Assistant logs" ;;
          esac

          return 1
        fi
      fi

      response="$menu_response_body"
    else
      # Form step submission
      local form_response
      form_response=$(curl -s -w "\n%{http_code}" -X POST "$HA_URL/api/config/config_entries/flow/$flow_id" \
        -H "Authorization: Bearer $auth_token" \
        -H "Content-Type: application/json" \
        -d "$request_body" 2>&1)

      local form_http_code
      form_http_code=$(echo "$form_response" | tail -n1)
      local form_response_body
      form_response_body=$(echo "$form_response" | sed '$d')

      if [ "$form_http_code" -lt 200 ] || [ "$form_http_code" -ge 300 ]; then
        log_error "Failed to submit MQTT config flow step"
        log_error "HTTP Status: $form_http_code"
        log_error "Endpoint: $HA_URL/api/config/config_entries/flow/$flow_id"
        log_error "Response: $form_response_body"

        case "$form_http_code" in
          401) log_error "Authentication failed - token may be invalid or expired" ;;
          403) log_error "Access forbidden - check token permissions" ;;
          404) log_error "Endpoint not found - flow may have expired" ;;
          500) log_error "Server error - check Home Assistant logs" ;;
        esac

        return 1
      fi

      response="$form_response_body"
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
  local auth_token="${LONG_LIVED_ACCESS_TOKEN:-}"

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
    -d "$payload" 2> /dev/null || echo "000")

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

  # Step 2.5: Wait for HA Core service to be ready (not just API responding)
  wait_for_ha_core_ready

  # Step 2.75: Verify HTTP API is ready for Python requests
  wait_for_ha_api_ready

  # Step 3: Handle onboarding if needed
  if check_onboarding_status; then
    log_info "Home Assistant needs onboarding, running automation script..."
    log_info "This will create user (if needed) and complete all onboarding steps..."

    local auth_token=""
    local onboarding_result=1
    local retry_count=0
    local max_retries=2
    local retry_delay=10

    # Retry logic with exponential backoff and restart handling
    while [ $retry_count -le $max_retries ]; do
      if [ $retry_count -gt 0 ]; then
        log_info "Retrying onboarding automation (attempt $((retry_count + 1))/$((max_retries + 1)))..."
        log_info "Waiting ${retry_delay}s before retry..."
        sleep $retry_delay
        retry_delay=$((retry_delay * 2)) # Exponential backoff
      fi

      # Use the new Python-based onboarding automation
      set +e
      auth_token=$(run_onboarding_automation)
      onboarding_result=$?
      set -e

      # Handle restart code (2): restart HA Core and retry
      if [ $onboarding_result -eq 2 ]; then
        log_warn "Onboarding script indicates HA Core restart is needed"
        log_info "Restarting Home Assistant Core..."

        if ha core restart > /dev/null 2>&1; then
          log_success "HA Core restart command issued"
          log_info "Waiting for HA Core to restart and become ready..."

          # Wait for Core to restart (up to 60 seconds)
          local wait_count=0
          local max_wait=12
          while [ $wait_count -lt $max_wait ]; do
            sleep 5
            local core_version
            core_version=$(ha core info --raw-json 2> /dev/null | jq -r '.data.version // empty' 2> /dev/null || echo "")
            if [ -n "$core_version" ] && [ "$core_version" != "null" ] && [ "$core_version" != "" ]; then
              log_success "HA Core restarted and ready (version: $core_version)"
              break
            fi
            wait_count=$((wait_count + 1))
            log_info "Waiting for Core restart... ($wait_count/$max_wait)"
          done

          # Verify HA API is responsive again
          wait_for_ha
          wait_for_ha_core_ready
          wait_for_ha_api_ready

          # Retry onboarding (increment counter and continue loop)
          retry_count=$((retry_count + 1))
          continue
        else
          log_error "Failed to restart HA Core"
          log_error "Cannot proceed without completing onboarding"
          exit 1
        fi
      fi

      # Success case
      if [ $onboarding_result -eq 0 ]; then
        log_success "Onboarding automation completed successfully"
        break
      fi

      # Failure case (exit code 1): retry if we have retries left
      if [ $retry_count -lt $max_retries ]; then
        log_warn "Onboarding automation failed (exit code: $onboarding_result)"
        log_info "Will retry with exponential backoff..."
        retry_count=$((retry_count + 1))
      else
        log_error "Failed to complete onboarding automation after $((max_retries + 1)) attempts"
        log_error "Cannot proceed without completing onboarding"
        log_error "Check /tmp/onboarding-automation.log for detailed error output"
        exit 1
      fi
    done

    if [ -z "$auth_token" ]; then
      # Try to get token from credentials file (prefer LONG_LIVED_ACCESS_TOKEN, fallback to ONBOARDING_TOKEN)
      if [ -f "$CREDENTIALS_FILE" ]; then
        # First, try to get LONG_LIVED_ACCESS_TOKEN (preferred - long-lived)
        auth_token=$(grep "^LONG_LIVED_ACCESS_TOKEN=" "$CREDENTIALS_FILE" | cut -d'=' -f2 | tr -d '"' || echo "")

        # If no long-lived token, try ONBOARDING_TOKEN (short-lived, but usable)
        if [ -z "$auth_token" ]; then
          local onboarding_token
          onboarding_token=$(grep "^ONBOARDING_TOKEN=" "$CREDENTIALS_FILE" | cut -d'=' -f2 | tr -d '"' || echo "")
          if [ -n "$onboarding_token" ]; then
            log_info "Found ONBOARDING_TOKEN, creating long-lived token..."
            # Try to create long-lived token from onboarding token
            local bootstrap_token_script="$REPO_ROOT/scripts/create-token-from-existing.js"
            if [ -f "$bootstrap_token_script" ]; then
              local token_output
              token_output=$(HA_URL="$HA_URL" EXISTING_TOKEN="$onboarding_token" ONBOARDING_TOKEN="$onboarding_token" node "$bootstrap_token_script" 2>&1) || {
                log_warn "Failed to create long-lived token from onboarding token"
                log_warn "Will use onboarding token (may be short-lived)"
                auth_token="$onboarding_token"
              }

              # Extract the long-lived token from output
              local new_token
              new_token=$(echo "$token_output" | grep -oE "eyJ[A-Za-z0-9_-]*\.[A-Za-z0-9_-]*\.[A-Za-z0-9_-]*" | head -n1)
              if [ -n "$new_token" ]; then
                log_success "Successfully created long-lived token from onboarding token"
                auth_token="$new_token"
                # Save the long-lived token to credentials file
                if grep -q "LONG_LIVED_ACCESS_TOKEN=" "$CREDENTIALS_FILE" 2> /dev/null; then
                  sed -i "s|^LONG_LIVED_ACCESS_TOKEN=.*|LONG_LIVED_ACCESS_TOKEN=$new_token|" "$CREDENTIALS_FILE"
                else
                  echo "LONG_LIVED_ACCESS_TOKEN=$new_token" >> "$CREDENTIALS_FILE"
                fi
              else
                log_warn "Failed to extract long-lived token, using onboarding token"
                auth_token="$onboarding_token"
              fi
            else
              log_warn "Token bootstrap script not found, using onboarding token"
              auth_token="$onboarding_token"
            fi
          fi
        fi
      fi

      # If still no token, try WebSocket token creation as fallback (username/password based)
      if [ -z "$auth_token" ]; then
        log_warn "No token found after onboarding automation"
        log_info "Attempting to create token via WebSocket (username/password)..."
        local token_script="$REPO_ROOT/scripts/create-token-websocket.js"

        if [ -f "$token_script" ]; then
          local token_output
          token_output=$(HA_URL="$HA_URL" HASS_USERNAME="$HASS_USERNAME" HASS_PASSWORD="$HASS_PASSWORD" node "$token_script" 2>&1) || {
            log_error "Failed to create token using WebSocket script"
            log_error "Output: $token_output"
            log_error "Cannot proceed without authentication token"
            exit 1
          }

          # Extract the token from the output
          auth_token=$(echo "$token_output" | grep -oE "eyJ[A-Za-z0-9_-]*\.[A-Za-z0-9_-]*\.[A-Za-z0-9_-]*" | head -n1)

          if [ -z "$auth_token" ]; then
            log_error "Failed to extract token from WebSocket script output"
            log_error "Output: $token_output"
            log_error "Cannot proceed without authentication token"
            exit 1
          fi

          log_success "Successfully created token using WebSocket script"
        else
          log_error "WebSocket token creation script not found: $token_script"
          log_error "Cannot proceed without authentication token"
          exit 1
        fi
      fi
    fi

    log_success "Onboarding completed successfully"
    log_info "Auth token obtained and ready for use"

    # Verify onboarding is complete (Python script should have handled everything)
    # Add delay to allow token activation and use long-lived token for verification
    log_info "Verifying onboarding completion..."
    log_info "Waiting for token activation (3 seconds)..."
    sleep 3

    # Ensure we're using LONG_LIVED_ACCESS_TOKEN for verification (not ONBOARDING_TOKEN)
    if [ -f "$CREDENTIALS_FILE" ]; then
      local verify_token
      verify_token=$(grep "^LONG_LIVED_ACCESS_TOKEN=" "$CREDENTIALS_FILE" | cut -d'=' -f2 | tr -d '"' || echo "")
      if [ -n "$verify_token" ]; then
        log_info "Using LONG_LIVED_ACCESS_TOKEN for verification"
        auth_token="$verify_token"
      else
        log_warn "No LONG_LIVED_ACCESS_TOKEN found, using available token for verification"
      fi
    fi

    local incomplete_steps
    local verify_result
    local verify_retry_count=0
    local max_verify_retries=3

    # Retry verification if it fails with 401 (token may need more time to activate)
    while [ $verify_retry_count -lt $max_verify_retries ]; do
      incomplete_steps=$(discover_onboarding_steps "$auth_token" false)
      verify_result=$?

      if [ $verify_result -eq 0 ]; then
        # Verification succeeded
        break
      fi

      # If verification failed with 401, wait and retry
      if [ $verify_retry_count -lt $((max_verify_retries - 1)) ]; then
        log_warn "Verification failed (exit code: $verify_result), retrying in 2 seconds..."
        sleep 2
        verify_retry_count=$((verify_retry_count + 1))
      else
        break
      fi
    done

    if [ $verify_result -eq 0 ]; then
      if [ -z "$incomplete_steps" ]; then
        log_success "All onboarding steps completed successfully"
      else
        log_warn "Some onboarding steps may still be incomplete:"
        echo "$incomplete_steps" | while IFS= read -r step; do
          [ -n "$step" ] && log_warn "  - $step"
        done
        log_info "Python automation script should have completed all steps"
        log_info "If steps remain incomplete, you may need to check Home Assistant logs"
      fi
    else
      # Verification failed (likely 401 - token issue)
      # Since Python script reported success, assume onboarding completed
      log_warn "Verification step failed (likely token issue) after $max_verify_retries attempts"
      log_info "Python script reported onboarding completed successfully"
      log_info "Assuming onboarding is complete (verification could not be performed)"
    fi
  else
    log_info "Onboarding already completed, proceeding with token creation"
  fi

  # Step 4: Create fresh long-lived access token using WebSocket script (only if one doesn't exist)
  # Check if we already have a LONG_LIVED_ACCESS_TOKEN
  local existing_llat=""
  if [ -f "$CREDENTIALS_FILE" ]; then
    existing_llat=$(grep "^LONG_LIVED_ACCESS_TOKEN=" "$CREDENTIALS_FILE" | cut -d'=' -f2 | tr -d '"' || echo "")
  fi

  if [ -n "$existing_llat" ]; then
    log_info "Long-lived access token already exists, validating before use"
    LONG_LIVED_ACCESS_TOKEN="$existing_llat"

    # Validate and refresh token if expired or near expiry
    if ! validate_and_refresh_token "$existing_llat"; then
      log_error "Failed to validate/refresh token; cannot proceed"
      exit 1
    fi

    log_success "Using validated LONG_LIVED_ACCESS_TOKEN"
  else
    log_info "No long-lived access token found, creating fresh one using WebSocket script..."

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
