#!/usr/bin/env bash
#
# Clear MQTT discovery messages for all Cync entities
#
# This sends empty retained messages to all MQTT discovery topics,
# telling Home Assistant to remove the entities completely.
#
# Usage:
#   ./scripts/clear-mqtt-discovery.sh

set -e

echo "╔═══════════════════════════════════════════════════════════════════════╗"
echo "║          Clear MQTT Discovery Messages (Nuclear Option)             ║"
echo "╚═══════════════════════════════════════════════════════════════════════╝"
echo ""

# MQTT broker details (from addon)
MQTT_HOST="${MQTT_HOST:-core-mosquitto}"
MQTT_PORT="${MQTT_PORT:-1883}"
MQTT_USER="${MQTT_USER:-}"
MQTT_PASS="${MQTT_PASS:-}"

# Home Assistant MQTT discovery prefix
HA_DISCOVERY_PREFIX="homeassistant"

echo "This will send empty (delete) messages to ALL MQTT discovery topics"
echo "for Cync devices. This forces Home Assistant to forget everything."
echo ""
read -p "Continue? (y/N): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
  echo "❌ Aborted"
  exit 1
fi

echo ""
echo "🗑️  Clearing MQTT discovery topics..."

# Build mosquitto_pub auth args
AUTH_ARGS=""
if [ -n "$MQTT_USER" ]; then
  AUTH_ARGS="-u $MQTT_USER -P $MQTT_PASS"
fi

# Clear all homeassistant/+/cync_lan_* topics (device entities)
echo "   Clearing device entity topics..."
mosquitto_pub -h "$MQTT_HOST" -p "$MQTT_PORT" $AUTH_ARGS \
  -t "${HA_DISCOVERY_PREFIX}/light/+/config" \
  -n -r 2> /dev/null || true

mosquitto_pub -h "$MQTT_HOST" -p "$MQTT_PORT" $AUTH_ARGS \
  -t "${HA_DISCOVERY_PREFIX}/switch/+/config" \
  -n -r 2> /dev/null || true

mosquitto_pub -h "$MQTT_HOST" -p "$MQTT_PORT" $AUTH_ARGS \
  -t "${HA_DISCOVERY_PREFIX}/fan/+/config" \
  -n -r 2> /dev/null || true

# Clear bridge entity topics
echo "   Clearing bridge entity topics..."
for entity_type in button binary_sensor sensor number; do
  mosquitto_pub -h "$MQTT_HOST" -p "$MQTT_PORT" $AUTH_ARGS \
    -t "${HA_DISCOVERY_PREFIX}/${entity_type}/+/config" \
    -n -r 2> /dev/null || true
done

echo ""
echo "✅ MQTT discovery topics cleared!"
echo ""
echo "⚠️  IMPORTANT: Now delete from registries and restart:"
echo ""
echo "1. Delete from registries:"
echo "   sudo python3 scripts/delete-mqtt-completely.py"
echo ""
echo "2. Restart Home Assistant:"
echo "   ha core restart"
echo ""
echo "3. Start addon (entities will be fresh):"
echo "   ha addons start local_cync-lan"
echo ""
