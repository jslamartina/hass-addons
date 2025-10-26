# MCP Development Tools

The devcontainer includes Model Context Protocol (MCP) servers for specialized development tasks. MCP servers are configured in `.cursor/mcp.json` and automatically installed by `uvx` when first used (no manual setup required).

## Available Tools

| Tool                    | Purpose                 | Key Functions                        | When to Use                                        |
| ----------------------- | ----------------------- | ------------------------------------ | -------------------------------------------------- |
| **web_fetch**           | Web content fetching    | `fetch` (markdown/HTML)              | Documentation, API specs, release notes            |
| **python**              | Native Python execution | `run_python_code`, `run_python_file` | Large file processing, data analysis, code testing |
| **sequential-thinking** | Reasoning tracker       | `think` (branching, progress)        | Multi-step debugging, complex investigations       |

**Installation:** The `uv` package manager is installed during devcontainer setup (`.devcontainer/02-setup-mcp-servers.sh`). MCP servers are automatically downloaded and cached by `uvx` when Cursor first connects.

## Limitations & Error Handling

**Known Limitations:**

- **Python**: Full filesystem access. Package installs are temporary per execution.
- **Web Fetch**: Respects robots.txt (some sites may block automated access).
- **Sequential Thinking**: Primarily for logging/tracking, not execution.

**When MCP tools fail:**

1. ✅ Use standard tools (grep, read_file, terminal commands)
2. ✅ Note the failure in your response
3. ✅ Continue gracefully - don't let it block the task

**Example fallback:**

```bash
# Preferred: MCP Python for large files
# If it fails, use read_file + search_replace for smaller edits
```

---

## Detailed Documentation

### 🐍 Python Code Execution (`mcp-python-interpreter`)

Execute native Python 3.13 code with full filesystem access.

**Available Functions:**

- `mcp_python_run_python_code` - Execute Python code in-process
- `mcp_python_run_python_file` - Execute a Python file
- `mcp_python_list_python_environments` - List available Python environments
- `mcp_python_list_installed_packages` - Show installed packages
- `mcp_python_install_package` - Install packages (temporary per execution)

**When to use:**

- ✅ **Large file processing** - Transform files without loading into context
- ✅ Quick Python calculations and data analysis
- ✅ Testing code snippets before implementation
- ✅ File transformations and validation
- ✅ Prototyping algorithms

**Features:**

- **Native CPython 3.13** (not WebAssembly)
- **Full filesystem access** - Use `open()`, `Path()`, read/write files directly
- **Standard library** - json, datetime, pathlib, re, etc.
- **Working directory**: `/mnt/supervisor/addons/local/hass-addons`
- **Async support** - Use asyncio and await

**Example: Process Large File**

```python
mcp_python_run_python_code("""
from pathlib import Path
import re

# Read and transform without loading into context
file = Path("cync-controller/src/cync_lan/mqtt_client.py")
content = file.read_text()

# Apply transformations
transformed = re.sub(r'old_pattern', 'new_pattern', content)

# Write back
file.write_text(transformed)
print(f"Processed {len(content.split(chr(10)))} lines")
""")
```

**Example: Validate Configuration**

```python
mcp_python_run_python_code("""
import json
from pathlib import Path

config = json.loads(Path("cync-controller/config.yaml").read_text())
print("Valid config:", bool(config.get("name")))
""")
```

**Key Advantage:**

Process multi-megabyte files without tokenizing them into context. Ideal for bulk transformations and file analysis.


### 🌐 Web Content Fetching (`mcp-server-fetch`)

Fetch web pages as simplified markdown or raw HTML.

**Available Functions:**

- `mcp_web_fetch_fetch` - Fetch URL content

**When to use:**

- ✅ Reading documentation and API specs
- ✅ Retrieving release notes or changelogs
- ✅ Looking up protocol information
- ✅ Researching best practices

**Don't use for:**

- ❌ Searching the codebase (use `codebase_search`)
- ❌ Reading project files (use `read_file`)

**Features:**

- **Markdown mode** - Simplified, readable content (default)
- **Raw HTML mode** - Full HTML for custom parsing
- **Pagination** - Use `start_index` for long pages
- **Length limits** - Control output size with `max_length`
- **Respects robots.txt**

**Example: Fetch Documentation**

```python
# Get Home Assistant MQTT integration docs
mcp_web_fetch_fetch(
  url="https://www.home-assistant.io/integrations/mqtt/",
  max_length=5000
)
```

**Example: Continue Long Page**

```python
# Read first chunk
mcp_web_fetch_fetch(url="https://long-article.com", max_length=5000)

# Read next chunk
mcp_web_fetch_fetch(url="https://long-article.com", start_index=5000, max_length=5000)
```

**Example: Raw HTML**

```python
# Get raw HTML for parsing
mcp_web_fetch_fetch(
  url="https://api-docs.example.com",
  raw=True,
  max_length=10000
)
```


### 🧠 Sequential Thinking (`sequential-thinking-mcp`)

Track multi-step reasoning with branching, progress tracking, and completion status.

**Available Functions:**

- `mcp_sequential-thinking_think` - Log reasoning step with branching support

**When to use:**

- ✅ Multi-step debugging with parallel hypotheses
- ✅ Complex investigations requiring explicit planning
- ✅ Tracking progress across long tasks

**When NOT to use:**

- ❌ Simple linear tasks (1-2 steps)
- ❌ When branching logic isn't needed

**Parameters:**

```python
thread_purpose: str          # High-level objective/identifier
thought: str                 # Current reasoning step
thought_index: int           # Sequence number in thread
tool_recommendation: str     # Next tool to use (optional)
left_to_be_done: str         # Remaining steps (optional)
```

**Example: Simple Investigation**

```python
mcp_sequential-thinking_think(
  thread_purpose="MQTT entity disappearance",
  thought="Logs show clean restart. MQTT connected. Checking publish timing vs mesh query.",
  thought_index=2,
  tool_recommendation="grep",
  left_to_be_done="Search for publish_all_states call order"
)
```

**Example: Parallel Hypotheses**

```python
# Investigation identifies multiple potential causes
mcp_sequential-thinking_think(
  thread_purpose="Command ACK timeout",
  thought="Three possibilities: (1) Network latency, (2) Device offline, (3) Callback registration missing",
  thought_index=1,
  left_to_be_done="Test each hypothesis in parallel"
)
```

**Best Practices:**

✅ **DO:**
- Use descriptive `thread_purpose` names
- Include `tool_recommendation` for next action
- Update `left_to_be_done` with remaining work
- Keep thoughts focused on reasoning, not implementation

❌ **DON'T:**
- Use for simple 1-2 step tasks
- Create entries without clear next actions
- Mix multiple investigations in one thread

## Configuration

MCP servers are configured in `.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "web_fetch": {
      "command": "uv",
      "args": ["run", "--with", "mcp-server-fetch", "mcp-server-fetch"]
    },
    "python": {
      "command": "uv",
      "args": [
        "run",
        "--with",
        "mcp-python-interpreter",
        "mcp-python-interpreter",
        "--dir",
        "/mnt/supervisor/addons/local/hass-addons",
        "--python-path",
        "/usr/local/bin/python3"
      ]
    },
    "sequential-thinking": {
      "command": "uv",
      "args": [
        "run",
        "--with",
        "sequential-thinking-mcp",
        "sequential-thinking-mcp"
      ]
    }
  }
}
```

**Installation:** The `uv` package manager is installed during devcontainer setup via `.devcontainer/02-setup-mcp-servers.sh`. MCP servers are automatically downloaded and cached when Cursor first connects.

---

_For more information, see [AGENTS.md](../../AGENTS.md) in the repository root._

