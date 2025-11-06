# Cloud Relay Mode - Implementation Complete

**Date:** October 11, 2025
**Version:** 0.0.4.0
**Status:** ✅ Ready for Testing

## Summary

Successfully integrated MITM proxy functionality into the cync-controller Python package and Home Assistant add-on. The add-on can now optionally act as a transparent relay between Cync devices and the cloud, enabling packet inspection, protocol analysis, and debugging.

## Files Modified/Created in Git Repo

### Modified Files (3):

1. **`src/cync_lan/const.py`**
   - Added 6 cloud relay constants
   - Environment variable loading for all relay options

2. **`src/cync_lan/server.py`**
   - New `CloudRelayConnection` class (~300 lines)
   - Modified `NCyncServer` for relay mode support
   - Bidirectional packet forwarding with inspection

3. **`src/cync_lan/structs.py`**
   - Added 6 fields to `GlobalObjEnv`
   - Updated `reload_env()` method

### New Files (3):

4. **`src/cync_lan/packet_parser.py`**
   - Copied from mitm/ tools
   - Parses 11 packet types
   - Extracts device statuses, commands, endpoints

5. **`src/cync_lan/packet_checksum.py`**
   - Copied from mitm/ tools
   - Checksum calculation for crafted packets

6. **`docs/CLOUD_RELAY.md`**
   - Comprehensive 465-line user guide
   - Configuration examples, use cases, troubleshooting

## Files Modified in Add-on Directory

Location: `/mnt/supervisor/addons/local/hass-addons/cync-controller/`

1. **`config.yaml`**
   - Added `cloud_relay` configuration section
   - Bumped version to 0.0.4.0

2. **`run.sh`**
   - Exports 6 cloud relay environment variables

3. **`CHANGELOG.md`**
   - Added v0.0.4.0 entry

## Git Status

```bash
On branch hass_addon
Modified: src/cync_lan/const.py
Modified: src/cync_lan/server.py
Modified: src/cync_lan/structs.py
New: src/cync_lan/packet_checksum.py
New: src/cync_lan/packet_parser.py
New: docs/CLOUD_RELAY.md
```

## Configuration

Add to your add-on configuration:

```yaml
cloud_relay:
  enabled: false # Enable relay mode (default)
  forward_to_cloud: true # Forward to cloud (default)
  cloud_server: "35.196.85.236" # Cloud server IP
  cloud_port: 23779 # Cloud server port
  debug_packet_logging: false # Verbose packet logs
  disable_ssl_verification: false # Debug SSL mode (insecure)
```

## Build and Test

```bash
# Navigate to add-on directory
cd /mnt/supervisor/addons/local/hass-addons/cync-controller

# Rebuild (syncs from git repo + builds container)
./rebuild.sh

# View logs
ha addons logs local_cync-controller --follow
```

## Testing Modes

### 1. Default (Backward Compatibility)

```yaml
cloud_relay:
  enabled: false
```

- Existing LAN-only behavior
- No changes required to existing configs

### 2. Cloud Relay with Forwarding

```yaml
cloud_relay:
  enabled: true
  forward_to_cloud: true
```

- Acts as transparent proxy
- Devices → Relay → Cloud
- MQTT integration works
- Cloud app still functions

### 3. Debug Logging

```yaml
cloud_relay:
  enabled: true
  forward_to_cloud: true
  debug_packet_logging: true
```

- Same as #2 but with verbose packet logs
- Good for protocol analysis

### 4. LAN-only with Inspection

```yaml
cloud_relay:
  enabled: true
  forward_to_cloud: false
  debug_packet_logging: true
```

- Blocks cloud communication
- Still logs packets locally
- Maximum privacy

## Packet Injection (Debug)

When relay mode is enabled:

```bash
# Inject mode change
echo "smart" > /tmp/cync_inject_command.txt
echo "traditional" > /tmp/cync_inject_command.txt

# Inject raw packet bytes
echo "73 00 00 00 1e ..." > /tmp/cync_inject_raw_bytes.txt
```

## Architecture

```
Config (config.yaml)
    ↓
run.sh (exports env vars)
    ↓
const.py (loads constants)
    ↓
structs.py (GlobalObjEnv)
    ↓
server.py: NCyncServer
    ↓
_register_new_connection()
    │
    ├─ if cloud_relay_enabled:
    │   └─ CloudRelayConnection
    │       ├─ connect_to_cloud()
    │       ├─ _forward_with_inspection() x2
    │       │   ├─ parse_cync_packet()
    │       │   ├─ parse_status() → MQTT
    │       │   └─ forward to destination
    │       └─ _check_injection_commands()
    │
    └─ else:
        └─ CyncTCPDevice (existing)
```

## Key Features

✅ **Backward Compatible** - Disabled by default
✅ **Flexible Modes** - LAN-only, cloud backup, debugging
✅ **Packet Inspection** - Real-time parsing and logging
✅ **MQTT Integration** - Automatic status publishing
✅ **Packet Injection** - File-based debugging
✅ **Security Options** - Secure and debug SSL modes
✅ **Clean Architecture** - Minimal changes to existing code

## Documentation

- **User Guide:** `docs/user/cloud-relay.md`
- **Add-on Docs:** `/mnt/supervisor/addons/local/hass-addons/cync-controller/DOCS.md`
- **Agent Guide:** `/mnt/supervisor/addons/local/hass-addons/AGENTS.md`
- **Changelog:** `/mnt/supervisor/addons/local/hass-addons/cync-controller/CHANGELOG.md`

## Next Steps

1. **Test the build:**

   ```bash
   cd /mnt/supervisor/addons/local/hass-addons/cync-controller
   ./rebuild.sh
   ```

2. **Verify default mode** (relay disabled)
   - Check devices still connect
   - Verify commands work

3. **Enable relay mode** and test
   - Try each configuration variant
   - Monitor logs for errors
   - Test packet injection

4. **Commit changes** (when satisfied)
   ```bash
   cd /mnt/supervisor/addons/local/hass-addons
   git add src/cync_lan/packet_*.py
   git add src/cync_lan/const.py
   git add src/cync_lan/server.py
   git add src/cync_lan/structs.py
   git add docs/user/cloud-relay.md
   git commit -m "feat: Add cloud relay mode for packet inspection and debugging"
   ```

## Troubleshooting

### Build fails

- Check Python syntax errors
- Verify all imports are correct
- Check linter output

### Relay won't connect to cloud

- Verify internet connectivity
- Check firewall rules (port 23779)
- Try `disable_ssl_verification: true`

### Devices not connecting

- Verify DNS redirection still configured
- Check add-on is listening: `netstat -an | grep 23779`
- Restart devices

### No packet logs

- Verify `debug_packet_logging: true`
- Check log level is DEBUG
- Confirm relay mode is enabled

## Success Criteria

✅ Files in correct git repo location
✅ Add-on configuration updated
✅ Documentation complete
⏳ Build succeeds
⏳ Default mode works (backward compatibility)
⏳ Relay mode connects and forwards
⏳ Packet logging works
⏳ MQTT integration functional

---

**Implementation:** Complete
**Testing:** Ready to begin
**Status:** Awaiting user validation
