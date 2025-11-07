# Phase 8: GUI Validation & Human Interaction Testing

## Purpose

Validate end-user experience through Home Assistant GUI to ensure cloud relay mode doesn't break user-facing functionality and that real-time device control works correctly.

## Prerequisites

- Addon running in cloud relay mode (with forwarding enabled)
- At least one physical device powered on
- Home Assistant accessible at <http://localhost:8123>

## Test Categories

### 1. Device Control - Light Entities

#### Test 1.1: Basic On/Off Control

- [ ] Navigate to Home Assistant dashboard
- [ ] Locate a Cync light entity (e.g., "Hallway Floodlight 1")
- [ ] Click to turn OFF → Verify light physically turns off
- [ ] Click to turn ON → Verify light physically turns on
- [ ] Check entity state updates in real-time (no delay)
- [ ] Verify MQTT messages are sent (check logs)

### Test 1.2: Brightness Control

- [ ] Select a tunable light entity
- [ ] Open light control panel
- [ ] Drag brightness slider from 0% to 100%
- [ ] Verify physical light brightness changes smoothly
- [ ] Set brightness to 50% → Verify physical brightness matches
- [ ] Check entity attribute shows correct brightness value

**Test 1.3: Color Temperature Control** (for tunable white bulbs)

- [ ] Open light control panel
- [ ] Move color temperature slider (2000K to 7000K range)
- [ ] Verify physical light color changes (warm to cool)
- [ ] Set to 2000K (warm) → Verify warm white light
- [ ] Set to 7000K (cool) → Verify cool white light
- [ ] Check entity attribute shows correct color_temp value

### Expected Results

- Commands execute within 1-2 seconds
- Physical devices respond correctly
- GUI state matches physical state
- No errors in addon logs

---

### 2. Device Control - Switch Entities

#### Test 2.1: Switch Toggle

- [ ] Locate a Cync switch entity (e.g., "Master Bedroom Fan Switch")
- [ ] Toggle switch OFF → Verify connected device turns off
- [ ] Toggle switch ON → Verify connected device turns on
- [ ] Check entity state reflects toggle

### Test 2.2: Dimmer Switch Control

- [ ] Select a dimmer switch entity
- [ ] Adjust brightness slider
- [ ] Verify controlled lights dim/brighten
- [ ] Test multiple brightness levels

---

### 3. Bidirectional State Updates

#### Test 3.1: Physical Switch → GUI Update

- [ ] Physically toggle a wall switch or bulb
- [ ] Observe Home Assistant GUI (within 5 seconds)
- [ ] Verify entity state updates automatically
- [ ] Check timestamp of last update

### Test 3.2: Multi-Device Scenes

- [ ] Physically change multiple devices
- [ ] Verify all entity states update in GUI
- [ ] Check Developer Tools → States for real-time updates

### Expected Results for Command Verification

- Physical changes reflected in GUI within 3-5 seconds
- No manual refresh needed
- State updates appear in history

---

### 4. Entity Attributes & Information

#### Test 4.1: Device Information

- [ ] Select a device entity
- [ ] Click "Settings" or info icon
- [ ] Verify device attributes are correct:
  - Device name
  - Model information
  - Manufacturer (Savant)
  - Software version
  - Supported features
  - Connection status

### Test 4.2: Entity History

- [ ] Open entity history
- [ ] Verify state changes are logged
- [ ] Check timestamps are accurate
- [ ] Verify attribute changes appear (brightness, color_temp)

---

### 5. Addon Configuration UI

#### Test 5.1: Cloud Relay Configuration Visibility

- [ ] Navigate to Settings → Add-ons → Cync Controller
- [ ] Click "Configuration" tab
- [ ] Verify cloud_relay section appears
- [ ] Check all options are visible:
  - [ ] enabled (boolean toggle)
  - [ ] forward_to_cloud (boolean toggle)
  - [ ] cloud_server (text input)
  - [ ] cloud_port (number input)
  - [ ] debug_packet_logging (boolean toggle)
  - [ ] disable_ssl_verification (boolean toggle)

### Test 5.2: Configuration Changes via UI

- [ ] Toggle debug_packet_logging ON
- [ ] Click "Save"
- [ ] Click "Restart" addon
- [ ] Verify logs show debug packets after restart
- [ ] Toggle debug_packet_logging OFF
- [ ] Save and restart
- [ ] Verify debug packets no longer appear

### Test 5.3: Configuration Validation

- [ ] Try invalid cloud_server IP (e.g., "999.999.999.999")
- [ ] Verify validation error appears
- [ ] Try invalid cloud_port (e.g., 99999)
- [ ] Verify validation error or warning

---

### 6. Addon Management UI

#### Test 6.1: Addon Information Display

- [ ] Navigate to Settings → Add-ons → Cync Controller
- [ ] Verify "Info" tab shows:
  - [ ] Version: 0.0.4.0
  - [ ] State: Running
  - [ ] Network ports (23779, 23778)
  - [ ] Description mentions DNS requirement

### Test 6.2: Addon Logs Access

- [ ] Click "Logs" tab
- [ ] Verify logs are displayed
- [ ] Check "Follow" option works (auto-scroll)
- [ ] Verify cloud relay messages appear:
  - "New connection in RELAY mode"
  - "Connected to cloud server"
  - Device endpoint logs

### Test 6.3: Addon Control Buttons

- [ ] Test "Restart" button → Addon restarts successfully
- [ ] Test "Stop" button → Addon stops
- [ ] Test "Start" button → Addon starts
- [ ] Verify state changes in UI

**Test 6.4: Ingress Web UI** (Device Export)

- [ ] Click "Open Web UI" or ingress link
- [ ] Verify device export page loads
- [ ] Check if page is functional (even if not used during cloud relay)

---

### 7. Developer Tools Validation

#### Test 7.1: MQTT Message Inspection

- [ ] Navigate to Developer Tools → MQTT
- [ ] Subscribe to: `cync_lan_addon/#`
- [ ] Toggle a light
- [ ] Verify MQTT messages appear:
  - Command: `cync_lan_addon/set/<device>`
  - State: `cync_lan_addon/state/<device>`

### Test 7.2: Entity State Inspection

- [ ] Navigate to Developer Tools → States
- [ ] Filter for "cync" or "hallway"
- [ ] Verify all device entities appear
- [ ] Check attributes:
  - brightness (0-100)
  - color_temp (2000-7000 for tunable)
  - supported_features
  - device_class

### Test 7.3: Service Calls

- [ ] Navigate to Developer Tools → Services
- [ ] Select service: `light.turn_on`
- [ ] Select a Cync light entity
- [ ] Set brightness: 50
- [ ] Set color_temp: 3000
- [ ] Call service
- [ ] Verify light responds correctly

---

### 8. Error Scenarios & Edge Cases

#### Test 8.1: Device Unavailable

- [ ] Power off a physical device
- [ ] Wait 30 seconds
- [ ] Check if entity shows as "unavailable" in GUI
- [ ] Power device back on
- [ ] Verify entity becomes "available" again

### Test 8.2: Addon Restart During Control

- [ ] Start controlling a light (adjust brightness)
- [ ] Restart addon mid-operation
- [ ] Verify graceful handling (no crashes)
- [ ] Verify device reconnects after addon restart

### Test 8.3: Rapid Commands

- [ ] Rapidly toggle a light ON/OFF/ON/OFF (10 times quickly)
- [ ] Verify all commands are processed
- [ ] Check for command queue or rate limiting
- [ ] Verify no errors in logs

### Test 8.4: Multiple Simultaneous Commands

- [ ] Control 3-4 lights simultaneously
- [ ] Change brightness on all at once
- [ ] Verify all devices respond
- [ ] Check for any performance degradation

---

### 9. Relay Mode Specific Validations

#### Test 9.1: Cloud Relay Impact on Latency

- [ ] Measure response time with relay OFF (baseline)
- [ ] Toggle light 5 times, note average response time
- [ ] Enable cloud relay mode
- [ ] Toggle same light 5 times, note average response time
- [ ] Compare: relay mode should add minimal latency (<500ms)

### Test 9.2: LAN-only Mode Device Control

- [ ] Switch to LAN-only relay (forward_to_cloud: false)
- [ ] Attempt to control devices via GUI
- [ ] Expected: Limited functionality (devices need cloud responses)
- [ ] Verify graceful degradation (no crashes)

### Test 9.3: Debug Logging Impact

- [ ] Enable debug_packet_logging
- [ ] Control multiple devices
- [ ] Verify GUI remains responsive
- [ ] Check logs fill with packet data
- [ ] Disable debug_packet_logging
- [ ] Verify performance improves

---

### 10. Visual Validation Checklist

#### Test 10.1: Entity Icons & States

- [ ] Verify light entities show light bulb icons
- [ ] Verify switch entities show switch icons
- [ ] Check ON state shows yellow/active color
- [ ] Check OFF state shows gray/inactive color
- [ ] Verify unavailable shows red/error color

### Test 10.2: Dashboard Cards

- [ ] Create a dashboard card with Cync devices
- [ ] Verify all controls work from card
- [ ] Check compact view works
- [ ] Test different card types (entities, button, etc.)

### Test 10.3: Device Page Layout

- [ ] Navigate to Settings → Devices & Services
- [ ] Locate Cync Controller bridge device
- [ ] Click to open device page
- [ ] Verify all linked entities appear
- [ ] Check device information is complete

---

## Success Criteria

### Critical (Must Pass)

- ✅ All lights respond to on/off commands within 2 seconds
- ✅ Brightness and color temperature controls work correctly
- ✅ Physical device changes reflect in GUI within 5 seconds
- ✅ Configuration UI shows all cloud relay options
- ✅ No errors when controlling devices
- ✅ Addon logs accessible and show relay activity

### Important (Should Pass)

- ✅ Entity attributes display correctly
- ✅ Service calls work from Developer Tools
- ✅ Rapid commands handled gracefully
- ✅ Multiple devices controlled simultaneously
- ✅ Device unavailable states handled correctly

### Nice to Have

- ✅ Minimal latency impact from relay mode (<500ms)
- ✅ Dashboard cards display beautifully
- ✅ History graphs show state changes
- ✅ Configuration validation prevents errors

---

## Test Execution Log Template

For each test, record:

```yaml
Test: [Test ID and Name]
Date: [timestamp]
Result: PASS / FAIL / PARTIAL
Notes: [observations]
Screenshots: [if applicable]
Logs: [relevant log excerpts]
```

---

## Known Limitations (Not Testable)

- Visual appearance of physical lights (color accuracy)
- Exact physical brightness calibration
- RF signal strength variations
- Multi-user concurrent access (requires multiple browsers)

---

## Recommended Test Order

1. Start with basic on/off controls (Test 1.1, 2.1)
2. Test attribute controls (Test 1.2, 1.3)
3. Validate bidirectional updates (Test 3)
4. Check addon UI (Tests 5, 6)
5. Use developer tools (Test 7)
6. Stress test with edge cases (Tests 8, 9)
7. Final visual validation (Test 10)

---

## Automation Potential

### Cannot be automated

- Physical light observation
- Visual color validation
- Physical switch toggling

### Can be automated

- API/service calls
- Entity state verification
- Log parsing
- Configuration changes
- MQTT message validation

### Hybrid approach

- Send commands programmatically
- Human validates physical device response
- Automated verification of state updates

---

**Estimated Testing Time:** 45-60 minutes (human-in-the-loop)
