<!-- 56394217-30ff-4825-9208-dd9226e0a36a 5d7ed494-f1f2-4871-8def-128de24e931d -->
# Cloud Relay Mode Testing Plan

Systematic validation of all Cloud Relay operating modes with real devices in devcontainer.

## Prerequisites Check

Before testing, verify:

- Git repo changes are committed: `/mnt/supervisor/addons/local/cync-lan/`
  ```bash
  # Use Git MCP tool to check status
  mcp_git_git_status("/mnt/supervisor/addons/local/cync-lan/")
  # Should show clean working tree, or use: git status
  ```

- DNS redirection is active for `cm.gelighting.com`
- MQTT broker (EMQX) is running and accessible
  ```bash
  # Use Docker MCP to verify EMQX container
  mcp_docker_list_containers(filters={"name": ["emqx"]})
  # Or use: docker ps | grep emqx
  ```

- At least one Cync device is powered on and can connect

## Test Structure

Each test follows this pattern:

1. Update add-on configuration
2. Rebuild and restart add-on
3. Monitor logs for device connections
4. Validate MQTT messages in Home Assistant
5. Test device control (on/off, brightness if applicable)
6. Document results

### MCP Tools for Testing

**Docker MCP** - Container and log inspection:

```python
# Check addon container status
mcp_docker_list_containers(all=True, filters={"name": ["addon_local_cync-lan"]})

# Fetch logs with specific tail count
mcp_docker_fetch_container_logs("addon_local_cync-lan", tail=100)
```

**Python MCP** - Log analysis and packet validation:

```python
# Parse and analyze log entries
import re
logs = "... log content ..."
packet_types = re.findall(r'Type: (0x[0-9a-f]+)', logs)
print(f"Found {len(packet_types)} packets: {set(packet_types)}")

# Validate packet structure
expected_fields = ['Type', 'Seq', 'Device', 'RSSI']
for field in expected_fields:
    count = logs.count(field)
    print(f"{field}: {count} occurrences")
```

**Git MCP** - Track test changes:

```python
# Check for uncommitted test configs
mcp_git_git_status("/mnt/supervisor/addons/local/cync-lan/")

# Review changes made during testing
mcp_git_git_diff_unstaged("/mnt/supervisor/addons/local/cync-lan/", context_lines=3)
```

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

# Alternative: Use Docker MCP for log retrieval
mcp_docker_fetch_container_logs("addon_local_cync-lan", tail=100)
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

**Log Analysis with Python MCP:**

```python
# Analyze packet statistics from logs
import re
from collections import Counter

logs = mcp_docker_fetch_container_logs("addon_local_cync-lan", tail=500)

# Count packet directions
device_to_cloud = logs.count("[RELAY Device→Cloud]")
cloud_to_device = logs.count("[RELAY Cloud→Device]")

# Extract and count packet types
packet_types = re.findall(r'Type: (0x[0-9a-f]+)', logs)
type_counts = Counter(packet_types)

# Calculate average RSSI
rssi_values = [int(x) for x in re.findall(r'RSSI: (-?\d+)', logs)]
avg_rssi = sum(rssi_values) / len(rssi_values) if rssi_values else 0

print(f"Packets Device→Cloud: {device_to_cloud}")
print(f"Packets Cloud→Device: {cloud_to_device}")
print(f"Packet types: {dict(type_counts)}")
print(f"Average RSSI: {avg_rssi:.1f} dBm")
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

**Performance Monitoring with Python MCP:**

   ```python
   import time
   from datetime import datetime
   
   # Record start time
   start_time = datetime.now()
   print(f"Stability test started: {start_time}")
   
   # After 1+ hour, analyze metrics
   logs = mcp_docker_fetch_container_logs("addon_local_cync-lan", tail=1000)
   
   # Count errors/warnings
   errors = logs.count("ERROR")
   warnings = logs.count("WARNING")
   reconnects = logs.count("Device reconnected") + logs.count("Connection reset")
   
   # Check for memory issues
   oom_indicators = ["out of memory", "MemoryError", "killed"]
   memory_issues = sum(logs.count(indicator) for indicator in oom_indicators)
   
   print(f"Test duration: {datetime.now() - start_time}")
   print(f"Errors: {errors}, Warnings: {warnings}")
   print(f"Reconnections: {reconnects}")
   print(f"Memory issues: {memory_issues}")
   ```

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

### Automated Test Result Collection

**Use Python MCP to generate comprehensive test reports:**

```python
from datetime import datetime
from collections import defaultdict

# Collect test data
test_results = {
    "timestamp": datetime.now().isoformat(),
    "phases": []
}

# For each test phase
phases = ["Baseline", "Cloud Relay", "Debug Logging", "LAN-only", "Packet Injection", "SSL Modes", "Edge Cases"]

for phase in phases:
    # Fetch and analyze logs for this phase
    logs = mcp_docker_fetch_container_logs("addon_local_cync-lan", tail=200)

    result = {
        "name": phase,
        "error_count": logs.count("ERROR"),
        "warning_count": logs.count("WARNING"),
        "device_connections": logs.count("Device connected") + logs.count("registered"),
        "mqtt_publishes": logs.count("Publishing to MQTT"),
        "status": "Pass" if logs.count("ERROR") == 0 else "Fail"
    }

    test_results["phases"].append(result)

# Generate summary
print("\n" + "="*70)
print("TEST EXECUTION SUMMARY")
print("="*70)
for phase in test_results["phases"]:
    status_emoji = "✅" if phase["status"] == "Pass" else "❌"
    print(f"{status_emoji} {phase['name']}: {phase['status']}")
    print(f"   Errors: {phase['error_count']}, Warnings: {phase['warning_count']}")
    print(f"   Connections: {phase['device_connections']}, MQTT: {phase['mqtt_publishes']}")

# Calculate overall pass rate
passed = sum(1 for p in test_results["phases"] if p["status"] == "Pass")
total = len(test_results["phases"])
print(f"\nOverall: {passed}/{total} phases passed ({passed/total*100:.1f}%)")
```

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