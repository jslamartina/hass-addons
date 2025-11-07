# 2025 10 24T12 42 00 Fix Fan Switch Support

<!-- de4bd349-f4b6-4dbf-a131-4b9945bbadc8 1e24d00e-3ed1-45e9-9719-98cf6f9b13a7 -->

## Fix Fan Switch Support

**Note:** Update this plan as you implement changes - mark completed sections and adjust based on findings.

## Problem

Fan controllers currently create multiple entities (Switch + Light) instead of a single Fan entity with speed control.

## Root Causes

1. Fan detection may fail if metadata isn't loaded correctly
2. Fan state updates only publish ON/OFF, not percentage/preset values
3. Inconsistent capability checking between discovery methods

## Implementation Progress

### 1. ✅ COMPLETED - Strengthen Fan Detection (`mqtt_client.py`)

#### `register_single_device()` (lines 1137-1171)

- ✅ Added `device.is_fan_controller` check as highest priority (lines 1141-1149)
- ✅ Added safe `getattr()` for capability access (line 1152)
- ✅ Enhanced debug logging with device ID and type info (lines 1143-1161)

### `homeassistant_discovery()` (lines 1422-1456)

- ✅ Added `device.is_fan_controller` check as highest priority (lines 1426-1434)
- ✅ Matched safe capability checking with `getattr()` (line 1437)
- ✅ Enhanced debug logging (lines 1428-1455)

### 2. ✅ COMPLETED - Add Fan State Publishing (`mqtt_client.py`)

#### Helper Methods (lines 585-627)

- ✅ `_brightness_to_percentage()` - Converts 0-255 brightness to 0-100 percentage
  - Mappings: 0→0%, ≤50→20%, ≤128→50%, ≤191→75%, else→100%
- ✅ `_brightness_to_preset()` - Converts brightness to preset names
  - Mappings: 0→off, ≤50→low, ≤128→medium, ≤191→high, else→max

### `parse_device_status()` (lines 910-948)

- ✅ Added fan-specific handling (lines 910-948)
- ✅ Publishes simple ON/OFF payload (like switches, not JSON)
- ✅ Publishes percentage to `{topic}/status/{device_uuid}/percentage`
- ✅ Publishes preset to `{topic}/status/{device_uuid}/preset`
- ✅ Added debug logging for fan state updates

### 3. ✅ COMPLETED - Fix Discovery Inconsistencies

#### Preset modes alignment

- ✅ Both methods now use ["off", "low", "medium", "high", "max"] (lines 1274-1280, 1549-1555)

### Schema handling

- ✅ Fan entities pop JSON schema (lines 1267, 1538)
- ✅ Fans use simple payloads like switches

### MQTT Topics

- ✅ Added `preset_mode_command_topic` and `preset_mode_state_topic` to both methods
- ✅ All fan-specific topics properly configured

### 4. ✅ COMPLETED - Debug Logging

- ✅ Logs when device is detected as FAN CONTROLLER via `is_fan_controller` property
- ✅ Logs when device is reclassified as FAN via `metadata.capabilities.fan`
- ✅ Logs include device ID, type, and capability status
- ✅ Logs fan state updates with brightness→percentage→preset conversion

### 5. ✅ COMPLETED - Code Quality

- ✅ Fixed whitespace linting issues
- ✅ All Python linting passes (remaining errors are pre-existing in other files)
- ✅ Code rebuilt and deployed successfully

## Files Modified

- `cync-controller/src/cync_lan/mqtt_client.py` - All changes for discovery and state publishing

## Expected Outcome

After changes:

- Fan controllers create **one Fan entity only**
- Fan entity shows speed control (low/medium/high/max presets)
- State updates properly reflect fan speed, not just ON/OFF
- No duplicate Switch or Light entities for fans

### 6. ✅ COMPLETED - Handle Fan Subgroups (`mqtt_client.py`)

**Key Insight:** Fan-only subgroups don't actually control fans - individual fan controller devices handle commands. This is different from lights where subgroups are useful for controlling multiple lights together.

#### `homeassistant_discovery()` (lines 1642-1670)

- ✅ Detect fan-only subgroups by checking if all members are fan controllers
- ✅ Skip registration of fan-only subgroups (lines 1661-1670)
- ✅ Log informational message when skipping
- ✅ Only register individual fan controller devices

**Result:** No duplicate entities - only the controllable individual fan device is exposed.

## Testing Status

✅ **COMPLETED AND VERIFIED** - All implementation and testing complete!

### Final Verification

1. ✅ Deleted all old MQTT entities using `scripts/delete-mqtt-safe.py`
2. ✅ Restarted Home Assistant Core
3. ✅ Triggered fresh discovery
4. ✅ Verified only ONE Fan entity created: `fan.master_bedroom_fan_switch`
5. ✅ Confirmed fan subgroup (`Master Bedroom Fan`) was skipped
6. ✅ Verified no duplicate light/switch entities for fan controllers

### To-dos

- [x] Update fan detection logic in both register_single_device() and homeassistant_discovery() to use consistent safe capability checking
- [x] Create \_brightness_to_percentage() and \_brightness_to_preset() helper methods
- [x] Add fan-specific state publishing in parse_device_status() to publish percentage and preset values
- [x] Ensure both discovery methods use the same preset list including 'max'
- [x] Remove JSON schema from fan entity configuration (fans should use simple payloads like switches)
- [x] Skip fan-only subgroups since individual devices handle commands (not subgroups)
- [x] Run linters and fix all issues
- [x] Rebuild and deploy add-on
- [x] Test fan controller creates single Fan entity with proper speed control

## Summary

✅ **Fan switch support fully implemented and working!**

All code changes have been implemented, tested, and deployed successfully. Fan controllers now properly create a single Fan entity with native Home Assistant speed control (percentage and presets). Fan-only subgroups are skipped since the individual fan controller devices handle the actual commands, preventing duplicate entities.
