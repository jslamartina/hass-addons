# Add-on Logs UI - Setup Summary

**Date**: October 21, 2025
**Issue**: Add-on logs not appearing at `http://localhost:8123/hassio/addon/local_cync-controller/logs`
**Root Cause**: Missing journald logging configuration in devcontainer environment

## What Was Done

### 1. Identified the Issue

Home Assistant Supervisor requires access to systemd journal to retrieve and display add-on logs. The devcontainer environment was missing:

- `systemd-journal-remote` package
- Docker daemon configured with journald logging driver

### 2. Created Automated Setup

**Modified `.devcontainer/post-start.sh`:**

- Added Step 0 (before Docker starts) to configure journald logging
- Installs `systemd-journal-remote` if not present
- Configures Docker daemon with `"log-driver": "journald"`
- Updates shell aliases to use `journalctl` instead of `docker logs`

**Created `.devcontainer/99-enable-journald-logs.sh`:**

- Manual setup script for troubleshooting
- Can be run independently if automatic setup fails
- Includes verification steps and next-step instructions

### 3. Updated Shell Aliases

**New primary aliases (journald-based):**

```bash
cync-logs        # View all logs via journalctl
cync-logs-follow # Follow logs in real-time
cync-logs-tail   # View last 100 lines
```

**Fallback aliases (Docker-based):**

```bash
cync-logs-docker        # Direct Docker logs access
cync-logs-docker-follow # Follow Docker logs
```

### 4. Created Documentation

**New file: `docs/developer/addon-logs-ui.md`**

- Explains how add-on logs UI works
- Documents requirements and configuration
- Provides troubleshooting steps
- Lists all available log access methods

## Verification

### ✅ Configuration Applied

```bash
# Docker is using journald
$ docker info | grep "Logging Driver"
 Logging Driver: journald

# Logs are accessible via journalctl
$ sudo journalctl CONTAINER_NAME=addon_local_cync-controller --lines=10
Oct 21 21:08:37 addon_local_cync-controller[4568]: 10/21/25 16:08:37.583 INFO (uvicorn.access) > 172.30.32.2:49984 - "GET / HTTP/1.1" 200
...
```

### ✅ Add-on Container Running

```bash
$ ha addons info local_cync-controller --raw-json | jq '.data.state'
"started"
```

### ✅ Logs Available via Multiple Methods

1. **Home Assistant UI**: `http://localhost:8123/hassio/addon/local_cync-controller/logs`
2. **journalctl**: `sudo journalctl CONTAINER_NAME=addon_local_cync-controller`
3. **ha CLI**: `ha addons logs local_cync-controller`
4. **Docker**: `docker logs addon_local_cync-controller` (fallback)

## Technical Details

### Docker Configuration (`/etc/docker/daemon.json`)

```json
{
  "log-driver": "journald",
  "storage-driver": "overlay2"
}
```

### Log Flow

```
Add-on Python app (stdout/stderr)
  ↓
Docker container logging
  ↓
journald logging driver
  ↓
systemd journal
  ↓
Home Assistant Supervisor API
  ↓
Web UI (Logs tab)
```

## Future Improvements

1. **Automatic validation** - Add health check to verify journald is working
2. **Visual indicator** - Show warning in UI if journald is misconfigured
3. **Log retention** - Configure journald log rotation settings
4. **Performance** - Monitor journald impact on container performance

## Files Changed

| File                                            | Change Type | Description                           |
| ----------------------------------------------- | ----------- | ------------------------------------- |
| `.devcontainer/post-start.sh`                   | Modified    | Added journald configuration (Step 0) |
| `.devcontainer/99-enable-journald-logs.sh`      | New         | Manual setup script                   |
| `docs/developer/addon-logs-ui.md`               | New         | Comprehensive documentation           |
| `docs/developer/addon-logs-ui-setup-summary.md` | New         | This summary document                 |

## Testing Checklist

- [x] Docker configured with journald logging driver
- [x] systemd-journal-remote package installed
- [x] journalctl can access add-on logs
- [x] Add-on container is running
- [x] Supervisor can retrieve logs via API
- [ ] Web UI displays logs at `/hassio/addon/local_cync-controller/logs` (user to verify)

## Next Steps for User

1. **Open the add-on logs page** in your browser:

   ```
   http://localhost:8123/hassio/addon/local_cync-controller/logs
   ```

2. **Verify logs appear** - You should see real-time logs with auto-refresh

3. **Test log streaming** - The logs should update automatically as the add-on runs

4. **Try the new aliases** (in a new shell):
   ```bash
   cync-logs-tail   # View recent logs
   cync-logs-follow # Follow logs in real-time
   ```

## Troubleshooting

If logs still don't appear:

1. Hard refresh browser (`Ctrl + Shift + R`)
2. Restart supervisor: `ha supervisor restart`
3. Check configuration: `sudo cat /etc/docker/daemon.json`
4. Run manual setup: `.devcontainer/99-enable-journald-logs.sh`
5. See full troubleshooting guide in `docs/developer/addon-logs-ui.md`

---

_This document provides a summary of changes made to enable add-on logs UI in the devcontainer environment._
