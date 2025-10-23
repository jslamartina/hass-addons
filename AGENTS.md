# AGENTS.md

This file provides guidance for AI coding agents working with the Home Assistant Cync Controller Add-on repository.

## Project Overview

This repository contains Home Assistant add-ons for controlling Cync/C by GE smart devices locally without cloud dependency. The main add-on intercepts device communications and bridges them to Home Assistant via MQTT.

## Quick Start for AI Agents

**First time here? Read in this order:**

1. **Repository Structure** (below) - Understand the project layout
2. **AI Agent Tools** - Know what tools you have available
3. **Development Workflows** - Learn the standard development process
4. **Important Rules** - DON'T section prevents critical mistakes

**Most used commands:**

```bash
ha addons logs local_cync-controller     # View logs
./scripts/configure-addon.sh      # Configure addon
ha addons restart local_cync-controller  # Restart addon
npm run lint                      # Run all linters
npm run lint:python:fix           # Auto-fix Python issues
```

**Critical files:**

- `.devcontainer/README.md` - Devcontainer quirks (read before modifying startup scripts)
- `docs/user/dns-setup.md` - DNS redirection setup (required for addon to work)
- `hass-credentials.env` - Login credentials (Username: `dev`, Password: `dev`)
- [Architecture Guide](docs/developer/architecture.md) - Command flow, ACK handling, protocol details
- [Troubleshooting Guide](docs/user/troubleshooting.md) - Known issues and solutions

## Before Starting ANY Task

**⚠️ CRITICAL:** Python files (`.py`) require **rebuild** (`ha addons rebuild local_cync-controller`), config/scripts only need **restart**. See [Development Workflows](#development-workflows) for details.

## Repository Structure

```
hass-addons/
├── cync-controller/          # Main add-on (Python package, Dockerfile, config)
│   ├── src/cync_lan/         # Python source (server.py, devices.py, mqtt_client.py)
│   └── rebuild.sh            # Rebuild script (use after Python changes)
├── .devcontainer/            # Dev environment (read README.md for quirks!)
├── docs/                     # Documentation
│   ├── developer/            # Dev guides (architecture.md, mcp-tools.md, etc.)
│   ├── user/                 # User docs (dns-setup.md, troubleshooting.md)
│   └── protocol/             # Protocol research (findings.md)
└── scripts/                  # Helper scripts (configure-addon.sh, setup-fresh-ha.sh)
```

**Key files:**
- `cync-controller/src/cync_lan/` - Python package source code
- `.devcontainer/README.md` - Critical devcontainer quirks
- `docs/user/dns-setup.md` - DNS redirection setup (required)
- `scripts/configure-addon.sh` - Programmatic addon configuration


---

## Development Workflows

### ⚠️ CRITICAL: Python vs Config Changes

**Python files (`.py`)** → **MUST REBUILD**:

```bash
cd cync-controller && ./rebuild.sh
# Or: ha addons rebuild local_cync-controller
```

**Config/scripts** (`config.yaml`, `run.sh`, `static/*`) → **JUST RESTART**:

```bash
ha addons restart local_cync-controller
```

**Why?** Python packages are baked into the Docker image at build time. Just restarting won't pick up Python changes.

### Standard Development Workflow

#### 1. Make Your Changes

Edit Python, config, or script files as needed.

#### 2. Run Linters (MANDATORY)

```bash
# Python files
npm run lint:python:fix    # Auto-fix issues
npm run format:python      # Auto-format

# Shell scripts
npm run lint:shell         # Check for warnings

# Everything
npm run lint               # Check all (Python + Shell + Formatting)
npm run format             # Format all files
```

**Fix ALL issues before proceeding** - no exceptions.

#### 3. Build or Restart

```bash
# If you edited Python files:
cd cync-controller && ./rebuild.sh

# If you only edited config/scripts:
ha addons restart local_cync-controller
```

#### 4. Verify

```bash
# Check logs
ha addons logs local_cync-controller --follow

# Check entities (Developer Tools → States → Filter "cync")
```

### Additional Tasks

#### Delete Stale MQTT Entities

Use when you changed `suggested_area` or other discovery fields:

```bash
# Automated (recommended)
sudo python3 scripts/delete-mqtt-safe.py [--dry-run]
ha addons restart local_cync-controller
```

**Manual UI approach**: Settings → Devices & Services → Entities → Enter selection mode → Select entities → Action → Delete selected

#### When In Doubt

**Always rebuild** - it's safer and only takes ~30 seconds more than restart.

---

## Development Environment

### Devcontainer Setup

This project uses a devcontainer based on the Home Assistant add-on development image. **Critical:** Read `.devcontainer/README.md` before modifying any startup scripts - it contains important quirks about Docker initialization and log filtering.

### Quick Start

```bash
# The devcontainer automatically:
# 1. Starts Home Assistant Supervisor
# 2. BACKUP RESTORE CURRENTLY DISABLED (see .devcontainer/post-start.sh)
#    - Comment out lines 131-216 to re-enable test backup restoration
# 3. Sets up the hass-addons repository

# For fresh HA setup with EMQX and Cync Controller:
cd scripts
./setup-fresh-ha.sh  # Automated onboarding, EMQX install, addon config

# Access Home Assistant
# URL: http://localhost:8123
# Credentials: /mnt/supervisor/addons/local/hass-addons/hass-credentials.env
#   Username: dev
#   Password: dev
```

---

## AI Agent Tools

### Web Search

When working with this codebase, AI agents should use web search tools to stay current with:
- Home Assistant API changes and best practices
- Python package updates and security advisories
- Protocol standards and networking concepts
- Docker and containerization best practices

**When to search:**
- Verifying current Home Assistant add-on APIs
- Looking up recent changes in dependencies (asyncio, MQTT, FastAPI, etc.)
- Understanding DNS/networking concepts for device interception
- Researching protocol standards (TCP, SSL/TLS, packet structures)
- Checking for security best practices when dealing with MITM proxies

### Tool Usage Guidelines

#### Tool Policy — Codebase Search First
- Use `codebase_search` to find definitions, call sites, and related files before taking any action.
- Prefer ranked slices from the index over shell greps. Do **not** paste large grep outputs.
- Only use `grep`/`ripgrep` for exact string matches or unindexed/new files.
- For every result, include `file:path:line` and a one-line rationale ("why this matters").
- If results look sparse or noisy, ask a clarifying question rather than broadening to repo-wide grep.

**Rationale:** This keeps the prompt focused on the most relevant code via the editor's codebase indexing and planning flow, reducing errors from noisy context.


### MCP Development Tools

The devcontainer includes several Model Context Protocol (MCP) servers that provide specialized capabilities for development tasks.

**Quick reference:** Time operations, Python execution, Docker management, Git operations, Web content fetching, Filesystem operations.

**📖 See [MCP Tools Guide](docs/developer/mcp-tools.md) for detailed documentation.**

**Key points:**

- Automatic installation via `uvx`/`npx` (no manual setup)
- Configured in `.cursor/mcp.json`
- When MCP tools fail, use standard tools (grep, terminal commands) and continue gracefully

---

## Key Concepts

For architecture details, protocol information, and critical implementation concepts, see **[Architecture Guide](docs/developer/architecture.md)**.

**Quick essentials:**

- **DNS Redirection Required** - Add-on intercepts device traffic (see [DNS Setup](docs/user/dns-setup.md))
- **Command Flow** - MQTT → Callback Registration → TCP Send → ACK → State Update
- **Cloud Relay Mode** - Optional MITM proxy for protocol analysis (read-only currently)

---

## Coding Conventions

For detailed coding standards, linting requirements, and contribution guidelines, see **[CONTRIBUTING.md](CONTRIBUTING.md)**.

**Critical points:**

- **⚠️ Linting is MANDATORY** - Run `npm run lint` after every file edit
- **Python:** Use Ruff for linting/formatting (`npm run lint:python:fix`)
- **Shell scripts:** Must be idempotent (safe to run multiple times)
- **Zero tolerance** for linting errors in PRs

---

## Useful Commands

| Command                                                 | Purpose                                                 |
| ------------------------------------------------------- | ------------------------------------------------------- |
| `ha addons logs local_cync-controller`                  | View add-on logs for debugging                          |
| `./scripts/configure-addon.sh`                          | Configure add-on settings programmatically              |
| `ha addons restart local_cync-controller`               | Restart the add-on (for non-Python changes)             |
| `cd cync-controller && ./rebuild.sh`                    | **Rebuild add-on** (REQUIRED after Python code changes) |
| `ha addons rebuild local_cync-controller`               | Alternative rebuild command using HA CLI                |
| `npm run lint`                                          | Run all linters (Python + Shell + Format check)         |
| `npm run lint:python:fix`                               | Auto-fix Python linting issues with Ruff                |
| `ruff check .`                                          | Check Python code for linting errors                    |
| `./scripts/lint-all.sh`                                 | Alternative: Run all linters via shell script           |
| `docker exec -it addon_local_cync-controller /bin/bash` | Access add-on container shell for debugging             |
| `./scripts/test-cloud-relay.sh`                         | Run comprehensive cloud relay test suite                |
| `sudo python3 scripts/delete-mqtt-safe.py`              | Clean up stale MQTT entities safely                     |

#### Running Scripts That Access Supervisor API

**⚠️ Important:** Scripts that need to access the Home Assistant Supervisor API (e.g., `configure-addon.sh`, `setup-fresh-ha.sh`) **MUST be run from within the `hassio_cli` container** because the `supervisor` hostname is only resolvable inside supervisor-managed containers.

**When running from the devcontainer shell:**

```bash
# ❌ WRONG - Will fail with "Could not resolve host: supervisor"
./scripts/configure-addon.sh get

# ✅ CORRECT - Use ha CLI commands directly (automatically runs in hassio_cli)
ha addons info local_cync-controller --raw-json | jq '.data.options'

# OR: Run individual curl commands inside hassio_cli
docker exec hassio_cli curl -sf \
  -H "Authorization: Bearer $SUPERVISOR_TOKEN" \
  http://supervisor/addons/local_cync-controller/options
```

**Why this matters:**
- The devcontainer shell is **outside** the Home Assistant Supervisor network
- The `supervisor` hostname only resolves inside supervisor-managed containers (like `hassio_cli`, `hassio_supervisor`, and add-on containers)
- Scripts using `curl http://supervisor/...` need to run inside `hassio_cli` OR use `ha` CLI commands
- The `hassio_cli` container **does not** have access to the devcontainer filesystem

**Recommended approach:**
- **Use `ha` CLI commands directly** - They automatically run inside hassio_cli and handle authentication
- **For complex operations**: Create helper scripts that use `ha` CLI internally instead of direct Supervisor API calls
- **For one-off API calls**: Use `docker exec hassio_cli` with inline curl commands

**Scripts behavior:**
- `scripts/configure-addon.sh` - Uses direct Supervisor API, requires `SUPERVISOR_TOKEN` access
- `scripts/setup-fresh-ha.sh` - Uses `docker exec hassio_cli curl ...` internally
- `scripts/test-cloud-relay.sh` - ✅ Works from devcontainer (uses `ha` CLI)
- `cync-controller/rebuild.sh` - ✅ Works from devcontainer (uses `ha` CLI)

### Testing Add-on Configuration Changes

#### Automated Configuration Testing (Recommended)

The project includes automated tools for testing add-on configuration without manual UI interaction:

**`scripts/configure-addon.sh`** - Programmatic configuration via Supervisor API

```bash
# View current configuration
./scripts/configure-addon.sh get

# Set cloud relay options
./scripts/configure-addon.sh set-cloud-relay true true false

# Apply test presets
./scripts/configure-addon.sh preset-baseline              # LAN-only mode
./scripts/configure-addon.sh preset-relay-with-forward    # Cloud relay enabled
./scripts/configure-addon.sh preset-relay-debug           # With packet logging
./scripts/configure-addon.sh preset-lan-only              # Privacy mode

# Utility commands
./scripts/configure-addon.sh restart
./scripts/configure-addon.sh logs
```

**`scripts/test-cloud-relay.sh`** - Comprehensive test suite

```bash
# Run full automated test suite (all phases)
./scripts/test-cloud-relay.sh

# Tests:
# - Phase 1: Baseline LAN-only Mode
# - Phase 2: Cloud Relay with Forwarding
# - Phase 3: Debug Packet Logging
# - Phase 4: LAN-only Relay (Privacy Mode)
# - Phase 5: Packet Injection
# - Phase 6: Return to Baseline
```

**Advantages:**
- ✅ No manual UI interaction required
- ✅ Repeatable and scriptable
- ✅ Fast configuration switching (~15 seconds)
- ✅ Automated validation of expected behaviors
- ✅ Works in devcontainer environment

#### Full Rebuild Workflow (For Schema Changes)

When adding new configuration options or changing the schema:

```bash
# 1. Stop the add-on
ha addons stop local_cync-controller

# 2. Remove all cached Docker images
docker rmi -f $(docker images -q local/aarch64-addon-cync-controller)

# 3. Clear Docker build cache
docker builder prune -af

# 4. Restart Supervisor to clear metadata cache
ha supervisor restart
sleep 10  # Wait for supervisor to fully restart

# 5. Rebuild with fresh cache
ha addons rebuild local_cync-controller

# 6. Verify new version is detected
ha addons info local_cync-controller | grep -E "^version"

# 7. Update (if version changed)
ha addons update local_cync-controller

# 8. Test with automated tools
./scripts/configure-addon.sh get
./scripts/test-cloud-relay.sh
```

#### Manual UI Verification (Optional)

For manual testing or end-user validation:

1. Hard refresh browser (`Ctrl + Shift + R`)
2. Navigate: Settings → Add-ons → [Your Add-on]
3. Verify version number matches expected version
4. Click "Configuration" tab
5. Verify new configuration sections appear
6. Expand sections and verify options are present
7. Make configuration changes and click "Save"
8. Restart add-on from Info tab
9. Check logs for configuration being applied

#### Browser Automation with Playwright

For UI testing with Playwright, **see [Browser Automation Guide](docs/developer/browser-automation.md)** for detailed patterns and best practices.

**Key points:**

- **Prefer API tools** over browser automation (see `scripts/configure-addon.sh`)
- Home Assistant UI uses Shadow DOM - use `getByRole` selectors that pierce through
- Avoid `{force: true}` clicks - they bypass safety checks
- **Credentials**: Username `dev`, Password `dev` (see `hass-credentials.env`)

### Debugging

```bash
# View add-on logs
ha addons logs local_cync-controller

# View supervisor logs (includes add-on lifecycle)
tail -f /tmp/supervisor_run.log

# Access add-on container
docker exec -it addon_local_cync-controller /bin/bash

# Verify environment variables loaded correctly
docker exec addon_local_cync-controller env | grep CYNC_

# Cloud relay packet injection (when relay mode enabled)
# Inject raw packet bytes
echo "73 00 00 00 1e ..." > /tmp/cync_inject_raw_bytes.txt

# Inject mode change for switches
echo "smart" > /tmp/cync_inject_command.txt
# or
echo "traditional" > /tmp/cync_inject_command.txt

# Note: MITM tools have been archived - see docs/archive/mitm/ for historical reference
# Cloud relay mode is the current recommended approach for protocol analysis
```

### Troubleshooting

For common issues and solutions, see **[Troubleshooting Guide](docs/user/troubleshooting.md)**.

---

## Important Rules

### DO

- ✅ Read `.devcontainer/README.md` before modifying startup scripts
- ✅ Use the embedded `cync-controller-python` package (don't duplicate code)
- ✅ Follow Home Assistant add-on best practices (see https://developers.home-assistant.io/)
- ✅ Document protocol findings in `mitm/` when discovering new packet structures
- ✅ Update `CHANGELOG.md` when making user-facing changes
- ✅ Preserve DNS redirection warnings in documentation (users MUST do this)
- ✅ **Add ISO 8601 timestamps when archiving documentation** - When moving ad-hoc documentation, plans, or completed work to `docs/archive/`, name files using format: `YYYY-MM-DDTHH-MM-SS-description.md` (e.g., `2025-10-22T23-15-44-http-error-logging-improvement.md`). Use the file's modification time as the timestamp.

### DON'T

- ❌ **Don't just restart the add-on after editing Python files** (you MUST rebuild with `./rebuild.sh`)
- ❌ Don't start Docker manually in `post-start.sh` (supervisor_run handles this)
- ❌ Don't remove Docker CLI version pinning (prevents version mismatch issues)
- ❌ Don't modify the backup restore logic without testing thoroughly
- ❌ Don't hardcode IP addresses or credentials (use config options)
- ❌ Don't bypass the MQTT discovery schema (breaks Home Assistant integration)
- ❌ Don't commit `hass-credentials.env` (contains dev credentials)
- ❌ **Don't remove callback registration from command methods** (causes silent failures - commands send but devices don't respond)
- ❌ **Don't add automatic refresh after command ACKs** (causes cascading refreshes that break subsequent commands)
- ❌ **Don't mark devices offline immediately from mesh info** (use offline_count with threshold to prevent flickering)

---

## PR Instructions

See **[CONTRIBUTING.md](CONTRIBUTING.md)** for full PR guidelines, testing checklist, documentation standards, and file naming conventions.

**Quick checklist:**
- Run `npm run lint` and `npm run format` - must pass
- Update CHANGELOG.md for user-facing changes
- Test in devcontainer
- Title format: `[component] Brief description`

---

## Resources & Getting Help

**Documentation:**
- [Architecture Guide](docs/developer/architecture.md) - Key concepts and protocol details
- [CONTRIBUTING.md](CONTRIBUTING.md) - Coding standards and PR guidelines
- [Troubleshooting Guide](docs/user/troubleshooting.md) - Common issues and solutions
- [MCP Tools Guide](docs/developer/mcp-tools.md) - Development tools reference
- [Browser Automation Guide](docs/developer/browser-automation.md) - Playwright patterns
- [Protocol Research](docs/protocol/findings.md) - Protocol reverse engineering notes

**External Resources:**
- [Home Assistant Add-on Documentation](https://developers.home-assistant.io/docs/add-ons/)
- [MQTT Discovery Schema](https://www.home-assistant.io/integrations/mqtt/#mqtt-discovery)

**Project Files:**
- `.devcontainer/README.md` - Devcontainer quirks and setup
- `docs/user/dns-setup.md` - DNS redirection setup (required)
- `scripts/README.md` - Helper scripts reference

---

_Last updated: October 22, 2025_
