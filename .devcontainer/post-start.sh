#!/bin/bash
set -e

echo "========================================="
echo "Starting Post-Start Configuration"
echo "========================================="

# Step 1: Run devcontainer bootstrap
echo "Running devcontainer bootstrap..."
bash /usr/bin/devcontainer_bootstrap

# Step 2: Start Docker service
echo "Starting Docker service..."
sudo service docker start

# Step 3: Wait for Docker to be ready
echo "Waiting for Docker to be ready..."
until docker info > /dev/null 2>&1; do
  echo "  Still waiting for Docker..."
  sleep 2
done
echo "Docker is ready!"

# Step 4: Pin Docker CLI version (if not already present)
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

# Step 5: Start Home Assistant Supervisor
echo "Starting Home Assistant Supervisor..."
sudo script -q -c 'sudo supervisor_run' /tmp/supervisor_run.log &

# Step 6: Wait for Supervisor to be ready
echo "Waiting for Supervisor to be ready..."
sleep 5
until ha supervisor info 2> /dev/null; do
  echo "  Still waiting for Supervisor..."
  sleep 2
done
echo "Supervisor is ready!"

# Step 6b: Wait for all essential supervisor services to be running
echo "Waiting for all supervisor services to be ready..."

echo "  Checking DNS..."
until docker ps --filter "name=hassio_dns" --format "{{.Names}}" | grep -q hassio_dns; do
  echo "    Still waiting for DNS..."
  sleep 2
done

echo "  Checking Audio..."
until docker ps --filter "name=hassio_audio" --format "{{.Names}}" | grep -q hassio_audio; do
  echo "    Still waiting for Audio..."
  sleep 2
done

echo "  Checking Multicast..."
until docker ps --filter "name=hassio_multicast" --format "{{.Names}}" | grep -q hassio_multicast; do
  echo "    Still waiting for Multicast..."
  sleep 2
done

echo "  Checking Observer..."
until docker ps --filter "name=hassio_observer" --format "{{.Names}}" | grep -q hassio_observer; do
  echo "    Still waiting for Observer..."
  sleep 2
done

echo "  Checking CLI..."
until docker ps --filter "name=hassio_cli" --format "{{.Names}}" | grep -q hassio_cli; do
  echo "    Still waiting for CLI..."
  sleep 2
done

echo "All supervisor services are running!"

# Step 6c: Wait for Home Assistant Core to be fully running
echo "Waiting for Home Assistant Core to be fully running..."
until ha core info 2> /dev/null | jq -e '.data.state == "running"' > /dev/null 2>&1; do
  echo "  Still waiting for Home Assistant Core..."
  sleep 2
done
echo "Home Assistant Core is running!"

# Step 7: Install addons (if not already installed)
echo "Checking CyncLAN addon..."
if ha addon info local_cync-lan 2> /dev/null | jq -e '.data.installed == true' > /dev/null 2>&1; then
  echo "  CyncLAN addon already installed, skipping..."
else
  echo "  Installing CyncLAN addon..."
  ha addon install local_cync-lan || echo "  WARNING: CyncLAN addon installation failed"
fi

echo "Checking EMQX addon..."
if ha addon info a0d7b954_emqx 2> /dev/null | jq -e '.data.installed == true' > /dev/null 2>&1; then
  echo "  EMQX addon already installed, skipping..."
else
  echo "  Installing EMQX addon..."
  ha store addon install a0d7b954_emqx || echo "  WARNING: EMQX addon installation failed"
fi

# Step 8: Configure EMQX addon environment variables via Supervisor API
echo "Configuring EMQX addon..."

echo "  Extracting API token..."
TOKEN=$(ha --log-level debug addons info a0d7b954_emqx 2>&1 | grep -oP 'apiToken=\K[^ ]+')

if [ -z "$TOKEN" ]; then
  echo "  WARNING: Failed to extract API token, skipping EMQX configuration"
else
  echo "  Updating EMQX options via Supervisor API..."
  RESPONSE=$(curl -s -X POST \
    -H "Authorization: Bearer ${TOKEN}" \
    -H "Content-Type: application/json" \
    -d '{
      "options": {
        "env_vars": [
          {"name": "EMQX_NODE__COOKIE", "value": "localhost"},
          {"name": "EMQX_NODE__NAME", "value": "emqx@localhost"},
          {"name": "EMQX_HOST", "value": "localhost"},
          {"name": "EMQX_NAME", "value": "emqx"}
        ]
      }
    }' \
    http://supervisor/addons/a0d7b954_emqx/options)

  if echo "$RESPONSE" | jq -e '.result == "ok"' > /dev/null 2>&1; then
    echo "  ✅ EMQX configuration updated successfully!"
  else
    echo "  ⚠️  EMQX configuration may have failed:"
    echo "$RESPONSE" | jq '.'
  fi

  # Step 9: Configure CyncLAN addon options via Supervisor API
  echo "Configuring CyncLAN addon..."
  echo "  Updating CyncLAN options via Supervisor API..."
  CYNC_RESPONSE=$(curl -s -X POST \
    -H "Authorization: Bearer ${TOKEN}" \
    -H "Content-Type: application/json" \
    -d '{
      "options": {
        "account_username": "jslamartina@gmail.com",
        "account_password": "your_password_here",
        "debug_log_level": true,
        "mqtt_host": "localhost",
        "mqtt_port": 1883,
        "mqtt_user": "dev",
        "mqtt_pass": "dev",
        "mqtt_topic": "cync_lan_addon",
        "tuning": {
          "tcp_whitelist": "",
          "command_targets": 2,
          "max_clients": 8
        }
      }
    }' \
    http://supervisor/addons/local_cync-lan/options)

  if echo "$CYNC_RESPONSE" | jq -e '.result == "ok"' > /dev/null 2>&1; then
    echo "  ✅ CyncLAN configuration updated successfully!"
  else
    echo "  ⚠️  CyncLAN configuration may have failed:"
    echo "$CYNC_RESPONSE" | jq '.'
  fi

  # Start addons via API (non-blocking)
  echo "Starting addons..."

  echo "  Starting EMQX addon..."
  curl -s -X POST \
    -H "Authorization: Bearer ${TOKEN}" \
    http://supervisor/addons/a0d7b954_emqx/start > /dev/null
  echo "  EMQX addon start triggered"

  echo "  Starting CyncLAN addon..."
  curl -s -X POST \
    -H "Authorization: Bearer ${TOKEN}" \
    http://supervisor/addons/local_cync-lan/start > /dev/null
  echo "  CyncLAN addon start triggered"
fi

# Step 10: Add shell aliases
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

echo "========================================="
echo "Post-Start Configuration Complete!"
echo "========================================="
