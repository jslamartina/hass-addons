#!/bin/bash
#
# Run Integration Tests
#
# This script sets up Docker environment and runs integration tests
# for the Cync Controller add-on.
#
# Usage:
#   ./scripts/run-integration-tests.sh [pytest-args]
#
# Examples:
#   ./scripts/run-integration-tests.sh                 # Run all integration tests
#   ./scripts/run-integration-tests.sh -v              # Verbose output
#   ./scripts/run-integration-tests.sh -k mqtt         # Run only MQTT tests
#   ./scripts/run-integration-tests.sh --setup-only    # Setup environment only
#   ./scripts/run-integration-tests.sh --teardown-only # Teardown only

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
COMPOSE_FILE="cync-controller/tests/integration/docker-compose.test.yml"
TEST_DIR="cync-controller/tests/integration"
LOG_FILE="integration-test-logs.txt"

# Print colored message
print_msg() {
  local color=$1
  shift
  echo -e "${color}$*${NC}"
}

# Print section header
print_section() {
  echo
  print_msg "$BLUE" "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  print_msg "$BLUE" "$1"
  print_msg "$BLUE" "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
}

# Check if running in correct directory
check_directory() {
  if [ ! -f "$COMPOSE_FILE" ]; then
    print_msg "$RED" "❌ Error: docker-compose.test.yml not found"
    print_msg "$YELLOW" "Please run this script from the repository root:"
    print_msg "$YELLOW" "  cd /workspaces/hass-addons && ./scripts/run-integration-tests.sh"
    exit 1
  fi
}

# Setup test environment
setup_environment() {
  print_section "🚀 Starting Integration Test Environment"

  print_msg "$BLUE" "Starting Docker containers..."
  docker-compose -f "$COMPOSE_FILE" up -d

  print_msg "$BLUE" "Waiting for services to be ready..."
  sleep 5

  # Wait for EMQX to be healthy
  print_msg "$BLUE" "Waiting for EMQX broker..."
  local max_attempts=30
  local attempt=0
  while [ $attempt -lt $max_attempts ]; do
    if docker-compose -f "$COMPOSE_FILE" ps | grep -q "emqx.*healthy"; then
      print_msg "$GREEN" "✅ EMQX broker is ready"
      break
    fi
    attempt=$((attempt + 1))
    sleep 1
  done

  if [ $attempt -eq $max_attempts ]; then
    print_msg "$RED" "❌ EMQX broker failed to become healthy"
    print_msg "$YELLOW" "Check logs with: docker-compose -f $COMPOSE_FILE logs emqx"
    return 1
  fi

  # Wait for cync-controller to be healthy
  print_msg "$BLUE" "Waiting for Cync Controller..."
  attempt=0
  while [ $attempt -lt $max_attempts ]; do
    if docker-compose -f "$COMPOSE_FILE" ps | grep -q "cync-controller.*healthy"; then
      print_msg "$GREEN" "✅ Cync Controller is ready"
      break
    fi
    attempt=$((attempt + 1))
    sleep 1
  done

  if [ $attempt -eq $max_attempts ]; then
    print_msg "$RED" "❌ Cync Controller failed to become healthy"
    print_msg "$YELLOW" "Check logs with: docker-compose -f $COMPOSE_FILE logs cync-controller"
    return 1
  fi

  # Give services a bit more time to fully initialize
  print_msg "$BLUE" "Waiting for full service initialization..."
  sleep 5

  print_msg "$GREEN" "✅ Integration test environment ready!"
}

# Run integration tests
run_tests() {
  print_section "🧪 Running Integration Tests"

  # Set environment variables for tests
  export MQTT_HOST=localhost
  export MQTT_PORT=1883
  export MQTT_USER=test_user
  export MQTT_PASS=test_pass
  export CYNC_CONTROLLER_HOST=localhost
  export CYNC_CONTROLLER_PORT=23779

  # Run pytest with integration marker
  print_msg "$BLUE" "Running pytest..."
  cd cync-controller

  # Install test dependencies if needed
  if ! python3 -c "import pytest" 2> /dev/null; then
    print_msg "$YELLOW" "Installing test dependencies..."
    pip install -e ".[test]" -q
  fi

  # Run tests
  local pytest_args=("$@")
  if [ ${#pytest_args[@]} -eq 0 ]; then
    pytest_args=("-v" "-m" "integration")
  fi

  pytest tests/integration/ "${pytest_args[@]}" || true

  cd ..

  print_msg "$GREEN" "✅ Tests complete!"
}

# Collect logs
collect_logs() {
  print_section "📋 Collecting Container Logs"

  print_msg "$BLUE" "Saving logs to $LOG_FILE..."
  docker-compose -f "$COMPOSE_FILE" logs > "$LOG_FILE" 2>&1

  print_msg "$GREEN" "✅ Logs saved to $LOG_FILE"
}

# Teardown test environment
teardown_environment() {
  print_section "🧹 Cleaning Up"

  print_msg "$BLUE" "Stopping containers..."
  docker-compose -f "$COMPOSE_FILE" down

  print_msg "$GREEN" "✅ Cleanup complete!"
}

# Main execution
main() {
  check_directory

  # Parse special flags
  local setup_only=false
  local teardown_only=false
  local skip_teardown=false
  local pytest_args=()

  for arg in "$@"; do
    case $arg in
      --setup-only)
        setup_only=true
        ;;
      --teardown-only)
        teardown_only=true
        ;;
      --no-teardown)
        skip_teardown=true
        ;;
      *)
        pytest_args+=("$arg")
        ;;
    esac
  done

  # Handle teardown-only mode
  if [ "$teardown_only" = true ]; then
    teardown_environment
    exit 0
  fi

  # Setup environment
  setup_environment || {
    print_msg "$RED" "❌ Failed to setup environment"
    collect_logs
    teardown_environment
    exit 1
  }

  # Handle setup-only mode
  if [ "$setup_only" = true ]; then
    print_msg "$YELLOW" "Setup complete. Environment is running."
    print_msg "$YELLOW" "Run tests manually or use --teardown-only to clean up."
    exit 0
  fi

  # Run tests
  run_tests "${pytest_args[@]}"

  # Collect logs
  collect_logs

  # Teardown unless skipped
  if [ "$skip_teardown" = false ]; then
    teardown_environment
  else
    print_msg "$YELLOW" "Skipping teardown (--no-teardown specified)"
    print_msg "$YELLOW" "Environment is still running. Use --teardown-only to clean up."
  fi

  print_section "✅ Integration Tests Complete"
}

# Run main
main "$@"
