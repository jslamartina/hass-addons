# Cloud Relay Mode

**New in v0.0.4.0**

The CyncLAN add-on can optionally operate as a Man-in-the-Middle (MITM) proxy between your Cync devices and the Cync cloud servers. This enables real-time packet inspection, protocol analysis, and debugging while maintaining full device functionality.

## What is Cloud Relay Mode?

In normal operation, the CyncLAN add-on acts as a **local replacement** for the Cync cloud - devices connect directly to the add-on and never communicate with Cync servers.

With **Cloud Relay Mode** enabled, the add-on acts as a **transparent proxy**:

```
Device ←→ CyncLAN Relay ←→ Cync Cloud
              ↓
          MQTT/HA
          Packet Logs
```

This architecture provides:
- **Packet Inspection**: See exactly what devices and cloud are saying
- **Protocol Analysis**: Reverse engineer new device features
- **Cloud Backup**: Devices continue working even if relay fails (they fall back to cloud)
- **Debugging**: Test behavior while observing actual cloud interactions
- **LAN-only Option**: Block cloud access while still inspecting packets locally

## Configuration

Add the `cloud_relay` section to your add-on configuration:

```yaml
cloud_relay:
  enabled: false                      # Enable relay mode (default: false)
  forward_to_cloud: true              # Forward packets to cloud (default: true)
  cloud_server: "35.196.85.236"       # Cync cloud server IP (default: 35.196.85.236)
  cloud_port: 23779                   # Cync cloud port (default: 23779)
  debug_packet_logging: false         # Log all packets (default: false)
  disable_ssl_verification: false     # Disable SSL verify - DEBUG ONLY (default: false)
```

### Configuration Options

| Option                     | Type    | Default           | Description                                                  |
| -------------------------- | ------- | ----------------- | ------------------------------------------------------------ |
| `enabled`                  | boolean | `false`           | Enable cloud relay mode                                      |
| `forward_to_cloud`         | boolean | `true`            | Forward packets to Cync cloud (false = LAN-only)             |
| `cloud_server`             | string  | `"35.196.85.236"` | Cync cloud server IP address                                 |
| `cloud_port`               | integer | `23779`           | Cync cloud server port                                       |
| `debug_packet_logging`     | boolean | `false`           | Log all parsed packets (verbose)                             |
| `disable_ssl_verification` | boolean | `false`           | Disable SSL certificate verification (INSECURE - debug only) |

## Operating Modes

### Mode 1: Normal LAN-only (Relay Disabled)

**Configuration:**
```yaml
cloud_relay:
  enabled: false
```

**Behavior:**
- Default mode - add-on acts as local Cync cloud replacement
- No cloud communication
- Requires DNS redirection
- Most secure and private

**Use When:** You want full local control with no cloud dependency.

---

### Mode 2: Cloud Relay with Forwarding

**Configuration:**
```yaml
cloud_relay:
  enabled: true
  forward_to_cloud: true
  debug_packet_logging: false
```

**Behavior:**
- Devices connect to add-on, add-on forwards to real cloud
- Transparent proxy - devices work as if connected directly to cloud
- MQTT integration still works
- Minimal logging (only non-keepalive packets at debug level)

**Use When:** You want cloud backup while maintaining Home Assistant integration.

---

### Mode 3: Cloud Relay with Debug Logging

**Configuration:**
```yaml
cloud_relay:
  enabled: true
  forward_to_cloud: true
  debug_packet_logging: true
```

**Behavior:**
- Same as Mode 2, but logs all packet details
- Useful for protocol analysis and debugging
- Can generate large logs

**Use When:** Debugging device behavior or reverse engineering protocol.

**Example Log Output:**
```
[CLOUD->DEV] 0x43 DEVICE_INFO | EP:1b dc da 3e | CTR:0x15 | LEN:314
  Device Statuses (12 devices):
    [160] ON  Bri:100 Temp: 50 Online:True
    [ 94] OFF Bri:  0 Temp:  0 Online:True
```

---

### Mode 4: LAN-only with Packet Inspection

**Configuration:**
```yaml
cloud_relay:
  enabled: true
  forward_to_cloud: false
  debug_packet_logging: true
```

**Behavior:**
- Devices connect to add-on
- Packets are parsed and logged
- **No forwarding to cloud** - cloud connection blocked
- Device commands still work via MQTT

**Use When:** Maximum privacy while still enabling protocol analysis.

---

### Mode 5: Debug Mode (SSL Verification Disabled)

**Configuration:**
```yaml
cloud_relay:
  enabled: true
  forward_to_cloud: true
  debug_packet_logging: true
  disable_ssl_verification: true
```

**Behavior:**
- Same as Mode 3, but disables SSL certificate verification
- **⚠️ INSECURE** - vulnerable to MITM attacks
- Only for local testing/development

**Security Warning:**
```
============================================================
⚠️  SSL VERIFICATION DISABLED - DEBUG MODE ACTIVE ⚠️
This mode should ONLY be used for local debugging!
DO NOT use on untrusted networks or production systems!
============================================================
```

**Use When:** Local development when SSL cert issues prevent connection.

## Use Cases

### Protocol Analysis

**Goal:** Understand how Cync devices communicate

**Configuration:**
```yaml
cloud_relay:
  enabled: true
  forward_to_cloud: true
  debug_packet_logging: true
```

**Workflow:**
1. Enable relay with debug logging
2. Trigger device actions in Cync app or Home Assistant
3. Review logs to see packet structures
4. Use insights to implement new features

---

### Debugging Device Issues

**Goal:** Figure out why a device isn't responding correctly

**Configuration:**
```yaml
cloud_relay:
  enabled: true
  forward_to_cloud: true
  debug_packet_logging: true
```

**Workflow:**
1. Enable relay mode
2. Reproduce the issue
3. Check logs for:
   - Packet delivery (DEV->CLOUD and CLOUD->DEV)
   - Device status updates
   - Error responses
4. Compare with expected behavior

---

### Testing Without Cloud Dependency

**Goal:** Ensure add-on works without internet

**Configuration:**
```yaml
cloud_relay:
  enabled: true
  forward_to_cloud: false
```

**Workflow:**
1. Enable relay without forwarding
2. Test all device functions
3. Verify MQTT integration works
4. Confirm no external connections

---

### Cloud Backup Strategy

**Goal:** Keep cloud as fallback while using Home Assistant

**Configuration:**
```yaml
cloud_relay:
  enabled: true
  forward_to_cloud: true
  debug_packet_logging: false
```

**Benefit:** If your Home Assistant instance goes down, devices still work via Cync app since they maintain cloud connection.

## Packet Injection (Advanced)

When relay mode is enabled, you can inject custom packets for testing.

### Inject Raw Packet Bytes

Create a file with hex-formatted packet data:

```bash
# From add-on container
echo "73 00 00 00 1e 1b dc da 3e 00 13 00 7e 0d 01 00 00 f8 8e 0c 00 0e 01 00 00 00 a0 00 f7 11 02 01 01 55 7e" > /tmp/cync_inject_raw_bytes.txt
```

The relay will:
1. Detect the file
2. Parse the hex bytes
3. Inject packet to device
4. Delete the file

### Inject Mode Change (Switches)

For switches with smart bulb mode capability:

```bash
# Switch to smart/dimmable mode
echo "smart" > /tmp/cync_inject_command.txt

# Switch to traditional mode
echo "traditional" > /tmp/cync_inject_command.txt
```

**Note:** This only works if the relay has identified a device endpoint from the connection handshake.

## Packet Format

The relay uses the packet parser from the MITM research tools. See `mitm/FINDINGS_SUMMARY.md` for detailed packet structure documentation.

### Common Packet Types

| Type   | Name             | Direction | Description                                   |
| ------ | ---------------- | --------- | --------------------------------------------- |
| `0x23` | HANDSHAKE        | DEV→CLOUD | Initial connection, contains device endpoint  |
| `0x28` | HELLO_ACK        | CLOUD→DEV | Handshake acknowledgment                      |
| `0x43` | DEVICE_INFO      | DEV→CLOUD | Bulk device status (19 bytes per device)      |
| `0x48` | INFO_ACK         | CLOUD→DEV | Device info acknowledgment                    |
| `0x73` | DATA_CHANNEL     | Both      | Command/response channel (mode changes, etc.) |
| `0x78` | KEEPALIVE        | Both      | Connection keepalive (logged minimally)       |
| `0x83` | STATUS_BROADCAST | DEV→CLOUD | Device status update                          |
| `0x88` | STATUS_ACK       | CLOUD→DEV | Status acknowledgment                         |

## Security Considerations

### SSL Verification

**By default**, the relay uses SSL with verification **disabled** because:
1. Cync cloud uses self-signed certificates
2. The IP address doesn't match the certificate hostname
3. We're intentionally performing MITM interception

**In secure mode** (`disable_ssl_verification: false`):
- SSL is used but verification is still disabled (Cync limitation)
- Provides encryption but not identity verification

**In debug mode** (`disable_ssl_verification: true`):
- Explicitly disables all SSL checks
- Logs prominent security warnings
- **NEVER use on untrusted networks**

### Network Isolation

**Recommendations:**
- Run relay mode only on trusted local networks
- Use VLANs to isolate IoT devices
- Monitor logs for unexpected traffic
- Disable relay mode when not actively debugging

### Data Privacy

**What's logged:**
- Packet types and directions
- Device IDs and status
- Command structures
- Endpoint identifiers

**What's NOT logged:**
- Account credentials (never transmitted after initial export)
- Personal information
- Network passwords

**Logs are stored in:** Home Assistant supervisor logs (accessible via `ha addons logs local_cync-lan`)

## Troubleshooting

### Relay won't connect to cloud

**Symptoms:** Log shows "Failed to connect to cloud"

**Solutions:**
1. Check internet connectivity: `ping 35.196.85.236`
2. Verify firewall allows outbound connections on port 23779
3. Check cloud server IP hasn't changed (update `cloud_server` if needed)

---

### Devices not connecting to relay

**Symptoms:** No device connections visible in logs

**Solutions:**
1. Verify DNS redirection is still configured (relay mode still requires DNS)
2. Check devices are on same network
3. Restart devices to force reconnection
4. Confirm add-on is listening: `netstat -an | grep 23779`

---

### Packet logging too verbose

**Symptoms:** Logs filled with keepalive packets

**Solution:** Keepalives (`0x78`) are already filtered by default. If still too verbose, disable `debug_packet_logging` or adjust log level.

---

### SSL errors

**Symptoms:** SSL handshake failures

**Solutions:**
1. Try `disable_ssl_verification: true` (debug mode)
2. Check system time is correct (SSL certificates are time-sensitive)
3. Verify cloud server IP/port are correct

---

### Injection not working

**Symptoms:** Injection files ignored

**Check:**
1. Relay mode is enabled
2. Device has connected (relay knows endpoint)
3. File path is correct: `/tmp/cync_inject_*.txt`
4. Packet format is valid hex

## Migrating from Standalone MITM

If you were using the standalone `mitm/mitm_with_injection.py` tool:

### What's Different

| Feature            | Standalone MITM  | Cloud Relay Mode   |
| ------------------ | ---------------- | ------------------ |
| **Integration**    | Separate process | Built into add-on  |
| **Configuration**  | Command-line     | YAML config        |
| **Packet Parsing** | Same code        | Same code (copied) |
| **Injection**      | File-based       | File-based         |
| **MQTT**           | Manual           | Automatic          |
| **Logging**        | Console/file     | HA logs            |

### Migration Steps

1. Note your current MITM configuration
2. Enable `cloud_relay` in add-on with equivalent settings
3. Stop standalone MITM tool
4. Restart add-on
5. Verify devices connect and logs appear

### Advantages of Integrated Relay

- ✅ Single configuration point
- ✅ Automatic MQTT integration
- ✅ Managed by Home Assistant supervisor
- ✅ Survives add-on restarts
- ✅ No separate process to manage

## Performance Impact

### CPU Usage

- **Without debug logging:** Negligible (< 1% increase)
- **With debug logging:** Low (< 5% increase)
- **Packet parsing:** Efficient (< 1ms per packet)

### Memory Usage

- **Per connection:** ~1MB
- **With 8 devices:** ~8MB total

### Network Latency

- **Local only:** < 1ms added
- **With cloud forwarding:** ~10-50ms added (depends on internet)

**Recommendation:** Monitor add-on resources in Home Assistant → Settings → Add-ons → CyncLAN Bridge → Performance

## Advanced Topics

### Custom Cloud Servers

For testing or future-proofing:

```yaml
cloud_relay:
  enabled: true
  cloud_server: "backup.cync-cloud.example.com"
  cloud_port: 23779
```

### Multiple Relay Instances

Not recommended, but possible:
- Run multiple add-on instances on different ports
- Configure different devices to use different relays
- Useful for A/B testing protocol changes

### Packet Capture

For deep analysis, combine relay logging with packet capture:

```bash
# From Home Assistant host
sudo tcpdump -i any port 23779 -w cync_packets.pcap

# Analyze with Wireshark or tshark
```

## FAQ

**Q: Does relay mode work without DNS redirection?**
A: No. Devices still need to connect to the add-on first. DNS redirection is still required.

**Q: Can I use relay mode and LAN-only mode at the same time?**
A: No. It's one or the other. Relay mode replaces LAN-only mode.

**Q: Does this work with the Cync mobile app?**
A: Yes, if `forward_to_cloud: true`. The app talks to cloud, which relays through your add-on.

**Q: Will my devices stop working if the relay fails?**
A: If `forward_to_cloud: true`, devices fall back to direct cloud connection. If `forward_to_cloud: false`, devices lose connection until relay recovers.

**Q: Is this mode slower?**
A: Slightly. Expect 10-50ms additional latency due to proxy overhead.

**Q: Can I capture credentials with this?**
A: No. Authentication happens during device setup via the cloud API (not the TCP protocol). Devices use pre-shared tokens.

## References

- [Cync Protocol Documentation](packet_structure.md)
- [MITM Testing Guide](../../mitm/MITM_TESTING_GUIDE.md)
- [DNS Redirection Setup](DNS.md)
- [Troubleshooting Guide](troubleshooting.md)

---

**Last Updated:** October 2025
**Version:** 0.0.4.0

