#!/bin/bash
set -e

echo "🔧 Setting up MCP (Model Context Protocol) servers..."

# Install uv (fast Python package installer, optional but recommended)
pip install uv

# Install npm-based MCP servers
echo "📦 Installing npm-based MCP servers..."
npm install -g @modelcontextprotocol/server-sequential-thinking
npm install -g @modelcontextprotocol/server-filesystem

# Install pip-based MCP servers
echo "🐍 Installing pip-based MCP servers..."
pip install mcp-server-time
pip install mcp-server-docker
pip install mcp-server-fetch
pip install mcp-run-python
pip install mcp-server-git

echo "✅ MCP server setup complete!"
echo "💡 Available MCP servers:"
echo "   - mcp-server-time (pip)"
echo "   - @modelcontextprotocol/server-sequential-thinking (npm)"
echo "   - @modelcontextprotocol/server-filesystem (npm)"
echo "   - mcp-server-docker (pip)"
echo "   - mcp-server-fetch (pip)"
echo "   - mcp-run-python (pip)"
echo "   - mcp-server-git (pip)"
