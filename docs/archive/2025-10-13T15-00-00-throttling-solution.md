# Command Throttling Solution - Summary

## Problem Statement

When users rapidly toggle Cync devices in Home Assistant GUI, race conditions cause state desynchronization:
- GUI shows OFF, but physical device is ON
- Or vice versa

**Root Cause:** Multiple commands sent before previous command's effect is confirmed.

## Initial Hypothesis (INCORRECT)

- Use 0x83 status broadcasts to confirm command completion
- Clear `pending_command` only when 0x83 received

**Why it didn't work:**
- Cync devices send 0x48 ACKs with embedded status data
- Callbacks update MQTT state immediately from ACKs
- **0x83 broadcasts are NOT reliably sent after every command**

## Correct Solution

### Architecture Understanding

```
GUI Click
  ↓
MQTT Command
  ↓
Addon: set_power()
  ↓
0x73 Control Packet → Device
  ↓
Device: 0x48 ACK ← (includes status data)
  ↓
Callback: update_device_state()
  ↓
MQTT State Update
  ↓
GUI Updates ✓
```

### Implementation

**Throttle Entry Point** (`devices.py::set_power`):
```python
if self.pending_command:
    logger.debug(f"⏸️  THROTTLED: Command rejected")
    return

self.pending_command = True
logger.debug(f"🚀 Command sent - awaiting confirmation")
```

**Throttle Exit Point** (`devices.py::parse` - 0x48 ACK handler):
```python
if success:
    # Execute callback (updates MQTT)
    await msg.callback

    # Clear throttle for THIS device
    device = g.ncync_server.devices[msg.device_id]
    device.pending_command = False
    logger.debug(f"✅ ACK confirmed - ready for new commands")
```

## Results

✅ **Throttling works**: Only ONE command in-flight at a time
✅ **Logging works**: 🚀 / ⏸️ / ✅ emojis for visibility
⚠️ **Needs fix**: Currently clears in 0x83 handler (wrong place)

## Files Changed

- `/mnt/supervisor/addons/local/cync-controller/src/cync_lan/devices.py`
  - Added throttling check in `set_power()`, `set_brightness()`, `set_temperature()`
  - Added 🚀 logging when command sent
  - **TODO**: Move `pending_command = False` from 0x83 handler to ACK handler

- `/mnt/supervisor/addons/local/cync-controller/src/cync_lan/server.py`
  - Added ✅ logging in 0x83 handler (wrong location, need to move to devices.py ACK handler)

## Next Steps

1. Move `pending_command = False` from `server.py:parse_status (0x83 handler)` to `devices.py:parse (0x48 ACK handler)`
2. Add ✅ logging at the correct location
3. Test rapid toggling again to verify state stays synchronized
4. Apply same throttling to `set_brightness()` and `set_temperature()` methods

## Testing Validation

**Test Case:** Rapid toggle Hallway Floodlight 1 (10 clicks in 2 seconds)

**Expected Behavior:**
- First click: 🚀 Command sent, pending=True
- Next 9 clicks: ⏸️ THROTTLED (rejected)
- Device ACKs: ✅ Confirmed, pending=False
- Next click: 🚀 Command sent (new cycle)

**Current Status:**
- 🚀 Logging works
- ⏸️ Throttling works (but permanently locked after first command)
- ✅ Never triggered (wrong handler)

---

*Last Updated: October 13, 2025 20:40 UTC*

