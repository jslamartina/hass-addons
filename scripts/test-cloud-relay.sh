#!/usr/bin/env bash
# Automated Cloud Relay Mode Testing Script
# Tests all phases of cloud relay functionality
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/shell-common/common-output.sh"

LP="[$(basename "$0")]"
CONFIG_SCRIPT="${SCRIPT_DIR}/configure-addon.sh"

# Test results
TESTS_PASSED=0
TESTS_FAILED=0
TESTS_TOTAL=0

# Function to print section header (use log_section from common lib)
section() {
  log_section "$1"
}

# Override test_result to track totals
test_result() {
  local name="$1"
  local passed="$2"
  local message="$3"

  TESTS_TOTAL=$((TESTS_TOTAL + 1))

  if [ "$passed" = "true" ]; then
    echo -e "${GREEN}✅ PASS${NC} - $name"
    [ -n "$message" ] && echo "   $message"
    TESTS_PASSED=$((TESTS_PASSED + 1))
  else
    echo -e "${RED}❌ FAIL${NC} - $name"
    [ -n "$message" ] && echo "   $message"
    TESTS_FAILED=$((TESTS_FAILED + 1))
  fi
}

# Function to check log for pattern
check_log() {
  local pattern="$1"
  local description="$2"
  local max_lines="${3:-100}"

  if ha addons logs local_cync-controller 2>&1 | tail -n "$max_lines" | grep -q "$pattern"; then
    test_result "$description" true "Found: $pattern"
    return 0
  else
    test_result "$description" false "Not found: $pattern"
    return 1
  fi
}

# Function to wait for log pattern
wait_for_log() {
  local pattern="$1"
  local timeout="${2:-30}"
  local description="$3"

  echo "   Waiting for: $pattern (timeout: ${timeout}s)"

  local elapsed=0
  while [ $elapsed -lt "$timeout" ]; do
    if ha addons logs local_cync-controller 2>&1 | grep -q "$pattern"; then
      test_result "$description" true "Appeared after ${elapsed}s"
      return 0
    fi
    sleep 2
    elapsed=$((elapsed + 2))
  done

  test_result "$description" false "Timeout waiting for pattern"
  return 1
}

# Function to apply configuration and wait
apply_config() {
  local preset="$1"
  local description="$2"

  section "$description"
  echo "$LP Applying preset: $preset"

  if "$CONFIG_SCRIPT" "$preset" > /tmp/config-output.log 2>&1; then
    test_result "Configuration applied" true "Preset: $preset"
    echo "$LP Waiting for add-on to stabilize..."
    sleep 8
    return 0
  else
    test_result "Configuration applied" false "Failed to apply $preset"
    cat /tmp/config-output.log
    return 1
  fi
}

# Main test execution
main() {
  section "Cloud Relay Mode - Automated Testing"
  echo "$LP Starting comprehensive cloud relay tests..."
  echo "$LP This will test all operating modes and verify functionality"
  echo ""

  # Phase 1: Baseline (LAN-only mode)
  apply_config "preset-baseline" "Phase 1: Baseline LAN-only Mode"
  check_log "nCync server listening" "nCync server started"
  check_log "MQTT discovery complete" "MQTT discovery completed"

  # Verify NO cloud relay in baseline
  if ha addons logs local_cync-controller 2>&1 | tail -n 100 | grep -q "RELAY mode"; then
    test_result "Baseline: No relay mode" false "Found RELAY mode when disabled"
  else
    test_result "Baseline: No relay mode" true "Correctly running in normal mode"
  fi

  # Phase 2: Cloud Relay with Forwarding
  apply_config "preset-relay-with-forward" "Phase 2: Cloud Relay with Forwarding"
  check_log "Cloud relay mode ENABLED" "Cloud relay enabled"
  check_log "forward_to_cloud=True" "Cloud forwarding enabled"
  wait_for_log "New connection in RELAY mode" 15 "Device connected in relay mode"
  wait_for_log "Connected to cloud server" 15 "Cloud connection established"
  check_log "Device endpoint:" "Device endpoint identified"

  # Phase 3: Debug Packet Logging
  apply_config "preset-relay-debug" "Phase 3: Cloud Relay with Debug Logging"
  check_log "debug_packet_logging=True" "Debug logging enabled"
  check_log "New connection in RELAY mode" "Still in relay mode"

  # Wait for a packet to be logged (should happen quickly with active devices)
  echo "$LP Waiting for debug packet logs to appear..."
  sleep 10

  if ha addons logs local_cync-controller 2>&1 | tail -n 200 | grep -qE "RELAY Device→Cloud|RELAY Cloud→Device|\[PARSED\]"; then
    test_result "Debug packet logging" true "Found detailed packet logs"
  else
    test_result "Debug packet logging" false "No detailed packet logs found (may need device activity)"
  fi

  # Phase 4: LAN-only Mode (Privacy Mode)
  apply_config "preset-lan-only" "Phase 4: LAN-only Relay (Privacy Mode)"
  check_log "forward_to_cloud=False" "Cloud forwarding disabled"
  check_log "New connection in RELAY mode" "Still accepting connections"

  # In LAN-only mode, should NOT connect to cloud
  sleep 8
  if ha addons logs local_cync-controller 2>&1 | tail -n 100 | grep -q "Connected to cloud server"; then
    test_result "LAN-only: No cloud connection" false "Found cloud connection in LAN-only mode"
  else
    test_result "LAN-only: No cloud connection" true "Correctly blocking cloud access"
  fi

  # Phase 5: Packet Injection Test
  section "Phase 5: Packet Injection"

  # Check if injection directory exists in container
  docker exec addon_local_cync-controller test -d /tmp && injection_available=true || injection_available=false

  if [ "$injection_available" = "true" ]; then
    echo "$LP Testing mode change packet injection..."
    docker exec addon_local_cync-controller sh -c 'echo "smart" > /tmp/cync_inject_command.txt'
    sleep 3

    if ha addons logs local_cync-controller 2>&1 | tail -n 50 | grep -qE "Injecting|inject"; then
      test_result "Packet injection" true "Injection command processed"
    else
      test_result "Packet injection" false "No injection logs found"
    fi

    # Clean up injection file
    docker exec addon_local_cync-controller rm -f /tmp/cync_inject_command.txt 2> /dev/null || true
  else
    test_result "Packet injection" false "Container /tmp not accessible"
  fi

  # Phase 6: Return to baseline
  apply_config "preset-baseline" "Phase 6: Return to Baseline"
  check_log "Cloud relay mode DISABLED" "Cloud relay disabled"

  # Verify back to normal operation
  sleep 5
  if ha addons logs local_cync-controller 2>&1 | tail -n 100 | grep -q "RELAY mode"; then
    test_result "Baseline restore" false "Still in relay mode after disabling"
  else
    test_result "Baseline restore" true "Successfully returned to normal mode"
  fi

  # Final summary
  section "Test Summary"
  echo ""
  echo "Total Tests:  $TESTS_TOTAL"
  echo -e "${GREEN}Passed:       $TESTS_PASSED${NC}"

  if [ $TESTS_FAILED -gt 0 ]; then
    echo -e "${RED}Failed:       $TESTS_FAILED${NC}"
  else
    echo "Failed:       $TESTS_FAILED"
  fi

  echo ""

  if [ $TESTS_FAILED -eq 0 ]; then
    echo -e "${GREEN}╔═════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║                                                     ║${NC}"
    echo -e "${GREEN}║ ✅  ALL TESTS PASSED - CLOUD RELAY WORKING! ✅      ║${NC}"
    echo -e "${GREEN}║                                                     ║${NC}"
    echo -e "${GREEN}╚═════════════════════════════════════════════════════╝${NC}"
    exit 0
  else
    echo -e "${RED}╔═════════════════════════════════════════════════════╗${NC}"
    echo -e "${RED}║                                                     ║${NC}"
    echo -e "${RED}║     ❌  SOME TESTS FAILED - SEE ABOVE  ❌           ║${NC}"
    echo -e "${RED}║                                                     ║${NC}"
    echo -e "${RED}╚═════════════════════════════════════════════════════╝${NC}"
    exit 1
  fi
}

# Run main function
main "$@"
