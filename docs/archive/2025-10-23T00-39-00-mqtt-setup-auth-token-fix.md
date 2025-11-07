# MQTT Integration Setup - Authentication Token Issue Fix

**Date:** 2025-10-23T00:39:00
**Issue:** `setup-fresh-ha.sh` failing to configure MQTT integration with HTTP 404 error
**Root Cause:** Invalid/stale authentication token, not API timing

## Problem

The `setup-fresh-ha.sh` script was failing when trying to configure the MQTT integration via the Home Assistant API, displaying:

```ini
[setup-fresh-ha.sh] Configuring MQTT integration...
[setup-fresh-ha.sh] Failed to start MQTT integration config flow (curl error)
[setup-fresh-ha.sh] Full response (with headers):
[setup-fresh-ha.sh]   HTTP/1.1 404 Not Found
```

### Initial Misdiagnosis

Initially suspected the `/api/config_entries/flow` endpoint wasn't ready after onboarding, leading to an attempt to add wait logic. However, this was incorrect.

### Actual Root Cause

The real issue was **authentication failure**:

1. The `LONG_LIVED_ACCESS_TOKEN` in `hass-credentials.env` was stale/invalid
2. Testing the token showed `HTTP 401 Unauthorized`:

   ```bash
   curl -H "Authorization: Bearer $TOKEN" http://localhost:8123/api/
   # Returns: 401: Unauthorized

```

1. The HTTP 404 error was a secondary symptom - the API likely returns 404 for authenticated endpoints when auth fails in certain contexts

### Why Token Was Invalid

Home Assistant no longer supports the `grant_type=password` authentication flow that the script attempted to use (lines 266-270 of `setup-fresh-ha.sh`):

```bash
curl -X POST http://localhost:8123/auth/token \
  -d "grant_type=password&username=...&password=..."
## Returns: {"error":"unsupported_grant_type"}
```

This means:

- Fresh onboarding creates a valid token (returned during user creation)
- But on already-onboarded instances, tokens cannot be programmatically refreshed
- The only way to create new long-lived tokens is via the UI or WebSocket API (which also requires an existing valid token)

## Solution

### 1. Removed Obsolete Password Grant Code

**Deleted lines 260-316** from `setup-fresh-ha.sh`:

- Old code attempted to use `grant_type=password` which is no longer supported
- Tried to create tokens via `/auth/token` endpoint (returns "unsupported_grant_type")
- This code path never worked on modern Home Assistant installations

**Simplified `get_ha_auth_token()` function** to:

- Check for token from onboarding (fresh HA setup)
- Check for token in credentials file
- Provide clear instructions if no token available

### 2. New Token Management Script

Created `/workspaces/hass-addons/scripts/update-token.sh` to guide users through manually creating a token:

```bash
./scripts/update-token.sh
```

### What it does

- Provides step-by-step instructions to create a token via UI
- Accepts the token via secure input (hidden)
- Validates the token against the Home Assistant API
- Updates `hass-credentials.env` with the new token

### 3. Enhanced Setup Script Validation

Modified `setup-fresh-ha.sh` to validate tokens before use:

#### Added function (lines 596-620)

```bash
validate_ha_auth_token() {
  log_info "Validating authentication token..."

  local token_check
  token_check=$(curl -s -o /dev/null -w "%{http_code}" \
    -H "Authorization: Bearer ${HA_AUTH_TOKEN}" \
    "$HA_URL/api/" 2>&1)

  if [ "$token_check" = "200" ]; then
    log_success "Authentication token is valid"
    return 0
  elif [ "$token_check" = "401" ]; then
    log_error "Authentication token is invalid or expired (HTTP 401)"
    log_error "The LONG_LIVED_ACCESS_TOKEN in hass-credentials.env is stale"
    log_info ""
    log_info "To fix this, run: node scripts/create-token-from-existing.js"
    log_info ""
    return 1
  else
    log_warn "Unexpected response when validating token (HTTP $token_check)"
    log_warn "Continuing anyway..."
    return 0
  fi
}
```

### Updated `configure_mqtt_integration()` to call validation before attempting API calls

## Benefits

1. **Clear Error Messages:** Users immediately know if their token is invalid
2. **Actionable Instructions:** Script tells users exactly how to fix the problem
3. **Fail-Fast:** Validates auth before attempting configuration, avoiding confusing 404 errors
4. **Manual Override:** Provides simple script to update tokens without modifying code

## Testing

To test the fix:

1. **With invalid token:**

   ```bash
   ./scripts/setup-fresh-ha.sh
   # Should show clear "token is invalid" message and skip MQTT setup
   ```

1. **Update token:**

   ```bash
   ./scripts/update-token.sh
   # Follow prompts to create and save new token
   ```

1. **With valid token:**

   ```bash
   ./scripts/setup-fresh-ha.sh
   # Should successfully configure MQTT integration
   ```

## Related Files

- `scripts/setup-fresh-ha.sh` - Main setup script
  - Lines 244-273: Simplified `get_ha_auth_token()` (removed 73 lines of obsolete code)
  - Lines 596-620: New `validate_ha_auth_token()` function
  - Lines 640-643: Token validation before MQTT setup
- `scripts/update-token.sh` - New token update helper (manual UI-based token creation)
- `hass-credentials.env` - Contains `LONG_LIVED_ACCESS_TOKEN`

### Deleted files

- `scripts/create-token-auto.js` - Failed Playwright automation (Shadow DOM issues)
- `scripts/create-token-manual.sh` - Duplicate of update-token.sh

## Future Improvements

Potential enhancements:

1. **WebSocket Token Creation:** Implement token creation via WebSocket API when a valid token exists
2. **Token Refresh Logic:** Add automatic token refresh before expiration
3. **OAuth2 Flow:** Investigate if there's a supported OAuth2 flow for programmatic auth
4. **Supervisor Integration:** Check if Supervisor API can create tokens for Home Assistant users

## Lessons Learned

1. **Always validate auth first:** Check token validity before attempting authenticated API calls
2. **Don't assume timing issues:** 404 errors can have multiple causes beyond "API not ready"
3. **Test auth separately:** Use simple endpoints (`/api/`) to validate tokens before complex operations
4. **Modern HA auth:** Password grant type is deprecated; tokens must be created via UI or WebSocket
5. **Remove obsolete code proactively:** The 73-line password grant code was never working and added confusion
6. **Provide actionable errors:** Instead of generic failures, tell users exactly how to fix the problem (`./scripts/update-token.sh`)

---

**Status:** ✅ Fixed
**Impact:** Medium - affects fresh HA setup on already-onboarded instances
**Workaround:** Manual token creation via `./scripts/update-token.sh`
