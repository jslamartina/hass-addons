#!/usr/bin/env bash
#
# 99-enable-journald-logs.sh
#
# Enables journald logging for Home Assistant add-ons in devcontainer
# This allows the Supervisor to retrieve logs for display on add-on log pages
#
set -e

LP="[enable-journald-logs]"

echo "$LP Enabling journald logging support for add-on logs..."

# Step 1: Install systemd-journal-remote (provides journal-gatewayd)
echo "$LP Installing systemd-journal-remote..."
sudo apt-get update -qq
sudo apt-get install -y systemd-journal-remote

# Step 2: Configure Docker to use journald logging driver
echo "$LP Configuring Docker daemon to use journald logging..."
DOCKER_CONFIG="/etc/docker/daemon.json"

# Create or update daemon.json with journald logging
if [ -f "$DOCKER_CONFIG" ]; then
  echo "$LP Backing up existing $DOCKER_CONFIG..."
  sudo cp "$DOCKER_CONFIG" "${DOCKER_CONFIG}.bak"
fi

# Merge with existing config or create new one
sudo tee "$DOCKER_CONFIG" > /dev/null << 'EOF'
{
    "log-driver": "journald",
    "storage-driver": "overlay2"
}
EOF

echo "$LP Docker configuration updated:"
cat "$DOCKER_CONFIG"

# Step 3: Restart Docker service to apply changes
echo "$LP Restarting Docker service..."
sudo systemctl restart docker

# Wait for Docker to be ready
echo "$LP Waiting for Docker to be ready..."
sleep 5

# Verify Docker is running
if sudo systemctl is-active --quiet docker; then
  echo "$LP ✅ Docker service is running with journald logging enabled"
else
  echo "$LP ❌ ERROR: Docker service failed to start"
  exit 1
fi

# Step 4: Verify journald is accessible
if command -v journalctl &> /dev/null; then
  echo "$LP ✅ journalctl is available"
else
  echo "$LP ⚠️  WARNING: journalctl command not found"
fi

# Step 5: Start systemd-journal-gatewayd for Supervisor log access
echo "$LP Starting systemd-journal-gatewayd on port 19531..."
if pgrep -f systemd-journal-gatewayd > /dev/null; then
  echo "$LP ✅ systemd-journal-gatewayd is already running"
  echo "$LP    Supervisor can fetch logs at http://172.17.0.2:19531"
else
  # Use systemd-socket-activate to simulate systemd socket activation
  # This is required since systemd is not running in the devcontainer
  nohup systemd-socket-activate -l 19531 /lib/systemd/systemd-journal-gatewayd > /tmp/journal-gatewayd.log 2>&1 &
  sleep 2

  # Verify it's listening on port 19531
  if netstat -tln 2> /dev/null | grep -q ":19531" || ss -tln 2> /dev/null | grep -q ":19531"; then
    echo "$LP ✅ systemd-journal-gatewayd started successfully"
    echo "$LP    Listening on http://172.17.0.2:19531"
    echo "$LP    Supervisor can now fetch logs from this endpoint"
  else
    echo "$LP ⚠️  WARNING: Failed to start systemd-journal-gatewayd"
    echo "$LP    Check /tmp/journal-gatewayd.log for errors"
    cat /tmp/journal-gatewayd.log
    exit 1
  fi
fi

echo "$LP ✅ Setup complete!"
echo "$LP"
echo "$LP Next steps:"
echo "$LP   1. Restart the devcontainer to rebuild containers with journald logging"
echo "$LP   2. Or restart Home Assistant Supervisor: ha supervisor restart"
echo "$LP   3. Check add-on logs at: http://localhost:8123/hassio/addon/local_cync-controller/logs"
echo "$LP   4. Or use CLI: ha addons logs local_cync-controller"
