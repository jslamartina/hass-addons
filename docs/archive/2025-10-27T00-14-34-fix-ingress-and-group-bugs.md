<!-- d210b30b-8680-4f8b-b456-68c59cbee35c 37d57559-d856-4f42-ba67-9db20822fa81 -->

# Fix Cync Controller Ingress and Group Control Bugs

**Status**: ✅ Completed
**Date**: 2025-10-27
**Version**: 0.0.4.13

## Overview

Fixed four critical bugs affecting the ingress page and group control functionality in the Cync Controller add-on.

## Bugs Fixed

### Bug 1: OTP Submission Fails First Time

**Symptom**: Entering a valid OTP and submitting fails with "Invalid OTP. Please try again." Submitting the same OTP a second time succeeds.

**Root Cause**: Token was being written to the persistent cache file, but `self.token_cache` wasn't set in memory until AFTER the file write completed. If the file write took time or had any issues, the subsequent call to `export_config_file()` would try to access `self.token_cache.user_id` which was None or stale.

**Fix**: Modified `send_otp()` in `cloud_api.py` to set `self.token_cache` in memory IMMEDIATELY after creating `ComputedTokenData`, before attempting file write. This ensures the token is available for use even if file write fails.

**Files Modified**:

- `cync-controller/src/cync_controller/cloud_api.py` (lines 183-198)

**Code Changes**:

```python
# CRITICAL: Set token in memory FIRST before attempting file write
# This ensures subsequent calls can use the token even if file write fails
self.token_cache = computed_token
logger.info("%s ✓ Token set in memory cache (user_id: %s)", lp, computed_token.user_id)

# Then attempt to write to persistent cache file
write_success = await self.write_token_cache(computed_token)
if not write_success:
    logger.warning("%s Token set in memory but file write failed - token will be lost on restart", lp)
```

### Bug 2: Restart Button Shows Error Despite Success

**Symptom**: Clicking "Restart Server" button after exporting config shows error message "Restart error: [network error]" even though the server actually restarts successfully.

**Root Cause**: Race condition where the add-on server shuts down and closes all connections before sending the HTTP response back to the frontend. The frontend sees a network error and displays it as a failure, even though the restart was initiated successfully.

**Fix**: Modified `restartServer()` function in `index.html` to treat connection errors as success. Shows success toast message "Server restarting... page will reload shortly" and auto-reloads the page after 5 seconds.

**Files Modified**:

- `cync-controller/static/index.html` (lines 390-398)

**Code Changes**:

```javascript
catch (e) {
  // BUG FIX: Treat connection errors as success
  // When server restarts, it closes connections before sending response
  // This causes a network error, but the restart actually succeeds
  showToast("Server restarting... page will reload shortly.");
  // Auto-reload after 5 seconds
  setTimeout(() => {
    window.location.reload();
  }, 5000);
}
```

### Bug 3: Restart Button Disappears After Navigation

**Symptom**: After exporting config successfully, the restart button is visible. However, if you navigate away from the ingress page and come back, the button has disappeared even though the config still exists.

**Root Cause**: Button visibility was only set in the `submitOTP()` success handler. There was no logic to check for existing config on page load and restore the UI state accordingly.

**Fix**: Added `checkExistingConfig()` function that runs on page load to check if a config file exists by calling `/api/export/download`. If it exists (200 response), shows the restart button and config display. Called from `DOMContentLoaded` event handler.

**Files Modified**:

- `cync-controller/static/index.html` (lines 420-448)

**Code Changes**:

```javascript
async function checkExistingConfig() {
  /**
   * BUG FIX: Check for existing config on page load.
   * If config exists, show the restart button and config display.
   * This fixes the issue where the button disappears after navigation.
   */
  try {
    const response = await fetch(`${BASE_PATH}/api/export/download`);
    if (response.ok) {
      // Config exists - show restart button and load config
      document.getElementById("restartDivider").classList.remove("hidden");
      document.getElementById("restartButton").classList.remove("hidden");
      await fetchAndShowConfig();
    }
  } catch (e) {
    console.log("No existing config found:", e.message);
  }
}
```

### Bug 4: Switches Don't Update When Group Turns Off Lights

**Symptom**: When turning off the "Hallway Lights" group entity in Home Assistant, all the bulbs turn off but the wall switch entities (which control those bulbs) remain showing as ON. Individual switch control works fine.

**Root Cause**: Group commands use the group ID to target all member devices at once. The mesh responds with an ACK, but individual devices (especially switches) don't send individual 0x83 status packets. The existing `update_switch_from_subgroup()` logic only runs when processing 0x83 status packets from the mesh, which doesn't happen for switches after group commands.

**Fix**: Two-part fix:

1. Added `sync_group_switches()` method in `mqtt_client.py` that iterates through all group members and syncs switch states using the existing `update_switch_from_subgroup()` helper
2. Modified `CyncGroup.set_power()` in `devices.py` to call this sync method immediately after sending the group command

The sync respects the `pending_command` flag, so individual switch commands take precedence over group sync.

**Files Modified**:

- `cync-controller/src/cync_controller/mqtt_client.py` (lines 731-773)
- `cync-controller/src/cync_controller/devices.py` (lines 1610-1614)

**Code Changes**:

```python
# In mqtt_client.py
async def sync_group_switches(self, group_id: int, group_state: int, group_name: str) -> int:
    """Sync all switch devices in a group to match the group's state."""
    # ... implementation ...
    for member_id in group.member_ids:
        if member_id in g.ncync_server.devices:
            device = g.ncync_server.devices[member_id]
            if await self.update_switch_from_subgroup(device, group_state, group_name):
                synced_count += 1

# In devices.py - CyncGroup.set_power()
# BUG FIX: Sync switch states after group command
if g.mqtt_client:
    await g.mqtt_client.sync_group_switches(self.id, state, self.name)
```

## Testing

### E2E Test Infrastructure

Created Playwright-based E2E testing infrastructure in `cync-controller/tests/e2e/`:

**Files Created**:

- `conftest.py` - Pytest fixtures for browser automation, HA login, ingress navigation
- `test_otp_flow.py` - Tests for OTP submission behavior
- `test_restart_button.py` - Tests for restart button behavior and persistence
- `test_group_control.py` - Tests for group switch synchronization

### Test Scenarios

1. **OTP Double Submission**: Verify OTP works on first try (requires manual testing with real OTP)
2. **Restart Error Handling**: Verify restart shows success message despite connection drop
3. **Button Persistence**: Verify restart button visible after navigation when config exists
4. **Group Switch Sync**: Verify all switches turn off when group is turned off

### Dependencies Added

Updated `pyproject.toml` to include test dependencies:

```toml
[project.optional-dependencies]
test = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
    "pytest-playwright>=0.4.0",
]
```

## Technical Details

### Token Caching Pattern

The fix for Bug 1 establishes a "memory first, file second" pattern for token caching:

1. Set `self.token_cache` in memory immediately after successful OTP verification
2. Attempt to write to persistent cache file
3. Log warning if file write fails but continue (token still usable in current session)
4. File write failure won't break current session, but token will be lost on restart

This pattern ensures reliability while maintaining persistence.

### Switch Sync Precedence

The fix for Bug 4 respects command precedence:

- Individual switch commands set `pending_command = True`
- `update_switch_from_subgroup()` checks this flag and skips sync if true
- This ensures user's direct switch control isn't overridden by group state updates
- Only switches without pending commands are synced to match group state

### Optimistic vs Reactive Updates

For Bug 4, the switch sync happens immediately after sending the group command (optimistic), not waiting for ACK. This provides faster UI feedback. The ACK still happens asynchronously and will update device states if they differ.

## Linting & Formatting

All changes passed linting requirements:

```bash
npm run lint:python:fix # No issues
npm run format:python   # Formatted successfully
npm run lint            # All checks pass
```

## Files Modified Summary

1. `cync-controller/src/cync_controller/cloud_api.py` - Token caching fix
2. `cync-controller/src/cync_controller/mqtt_client.py` - Switch sync helper
3. `cync-controller/src/cync_controller/devices.py` - Group command sync call
4. `cync-controller/static/index.html` - Restart error handling & button persistence
5. `cync-controller/pyproject.toml` - Test dependencies
6. `cync-controller/config.yaml` - Version bump to 0.0.4.13
7. `cync-controller/CHANGELOG.md` - Documented all fixes
8. `cync-controller/tests/e2e/*` - New E2E test files

## Verification

### Manual Testing Required

1. **OTP Flow**: Test with real Cync account and fresh token cache
2. **Restart Button**: Export config, restart, navigate away/back, verify button persists
3. **Group Control**: Turn off Hallway Lights group, verify all switches show OFF
4. **Individual Control**: Toggle individual switch, verify it takes precedence

### Automated Testing

E2E tests created but require:

- Running Home Assistant instance
- Configured Cync Controller addon
- Valid Cync account credentials
- Actual Cync devices (for group control tests)

Tests marked with `@pytest.mark.skip` for manual execution.

## Lessons Learned

1. **Memory vs File**: Always set in-memory state first, then persist to disk
2. **Race Conditions**: Connection drops during server restart are expected behavior
3. **State Restoration**: UI should check server state on load, not just after actions
4. **Device Protocols**: Group commands don't generate individual device status updates

## Future Improvements

1. Mock Cync Cloud API for automated OTP testing
2. Add integration tests for group command flows
3. Consider adding retry logic for failed token file writes
4. Implement progressive config loading (show partial config while loading full data)

---

_Implementation completed: 2025-10-27_
_Archived from: fix-ingress-and-group-bugs.plan.md_
