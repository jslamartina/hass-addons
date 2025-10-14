#!/bin/bash
# GUI Test Automation Helper
# Monitors system while human performs GUI tests

echo "╔══════════════════════════════════════════════════════════════════╗"
echo "║     GUI Test Monitoring - Running Automated Checks              ║"
echo "╚══════════════════════════════════════════════════════════════════╝"
echo ""

# Check 1: Verify addon running
echo "🔍 Check 1: Addon Status"
ADDON_STATE=$(ha addons info local_cync-lan --raw-json | jq -r '.data.state')
if [ "$ADDON_STATE" = "started" ]; then
  echo "   ✅ Addon running: $ADDON_STATE"
else
  echo "   ❌ Addon not running: $ADDON_STATE"
fi
echo ""

# Check 2: Count connected devices
echo "🔍 Check 2: Device Connections"
DEVICE_COUNT=$(ha addons logs local_cync-lan -n 200 | grep "Device endpoint" | wc -l)
echo "   ℹ️  Devices connected via relay: $DEVICE_COUNT"
echo ""

# Check 3: Verify cloud relay active
echo "🔍 Check 3: Cloud Relay Status"
RELAY_CONNECTIONS=$(ha addons logs local_cync-lan -n 100 | grep "RELAY mode" | wc -l)
if [ "$RELAY_CONNECTIONS" -gt 0 ]; then
  echo "   ✅ Cloud relay active: $RELAY_CONNECTIONS connections"
else
  echo "   ⚠️  No recent relay connections"
fi
echo ""

# Check 4: Recent MQTT activity
echo "🔍 Check 4: MQTT Activity"
MQTT_PUBLISHES=$(ha addons logs local_cync-lan -n 300 | grep "device_status" | wc -l)
echo "   ℹ️  Recent MQTT publishes: $MQTT_PUBLISHES"
echo ""

# Check 5: Error count
echo "🔍 Check 5: Error Analysis"
ERROR_COUNT=$(ha addons logs local_cync-lan -n 500 | grep -i "ERROR" | grep -v "uvicorn" | wc -l)
if [ "$ERROR_COUNT" -eq 0 ]; then
  echo "   ✅ No errors detected"
else
  echo "   ⚠️  Errors found: $ERROR_COUNT (reviewing...)"
  ha addons logs local_cync-lan -n 500 | grep -i "ERROR" | grep -v "uvicorn" | tail -3
fi
echo ""

# Check 6: Performance metrics
echo "🔍 Check 6: Performance Metrics"
HEARTBEATS=$(ha addons logs local_cync-lan -n 200 | grep "HEARTBEAT" | wc -l)
echo "   ℹ️  Heartbeat packets (keepalives): $HEARTBEATS"
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Automated checks complete!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📊 SUMMARY:"
echo "   Addon State:        $ADDON_STATE"
echo "   Relay Connections:  $RELAY_CONNECTIONS"
echo "   MQTT Publishes:     $MQTT_PUBLISHES"
echo "   Errors:             $ERROR_COUNT"
echo ""

# Live log monitoring option
echo "To monitor logs in real-time during GUI testing:"
echo "  → ha addons logs local_cync-lan -f"
echo ""
echo "To filter for specific activity:"
echo "  → ha addons logs local_cync-lan -f | grep -E 'RELAY|0x73|0x83'"
echo ""
