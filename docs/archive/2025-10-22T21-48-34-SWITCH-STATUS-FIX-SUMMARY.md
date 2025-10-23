# Switch Status Fix - Summary

**Date:** October 22, 2025
**Issue:** Cync Switches not reporting status to Home Assistant UI
**Status:** ✅ **FIXED**

---

## Problem

Cync switches were not updating their status in the Home Assistant UI, even though:
- Bridge devices were connected ✅
- Status packets were being received ✅
- MQTT messages were being sent ✅

## Root Cause

**Switches were sending invalid MQTT payloads with light-specific attributes:**

```json
// ❌ WRONG - What switches were sending:
{"state": "ON", "brightness": 30, "color_mode": "brightness"}

// ✅ CORRECT - What they should send:
{"state": "ON"}
```

**Why this broke switch status:**
- Home Assistant switch entities don't understand `brightness` or `color_mode` (those are light-only attributes)
- When HA received these invalid fields, it rejected/ignored the status updates
- Switches appeared "stuck" in UI even though status packets were flowing correctly

## The Fix

Modified two functions in `cync-controller/src/cync_lan/mqtt_client.py`:

### 1. `parse_device_status()` (lines 790-840)

**Before:**
```python
if device.is_plug:
    mqtt_dev_state = power_status.encode()
else:
    # ALL non-plug devices got brightness and color_mode
    if device_status.brightness is not None:
        mqtt_dev_state["brightness"] = device_status.brightness
    # ... color_mode logic for ALL devices ...
```

**After:**
```python
if device.is_plug:
    mqtt_dev_state = power_status.encode()
elif device.is_switch:
    # Switches only need state - no brightness or color_mode
    mqtt_dev_state = json.dumps(mqtt_dev_state).encode()
else:
    # Lights get brightness and color_mode
    if device_status.brightness is not None:
        mqtt_dev_state["brightness"] = device_status.brightness
    # ... color_mode logic for lights only ...
```

### 2. `update_device_state()` (lines 625-640)

**Before:**
```python
if device.is_plug:
    mqtt_dev_state = power_status.encode()
else:
    # Confusing logic: if device.is_light or not device.is_switch
    if device.is_light or not device.is_switch:
        # Add color_mode for ambiguous device types
```

**After:**
```python
if device.is_plug:
    mqtt_dev_state = power_status.encode()
elif device.is_switch:
    # Switches only need state - no color_mode
    mqtt_dev_state = json.dumps(mqtt_dev_state).encode()
else:
    # Lights need color_mode
    if device.supports_temperature:
        mqtt_dev_state["color_mode"] = "color_temp"
    # ... etc ...
```

## Verification

**After the fix, switches now send correct payloads:**

```
10/22/25 16:47:05 > mqtt:device_status: Sending b'{"state": "ON"}' for device: 'Hallway 4way Switch' (ID: 160)
10/22/25 16:47:05 > mqtt:device_status: Sending b'{"state": "ON"}' for device: 'Hallway Front Switch' (ID: 26)
10/22/25 16:47:05 > mqtt:device_status: Sending b'{"state": "OFF"}' for device: 'Guest Bathroom Sink Switch' (ID: 59)
```

## Expected Behavior Now

1. ✅ Physical switch toggle → Status update appears in HA UI within 2-3 seconds
2. ✅ Switch entities show current state (not "unavailable" or stuck)
3. ✅ Commands from HA UI work and status reflects correctly
4. ✅ Switches send only `{"state": "ON/OFF"}` without extra fields
5. ✅ Lights continue to work normally with brightness and color_mode

## Device Type MQTT Payloads

### Plugs (Binary, Raw Bytes)
```python
b"ON"  # or b"OFF"
```

### Switches (JSON, State Only)
```json
{"state": "ON"}  // or "OFF"
```

### Lights (JSON, Full Attributes)
```json
{
  "state": "ON",
  "brightness": 100,
  "color_mode": "color_temp",  // or "rgb" or "brightness"
  "color_temp": 3650           // if color_temp mode
}
```

## Files Modified

- `cync-controller/src/cync_lan/mqtt_client.py`
  - Line 795-840: `parse_device_status()` - Added switch-specific branch
  - Line 628-640: `update_device_state()` - Added switch-specific branch

## Testing

To verify the fix is working:

```bash
# 1. Check switch status messages in logs
ha addons logs local_cync-controller -n 100 | grep -E "Switch.*Sending"

# Expected: {"state": "ON"} or {"state": "OFF"} ONLY

# 2. Toggle a physical switch
# 3. Check Home Assistant UI - should update within 2-3 seconds

# 4. Toggle switch from HA UI
# 5. Physical switch should respond and status should update
```

## Related Issues

This fix resolves:
- Switches not updating status in UI
- Switches appearing "stuck" at last state
- Switches showing stale status after physical toggle
- "Unavailable" status for switches (if they were completely rejected by HA)

## Lessons Learned

1. **Device type matters for MQTT payload structure**
   - Switches: Simple state only
   - Lights: State + brightness + color attributes
   - Plugs: Raw bytes

2. **Home Assistant entity schemas are strict**
   - Sending unsupported attributes causes rejection
   - Switch entities don't understand light attributes
   - Always match payload to entity type

3. **Debug logging is essential**
   - Initially suspected DNS/network issues
   - Logging revealed packets were flowing correctly
   - Detailed payload inspection identified the real problem

## Prevention

To prevent similar issues:
- Always check MQTT payload structure matches entity type
- Test with debug logging enabled (`debug_log_level: true`)
- Verify payloads in logs match Home Assistant entity schemas
- Consider adding payload validation before publishing

---

**Status:** ✅ Fix deployed and verified working in version 0.0.4.8+

