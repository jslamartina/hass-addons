# HTTP Error Logging Improvement Plan

**Date:** October 22, 2025
**Script:** `scripts/setup-fresh-ha.sh`
**Status:** 📋 Planning

---

## Problem

When HTTP API calls fail (non-200 status codes), the script often only logs the HTTP code without showing the response body. This makes debugging difficult because:

- ❌ No error message from the API
- ❌ No context about why the request failed
- ❌ Inconsistent error logging across different functions
- ❌ Some functions capture the body but don't log it

### Example of insufficient logging

```bash
log_warn "EMQX configuration returned HTTP $http_code"
## Missing: What did the API say? Why did it fail?
```text

---

## Current State Analysis

### Functions with HTTP Calls

| Function                                 | Line(s) | Current Logging              | Body Captured? | Body Logged?      |
| ---------------------------------------- | ------- | ---------------------------- | -------------- | ----------------- |
| `create_first_user()`                    | 150-182 | ✅ Good - logs body on error | ✅ Yes         | ✅ Yes (line 179) |
| `complete_onboarding()`                  | 201-227 | ✅ Good - logs response      | ✅ Yes         | ✅ Yes (line 220) |
| `configure_emqx()`                       | 414-430 | ❌ Only HTTP code            | ✅ Yes         | ❌ No             |
| `enable_emqx_sidebar()`                  | 438-456 | ❌ Only HTTP code            | ✅ Yes         | ❌ No             |
| `configure_mqtt_integration()`           | 570-620 | ❌ Only HTTP code            | ✅ Yes         | ❌ No             |
| `configure_cync_lan()`                   | 694-712 | ❌ Only HTTP code            | ✅ Yes         | ❌ No             |
| `enable_cync_sidebar()`                  | 721-739 | ❌ Only HTTP code            | ✅ Yes         | ❌ No             |
| `get_ha_auth_token()` (password auth)    | 266-276 | ❌ Silent failure            | ❌ No          | ❌ No             |
| `get_ha_auth_token()` (long-lived token) | 280-295 | ❌ Silent failure            | ❌ No          | ❌ No             |

---

## Solution

### Approach 1: Add Consistent Body Logging (Recommended)

#### Pattern to implement

```bash
local response
response=$(curl -sf -w "\n%{http_code}" -X POST \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  "$URL" \
  -d "$config" 2>&1)

local http_code
http_code=$(echo "$response" | tail -n1)
local body
body=$(echo "$response" | head -n -1)

if [ "$http_code" = "200" ]; then
  log_success "Operation succeeded"
else
  log_warn "Operation failed (HTTP $http_code)"
  # ← ADD THIS
  if [ -n "$body" ]; then
    log_warn "Response body:"
    echo "$body" | jq '.' 2> /dev/null || echo "$body"
  fi
fi
```text

### Benefits

- ✅ Shows full API error message
- ✅ Formatted JSON if possible, raw otherwise
- ✅ Consistent pattern across all functions

### Approach 2: Create Helper Function (Advanced)

Create a reusable function for API calls with built-in error logging:

```bash
## Make HTTP API call with automatic error logging
## Usage: api_call "Description" METHOD URL [DATA] [AUTH_TOKEN]
api_call() {
  local description="$1"
  local method="$2"
  local url="$3"
  local data="$4"
  local auth_token="$5"

  local curl_cmd="curl -sf -w \"\n%{http_code}\" -X $method"
  [ -n "$auth_token" ] && curl_cmd="$curl_cmd -H \"Authorization: Bearer $auth_token\""
  curl_cmd="$curl_cmd -H \"Content-Type: application/json\""
  [ -n "$data" ] && curl_cmd="$curl_cmd -d '$data'"
  curl_cmd="$curl_cmd \"$url\""

  local response
  response=$(eval "$curl_cmd" 2>&1)

  local http_code
  http_code=$(echo "$response" | tail -n1)
  local body
  body=$(echo "$response" | head -n -1)

  # Log results
  if [ "$http_code" = "200" ] || [ "$http_code" = "201" ]; then
    log_info "$description: Success (HTTP $http_code)"
    echo "$body" # Return body to stdout
    return 0
  else
    log_warn "$description: Failed (HTTP $http_code)"
    if [ -n "$body" ]; then
      log_warn "Response body:"
      echo "$body" | jq '.' 2> /dev/null || echo "$body"
    fi
    echo "$body" # Return body even on error (for parsing flow_id, etc)
    return 1
  fi
}

## Usage example:
response=$(api_call "Configure EMQX" "POST" \
  "http://supervisor/addons/$EMQX_SLUG/options" \
  "$config" \
  "$SUPERVISOR_TOKEN")
```text

### Benefits

- ✅ DRY (Don't Repeat Yourself)
- ✅ Consistent logging everywhere
- ✅ Easier to maintain

### Drawbacks

- More complex to implement
- Harder to customize per-function

---

## Implementation Plan

### Phase 1: Quick Wins (Approach 1) ✅ RECOMMENDED

Add body logging to functions that already capture the body but don't log it:

#### 1. `configure_emqx()` (Lines 414-430)

```bash
else
  log_warn "EMQX configuration returned HTTP $http_code"
  # ADD:
  if [ -n "$body" ]; then
    log_warn "Response: $(echo "$body" | jq -c '.' 2>/dev/null || echo "$body")"
  fi
fi
```text

#### 2. `enable_emqx_sidebar()` (Lines 438-456)

```bash
else
  log_warn "EMQX sidebar configuration returned HTTP $http_code"
  # ADD:
  if [ -n "$body" ]; then
    log_warn "Response: $(echo "$body" | jq -c '.' 2>/dev/null || echo "$body")"
  fi
  return 0
fi
```text

#### 3. `configure_mqtt_integration()` - Initial flow (Lines 570-620)

```bash
else
  log_warn "MQTT integration config flow returned HTTP $http_code"
  # ADD:
  if [ -n "$body" ]; then
    log_warn "Response: $(echo "$body" | jq -c '.' 2>/dev/null || echo "$body")"
  fi
fi
```text

#### 4. `configure_mqtt_integration()` - Complete flow (Lines 590-615)

```bash
else
  log_warn "Failed to complete MQTT config (HTTP $complete_http_code)"
  # ADD:
  local complete_body
  complete_body=$(echo "$complete_response" | head -n -1)
  if [ -n "$complete_body" ]; then
    log_warn "Response: $(echo "$complete_body" | jq -c '.' 2>/dev/null || echo "$complete_body")"
  fi
fi
```text

#### 5. `configure_cync_lan()` (Lines 694-712)

```bash
else
  log_warn "Cync Controller configuration returned HTTP $http_code"
  # ADD:
  if [ -n "$body" ]; then
    log_warn "Response: $(echo "$body" | jq -c '.' 2>/dev/null || echo "$body")"
  fi
  log_info "You may need to configure it manually via Home Assistant UI"
fi
```text

#### 6. `enable_cync_sidebar()` (Lines 721-739)

```bash
else
  log_warn "Cync Controller sidebar configuration returned HTTP $http_code"
  # ADD:
  if [ -n "$body" ]; then
    log_warn "Response: $(echo "$body" | jq -c '.' 2>/dev/null || echo "$body")"
  fi
  return 0
fi
```text

#### 7. `get_ha_auth_token()` - Password auth (Lines 266-276)

```bash
temp_token=$(curl -sf -X POST \
  "$HA_URL/auth/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=password&username=$HASS_USERNAME&password=$HASS_PASSWORD" 2>&1 \
  | jq -r '.access_token // empty' 2> /dev/null)

if [ -z "$temp_token" ]; then
  log_warn "Could not create auth token via password authentication"
  # ADD: Capture and log the full response
  local auth_response
  auth_response=$(curl -s -w "\n%{http_code}" -X POST \
    "$HA_URL/auth/token" \
    -H "Content-Type: application/x-www-form-urlencoded" \
    -d "grant_type=password&username=$HASS_USERNAME&password=$HASS_PASSWORD" 2>&1)
  local auth_http_code
  auth_http_code=$(echo "$auth_response" | tail -n1)
  local auth_body
  auth_body=$(echo "$auth_response" | head -n -1)
  log_warn "Password auth failed (HTTP $auth_http_code)"
  if [ -n "$auth_body" ]; then
    log_warn "Response: $(echo "$auth_body" | jq -c '.' 2> /dev/null || echo "$auth_body")"
  fi
  log_info "MQTT integration will need to be configured manually"
  return 1
fi
```text

#### 8. `get_ha_auth_token()` - Long-lived token creation (Lines 280-295)

```bash
long_lived_token=$(curl -sf -X POST \
  "$HA_URL/api/auth/long_lived_access_token" \
  -H "Authorization: Bearer $temp_token" \
  -H "Content-Type: application/json" \
  -d '{"client_name": "Setup Script", "lifespan": 3650}' 2>&1 \
  | jq -r '.access_token // .token // empty' 2> /dev/null)

if [ -n "$long_lived_token" ]; then
  # ... success case
else
  log_warn "Could not create long-lived access token"
  # ADD: Capture and log the full response
  local token_response
  token_response=$(curl -s -w "\n%{http_code}" -X POST \
    "$HA_URL/api/auth/long_lived_access_token" \
    -H "Authorization: Bearer $temp_token" \
    -H "Content-Type: application/json" \
    -d '{"client_name": "Setup Script", "lifespan": 3650}' 2>&1)
  local token_http_code
  token_http_code=$(echo "$token_response" | tail -n1)
  local token_body
  token_body=$(echo "$token_response" | head -n -1)
  log_warn "Token creation failed (HTTP $token_http_code)"
  if [ -n "$token_body" ]; then
    log_warn "Response: $(echo "$token_body" | jq -c '.' 2> /dev/null || echo "$token_body")"
  fi
  log_info "MQTT integration will need to be configured manually"
  return 1
fi
```text

---

### Phase 2: Refactor to Helper Function (Optional)

After Phase 1 is complete and tested, consider refactoring to use a helper function to reduce code duplication.

---

## Testing Checklist

After implementing changes, test scenarios where HTTP errors occur:

- [ ] EMQX configuration fails (e.g., invalid config)
- [ ] MQTT integration already exists (409 Conflict)
- [ ] Auth token is invalid (401 Unauthorized)
- [ ] Endpoint doesn't exist (404 Not Found)
- [ ] Network timeout (captured by curl)
- [ ] JSON parsing errors in response

**Expected:** All error scenarios show:

1. HTTP status code
2. Full response body (formatted if JSON)
3. Clear context about what operation failed

---

## Example Output

### Before

```bash
[setup-fresh-ha.sh] ⚠ EMQX configuration returned HTTP 400
```text

### After

```bash
[setup-fresh-ha.sh] ⚠ EMQX configuration returned HTTP 400
[setup-fresh-ha.sh] ⚠ Response: {"result":"error","message":"Invalid option 'env_vars': expected list, got string"}
```text

**Much better!** Now we know exactly what's wrong.

---

## Formatting Considerations

### Option 1: Compact JSON (Recommended for logs)

```bash
echo "$body" | jq -c '.' 2> /dev/null || echo "$body"
```text

- Single line output
- Easier to grep through logs
- Still readable

### Option 2: Pretty-printed JSON

```bash
echo "$body" | jq '.' 2> /dev/null || echo "$body"
```text

- Multi-line output
- More readable for complex responses
- Takes up more log space

### Option 3: Hybrid

```bash
## For short responses (< 200 chars), use compact
## For long responses, pretty-print
if [ ${#body} -lt 200 ]; then
  echo "$body" | jq -c '.' 2> /dev/null || echo "$body"
else
  echo "$body" | jq '.' 2> /dev/null || echo "$body"
fi
```text

**Recommendation:** Start with Option 1 (compact) for consistency.

---

## Summary

### Changes Needed

- **8 functions** need improved error logging
- **Total lines to add:** ~40-50 lines
- **Complexity:** Low (copy-paste pattern)
- **Risk:** Very low (only adds logging, doesn't change logic)

### Priority

**HIGH** - Debugging API failures is currently very difficult without response bodies.

### Estimated Effort

- Phase 1: 30-45 minutes
- Testing: 15-30 minutes
- Total: ~1 hour

---

**Status:** 📋 Ready to implement
**Recommendation:** Start with Phase 1 (add body logging to existing functions)
