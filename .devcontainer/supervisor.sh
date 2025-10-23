#!/bin/bash
set -eE

SUPERVISOR_VERSION="$(curl -s https://version.home-assistant.io/dev.json | jq -e -r '.supervisor')"
DOCKER_TIMEOUT=30
DOCKER_PID=0

function start_docker() {
  local starttime
  local endtime

  if grep -q 'Alpine|standard-WSL' /proc/version; then
    # The docker daemon does not start when running WSL2 without adjusting iptables
    update-alternatives --set iptables /usr/sbin/iptables-legacy || echo "Fails adjust iptables"
    update-alternatives --set ip6tables /usr/sbin/iptables-legacy || echo "Fails adjust ip6tables"
  fi

  echo "Starting docker."
  dockerd 2> /dev/null &
  DOCKER_PID=$!

  echo "Waiting for docker to initialize..."
  starttime="$(date +%s)"
  endtime="$(date +%s)"
  until docker info > /dev/null 2>&1; do
    if [ $((endtime - starttime)) -le $DOCKER_TIMEOUT ]; then
      sleep 1
      endtime=$(date +%s)
    else
      echo "Timeout while waiting for docker to come up"
      exit 1
    fi
  done
  echo "Docker was initialized"
}

function stop_docker() {
  local starttime
  local endtime

  echo "Stopping in container docker..."
  if [ "$DOCKER_PID" -gt 0 ] && kill -0 "$DOCKER_PID" 2> /dev/null; then
    starttime="$(date +%s)"
    endtime="$(date +%s)"

    # Now wait for it to die
    kill "$DOCKER_PID"
    while kill -0 "$DOCKER_PID" 2> /dev/null; do
      if [ $((endtime - starttime)) -le $DOCKER_TIMEOUT ]; then
        sleep 1
        endtime=$(date +%s)
      else
        echo "Timeout while waiting for container docker to die"
        exit 1
      fi
    done
  else
    echo "Your host might have been left with unreleased resources"
  fi
}

function cleanup_lastboot() {
  if [[ -f /tmp/supervisor_data/config.json ]]; then
    echo "Cleaning up last boot"
    cp /tmp/supervisor_data/config.json /tmp/config.json
    jq -rM 'del(.last_boot)' /tmp/config.json > /tmp/supervisor_data/config.json
    rm /tmp/config.json
  fi
}

function cleanup_docker() {
  echo "Cleaning up stopped containers..."
  docker rm "$(docker ps -a -q)" || true
}

function run_supervisor() {
  mkdir -p /tmp/supervisor_data

  # Make /tmp/supervisor_data a shared mount for mount propagation
  # First bind mount it to itself to make it a mount point
  if ! mount | grep -q "/tmp/supervisor_data"; then
    mount --bind /tmp/supervisor_data /tmp/supervisor_data
    mount --make-shared /tmp/supervisor_data
    echo "Configured /tmp/supervisor_data as shared mount"
  fi

  # Get the devcontainer IP for journal gateway access
  # Use the first non-loopback IP from hostname -I
  DEVCONTAINER_IP=$(hostname -I | awk '{print $1}')
  echo "Using devcontainer IP for journal gateway: $DEVCONTAINER_IP"

  docker run --rm --privileged \
    --name hassio_supervisor \
    --privileged \
    --security-opt seccomp=unconfined \
    --security-opt apparmor=unconfined \
    -v /run/docker.sock:/run/docker.sock:rw \
    -v /run/dbus:/run/dbus:ro \
    -v /run/udev:/run/udev:ro \
    -v /tmp/supervisor_data:/data:rw,rshared \
    -v "$WORKSPACE_DIRECTORY":/data/addons/local:rw \
    -v /etc/machine-id:/etc/machine-id:ro \
    -e SUPERVISOR_SHARE="/tmp/supervisor_data" \
    -e SUPERVISOR_NAME=hassio_supervisor \
    -e SUPERVISOR_DEV=1 \
    -e SUPERVISOR_MACHINE="qemuarm-64" \
    -e SUPERVISOR_SYSTEMD_JOURNAL_GATEWAYD_URL="http://${DEVCONTAINER_IP}:19531" \
    "ghcr.io/home-assistant/aarch64-hassio-supervisor:${SUPERVISOR_VERSION}"
}

function init_dbus() {
  if pgrep dbus-daemon; then
    echo "Dbus is running"
    return 0
  fi

  echo "Startup dbus"
  mkdir -p /var/lib/dbus
  cp -f /etc/machine-id /var/lib/dbus/machine-id

  # cleanups
  mkdir -p /run/dbus
  rm -f /run/dbus/pid

  # run
  dbus-daemon --system --print-address
}

function init_udev() {
  if pgrep systemd-udevd; then
    echo "udev is running"
    return 0
  fi

  echo "Startup udev"

  # cleanups
  mkdir -p /run/udev

  # run
  /lib/systemd/systemd-udevd --daemon
  sleep 3
  udevadm trigger && udevadm settle
}

function start_journald() {
  if pgrep systemd-journald; then
    echo "journald is running"
    return 0
  fi

  echo "Starting systemd-journald..."

  # Create journal directory if it doesn't exist
  if ! [ -e /var/log/journal ]; then
    echo "Creating systemd-journald tmpfiles."
    systemd-tmpfiles --create --prefix /var/log/journal
  fi

  # Start journald
  /usr/lib/systemd/systemd-journald &
  sleep 2

  echo "journald started"
}

echo "Start Test-Env"

start_journald
start_docker
trap "stop_docker" ERR

docker system prune -f

cleanup_lastboot
cleanup_docker
init_dbus
init_udev
run_supervisor
stop_docker
