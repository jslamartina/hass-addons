# AGENTS.md

This file provides guidance for AI coding agents working with the Home Assistant CyncLAN Add-on repository.

## Project Overview

This repository contains Home Assistant add-ons for controlling Cync/C by GE smart devices locally without cloud dependency. The main add-on intercepts device communications and bridges them to Home Assistant via MQTT.

## Quick Start for AI Agents

**First time here? Read in this order:**

1. **Repository Structure** (below) - Understand the project layout
2. **AI Agent Tools** - Know what tools you have available
3. **Common Tasks** - Learn frequent workflows
4. **Important Rules** - DON'T section prevents critical mistakes

**Most used commands:**

```bash
ha addons logs local_cync-lan     # View logs
./scripts/configure-addon.sh      # Configure addon
ha addons restart local_cync-lan  # Restart addon
npm run lint                      # Run all linters
npm run lint:python:fix           # Auto-fix Python issues
```

**Critical files to know:**

- `.devcontainer/README.md` - Docker quirks and devcontainer gotchas
- `docs/protocol/findings.md` - Protocol reverse engineering documentation
- `docs/user/dns-setup.md` - DNS redirection setup (required for addon to work)
- `CHANGELOG.md` - Version history and breaking changes
- `hass-credentials.env` - Home Assistant login credentials (Username: `dev`, Password: `dev`)
- `docs/developer/linting-setup.md` - Linting setup summary (Ruff configuration and npm scripts)

**Important sections:**
- **Command Flow and ACK Handling** (below) - Critical for understanding how commands work
- **Known Issues and Solutions** (below) - Common bugs and their fixes
- **Browser Automation with Playwright** (below) - How to properly click elements in HA UI
- **PR Instructions** (below) - Guidelines for submitting pull requests

## Before Starting ANY Task: Mandatory Checklist

**🛑 STOP. Before writing ANY code or making changes, answer these questions:**

1. **What type of files am I about to modify?**
   - [ ] Python files (`.py`) → You MUST rebuild after (`ha addons rebuild local_cync-lan`)
   - [ ] Config/shell scripts (`config.yaml`, `run.sh`) → You only need to restart after
   - [ ] Documentation/static files → No rebuild needed

2. **What is the correct workflow for this change type?**
   - Write out the workflow explicitly before proceeding
   - Check the "Workflow: Making Code Changes" section below

3. **Have I checked if there's a dedicated tool/script for this task?**
   - Check: Common Tasks, Testing sections, scripts/ directory

**⚠️ If you skip this checklist, you WILL waste time with changes that don't take effect.**

## Task Planning and Tracking

### Using Plan Files

When working on complex multi-step tasks, you may create plan files in `.cursor/plans/`. These are static markdown documents with checkboxes that outline the implementation strategy.

**Important:** Plan files do NOT automatically update when you complete tasks. You must manually update them.

**When to update plan files:**

1. **At major milestones** - After completing a significant phase
2. **At task completion** - Mark all checkboxes complete and add summary
3. **When blocked** - Document blockers or changes to approach

**How to update a plan file:**

```markdown
### To-dos

- [x] Task 1 description (✅ completed with notes)
- [x] Task 2 description
- [ ] Task 3 description (⚠️ blocked: reason)

## ✅ Implementation Complete (or "In Progress" or "Blocked")

Brief summary of current state and any notes.
```

**Best practice:** Update the plan file **after completing each step**, not just at the end. This provides real-time progress visibility and demonstrates the incremental update workflow.

**Example workflow:**
1. Complete a task (e.g., update .gitignore)
2. Immediately update the plan file: `- [x] Update .gitignore ✅`
3. Move to next task
4. Repeat

This approach helps track progress during long-running tasks and makes it clear what's done vs pending.

## Repository Structure

```
/mnt/supervisor/addons/local/hass-addons/
├── cync-lan/                   # Main CyncLAN add-on directory
│   ├── src/cync_lan/          # Python package source code
│   │   ├── __init__.py
│   │   ├── main.py            # CLI entry point
│   │   ├── server.py          # TCP server (masquerades as Cync cloud)
│   │   ├── devices.py         # Device classes and command handling
│   │   ├── mqtt_client.py     # MQTT integration for Home Assistant
│   │   ├── exporter.py        # Web interface for device export
│   │   ├── cloud_api.py       # Cync cloud API integration
│   │   └── metadata/          # Device metadata and model info
│   ├── pyproject.toml         # Package configuration and dependencies
│   ├── README-DEV.md          # Developer workflow guide
│   ├── Dockerfile             # Add-on container build
│   ├── config.yaml            # Add-on configuration schema
│   ├── run.sh                 # Add-on entry point
│   ├── rebuild.sh             # Rebuilds and restarts add-on
│   └── static/                # Web UI for device export
├── .devcontainer/             # Development container setup
│   ├── post-start.sh          # Devcontainer startup script
│   ├── post-create.sh         # Initial setup script
│   └── README.md              # Devcontainer documentation (IMPORTANT: read this!)
├── mitm/                      # MITM testing tools for protocol analysis
├── docs/                      # Documentation
│   ├── user/                  # User-facing documentation (DNS setup, troubleshooting, tips)
│   ├── developer/             # Developer documentation (CLI reference, entity management, cloud relay)
│   ├── protocol/              # Protocol research (packet structure, debugging sessions, findings)
│   └── archive/               # Historical documentation and archived research
└── scripts/                   # Development and testing scripts
```

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

# Access Home Assistant
# URL: http://localhost:8123
# Credentials: /mnt/supervisor/addons/local/hass-addons/hass-credentials.env
#   Username: dev
#   Password: dev
```

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

The devcontainer includes several Model Context Protocol (MCP) servers that provide specialized capabilities for development tasks. MCP servers are managed via `.cursor/mcp.json` and automatically installed by `uvx`/`npx` on first use (no manual installation required).

#### Quick Reference

| MCP Server               | Primary Use          | Key Functions                                          | When to Use                                                   |
| ------------------------ | -------------------- | ------------------------------------------------------ | ------------------------------------------------------------- |
| `mcp-server-time`        | Timezone operations  | `get_current_time`, `convert_time`                     | Scheduling, timestamps, DST calculations                      |
| `mcp-python-interpreter` | Code execution       | `run_python_code` (native Python, filesystem access)   | Large file processing, data analysis, prototyping, automation |
| `mcp-server-docker`      | Container management | 15 functions (containers/images/networks/volumes)      | Inspecting containers, managing dev environments              |
| `mcp-server-fetch`       | Web content          | `fetch` (markdown/HTML modes)                          | Reading docs, fetching API specs, release notes               |
| `mcp-server-git`         | Version control      | 12 Git operations                                      | Analyzing history, managing branches, reviewing changes       |
| `mcp-server-filesystem`  | File operations      | `read_file`, `write_file`, `edit_file`, `search_files` | Bulk file edits, transformations, reading/writing files       |

**Installation:** Automatic via `uvx`/`npx` on first use. The `uv` package manager is installed during devcontainer creation via `.devcontainer/02-setup-mcp-servers.sh`, then `uvx` automatically downloads and caches MCP servers when Cursor first connects to them (configured in `.cursor/mcp.json`).

#### Tool Limitations & Error Handling

**Known Limitations:**

- **Python MCP**: Native Python execution with full filesystem access. Can install packages on-demand but installations are temporary per execution.
- **Filesystem MCP**: Only has access to directories specified in configuration (scoped access)
- **Docker MCP**: Requires Docker socket access (may fail in restricted environments)
- **Git MCP**: Operations are synchronous (may be slow for large repositories)
- **Fetch MCP**: Respects robots.txt (some sites may block automated access)

**When MCP tools fail:**

1. ✅ **Don't stop the task** - use alternative approaches
2. ✅ **Try standard tools** - grep, file operations, terminal commands
3. ✅ **Mention the failure** - note what failed in your response
4. ✅ **Continue gracefully** - MCP tools are productivity enhancers, not blockers

**Fallback example:**

```python
# Preferred: MCP Docker tool
try:
    logs = mcp_docker_fetch_container_logs("addon_local_cync-lan", tail=100)
except:
    # Fallback: Standard terminal command
    logs = run_terminal_cmd("docker logs addon_local_cync-lan --tail 100")
```

---

#### Detailed Tool Documentation

#### Time Operations (`mcp-server-time`)

**Tools Available:**
- `mcp_time_get_current_time` - Get current time in any timezone
- `mcp_time_convert_time` - Convert time between timezones

**When to use:**
- Scheduling tasks across different timezones
- Logging with timezone-aware timestamps
- Testing time-dependent functionality
- Understanding UTC offsets and DST behavior

**Example use cases:**
```python
# Get current time in multiple zones for log correlation
chicago_time = get_current_time("America/Chicago")
tokyo_time = get_current_time("Asia/Tokyo")

# Convert meeting time for international collaboration
convert_time("America/New_York", "14:00", "Europe/London")
```

**Features:**
- ✅ Automatic DST detection
- ✅ Day of week calculation
- ✅ Timezone offset information
- ✅ Time difference calculation for conversions

#### Python Code Execution (`mcp-python-interpreter`)

**Tools Available:**
- `mcp_python_run_python_code` - Execute native Python code with full filesystem access

**When to use:**
- **Large file processing** - Process files directly without loading into context
- Quick Python calculations and data processing
- Testing Python code snippets before implementation
- Data analysis and statistical computations
- Prototyping algorithms
- File transformations and analysis
- Validating JSON/YAML transformations

**Example use cases:**
```python
# Process large files without loading into context
from pathlib import Path

file = Path("cync-lan/src/cync_lan/mqtt_client.py")
content = file.read_text()
line_count = len(content.split("\n"))
print(f"Processed {len(content)} characters in {line_count} lines")

# File transformations
import re
source = Path("input.py").read_text()
transformed = re.sub(r'old_pattern', 'new_pattern', source)
Path("output.py").write_text(transformed)

# Test data transformation logic
data = {"numbers": [1, 2, 3, 4, 5]}
result = sum(data["numbers"]) / len(data["numbers"])

# Validate regex patterns
import re
pattern = r'^[a-z0-9_-]{3,16}$'
test_cases = ["valid_user", "test-123", "ab"]
matches = [bool(re.match(pattern, t)) for t in test_cases]

# Parse and validate configuration
import json
config = json.loads('{"key": "value"}')
```

**Features:**
- ✅ **Native Python 3.13** (CPython, not WebAssembly)
- ✅ **Full filesystem access** - Use `open()`, `Path()`, etc. on host files
- ✅ **Process large files** without context limitations
- ✅ Full standard library access (json, datetime, math, statistics, pathlib, etc.)
- ✅ Async/await support with asyncio
- ✅ Return value extraction and stdout/stderr capture
- ✅ Working directory: `/mnt/supervisor/addons/local/hass-addons`

**Key Advantage:**
Unlike the old Pyodide-based `mcp-run-python`, this runs native Python with direct filesystem access. You can process multi-megabyte files without tokenizing them into context, making it ideal for bulk file operations and transformations.

#### Docker Management (`mcp-server-docker`)

**Tools Available (15 total):**

**Container Operations:**
- `mcp_docker_list_containers` - List all Docker containers
- `mcp_docker_create_container` - Create a new container
- `mcp_docker_run_container` - Run an image in a new container (preferred over create + start)
- `mcp_docker_start_container` - Start a stopped container
- `mcp_docker_stop_container` - Stop a running container
- `mcp_docker_remove_container` - Remove a container
- `mcp_docker_fetch_container_logs` - Get container logs

**Image Operations:**
- `mcp_docker_list_images` - List Docker images
- `mcp_docker_pull_image` - Pull an image from registry
- `mcp_docker_build_image` - Build image from Dockerfile
- `mcp_docker_remove_image` - Remove an image

**Network & Volume Operations:**
- `mcp_docker_list_networks` - List Docker networks
- `mcp_docker_create_network` - Create a network
- `mcp_docker_list_volumes` - List volumes
- `mcp_docker_create_volume` - Create a volume

**When to use:**
- Managing addon containers during development
- Inspecting container states and logs
- Testing container configurations
- Managing development networks and volumes
- Building and testing Docker images

**Example use cases:**
```bash
# Check addon container status
list_containers(all=True, filters={"label": ["io.hass.type=addon"]})

# Inspect addon logs for debugging
fetch_container_logs("addon_local_cync-lan", tail=100)

# Manage test networks for multi-container testing
create_network("cync-test-net", driver="bridge")
```

#### Web Content Fetching (`mcp-server-fetch`)

**Tools Available:**
- `mcp_web_fetch_fetch` - Fetch URL content as simplified markdown or raw HTML

**When to use:**
- Reading documentation from external sources
- Fetching API documentation or specifications
- Retrieving release notes or changelogs
- Analyzing web page structure
- Extracting information from online resources

**Example use cases:**
```python
# Fetch Home Assistant documentation
content = fetch("https://www.home-assistant.io/integrations/mqtt/",
               max_length=5000)

# Get raw HTML for parsing
raw_html = fetch("https://example.com/api-docs",
                raw=True, max_length=10000)

# Continue reading with offset for long pages
fetch("https://long-article.com", start_index=5000, max_length=5000)
```

**Features:**
- ✅ Automatic markdown conversion (simplified content)
- ✅ Raw HTML mode for custom parsing
- ✅ Configurable content length limits
- ✅ Start index for pagination
- ✅ Respects robots.txt

#### Git Operations (`mcp-server-git`)

**Tools Available:**
- `mcp_git_git_status` - Shows working tree status
- `mcp_git_git_diff_unstaged` - Shows unstaged changes
- `mcp_git_git_diff_staged` - Shows staged changes
- `mcp_git_git_diff` - Shows differences between branches/commits
- `mcp_git_git_commit` - Records changes to repository
- `mcp_git_git_add` - Adds file contents to staging area
- `mcp_git_git_reset` - Unstages all staged changes
- `mcp_git_git_log` - Shows commit logs with filtering
- `mcp_git_git_create_branch` - Creates a new branch
- `mcp_git_git_checkout` - Switches branches
- `mcp_git_git_show` - Shows contents of a commit
- `mcp_git_git_branch` - Lists branches with filtering

**When to use:**
- Analyzing repository history and changes
- Creating and managing branches
- Reviewing staged/unstaged changes
- Filtering commits by timestamp
- Checking branch relationships

**Example use cases:**
```bash
# Check what's changed in working directory
git_status("/mnt/supervisor/addons/local/hass-addons")

# Review unstaged changes before committing
git_diff_unstaged("/mnt/supervisor/addons/local/hass-addons", context_lines=5)

# Find commits in last week
git_log(repo_path=".", start_timestamp="1 week ago", max_count=20)

# Create feature branch
git_create_branch(repo_path=".", branch_name="feature/mcp-docs",
                 base_branch="main")
```

**Features:**
- ✅ Full Git workflow support
- ✅ Timestamp-based log filtering (ISO 8601, relative dates)
- ✅ Branch filtering (by commit containment)
- ✅ Configurable context lines for diffs
- ✅ Works with any local Git repository

#### Filesystem Operations (`mcp-server-filesystem`)

**Tools Available:**
- `mcp_filesystem_read_text_file` - Read file contents as text
- `mcp_filesystem_read_media_file` - Read images/audio as base64
- `mcp_filesystem_read_multiple_files` - Read multiple files simultaneously
- `mcp_filesystem_write_file` - Create or overwrite files
- `mcp_filesystem_edit_file` - Make line-based edits with diff output
- `mcp_filesystem_create_directory` - Create directories
- `mcp_filesystem_list_directory` - List directory contents
- `mcp_filesystem_list_directory_with_sizes` - List with file sizes
- `mcp_filesystem_directory_tree` - Get recursive tree structure
- `mcp_filesystem_move_file` - Move or rename files
- `mcp_filesystem_search_files` - Search for patterns in files
- `mcp_filesystem_get_file_info` - Get file metadata
- `mcp_filesystem_list_allowed_directories` - List accessible directories

**When to use:**
- **Bulk file operations** - Read, transform, and write entire files
- **Complex transformations** - Multi-line edits, regex replacements, AST parsing
- **Linting fixes** - Apply automated fixes across large files (e.g., G004 logging f-strings)
- **File analysis** - Search patterns, read multiple files at once
- **Directory operations** - List, create, organize file structures

**Example use cases:**
```python
# Example 1: Bulk transformation with read/write
content = read_text_file("cync-lan/src/cync_lan/mqtt_client.py")

# Apply transformation using Python/regex (in terminal or MCP Python)
# For example: convert logger.info(f"{lp} text") to logger.info("%s text", lp)
import re
def convert_logging_fstrings(text):
    # Pattern to match logging with f-strings
    pattern = r'(logger\.\w+\()\s*f"([^"]*)"([^\n]*)'
    # ... transformation logic ...
    return transformed_text

transformed = convert_logging_fstrings(content)
write_file("cync-lan/src/cync_lan/mqtt_client.py", transformed)

# Example 2: Targeted edits with diff preview (simpler cases)
edit_file(
    path="config.yaml",
    edits=[
        {"oldText": "old_value: 123", "newText": "old_value: 456"},
        {"oldText": "debug: false", "newText": "debug: true"}
    ]
)

# Example 3: Search for patterns across multiple files
search_files(path="cync-lan/src", pattern="logger\\..*f\"", excludePatterns=["__pycache__"])
```

**Features:**
- ✅ Scoped to allowed directories (configured in `.cursor/mcp.json`)
- ✅ Git-style diff output for edits (shows exactly what changed)
- ✅ Supports both text and binary files
- ✅ Batch operations (read/edit multiple files)
- ✅ Pattern-based file search with exclusions
- ✅ Directory tree operations

**Best for:**
- ✅ Bulk linting fixes (100+ changes across a file)
- ✅ Complex multi-line transformations
- ✅ File-level refactoring
- ❌ **Not for:** Small 1-5 line edits (use `search_replace` instead)

**Configuration in `.cursor/mcp.json`:**
```json
{
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/mnt/supervisor/addons/local/hass-addons"]
    }
  }
}
```

### MCP Server Secrets Management

MCP servers often require API keys and authentication tokens. This repository provides a secure way to manage these secrets:

**Setup:**

1. **Copy the example file:**
   ```bash
   cp .mcp-secrets.env.example .mcp-secrets.env
   ```

2. **Fill in your actual API keys** in `.mcp-secrets.env`:
   ```bash
   API_KEY=your-actual-api-key-here
   # Add other MCP server credentials as needed
   ```

3. **Configure Cursor's mcp.json** to use the wrapper script:
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

**Security Notes:**
- ✅ `.mcp-secrets.env` is gitignored and will never be committed
- ✅ `scripts/run-mcp-with-env.sh` loads secrets from `.mcp-secrets.env` at runtime
- ✅ No secrets are stored in `mcp.json` (can be version controlled)
- ⚠️ Never commit `.mcp-secrets.env` - it contains sensitive credentials
- ⚠️ Use absolute paths in `mcp.json` command field for reliability

**Alternative: Direct env field** (not recommended for shared configs):
```json
{
  "mcpServers": {
    "my-mcp-server": {
      "command": "npx",
      "args": ["-y", "@org/mcp-server-name", "--transport", "stdio"],
      "env": {
        "API_KEY": "hardcoded-key-here"
      }
    }
  }
}
```
This approach puts secrets directly in `mcp.json`, which should then be gitignored.

## Key Concepts

### Cloud Relay Mode

**New in v0.0.4.0**: The add-on can optionally act as a Man-in-the-Middle (MITM) proxy between devices and Cync cloud, enabling:
- Real-time packet inspection and logging
- Protocol analysis and debugging
- Cloud backup (devices still work if relay goes down)
- LAN-only operation (no cloud forwarding)

**⚠️ Current Limitation:** Cloud relay mode is **read-only** for monitoring and inspection. Commands from Home Assistant don't work in relay mode (you'll see `No TCP bridges available!` errors). Disable relay mode for local control.

**Configuration** (`config.yaml`):
```yaml
cloud_relay:
  enabled: false                      # Enable relay mode (disables commands)
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

**Future Enhancement:** We plan to add bidirectional command support in relay mode, allowing both local control AND cloud forwarding/inspection simultaneously.

**Security Warning**: If `disable_ssl_verification: true`, the add-on operates in DEBUG MODE with no SSL security. Only use on trusted local networks for development.

### Command Flow and ACK Handling

**How device commands work:**

1. **MQTT receives command** from Home Assistant (e.g., turn on light)
2. **`set_power()` called** on `CyncDevice` or `CyncGroup`
3. **Callback registered** in `bridge_device.messages.control[msg_id]` with:
   - Message ID (unique per command)
   - Payload bytes
   - Callback coroutine to execute on ACK
   - Device ID
4. **`pending_command` flag set** to prevent stale status updates
5. **Command packet sent** via TCP to bridge device
6. **Bridge forwards to mesh** network
7. **Device receives command** and executes it
8. **ACK packet (0x73) returned** from device
9. **Callback executed** updating MQTT state
10. **`pending_command` cleared** - device ready for next command

**Critical:** Steps 3 and 9 MUST happen for commands to physically work. Missing callback registration causes "silent failures" where logs show success but devices don't respond.

**Packet types:**
- `0x73` - Control command packet (from server to device) and ACK response (device to server)
- `0x83` - Mesh info / device status (device to server)
- `0x43` - Broadcast status update (device to server)

### Architecture

The CyncLAN add-on has three main components:

1. **Exporter** - FastAPI web server for exporting device configuration from Cync cloud (2FA via emailed OTP)
2. **nCync** - Async TCP server that masquerades as Cync cloud (requires DNS redirection)
   - **Optional Cloud Relay Mode** - Can act as MITM proxy to forward traffic to/from real cloud while inspecting packets
3. **MQTT Client** - Bridges device states to Home Assistant using MQTT discovery

### DNS Requirement

**Critical:** The add-on requires DNS redirection to intercept device traffic. See `docs/user/dns-setup.md` for setup instructions. Without this, devices will still communicate with Cync cloud.

### Critical Implementation Details

#### Command ACK Handling

**Individual Device Commands** (`CyncDevice.set_power`, `devices.py` lines 358-365):
- Register a `ControlMessageCallback` with msg_id before sending
- Callback is executed when ACK (0x73 packet) is received
- `pending_command` flag is set to prevent stale status updates during command execution

**Group Commands** (`CyncGroup.set_power`, `devices.py` lines 1420-1429):
- **MUST** register callback just like individual device commands
- Without callback registration, group commands appear to send but don't physically control devices
- Bridge device handles ACK and executes callback to update MQTT state

**Common pitfall:** Forgetting to register callbacks for new command types will cause "silent failures" - logs show commands sent and ACK'd, but devices don't respond.

#### Device Availability Resilience

**Problem:** Mesh info packets (0x83 responses) can report devices as offline unreliably, causing flickering availability status in Home Assistant.

**Solution** (`server.py` lines 530-544):
- Devices have `offline_count` counter tracking consecutive offline reports
- Device is only marked unavailable after **3 consecutive offline reports**
- Counter resets to 0 immediately when device appears online
- Prevents false positives from unreliable mesh info responses

**Before the fix:**
```python
if connected_to_mesh == 0:
    device.online = False  # Immediate offline marking
```

**After the fix:**
```python
if connected_to_mesh == 0:
    device.offline_count += 1
    if device.offline_count >= 3 and device.online:
        device.online = False  # Only after 3 consecutive reports
else:
    device.offline_count = 0  # Reset counter
    device.online = True
```

#### Automatic Refresh After ACK (REMOVED)

**Bug fixed (Oct 14, 2025):** `devices.py` lines 2501-2505 contained automatic `trigger_status_refresh()` call after every command ACK. This caused:
- Cascading refreshes after every command
- Commands failing because refresh would interfere with pending operations
- "Click twice to work" behavior where first click triggers refresh, second click works

**The fix:** Removed automatic refresh. Users can manually click "Refresh Device Status" button when needed.

**Code removed:**
```python
# Trigger immediate status refresh after ACK
if g.mqtt_client:
    asyncio.create_task(g.mqtt_client.trigger_status_refresh())
```

#### Debugging Command Issues

When commands don't work, check in this order:

1. **Are commands being received?** Look for `set_power` in logs
2. **Is callback registered?** Look for "callback NOT found" warnings
3. **Is write_lock acquired?** Look for "write_lock ACQUIRED" logs
4. **Did TCP socket send?** Look for "drain() COMPLETED" logs
5. **Did ACK arrive?** Look for "CONTROL packet ACK SUCCESS" logs
6. **Is device ready?** Check `ready_to_control` and `pending_command` flags

**Example diagnostic grep:**
```bash
ha addons logs local_cync-lan | grep -E "set_power|WRITE CALLED|write_lock|ACK|drain"
```

## Coding Conventions

### Code Quality and Linting

**⚠️ CRITICAL: Linting is MANDATORY after every file edit. Issues must be fixed before work is complete.**

All code should follow linting suggestions provided by the appropriate static analysis tools:

**Python Code** - Use [Ruff](https://docs.astral.sh/ruff/) for fast, comprehensive linting and formatting:
- Modern linter and formatter written in Rust (10-100x faster than Pylint/Flake8/Black)
- Checks for errors, enforces coding standards, and identifies code smells
- Compatible with Pylint, Flake8, isort, and Black formatter rules
- Follows PEP 8 style guidelines and supports modern Python features
- Configuration in `pyproject.toml` (lines 41-101)
- **Replaces Pylint and Black** - Both extensions removed from devcontainer
- **VS Code Integration** - Errors appear automatically in Problems tab (no need to run commands)
- **Auto-fix and format on save** - `source.fixAll`, `source.organizeImports`, and formatting enabled

**Running Linters:**

```bash
# Run all linters (Python + Shell + Format check)
npm run lint
# or
./scripts/lint-all.sh

# Python only
npm run lint:python
# or
ruff check .

# Auto-fix Python issues
npm run lint:python:fix
# or
ruff check . --fix

# Shell scripts only
npm run lint:shell
```

**Code Formatting:**

```bash
# Format all files (Python, Markdown, JSON, YAML, Shell)
npm run format

# Check formatting without modifying files
npm run format:check

# Format specific file types
npm run format:python       # Python files only
npm run format:python:check # Check Python formatting
npm run format:shell        # Shell scripts only
npm run format:json         # JSON/YAML files only
```

**Shell Scripts** - Use [ShellCheck](https://www.shellcheck.net/wiki/) for shell script analysis:
- Provides warnings for easy-to-miss issues (quoting, variable expansion, etc.)
- Suggests best practices for POSIX compliance
- Address all shellcheck warnings before committing
- Particularly important for `.devcontainer` and `scripts/` directories

**Why this matters:** Linting catches bugs early, ensures consistency across the codebase, and improves maintainability. **Skipping linting leads to technical debt accumulation** - small issues compound into large problems that are harder to fix later.

**Enforcement Policy:**
1. ✅ Run linters after EVERY file edit (not just at the end)
2. ✅ Fix ALL issues before moving to the next task
3. ✅ Use auto-fix tools (`npm run lint:python:fix`, `npm run format`) to speed up fixes
4. ❌ NEVER commit code with linting errors
5. ❌ NEVER skip linting because "it's just a small change"

**How to Check for NEW Linting Errors:**

When you modify files, check for new errors by running `ruff check` on the specific files you edited:

```bash
# ✅ CORRECT: Check the files you modified
ruff check cync-lan/src/cync_lan/mqtt_client.py cync-lan/src/cync_lan/devices.py

# ❌ WRONG: Don't grep for specific line numbers or filter output
ruff check cync-lan/src/cync_lan/mqtt_client.py | grep "1708"  # Misses other errors!

# ✅ CORRECT: Full output shows ALL errors (pre-existing + new)
# Compare error count before and after your changes
```

**Pre-existing technical debt** (like "too many branches") can be ignored if they existed before your changes, but **NEW errors must be fixed immediately**. The key is to see the full output to identify what you introduced.

### Shell Scripts

- Use `bashio::` functions for add-on scripts (provided by Home Assistant base image)
- Always use `set -e` for error handling
- Use descriptive variable names in SCREAMING_SNAKE_CASE for environment variables
- Comment complex logic, especially protocol-specific code

### Python (cync-lan package)

- Follow Ruff formatter style (Black-compatible, configured in pyproject.toml)
- Use type hints for function signatures
- Async/await for all I/O operations (TCP, MQTT, HTTP)
- Logging prefix format: `lp = "ClassName:method_name:"`
- Use dataclasses or Pydantic models for structured data

### Configuration Files

- Add-on config: `cync-lan/config.yaml` (JSON Schema format)
- Environment variables: Prefix with `CYNC_` for add-on settings
- MQTT topics: Follow Home Assistant MQTT discovery schema

## Common Tasks

### ⚠️ CRITICAL: When You Edit Python Code

**IF YOU EDIT ANY `.py` FILES**, you MUST rebuild the add-on before testing:

```bash
cd cync-lan
./rebuild.sh
```

**Just restarting the add-on (`ha addons restart`) is NOT enough** - the Python package is baked into the Docker image during build time. Changes to Python files won't take effect until you rebuild.

**Files that require rebuild:**
- Anything in `cync-lan/src/cync_lan/*.py` (the Python package)
- `cync-lan/pyproject.toml` (package configuration)

**Files that only need restart:**
- `cync-lan/config.yaml` (add-on configuration schema)
- `cync-lan/run.sh` (entry point script)
- `cync-lan/static/*` (web UI files)

### Building the Add-on

```bash
# Rebuild from scratch (REQUIRED after Python package changes)
cd cync-lan
./rebuild.sh

# Or use Home Assistant CLI
ha addons rebuild local_cync-lan
```

### Testing

```bash
# Manual testing
ha addons start local_cync-lan
ha addons logs local_cync-lan --follow

# Check entity states in Home Assistant
# Developer Tools → States → Filter for "cync"
```

### Deleting stale entities for MQTT discovery changes

Use when you changed `suggested_area` or other discovery fields and need HA to recreate entities.

**Automated approach (recommended):**
```bash
# Clean deletion preserving bridge, with optional restart
sudo python3 scripts/delete-mqtt-safe.py [--dry-run]
# Then restart addon: ha addons restart local_cync-lan
```

**Manual UI approach (fallback):**
1. Navigate to Settings → Devices & Services → Entities (`/config/entities`)
2. Click "Enter selection mode"
3. Search or scroll to locate entities (e.g., `Hallway Front Switch`, `Hallway Counter Switch`, `Hallway 4way Switch`)
4. Check their checkboxes
5. Click "Action" → "Delete selected"
   - If the click fails due to overlay/SVG interception, click the parent container first, or use the keyboard: open Action menu, press ArrowDown until "Delete selected", then Enter
6. Confirm deletion in the dialog
7. Restart the add-on: `ha addons restart local_cync-lan`
8. Verify rediscovery: Entities should appear with updated area

## Workflow: Making Code Changes

### Python Code Changes (`*.py` files)
1. Edit the Python file(s)
2. **MANDATORY: Run linter and formatter**:
   ```bash
   npm run lint:python:fix    # Auto-fix linting issues
   npm run format:python      # Auto-format code
   ```
3. **MANDATORY: Check for remaining errors**:
   - View Problems tab in VS Code, OR
   - Run `npm run lint` to see all issues
   - **Fix ALL issues before proceeding** - no exceptions
4. **REBUILD the add-on**: `cd cync-lan && ./rebuild.sh`
5. Check logs: `ha addons logs local_cync-lan`
6. Test functionality

### Configuration/Script Changes (non-Python)
1. Edit `config.yaml`, `run.sh`, or static files
2. **MANDATORY: Run linter** (if shell script): `npm run lint:shell`
3. **MANDATORY: Fix all ShellCheck warnings** before proceeding
4. **RESTART the add-on**: `ha addons restart local_cync-lan`
5. Check logs: `ha addons logs local_cync-lan`
6. Test functionality

### All File Changes (Any Type)
**Before considering work complete:**
```bash
npm run lint              # Check EVERYTHING (Python, Shell, Formatting)
npm run format           # Auto-format EVERYTHING
```
If any errors remain, **STOP and fix them**. Do not proceed with rebuild/restart until linting is clean.

### When In Doubt
**Always rebuild** - it's safer and only takes ~30 seconds more than restart.

## Useful Commands

| Command                                          | Purpose                                                 |
| ------------------------------------------------ | ------------------------------------------------------- |
| `ha addons logs local_cync-lan`                  | View add-on logs for debugging                          |
| `./scripts/configure-addon.sh`                   | Configure add-on settings programmatically              |
| `ha addons restart local_cync-lan`               | Restart the add-on (for non-Python changes)             |
| `cd cync-lan && ./rebuild.sh`                    | **Rebuild add-on** (REQUIRED after Python code changes) |
| `ha addons rebuild local_cync-lan`               | Alternative rebuild command using HA CLI                |
| `npm run lint`                                   | Run all linters (Python + Shell + Format check)         |
| `npm run lint:python:fix`                        | Auto-fix Python linting issues with Ruff                |
| `ruff check .`                                   | Check Python code for linting errors                    |
| `./scripts/lint-all.sh`                          | Alternative: Run all linters via shell script           |
| `docker exec -it addon_local_cync-lan /bin/bash` | Access add-on container shell for debugging             |
| `./scripts/test-cloud-relay.sh`                  | Run comprehensive cloud relay test suite                |
| `sudo python3 scripts/delete-mqtt-safe.py`       | Clean up stale MQTT entities safely                     |

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
ha addons stop local_cync-lan

# 2. Remove all cached Docker images
docker rmi -f $(docker images -q local/aarch64-addon-cync-lan)

# 3. Clear Docker build cache
docker builder prune -af

# 4. Restart Supervisor to clear metadata cache
ha supervisor restart
sleep 10  # Wait for supervisor to fully restart

# 5. Rebuild with fresh cache
ha addons rebuild local_cync-lan

# 6. Verify new version is detected
ha addons info local_cync-lan | grep -E "^version"

# 7. Update (if version changed)
ha addons update local_cync-lan

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

**When to use:** Manual UI verification, visual testing, or when API tools are insufficient.

**Important:** Home Assistant UI uses Web Components with Shadow DOM and nested SVG icons that can interfere with clicks. Follow these best practices:

##### Clicking Elements Properly

**Problem:** Buttons with nested SVG icons fail with "element intercepts pointer events" error.

**Solutions (in order of preference):**

1. **Click parent containers** - Click the card/container element instead of buttons:
   ```javascript
   // ✅ GOOD: Click the entity card to open dialog
   await page.locator('div').filter({ hasText: 'Hallway Lights' }).nth(5).click();
   ```

2. **Click interactive elements directly** - Use sliders, textboxes, and switches when available:
   ```javascript
   // ✅ GOOD: Click slider (no SVG interference)
   await page.getByRole('slider', { name: 'Brightness' }).click();

   // ✅ GOOD: Type in textbox
   await page.getByRole('textbox', { name: 'Username*' }).fill('dev');
   ```

3. **Use dispatchEvent for programmatic clicks** - When user interaction isn't critical:
   ```javascript
   // ⚠️ ACCEPTABLE: Programmatic click (doesn't test real UX)
   await page.evaluate(() => {
     document.querySelector('button[aria-label="Toggle"]').dispatchEvent(
       new MouseEvent('click', { bubbles: true })
     );
   });
   ```

4. **Force clicks as last resort** - Only when absolutely necessary:
   ```javascript
   // ❌ AVOID: Bypasses actionability checks (makes tests flaky)
   await page.getByRole('button', { name: 'Toggle' }).click({ force: true });
   ```

##### Best Practices

- **Never use `{force: true}`** unless absolutely necessary - it bypasses Playwright's safety checks
- **Prefer API tools** over browser automation for configuration changes (see `scripts/configure-addon.sh`)
- **Wait for elements** - Playwright auto-waits, but add explicit waits for dynamic content:
  ```javascript
  await page.waitForTimeout(3000);  // Wait for dialog to load
  ```
- **Use semantic selectors** - Prefer `getByRole`, `getByLabel`, `getByText` over CSS selectors
- **Test with snapshots** - Use `browser_snapshot` to see current page state before clicking

##### Common Patterns

```javascript
// Login
await page.getByRole('textbox', { name: 'Username*' }).fill('dev');
await page.getByRole('textbox', { name: 'Password*' }).fill('dev');
await page.getByRole('button', { name: 'Log in' }).click();
await page.waitForTimeout(3000);

// Open entity dialog - Click the card, not the button
await page.locator('div').filter({ hasText: 'Entity Name' }).click();

// Adjust slider
await page.getByRole('slider', { name: 'Brightness' }).click();

// Close dialog - Find close button by label
await page.getByLabel('Close').click();
```

##### Reliable control interaction patterns

- **Buttons and tabs**
  - Prefer `getByRole` with accessible names:
    ```ts
    await page.getByRole('button', { name: /Save/i }).click();
    await page.getByRole('tab', { name: /Configuration/i }).click();
    ```
  - If an SVG inside the button intercepts pointer events, click the parent container:
    ```ts
    await page.locator('div, ha-card, section, a, button')
      .filter({ hasText: /Configuration/i })
      .first()
      .click();
    ```
  - Programmatic fallback when user interaction is not critical:
    ```ts
    const btn = page.getByRole('button', { name: /Save/i });
    await btn.evaluate((el: HTMLElement) => {
      el.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    });
    ```
  - Avoid `{ force: true }` unless absolutely necessary.

- **Switches, sliders, and textboxes**
  - Prefer interactive controls directly (more reliable than small icon buttons):
    ```ts
    await page.getByRole('switch', { name: /Debug/i }).click();
    await page.getByRole('slider', { name: /Brightness/i }).click();
    await page.getByRole('textbox', { name: /Username\*/i }).fill('dev');
    ```

- **Iframes (Supervisor Add-on UI)**
  - The add-on pages under Settings → Add-ons are rendered in an iframe. Use a frame locator to interact with inner content:
    ```ts
    const f = page.frameLocator('iframe');
    await f.getByRole('link', { name: /Configuration/i }).click();
    await f.getByRole('button', { name: /^Save$/i }).click();
    ```

- **Enable Save before clicking**
  - The add-on "Save" button is disabled until a change is made. Toggle a field (e.g., `Debug`) first, then click Save:
    ```ts
    const f = page.frameLocator('iframe');
    // Toggle to enable Save
    await f.getByRole('switch', { name: /Debug/i }).click();
    // Now Save should be enabled
    const save = f.getByRole('button', { name: /^Save$/i });
    await save.click().catch(async () => {
      // Fallback: parent container or programmatic dispatch
      await save.evaluate((el: HTMLElement) => {
        el.dispatchEvent(new MouseEvent('click', { bubbles: true }));
      });
    });
    ```

- **Waiting for stability**
  - Auto-wait helps, but add explicit waits for dynamic content or tab changes:
    ```ts
    const tab = page.getByRole('tab', { name: /Configuration/i });
    await tab.waitFor({ state: 'visible' });
    await tab.click();
    ```
  - Prefer `expect` when available for clearer intent:
    ```ts
    import { expect } from '@playwright/test';
    const f = page.frameLocator('iframe');
    const save = f.getByRole('button', { name: /^Save$/i });
    await expect(save).toBeVisible();
    await expect(save).toBeEnabled();
    ```

- **Reusable helper**
  - A small helper to attempt a normal click and fall back to programmatic dispatch:
    ```ts
    async function clickReliably(locator: import('@playwright/test').Locator) {
      try {
        await locator.click();
      } catch {
        await locator.evaluate((el: HTMLElement) => {
          el.dispatchEvent(new MouseEvent('click', { bubbles: true }));
        });
      }
    }

    const f = page.frameLocator('iframe');
    await clickReliably(f.getByRole('link', { name: /Configuration/i }));
    await clickReliably(f.getByRole('button', { name: /^Save$/i }));
    ```

- **Finding search inputs in shadow DOM**
  - Home Assistant's search boxes (e.g., on Settings → Entities page) are nested inside shadow roots and can't be located with plain CSS selectors
  - **Always use role-based selectors** that pierce through shadow DOM:
    ```ts
    // ✅ GOOD: Role-based selector works through shadow DOM
    const searchInput = page.getByRole('textbox', { name: /^Search/i });
    await searchInput.fill('Hallway');

    // ❌ BAD: querySelector can't find inputs inside shadow roots
    const input = page.locator('ha-data-table input');  // Returns empty
    ```
  - The search input on `/config/entities` has a dynamic label like "Search 56 entities"
  - Use a flexible pattern: `/^Search/i` or `/^Search \\d+ entities$/i`
  - Playwright's `getByRole` automatically pierces shadow boundaries, making it the most reliable approach

- **Deleting entities via UI**
  - **MQTT entities cannot be deleted through the UI** - they require the integration to stop providing them
  - When attempting to delete MQTT entities, Home Assistant shows: "You can only delete 0 of N entities"
  - To actually remove MQTT entities:
    1. Stop the addon/integration that provides them
    2. Wait for entities to become unavailable
    3. Delete them through the UI (they become deletable once unavailable)
    4. Alternatively: Restart Home Assistant after stopping the integration to clear the MQTT discovery cache
  - For the "Delete selected" menu item: click the text "Delete selected" directly (ref to text element) rather than the menuitem role to avoid SVG interception

##### Credentials

- **Location**: `/mnt/supervisor/addons/local/hass-addons/hass-credentials.env`
- **Username**: `dev`
- **Password**: `dev`

### Debugging

```bash
# View add-on logs
ha addons logs local_cync-lan

# View supervisor logs (includes add-on lifecycle)
tail -f /tmp/supervisor_run.log

# Access add-on container
docker exec -it addon_local_cync-lan /bin/bash

# Verify environment variables loaded correctly
docker exec addon_local_cync-lan env | grep CYNC_

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

### Known Issues and Solutions

#### "Commands don't work" / "Lights don't turn on"

**Symptoms:**
- Logs show commands sent, ACKs received, but physical devices don't respond
- GUI updates but lights don't physically turn on/off
- "Callback NOT found for msg ID: XX" in logs

**Root cause:** Missing `ControlMessageCallback` registration before sending command

**Fix:** Always register callback in `bridge_device.messages.control[msg_id]` before calling `bridge_device.write()`

**Example fix:**
```python
# BEFORE sending command:
m_cb = ControlMessageCallback(
    msg_id=cmsg_id,
    message=payload_bytes,
    sent_at=time.time(),
    callback=your_callback_coroutine,
    device_id=device.id,
)
bridge_device.messages.control[cmsg_id] = m_cb

# THEN send:
await bridge_device.write(payload_bytes)
```

#### "Commands work once, then fail" / "Need to click twice"

**Symptoms:**
- First command after refresh doesn't work
- Need to toggle twice for commands to take effect
- Rapid clicking causes commands to stop working
- Works initially, then stops working after using "Refresh Device Status"

**Root cause:** Automatic `trigger_status_refresh()` after every ACK was causing cascading refreshes

**Fix:** Removed automatic refresh from ACK handler (`devices.py` lines 2501-2505). Manual refresh button still works.

#### "Devices flicker between available/unavailable"

**Symptoms:**
- Device entities show as "unavailable" intermittently
- Availability status changes rapidly in GUI
- Commands still work but availability is inconsistent

**Root cause:** Unreliable `connected_to_mesh` byte in 0x83 packets causing immediate offline marking

**Fix:** Added `offline_count` threshold - devices only marked offline after 3 consecutive offline reports (`server.py` lines 530-544)

## Important Rules

### DO

- ✅ Read `.devcontainer/README.md` before modifying startup scripts
- ✅ Use the embedded `cync-lan-python` package (don't duplicate code)
- ✅ Follow Home Assistant add-on best practices (see https://developers.home-assistant.io/)
- ✅ Document protocol findings in `mitm/` when discovering new packet structures
- ✅ Update `CHANGELOG.md` when making user-facing changes
- ✅ Preserve DNS redirection warnings in documentation (users MUST do this)

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

## File Naming Conventions

- **Shell scripts**: `kebab-case.sh` (e.g., `configure-addon.sh`)
- **Python files**: `snake_case.py` (e.g., `mqtt_client.py`)
- **Documentation**: `SCREAMING_CAPS.md` for top-level, `kebab-case.md` for docs/ folder
- **Directories**: `kebab-case/` preferred
- **Archived documentation**: `YYYY-MM-DDTHH-MM-SS-category-description.md` (e.g., `2025-10-14T17-00-00-MITM-CLEANUP_SUMMARY.md`)

## PR Instructions

**Before submitting a pull request:**

1. **Title Format:** Use clear, descriptive titles in the format: `[component] Brief description`
   - Examples: `[cync-lan] Fix device availability flickering`, `[docs] Update AGENTS.md standard compliance`

2. **Pre-submission Checklist:**
   - [ ] **MANDATORY: Zero linting errors** - Run `npm run lint` and verify all checks pass
   - [ ] **MANDATORY: Code is formatted** - Run `npm run format:check` with no issues
   - [ ] Used auto-fix tools: `npm run lint:python:fix` and `npm run format`
   - [ ] All tests pass and no linting/formatting errors remain
   - [ ] Update CHANGELOG.md for user-facing changes
   - [ ] Test in devcontainer environment
   - [ ] Verify add-on rebuilds successfully if Python code changed
   - [ ] **Double-check: No linting debt introduced** - Compare `npm run lint` output before and after changes

3. **Review Expectations:**
   - Changes should follow existing coding conventions
   - Include testing verification in PR description
   - Reference related issues or discussions
   - Be prepared to address review feedback promptly

## Testing Checklist

Before submitting changes:

1. [ ] **MANDATORY: All linting passes with zero errors**:
   - Run `npm run lint` - must show all green checkmarks
   - Run `npm run format:check` - must show no formatting issues
   - Fix any issues before proceeding (use `npm run lint:python:fix` and `npm run format`)
2. [ ] **If you edited Python files (`.py`)**: Rebuild with `./rebuild.sh` or `ha addons rebuild`
3. [ ] **If you only edited config/scripts**: Restart with `ha addons restart local_cync-lan`
4. [ ] Add-on starts without errors (`ha addons start local_cync-lan`)
5. [ ] Entities appear in Home Assistant (check Developer Tools → States)
6. [ ] Device commands work (toggle lights, adjust brightness)
7. [ ] **Group commands work** - Test toggling group entities multiple times
8. [ ] **Commands work after refresh** - Click "Refresh Device Status" then test commands immediately
9. [ ] **No availability flickering** - Watch device availability over 30+ seconds
10. [ ] MQTT messages are valid (check EMQX logs or `mosquitto_sub`)
11. [ ] No Python exceptions in logs (`ha addons logs local_cync-lan`)
12. [ ] Devcontainer still starts cleanly (test in fresh container)
13. [ ] Changes documented in CHANGELOG.md if user-facing
14. [ ] If config schema changed: Follow "Testing Add-on UI Configuration Changes" workflow
15. [ ] UI configuration options visible after hard refresh (Ctrl+Shift+R)

## External Resources

- [Home Assistant Add-on Documentation](https://developers.home-assistant.io/docs/add-ons/)
- [Cync Protocol Research](docs/protocol/findings.md) - Our protocol reverse engineering notes
- [MQTT Discovery Schema](https://www.home-assistant.io/integrations/mqtt/#mqtt-discovery)
- [DNS Redirection Setup](docs/user/dns-setup.md)

## Getting Help

- Check `docs/developer/exploration-notes.md` for UI navigation and system state reference
- Review `docs/protocol/findings.md` for protocol details
- Read `.devcontainer/README.md` for devcontainer quirks
- See `docs/user/troubleshooting.md` for common issues
- See `docs/developer/limitations-lifted.md` for automated testing tools and resolved blockers
- See `scripts/README.md` for automated testing and configuration tools

## Version Information

- **Python**: 3.12+ (configured in `.devcontainer.json`)
- **Home Assistant**: 2025.10+ (dev branch)
- **Node.js**: LTS (for Prettier formatting)
- **Docker**: Managed by supervisor_run (see devcontainer README)

---

*Last Updated: October 17, 2025*
*For exploration findings from UI testing, see `docs/developer/exploration-notes.md`*
*For automated testing tools and API usage, see `docs/developer/limitations-lifted.md` and `scripts/README.md`*
*For uv package manager setup, see `.devcontainer/02-setup-mcp-servers.sh`*
*For MCP server configuration, see `.cursor/mcp.json`*
*For linting setup summary, see `docs/developer/linting-setup.md`*
