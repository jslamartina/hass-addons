#!/usr/bin/env bash
# Monitor RAM usage for npm run test:unit
# Usage: ./scripts/monitor-test-memory.sh [test-command]

set -Eeuo pipefail
IFS=$'\n\t'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091  # Source path is dynamic via $SCRIPT_DIR
source "$SCRIPT_DIR/shell-common/common-output.sh"

# shellcheck disable=SC2034  # LP used by common-output.sh log functions
LP="[$(basename "$0")]"

# Get the test command from args or use default
TEST_CMD="${1:-npm run test:unit}"

# Global variables for tracking
MAX_MEMORY=0
TEST_PID=0
EXIT_CODE=0

# Cleanup function (invoked via trap)
# shellcheck disable=SC2329,SC2317  # Function is invoked via trap statement
cleanup() {
  trap - EXIT ERR
  # Kill test process if still running
  if [ "$TEST_PID" -gt 0 ] && kill -0 "$TEST_PID" 2> /dev/null; then
    kill "$TEST_PID" 2> /dev/null || true
    wait "$TEST_PID" 2> /dev/null || true
  fi
}

# Error handler (invoked via trap)
# shellcheck disable=SC2329,SC2317  # Function is invoked via trap statement
on_error() {
  echo -e "${RED}Error on line $1${NC}" >&2
  cleanup
  exit 1
}

trap 'cleanup' EXIT
trap 'on_error $LINENO' ERR

# Function to get memory info in MB
get_mem_info() {
  local pid=$1
  if [ -z "$pid" ] || ! kill -0 "$pid" 2> /dev/null; then
    echo "0"
    return
  fi

  # Use ps to get RSS (Resident Set Size) in KB, convert to MB
  if command -v ps > /dev/null 2>&1; then
    # shellcheck disable=SC2015
    ps -o rss= -p "$pid" 2> /dev/null | awk '{print int($1/1024)}' || echo "0"
  else
    echo "0"
  fi
}

# Function to monitor process tree memory
monitor_tree_memory() {
  local parent_pid=$1
  local max_mem=0
  local sample_count=0

  echo -e "${YELLOW}Monitoring memory usage (sampling every 0.5s)...${NC}"
  echo ""

  # Get process group ID
  local pgid
  pgid=$(ps -o pgid= -p "$parent_pid" 2> /dev/null | tr -d ' ' || echo "")

  while kill -0 "$parent_pid" 2> /dev/null || [ -n "$(ps -p "$parent_pid" 2> /dev/null || true)" ]; do
    # Find all processes in the process tree - use both pgrep -P and pgid
    local pids="$parent_pid"

    # Find direct children
    local children
    children=$(pgrep -P "$parent_pid" 2> /dev/null || true)
    if [ -n "$children" ]; then
      pids="$pids $children"
    fi

    # Find all processes in the same process group if pgid is available
    if [ -n "$pgid" ] && [ "$pgid" != "0" ]; then
      local pgid_pids
      pgid_pids=$(ps -o pid= -g "$pgid" 2> /dev/null | tr -d ' ' || true)
      if [ -n "$pgid_pids" ]; then
        pids="$pids $pgid_pids"
      fi
    fi

    # Remove duplicates and get unique PIDs
    pids=$(echo "$pids" | tr ' ' '\n' | sort -u | tr '\n' ' ')

    local total_mem=0
    local process_count=0

    for pid in $pids; do
      # Skip if pid is empty or not a number
      [ -z "$pid" ] || [ "$pid" = "0" ] && continue

      local mem
      mem=$(get_mem_info "$pid")
      if [ "$mem" -gt 0 ]; then
        total_mem=$((total_mem + mem))
        process_count=$((process_count + 1))
      fi
    done

    if [ "$total_mem" -gt "$max_mem" ]; then
      max_mem=$total_mem
      MAX_MEMORY=$max_mem
    fi

    sample_count=$((sample_count + 1))

    # Print every 5 samples (2.5 seconds) to avoid spam
    if [ $((sample_count % 5)) -eq 0 ]; then
      printf "\r${GREEN}Current: %5d MB | Peak: %5d MB | Processes: %2d${NC}" \
        "$total_mem" "$max_mem" "$process_count"
    fi

    # If process finished and no memory tracked, wait a bit more for cleanup
    if ! kill -0 "$parent_pid" 2> /dev/null && [ "$total_mem" -eq 0 ] && [ "$sample_count" -lt 10 ]; then
      sleep 0.5
      continue
    fi

    # If process is gone and we've waited enough, exit
    if ! kill -0 "$parent_pid" 2> /dev/null && [ "$total_mem" -eq 0 ]; then
      break
    fi

    sleep 0.5
  done

  echo ""
  echo ""
}

echo -e "${BLUE}=== Memory Monitor for: ${TEST_CMD} ===${NC}"
echo ""

# Get initial memory state
initial_mem=0
if command -v free > /dev/null 2>&1; then
  initial_mem=$(free -m 2> /dev/null | awk '/^Mem:/ {print $3}' || echo "0")
fi

echo -e "${BLUE}Initial system memory in use: ${initial_mem} MB${NC}"
echo ""

# Start the test command in background and capture PID
# Use bash -c to properly execute commands with spaces/arguments
bash -c "$TEST_CMD" &
TEST_PID=$!

# Wait a moment for process to start
sleep 0.5

# Monitor memory usage (runs until process finishes)
monitor_tree_memory "$TEST_PID" &

# Store monitor PID for cleanup
MONITOR_PID=$!

# Wait for process to finish
wait "$TEST_PID" || true
EXIT_CODE=$?

# Wait a moment for monitor to catch up
sleep 0.5

# Stop monitor if still running
kill "$MONITOR_PID" 2> /dev/null || true
wait "$MONITOR_PID" 2> /dev/null || true

# Get final memory state
final_mem=0
if command -v free > /dev/null 2>&1; then
  final_mem=$(free -m 2> /dev/null | awk '/^Mem:/ {print $3}' || echo "0")
fi

mem_diff=$((final_mem - initial_mem))

echo -e "${BLUE}=== Memory Usage Summary ===${NC}"
echo -e "Peak memory usage: ${GREEN}${MAX_MEMORY} MB${NC}"
echo -e "Initial system memory: ${initial_mem} MB"
echo -e "Final system memory: ${final_mem} MB"
if [ "$mem_diff" -gt 0 ]; then
  echo -e "System memory delta: ${GREEN}+${mem_diff}${NC} MB"
elif [ "$mem_diff" -lt 0 ]; then
  echo -e "System memory delta: ${RED}${mem_diff}${NC} MB"
else
  echo -e "System memory delta: 0 MB"
fi
echo ""

# Also use /usr/bin/time if available for additional metrics
if command -v /usr/bin/time > /dev/null 2>&1; then
  echo -e "${BLUE}=== Detailed Timing & Memory (using time command) ===${NC}"
  echo ""
  /usr/bin/time -v bash -c "$TEST_CMD" 2>&1 | grep -E "(Maximum resident|User time|System time|Elapsed)" || true
  echo ""
fi

# Exit with the same code as the test command
exit $EXIT_CODE
