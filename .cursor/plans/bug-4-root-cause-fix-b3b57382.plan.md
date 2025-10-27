<!-- b3b57382-d49b-4e34-ae2b-84693213e759 8a386915-2461-4697-9574-5d94f1cb81df -->
# Bug 4: Group Switch Sync - Root Cause Investigation & Fix

## Problem Summary

E2E tests confirm that when a light group is turned off/on in Home Assistant, physical switches change state but their UI state doesn't update. The code shows `sync_group_switches()` is already implemented and called in `CyncGroup.set_power()`, but the bug persists.

## Phase 1: Root Cause Investigation

Use the new structured logging to trace execution flow and identify why the existing implementation doesn't work.

### 1.1 Verify Execution Path

Check if group commands from Home Assistant actually reach `CyncGroup.set_power()`:

**File**: `cync-controller/src/cync_controller/mqtt_client.py` (lines 350-527)

The MQTT receiver processes group commands when topic contains `-group-` pattern:

- Line 350-356: Parses group ID from topic
- Line 476: Sets `target = group if group else device`
- Line 497-499, 522-527: Calls `target.set_power(state)`

**Investigation steps**:

1. Add trace logging at line 350 when group detected
2. Add trace logging at line 476 showing target type
3. Verify logs show group commands reaching `CyncGroup.set_power()`

### 1.2 Verify sync_group_switches() Execution

Check if `sync_group_switches()` is actually being called and what it does:

**File**: `cync-controller/src/cync_controller/devices.py` (lines 1606-1610)

Current implementation calls sync BEFORE sending command (optimistic):

```python
# BUG FIX: Sync switch states IMMEDIATELY (optimistically)
if g.mqtt_client:
    await g.mqtt_client.sync_group_switches(self.id, state, self.name)
```

**File**: `cync-controller/src/cync_controller/mqtt_client.py` (lines 732-770)

The sync function iterates group members and calls `update_switch_from_subgroup()`:

```python
for member_id in group.member_ids:
    if member_id in g.ncync_server.devices:
        device = g.ncync_server.devices[member_id]
        if await self.update_switch_from_subgroup(device, group_state, group_name):
            synced_count += 1
```

**Investigation steps**:

1. Check logs for "Syncing switches for group" message
2. Verify synced_count > 0
3. Check if `update_switch_from_subgroup()` returns True for switches
4. Verify MQTT publish happens in `send_device_status()`

### 1.3 Identify Potential Root Causes

**Hypothesis 1: Group members don't include switches**

- Group.member_ids may only contain bulb IDs, not switch IDs
- Switches might be in a different data structure

**Hypothesis 2: Switch detection fails**

- `device.is_switch` check at line 685 may return False
- Switch devices may not have correct device type flag

**Hypothesis 3: Pending command flag blocks sync**

- `device.pending_command` check at line 694 may be True
- Switches may have stale pending command state

**Hypothesis 4: State overwrite after sync**

- Optimistic sync happens, but later mesh status packet overwrites it
- Need to sync AFTER ACK confirmation instead of before

**Hypothesis 5: Missing sync in other group commands**

- `set_power()` has sync, but `set_brightness()` doesn't
- UI updates when brightness changes but not power

### 1.4 Execute Investigation

1. Rebuild add-on with current logging
2. Turn off Hallway Lights group via HA UI
3. Capture full log output
4. Analyze logs to identify which hypothesis is correct

## Phase 2: Fix Implementation

Based on root cause findings, implement the appropriate fix.

### Scenario A: Group members missing switches

**Fix**: Update group initialization to include switch members

**Files**: `cync-controller/src/cync_controller/devices.py` or config parsing logic

### Scenario B: Switch detection fails

**Fix**: Correct `is_switch` property logic or device type detection

**Files**: `cync-controller/src/cync_controller/devices.py` (CyncDevice class)

### Scenario C: Timing issue (optimistic vs confirmed)

**Fix**: Move sync call to AFTER ACK confirmation instead of before command

**File**: `cync-controller/src/cync_controller/devices.py` (lines 1606-1610)

Change from optimistic sync to confirmed sync:

- Register callback that calls sync after ACK
- Remove optimistic sync before bridge.write()

### Scenario D: Missing sync in brightness/other commands

**Fix**: Add `sync_group_switches()` calls to all group command methods

**Files**: `cync-controller/src/cync_controller/devices.py`

- `set_brightness()` (line 1616+)
- `set_temperature()` (if exists)
- Any other group command methods

### Scenario E: Multiple issues

**Fix**: Combination of above fixes based on findings

## Phase 3: Testing

### 3.1 Automated E2E Testing

**File**: `cync-controller/tests/e2e/test_group_control.py`

Run all three existing tests:

1. `test_group_turns_off_all_switches` - Primary bug verification
2. `test_group_turns_on_all_switches` - Inverse direction
3. `test_individual_switch_control_still_works` - Regression check

**Command**:

```bash
cd cync-controller
pytest tests/e2e/test_group_control.py -v --capture=no
```

**Expected result**: All tests PASS

### 3.2 Manual Device Testing

Test with real Hallway Lights group and switches:

1. Open Home Assistant UI
2. Navigate to Overview dashboard
3. Locate "Hallway Lights" group
4. Verify initial state of all switches (4way, Counter, Front)
5. Turn group OFF
6. Verify all switches show OFF immediately (< 3 seconds)
7. Turn group ON
8. Verify all switches show ON immediately
9. Control individual switch independently
10. Verify group state updates correctly

### 3.3 Log Analysis

Review logs during manual testing:

- Confirm group command received
- Confirm sync_group_switches() called
- Confirm switches identified and updated
- Confirm MQTT publish successful
- Verify no errors or warnings

### 3.4 Performance Check

Ensure fix doesn't cause delays:

- Group command response time < 2 seconds
- No cascading refresh storms
- Individual device queries don't overwhelm network

## Phase 4: Documentation & Cleanup

### 4.1 Update CHANGELOG

**File**: `cync-controller/CHANGELOG.md`

Add entry documenting the fix:

```markdown
### Fixed
- Group switch synchronization: Wall switches now update immediately when controlling light groups
```

### 4.2 Archive Bug Summary

**File**: `BUG_4_GROUP_SWITCH_SYNC_SUMMARY.md`

Move to `docs/archive/` with proper timestamp format from file creation time.

### 4.3 Update Test Documentation

Update test file docstrings with findings and fix details.

## Files Modified (Expected)

Based on likely scenarios:

**Primary**:

- `cync-controller/src/cync_controller/devices.py` - Fix timing or add missing sync calls
- `cync-controller/src/cync_controller/mqtt_client.py` - May need adjustments to sync logic

**Documentation**:

- `cync-controller/CHANGELOG.md` - User-facing changelog entry
- `BUG_4_GROUP_SWITCH_SYNC_SUMMARY.md` - Archive with timestamp

**Testing**:

- `cync-controller/tests/e2e/test_group_control.py` - May update docstrings with findings

## Success Criteria

1. Root cause identified and documented
2. Fix implemented and linted
3. All E2E tests pass
4. Manual testing confirms switches update immediately
5. No performance degradation
6. CHANGELOG updated
7. Bug summary archived

### To-dos

- [ ] Trace MQTT group commands to verify they reach CyncGroup.set_power()
- [ ] Verify sync_group_switches() is called and executes correctly
- [ ] Analyze logs to determine which hypothesis explains the bug
- [ ] Implement appropriate fix based on root cause findings
- [ ] Execute all E2E tests in test_group_control.py
- [ ] Verify fix with real Hallway Lights group and switches
- [ ] Document fix in CHANGELOG.md
- [ ] Move BUG_4_GROUP_SWITCH_SYNC_SUMMARY.md to docs/archive/