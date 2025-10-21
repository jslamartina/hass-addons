# Devcontainer Setup Scripts

This directory contains setup scripts for the Cync Controller development environment.

## File Organization

### Setup Scripts (in execution order)

#### Addon Development (Node.js/Prettier)
- **`00-setup-prettier.sh`** - Sets up Node.js and Prettier for addon development
- **`addon-format-code.sh`** - Formats code with Prettier (utility script)

#### Browser Automation (Playwright)
- **`03-setup-playwright.sh`** - Installs Playwright browsers and configures testing environment

#### Python Package Development (cync-controller)
- **`01-00-python-setup-all.sh`** - Master script that runs all Python development scripts in order
- **`01-01-python-env-setup.sh`** - Sets up Python development environment
- **`01-02-python-clone-repo.sh`** - Clones the cync-controller repository
- **`01-03-python-workspace-setup.sh`** - Sets up development workspace
- **`01-04-python-vscode-configure.sh`** - Configures VS Code for Python development
- **`01-05-python-venv-setup.sh`** - Sets up Python virtual environment

### Workspace Files
- **`hass-cync-dev.code-workspace`** - Multi-root workspace configuration (in repo root)

## Devcontainer Configuration

The main `.devcontainer.json` file (in the root directory) is configured to:
1. Use the Home Assistant devcontainer base image
2. Install Python 3.12 with development tools
3. Mount your local `cync-controller` repository for live editing
4. Automatically run setup scripts on container creation:
   - `00-setup-prettier.sh` (Node.js/Prettier)
   - `03-setup-playwright.sh` (Playwright browser automation)
   - `01-00-python-setup-all.sh` (Python environment with uv & cync-controller repo)
5. MCP servers are managed via `.cursor/mcp.json` and auto-installed by uvx/npx on first use

## Usage

### Automatic (via devcontainer)
The scripts run automatically when the devcontainer is created.

### Manual
```bash
# Run all Python development setup
bash .devcontainer/01-00-python-setup-all.sh

# Run individual scripts in order
bash .devcontainer/00-setup-prettier.sh        # Addon setup first
bash .devcontainer/03-setup-playwright.sh      # Playwright browsers
bash .devcontainer/01-01-python-env-setup.sh   # Python env (includes uv)
bash .devcontainer/01-02-python-clone-repo.sh  # Clone repo
bash .devcontainer/01-03-python-workspace-setup.sh # Setup workspace
bash .devcontainer/01-04-python-vscode-configure.sh # Configure IDE
bash .devcontainer/01-05-python-venv-setup.sh  # Virtual environment

# Format code (utility)
bash .devcontainer/addon-format-code.sh

# Delete entities via Playwright
npm run playwright:delete-entities switch.hallway_front_switch switch.hallway_counter_switch
```

## Directory Structure After Setup

```
/mnt/supervisor/addons/local/
├── hass-addons/           # Home Assistant addon repository
│   ├── hass-cync-dev.code-workspace  # Multi-repo workspace file
│   └── test-cync-controller.sh   # Test script
├── cync-controller/              # Python package repository
└── .vscode/               # Global VS Code settings
```

## Development Workflow

### Multi-Repository Setup

**To automatically load both repositories:**
1. From your **local machine**, open the file: `hass-cync-dev.code-workspace`
2. VS Code/Cursor will prompt to "Reopen in Container"
3. Both repositories will load automatically in the multi-root workspace

**If you opened the folder first (single repo view):**
1. Inside the container, click File → Open Workspace from File
2. Select: `hass-cync-dev.code-workspace`
3. This will reload with both hass-addons and cync-controller repositories

### Daily Development
1. Make changes to either repository
2. Test with: `./test-cync-controller.sh`
3. Format code: `npm run format`

## Important Quirks and Gotchas

### Docker CLI Version Pinning

The `post-start.sh` script includes a Docker CLI version pinning workaround (Step 5). Home Assistant pins the Docker CLI image to match the exact daemon version (e.g., `docker:28.5.0-cli`), but Docker doesn't always publish CLI images for every patch version.

**The workaround:**
1. Pulls the major version that exists (e.g., `docker:28-cli`)
2. Tags it as the specific version HA expects (e.g., `docker:28.5.0-cli`)

This prevents the devcontainer from breaking when HA updates to a Docker version that doesn't have a matching CLI image in the registry. **Do not remove this step.**

### Supervisor Log Filtering

To suppress DEBUG logs from Home Assistant Supervisor during startup while preserving them for debugging:

```bash
# Start supervisor_run with script to provide TTY, logs to file only
sudo script -qefc 'sudo supervisor_run' /tmp/supervisor_run.log > /dev/null 2>&1 &
# Tail the log file and filter out DEBUG lines for console display
tail -f /tmp/supervisor_run.log 2>/dev/null | grep --line-buffered -v "DEBUG" &
```

**Key details:**
- `script -qefc` provides a pseudo-TTY (required for `stty sane` command in supervisor_run)
- `> /dev/null 2>&1` suppresses script's console output (it outputs to BOTH file AND stdout by default)
- Full logs (with DEBUG) are saved to `/tmp/supervisor_run.log`
- `tail -f` with `grep --line-buffered -v "DEBUG"` shows only INFO+ messages on console
- The `-f` flag on script ensures immediate flushing to prevent buffering issues

### Docker Startup - Critical Warning

**DO NOT start Docker separately before running `supervisor_run`.**

The `supervisor_run` script has its own Docker initialization (via `start_docker` function in `/etc/supervisor_scripts/common`) and will hang with "Waiting for Docker to initialize" if Docker is already running.

**Why it breaks:**
- The script uses `set -e` (exit immediately on any command failure)
- When Docker is already running, `stty sane` fails (no TTY needed)
- `set -e` sees the failure and exits the entire script before starting the supervisor container

**Let supervisor_run handle:**
- Starting Docker
- Starting systemd-journald
- Starting dbus, udev, and os-agent
- All other system initialization

Any duplicate Docker startup in post-start.sh will cause the hang.

### Supervisor API Access from Devcontainer

**The devcontainer is NOT in the hassio Docker network**, which means the `supervisor` hostname doesn't resolve. This affects how you check component health during startup.

**What doesn't work:**
```bash
# ❌ This fails - hostname 'supervisor' doesn't resolve
curl -s http://supervisor/core/info
```

**What works:**
```bash
# ✅ Use ha CLI - automatically handles networking
ha core info --raw-json | jq -r '.data.version'

# ✅ Or use the supervisor IP directly
SUPERVISOR_IP=$(docker network inspect hassio | jq -r '.[0].Containers | to_entries[] | select(.value.Name | contains("supervisor")) | .value.IPv4Address' | cut -d'/' -f1)
curl -s -H "Authorization: Bearer ${TOKEN}" "http://${SUPERVISOR_IP}/core/info"
```

**Why this matters:**
The health check in `post-start.sh` (lines 89-132) uses `ha` CLI commands instead of direct curl requests because:
1. The devcontainer runs in the default Docker bridge network
2. The supervisor and plugins run in the isolated `hassio` network (172.30.32.0/24)
3. DNS resolution for `supervisor` only works within the `hassio` network
4. The `ha` CLI connects via Unix socket or other mechanisms that work across networks

**Historical issue:** Prior to this fix, the health check script used curl with `http://supervisor/` which caused 240-second timeouts during startup because all health checks failed silently.

