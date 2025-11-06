# Cursor Rules Guide

This project uses Cursor Rules for all development guidance. These rules replaced the old `AGENTS.md` file to provide more targeted, context-aware guidance.

All rules are stored in `.cursor/rules/` with the `.mdc` extension.

## Rules Index

### Always Apply Rules

These rules are always loaded when working in the repository:

1. **[development-workflow.mdc](.cursor/rules/development-workflow.mdc)** - 4-step development process
2. **[linting-mandatory.mdc](.cursor/rules/linting-mandatory.mdc)** - Code quality requirements
3. **[git-practices.mdc](.cursor/rules/git-practices.mdc)** - Git and commit guidelines
4. **[logging-mandatory.mdc](.cursor/rules/logging-mandatory.mdc)** - Modern structured logging requirements

### Critical Guardrails

These prevent common mistakes and are always loaded:

5. **[critical-commands.mdc](.cursor/rules/critical-commands.mdc)** - Command handling rules
6. **[critical-state-management.mdc](.cursor/rules/critical-state-management.mdc)** - State management rules
7. **[critical-credentials.mdc](.cursor/rules/critical-credentials.mdc)** - Credential handling rules
8. **[critical-docker.mdc](.cursor/rules/critical-docker.mdc)** - Docker handling rules
9. **[file-size-limits.mdc](.cursor/rules/file-size-limits.mdc)** - Code file size limits (600 lines)

### File-Specific Rules

Rules that only apply to specific file types (Python, shell scripts, etc.):

11. **[python-changes-require-rebuild.mdc](.cursor/rules/python-changes-require-rebuild.mdc)** - Python rebuild workflow
12. **[shell-scripting.mdc](.cursor/rules/shell-scripting.mdc)** - Shell script standards
13. **[mqtt-integration.mdc](.cursor/rules/mqtt-integration.mdc)** - MQTT discovery patterns

### Reference Rules

Context-specific rules that can be referenced on demand:

#### Quick Reference & Navigation

14. **[quick-start.mdc](.cursor/rules/quick-start.mdc)** - Navigation index to all rules
15. **[daily-dev-cheatsheet.mdc](.cursor/rules/daily-dev-cheatsheet.mdc)** - Most common daily commands

#### Setup & Requirements

16. **[dns-requirements.mdc](.cursor/rules/dns-requirements.mdc)** - DNS redirection setup (REQUIRED)
17. **[token-creation-flow.mdc](.cursor/rules/token-creation-flow.mdc)** - Automated LLAT creation
18. **[devcontainer-quirks.mdc](.cursor/rules/devcontainer-quirks.mdc)** - Dev environment setup

#### Helper Tools & Automation

19. **[helper-scripts.mdc](.cursor/rules/helper-scripts.mdc)** - Automation scripts and tools
20. **[mqtt-entity-cleanup.mdc](.cursor/rules/mqtt-entity-cleanup.mdc)** - Entity deletion workflows
21. **[common-commands.mdc](.cursor/rules/common-commands.mdc)** - Command reference
22. **[mcp-tools-guide.mdc](.cursor/rules/mcp-tools-guide.mdc)** - MCP tools usage

#### Testing & Debugging

23. **[testing-workflows.mdc](.cursor/rules/testing-workflows.mdc)** - Testing procedures
24. **[ai-browser-testing.mdc](.cursor/rules/ai-browser-testing.mdc)** - Playwright browser automation
25. **[debugging-guide.mdc](.cursor/rules/debugging-guide.mdc)** - Debug techniques
26. **[known-bugs-workarounds.mdc](.cursor/rules/known-bugs-workarounds.mdc)** - Bug patterns and fixes

#### Architecture & Patterns

27. **[architecture-concepts.mdc](.cursor/rules/architecture-concepts.mdc)** - Key architectural patterns
28. **[repository-structure.mdc](.cursor/rules/repository-structure.mdc)** - Project structure
29. **[supervisor-api-access.mdc](.cursor/rules/supervisor-api-access.mdc)** - Supervisor API patterns
30. **[cloud-relay-patterns.mdc](.cursor/rules/cloud-relay-patterns.mdc)** - Cloud relay mode usage

#### Performance & Optimization

31. **[performance-tuning.mdc](.cursor/rules/performance-tuning.mdc)** - Performance tuning and optimization
32. **[logging-examples.mdc](.cursor/rules/logging-examples.mdc)** - Logging patterns

#### Documentation & Process

33. **[documentation-archiving.mdc](.cursor/rules/documentation-archiving.mdc)** - Documentation archiving
34. **[pr-checklist.mdc](.cursor/rules/pr-checklist.mdc)** - PR submission checklist

## When Each Rule Applies

- **Always Apply:** Automatically loaded for all development tasks
- **Globs:** Auto-applied when editing matching files (e.g., Python files, shell scripts)
- **Reference:** On-demand, referenced by other rules or when specifically needed

## How AI Uses These Rules

1. **Automatically applies** rules marked with `alwaysApply: true`
2. **Applies file-specific rules** based on glob patterns when editing those files
3. **References on demand** for context-specific guidance

## Development Workflow

1. Follow **development-workflow.mdc** for the standard 4-step process
2. Reference **quick-start.mdc** for navigation overview if needed
3. Reference specific rules as needed during development

## See Also

- `CONTRIBUTING.md` - Full contribution guidelines
- `docs/developer/architecture.md` - Protocol details
- `docs/user/troubleshooting.md` - Known issues and solutions
- `.devcontainer/README.md` - Devcontainer setup

---

**Note:** These rules replaced the old `AGENTS.md` file to provide more modular, context-aware guidance.
