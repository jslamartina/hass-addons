# Automated Long-Lived Access Token Creation

**Status:** ✅ Implemented
**Approach:** WebSocket API with existing token bootstrap
**Goal:** Fully automated token creation without manual intervention

## Overview

The system automatically creates Home Assistant long-lived access tokens using the official WebSocket API. It uses an existing token (from onboarding or credentials file) to bootstrap the creation of a new long-lived token.

## How It Works

### 1. **Fresh Onboarding**

- Home Assistant onboarding creates first user
- Returns short-lived access token
- Token is **immediately saved as `ONBOARDING_TOKEN`** in `hass-credentials.env`

### 2. **Bootstrap Long-Lived Token Creation**

- `setup-fresh-ha.sh` checks for `ONBOARDING_TOKEN` (fresh from onboarding)
- Passes it to `create-token-from-existing.js` via `EXISTING_TOKEN` env var
- Script validates token with Home Assistant API
- If valid → proceeds to WebSocket token creation

### 3. **WebSocket Token Creation**

- Connects to `ws://localhost:8123/api/websocket`
- Authenticates with onboarding token
- Sends `auth/long_lived_access_token` request
- Receives new long-lived token (10-year lifespan)

### 4. **Long-Lived Token Replacement**

- New LLAT saved as `LONG_LIVED_ACCESS_TOKEN` in `hass-credentials.env`
- Replaces the temporary onboarding token
- LLAT used for all subsequent API calls

## Implementation

### Core Script: `scripts/create-token-from-existing.js`

```javascript
// 1. Load existing token from environment variable
const EXISTING_TOKEN = process.env.EXISTING_TOKEN;

// 2. Validate token
const testResponse = await fetch(`${HA_URL}/api/`, {
  headers: { Authorization: `Bearer ${EXISTING_TOKEN}` },
});

// 3. Create long-lived token via WebSocket
const ws = new WebSocket(WS_URL);
ws.send(
  JSON.stringify({
    type: "auth",
    access_token: EXISTING_TOKEN,
  }),
);
ws.send(
  JSON.stringify({
    id: 1,
    type: "auth/long_lived_access_token",
    client_name: "Setup Script",
    lifespan: 3650,
  }),
);
```

### Integration: `scripts/setup-fresh-ha.sh`

```bash
# During fresh onboarding
create_first_user() {
  # Create user via onboarding API, get short-lived token
  local auth_token=$(curl -X POST "$HA_URL/api/onboarding/users" ...)
  echo "$auth_token"
}

# Save onboarding token
ONBOARDING_TOKEN="$(create_first_user)"
echo "ONBOARDING_TOKEN=$ONBOARDING_TOKEN" >> hass-credentials.env

# Later, when needing long-lived token
get_ha_auth_token() {
  # Use onboarding token to bootstrap LLAT creation
  if [ -n "$ONBOARDING_TOKEN" ]; then
    local new_token=$(EXISTING_TOKEN="$ONBOARDING_TOKEN" node scripts/create-token-from-existing.js)
    HA_AUTH_TOKEN="$new_token"
    # Save as long-lived token
    echo "LONG_LIVED_ACCESS_TOKEN=$new_token" >> hass-credentials.env
    return 0
  fi

  # Fallback: use existing LLAT if available
  if [ -n "$LONG_LIVED_ACCESS_TOKEN" ]; then
    HA_AUTH_TOKEN="$LONG_LIVED_ACCESS_TOKEN"
    return 0
  fi
}
```

## Usage

### Automatic (Recommended)

```bash
# Setup script automatically creates tokens when needed
./scripts/setup-fresh-ha.sh
```

### Direct Token Creation

```bash
# Create token directly from existing token
node scripts/create-token-from-existing.js
```

## Requirements

### For Fresh HA Setup

- ✅ **Onboarding creates initial token**
- ✅ **Token immediately saved as `ONBOARDING_TOKEN`**
- ✅ **LLAT created automatically from onboarding token**

### For Already-Onboarded HA (Fallback)

- ✅ **Valid `LONG_LIVED_ACCESS_TOKEN` in `hass-credentials.env`**
- ✅ **Token must authenticate successfully**
- ⚠️ **Cannot create new LLAT if existing one is expired**

## Error Handling

### Missing Environment Variable

```
❌ No existing token found in environment (EXISTING_TOKEN)
💡 This script requires an existing token to bootstrap LLAT creation
```

### Invalid Token

```
❌ Existing token is invalid (HTTP 401)
💡 Please ensure token passed via EXISTING_TOKEN environment variable is valid
```

### WebSocket Failure

```
❌ Failed to create token: {"type":"result","success":false,"error":"..."}
```

## Benefits

✅ **Fully automated** - No manual intervention required
✅ **Uses official API** - WebSocket `auth/long_lived_access_token`
✅ **Long lifespan** - 10-year tokens (3650 days)
✅ **Seamless integration** - Works with existing setup script
✅ **Fresh bootstrap** - Uses onboarding token, not stale credentials
✅ **Clear error messages** - Tells users exactly what to fix

## Technical Details

### WebSocket Protocol

- **Endpoint:** `ws://localhost:8123/api/websocket`
- **Authentication:** `{"type":"auth","access_token":"..."}`
- **Token Creation:** `{"type":"auth/long_lived_access_token","client_name":"Setup Script","lifespan":3650}`

### Token Format

- **Type:** JWT (JSON Web Token)
- **Prefix:** `eyJ` (base64 encoded JSON header)
- **Lifespan:** 3650 days (10 years)
- **Usage:** Bearer token in Authorization header

### Token Lifecycle

1. **Onboarding Token** - Short-lived, created by onboarding
2. **Saved as `ONBOARDING_TOKEN`** - For bootstrapping LLAT creation
3. **Long-Lived Token** - Created via WebSocket
4. **Saved as `LONG_LIVED_ACCESS_TOKEN`** - For all subsequent API calls

## Usage Scenarios

### Fresh HA Setup (Recommended)

```bash
./scripts/setup-fresh-ha.sh
# Automatically handles onboarding and token creation
```

### With Existing LLAT

```bash
# Fallback mode - uses existing token if available
HA_AUTH_TOKEN="$LONG_LIVED_ACCESS_TOKEN" node scripts/create-token-from-existing.js
```

### Direct Bootstrap

```bash
# Pass any valid token via environment variable
EXISTING_TOKEN="$ONBOARDING_TOKEN" node scripts/create-token-from-existing.js
```

---

**Last Updated:** 2025-10-23
**Status:** Production Ready
**Maintainer:** AI Agent
