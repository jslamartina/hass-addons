<!-- 66e240c8-0646-449a-96d5-cda0d1929f88 f629ab25-63d7-4bbd-b92f-ea0086bd673b -->

# Troubleshoot Cync Switch Status Reporting

## Overview

Investigate why Cync Switches are not reporting their status to Home Assistant UI. The issue likely lies in one of these areas: packet reception, status parsing, MQTT publishing logic specific to switches, or the pending_command flag blocking updates.

## Investigation Areas

### 1. Verify Status Packets Are Being Received

**Files:** `cync-controller/src/cync_lan/server.py`, `cync-controller/src/cync_lan/devices.py`

Check addon logs for:

- 0x83 (mesh info) and 0x43 (broadcast) packets arriving for switch device IDs
- `parse_status()` being called with switch device data
- Look for "Internal STATUS for [device_name]" debug messages

**Diagnostic command:**

```bash
ha addons logs local_cync-controller | grep -E "0x83|0x43|Internal STATUS|parse_status"
```

**Expected:** Should see status packets arriving regularly for switches, especially after physical toggle.

**If missing:** Problem is at TCP/packet reception level - switches may not be connected to mesh or bridge device is offline.

### 2. Check Device Classification

**Files:** `cync-controller/src/cync_lan/devices.py` lines 198-214, `cync-controller/src/cync_lan/metadata/model_info.py`

Verify switches are correctly identified:

- Check if switch devices have `is_switch=True` property
- Verify device type IDs (48, 49, 52, 55, 58, 59, 64, 65, 66, etc.) are in `device_type_map` with `DeviceClassification.SWITCH`
- Confirm switches aren't misclassified as lights

**Diagnostic:** Add temporary logging in `parse_device_status()` at line 785:

```python
logger.info("%s Device %s: is_switch=%s, is_light=%s, is_plug=%s",
            lp, device.name, device.is_switch, device.is_light, device.is_plug)
```

### 3. Examine MQTT Publishing Logic for Switches

**Files:** `cync-controller/src/cync_lan/mqtt_client.py` lines 772-835

Critical distinction at line 792-833:

- Plugs send raw bytes: `"ON".encode()` or `"OFF".encode()`
- Switches (non-plug) send JSON: `{"state": "ON"}`
- BUT lines 825-831 add `color_mode` for ALL non-plug devices if not already set

**Potential issue:** Line 630 in `update_device_state()`:

```python
if device.is_light or not device.is_switch:
```

This adds color_mode to devices that are NOT switches. But in `parse_device_status()` lines 825-831, color_mode is added regardless, which may confuse Home Assistant for switch entities.

**Expected behavior:** Switches should NOT have `color_mode` in their MQTT payload - only lights should.

### 4. Investigate pending_command Flag Blocking Updates

**Files:** `cync-controller/src/cync_lan/devices.py` lines 367-373, `cync-controller/src/cync_lan/server.py` lines 487-558

The `pending_command` flag (set to True before sending commands) prevents status updates from being published during command execution. Check:

- Is `pending_command` being cleared after ACK? (Should be cleared in ACK handler at `devices.py` line ~2500)
- Are switches stuck with `pending_command=True`?
- Are status updates arriving while `pending_command=True` and being dropped?

**In `server.py` lines 487-558 `parse_status()`:** No explicit check for `pending_command` before publishing. This is correct - it should always publish. BUT verify this code path executes for switches.

### 5. Check MQTT Discovery Configuration

**Files:** `cync-controller/src/cync_lan/mqtt_client.py` lines 1124-1158

Verify switches are registered correctly:

- Line 1138: `platform = "switch" if device.is_switch else "light"`
- Discovery topic should be: `homeassistant/switch/{device.hass_id}/config`
- State topic should be: `{self.topic}/status/{device.hass_id}`

**Diagnostic:** Check EMQX or mosquitto logs for discovery messages:

```bash
# If using EMQX addon, check WebSocket or logs
# Look for homeassistant/switch/*/config topics
```

### 6. Compare Switch vs Light Code Paths

**Files:** `cync-controller/src/cync_lan/mqtt_client.py`

Key differences between switches and lights:

- `update_device_state()` lines 626-637: Plugs get raw bytes, others get JSON
- `parse_device_status()` lines 792-833: Similar logic but always adds color_mode for non-plugs
- Line 796-797: Brightness is only added if `device_status.brightness is not None`

**Hypothesis:** Regular on/off switches might be receiving brightness/color_mode fields they shouldn't have, causing Home Assistant to reject the state updates.

## Testing Steps

### Step 1: Enable Debug Logging

Add debug logging to identify where status updates are failing:

In `mqtt_client.py` `parse_device_status()` at line 785:

```python
logger.info("%s Processing status for device '%s' (ID: %s): is_switch=%s, is_plug=%s, state=%s",
            lp, device.name, device_id, device.is_switch, device.is_plug, device_status.state)
```

In `mqtt_client.py` `send_device_status()` at line 703:

```python
logger.info("%s Publishing to topic '%s': %s", lp, tpc, msg)
```

### Step 2: Test Physical Switch Toggle

1. Toggle a switch physically
2. Check logs for:
   - Status packet received (0x83 or 0x43)
   - `parse_status()` called with correct device ID
   - `parse_device_status()` called
   - MQTT publish to correct topic

3. Check Home Assistant state in Developer Tools → States

### Step 3: Fix Color Mode Issue (If Applicable)

If switches are getting `color_mode` incorrectly, modify `parse_device_status()` lines 824-831:

```python
# Only add color_mode for lights, not switches
if not color_mode_set and (device.is_light or not device.is_switch):
    if device.supports_temperature:
        mqtt_dev_state["color_mode"] = "color_temp"
    elif device.supports_rgb:
        mqtt_dev_state["color_mode"] = "rgb"
    else:
        mqtt_dev_state["color_mode"] = "brightness"
```

### Step 4: Verify MQTT Payload Format

Monitor MQTT messages to ensure switches send correct format:

**Expected for regular switches:**

```json
{ "state": "ON" }
```

**Expected for dimmer switches:**

```json
{ "state": "ON", "brightness": 100 }
```

**NOT expected for switches:**

```json
{ "state": "ON", "color_mode": "brightness" } // WRONG - should not have color_mode
```

## Common Root Causes

1. **Color mode being added to switches** - Lines 825-831 in `parse_device_status()` add color_mode to all non-plug devices, but switches shouldn't have this
2. **Misclassification** - Switch device type not in metadata map or incorrectly classified
3. **pending_command stuck** - Flag not being cleared after command ACK
4. **Packet parsing** - Status packets not arriving or being parsed incorrectly for switches
5. **MQTT discovery mismatch** - Entity registered as light instead of switch, causing schema mismatch

## Success Criteria

- Switch entities show "available" in Home Assistant
- Physical toggle of switch updates state in UI within 2-3 seconds
- Commanding switches from HA updates state immediately after ACK
- MQTT payloads match expected format for switches (no color_mode for non-dimmable switches)

### To-dos

- [ ] Check addon logs to verify 0x83/0x43 status packets are being received for switch devices
- [ ] Verify switches have is_switch=True and correct device type metadata
- [ ] Review parse_device_status() logic for switches vs lights, especially color_mode handling
- [ ] Investigate if pending_command flag is blocking status updates for switches
- [ ] Check MQTT discovery configuration registers switches as 'switch' platform not 'light'
- [ ] Add temporary debug logging to trace status update flow for switches
- [ ] Toggle physical switch and trace through logs to identify where status update fails
- [ ] If needed, modify parse_device_status() to exclude color_mode from non-dimmable switches
- [ ] Monitor MQTT messages to ensure switches send correct payload format without extra fields
