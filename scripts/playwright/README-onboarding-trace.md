# Onboarding WebSocket Trace Script

This script automates the Home Assistant onboarding process while capturing all WebSocket messages and HTTP requests for reverse engineering analysis.

## Usage

### Run the Trace Script

```bash
# Run with headed browser (visible)
npx playwright test scripts/playwright/trace-onboarding-websocket.ts --headed

# Run headless (faster, no UI)
npx playwright test scripts/playwright/trace-onboarding-websocket.ts

# Run with custom URL and credentials
HA_BASE_URL=http://localhost:8123 \
HA_USERNAME=dev \
HA_PASSWORD=dev \
npx playwright test scripts/playwright/trace-onboarding-websocket.ts --headed
```

### Environment Variables

- `HA_BASE_URL`: Home Assistant base URL (default: `http://localhost:8123`)
- `HA_USERNAME`: Login username (default: `dev`)
- `HA_PASSWORD`: Login password (default: `dev`)

## Output Artifacts

All outputs are saved to `test-results/`:

### 1. WebSocket Trace
**File**: `test-results/onboarding-websocket-trace.json`

Contains all WebSocket messages with:
- Timestamp
- Direction (sent/received)
- Current onboarding step context
- Parsed message object
- Raw message string

### 2. Network Requests
**File**: `test-results/onboarding-network-requests.json`

Contains all HTTP API requests with:
- Timestamp
- Request method and URL
- Request/response headers
- Request/response bodies
- HTTP status codes

### 3. Screenshots
**Directory**: `test-results/onboarding-steps-screenshots/`

Screenshots captured at key points:
- `initial-{step}.png` - Initial state
- `after-login.png` - After login
- `core_config-before.png` - Before location step
- `core_config-after.png` - After location step
- `analytics-before.png` - Before analytics step
- `analytics-after.png` - After analytics step
- `final-{step}.png` - Final state
- `error-state.png` - Error state (if any)

## Features

### WebSocket Monitoring
- Automatically captures all WebSocket frames (sent and received)
- Associates messages with onboarding step context
- Parses JSON messages for easy analysis
- Preserves raw message strings

### Network Request Monitoring
- Captures all API calls to `/api/` and `/onboarding`
- Includes request/response headers and bodies
- Tracks HTTP status codes
- Associates requests with onboarding steps

### UI Automation
- Multi-strategy location picker interaction:
  - Click on map coordinates
  - Fill latitude/longitude inputs
  - Use location search/autocomplete
- Automatic timezone and unit selection
- Analytics opt-out handling
- Robust error handling with retries

### Step Detection
- API-based detection (most reliable)
- UI-based fallback detection
- Support for all onboarding steps:
  - `user` - User creation
  - `core_config` - Location configuration
  - `analytics` - Analytics preferences
  - `complete` - Onboarding finished

## Error Handling

The script includes:
- Automatic retries with exponential backoff
- Graceful error recovery
- Saves trace files even on errors
- Takes error screenshots for debugging
- Comprehensive error logging

## Optional: Browser Extension Tools

For manual/interactive monitoring, you can use browser extension MCP tools:

```typescript
// Example: Manual snapshot capture
mcp_cursor-browser-extension_browser_snapshot()

// Example: Manual network request capture
mcp_cursor-browser-extension_browser_network_requests()
```

However, the automated script already captures all necessary data, so these are optional for manual analysis only.

## Analysis

After running the script, analyze the trace files to:
1. Understand WebSocket message structure and sequence
2. Identify API endpoints used during onboarding
3. Reverse engineer the onboarding protocol
4. Replicate onboarding via API calls

## Troubleshooting

### Script Times Out
- Increase timeout: Modify `test.setTimeout()` in the script
- Check if HA is responsive: `curl http://localhost:8123/api/`

### WebSocket Messages Not Captured
- Ensure page has loaded completely
- Check browser console for WebSocket connection errors
- Verify HA WebSocket API is accessible

### Location Picker Not Found
- Check screenshot: `test-results/onboarding-steps-screenshots/core_config-before.png`
- Verify onboarding UI has loaded
- Try manual interaction to identify selectors

### Analytics Step Skipped
- Script tries multiple opt-out strategies
- Check screenshot to see available buttons
- Manual intervention may be needed

## Notes

- The script assumes you're starting at the "pick a location" screen (core_config step)
- If already logged in, it will skip login and proceed to onboarding
- All timeouts are configurable in the script
- Shadow DOM safe selectors are used throughout (HA uses shadow DOM)


