# Bug 4: Group Switch Sync Issue - Status Summary

**Date**: October 26, 2025
**Status**: ⚠️ **NOT RESOLVED - Test Created, Fix Pending**

---

## Problem Description

When turning off a light group in Home Assistant, all member switches should turn off and their UI should update to reflect the "off" state. However, the switches don't update properly.

**Expected Behavior**:
1. User turns off light group
2. Group command sent to all member devices
3. All member switches turn off physically
4. All member switches show "off" state in Home Assistant UI

**Actual Behavior**:
1. User turns off light group
2. Group command sent
3. Physical devices turn off ✅
4. Switches remain showing "on" state in UI ❌

---

## Root Cause

Group commands don't trigger individual 0x83 status packets from member switches. The system sends the group command successfully, but because individual devices don't send back their status updates after a group command, the Home Assistant UI doesn't reflect the new state.

**Protocol Behavior**:
- Individual device commands → Device sends 0x83 status packet → HA updates
- Group commands → No individual status packets → HA doesn't update

---

## Attempted Solutions

### Solution Explored: `sync_group_switches()`

The theory was to call `sync_group_switches()` immediately after sending group commands to force a status refresh of all member switches.

**Implementation Points**:
- Would need to be called after group off/on commands
- Should query individual switch states
- Update HA via MQTT with current states

**Status**: ❌ **Not implemented** - Test was created but fix was never applied

---

## What We Created

### E2E Test: `test_group_control.py`

Created comprehensive Playwright test to verify the expected behavior:

```python
def test_group_turns_off_all_switches(ha_login: Page, ha_base_url: str):
    """
    Test Bug 4: Turning off a light group should turn off all member switches.

    Current behavior: Physical switches turn off but UI doesn't update.
    Expected behavior: Both physical switches AND UI should reflect off state.
    """
```

**Test Steps**:
1. Navigate to overview dashboard
2. Identify target group (Hallway Lights) and member switches
3. Turn off the group
4. Wait for state propagation
5. Verify all member switches show "off" state
6. Turn group back on
7. Verify all member switches show "on" state

**Current Status**: Test exists but would currently **FAIL** because the bug is not fixed.

**File Location**: `cync-controller/tests/e2e/test_group_control.py`

---

## Current Status

### ✅ What We Have
- Comprehensive E2E test that documents expected behavior
- Clear understanding of root cause
- Identified solution approach (`sync_group_switches()`)

### ❌ What's Missing
- Actual implementation of `sync_group_switches()` calls after group commands
- Code changes to mqtt_client.py or server.py to trigger status refresh
- Verification that the fix works

### 📋 Where to Implement

**Location**: `cync-controller/src/cync_controller/mqtt_client.py`

**Functions that need updating**:
- Group off command handler
- Group on command handler
- Any other group state change handlers

**Required Change**:
```python
async def handle_group_command(self, group_id, command):
    # Send group command
    await self.send_group_command(group_id, command)

    # NEW: Sync member switch states
    await self.sync_group_switches(group_id)  # ← ADD THIS
```

---

## Next Steps to Fix

1. **Locate group command handlers** in mqtt_client.py
2. **Add `sync_group_switches()` call** after group commands
3. **Implement or verify `sync_group_switches()`** function:
   - Get all member devices of the group
   - Query current state of each member
   - Publish updated state to MQTT for each switch
4. **Run E2E test** to verify fix works
5. **Test with real devices** to ensure no performance issues

---

## Why It Wasn't Fixed

During the logging implementation session, we focused on:
- Creating the logging infrastructure
- Refactoring all Python modules
- Creating E2E test infrastructure
- **Creating the test for Bug 4** ← We did this

But we did NOT:
- Actually implement the fix
- Call `sync_group_switches()` after group commands
- Verify the fix works

The test exists as a regression test for when the bug IS fixed, but the underlying issue remains unresolved.

---

## Testing Strategy

Once the fix is implemented:

1. **Run the E2E test**:
   ```bash
   cd cync-controller
   pytest tests/e2e/test_group_control.py::test_group_turns_off_all_switches -v
   ```

2. **Manual verification**:
   - Open Home Assistant UI
   - Find a group with multiple switches
   - Turn group off
   - Verify all switches show "off" immediately
   - Turn group on
   - Verify all switches show "on" immediately

3. **Performance check**:
   - Monitor logs for timing issues
   - Ensure `sync_group_switches()` doesn't cause delays
   - Check that individual device queries don't overwhelm network

---

## Related Files

**Test**: `cync-controller/tests/e2e/test_group_control.py` (215 lines)
**Implementation Needed**: `cync-controller/src/cync_controller/mqtt_client.py`
**Possible Helper**: `cync-controller/src/cync_controller/server.py` (if sync function lives there)

---

## Conclusion

**Bug 4 Status**: ⚠️ **UNRESOLVED**

We created comprehensive E2E tests that document the expected behavior and provide a regression test for when the fix is implemented. However, the actual code changes to call `sync_group_switches()` after group commands were never applied.

The test exists and is ready to verify the fix, but the bug itself remains in the codebase.

**Estimated effort to fix**: ~30 minutes (locate handlers, add sync calls, test)

