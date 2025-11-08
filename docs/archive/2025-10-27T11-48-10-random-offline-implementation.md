# Fix Random Offline Device Issue - Implementation Complete

**Status**: ✅ COMPLETED
**Date**: 2025-10-27

## Problem Fixed

Devices were randomly going offline due to a race condition between two conflicting systems managing device availability:

1. **Proper offline detection** (`server.py`): Uses `offline_count` threshold (3 consecutive failures)
2. **Conflicting overrides** (`mqtt_client.py`): Unconditional `device.online = True` assignments

The MQTT client methods were bypassing the offline threshold mechanism, causing devices marked offline to immediately return online.

## Solution Implemented

### 1. Removed Conflicting Online Assignments

**File**: `cync-controller/src/cync_controller/mqtt_client.py`

Removed `device.online = True` from 5 update methods:

- `update_device_state()` (line 860)
- `update_subgroup_switch_state()` (line 942)
- `update_brightness()` (line 1068)
- `update_temperature()` (line 1138)
- `update_rgb()` (line 1154)

Updated docstrings to clarify that device availability is managed by `server.parse_status()`.

### 2. Enhanced Logging for Offline Detection

**File**: `cync-controller/src/cync_controller/server.py`

Added comprehensive logging to track:

- Every offline_count increment: `[OFFLINE_TRACKING]`
- Offline threshold reached: `[OFFLINE_STATE]` (3 consecutive failures)
- Device back online: `[ONLINE_STATE]`

### 3. Single Source of Truth

**File**: `cync-controller/src/cync_controller/server.py`

Established `server.parse_status()` as the single source of truth for device availability based on the `connected_to_mesh` byte.

## Key Logic Flow

```text
Device Status Packet Received
↓
parse_status() called with connected_to_mesh byte
↓
If connected_to_mesh == 0:
  - Increment offline_count
  - If offline_count >= 3: mark device offline
  - Log: [OFFLINE_TRACKING] or [OFFLINE_STATE]
↓
Else:
  - Reset offline_count to 0
  - Set device.online = True
  - Log: [ONLINE_STATE]
↓
MQTT client updates WITHOUT modifying device.online
```text

## Deployment

1. Rebuild required: `cd cync-controller && ./rebuild.sh`
2. No configuration changes needed
3. Monitor logs for offline tracking entries

## Testing Checklist

- [ ] Monitor `[OFFLINE_TRACKING]` logs when device has issues
- [ ] Verify `[OFFLINE_STATE]` logged on 3rd consecutive failure
- [ ] Verify `[ONLINE_STATE]` logged when device reconnects
- [ ] Confirm devices don't flicker online/offline
- [ ] Test offline devices remain unavailable in Home Assistant
- [ ] Test state updates work correctly while online

## Known Issues

### Groups No Longer Reported to MQTT (Pre-existing)

**Status**: Regression from earlier commits (NOT caused by this fix)
**Severity**: HIGH - Requires separate fix before deployment

This appears to be caused by changes to `publish_optimistic()` methods from a previous commit,
not from the offline detection fix implemented here.

The offline detection fix only:

- Removed 5 x `device.online = True` assignments
- Added enhanced logging

See `FIX_SUMMARY.md` for full investigation details on group reporting issue.
