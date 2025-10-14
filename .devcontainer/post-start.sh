#!/bin/bash
set -e

echo "========================================="
echo "Starting Post-Start Configuration"
echo "========================================="

# Run devcontainer bootstrap
echo "Running devcontainer bootstrap..."
bash /usr/bin/devcontainer_bootstrap

# Note: supervisor_run will start Docker itself, so we skip that step here

# Step 4: Start Home Assistant Supervisor (this will start Docker internally)
echo "Starting Home Assistant Supervisor..."
# Start supervisor_run with script to provide TTY, logs to file only (no console output)
sudo script -qefc 'sudo supervisor_run' /tmp/supervisor_run.log > /dev/null 2>&1 &
# Tail the log file and filter out DEBUG lines for console display
sleep 1
tail -f /tmp/supervisor_run.log 2> /dev/null | grep --line-buffered -v "DEBUG" &

echo "Waiting for Supervisor to be ready..."
sleep 5
RETRY_DELAY=1
MAX_DELAY=30
until ha supervisor info 2> /dev/null; do
  echo "  Still waiting for Supervisor... (sleep ${RETRY_DELAY}s)"
  sleep $RETRY_DELAY
  RETRY_DELAY=$((RETRY_DELAY * 2))
  [ $RETRY_DELAY -gt $MAX_DELAY ] && RETRY_DELAY=$MAX_DELAY
done
echo "Supervisor is ready!"

# Step 5: Pin Docker CLI version (now that Docker is running from supervisor_run)
echo "Checking Docker CLI version..."
DOCKER_VERSION=$(docker version --format '{{.Server.Version}}' 2> /dev/null || echo '0.0.0')
DOCKER_MAJOR=$(echo "$DOCKER_VERSION" | cut -d. -f1)

echo "  Docker version: ${DOCKER_VERSION} (major: ${DOCKER_MAJOR})"

if [ "$DOCKER_MAJOR" != "0" ]; then
  # Check if the specific version CLI image already exists
  if docker image inspect "docker:${DOCKER_VERSION}-cli" > /dev/null 2>&1; then
    echo "  docker:${DOCKER_VERSION}-cli already exists, skipping..."
  else
    echo "  Pulling docker:${DOCKER_MAJOR}-cli..."
    docker pull "docker:${DOCKER_MAJOR}-cli"

    echo "  Tagging as docker:${DOCKER_VERSION}-cli..."
    docker tag "docker:${DOCKER_MAJOR}-cli" "docker:${DOCKER_VERSION}-cli"

    echo "  Successfully tagged docker:${DOCKER_VERSION}-cli"
  fi
else
  echo "  WARNING: Failed to get docker version"
fi

# Step 6: Extract API token (with retry logic)
echo "Extracting API token..."
TOKEN=""
RETRY_COUNT=0
MAX_RETRIES=10

RETRY_DELAY=1
MAX_DELAY=30
while [ -z "$TOKEN" ] && [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
  TOKEN=$(ha --log-level debug supervisor info 2>&1 | grep -oP 'apiToken=\K[^ ]+' || echo "")

  if [ -z "$TOKEN" ]; then
    RETRY_COUNT=$((RETRY_COUNT + 1))
    echo "  Token extraction attempt $RETRY_COUNT/$MAX_RETRIES failed, retrying in ${RETRY_DELAY}s..."
    sleep $RETRY_DELAY
    RETRY_DELAY=$((RETRY_DELAY * 2))
    [ $RETRY_DELAY -gt $MAX_DELAY ] && RETRY_DELAY=$MAX_DELAY
  fi
done

if [ -z "$TOKEN" ]; then
  echo "  ERROR: Failed to extract API token after $MAX_RETRIES attempts"
  echo "  Cannot use jobs API without authentication token"
  exit 1
fi

echo "  Token extracted successfully!"

# Step 7: Wait for all supervisor components to be ready
echo "Waiting for all supervisor components to be ready..."
MAX_WAIT_SECONDS=240
TOTAL_WAIT=0
WAIT_COUNT=0

# Critical components that must be ready before proceeding
COMPONENTS=("core" "audio" "dns" "cli" "observer" "multicast")

WAIT_INTERVAL=2
while [ $TOTAL_WAIT -lt $MAX_WAIT_SECONDS ]; do
  ALL_READY=true
  SUPERVISOR_HEALTHY=$(curl -s -H "Authorization: Bearer ${TOKEN}" http://supervisor/supervisor/info | jq -r '.data.healthy' 2> /dev/null || echo "false")

  echo "  Supervisor healthy: $SUPERVISOR_HEALTHY"

  # Check each component
  for component in "${COMPONENTS[@]}"; do
    VERSION=$(curl -s -H "Authorization: Bearer ${TOKEN}" "http://supervisor/${component}/info" | jq -r '.data.version' 2> /dev/null || echo "null")

    if [ "$VERSION" = "null" ] || [ -z "$VERSION" ]; then
      echo "    ❌ $component: Not ready"
      ALL_READY=false
    else
      echo "    ✅ $component: Ready (v$VERSION)"
    fi
  done

  # All components ready and supervisor healthy means initialization is complete
  if [ "$ALL_READY" = "true" ] && [ "$SUPERVISOR_HEALTHY" = "true" ]; then
    echo "All supervisor components ready - initialization completed!"
    break
  fi

  WAIT_COUNT=$((WAIT_COUNT + 1))
  echo "  Waiting for remaining components... (sleep ${WAIT_INTERVAL}s)"

  sleep $WAIT_INTERVAL
  TOTAL_WAIT=$((TOTAL_WAIT + WAIT_INTERVAL))
done

if [ $TOTAL_WAIT -ge $MAX_WAIT_SECONDS ]; then
  echo "  WARNING: Timeout waiting for supervisor components after ${TOTAL_WAIT}s"
fi

# Step 8: Restore full backup (includes addons, configuration, and all data)
# COMMENTED OUT FOR TESTING: Start from fresh install instead of restoring backup
# echo "Restoring full backup..."
# BACKUP_FILE="/mnt/supervisor/addons/local/hass-addons/full_test_backup_20251004_005214.tar"
# BACKUP_DEST="/mnt/supervisor/backup/"
#
# if [ -f "$BACKUP_FILE" ]; then
#   echo "  Copying backup file to $BACKUP_DEST..."
#   sudo cp "$BACKUP_FILE" "$BACKUP_DEST"
#
#   echo "  Reloading backups..."
#   ha backups reload
#
#   echo "  Finding backup slug..."
#   # Find the backup by matching the backup name or by checksum
#   BACKUP_SLUG=$(ha backups --raw-json | jq -r '.data.backups[] | select(.name | contains("Full-Test-Backup")) | .slug' | head -1)
#
#   if [ -z "$BACKUP_SLUG" ]; then
#     # Fallback: find by matching file checksum
#     BACKUP_CHECKSUM=$(md5sum "$BACKUP_FILE" | cut -d' ' -f1)
#     for backup_file in /mnt/supervisor/backup/*.tar; do
#       if [ "$(md5sum "$backup_file" | cut -d' ' -f1)" = "$BACKUP_CHECKSUM" ]; then
#         BACKUP_SLUG=$(basename "$backup_file" .tar)
#         break
#       fi
#     done
#   fi
#
#   if [ -n "$BACKUP_SLUG" ]; then
#     echo "  ✅ Backup uploaded successfully! (slug: $BACKUP_SLUG)"
#
#     # Wait for Home Assistant core to be running (check if stats are available)
#     echo "  Waiting for Home Assistant core to be running..."
#     MAX_HA_WAIT=60
#     HA_WAIT_COUNT=0
#     while [ $HA_WAIT_COUNT -lt $MAX_HA_WAIT ]; do
#       if ha core stats --raw-json 2> /dev/null | jq -e '.result == "ok"' > /dev/null 2>&1; then
#         echo "    ✅ Home Assistant core is running"
#         break
#       else
#         echo "    ⏳ Home Assistant core not running yet..."
#         HA_WAIT_COUNT=$((HA_WAIT_COUNT + 1))
#         sleep 5
#       fi
#     done
#
#     if [ $HA_WAIT_COUNT -ge $MAX_HA_WAIT ]; then
#       echo "    ⚠️  Timeout waiting for HA core, attempting restore anyway..."
#     fi
#
#     # Wait for any running jobs to complete before restoring
#     echo "  Waiting for system to be idle before restore..."
#     MAX_JOB_WAIT=60
#     JOB_WAIT_COUNT=0
#     while [ $JOB_WAIT_COUNT -lt $MAX_JOB_WAIT ]; do
#       ACTIVE_JOBS=$(ha jobs info --raw-json | jq '[.data.jobs[] | select(.done == false)] | length')
#
#       if [ "$ACTIVE_JOBS" = "0" ]; then
#         echo "    ✅ System idle, ready to restore"
#         break
#       else
#         echo "    ⏳ Waiting for $ACTIVE_JOBS job(s) to complete..."
#         JOB_WAIT_COUNT=$((JOB_WAIT_COUNT + 1))
#         sleep 5
#       fi
#     done
#
#     if [ $JOB_WAIT_COUNT -ge $MAX_JOB_WAIT ]; then
#       echo "    ⚠️  Timeout waiting for jobs, attempting restore anyway..."
#     fi
#
#     echo "  Restoring backup (excluding addons/local folder to preserve dev environment)..."
#     # Get all folders from backup except addons/local and build flags
#     FOLDER_FLAGS=$(ha backups info "$BACKUP_SLUG" --raw-json | jq -r '.data.folders[] | select(. != "addons/local") | "--folders " + .' | tr '\n' ' ')
#     ADDON_FLAGS=$(ha backups info "$BACKUP_SLUG" --raw-json | jq -r '.data.addons[] | "--addons " + .slug' | tr '\n' ' ')
#
#     echo "    Restoring: Home Assistant core + addons + folders (excluding addons/local)"
#     ha backups restore "$BACKUP_SLUG" --homeassistant "$FOLDER_FLAGS" "$ADDON_FLAGS"
#     echo "  ✅ Backup restored successfully!"
#   else
#     echo "  ⚠️  Could not find backup slug after upload"
#   fi
# else
#   echo "  ⚠️  Backup file not found: $BACKUP_FILE"
# fi
echo "  ⚠️  Backup restore is DISABLED - starting from fresh install"

# Step 9: Add shell aliases
echo "Adding shell aliases..."
cat >> ~/.zshrc << 'EOF'

# CyncLAN addon helper aliases
alias clear-cync-logs='docker ps --filter "name=cync" --no-trunc --format "{{.ID}}" | xargs -I {} sudo truncate -s 0 /var/lib/docker/containers/{}/{}-json.log && echo "CyncLAN logs cleared"'
alias cync-logs='ha addon logs local_cync-lan'
alias cync-logs-follow='ha addon logs local_cync-lan --follow'
alias cync-restart='ha addon restart local_cync-lan'
alias cync-stop='ha addon stop local_cync-lan'
alias cync-start='ha addon start local_cync-lan'
EOF
echo "  Aliases added to ~/.zshrc"

# Step 10: Clean up old test results (older than 3 days)
echo "Cleaning up old test results..."
TEST_RESULTS_DIR="/mnt/supervisor/addons/local/hass-addons/test-results"
if [ -d "$TEST_RESULTS_DIR" ]; then
  echo "  Searching for test result folders older than 3 days..."

  # Find and remove folders older than 3 days in test-results/runs/
  find "$TEST_RESULTS_DIR/runs" -type d -mtime +3 -exec rm -rf {} \; 2> /dev/null || true

  # Find and remove folders older than 3 days in test-results/screenshots/
  find "$TEST_RESULTS_DIR/screenshots" -type f -mtime +3 -delete 2> /dev/null || true

  # Count remaining items
  REMAINING_RUNS=$(find "$TEST_RESULTS_DIR/runs" -mindepth 1 -maxdepth 1 -type d 2> /dev/null | wc -l)
  REMAINING_SCREENSHOTS=$(find "$TEST_RESULTS_DIR/screenshots" -type f 2> /dev/null | wc -l)

  echo "  ✅ Cleanup complete: $REMAINING_RUNS test run folders, $REMAINING_SCREENSHOTS screenshot files remaining"
else
  echo "  ⚠️  Test results directory not found: $TEST_RESULTS_DIR"
fi

echo "========================================="
echo "Post-Start Configuration Complete!"
echo "========================================="
