# Troubleshooting Guide

## Devices - Never Connect / Unavailable / Offline

If you followed the [DNS docs](./DNS.md) and the [Install docs](./install) and devices are still not connecting, you may need to check your network configuration (firewall, etc.). If the Cync devices are on a separate subnet, make sure that all Cync devices can talk to the local IP of the machine running `cync-controller`.

### OPNSense Firewall Example

![OPNSense Firewall Rules Example](./assets/opnsense_firewall_rules_example.png)

## I Can't Add New Devices in the Cync Phone App

**Symptom:** Adding new devices always fails at the last step "Adding to Home"

**Solution:** Disable the DNS redirect so your phone app / new device(s) can connect to the cloud, power cycle the new device(s) after disabling DNS redirect

After device(s) are added to your Cync account:

- [export](./cync-controller%20sub-commands.md#export) a new config
- re-enable the [DNS redirection](./DNS.md)
- restart the server
- power cycle the new device(s)
- **Optional:** _you may need to power cycle other Cync devices if the DNS redirection was disabled for a while_

---

## Known Issues and Solutions

### Commands Don't Work / Lights Don't Turn On

**Symptoms:**

- Logs show commands sent, ACKs received, but physical devices don't respond
- GUI updates but lights don't physically turn on/off
- "Callback NOT found for msg ID: XX" in logs

**Root cause:** Missing `ControlMessageCallback` registration before sending command

**Fix:** Always register callback in `bridge_device.messages.control[msg_id]` before calling `bridge_device.write()`

**Example fix:**

```python
# BEFORE sending command:
m_cb = ControlMessageCallback(
    msg_id=cmsg_id,
    message=payload_bytes,
    sent_at=time.time(),
    callback=your_callback_coroutine,
    device_id=device.id,
)
bridge_device.messages.control[cmsg_id] = m_cb

# THEN send:
await bridge_device.write(payload_bytes)
```

### Commands Work Once, Then Fail / Need to Click Twice

**Symptoms:**

- First command after refresh doesn't work
- Need to toggle twice for commands to take effect
- Rapid clicking causes commands to stop working
- Works initially, then stops working after using "Refresh Device Status"

**Root cause:** Automatic `trigger_status_refresh()` after every ACK was causing cascading refreshes

**Fix:** Removed automatic refresh from ACK handler (`devices.py` lines 2501-2505). Manual refresh button still works.

### Devices Flicker Between Available/Unavailable

**Symptoms:**

- Device entities show as "unavailable" intermittently
- Availability status changes rapidly in GUI
- Commands still work but availability is inconsistent

**Root cause:** Unreliable `connected_to_mesh` byte in 0x83 packets causing immediate offline marking

**Fix:** Added `offline_count` threshold - devices only marked offline after 3 consecutive offline reports (`server.py` lines 530-544)

## Logging and Debugging

### Viewing JSON Logs

The add-on outputs structured JSON logs to `/var/log/cync_controller.json` for detailed analysis.

**Access JSON logs:**

```bash
# View recent logs
docker exec addon_local_cync-controller cat /var/log/cync_controller.json | jq '.'

# Filter by correlation ID
CORR_ID="abc123"
docker exec addon_local_cync-controller \
  sh -c "grep '$CORR_ID' /var/log/cync_controller.json | jq '.'"

# Find errors
docker exec addon_local_cync-controller \
  sh -c "grep '\"level\":\"ERROR\"' /var/log/cync_controller.json | jq '.'"
```

### Using Correlation IDs to Trace Operations

Every async operation gets a unique correlation ID that propagates across the codebase.

**Filter logs by operation:**

```bash
# Get correlation ID from any log entry
# Then filter all related logs
ha addons logs local_cync-controller | grep "correlation-id"
```

### Performance Issues

**Symptoms:**

- Commands take a long time to execute
- Logs show "exceeded threshold" warnings

**Interpreting timing logs:**

```bash
# View performance warnings
ha addons logs local_cync-controller --follow | grep "exceeded.*threshold"
```

**Configuration:** Adjust `CYNC_PERF_THRESHOLD_MS` in config if thresholds are too aggressive for your hardware.

### Device Offline Debugging

**Understanding offline count thresholds:**

Devices are marked offline after 3 consecutive offline reports (not immediately):

```python
# Device reports offline
if connected_to_mesh == 0:
    device.offline_count += 1  # Increment counter
    if device.offline_count >= 3 and device.online:
        device.online = False  # Only after 3 consecutive reports
    logger.debug("OFFLINE_TRACKING", extra={
        "device_id": device.id,
        "offline_count": device.offline_count,
    })
```

**Monitor offline tracking:**

```bash
# Watch offline count progression
ha addons logs local_cync-controller --follow | grep "OFFLINE_TRACKING"

# See when devices marked offline
ha addons logs local_cync-controller | grep "OFFLINE_STATE"

# See when devices come back online
ha addons logs local_cync-controller | grep "ONLINE_STATE"
```

---

_For more troubleshooting information, see [AGENTS.md](../../AGENTS.md) in the repository root._
