#!/usr/bin/with-contenv bashio
# shellcheck shell=bash
LP='[run.sh]'

bashio::log.info "${LP} Starting CyncLAN Bridge Add-On"
# pull values from the add-on configuration
export CYNC_ACCOUNT_USERNAME="$(bashio::config 'account_username')"
export CYNC_ACCOUNT_PASSWORD="$(bashio::config 'account_password')"
export CYNC_TOPIC="$(bashio::config 'mqtt_topic')"
export CYNC_DEBUG="$(bashio::config 'debug_log_level')"
export CYNC_MQTT_HOST="$(bashio::config 'mqtt_host')"
export CYNC_MQTT_PORT="$(bashio::config 'mqtt_port')"
export CYNC_MQTT_USER="$(bashio::config 'mqtt_user')"
export CYNC_MQTT_PASS="$(bashio::config 'mqtt_pass')"
export CYNC_TCP_WHITELIST="$(bashio::config 'tuning' | jq -r '.tcp_whitelist')"
export CYNC_CMD_BROADCASTS="$(bashio::config 'tuning' | jq -r '.command_targets')"
export CYNC_MAX_TCP_CONN="$(bashio::config 'tuning' | jq -r '.max_clients')"

# when installing the cync_lan python package, pyproject.toml creates a cync-lan executable
#cync-lan --enable-export
# for some wierd reason, the cync-lan executable does not work in the add-on container all of a sudden
python -c "from cync_lan.main import main; main()" --enable-export
