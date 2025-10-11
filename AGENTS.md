# AGENTS.md

This file provides guidance for AI coding agents working with the Home Assistant CyncLAN Add-on repository.

## Project Overview

This repository contains Home Assistant add-ons for controlling Cync/C by GE smart devices locally without cloud dependency. The main add-on intercepts device communications and bridges them to Home Assistant via MQTT.

## Repository Structure

```
/mnt/supervisor/addons/local/hass-addons/
├── cync-lan/                    # Main CyncLAN add-on
│   ├── cync-lan-python/        # Embedded Python package (submodule/symlink)
│   ├── Dockerfile              # Add-on container build
│   ├── config.yaml             # Add-on configuration schema
│   ├── run.sh                  # Add-on entry point
│   └── static/                 # Web UI for device export
├── .devcontainer/              # Development container setup
│   ├── post-start.sh           # Devcontainer startup script
│   ├── post-create.sh          # Initial setup script
│   └── README.md               # Devcontainer documentation (IMPORTANT: read this!)
├── mitm/                       # MITM testing tools for protocol analysis
├── docs/                       # Documentation
├── test-cync-lan.sh           # Quick test script
└── EXPLORATION_NOTES.md       # System exploration findings (for reference)
```

## Development Environment

### Devcontainer Setup

This project uses a devcontainer based on the Home Assistant add-on development image. **Critical:** Read `.devcontainer/README.md` before modifying any startup scripts - it contains important quirks about Docker initialization and log filtering.

### Quick Start

```bash
# The devcontainer automatically:
# 1. Starts Home Assistant Supervisor
# 2. Restores a test backup with sample devices
# 3. Sets up both hass-addons and cync-lan repositories

# Test the add-on
./test-cync-lan.sh

# Access Home Assistant
# URL: http://localhost:8123
# Credentials: dev/dev (stored in hass-credentials.env)
```

## Key Concepts

### Cloud Relay Mode

**New in v0.0.4.0**: The add-on can optionally act as a Man-in-the-Middle (MITM) proxy between devices and Cync cloud, enabling:
- Real-time packet inspection and logging
- Protocol analysis and debugging
- Cloud backup (devices still work if relay goes down)
- LAN-only operation (no cloud forwarding)

**Configuration** (`config.yaml`):
```yaml
cloud_relay:
  enabled: false                      # Enable relay mode
  forward_to_cloud: true              # Forward packets to cloud (false = LAN-only)
  cloud_server: "35.196.85.236"       # Cync cloud server IP
  cloud_port: 23779                   # Cync cloud port
  debug_packet_logging: false         # Log parsed packets (verbose)
  disable_ssl_verification: false     # Disable SSL verify (debug only)
```

**Use Cases:**
- **Protocol Analysis**: Enable `debug_packet_logging` to see all packet structures
- **Debugging**: Test device behavior while observing cloud interactions
- **LAN-only with inspection**: Set `forward_to_cloud: false` to block cloud access while logging packets
- **Cloud backup**: Keep `forward_to_cloud: true` so devices work even if relay fails

**Security Warning**: If `disable_ssl_verification: true`, the add-on operates in DEBUG MODE with no SSL security. Only use on trusted local networks for development.

### Architecture

The CyncLAN add-on has three main components:

1. **Exporter** - FastAPI web server for exporting device configuration from Cync cloud (2FA via emailed OTP)
2. **nCync** - Async TCP server that masquerades as Cync cloud (requires DNS redirection)
   - **Optional Cloud Relay Mode** - Can act as MITM proxy to forward traffic to/from real cloud while inspecting packets
3. **MQTT Client** - Bridges device states to Home Assistant using MQTT discovery

### DNS Requirement

**Critical:** The add-on requires DNS redirection to intercept device traffic. See `docs/cync-lan/DNS.md` for setup instructions. Without this, devices will still communicate with Cync cloud.

## Coding Conventions

### Shell Scripts

- Use `bashio::` functions for add-on scripts (provided by Home Assistant base image)
- Always use `set -e` for error handling
- Use descriptive variable names in SCREAMING_SNAKE_CASE for environment variables
- Comment complex logic, especially protocol-specific code

### Python (cync-lan package)

- Follow Black formatter style (configured in pyproject.toml)
- Use type hints for function signatures
- Async/await for all I/O operations (TCP, MQTT, HTTP)
- Logging prefix format: `lp = "ClassName:method_name:"`
- Use dataclasses or Pydantic models for structured data

### Configuration Files

- Add-on config: `cync-lan/config.yaml` (JSON Schema format)
- Environment variables: Prefix with `CYNC_` for add-on settings
- MQTT topics: Follow Home Assistant MQTT discovery schema

## Common Tasks

### Building the Add-on

```bash
# Rebuild from scratch (useful after Python package changes)
cd cync-lan
./rebuild.sh

# Or use Home Assistant CLI
ha addons rebuild local_cync-lan
```

### Testing

```bash
# Quick functional test
./test-cync-lan.sh

# Manual testing
ha addons start local_cync-lan
ha addons logs local_cync-lan --follow

# Check entity states in Home Assistant
# Developer Tools → States → Filter for "cync"
```

### Debugging

```bash
# View add-on logs
ha addons logs local_cync-lan

# View supervisor logs (includes add-on lifecycle)
tail -f /tmp/supervisor_run.log

# Access add-on container
docker exec -it addon_local_cync-lan /bin/bash

# Cloud relay packet injection (when relay mode enabled)
# Inject raw packet bytes
echo "73 00 00 00 1e ..." > /tmp/cync_inject_raw_bytes.txt

# Inject mode change for switches
echo "smart" > /tmp/cync_inject_command.txt
# or
echo "traditional" > /tmp/cync_inject_command.txt

# MITM testing (legacy standalone tool for protocol analysis)
cd mitm
./run_mitm.sh
# See mitm/README.md for detailed usage
# Note: Cloud relay mode is now the recommended approach
```

## Important Rules

### DO

- ✅ Read `.devcontainer/README.md` before modifying startup scripts
- ✅ Test changes with `./test-cync-lan.sh` before committing
- ✅ Use the embedded `cync-lan-python` package (don't duplicate code)
- ✅ Follow Home Assistant add-on best practices (see https://developers.home-assistant.io/)
- ✅ Document protocol findings in `mitm/` when discovering new packet structures
- ✅ Update `CHANGELOG.md` when making user-facing changes
- ✅ Preserve DNS redirection warnings in documentation (users MUST do this)

### DON'T

- ❌ Don't start Docker manually in `post-start.sh` (supervisor_run handles this)
- ❌ Don't remove Docker CLI version pinning (prevents version mismatch issues)
- ❌ Don't modify the backup restore logic without testing thoroughly
- ❌ Don't hardcode IP addresses or credentials (use config options)
- ❌ Don't bypass the MQTT discovery schema (breaks Home Assistant integration)
- ❌ Don't commit `hass-credentials.env` (contains dev credentials)

## File Naming Conventions

- **Shell scripts**: `kebab-case.sh` (e.g., `test-cync-lan.sh`)
- **Python files**: `snake_case.py` (e.g., `mqtt_client.py`)
- **Documentation**: `SCREAMING_CAPS.md` for top-level, `kebab-case.md` for docs/ folder
- **Directories**: `kebab-case/` preferred

## Testing Checklist

Before submitting changes:

1. [ ] Add-on builds successfully (`./rebuild.sh` or `ha addons rebuild`)
2. [ ] Add-on starts without errors (`ha addons start local_cync-lan`)
3. [ ] Entities appear in Home Assistant (check Developer Tools → States)
4. [ ] Device commands work (toggle lights, adjust brightness)
5. [ ] MQTT messages are valid (check EMQX logs or `mosquitto_sub`)
6. [ ] No Python exceptions in logs (`ha addons logs local_cync-lan`)
7. [ ] Devcontainer still starts cleanly (test in fresh container)
8. [ ] Changes documented in CHANGELOG.md if user-facing

## External Resources

- [Home Assistant Add-on Documentation](https://developers.home-assistant.io/docs/add-ons/)
- [Cync Protocol Research](mitm/FINDINGS_SUMMARY.md) - Our protocol reverse engineering notes
- [MQTT Discovery Schema](https://www.home-assistant.io/integrations/mqtt/#mqtt-discovery)
- [DNS Redirection Setup](docs/cync-lan/DNS.md)

## Getting Help

- Check `EXPLORATION_NOTES.md` for UI navigation and system state reference
- Review `mitm/FINDINGS_SUMMARY.md` for protocol details
- Read `.devcontainer/README.md` for devcontainer quirks
- See `docs/cync-lan/troubleshooting.md` for common issues

## Version Information

- **Python**: 3.12+ (configured in `.devcontainer.json`)
- **Home Assistant**: 2025.10+ (dev branch)
- **Node.js**: LTS (for Prettier formatting)
- **Docker**: Managed by supervisor_run (see devcontainer README)

---

*Last Updated: October 2025*
*For exploration findings from UI testing, see `EXPLORATION_NOTES.md`*

