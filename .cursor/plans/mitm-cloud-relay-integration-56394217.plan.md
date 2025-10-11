<!-- 56394217-30ff-4825-9208-dd9226e0a36a 5d7ed494-f1f2-4871-8def-128de24e931d -->
# Cloud Relay Mode Testing Plan

Systematic validation of all Cloud Relay operating modes with real devices in devcontainer.

## Prerequisites Check

Before testing, verify:

- Git repo changes are committed: `/mnt/supervisor/addons/local/cync-lan/`
- DNS redirection is active for `cm.gelighting.com`
- MQTT broker (EMQX) is running and accessible
- At least one Cync device is powered on and can connect

## Test Structure

Each test follows this pattern:

1. Update add-on configuration
2. Rebuild and restart add-on
3. Monitor logs for device connections
4. Validate MQTT messages in Home Assistant
5. Test device control (on/off, brightness if applicable)
6. Document results

## Phase 1: Baseline - Normal LAN-only Mode

**Purpose:** Verify backward compatibility - existing behavior unchanged.

**Configuration** (`/mnt/supervisor/addons/local/hass-addons/cync-lan/config.yaml` options):

```yaml
cloud_relay:
  enabled: false
```

**Build & Start:**

```bash
cd /mnt/supervisor/addons/local/cync-lan
./rebuild.sh
ha addons logs local_cync-lan --follow
```

**Validation:**

- [ ] Add-on starts without errors
- [ ] Device connects and appears in logs
- [ ] MQTT discovery messages published
- [ ] Device entities appear in Home Assistant
- [ ] Device controls work (toggle on/off)
- [ ] No cloud connection attempts in logs

**Success Criteria:** All existing functionality works as before.

---

## Phase 2: Cloud Relay with Forwarding

**Purpose:** Test transparent proxy mode - devices work through cloud.

**Configuration:**

```yaml
cloud_relay:
  enabled: true
  forward_to_cloud: true
  debug_packet_logging: false
```

**Update & Restart:**

```bash
# Edit options in Home Assistant UI or config file
ha addons restart local_cync-lan
ha addons logs local_cync-lan --follow
```

**Validation:**

- [ ] Add-on starts without errors
- [ ] Device connects to relay
- [ ] Cloud connection established (check logs for SSL handshake)
- [ ] Device shows as online in Home Assistant
- [ ] Commands work (toggle, brightness changes)
- [ ] MQTT state updates still published
- [ ] Logs show minimal packet info (only non-keepalives at debug level)

**Success Criteria:** Devices work normally with cloud backup capability.

---

## Phase 3: Cloud Relay with Debug Logging

**Purpose:** Validate packet inspection and logging features.

**Configuration:**

```yaml
cloud_relay:
  enabled: true
  forward_to_cloud: true
  debug_packet_logging: true
```

**Validation:**

- [ ] Add-on restarts cleanly
- [ ] Detailed packet logs appear (type, seq, device ID, RSSI, etc.)
- [ ] Both device→cloud and cloud→device packets logged
- [ ] Parsed packet structure matches expected format (see `CLOUD_RELAY.md`)
- [ ] Commands still work while logging
- [ ] Performance acceptable (no significant lag)

**Expected Log Format:**

```
[RELAY Device→Cloud] Type: 0x73, Seq: 42, Device: 1234567890, RSSI: -45
[RELAY Cloud→Device] Type: 0x73, Seq: 43, Status update...
```

**Success Criteria:** Detailed packet inspection works without breaking functionality.

---

## Phase 4: LAN-only Relay Mode (No Cloud)

**Purpose:** Test privacy mode - local processing only, no cloud forwarding.

**Configuration:**

```yaml
cloud_relay:
  enabled: true
  forward_to_cloud: false
  debug_packet_logging: true
```

**Validation:**

- [ ] Add-on starts without errors
- [ ] Device connects to relay
- [ ] NO cloud connection established (verify in logs)
- [ ] Packets logged but not forwarded
- [ ] Device works via local MQTT control
- [ ] MQTT state updates published
- [ ] Logs confirm "Cloud forwarding disabled"

**Success Criteria:** Local control works without cloud dependency, packets still inspected.

---

## Phase 5: Packet Injection Testing

**Purpose:** Validate debug packet injection features.

**Configuration:** Keep Phase 3 or 4 config active.

**Test Mode Change Injection:**

```bash
# Get shell in add-on container
docker exec -it addon_local_cync-lan /bin/bash

# Inject "smart" mode command
echo "smart" > /tmp/cync_inject_command.txt

# Wait ~10 seconds, check logs for injection confirmation
# Then inject "traditional" mode
echo "traditional" > /tmp/cync_inject_command.txt
```

**Validation:**

- [ ] Injection file detected (check logs)
- [ ] Mode packet crafted and sent to device
- [ ] Device responds (check response in logs)
- [ ] File deleted after processing

**Test Raw Bytes Injection:**

```bash
# Inject custom 0x73 packet (example, adjust as needed)
echo "73 00 00 00 1e 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00" > /tmp/cync_inject_raw_bytes.txt
```

**Validation:**

- [ ] Raw packet detected and parsed
- [ ] Checksum calculated and inserted
- [ ] Packet sent to device
- [ ] File deleted after processing

**Success Criteria:** Injection mechanism works for debugging/analysis.

---

## Phase 6: SSL Verification Modes

**Purpose:** Test secure vs debug SSL modes.

**Test A - Secure Mode (Default):**

```yaml
cloud_relay:
  enabled: true
  forward_to_cloud: true
  disable_ssl_verification: false
```

**Validation:**

- [ ] SSL connection uses proper verification
- [ ] No security warnings in logs

**Test B - Debug Mode (Insecure):**

```yaml
cloud_relay:
  enabled: true
  forward_to_cloud: true
  disable_ssl_verification: true
```

**Validation:**

- [ ] Security warning appears in logs at startup
- [ ] SSL connection still works (without verification)
- [ ] Warning includes "DEBUG MODE" or similar

**Success Criteria:** Both modes work, debug mode has prominent warnings.

---

## Phase 7: Edge Cases & Error Handling

**Tests:**

1. **Cloud Unreachable** (relay enabled, cloud server down/wrong IP):

   - [ ] Device still connects to relay
   - [ ] Error logged gracefully (no crash)
   - [ ] Local control still works if `forward_to_cloud: false`

2. **Multiple Devices** (if available):

   - [ ] Multiple devices connect simultaneously
   - [ ] Each gets own relay connection
   - [ ] Packet logs clearly identify which device

3. **Mode Switching**:

   - [ ] Switch from LAN-only → Relay mode (restart required)
   - [ ] Switch back to LAN-only (no lingering cloud connections)
   - [ ] Devices reconnect properly after config changes

4. **Long-running Stability**:

   - [ ] Leave relay running for 1+ hour
   - [ ] No memory leaks or connection drops
   - [ ] Devices stay responsive

**Success Criteria:** Graceful error handling, no crashes, stable operation.

---

## Documentation Validation

**Review Documentation:**

- [ ] `CLOUD_RELAY.md` - Accurate and comprehensive
- [ ] `AGENTS.md` - Cloud relay section clear
- [ ] `CHANGELOG.md` - Changes properly documented
- [ ] `config.yaml` - Schema comments helpful

**Success Criteria:** Documentation matches implementation.

---

## Final Checklist

- [ ] All 7 test phases completed
- [ ] No critical errors found
- [ ] Performance acceptable (no noticeable lag)
- [ ] Documentation accurate
- [ ] Ready for production use

## Test Results Template

For each phase, document:

- **Status**: Pass / Fail / Partial
- **Issues Found**: List any problems
- **Logs**: Save relevant log excerpts
- **Notes**: Performance, behavior observations

## Rollback Plan

If critical issues found:

1. Revert configuration to `cloud_relay.enabled: false`
2. Document issue details
3. Check logs for error messages
4. Report findings for fixes

### To-dos

- [ ] Add cloud_relay configuration options to config.yaml schema
- [ ] Add cloud relay constants to const.py with environment variable loading
- [ ] Copy packet_parser.py from mitm/ to cync_lan package
- [ ] Copy checksum.py to cync_lan/packet_checksum.py
- [ ] Create CloudRelayConnection class to manage cloud connections
- [ ] Modify NCyncServer to support relay mode in _register_new_connection
- [ ] Implement bidirectional packet forwarding with inspection
- [ ] Integrate packet parsing with existing MQTT status publishing
- [ ] Add file-based packet injection for debugging
- [ ] Implement secure and debug SSL verification modes with warnings
- [ ] Update AGENTS.md with cloud relay documentation
- [ ] Create comprehensive CLOUD_RELAY.md documentation
- [ ] Update CHANGELOG.md with new feature
- [ ] Test all modes: LAN-only, relay without cloud, relay with cloud, debug logging