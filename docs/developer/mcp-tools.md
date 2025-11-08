# MCP Development Tools

The devcontainer includes Model Context Protocol (MCP) servers for specialized development tasks. MCP servers are configured in `.cursor/mcp.json` and automatically installed by `uvx` when first used (no manual setup required).

## Available Tools

| Tool          | Purpose                 | Key Functions                        | When to Use                                        |
| ------------- | ----------------------- | ------------------------------------ | -------------------------------------------------- |
| **web_fetch** | Web content fetching    | `fetch` (markdown/HTML)              | Documentation, API specs, release notes            |
| **python**    | Native Python execution | `run_python_code`, `run_python_file` | Large file processing, data analysis, code testing |

**Installation:** The `uv` package manager is installed during devcontainer setup (`.devcontainer/02-setup-mcp-servers.sh`). MCP servers are automatically downloaded and cached by `uvx` when Cursor first connects.

## Limitations & Error Handling

### Known Limitations

- **Python**: Full filesystem access. Package installs are temporary per execution.
- **Web Fetch**: Respects robots.txt (some sites may block automated access).

### When MCP tools fail

1. ✅ Use standard tools (grep, read_file, terminal commands)
2. ✅ Note the failure in your response
3. ✅ Continue gracefully - don't let it block the task

### Example fallback

```bash
## Preferred: MCP Python for large files
## If it fails, use built-in tools for smaller edits.
```

---

## Detailed Documentation

### 🐍 Python Code Execution (`mcp-python-interpreter`)

Execute native Python 3.13 code with full filesystem access.

#### Available Functions

- `mcp_python_run_python_code` - Execute Python code in-process
- `mcp_python_run_python_file` - Execute a Python file
- `mcp_python_list_python_environments` - List available Python environments
- `mcp_python_list_installed_packages` - Show installed packages
- `mcp_python_install_package` - Install packages (temporary per execution)

### When to use

- ✅ **Large file processing** - Transform files without loading into context
- ✅ Quick Python calculations and data analysis
- ✅ Testing code snippets before implementation
- ✅ File transformations and validation
- ✅ Prototyping algorithms

### Features

- **Native CPython 3.13** (not WebAssembly)
- **Full filesystem access** - Use `open()`, `Path()`, read/write files directly
- **Standard library** - json, datetime, pathlib, re, etc.
- **Working directory**: `/mnt/supervisor/addons/local/hass-addons`
- **Async support** - Use asyncio and await

### Example: Process Large File

```python
mcp_python_run_python_code("""
from pathlib import Path
import re

## Read and transform without loading into context
file = Path("cync-controller/src/cync_lan/mqtt_client.py")
content = file.read_text()

## Apply transformations
transformed = re.sub(r'old_pattern', 'new_pattern', content)

## Write back
file.write_text(transformed)
print(f"Processed {len(content.split(chr(10)))} lines")
""")
```

### Example: Validate Configuration

```python
mcp_python_run_python_code("""
import json
from pathlib import Path

config = json.loads(Path("cync-controller/config.yaml").read_text())
print("Valid config:", bool(config.get("name")))
""")
```

### Key Advantage

Process multi-megabyte files without tokenizing them into context. Ideal for bulk transformations and file analysis.

### 🌐 Web Content Fetching (`mcp-server-fetch`)

Fetch web pages as simplified markdown or raw HTML.

#### Available Functions

- `mcp_web_fetch_fetch` - Fetch URL content

### When to use web fetch

- ✅ Reading documentation and API specs
- ✅ Retrieving release notes or changelogs
- ✅ Looking up protocol information
- ✅ Researching best practices

### Don't use for

- ❌ Searching the codebase (use `codebase_search`)
- ❌ Reading project files (use `read_file`)

### Web fetch features

- **Markdown mode** - Simplified, readable content (default)
- **Raw HTML mode** - Full HTML for custom parsing
- **Pagination** - Use `start_index` for long pages
- **Length limits** - Control output size with `max_length`
- **Respects robots.txt**

### Example: Fetch Documentation

```python
## Get Home Assistant MQTT integration docs
mcp_web_fetch_fetch(
  url="https://www.home-assistant.io/integrations/mqtt/",
  max_length=5000
)
```

### Example: Continue Long Page

```python
## Read first chunk
mcp_web_fetch_fetch(url="https://long-article.com", max_length=5000)

## Read next chunk
mcp_web_fetch_fetch(url="https://long-article.com", start_index=5000, max_length=5000)
```

## Example: Raw HTML

```python
## Get raw HTML for parsing
mcp_web_fetch_fetch(
  url="https://api-docs.example.com",
  raw=True,
  max_length=10000
)
```

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
    }
  }
}
```
