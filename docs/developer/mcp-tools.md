# MCP Development Tools

The devcontainer includes several Model Context Protocol (MCP) servers that provide specialized capabilities for development tasks. MCP servers are managed via `.cursor/mcp.json` and automatically installed by `uvx`/`npx` on first use (no manual installation required).

## Quick Reference

| MCP Server                | Primary Use          | Key Functions                                           | When to Use                                                   |
| ------------------------- | -------------------- | ------------------------------------------------------- | ------------------------------------------------------------- |
| `cursor-playwright`       | Browser automation   | `browser_navigate`, `browser_snapshot`, `browser_click` | UI testing, visual verification, interactive debugging        |
| `mcp-server-time`         | Timezone operations  | `get_current_time`, `convert_time`                      | Scheduling, timestamps, DST calculations                      |
| `mcp-python-interpreter`  | Code execution       | `run_python_code` (native Python, filesystem access)    | Large file processing, data analysis, prototyping, automation |
| `mcp-server-docker`       | Container management | 15 functions (containers/images/networks/volumes)       | Inspecting containers, managing dev environments              |
| `mcp-server-fetch`        | Web content          | `fetch` (markdown/HTML modes)                           | Reading docs, fetching API specs, release notes               |
| `mcp-server-git`          | Version control      | 12 Git operations                                       | Analyzing history, managing branches, reviewing changes       |
| `mcp-server-filesystem`   | File operations      | `read_file`, `write_file`, `edit_file`, `search_files`  | Bulk file edits, transformations, reading/writing files       |
| `sequential-thinking-mcp` | Thought logging      | `think` (threaded steps, tool recs, planning)           | Track reasoning steps, plan actions, log progress             |

**Installation:** Automatic via `uvx`/`npx` on first use. The `uv` package manager is installed during devcontainer creation via `.devcontainer/02-setup-mcp-servers.sh`, then `uvx` automatically downloads and caches MCP servers when Cursor first connects to them (configured in `.cursor/mcp.json`).

## Tool Limitations & Error Handling

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
    logs = mcp_docker_fetch_container_logs("addon_local_cync-controller", tail=100)
except:
    # Fallback: Standard terminal command
    logs = run_terminal_cmd("docker logs addon_local_cync-controller --tail 100")
```

---

## Detailed Tool Documentation

### Browser Automation (`cursor-playwright`)

**Built-in Tool:** Cursor provides Playwright browser automation through MCP (no configuration needed).

**Tools Available:**

- `mcp_cursor-playwright_browser_navigate` - Navigate to URLs
- `mcp_cursor-playwright_browser_snapshot` - Capture accessibility tree (best for understanding structure)
- `mcp_cursor-playwright_browser_click` - Click elements
- `mcp_cursor-playwright_browser_type` - Type text into inputs
- `mcp_cursor-playwright_browser_fill_form` - Fill multiple form fields
- `mcp_cursor-playwright_browser_evaluate` - Execute JavaScript
- `mcp_cursor-playwright_browser_take_screenshot` - Capture visual state
- `mcp_cursor-playwright_browser_wait_for` - Wait for content/time
- `mcp_cursor-playwright_browser_console_messages` - Get console logs
- `mcp_cursor-playwright_browser_network_requests` - Get network activity
- `mcp_cursor-playwright_browser_tabs` - Manage browser tabs
- `mcp_cursor-playwright_browser_select_option` - Select dropdown options
- `mcp_cursor-playwright_browser_hover` - Hover over elements
- `mcp_cursor-playwright_browser_drag` - Drag and drop
- `mcp_cursor-playwright_browser_press_key` - Keyboard input
- `mcp_cursor-playwright_browser_handle_dialog` - Handle alerts/dialogs
- `mcp_cursor-playwright_browser_file_upload` - Upload files

**When to use:**

- **Interactive testing** - Explore UI, verify behavior, find bugs
- **Visual verification** - Check if configuration options appear
- **Debugging** - Understand why something doesn't work in the UI
- **Ad-hoc operations** - Quick one-off UI interactions
- **Documentation** - Capture screenshots of UI states

**When NOT to use:**

- ❌ Automated repetitive tasks (use TypeScript scripts instead)
- ❌ Configuration changes (use `scripts/configure-addon.sh` API tool)
- ❌ Bulk operations (use TypeScript scripts in `scripts/playwright/`)
- ❌ CI/CD pipelines (use headless Playwright scripts)

**Example use cases:**

```typescript
// Login to Home Assistant
await mcp_cursor-playwright_browser_navigate({ url: "http://localhost:8123" });
await mcp_cursor-playwright_browser_fill_form({
  fields: [
    { name: "Username", type: "textbox", ref: "input[name='username']", value: "dev" },
    { name: "Password", type: "textbox", ref: "input[name='password']", value: "dev" }
  ]
});
await mcp_cursor-playwright_browser_click({ element: "Log in", ref: "button[type='submit']" });

// Verify configuration option appears
await mcp_cursor-playwright_browser_navigate({
  url: "http://localhost:8123/hassio/addon/local_cync-controller"
});
await mcp_cursor-playwright_browser_click({
  element: "Configuration tab",
  ref: "iframe >> a[role='tab']:has-text('Configuration')"
});
await mcp_cursor-playwright_browser_snapshot(); // See structure

// Debug UI issue with screenshots
await mcp_cursor-playwright_browser_take_screenshot({ filename: "before-click.png" });
await mcp_cursor-playwright_browser_click({ element: "Button", ref: "button.problem" });
await mcp_cursor-playwright_browser_take_screenshot({ filename: "after-click.png" });
await mcp_cursor-playwright_browser_console_messages(); // Check for errors
```

**Features:**

- ✅ **Headless by default** - Fast, non-intrusive testing
- ✅ **Shadow DOM support** - Role-based selectors pierce shadow boundaries
- ✅ **Screenshot/snapshot** - Visual and structural verification
- ✅ **Console/network access** - Debug JavaScript and API issues
- ✅ **Permission-based** - Safe automation with user awareness
- ✅ **Iframe support** - Access add-on pages with `iframe >>` prefix

**Key Gotchas:**

⚠️ **Home Assistant UI uses Shadow DOM** - Standard CSS selectors don't work. Use `browser_snapshot()` first to see accessibility tree, then use role-based or text selectors.

⚠️ **Add-on pages are in iframes** - Use `iframe >>` prefix for selectors:
```typescript
ref: "iframe >> button:has-text('Save')"
```

⚠️ **SVG icons intercept clicks** - Click parent containers instead of buttons with SVG icons.

⚠️ **Dynamic content loads** - Wait for elements before interacting:
```typescript
await mcp_cursor-playwright_browser_wait_for({ text: "Configuration", time: 5 });
```

**Full Documentation:**

See **[AI Browser Testing Plan](ai-browser-testing-plan.md)** for comprehensive guide including:
- All tool parameters and usage
- Home Assistant UI patterns and quirks
- Debugging workflows
- Templates and examples
- Integration with TypeScript scripts

Also see **[Browser Automation Guide](browser-automation.md)** for Playwright-specific patterns.

### Time Operations (`mcp-server-time`)

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

### Python Code Execution (`mcp-python-interpreter`)

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

file = Path("cync-controller/src/cync_lan/mqtt_client.py")
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

### Docker Management (`mcp-server-docker`)

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
fetch_container_logs("addon_local_cync-controller", tail=100)

# Manage test networks for multi-container testing
create_network("cync-test-net", driver="bridge")
```

### Web Content Fetching (`mcp-server-fetch`)

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

### Git Operations (`mcp-server-git`)

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

### Sequential Thinking (`sequential-thinking-mcp`)

**Purpose:** Track multi-step reasoning with explicit branching, progress tracking, and completion status.

**Tools Available:**

- `mcp_sequential-thinking_sequentialthinking` - Log a reasoning step with optional branching, tool recommendations, and status tracking

**When to use:**

- ✅ Multi-step debugging with parallel hypotheses
- ✅ Complex decision trees with branching and reconvergence
- ✅ Tracking progress across long tasks
- ✅ Enforcing disciplined reasoning with explicit next actions
- ✅ Planning investigations with multiple exploration paths

**When NOT to use:**

- ❌ Simple linear tasks (1-2 steps)
- ❌ Tasks not requiring branching logic
- ❌ When you don't need progress tracking

**Parameters:**

```python
thought: str                  # Current reasoning step (required)
nextThoughtNeeded: bool       # Whether more thinking needed (required)
thoughtNumber: int            # Current thought index in thread (required)
totalThoughts: int            # Estimated total thoughts needed (required)

# Optional branching parameters:
branchFromThought: int        # Parent thought number to branch from
branchId: str                 # Unique identifier for this branch
isRevision: bool              # If revising a previous thought
revisesThought: int           # Which thought number is being reconsidered
```

**Response Structure:**

```json
{
  "thoughtNumber": 1,
  "totalThoughts": 5,
  "nextThoughtNeeded": true,
  "branches": ["branch_id_1", "branch_id_2"],
  "thoughtHistoryLength": 3
}
```

**Example 1: Simple Linear Reasoning**

```python
# Step 1: Problem analysis
think(
  thought="User reports MQTT entities disappearing after restart. Could be discovery timing issue, retained messages, or registration bug.",
  nextThoughtNeeded=True,
  thoughtNumber=1,
  totalThoughts=3
)

# Step 2: Check logs
think(
  thought="Verified addon logs show clean restart. MQTT connection established. No errors visible.",
  nextThoughtNeeded=True,
  thoughtNumber=2,
  totalThoughts=3
)

# Step 3: Resolved
think(
  thought="Found issue: publish_all_states() called before devices populated from mesh query. Fixed by reordering startup sequence.",
  nextThoughtNeeded=False,  # Investigation complete
  thoughtNumber=3,
  totalThoughts=3
)
```

**Example 2: Branching Investigation (Multiple Hypotheses)**

```python
# Main investigation
think(
  thought="Error: Could be three causes: (1) Discovery schema issue, (2) Entity registration timing, (3) HA caching",
  nextThoughtNeeded=True,
  thoughtNumber=1,
  totalThoughts=2
)

# Identify need to branch
think(
  thought="Need to test each hypothesis separately. Creating parallel branches.",
  nextThoughtNeeded=True,
  thoughtNumber=2,
  totalThoughts=2
)

# ─── BRANCH 1: Discovery schema ───
think(
  thought="Branch 1: Checking MQTT discovery payload structure",
  nextThoughtNeeded=True,
  thoughtNumber=1,
  totalThoughts=2,
  branchFromThought=2,      # Branches from main thought 2
  branchId="discovery_check"
)

think(
  thought="Discovery payload validates correctly against MQTT schema. Not the issue.",
  nextThoughtNeeded=True,
  thoughtNumber=2,
  totalThoughts=2,
  branchId="discovery_check"
)

# ─── BRANCH 2: Entity registration timing (FOUND ISSUE) ───
think(
  thought="Branch 2: Examining device population on startup",
  nextThoughtNeeded=True,
  thoughtNumber=1,
  totalThoughts=3,
  branchFromThought=2,        # Parallel branch from main thought 2
  branchId="registration_timing"
)

think(
  thought="Found: publish_all_states() executes BEFORE mesh query completes. Devices dict is empty!",
  nextThoughtNeeded=True,
  thoughtNumber=2,
  totalThoughts=3,
  branchId="registration_timing"
)

think(
  thought="Fixed by reordering: mesh query first, then publish_all_states(). Entities now persist after restart.",
  nextThoughtNeeded=True,
  thoughtNumber=3,
  totalThoughts=3,
  branchId="registration_timing"
)
```

**Example 3: Nested Branching (Multi-level Investigation)**

```python
# Main investigation finds issue
think(
  thought="Found timing bug, but need to verify edge cases",
  nextThoughtNeeded=True,
  thoughtNumber=3,
  totalThoughts=3,
  branchId="registration_timing"
)

# ─── SUB-BRANCH: Edge case handling ───
think(
  thought="Sub-branch: What if mesh query times out? Need timeout protection.",
  nextThoughtNeeded=True,
  thoughtNumber=1,
  totalThoughts=2,
  branchFromThought=3,        # Branches from registration_timing thought 3
  branchId="timeout_handling"
)

think(
  thought="Implemented timeout handler with exponential backoff retry. Edge case protected.",
  nextThoughtNeeded=False,    # Complete
  thoughtNumber=2,
  totalThoughts=2,
  branchId="timeout_handling"
)
```

**Understanding the Response:**

| Field | Meaning |
|-------|---------|
| `thoughtNumber` | Current index in this specific branch |
| `totalThoughts` | Estimated total for this branch (can adjust) |
| `nextThoughtNeeded` | `false` = investigation complete, `true` = more thinking needed |
| `branches` | Array of all active branch IDs (shows investigation scope) |
| `thoughtHistoryLength` | Total thoughts logged across all branches |

**Real-world Workflow:**

```
Main Thread: "Investigate Docker build failure" [1-2]
    │
    └─► Thought 2: "Found package issue. Branch to test solutions."
        │
        ├─► Branch 1A: "apt cache refresh" [1-3]
        │   └─ Thought 3: "Not the issue. Reconverge."
        │
        └─► Branch 1B: "base image investigation" [1-3] ← FOUND SOLUTION
            ├─ Thought 1-2: Testing different base images
            └─ Thought 3: Branch to slim variant investigation
                │
                └─► Sub-branch: "slim package differences" [1-3]
                    ├─ Thought 1-2: Identify missing package
                    └─ Thought 3: "RESOLVED - Use full bullseye image" ✓
                        (nextThoughtNeeded=false)
```

**Best Practices:**

✅ **DO:**
- Start with `totalThoughts` estimate, adjust as you go
- Use `branchId` names that describe the investigation path
- Set `nextThoughtNeeded=false` when a branch is complete
- Create sub-branches for edge cases after main issue found
- Keep thoughts focused on reasoning steps, not implementation details

❌ **DON'T:**
- Use branching for simple 2-3 step processes
- Create branches without identifying decision points
- Forget to set `nextThoughtNeeded=false` when complete
- Use vague branch IDs (use descriptive names)

**Configuration in `.cursor/mcp.json`:**

```json
{
  "mcpServers": {
    "sequential-thinking": {
      "command": "uvx",
      "args": ["--refresh", "sequential-thinking-mcp"]
    }
  }
}
```

---

### Filesystem Operations (`mcp-server-filesystem`)

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
content = read_text_file("cync-controller/src/cync_lan/mqtt_client.py")

# Apply transformation using Python/regex (in terminal or MCP Python)
# For example: convert logger.info(f"{lp} text") to logger.info("%s text", lp)
import re
def convert_logging_fstrings(text):
    # Pattern to match logging with f-strings
    pattern = r'(logger\.\w+\()\s*f"([^"]*)"([^\n]*)'
    # ... transformation logic ...
    return transformed_text

transformed = convert_logging_fstrings(content)
write_file("cync-controller/src/cync_lan/mqtt_client.py", transformed)

# Example 2: Targeted edits with diff preview (simpler cases)
edit_file(
    path="config.yaml",
    edits=[
        {"oldText": "old_value: 123", "newText": "old_value: 456"},
        {"oldText": "debug: false", "newText": "debug: true"}
    ]
)

# Example 3: Search for patterns across multiple files
search_files(path="cync-controller/src", pattern="logger\\..*f\"", excludePatterns=["__pycache__"])
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
      "args": [
        "-y",
        "@modelcontextprotocol/server-filesystem",
        "/mnt/supervisor/addons/local/hass-addons"
      ]
    }
  }
}
```

## MCP Server Secrets Management

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

---

_For more information, see [AGENTS.md](../../AGENTS.md) in the repository root._

