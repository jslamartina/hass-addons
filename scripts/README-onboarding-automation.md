# Onboarding Automation Script

Python script to automate Home Assistant onboarding using the reverse-engineered HTTP REST API protocol.

## Usage

```bash
# Basic usage (uses default credentials from hass-credentials.env)
python3 scripts/automate-onboarding.py

# With custom URL
HA_URL=http://localhost:8123 python3 scripts/automate-onboarding.py

# With custom credentials
HA_URL=http://localhost:8123 \
HASS_USERNAME=dev \
HASS_PASSWORD=dev \
python3 scripts/automate-onboarding.py
```

## Environment Variables

### Required
- `HA_URL` - Home Assistant URL (default: `http://localhost:8123`)
- `HASS_USERNAME` - Username for authentication (default: `dev`)
- `HASS_PASSWORD` - Password for authentication (default: `dev`)

### Optional Location Configuration
- `ONBOARDING_LATITUDE` - Latitude (default: `41.8781` - Chicago)
- `ONBOARDING_LONGITUDE` - Longitude (default: `-87.6298` - Chicago)
- `ONBOARDING_ELEVATION` - Elevation in meters (default: `181`)
- `ONBOARDING_UNIT_SYSTEM` - Unit system: `imperial` or `metric` (default: `imperial`)
- `ONBOARDING_TIME_ZONE` - IANA timezone (default: `America/Chicago`)

### Optional Analytics
- `ONBOARDING_ANALYTICS` - Enable analytics: `true` or `false` (default: `false`)

### Authentication
- `LONG_LIVED_ACCESS_TOKEN` - Existing long-lived token
- `ONBOARDING_TOKEN` - Onboarding token (fallback)

## How It Works

Based on reverse-engineered protocol analysis:

1. **Check Status**: `GET /api/onboarding` - Discover incomplete steps
2. **Complete Steps**: `POST /api/onboarding/{step}` - Complete each step via HTTP
3. **Verify**: `GET /api/onboarding` - Confirm all steps completed

### Supported Steps

- `core_config` - Location configuration (latitude, longitude, elevation, units, timezone)
- `analytics` - Analytics preferences (opt-in/opt-out)
- `integration` - Integration setup (if applicable)
- `user` - User creation (handled separately, not by this script)

## Features

- ✅ Uses HTTP REST API (simpler, no WebSocket overhead)
- ✅ Automatic token retrieval from credentials file
- ✅ Fallback token creation via WebSocket script
- ✅ Graceful error handling with restart suggestions
- ✅ Configurable location and preferences
- ✅ Verification of completion

## Error Handling

- **HTTP 200/201**: Success
- **HTTP 400**: Initialization issue, may need HA restart
- **HTTP 401**: Unauthorized (invalid token)
- **HTTP 403**: Already completed
- **HTTP 404**: Onboarding complete (endpoint unavailable)

## Examples

### Default (Chicago)
```bash
python3 scripts/automate-onboarding.py
```

### Custom Location
```bash
ONBOARDING_LATITUDE=40.7128 \
ONBOARDING_LONGITUDE=-74.0060 \
ONBOARDING_TIME_ZONE=America/New_York \
ONBOARDING_UNIT_SYSTEM=imperial \
python3 scripts/automate-onboarding.py
```

### Enable Analytics
```bash
ONBOARDING_ANALYTICS=true \
python3 scripts/automate-onboarding.py
```

## Dependencies

```bash
pip install requests
```

## Protocol Reference

See `test-results/ONBOARDING_PROTOCOL.md` for complete protocol specification.

## Related Scripts

- `scripts/setup-fresh-ha.sh` - Full HA setup including onboarding
- `scripts/create-token-websocket.js` - Token creation via WebSocket
- `scripts/playwright/trace-onboarding-websocket.ts` - WebSocket trace capture


