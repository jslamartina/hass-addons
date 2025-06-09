#!/usr/bin/with-contenv bashio
# shellcheck shell=bash
LP='[run.sh]'

bashio::log.info "${LP} Starting CyncLAN (nCync) Add-On"
# pull values from the add-on configuration
export CYNC_ACCOUNT_USERNAME="$(bashio::config 'account_username')"
export CYNC_ACCOUNT_PASSWORD="$(bashio::config 'account_password')"
export CYNC_TOPIC="$(bashio::config 'mqtt_topic')"
export CYNC_DEBUG="$(bashio::config 'debug_log_level')"
export CYNC_MQTT_HOST="$(bashio::config 'mqtt_host')"
export CYNC_MQTT_PORT="$(bashio::config 'mqtt_port')"
export CYNC_MQTT_USER="$(bashio::config 'mqtt_user')"
export CYNC_MQTT_PASS="$(bashio::config 'mqtt_pass')"
export CYNC_TCP_WHITELIST="$(bashio::config 'fine_tune' | jq -r '.ip_whitelist | join(",")')"
export CYNC_CMD_BROADCASTS="$(bashio::config 'fine_tune' | jq -r '.command_targets | join(",")')"
export CYNC_MAX_TCP_CONN="$(bashio::config 'fine_tune' | jq -r '.max_clients | join(",")')"


if bashio::services.available mqtt ; then
  export CYNC_MQTT_HOST="$(bashio::services mqtt 'host')"
  export CYNC_MQTT_PORT="$(bashio::services mqtt 'port')"
  export CYNC_MQTT_USER="$(bashio::services mqtt 'username')"
  export CYNC_MQTT_PASS="$(bashio::services mqtt 'password')"
else
  bashio::log.error "HASS MQTT service not available using 'bashio::services.available mqtt'"
fi

# when installing the cync_lan python package, pyproject.toml creates a cync-lan executable
# default is to not run the export server, we want it in the add-on
cync-lan --enable-export