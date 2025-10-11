#!/usr/bin/with-contenv bashio
# shellcheck shell=bash
LP='[run.sh]'

bashio::log.info "${LP} Starting CyncLAN Bridge Add-On"
# pull values from the add-on configuration
CYNC_ACCOUNT_USERNAME="$(bashio::config 'account_username')"
CYNC_ACCOUNT_PASSWORD="$(bashio::config 'account_password')"
CYNC_TOPIC="$(bashio::config 'mqtt_topic')"
CYNC_DEBUG="$(bashio::config 'debug_log_level')"
CYNC_MQTT_HOST="$(bashio::config 'mqtt_host')"
CYNC_MQTT_PORT="$(bashio::config 'mqtt_port')"
CYNC_MQTT_USER="$(bashio::config 'mqtt_user')"
CYNC_MQTT_PASS="$(bashio::config 'mqtt_pass')"
CYNC_TCP_WHITELIST="$(bashio::config 'tuning' | jq -r '.tcp_whitelist')"
CYNC_CMD_BROADCASTS="$(bashio::config 'tuning' | jq -r '.command_targets')"
CYNC_MAX_TCP_CONN="$(bashio::config 'tuning' | jq -r '.max_clients')"
CYNC_CLOUD_RELAY_ENABLED="$(bashio::config 'cloud_relay' | jq -r '.enabled')"
CYNC_CLOUD_FORWARD="$(bashio::config 'cloud_relay' | jq -r '.forward_to_cloud')"
CYNC_CLOUD_SERVER="$(bashio::config 'cloud_relay' | jq -r '.cloud_server')"
CYNC_CLOUD_PORT="$(bashio::config 'cloud_relay' | jq -r '.cloud_port')"
CYNC_CLOUD_DEBUG_LOGGING="$(bashio::config 'cloud_relay' | jq -r '.debug_packet_logging')"
CYNC_CLOUD_DISABLE_SSL_VERIFY="$(bashio::config 'cloud_relay' | jq -r '.disable_ssl_verification')"
export CYNC_ACCOUNT_USERNAME CYNC_ACCOUNT_PASSWORD CYNC_TOPIC CYNC_DEBUG CYNC_MQTT_HOST CYNC_MQTT_PORT CYNC_MQTT_USER CYNC_MQTT_PASS CYNC_TCP_WHITELIST CYNC_CMD_BROADCASTS CYNC_MAX_TCP_CONN
export CYNC_CLOUD_RELAY_ENABLED CYNC_CLOUD_FORWARD CYNC_CLOUD_SERVER CYNC_CLOUD_PORT CYNC_CLOUD_DEBUG_LOGGING CYNC_CLOUD_DISABLE_SSL_VERIFY

# when installing the cync_lan python package, pyproject.toml creates a cync-lan executable
#cync-lan --enable-export
# for some wierd reason, the cync-lan executable does not work in the add-on container all of a sudden
python -c "from cync_lan.main import main; main()" --enable-export
