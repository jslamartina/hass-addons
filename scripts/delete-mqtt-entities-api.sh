#!/usr/bin/env bash
#
# Permanently delete MQTT entities using Home Assistant API
#
# This script:
# 1. Finds all MQTT entities (except bridge)
# 2. Deletes them from the entity registry via API
# 3. Optionally restarts the addon
#
# Usage:
#   ./scripts/delete-mqtt-entities-api.sh [--restart]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_ROOT="$(dirname "$SCRIPT_DIR")"

# Configuration
BRIDGE_PATTERN="${BRIDGE_PATTERN:-CyncLAN Bridge}"
RESTART_ADDON="${1:-false}"
if [ "$1" = "--restart" ]; then
  RESTART_ADDON="true"
fi

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "╔═══════════════════════════════════════════════════════════════════════╗"
echo "║       Permanently Delete MQTT Entities (API Method)                 ║"
echo "╚═══════════════════════════════════════════════════════════════════════╝"
echo ""

# Get all entities from Home Assistant
echo "🔍 Fetching all entities from Home Assistant..."
ALL_ENTITIES=$(curl -s -H "Authorization: Bearer ${SUPERVISOR_TOKEN}" \
  http://supervisor/core/api/states | jq -r '.[].entity_id')

# Filter for MQTT entities (platform = mqtt)
echo "🔍 Identifying MQTT entities..."
MQTT_ENTITIES=()
BRIDGE_ENTITIES=()

while IFS= read -r entity_id; do
  if [ -z "$entity_id" ]; then
    continue
  fi

  # Get entity details
  ENTITY_INFO=$(curl -s -H "Authorization: Bearer ${SUPERVISOR_TOKEN}" \
    "http://supervisor/core/api/states/${entity_id}")

  # Check if it's an MQTT entity
  PLATFORM=$(echo "$ENTITY_INFO" | jq -r '.attributes.device_class // empty')
  FRIENDLY_NAME=$(echo "$ENTITY_INFO" | jq -r '.attributes.friendly_name // empty')

  # Check if entity ID or friendly name contains mqtt-related info
  if echo "$entity_id" | grep -qi "mqtt" || echo "$FRIENDLY_NAME" | grep -qi "$BRIDGE_PATTERN"; then
    if echo "$FRIENDLY_NAME" | grep -qi "$BRIDGE_PATTERN"; then
      BRIDGE_ENTITIES+=("$entity_id")
      echo -e "${GREEN}✅ PRESERVE: $FRIENDLY_NAME ($entity_id)${NC}"
    else
      MQTT_ENTITIES+=("$entity_id")
      echo -e "${RED}❌ DELETE: $FRIENDLY_NAME ($entity_id)${NC}"
    fi
  fi
done <<< "$ALL_ENTITIES"

echo ""
echo "═════════════════ SUMMARY ═════════════════"
echo "Total MQTT entities found: $((${#MQTT_ENTITIES[@]} + ${#BRIDGE_ENTITIES[@]}))"
echo -e "${GREEN}✅ To preserve (bridge): ${#BRIDGE_ENTITIES[@]}${NC}"
echo -e "${RED}❌ To delete: ${#MQTT_ENTITIES[@]}${NC}"
echo "═════════════════════════════════════════════"
echo ""

if [ ${#MQTT_ENTITIES[@]} -eq 0 ]; then
  echo "⚠️  No MQTT entities to delete"
  exit 0
fi

read -p "⚠️  Delete ${#MQTT_ENTITIES[@]} entities? (y/N): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
  echo "❌ Aborted"
  exit 1
fi

echo ""
echo "🗑️  Deleting entities from registry..."

DELETED_COUNT=0
for entity_id in "${MQTT_ENTITIES[@]}"; do
  echo "   Deleting: $entity_id"

  # Delete via entity registry API
  RESPONSE=$(curl -s -w "\n%{http_code}" -X DELETE \
    -H "Authorization: Bearer ${SUPERVISOR_TOKEN}" \
    -H "Content-Type: application/json" \
    "http://supervisor/core/api/config/entity_registry/${entity_id}" 2>&1)

  HTTP_CODE=$(echo "$RESPONSE" | tail -n1)

  if [ "$HTTP_CODE" = "200" ] || [ "$HTTP_CODE" = "204" ]; then
    DELETED_COUNT=$((DELETED_COUNT + 1))
    echo -e "     ${GREEN}✅ Deleted${NC}"
  else
    echo -e "     ${YELLOW}⚠️  Failed (HTTP $HTTP_CODE)${NC}"
  fi
done

echo ""
echo "═════════════════════════════════════════════"
echo -e "${GREEN}✅ Successfully deleted: $DELETED_COUNT entities${NC}"
echo "═════════════════════════════════════════════"

if [ "$RESTART_ADDON" = "true" ]; then
  echo ""
  echo "🔄 Restarting addon: local_cync-lan"
  ha addons restart local_cync-lan
  echo "✅ Addon restarted"
fi

echo ""
echo "✅ Permanent deletion complete!"
