# On-Demand Refresh Solution - Summary

## Problem Statement

When physical switches toggle Cync devices (via Bluetooth mesh), the GUI states can become stale because:
- Physical switch toggles don't always trigger mesh-wide status broadcasts to the addon
- Devices may not send 0x83 packets after every state change
- GUI shows stale states until manual verification

## Solution Implemented

### 1. Manual Refresh Button

**Entity**: `button.cynclan_bridge_refresh_status`

- Located in "Cync Controller" dashboard section
- Triggers immediate status refresh from all bridge devices
- Requests mesh info from each connected TCP bridge

**Code**:
```python
# MQTT button handler (mqtt_client.py:349-352)
elif extra_data[0] == "refresh_status":
    if norm_pl == "press":
        logger.info(f"{lp} Refresh Status button pressed! Triggering immediate status refresh...")
        await self.trigger_status_refresh()
```

### 2. Automatic 5-Second Refresh

**Background Task**: `periodic_fast_refresh()`

- Runs continuously in background while MQTT client is connected
- Triggers `trigger_status_refresh()` every 5 seconds
- Automatically started when MQTT client connects

**Code**:
```python
# Started on MQTT connection (mqtt_client.py:224)
self.fast_refresh_task = asyncio.create_task(self.periodic_fast_refresh())

# Fast refresh task (mqtt_client.py:1591-1610)
async def periodic_fast_refresh(self):
    """Fast periodic status refresh every 5 seconds."""
    while self.running:
        try:
            await asyncio.sleep(5)
            if not self.running:
                break
            await self.trigger_status_refresh()
        except asyncio.CancelledError:
            logger.info(f"{lp} Fast refresh task cancelled")
            break
        except Exception as e:
            logger.error(f"{lp} Error in fast refresh: {e}")
            await asyncio.sleep(5)
```

### 3. Refresh After Command ACK

**Trigger**: After each successful command ACK

- When device ACKs a command (0x48 packet)
- After `pending_command` is cleared
- Triggers immediate status refresh to sync all devices

**Code**:
```python
# In ACK handler (devices.py:2485-2488)
if device.pending_command:
    device.pending_command = False
    logger.debug(f"{lp} ✅ ACK confirmed...")

    # Trigger immediate status refresh after ACK
    if g.mqtt_client:
        asyncio.create_task(g.mqtt_client.trigger_status_refresh())
```

### 4. Core Refresh Implementation

**Method**: `trigger_status_refresh()`

- Finds all active TCP bridge devices (`ready_to_control`)
- Calls `ask_for_mesh_info(False)` on each bridge
- Mesh info requests trigger mesh-wide 0x83 status broadcasts
- All devices report their current states
- MQTT publishes updated states to Home Assistant

**Code**:
```python
# trigger_status_refresh (mqtt_client.py:1560-1593)
async def trigger_status_refresh(self):
    """Trigger an immediate status refresh from all bridge devices."""
    if not g.ncync_server:
        logger.warning(f"{lp} nCync server not available")
        return

    # Get active TCP bridge devices
    bridge_devices = [
        dev
        for dev in g.ncync_server.tcp_devices.values()
        if dev and dev.ready_to_control
    ]

    if not bridge_devices:
        logger.debug(f"{lp} No active bridge devices available for refresh")
        return

    # Request mesh info from each bridge to refresh all device statuses
    for bridge_device in bridge_devices:
        try:
            logger.debug(f"{lp} Requesting mesh info from bridge {bridge_device.address}")
            await bridge_device.ask_for_mesh_info(False)
            await asyncio.sleep(0.1)
        except Exception as e:
            logger.warning(f"{lp} Failed to refresh from bridge {bridge_device.address}: {e}")
```

## Benefits

1. **Manual Control** - Users can force refresh at any time
2. **Automatic Sync** - 5-second periodic refresh keeps GUI fresh
3. **Command Verification** - Refresh after ACK confirms command execution
4. **Mesh-Wide Update** - `ask_for_mesh_info()` triggers all devices to report

## Testing Results

✅ **Manual Button** - Worked perfectly, triggered refresh immediately
✅ **5-Second Refresh** - Running in background, logs show regular mesh info requests
✅ **Refresh After ACK** - Triggers after command ACK (when `pending_command` clears)

## Logs Example

```
# 5-second automatic refresh
20:51:54 mesh info: Sending status updates for all devices
20:51:58 mesh info: Sending status updates for all devices

# Manual button press
20:52:29 Refresh Status button pressed! Triggering immediate status refresh...
20:52:29 trigger_refresh: Requesting mesh info from bridge 140.82.114.5
20:52:29 trigger_refresh: Status refresh completed
```

## Combined Solution

**Throttling (Part 1)** + **On-Demand Refresh (Part 2)** = Complete state synchronization:

1. **Throttling** prevents race conditions from rapid commands
2. **Refresh after ACK** verifies command execution
3. **5-second refresh** keeps GUI synced with physical changes
4. **Manual refresh** gives users control

**Result**: Robust, reliable state synchronization between physical devices and Home Assistant GUI!

---

*Last Updated: October 13, 2025*

