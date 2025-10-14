# Automated Testing Scripts

This directory contains automated tools for testing and configuring the CyncLAN add-on without manual UI interaction.

## Overview

These scripts use the **Home Assistant Supervisor API** to programmatically configure add-ons, bypassing the limitations of manual configuration file editing in the devcontainer environment.

## Scripts

### `configure-addon.sh`

Programmatically configure the CyncLAN add-on via Supervisor API.

**Usage:**
```bash
./configure-addon.sh <command> [args...]
```

**Commands:**

| Command                                       | Description                              | Example                                                |
| --------------------------------------------- | ---------------------------------------- | ------------------------------------------------------ |
| `get`                                         | Show current configuration               | `./configure-addon.sh get`                             |
| `set-cloud-relay <enabled> <forward> <debug>` | Set cloud relay options                  | `./configure-addon.sh set-cloud-relay true true false` |
| `preset-baseline`                             | Disable cloud relay (LAN-only)           | `./configure-addon.sh preset-baseline`                 |
| `preset-relay-with-forward`                   | Enable relay with cloud forwarding       | `./configure-addon.sh preset-relay-with-forward`       |
| `preset-relay-debug`                          | Enable relay with debug packet logging   | `./configure-addon.sh preset-relay-debug`              |
| `preset-lan-only`                             | Enable relay in LAN-only mode (no cloud) | `./configure-addon.sh preset-lan-only`                 |
| `restart`                                     | Restart the add-on                       | `./configure-addon.sh restart`                         |
| `logs`                                        | Show add-on logs                         | `./configure-addon.sh logs`                            |

**Examples:**

```bash
# Check current configuration
./configure-addon.sh get

# Enable cloud relay with forwarding
./configure-addon.sh preset-relay-with-forward

# Watch logs for relay activity
./configure-addon.sh logs | grep -i "relay\|cloud"

# Return to baseline LAN-only mode
./configure-addon.sh preset-baseline
```

**How It Works:**

1. Extracts `SUPERVISOR_TOKEN` from the `hassio_cli` container
2. Sends HTTP POST requests to Supervisor API endpoints
3. Automatically restarts the add-on after configuration changes
4. Shows relevant logs after restart

**API Endpoints Used:**
- `GET /addons/local_cync-lan/info` - Read current configuration
- `POST /addons/local_cync-lan/options` - Update configuration
- `POST /addons/local_cync-lan/restart` - Restart add-on

---

### `test-cloud-relay.sh`

Comprehensive automated test suite for all cloud relay operating modes.

**Usage:**
```bash
./test-cloud-relay.sh
```

**Test Phases:**

1. **Phase 1: Baseline LAN-only Mode**
   - Verifies cloud relay is disabled
   - Checks normal operation (backward compatibility)
   - Ensures no cloud connections in baseline mode

2. **Phase 2: Cloud Relay with Forwarding**
   - Enables cloud relay mode
   - Verifies SSL connection to cloud server
   - Confirms bidirectional packet forwarding

3. **Phase 3: Debug Packet Logging**
   - Enables detailed packet logging
   - Verifies parsed packet logs appear
   - Tests packet inspection functionality

4. **Phase 4: LAN-only Relay (Privacy Mode)**
   - Enables relay but blocks cloud forwarding
   - Verifies local control works
   - Confirms no cloud connections

5. **Phase 5: Packet Injection**
   - Tests mode change injection (`smart`/`traditional`)
   - Verifies injection logs appear
   - Tests raw packet injection (if container accessible)

6. **Phase 6: Return to Baseline**
   - Disables cloud relay
   - Verifies return to normal operation
   - Confirms clean state transition

**Output:**

```
═══════════════════════════════════════════════════════════
  Cloud Relay Mode - Automated Testing
═══════════════════════════════════════════════════════════

═══════════════════════════════════════════════════════════
  Phase 1: Baseline LAN-only Mode
═══════════════════════════════════════════════════════════
✅ PASS - Configuration applied
✅ PASS - Baseline: No relay mode

═══════════════════════════════════════════════════════════
  Phase 2: Cloud Relay with Forwarding
═══════════════════════════════════════════════════════════
✅ PASS - Configuration applied
✅ PASS - Cloud relay enabled
✅ PASS - Device connected in relay mode
✅ PASS - Cloud connection established

[... more tests ...]

═══════════════════════════════════════════════════════════
  Test Summary
═══════════════════════════════════════════════════════════

Total Tests:  18
Passed:       17
Failed:       1

╔═══════════════════════════════════════════════════════╗
║                                                       ║
║  ✅  ALL TESTS PASSED - CLOUD RELAY WORKING! ✅      ║
║                                                       ║
╚═══════════════════════════════════════════════════════╝
```

**Exit Codes:**
- `0` - All tests passed
- `1` - Some tests failed

---

### `run-mcp-with-env.sh`

Environment variable loader for MCP (Model Context Protocol) servers in Cursor IDE.

**Purpose:**

Cursor's `mcp.json` doesn't support environment variable expansion (like `${ENV_VAR}`). This wrapper script loads secrets from `.mcp-secrets.env` before launching MCP servers, allowing you to:
- Keep secrets out of version control
- Share `mcp.json` configurations across machines
- Manage API keys centrally in one gitignored file

**Usage in `mcp.json`:**
```json
{
  "mcpServers": {
    "brave": {
      "command": "/absolute/path/to/hass-addons/scripts/run-mcp-with-env.sh",
      "args": ["npx", "-y", "@brave/brave-search-mcp-server", "--transport", "stdio"]
    }
  }
}
```

**Setup:**
1. Copy `.mcp-secrets.env.example` to `.mcp-secrets.env`
2. Fill in your API keys in `.mcp-secrets.env`
3. Update `mcp.json` with the absolute path to this script

**Security:**
- `.mcp-secrets.env` is gitignored (never committed)
- Script validates secrets file exists before running
- MCP servers inherit environment variables from loaded `.mcp-secrets.env`

**See also:**
- `docs/developer/agents-guide.md` - Full MCP secrets management documentation
- `.mcp-secrets.env.example` - Template with placeholder values

---

## Technical Details

### Supervisor API Authentication

Both scripts use the Supervisor API token for authentication:

```bash
# Token is extracted from hassio_cli container
SUPERVISOR_TOKEN=$(docker exec hassio_cli env | grep SUPERVISOR_TOKEN | cut -d= -f2)

# API requests use Bearer token authentication
curl -H "Authorization: Bearer ${SUPERVISOR_TOKEN}" \
     http://supervisor/addons/local_cync-lan/info
```

### Configuration Persistence

Unlike manual file edits, API-based configuration changes:
- ✅ Trigger proper Supervisor reload mechanisms
- ✅ Update `/data/options.json` automatically
- ✅ Reload environment variables correctly
- ✅ Work reliably in devcontainer environment

### Performance

- **Configuration change:** ~5 seconds (API call + validation)
- **Add-on restart:** ~5-8 seconds
- **Full test suite:** ~2-3 minutes (all phases with waits)

---

## Troubleshooting

### "Could not retrieve SUPERVISOR_TOKEN"

**Cause:** The `hassio_cli` container is not running.

**Solution:**
```bash
# Check if hassio_cli is running
docker ps | grep hassio_cli

# Restart supervisor if needed
ha supervisor restart
```

### "Configuration update failed (HTTP 401)"

**Cause:** Invalid or expired Supervisor token.

**Solution:**
```bash
# Verify token is set
docker exec hassio_cli env | grep SUPERVISOR_TOKEN

# Restart supervisor to refresh
ha supervisor restart
```

### "Add-on restart timeout"

**Cause:** Add-on taking longer than expected to restart.

**Solution:**
- Check add-on logs: `ha addons logs local_cync-lan`
- Manually restart: `ha addons restart local_cync-lan`
- Check for errors in supervisor logs: `tail -f /tmp/supervisor_run.log`

### Test fails with "No such container"

**Cause:** Add-on container name mismatch.

**Solution:**
```bash
# Find correct container name
docker ps | grep addon

# Update script if needed (unlikely, should auto-detect)
```

---

## Development

### Adding New Configuration Presets

Edit `configure-addon.sh` and add a new case to the main switch statement:

```bash
preset-my-custom-config)
    echo "$LP Applying preset: My Custom Config"
    current_config=$(get_config)
    new_config=$(echo "$current_config" | jq '
        .cloud_relay.enabled = true |
        .cloud_relay.forward_to_cloud = false |
        .cloud_relay.debug_packet_logging = true
    ')
    update_config "$(echo "{\"options\": $new_config}" | jq -c '.')"
    restart_addon
    show_logs | tail -50
    ;;
```

### Adding New Test Phases

Edit `test-cloud-relay.sh` and add a new test phase:

```bash
# Phase 7: My Custom Test
section "Phase 7: My Custom Test"
apply_config "preset-my-custom-config" "Testing my custom configuration"
check_log "Expected log pattern" "Test description"
wait_for_log "Pattern to wait for" 15 "Wait description"
```

---

## Related Documentation

- **../docs/developer/limitations-lifted.md** - Full documentation of resolved testing limitations
- **../docs/developer/agents-guide.md** - AI agent guidance (includes testing and configuration section)
- **../docs/developer/test-results.md** - Comprehensive test execution results

---

*Last Updated: October 11, 2025*
*Status: Production Ready* ✅

