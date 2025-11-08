# MQTT Integration Auto-Configuration

**Date:** October 22, 2025
**Script:** `scripts/setup-fresh-ha.sh`
**Status:** ✅ Implemented

---

## What Was Added

Automated MQTT integration configuration in the fresh Home Assistant setup script, so the MQTT integration is automatically configured and connected to the EMQX broker without manual UI interaction.

## Implementation

### New Function: `configure_mqtt_integration()`

**Location:** `scripts/setup-fresh-ha.sh` lines 452-542

#### What it does

1. Checks if MQTT credentials are available in `hass-credentials.env`
2. Checks if MQTT integration already exists (idempotent)
3. Creates MQTT config entry via Home Assistant config flow API
4. Configures connection to EMQX broker running on localhost:1883

### Configuration

```json
{
  "broker": "localhost",
  "port": 1883,
  "username": "$MQTT_USER", // from hass-credentials.env
  "password": "$MQTT_PASS" // from hass-credentials.env
}
```text

### Workflow Integration

#### Added to main() flow at Step 6.5

```bash
## Step 6: Install and configure EMQX
install_emqx
configure_emqx
enable_emqx_sidebar
start_emqx

## Step 6.5: Configure MQTT integration  ← NEW
configure_mqtt_integration

## Step 7: Install and configure Cync Controller
install_cync_lan
configure_cync_lan
```text

## How It Works

### Config Flow API

The function uses the Home Assistant config flow API to programmatically set up the integration:

1. **Start config flow:**

   ```bash
   POST http://supervisor/core/api/config_entries/flow
   {
     "handler": ["mqtt", null],
     "data": {
       "broker": "localhost",
       "port": 1883,
       "username": "dev",
       "password": "dev"
     }
   }
   ```

```text

1. **Extract flow_id from response**

2. **Complete the flow:**

   ```bash
   POST http://supervisor/core/api/config_entries/flow/{flow_id}
   {}
```text

3. **MQTT integration is now configured and active**

### Credentials Source

Reads from `hass-credentials.env`:

```bash
MQTT_USER=dev
MQTT_PASSWORD=dev
```text

### Idempotency

The function checks if MQTT integration already exists before attempting configuration:

```bash
existing_mqtt=$(curl -H "Authorization: Bearer ${SUPERVISOR_TOKEN}" \
  "http://supervisor/core/api/config_entries/entry" \
  | jq -r '.data[] | select(.domain == "mqtt") | .entry_id')
```text

If found, it skips configuration and logs the existing entry_id.

## Benefits

### Before

1. ❌ User had to manually navigate to Settings → Devices & Services
2. ❌ User had to click "+ Add Integration"
3. ❌ User had to search for "MQTT"
4. ❌ User had to enter broker, port, username, password manually
5. ❌ User had to click "Submit" and wait for connection test

### After

1. ✅ Script automatically configures MQTT integration
2. ✅ Connection credentials pulled from `hass-credentials.env`
3. ✅ No manual UI interaction required
4. ✅ MQTT ready to use immediately after setup completes

## Testing

To test the MQTT integration after setup:

```bash
## 1. Check MQTT integration exists
curl -sf -H "Authorization: Bearer ${SUPERVISOR_TOKEN}" \
  http://supervisor/core/api/config_entries/entry \
  | jq '.data[] | select(.domain == "mqtt")'

## 2. Publish test message via EMQX WebUI
## Navigate to: Settings → Add-ons → EMQX → Open Web UI
## Login with credentials from hass-credentials.env
## Go to: WebSocket → Connect → Publish message to topic

## 3. Subscribe to test in Home Assistant
## Developer Tools → Events → Listen to "mqtt_event"
```text

## Error Handling

The function handles several scenarios gracefully:

1. **No MQTT credentials:** Logs warning and skips (allows manual config later)
2. **MQTT already configured:** Logs info and skips (idempotent)
3. **API call fails:** Logs warning and continues (doesn't block setup)
4. **Config flow fails:** Logs warning and provides manual instructions

**All failures are non-blocking** - setup continues even if MQTT config fails.

## Logging Output

### Success

```text

Configuring MQTT integration...
MQTT integration configured successfully
MQTT Broker: localhost:1883
MQTT Username: dev

```text

### Already configured

```sql

Configuring MQTT integration...
MQTT integration already configured (entry_id: abc123...)

```text

### Missing credentials

```text

Configuring MQTT integration...
MQTT credentials not found in credentials file
Skipping MQTT integration setup

```text

## Updated User Instructions

The post-setup message now reflects automatic MQTT configuration:

```sql

Next steps:

  1. Log in to Home Assistant at <http://localhost:8123>
     Username: dev
     Password: (from hass-credentials.env)

  2. MQTT integration is configured and connected to EMQX  ← UPDATED
     - Access EMQX WebUI via Add-ons page to monitor MQTT traffic

  3. Update Cync Controller configuration with your real Cync credentials...

```text

## Future Enhancements

Potential improvements:

- [ ] Add MQTT integration health check after configuration
- [ ] Automatically subscribe to test topics
- [ ] Configure MQTT discovery prefix if non-default
- [ ] Add retry logic for config flow failures
- [ ] Support advanced MQTT options (TLS, QoS, etc.)

## Files Modified

- `scripts/setup-fresh-ha.sh`
  - Lines 452-542: New `configure_mqtt_integration()` function
  - Line 841: Added function call in main workflow
  - Lines 861-862: Updated post-setup instructions

## Related

- **EMQX Setup:** Lines 265-450 in `setup-fresh-ha.sh`
- **Cync Controller Config:** Lines 568-624 (uses same MQTT credentials)
- **Credentials File:** `hass-credentials.env` (MQTT_USER, MQTT_PASSWORD)

---

**Status:** ✅ Implemented and ready to use
**Tested:** Pending user testing with fresh setup
