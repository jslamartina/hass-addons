# Cursor Rules Guide

This project uses Cursor Rules to provide AI agents (and human developers) with consistent guidance on code organization, standards, and workflows.

## Available Rules

All rules are stored in `.cursor/rules/` with the `.mdc` extension.

### 🚀 Start Here

- **[quick-start.mdc](.cursor/rules/quick-start.mdc)** - Overview for new contributors
  - Most common commands
  - Development workflow
  - Rules to remember

### 🔧 Development Guidelines

- **[python-changes-require-rebuild.mdc](.cursor/rules/python-changes-require-rebuild.mdc)** - Python workflow
  - When Python files change, you MUST rebuild
  - Linting requirements
  - Verification steps

- **[shell-scripting.mdc](.cursor/rules/shell-scripting.mdc)** - Shell script standards
  - Idempotency requirements
  - Error handling patterns
  - Logging conventions
  - Supervisor API access

- **[linting-mandatory.mdc](.cursor/rules/linting-mandatory.mdc)** - Code quality
  - Linting is required before any commit
  - Standard commands
  - What gets checked

### 🏗️ Architecture & Implementation

- **[token-creation-flow.mdc](.cursor/rules/token-creation-flow.mdc)** - LLAT system
  - Three-phase token creation
  - Onboarding bootstrap
  - Key files and workflows

- **[mqtt-integration.mdc](.cursor/rules/mqtt-integration.mdc)** - MQTT & discovery
  - Discovery protocol details
  - Entity configuration
  - Common issues and fixes

### ⚙️ Environment & Setup

- **[devcontainer-quirks.mdc](.cursor/rules/devcontainer-quirks.mdc)** - Dev environment
  - Docker and Supervisor setup
  - Credentials and access
  - Supervisor API access patterns
  - Common commands

- **[mcp-tools-guide.mdc](.cursor/rules/mcp-tools-guide.mdc)** - MCP tools usage
  - When to use each MCP server
  - Tool usage priorities
  - Common patterns
  - Troubleshooting

### ✋ Critical Rules

- **[important-dont-rules.mdc](.cursor/rules/important-dont-rules.mdc)** - Prevent bugs
  - Don't bypass authentication
  - Don't auto-refresh after ACKs
  - Don't hardcode credentials
  - Other critical "DON'T" rules

### 📋 Contribution Process

- **[pr-checklist.mdc](.cursor/rules/pr-checklist.mdc)** - PR requirements
  - Code quality checklist
  - Testing requirements
  - Documentation updates
  - Files not to commit

## How AI Uses These Rules

When the AI agent works on this repository, it will:

1. **Always apply** rules marked with `alwaysApply: true`
   - These are always visible and enforced

2. **Apply file-specific rules** based on glob patterns
   - Python files trigger Python rebuild rules
   - Shell scripts trigger shell scripting rules
   - etc.

3. **Reference on demand** for manually applied rules
   - You can ask the AI to reference a specific rule
   - Helpful for understanding workflow before starting

## How Developers Use These Rules

1. **Bookmark key rules** like [quick-start.mdc](.cursor/rules/quick-start.mdc)
2. **Reference before starting** work on a specific area
3. **Share with team** to ensure consistent practices
4. **Update together** when processes change

## Adding New Rules

To add a new rule:

1. Create a file in `.cursor/rules/` with `.mdc` extension
2. Add frontmatter with metadata (see examples)
3. Write the rule in Markdown with relevant details
4. Reference files using `[filename.ext](mdc:filename.ext)` format
5. Commit and share with team

## Structure

Each rule file contains:

```markdown
---
alwaysApply: true          # or globs: pattern
description: What this is  # Optional description for UI
---

# Title

Rule content in Markdown...
```

For more details on creating rules, see Cursor's documentation.

---

**Last Updated:** 2025-10-23  
**Maintainer:** AI Agent & Development Team
