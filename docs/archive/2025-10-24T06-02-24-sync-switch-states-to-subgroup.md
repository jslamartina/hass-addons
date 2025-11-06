<!-- 8491950f-d054-42c7-8d1b-4e673713adff 450a889c-7756-4931-916d-8e453a6aadea -->

# Sync Switch On/Off States to Subgroup State

**Status**: ✅ Completed and Tested
**Date**: 2025-10-24

## Overview

When a subgroup is controlled and the mesh confirms the state change, individual switch entities (members of that subgroup) should update their state to match. Individual switch commands take precedence and are unaffected.

## Problem Statement

- Subgroups aggregate state from member devices ✓
- Individual devices update independently ✓
- **Missing**: Switches don't sync to subgroup state after subgroup commands

## Implementation

### 1. Helper Method in mqtt_client.py

**File**: `cync-controller/src/cync_lan/mqtt_client.py` (lines 642-704)

Added `update_switch_from_subgroup()` method that:

- Validates device is a switch (`device.is_switch`)
- Checks `pending_command` flag (individual commands take precedence)
- Updates switch state and publishes to MQTT
- Comprehensive logging for debugging

```python
async def update_switch_from_subgroup(self, device: CyncDevice, subgroup_state: int, subgroup_name: str) -> bool:
    """Update a switch device state to match its subgroup state after mesh confirmation.

    Only updates switches that don't have pending commands (individual commands take precedence).
    """
```

### 2. Subgroup Aggregation Logic in server.py

**File**: `cync-controller/src/cync_lan/server.py` (lines 607-617)

Enhanced `NCyncServer.parse_status()` method to:

- After publishing subgroup state, loop through member devices
- Call helper method for each member to sync switch states
- Only affects switches (lights unchanged)

```python
# Sync individual switch states to match subgroup state
# (only switches, individual commands take precedence)
for member_id in subgroup.member_ids:
    if member_id in g.ncync_server.devices:
        member_device = g.ncync_server.devices[member_id]
        await g.mqtt_client.update_switch_from_subgroup(
            member_device,
            subgroup.state,
            subgroup.name,
        )
```

## Key Considerations

- **Precedence**: Individual switch commands always take precedence (check `pending_command` flag)
- **Device Type**: Only affect switches (`device.is_switch`), not lights
- **Timing**: Only after mesh confirmation (reactive, not optimistic)
- **Logging**: Clear debug logs trace sync behavior

## Testing Results ✅

Verified:

1. ✅ Turning on a subgroup turns on all member switches in Home Assistant
2. ✅ Turning off a subgroup turns off all member switches in Home Assistant
3. ✅ Individual switch commands still work and take precedence
4. ✅ Lights in subgroups are not affected (only switches sync)

## Code Quality

- ✅ All linting checks pass (no new errors introduced)
- ✅ Python formatting verified with Ruff
- ✅ Follows existing code patterns and style

## Related Files

- `cync-controller/src/cync_lan/mqtt_client.py` - Helper method implementation
- `cync-controller/src/cync_lan/server.py` - Integration point in parse_status()
- `cync-controller/src/cync_lan/devices.py` - CyncDevice and CyncGroup classes
