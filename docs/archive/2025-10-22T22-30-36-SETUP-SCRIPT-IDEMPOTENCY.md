# Setup Script Idempotency Improvements

**Date:** October 22, 2025
**File:** `scripts/setup-fresh-ha.sh`

## Status:**✅**IMPROVED - Now idempotent

---

## Problem

The `setup-fresh-ha.sh` script was designed only for fresh Home Assistant installations and would **timeout when run on an already-onboarded HA instance**.

### What Was Happening

1. Script tries to check if HA API is ready by testing `/api/onboarding`
2. On fresh HA: ✅ Endpoint exists and responds without auth
3. On onboarded HA: ❌ Endpoint doesn't exist or requires auth
4. Script waits 30 × 5 seconds = **150 seconds** for endpoint to respond
5. Finally times out with error: `Home Assistant API not responsive after 30 attempts`

## Solution

Made the script **idempotent** so it can run on both fresh AND already-configured Home Assistant instances.

### Changes Made

#### 1. `wait_for_ha()` Function (Lines 84-106)

#### Before

```bash
while [ $retry_count -lt $max_retries ]; do
  # Only checks onboarding endpoint
  if curl -sf "$HA_URL/api/onboarding" > /dev/null 2>&1; then
    log_success "Home Assistant API is responsive"
    return 0
  fi

  # Times out if endpoint doesn't exist...
done
```

### After

```bash
while [ $retry_count -lt $max_retries ]; do
  # Check if onboarding endpoint responds (for fresh HA)
  if curl -sf "$HA_URL/api/onboarding" > /dev/null 2>&1; then
    log_success "Home Assistant API is responsive (onboarding available)"
    return 0
  fi

  # NEW: Fallback check for already-onboarded HA
  local api_check
  api_check=$(curl -s -o /dev/null -w "%{http_code}" "$HA_URL/api/" 2>&1)
  if [ "$api_check" = "401" ] || [ "$api_check" = "200" ]; then
    log_success "Home Assistant API is responsive (already onboarded)"
    return 0
  fi

  # Continue waiting...
done
```

### Key Addition

- Tests `/api/` endpoint which exists on both fresh AND onboarded HA
- HTTP 401 (Unauthorized) = HA is running but requires auth (onboarded)
- HTTP 200 (OK) = HA is running and accessible
- Both cases mean "HA is ready" → script continues

## Idempotency Status

The script is now idempotent for all major steps:

| Step                 | Function                       | Idempotent? | How                                          |
| -------------------- | ------------------------------ | ----------- | -------------------------------------------- |
| **Wait for HA**      | `wait_for_ha()`                | ✅ YES      | Checks both onboarding AND core API          |
| **Onboarding**       | `check_onboarding_status()`    | ✅ YES      | Returns false if already done (line 127-129) |
| **User Creation**    | `create_first_user()`          | ✅ YES      | Skipped if onboarding not needed             |
| **Supervisor Token** | `get_supervisor_token()`       | ✅ YES      | Uses existing env var if available           |
| **Add EMQX Repo**    | `add_emqx_repository()`        | ✅ YES      | Checks if repo already exists (line 261)     |
| **Install EMQX**     | `install_emqx()`               | ✅ YES      | Checks if already installed (line 293-297)   |
| **Configure EMQX**   | `configure_emqx()`             | ✅ YES      | Updates options (safe to re-run)             |
| **Start EMQX**       | `start_emqx()`                 | ✅ YES      | Checks current state first (line 399-402)    |
| **Configure MQTT**   | `configure_mqtt_integration()` | ✅ YES      | Checks if integration exists (line 464-472)  |
| **Install Cync**     | `install_cync_lan()`           | ✅ YES      | Checks if already installed (line 554-562)   |
| **Configure Cync**   | `configure_cync_lan()`         | ✅ YES      | Updates options (safe to re-run)             |
| **Start Cync**       | `start_cync_lan()`             | ✅ YES      | Checks current state first                   |

## Testing

### Test 1: Fresh Home Assistant

```bash
## Start with completely reset HA
./scripts/setup-fresh-ha.sh
```

## Expected

- ✅ Waits for `/api/onboarding` to respond
- ✅ Creates first user
- ✅ Completes onboarding
- ✅ Installs and configures everything

### Test 2: Already-Onboarded Home Assistant

```bash
## Run on existing configured HA
./scripts/setup-fresh-ha.sh
```

## Expected

- ✅ Detects HA is responsive via `/api/` (HTTP 401)
- ✅ Skips onboarding ("already completed")
- ✅ Checks if EMQX already installed → uses existing or installs
- ✅ Checks if MQTT integration exists → skips if present
- ✅ Checks if Cync Controller installed → uses existing or installs
- ✅ Script completes successfully without errors

### Test 3: Partial Setup

```bash
## Run after some components already installed
./scripts/setup-fresh-ha.sh
```

## Expected

- ✅ Skips already-completed steps
- ✅ Completes missing steps
- ✅ No duplicate installations
- ✅ No errors about "already exists"

## Benefits

### Before (Non-Idempotent)

- ❌ Only worked on fresh HA
- ❌ Timed out on existing HA (150 second wait)
- ❌ Couldn't resume from failures
- ❌ Couldn't re-run for updates

### After (Idempotent)

- ✅ Works on both fresh AND existing HA
- ✅ No timeouts (detects HA state quickly)
- ✅ Can resume from any failure point
- ✅ Safe to re-run for configuration updates
- ✅ Can be used to "repair" partial setups

## Script Behavior Summary

### On Fresh Home Assistant

1. Waits for `/api/onboarding` endpoint
2. Creates first user and completes onboarding
3. Installs EMQX, MQTT integration, Cync Controller
4. **Result:** Fully configured HA

### On Already-Onboarded HA

1. Detects HA is running via `/api/` (HTTP 401)
2. Skips onboarding (already done)
3. Checks each component:
   - **Exists?** → Skip or update config
   - **Missing?** → Install and configure

4. **Result:** Missing components added, existing ones preserved

## Error Handling

The script remains robust with graceful fallbacks:

```bash
## Example: MQTT integration fails to configure
configure_mqtt_integration || {
  log_warn "MQTT integration setup failed"
  log_info "You may need to configure manually"
  # Script continues - doesn't block other components
}
```

Most functions:

- ✅ Check prerequisites before running
- ✅ Return success if already done
- ✅ Log warnings instead of failing
- ✅ Continue script execution

## Use Cases Enabled

**1. Fresh Setup** (original use case)

```bash
## Clean HA → Full setup
./scripts/setup-fresh-ha.sh
```

## 2. Repair Incomplete Setup

```bash
## EMQX failed to install? Re-run the script
./scripts/setup-fresh-ha.sh
## Will skip completed steps, finish EMQX setup
```

## 3. Update Configurations

```bash
## Changed MQTT credentials in hass-credentials.env
./scripts/setup-fresh-ha.sh
## Updates addon configs with new credentials
```

## 4. Add Missing Components

```bash
## Manually deleted MQTT integration? Re-run:
./scripts/setup-fresh-ha.sh
## Will reinstall just the MQTT integration
```

## 5. DevContainer Startup

```bash
## Run automatically in post-start.sh
## Safe to run every time container starts
./scripts/setup-fresh-ha.sh
```

## Files Modified

- `scripts/setup-fresh-ha.sh`
  - Lines 85-98: Updated `wait_for_ha()` with fallback API check
  - Added HTTP 401/200 detection for already-onboarded HA

## Related Documentation

- Switch status fix: `SWITCH-STATUS-FIX-SUMMARY.md`
- MQTT integration: `MQTT-INTEGRATION-AUTO-CONFIG.md`
- Script overview: `scripts/README.md` (if exists)

---

**Status:** ✅ Script is now fully idempotent and can safely run multiple times
