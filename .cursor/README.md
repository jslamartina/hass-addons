# Cursor Configuration for Home Assistant Add-ons

This directory contains Cursor-specific configuration to enhance AI assistance and code consistency.

## Structure

- **`rules/`** - Development rules and guidelines
  - See [RULES_GUIDE.md](RULES_GUIDE.md) for detailed information
  - Rules apply automatically based on file type or when manually referenced

- **`RULES_GUIDE.md`** - Index and explanation of all rules

- **`mcp.json`** - MCP servers configuration (if present)

## Quick Links

### For New Contributors

Start with **[rules/quick-start.mdc](rules/quick-start.mdc)** for:
- Essential commands
- Development workflow
- Rules to remember

### Common Tasks

| Task | Rule |
|------|------|
| Editing Python | [python-changes-require-rebuild.mdc](rules/python-changes-require-rebuild.mdc) |
| Writing shell scripts | [shell-scripting.mdc](rules/shell-scripting.mdc) |
| Creating token | [token-creation-flow.mdc](rules/token-creation-flow.mdc) |
| Submitting PR | [pr-checklist.mdc](rules/pr-checklist.mdc) |
| Critical "DON'Ts" | [important-dont-rules.mdc](rules/important-dont-rules.mdc) |

## How Cursor Uses These Rules

1. **File-specific rules** automatically apply when editing certain files
   - Python files → Rebuild rules
   - Shell scripts → Scripting standards
   - etc.

2. **Always-apply rules** show up in every request
   - Linting requirements
   - Critical rules
   - Process guidelines

3. **Reference on demand** for manual lookups
   - Ask the AI about specific topics
   - Get consistent, rule-based guidance

## Key Resources

Main documentation:
- [AGENTS.md](../AGENTS.md) - Full development guide
- [CONTRIBUTING.md](../CONTRIBUTING.md) - Code standards
- [docs/developer/](../docs/developer/) - Architecture and guides
- [docs/user/](../docs/user/) - User documentation

Development environment:
- [.devcontainer/README.md](../.devcontainer/README.md) - Setup details
- [hass-credentials.env](../hass-credentials.env) - Credentials reference

---

**For more information**, see [RULES_GUIDE.md](RULES_GUIDE.md)
