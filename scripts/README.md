# Automated Testing Scripts

This directory contains automated tools for testing and configuring the Cync Controller add-on without manual UI interaction.

## Overview

These scripts use the **Home Assistant Supervisor API** to programmatically configure add-ons, bypassing the limitations of manual configuration file editing in the devcontainer environment.

## Credentials File Setup

Before using these scripts, you need to configure the credentials file.

### Creating `hass-credentials.env`

1. **Copy the example file:**

   ```bash
   cp hass-credentials.env.example hass-credentials.env
   ```

2. **Edit the file with your credentials:**

   ```bash
   nano hass-credentials.env
   ```

3. **Required fields:**

   | Field                     | Description                                      | Default/Example              |
   | ------------------------- | ------------------------------------------------ | ---------------------------- |
   | `HASS_USERNAME`           | Home Assistant UI username                       | `dev`                        |
   | `HASS_PASSWORD`           | Home Assistant UI password                       | `dev`                        |
   | `CYNC_USERNAME`           | Your Cync/C by GE account email                  | `your-email@example.com`     |
   | `CYNC_PASSWORD`           | Your Cync/C by GE account password               | `your-cync-password`         |
   | `MQTT_USER`               | MQTT broker username                             | `dev`                        |
   | `MQTT_PASS`               | MQTT broker password                             | `dev`                        |
   | `LONG_LIVED_ACCESS_TOKEN` | HA API token (optional, auto-extracted if blank) | Leave blank for auto-extract |

4. **Security notes:**
   - ✅ `hass-credentials.env` is gitignored (never committed)
   - ✅ File is only used locally in devcontainer
   - ✅ Use test credentials for development (`dev`/`dev` for HA and MQTT)
   - ⚠️ Never commit this file with real credentials

### Example file contents

```bash
## Home Assistant credentials
HASS_USERNAME=dev
HASS_PASSWORD=dev

## Cync account credentials
CYNC_USERNAME=your-email@example.com
CYNC_PASSWORD=your-cync-password

## MQTT broker credentials
MQTT_USER=dev
MQTT_PASS=dev

## Optional: Long-lived access token (leave blank for auto-extract)
LONG_LIVED_ACCESS_TOKEN=
```

---

## Scripts

### `reset-ha-to-fresh-onboarded.sh`

Complete factory reset + automated onboarding in one command.

**Purpose:** Fast way to get from any state to "fresh but onboarded" state. Combines `reset-ha-to-fresh.sh` + `setup-fresh-ha.sh` into one command.

### Usage

```bash
./scripts/reset-ha-to-fresh-onboarded.sh
```

### What It Does

1. Resets HA to fresh state (calls `reset-ha-to-fresh.sh`)
2. Runs automated onboarding (calls `setup-fresh-ha.sh`)
3. Results in fully configured HA with EMQX and Cync Controller

### When to Use

- Quick iteration: need fresh onboarded state repeatedly
- Testing the complete setup flow
- Don't need to manually test fresh install steps

**Time:** ~3-4 minutes total

---

### `reset-ha-to-fresh.sh`

Complete factory reset of Home Assistant - **equivalent to rebuilding the devcontainer** - returns to fresh state.

**Purpose:** Recreates the exact conditions of a fresh devcontainer build without the 10-minute rebuild time. Essential for testing fresh install scenarios and debugging initialization errors that only appear on first boot.

### Usage

```bash
./scripts/reset-ha-to-fresh.sh
```

### What It Does

1. **Stop and Remove Container**
   - Stops Home Assistant Core
   - **Removes homeassistant container** to release all file locks
   - Ensures database files (including WAL) are truly deleted

2. **Complete Wipe (Matches Devcontainer Rebuild)**
   - Deletes `/tmp/supervisor_data/homeassistant/*` (all config, database, .storage)
   - Deletes `/tmp/supervisor_data/backup/*` (all backups)
   - Deletes `/tmp/supervisor_data/media/*` (media files)
   - Deletes `/tmp/supervisor_data/ssl/*` (certificates)
   - Deletes `/tmp/supervisor_data/tmp/*` (temporary files)
   - **Identical to a fresh devcontainer** - nothing persists

3. **Fresh Start**
   - Starts HA Core (creates fresh container)
   - Waits for HA to initialize and become responsive
   - Accepts both HTTP 200 and 404 as valid fresh states (404 = no owner user yet)

4. **Completion**
   - HA is now in fresh state
   - Ready for manual testing or running `setup-fresh-ha.sh`
   - Allows you to debug initialization issues that only occur on first boot

### Safety Features

- ✅ Confirmation required (must type "yes")
- ✅ Preserves addon code in `addons/local/`
- ✅ Verifies wipe worked by checking onboarding state
- ✅ Detailed error messages with debug steps
- ✅ Proper container removal to avoid file lock issues

### When to Use

- Testing fresh install scenarios repeatedly
- Debugging initialization errors that only happen on brand new builds
- Need to verify behavior on completely clean HA state
- Want devcontainer rebuild equivalent without 10-minute wait

### Technical Details

**Why remove the container?**
Linux filesystems allow deleted files to persist while processes have them open. The homeassistant container's Python process keeps database files (including SQLite WAL files) open. Simply deleting files from the host leaves them accessible in memory through file descriptors. Removing the container guarantees all file descriptors are closed and deleted data is truly gone.

**What's a WAL file?**
SQLite Write-Ahead Log - changes written to `.db-wal` before committing to main `.db` file. Can persist state even after deleting the main database.

### Examples

```bash
## Reset to fresh state
./scripts/reset-ha-to-fresh.sh

## Then manually test fresh install, OR run automated setup
./scripts/setup-fresh-ha.sh
```

## Time Savings

- Factory reset: ~2-3 minutes
- Devcontainer rebuild: ~10 minutes
- **Savings: ~7 minutes per iteration**

---

### `setup-fresh-ha.sh`

Automated setup script for fresh Home Assistant installations.

**Purpose:** Automates the complete onboarding process, including user creation, EMQX MQTT broker installation, and Cync Controller add-on setup with test credentials.

### Usage

```bash
./setup-fresh-ha.sh
```

### What It Does

1. **User Onboarding**
   - Checks if Home Assistant needs onboarding
   - Creates first user from `.hass-credentials` file
   - Completes onboarding process

2. **EMQX Installation**
   - Adds hassio-addons repository
   - Installs EMQX MQTT broker add-on
   - Configures EMQX with credentials
   - Starts EMQX service asynchronously with state polling

3. **Cync Controller Installation**
   - Installs local Cync Controller add-on
   - Configures with test Cync credentials (placeholder)
   - Configures MQTT connection to EMQX
   - Starts Cync Controller service asynchronously with state polling

4. **Verification**
   - Checks all services are running
   - Provides next steps for manual configuration

### Environment Variables

| Variable           | Description              | Default                           |
| ------------------ | ------------------------ | --------------------------------- |
| `HA_URL`           | Home Assistant URL       | `http://homeassistant.local:8123` |
| `CREDENTIALS_FILE` | Path to credentials file | `../hass-credentials.env`         |

### Examples

```bash
## Run with defaults
./setup-fresh-ha.sh

## Custom HA URL
HA_URL=http://192.168.1.100:8123 ./setup-fresh-ha.sh

## Custom credentials file
CREDENTIALS_FILE=/path/to/creds.env ./setup-fresh-ha.sh
```

## Output Example

```sql
[setup-fresh-ha.sh] Loading credentials from /workspaces/hass-addons/hass-credentials.env...
[setup-fresh-ha.sh] ✅ Credentials loaded (username: dev)
[setup-fresh-ha.sh] Waiting for Home Assistant to be ready...
[setup-fresh-ha.sh] ✅ Home Assistant API is responsive
[setup-fresh-ha.sh] Creating first user: dev...
[setup-fresh-ha.sh] ✅ User created successfully
[setup-fresh-ha.sh] ✅ Onboarding completed
[setup-fresh-ha.sh] ✅ EMQX installed successfully
[setup-fresh-ha.sh] Starting EMQX add-on...
[setup-fresh-ha.sh] Current EMQX state: stopped
[setup-fresh-ha.sh] Issuing start command...
[setup-fresh-ha.sh] Start command issued, waiting for addon to become ready...
[setup-fresh-ha.sh] Waiting for EMQX to start... (1/24, state: startup)
[setup-fresh-ha.sh] Waiting for EMQX to start... (2/24, state: startup)
[setup-fresh-ha.sh] ✅ EMQX started successfully
[setup-fresh-ha.sh] ✅ Cync Controller installed successfully
[setup-fresh-ha.sh] Starting Cync Controller add-on...
[setup-fresh-ha.sh] Current Cync Controller state: stopped
[setup-fresh-ha.sh] Issuing start command...
[setup-fresh-ha.sh] ✅ Cync Controller started successfully
[setup-fresh-ha.sh] ✅ Setup completed successfully!

Next steps:

  1. Log in to Home Assistant at http://homeassistant.local:8123
     Username: dev
     Password: (from /workspaces/hass-addons/hass-credentials.env)

  2. Access EMQX WebUI via Add-ons page to test MQTT

  3. Update Cync Controller configuration with your real Cync credentials:
     - account_username: Your Cync email
     - account_password: Your Cync password

  4. Restart Cync Controller add-on after updating credentials
```

### When to Use

- ✅ First-time devcontainer setup
- ✅ Resetting to fresh HA install
- ✅ CI/CD test environment initialization
- ✅ Automated demo setups

### Idempotency

The script is safe to re-run:

- Skips onboarding if already complete
- Skips add-on installation if already installed
- Updates configuration if needed
- Detects already-running addons and skips start
- Always safe to run multiple times

### Startup Behavior

The script uses **async start + state polling** to handle add-on startup:

- Starts add-ons in background (non-blocking)
- Polls actual add-on state every 5 seconds
- Shows real-time progress: `stopped` → `startup` → `started`
- Timeout protection: 120s for EMQX, 60s for Cync Controller
- Works reliably even when `ha` CLI has internal timeouts

### Requirements

- Fresh Home Assistant instance (or onboarded)
- `.hass-credentials.env` file with `HASS_USERNAME` and `HASS_PASSWORD`
- `jq` and `curl` installed (included in devcontainer)
- Docker access for Supervisor token extraction

### Troubleshooting

| Issue                                 | Solution                                                                   |
| ------------------------------------- | -------------------------------------------------------------------------- |
| "Credentials file not found"          | Create `.hass-credentials.env` in repo root                                |
| "Could not retrieve SUPERVISOR_TOKEN" | Ensure hassio_cli container is running                                     |
| "EMQX installation timed out"         | Check internet connection and retry                                        |
| "Cync Controller failed to start"     | Check logs: `ha addons logs local_cync-controller`                         |
| Stuck on "Waiting to start"           | Script polls for up to 120s - check addon logs if timeout occurs           |
| "Failed to start after X attempts"    | Addon didn't reach `started` state in time - check logs and manually start |

---

### `configure-addon.sh`

Programmatically configure the Cync Controller add-on via Supervisor API.

#### Usage

```bash
./configure-addon.sh < command > [args...]
```

### Commands

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

### Examples

```bash
## Check current configuration
./configure-addon.sh get

## Enable cloud relay with forwarding
./configure-addon.sh preset-relay-with-forward

## Watch logs for relay activity
./configure-addon.sh logs | grep -i "relay\|cloud"

## Return to baseline LAN-only mode
./configure-addon.sh preset-baseline
```

## How It Works

1. Extracts `SUPERVISOR_TOKEN` from the `hassio_cli` container
2. Sends HTTP POST requests to Supervisor API endpoints
3. Automatically restarts the add-on after configuration changes
4. Shows relevant logs after restart

### API Endpoints Used

- `GET /addons/local_cync-controller/info` - Read current configuration
- `POST /addons/local_cync-controller/options` - Update configuration
- `POST /addons/local_cync-controller/restart` - Restart add-on

---

### `test-cloud-relay.sh`

Comprehensive automated test suite for all cloud relay operating modes.

#### Usage

```bash
./test-cloud-relay.sh
```

### Test Phases

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

### Exit Codes

- `0` - All tests passed
- `1` - Some tests failed

---

### `run-mcp-with-env.sh`

Environment variable loader for MCP (Model Context Protocol) servers in Cursor IDE.

#### Purpose

Cursor's `mcp.json` doesn't support environment variable expansion (like `${ENV_VAR}`). This wrapper script loads secrets from `.mcp-secrets.env` before launching MCP servers, allowing you to:

- Keep secrets out of version control
- Share `mcp.json` configurations across machines
- Manage API keys centrally in one gitignored file

### Usage in `mcp.json`

```json
{
  "mcpServers": {
    "my-mcp-server": {
      "command": "/absolute/path/to/hass-addons/scripts/run-mcp-with-env.sh",
      "args": ["npx", "-y", "@org/mcp-server-name", "--transport", "stdio"]
    }
  }
}
```

### Setup

1. Copy `.mcp-secrets.env.example` to `.mcp-secrets.env`
2. Fill in your API keys in `.mcp-secrets.env`
3. Update `mcp.json` with the absolute path to this script

### Security

- `.mcp-secrets.env` is gitignored (never committed)
- Script validates secrets file exists before running
- MCP servers inherit environment variables from loaded `.mcp-secrets.env`

### See also

- `docs/developer/agents-guide.md` - Full MCP secrets management documentation
- `.mcp-secrets.env.example` - Template with placeholder values

---

### `delete-mqtt-safe.py`

Safe MQTT entity deletion script for development and testing.

**Purpose:** Cleanly removes MQTT entities while preserving the Cync Controller configuration.

### Usage

```bash
## Dry run (preview what will be deleted)
sudo python3 scripts/delete-mqtt-safe.py --dry-run

## Actually delete (preserves bridge, cleans registries and restore state)
sudo python3 scripts/delete-mqtt-safe.py
```

## Features

- ✅ Preserves Cync Controller entities
- ✅ Cleans entity and device registries
- ✅ Clears restore state (removes history memory)
- ✅ Safe dry-run mode for preview
- ✅ Comprehensive logging and backup creation

---

### `monitor-test-memory.sh`

Memory usage monitor for test commands (particularly `npm run test:unit`).

**Purpose:** Tracks RAM usage of test processes and their children to help identify memory-intensive operations.

### Usage

```bash
## Monitor default test:unit command
./scripts/monitor-test-memory.sh

## Or via npm script
npm run test:unit:mem

## Monitor a custom command
./scripts/monitor-test-memory.sh "cd cync-controller && pytest tests/unit/ -n 2"
```

## What It Shows

1. **Real-time monitoring** (every 2.5 seconds):
   - Current memory usage (sum of all test processes)
   - Peak memory usage
   - Number of processes being monitored

2. **Final summary:**
   - Peak memory usage (MB)
   - Initial system memory
   - Final system memory
   - Memory delta (system-wide change)

3. **Detailed metrics** (if `/usr/bin/time` available):
   - Maximum resident set size
   - User time
   - System time
   - Elapsed time

### Output Example

```bash
=== Memory Monitor for: npm run test:unit ===

Initial system memory in use: 2048 MB

Monitoring memory usage (sampling every 0.5s)...
Current:  156 MB | Peak:  256 MB | Processes:  8

=== Memory Usage Summary ===
Peak memory usage: 256 MB
Initial system memory: 2048 MB
Final system memory: 2064 MB
System memory delta: +16 MB

=== Detailed Timing & Memory (using time command) ===
Maximum resident set size (kbytes): 262144
User time (seconds): 12.34
System time (seconds): 2.45
Elapsed (wall clock) time (h:mm:ss or m:ss): 0:17.23
```

### How It Works

1. Starts the test command in background
2. Monitors the process tree (parent + all children) using `ps` to get RSS (Resident Set Size)
3. Samples every 0.5 seconds, displays updates every 2.5 seconds
4. Tracks peak memory across all processes
5. Reports final statistics including system-wide memory changes

### Use Cases

- Identifying memory-intensive test configurations
- Comparing RAM usage between different pytest worker counts (`-n auto` vs `-n 2`)
- Debugging OOM (Out of Memory) errors
- Optimizing test execution to reduce memory footprint

### See also

- `package.json` - `test:unit:mem` npm script
- `cync-controller/pytest.ini` - Pytest configuration (adjust `-n auto` to limit workers)

---

## Technical Details

### Supervisor API Authentication

All scripts use the Supervisor API token for authentication:

```bash
## Token is extracted from hassio_cli container
SUPERVISOR_TOKEN=$(docker exec hassio_cli env | grep SUPERVISOR_TOKEN | cut -d= -f2)

## API requests use Bearer token authentication
curl -H "Authorization: Bearer ${SUPERVISOR_TOKEN}" \
  http://supervisor/addons/local_cync-controller/info
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

#### Solution

```bash
## Check if hassio_cli is running
docker ps | grep hassio_cli

## Restart supervisor if needed
ha supervisor restart
```

### "Configuration update failed (HTTP 401)"

**Cause:** Invalid or expired Supervisor token.

#### Solution

```bash
## Verify token is set
docker exec hassio_cli env | grep SUPERVISOR_TOKEN

## Restart supervisor to refresh
ha supervisor restart
```

### "Add-on restart timeout"

**Cause:** Add-on taking longer than expected to restart.

#### Solution

- Check add-on logs: `ha addons logs local_cync-controller`
- Manually restart: `ha addons restart local_cync-controller`
- Check for errors in supervisor logs: `tail -f /tmp/supervisor_run.log`

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
## Phase 7: My Custom Test
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

_Last Updated: October 14, 2025_
_Status: Production Ready_ ✅
