# Devcontainer Setup Scripts

This directory contains setup scripts for the CyncLAN development environment.

## File Organization

### Setup Scripts (in execution order)

#### Addon Development (Node.js/Prettier)
- **`00-setup-prettier.sh`** - Sets up Node.js and Prettier for addon development
- **`addon-format-code.sh`** - Formats code with Prettier (utility script)

#### MCP (Model Context Protocol) Servers
- **`02-setup-mcp-servers.sh`** - Installs MCP server packages for AI assistant integration

#### Browser Automation (Playwright)
- **`03-setup-playwright.sh`** - Installs Playwright browsers and configures testing environment

#### Python Package Development (cync-lan)
- **`01-00-python-setup-all.sh`** - Master script that runs all Python development scripts in order
- **`01-01-python-env-setup.sh`** - Sets up Python development environment
- **`01-02-python-clone-repo.sh`** - Clones the cync-lan repository
- **`01-03-python-workspace-setup.sh`** - Sets up development workspace
- **`01-04-python-vscode-configure.sh`** - Configures VS Code for Python development
- **`01-05-python-venv-setup.sh`** - Sets up Python virtual environment

### Workspace Files
- **`hass-cync-dev.code-workspace`** - Multi-root workspace configuration (in repo root)

## Devcontainer Configuration

The main `.devcontainer.json` file (in the root directory) is configured to:
1. Use the Home Assistant devcontainer base image
2. Install Python 3.12 with development tools
3. Mount your local `cync-lan` repository for live editing
4. Automatically run setup scripts on container creation:
   - `00-setup-prettier.sh` (Node.js/Prettier)
   - `02-setup-mcp-servers.sh` (MCP server packages)
   - `03-setup-playwright.sh` (Playwright browser automation)
   - `01-00-python-setup-all.sh` (Python environment & cync-lan repo)

## Usage

### Automatic (via devcontainer)
The scripts run automatically when the devcontainer is created.

### Manual
```bash
# Run all Python development setup
bash .devcontainer/01-00-python-setup-all.sh

# Run individual scripts in order
bash .devcontainer/00-setup-prettier.sh        # Addon setup first
bash .devcontainer/02-setup-mcp-servers.sh     # MCP server packages
bash .devcontainer/03-setup-playwright.sh      # Playwright browsers
bash .devcontainer/01-01-python-env-setup.sh   # Then Python env
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
│   └── test-cync-lan.sh   # Test script
├── cync-lan/              # Python package repository
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
3. This will reload with both hass-addons and cync-lan repositories

### Daily Development
1. Make changes to either repository
2. Test with: `./test-cync-lan.sh`
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

