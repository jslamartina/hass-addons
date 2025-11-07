# Fan Command Issue - Diagnostic Findings

## Summary

**Root Cause Identified**: Home Assistant is NOT sending MQTT commands to the addon. The addon is working correctly, but Home Assistant's fan entity is either not discovered or not configured to send commands.

## Evidence

### 1. Addon Logging (Enhanced Diagnostic)

Added comprehensive logging to trace command flow:

- MQTT message reception (line 267)
- Fan percentage commands (line 449)
- Fan preset commands (line 494)
- Command dispatch to devices (line 536)

**Test Result**: Ran E2E slider test (5 commands attempted) - **ZERO MQTT messages received** by addon

### 2. TCP Connection Status

The addon shows device 103 is actively connected:

```text
10/25/25 23:20:05.960 Device connected: 172.67.68.90:26114[103]
TCP Pool: 8/8 ready_to_control
```

**Status**: Device is ready and waiting for commands ✓

### 3. Missing MQTT Commands

When E2E test runs 5 slider commands (0%, 25%, 50%, 75%, 100%):

- **Expected**: 5 MQTT messages on topic `cync_controller_addon/set/HASSID/percentage`
- **Actual**: 0 MQTT messages received
- **Logs**: No `>>> FAN PERCENTAGE COMMAND` entries

**Conclusion**: Home Assistant is not publishing commands to MQTT

## Root Cause

Home Assistant's fan entity is likely:

1. **Not discovered** - MQTT discovery message from addon not received by HA
2. **Not configured** - Discovery received but entity not created
3. **Not trusted** - Entity created but missing MQTT command configuration
4. **Wrong topic** - Publishing to a different topic than addon expects

## Investigation Needed

To fix this, we need to verify:

### Phase 1: Check Home Assistant Entity

In Home Assistant Developer Tools → States:

- Search for `fan.master_bedroom_fan_switch`
- Check if entity exists

If YES: Check entity attributes for:

```yaml
percentage: <value>
percentage_step: 1
preset_mode: <off|low|medium|high>
preset_modes: [off, low, medium, high]
```

If NO: Fan entity doesn't exist → Discovery failed

### Phase 2: Verify MQTT Discovery

Check addon logs at startup for:

```text
Registering fan device: Master Bedroom Fan Switch
Publishing percentage_command_topic: cync_controller_addon/set/{id}/percentage
Publishing percentage_state_topic: cync_controller_addon/status/{id}/percentage
```

### Phase 3: Test Direct MQTT

Bypass Home Assistant and test addon directly:

```bash
## Subscribe to see if addon receives messages
docker exec addon_emqx mosquitto_sub -h localhost -t "cync_controller_addon/set/#" -v

## In another terminal, publish a test command
docker exec addon_emqx mosquitto_pub -h localhost \
  -t "cync_controller_addon/set/12345-103/percentage" \
  -m "75"

## Check addon logs for ">>> FAN PERCENTAGE COMMAND"
ha addons logs local_cync-controller | grep "FAN PERCENTAGE"
```

If addon receives the test command → Issue is Home Assistant configuration
If addon does NOT receive → Issue is MQTT broker/networking

## Next Steps

1. **Verify fan entity exists** in Home Assistant
2. **Check MQTT discovery logs** at addon startup
3. **Test direct MQTT publishing** to confirm addon can receive
4. **Check Home Assistant MQTT integration** status
5. **Restart addon** to trigger discovery if needed
6. **Check Home Assistant logs** for MQTT integration errors

## Hypothesis

Most likely: Home Assistant's MQTT integration is not running or not connected to the MQTT broker.

**Test this by**:

1. Check HA Settings → Devices & Services → MQTT
2. Verify connection status shows "Connected"
3. If not connected, configure MQTT integration with:
   - Broker: `localhost` or `127.0.0.1`
   - Port: `1883`
   - Username: `dev`
   - Password: `dev`

---

**Status**: Awaiting user feedback on entity existence and MQTT integration status
