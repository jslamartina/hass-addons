# MCP Development Tools

The devcontainer includes several Model Context Protocol (MCP) servers that provide specialized capabilities for development tasks. MCP servers are managed via `.cursor/mcp.json` and automatically installed by `uvx`/`npx` on first use (no manual installation required).

## Quick Reference

| MCP Server               | Primary Use          | Key Functions                                          | When to Use                                                   |
| ------------------------ | -------------------- | ------------------------------------------------------ | ------------------------------------------------------------- |
| `mcp-server-time`        | Timezone operations  | `get_current_time`, `convert_time`                     | Scheduling, timestamps, DST calculations                      |
| `mcp-python-interpreter` | Code execution       | `run_python_code` (native Python, filesystem access)   | Large file processing, data analysis, prototyping, automation |
| `mcp-server-docker`      | Container management | 15 functions (containers/images/networks/volumes)      | Inspecting containers, managing dev environments              |
| `mcp-server-fetch`       | Web content          | `fetch` (markdown/HTML modes)                          | Reading docs, fetching API specs, release notes               |
| `mcp-server-git`         | Version control      | 12 Git operations                                      | Analyzing history, managing branches, reviewing changes       |
| `mcp-server-filesystem`  | File operations      | `read_file`, `write_file`, `edit_file`, `search_files` | Bulk file edits, transformations, reading/writing files       |

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

