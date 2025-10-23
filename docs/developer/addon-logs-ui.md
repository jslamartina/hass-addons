# Add-on Logs UI Configuration

## Overview

Home Assistant add-on logs can be accessed through the web UI at:
```
http://localhost:8123/hassio/addon/<addon_slug>/logs
```

For the Cync Controller add-on:
```
http://localhost:8123/hassio/addon/local_cync-controller/logs
```

## Requirements

For logs to appear in the Home Assistant UI, the following requirements must be met:

1. **Docker logging driver**: Docker must be configured with the `journald` logging driver
2. **systemd-journal-remote**: The `systemd-journal-remote` package must be installed
3. **Container logs**: Add-on must output logs to stdout/stderr (already configured)

## Devcontainer Setup

The devcontainer environment is now configured to automatically enable journald logging support:

### Automatic Configuration

The `.devcontainer/post-start.sh` script automatically:

1. Installs `systemd-journal-remote` package
2. Configures Docker daemon with journald logging driver
3. Starts Home Assistant Supervisor with journald support

### Docker Configuration

Docker daemon is configured with:

```json
{
    "log-driver": "journald",
    "storage-driver": "overlay2"
}
```

This configuration is written to `/etc/docker/daemon.json` before Docker starts.

## Accessing Logs

### Via Home Assistant UI

1. Navigate to Settings → Add-ons
2. Click on "Cync Controller"
3. Click on "Log" tab at the top
4. Logs will display in real-time with auto-refresh

### Via Command Line

**journalctl (recommended in devcontainer):**
```bash
# View recent logs
cync-logs-tail

# Follow logs in real-time
cync-logs-follow

# View all logs
cync-logs

# Raw journalctl command
sudo journalctl CONTAINER_NAME=addon_local_cync-controller --no-pager
```

**Docker logs (alternative):**
```bash
# View recent logs
cync-logs-docker

# Follow logs in real-time
cync-logs-docker-follow

# Raw docker command
docker logs addon_local_cync-controller
```

### Via Home Assistant CLI

```bash
# View logs via Home Assistant CLI
ha addons logs local_cync-controller

# Follow logs
ha addons logs local_cync-controller --follow
```

## Shell Aliases

The devcontainer provides convenient aliases for log access:

| Alias                     | Command                                                              | Description                 |
| ------------------------- | -------------------------------------------------------------------- | --------------------------- |
| `cync-logs`               | `sudo journalctl CONTAINER_NAME=addon_local_cync-controller`         | View all logs               |
| `cync-logs-follow`        | `sudo journalctl CONTAINER_NAME=addon_local_cync-controller -f`      | Follow logs in real-time    |
| `cync-logs-tail`          | `sudo journalctl CONTAINER_NAME=addon_local_cync-controller --lines` | View last 100 lines         |
| `cync-logs-docker`        | `docker logs addon_local_cync-controller`                            | Fallback: View via Docker   |
| `cync-logs-docker-follow` | `docker logs -f addon_local_cync-controller`                         | Fallback: Follow via Docker |
| `emqx-logs`               | `sudo journalctl CONTAINER_NAME=addon_a0d7b954_emqx`                 | View EMQX logs              |
| `emqx-logs-follow`        | `sudo journalctl CONTAINER_NAME=addon_a0d7b954_emqx -f`              | Follow EMQX logs            |
| `emqx-logs-tail`          | `sudo journalctl CONTAINER_NAME=addon_a0d7b954_emqx --lines 100`     | View last 100 lines of EMQX |

## Troubleshooting

### Logs Not Appearing in UI

If logs don't appear in the Home Assistant UI:

1. **Check Docker logging driver:**
   ```bash
   sudo cat /etc/docker/daemon.json
   # Should show: "log-driver": "journald"
   ```

2. **Verify journald is accessible:**
   ```bash
   sudo journalctl CONTAINER_NAME=addon_local_cync-controller --no-pager --lines=10
   # Should show recent log entries
   ```

3. **Restart the add-on:**
   ```bash
   ha addons restart local_cync-controller
   ```

4. **Restart the Supervisor:**
   ```bash
   ha supervisor restart
   sleep 15  # Wait for supervisor to restart
   ```

5. **Verify systemd-journal-remote is installed:**
   ```bash
   dpkg -l | grep systemd-journal-remote
   ```

### Manual Setup (If Automatic Setup Fails)

If the automatic setup in `post-start.sh` fails, run the manual setup script:

```bash
./.devcontainer/99-enable-journald-logs.sh
```

This script performs the same configuration steps with detailed output.

### Verifying Configuration

After setup, verify that everything is working:

```bash
# 1. Check Docker is using journald
docker info | grep "Logging Driver"
# Should show: Logging Driver: journald

# 2. Test journalctl access
sudo journalctl CONTAINER_NAME=addon_local_cync-controller --no-pager --lines=5

# 3. Check Home Assistant UI
# Navigate to: http://localhost:8123/hassio/addon/local_cync-controller/logs
```

## Technical Details

### How It Works

1. **Add-on outputs to stdout/stderr**: The `cync-controller` Python package uses standard logging to stdout (`main.py:40-54`)
2. **Docker captures logs**: Docker daemon captures container stdout/stderr
3. **journald logging driver**: Docker forwards logs to systemd journal
4. **Supervisor API**: Home Assistant Supervisor queries journald via API
5. **UI displays logs**: Web UI renders logs from Supervisor API

### Log Sources

The Cync Controller add-on logs include:

- **nCync server**: TCP server handling device communications
- **MQTT client**: Home Assistant MQTT discovery and state updates
- **ExportServer**: FastAPI web interface for device export
- **Cloud relay** (optional): MITM proxy packet inspection

### Log Levels

Controlled via `debug_log_level` option in add-on configuration:

- `true`: DEBUG level (verbose, includes packet details)
- `false`: INFO level (standard operation logs)

## Production vs Development

### Home Assistant OS (Production)

- Docker is pre-configured with journald logging driver
- systemd-journal-remote is included in the OS
- Logs UI works out-of-the-box

### Devcontainer (Development)

- Requires manual configuration (automated via `post-start.sh`)
- Docker daemon must be configured before first start
- systemd-journal-remote must be installed

## See Also

- [AGENTS.md](../../AGENTS.md#useful-commands) - Common log viewing commands
- [.devcontainer/README.md](../../.devcontainer/README.md) - Devcontainer quirks
- [Home Assistant Add-on Documentation](https://developers.home-assistant.io/docs/add-ons/) - Official add-on development guide

---

*Last Updated: October 21, 2025*
*Related Issue: Add-on logs not appearing in UI due to missing journald configuration*














