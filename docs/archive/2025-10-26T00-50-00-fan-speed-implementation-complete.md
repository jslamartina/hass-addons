# Fan Speed Control Implementation - Complete

**Date:** October 26, 2025
**Status:** ✅ Complete
**Version:** 0.0.4.12

## Summary

Successfully implemented persistent preset mode state for fan entities in the Cync Controller add-on. The fan control UI now correctly displays and persists the selected preset mode (off/low/medium/high/max) across UI reopens and addon restarts.

## Problem Statement

The Master Bedroom Fan Switch entity was experiencing two critical issues:

1. **Preset mode didn't persist** - The UI would reset to "unset" when reopening the fan control dialog
2. **No slider needed** - The physical fan only supports discrete preset modes, not continuous percentage control

## Solution

### 1. Removed Percentage Slider

- Removed `percentage_command_topic` and `percentage_state_topic` from MQTT discovery schema
- Fan UI now only shows preset mode buttons (off/low/medium/high/max)
- Cleaner user experience that matches physical device capabilities

### 2. Added Persistent Preset Mode State

Implemented `retain=True` for preset mode MQTT messages in three locations:

#### a) `update_brightness()` - Command Execution

When commands are sent to the fan, the preset mode is published to `preset_mode_state_topic` with `retain=True`.

#### b) `parse_device_status()` - Status Updates

When device status updates (0x83 packets) are received, the preset mode is published with `retain=True`.

#### c) `homeassistant_discovery()` - Initial Discovery

When devices are first registered, the initial preset mode is published with `retain=True`.

### 3. Brightness to Preset Mapping

```text
0   → "off"
25  → "low"
50  → "medium"
75  → "high"
100 → "max"
```text

## Files Modified

### Core Logic

- `cync-controller/src/cync_lan/mqtt_client.py`
  - Modified MQTT discovery schema for fan entities
  - Added preset mode publishing in `update_brightness()`
  - Added preset mode publishing in `parse_device_status()`
  - Added preset mode publishing in `homeassistant_discovery()`
- `cync-controller/src/cync_lan/devices.py`
  - Updated `set_fan_speed()` to use discrete brightness values (0, 25, 50, 75, 100)
  - Enhanced logging for fan commands

### Configuration

- `cync-controller/config.yaml` - Version bumped to 0.0.4.12
- `cync-controller/CHANGELOG.md` - Documented changes in version 0.0.4.7

### Documentation

- `docs/archive/2025-10-26T00-48-00-fan-preset-mode-persistence-fix.md` - Diagnostic findings

## Verification

### Docker Logs Confirmation

```text
10/26/25 00:45:46.854 INFO [mqtt_client:1647] > mqtt:hass: Registered fan: Master Bedroom Fan Switch (ID: 103)
10/26/25 00:45:46.854 INFO [mqtt_client:1689] > mqtt:hass: >>> FAN INITIAL PRESET: Published 'max' (brightness=100) for 'Master Bedroom Fan Switch'
```text

### User Testing

✅ Fan preset mode correctly shows "max" on startup
✅ Preset mode persists across UI window reopens
✅ Preset mode persists across addon restarts
✅ Physical fan responds to all preset mode changes
✅ Slider removed from UI (preset buttons only)

## Technical Details

### MQTT Retained Messages

The `retain=True` flag ensures that:

- The MQTT broker stores the last preset mode message
- New subscribers (e.g., Home Assistant after restart) immediately receive the latest state
- The UI always shows the correct preset mode, even if it wasn't actively subscribed during the publish

### Publishing Locations Rationale

1. **update_brightness()** - Ensures immediate UI feedback when commands are executed
2. **parse_device_status()** - Syncs UI when physical switch is used or device reports status
3. **homeassistant_discovery()** - Ensures correct initial state on device registration/discovery

## Testing Performed

1. ✅ MQTT wipe and fresh discovery
2. ✅ Preset mode changes via Home Assistant UI
3. ✅ Physical switch changes reflecting in UI
4. ✅ Addon restart with state persistence
5. ✅ Home Assistant restart with state persistence
6. ✅ Docker logs verification of initial preset publishing

## Future Considerations

- The current implementation publishes preset mode in three locations for maximum reliability
- If future optimizations are needed, consider consolidating to reduce MQTT traffic
- Monitor for any edge cases where preset mode might not sync correctly

## Lessons Learned

1. **MQTT Retained Messages Are Critical** - Without `retain=True`, state doesn't persist across restarts
2. **Logs Roll** - The `ha addons logs` command only shows last 100 lines; use `docker logs` for full history
3. **Discrete Device Support** - Not all devices support continuous sliders; match UI to physical capabilities
4. **Multiple Publish Points** - Publishing state in multiple locations (commands, status, discovery) ensures reliability

## References

- [MQTT Discovery Schema - Home Assistant](https://www.home-assistant.io/integrations/mqtt/#mqtt-discovery)
- [Fan Entity - Home Assistant](https://www.home-assistant.io/integrations/fan/)
- MQTT Retained Messages: <https://www.hivemq.com/blog/mqtt-essentials-part-8-retained-messages/>

---

**Implementation Complete** - Ready for PR submission
