# Developer Guide

> **Note:** This project is forked from [@baudneo/hass-addons](https://github.com/baudneo/hass-addons)

> **This file is for developers working on the add-on code, not for end users.**

## Source Code Location

All Python source code for the Cync Controller add-on is located in this directory:
- `src/cync_lan/` - Python package source code
- `pyproject.toml` - Package configuration and dependencies

## 🆕 Enhanced Development Features (v0.0.4.4)

### Cloud Relay Mode (WIP)
New MITM proxy functionality for packet inspection and debugging:
- **Transparent proxy** between devices and cloud
- **Packet inspection** and real-time logging
- **Multiple operating modes** for different use cases
- **File-based packet injection** for testing

### MCP Integration
Advanced AI agent development tools:
- **6 specialized MCP servers** for enhanced capabilities
- **Docker management** for container inspection
- **Python code execution** with filesystem access
- **Git operations** for repository analysis
- **Filesystem operations** for bulk file transformations

### Ruff Linting
**10-100x faster** Python linting and formatting:
- **Replaced Pylint** with Ruff (Rust-based)
- **Auto-fix on save** in VS Code/Cursor
- **Comprehensive rule set** (E, W, F, I, N, UP, B, C4, etc.)
- **Shell script linting** with ShellCheck

## Development Workflow

### Basic Workflow
1. Edit code in `src/cync_lan/` or `pyproject.toml`
2. **Run `./rebuild.sh` to rebuild and restart the add-on**
3. Check logs: `ha addons logs local_cync-controller`
4. Test functionality in Home Assistant

### Enhanced Workflow (v0.0.4.4)
1. Edit code in `src/cync_lan/` or `pyproject.toml`
2. **Run linting**: `npm run lint:python:fix` (auto-fixes issues)
3. **Run formatting**: `npm run format:python` (formats code)
4. **Rebuild**: `ha addons rebuild local_cync-controller`
5. **Test**: Use automated scripts for configuration and validation

### Testing Workflow
```bash
# Programmatic configuration
./scripts/configure-addon.sh preset-relay-debug

# Comprehensive testing
./scripts/test-cloud-relay.sh

# Check logs
ha addons logs local_cync-controller --follow | grep -i "relay\|cloud"
```

## Important Notes

- **Always rebuild after Python changes**: The Docker image must be rebuilt for code changes to take effect
- **Restart is not enough**: `ha addons restart` will not pick up Python code changes
- **Use `./rebuild.sh`** which handles rebuild + restart automatically
- **Enhanced linting**: Run `npm run lint` to check all code quality standards
- **MCP tools**: Available via Cursor IDE for enhanced development capabilities

## Development Tools

### Quick Commands
```bash
# Lint and format all code
npm run lint && npm run format

# Configure add-on programmatically
./scripts/configure-addon.sh preset-relay-with-forward

# Test cloud relay functionality
./scripts/test-cloud-relay.sh

# View add-on logs
ha addons logs local_cync-controller --follow

# Rebuild after Python changes
ha addons rebuild local_cync-controller
```

### MCP Servers Available
- **mcp-server-time** - Timezone operations and scheduling
- **mcp-python-interpreter** - Native Python code execution
- **mcp-server-docker** - Container management and inspection
- **mcp-server-fetch** - Web content fetching and processing
- **mcp-server-git** - Git operations and repository analysis
- **mcp-server-filesystem** - Advanced file operations and transformations
- **sequential-thinking-mcp** - Log step-wise reasoning, status updates, and next actions

**[📖 Complete Developer Guide →](../AGENTS.md)**
