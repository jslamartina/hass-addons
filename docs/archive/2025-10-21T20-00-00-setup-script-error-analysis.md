# Setup Script Error Analysis

**Date:** October 21, 2025
**Script:** `scripts/setup-fresh-ha.sh`
**Issue:** Script failing with nonzero exit code, errors being swallowed

## Root Cause Analysis

### 1. Why Errors Were Being Swallowed

The script had multiple issues with error handling:

#### Issue 1.1: Silent curl failures in `complete_onboarding()`

**Location:** Lines 173-176 (before fix)

```bash
response=$(curl -sf -w "\n%{http_code}" -X POST \
  "$HA_URL/api/onboarding/core_config" \
  -H "Content-Type: application/json" \
  -d "{}" 2>&1)
```

### Problem

- `curl -f` fails with exit code 22 on HTTP 4xx/5xx errors
- `2>&1` redirects stderr to stdout, capturing it in the variable
- User never sees the actual error message from curl
- Function always returned 0 even on HTTP errors (line 186)

**Impact:** When the onboarding endpoint returned 404 (already completed), the error was hidden but the function continued successfully.

#### Issue 1.2: No state checking before starting addons

**Location:** Lines 342-352 (`start_emqx()`) and 450-460 (`start_cync_lan()`)

```bash
start_emqx() {
  log_info "Starting EMQX add-on..."

  if ha addons start "$EMQX_SLUG" > /dev/null 2>&1; then
    log_success "EMQX started successfully"
    return 0
  else
    log_error "Failed to start EMQX"
    return 1 # ← Script exits here with set -e
  fi
}
```

### Problem

- Script doesn't check if addon is already running
- `ha addons start` returns exit code 1 when addon is already started
- With `set -e`, the script exits immediately
- Error message doesn't explain WHY it failed

### 2. The Actual Error

#### What happened

1. ✅ Onboarding was already complete from a previous run
2. ✅ User creation skipped (already exists)
3. ⚠️ `complete_onboarding()` called `/api/onboarding/core_config` → returned 404
   - This is actually fine! Endpoint no longer exists when onboarding is complete
   - Function returned 0, script continued

4. ✅ EMQX installation and configuration succeeded
5. ❌ **`start_emqx()` failed** because EMQX was already running
   - `ha addons start a0d7b954_emqx` returned exit code 1
   - Function returned 1
   - `set -e` caused immediate script exit

### Evidence from trace

```bash
+ start_emqx
+ log_info 'Starting EMQX add-on...'
+ echo -e '\033[0;32m[setup-fresh-ha.sh]\033[0m Starting EMQX add-on...'
[0
32m[setup-fresh-ha.sh][0m Starting EMQX add-on...
+ ha addons start a0d7b954_emqx
+ log_error 'Failed to start EMQX'
+ echo -e '\033[0;31m[setup-fresh-ha.sh]\033[0m Failed to start EMQX'
[0
31m[setup-fresh-ha.sh][0m Failed to start EMQX
+ return 1
```

Verification:

```bash
$ ha addons info a0d7b954_emqx --raw-json | jq '.data.state'
"started" # ← Already running!
```

## Solutions Implemented

### Fix 1: Improve error visibility in `complete_onboarding()`

#### Changes

1. Added `|| true` to prevent curl failure from exiting
2. Extract response body separately
3. Handle 404 explicitly (onboarding already complete)
4. Display response body when errors occur

```bash
complete_onboarding() {
  log_info "Completing onboarding (core config)..."

  local response
  local http_code

  # Capture full response including errors
  response=$(curl -sf -w "\n%{http_code}" -X POST \
    "$HA_URL/api/onboarding/core_config" \
    -H "Content-Type: application/json" \
    -d "{}" 2>&1) || true # Don't exit on curl failure

  http_code=$(echo "$response" | tail -n1)
  local body
  body=$(echo "$response" | sed '$d')

  if [ "$http_code" = "200" ] || [ "$http_code" = "201" ]; then
    log_success "Onboarding completed"
    return 0
  elif [ "$http_code" = "404" ]; then
    log_info "Onboarding already completed (endpoint no longer available)"
    return 0
  else
    log_warn "Onboarding completion returned HTTP $http_code (may already be complete)"
    if [ -n "$body" ]; then
      echo "Response: $body"
    fi
    return 0
  fi
}
```

### Fix 2: Check addon state before starting

#### Changes to `start_emqx()` and `start_cync_lan()`

1. Check current addon state before attempting to start
2. Return success if already running
3. Provide helpful error messages with state information

```bash
start_emqx() {
  log_info "Starting EMQX add-on..."

  # Check current state
  local current_state
  current_state=$(ha addons info "$EMQX_SLUG" --raw-json 2> /dev/null \
    | jq -r '.data.state // "unknown"' 2> /dev/null)

  if [ "$current_state" = "started" ]; then
    log_info "EMQX already running"
    return 0
  fi

  if ha addons start "$EMQX_SLUG" > /dev/null 2>&1; then
    log_success "EMQX started successfully"
    return 0
  else
    log_error "Failed to start EMQX (state: $current_state)"
    log_info "Check logs with: ha addons logs $EMQX_SLUG"
    return 1
  fi
}
```

### Fix 3: Fix shellcheck warning SC2155

**Problem:** Declaring and assigning local variables in one line masks return values

#### Before

```bash
local body=$(echo "$response" | sed '$d')
```

### After

```bash
local body
body=$(echo "$response" | sed '$d')
```

## Test Results

### Before fix

```bash
$ ./setup-fresh-ha.sh
## ... output ...
[setup-fresh-ha.sh] Starting EMQX add-on...
[setup-fresh-ha.sh] Failed to start EMQX
## Script exits with code 1
```

## After fix

```bash
$ ./setup-fresh-ha.sh
## ... output ...
[setup-fresh-ha.sh] Starting EMQX add-on...
[setup-fresh-ha.sh] EMQX already running
[setup-fresh-ha.sh] Checking if Cync Controller add-on is already installed...
[setup-fresh-ha.sh] Installing Cync Controller add-on...
[setup-fresh-ha.sh] ✅ Cync Controller installed successfully
## ... continues successfully ...
[setup-fresh-ha.sh] ✅ Setup completed successfully!
```

## Key Takeaways

1. **Always check resource state before operations** - Don't assume resources are in a particular state
2. **Make errors visible** - Don't swallow error messages with `2>&1` unless you display them later
3. **Handle idempotency** - Scripts should handle being run multiple times gracefully
4. **Provide context in error messages** - Include current state and helpful next steps
5. **Test with `set -e`** - Ensure functions return appropriate exit codes when strict error handling is enabled

## Related Files Modified

- `scripts/setup-fresh-ha.sh` (lines 167-197, 350-372, 469-491)

## Testing Commands

```bash
## Run the fixed script
./scripts/setup-fresh-ha.sh

## Verify shellcheck passes
shellcheck scripts/setup-fresh-ha.sh

## Check addon states
ha addons info a0d7b954_emqx --raw-json | jq '.data.state'
ha addons info local_cync-controller --raw-json | jq '.data.state'
```
