# Cursor Configuration for Home Assistant Add-ons

This directory contains Cursor-specific configuration to enhance AI assistance and code consistency.

## Rules Philosophy: Top+Tail Architecture

The rules structure is designed to combat **"lost-in-the-middle"** problems where LLMs ignore instructions buried in long contexts:

### Design Principles

1. **Top + Tail Salience** - Critical guardrails duplicated at start and end
   - `_00-exec-rules.mdc` - 7 must-follow rules (~214 tokens) at the top
   - `zz_end_recap.mdc` - One-line recap at the bottom
   - Model attends best to beginning and end; worst in the middle

2. **ACK Pattern (Always-Apply)** - Mandatory acknowledgment before any action
   - `_00-first-turn-ack.mdc` - Forces model to emit `ACK:{...}` with 7 rules + verification
   - `_00-guard-no-act-before-ack.mdc` - Blocks tool calls until ACK emitted
   - **Format:** First reply must start with `ACK:{rules_you_will_follow: [...], how_you_will_verify: [...]}` and end with `ACK-DONE`
   - Prevents action without explicit rule acknowledgment

3. **Fetch-on-Demand** - Long guidance kept as indexed modules, not inline dumps
   - `_10-rules-index.mdc` - Points to topic modules (use code search)
   - Avoids pasting 100k tokens of docs; model fetches sections as needed
   - Keeps creativity high while maintaining guardrails

4. **Byte-Stable Guardrails** - No timestamps or dynamic content in critical files
   - Preserves provider caching
   - Reduces drift across turns
   - Critical rules remain consistent

### The 7 Executive Rules

All work must follow these non-negotiable guardrails (see `_00-exec-rules.mdc`):

1. Python edits → rebuild with `./rebuild.sh`, never just restart
2. Never hardcode IPs/tokens; use env/config; never commit secrets
3. Device commands: register callbacks before send, wait for ACK
4. Logging mandatory: log entry/exit, state changes; set both logger AND handler levels from config
5. Docker/Supervisor: use `ha` CLI only; never start Docker manually
6. DNS redirection REQUIRED; validate with `dig cm.gelighting.com` before debugging
7. Multi-step (3+): track todos, update status (in_progress → completed), summarize at end

## Structure

- **`rules/`** - Development rules and guidelines
  - See [RULES_GUIDE.md](RULES_GUIDE.md) for detailed information
  - Rules apply automatically based on file type or when manually referenced

- **`RULES_GUIDE.md`** - Index and explanation of all rules

- **`mcp.json`** - MCP servers configuration (if present)

## Quick Links

### For New Contributors

Start with **[rules/\_10-rules-index.mdc](rules/_10-rules-index.mdc)** for:

- Fetch-on-demand navigation to all rule modules
- Essential commands and workflows
- Topic-specific guidance

### Common Tasks

| Task                  | Rule                                                                           |
| --------------------- | ------------------------------------------------------------------------------ |
| Editing Python        | [python-changes-require-rebuild.mdc](rules/python-changes-require-rebuild.mdc) |
| Writing shell scripts | [shell-scripting.mdc](rules/shell-scripting.mdc)                               |
| Creating token        | [token-creation-flow.mdc](rules/token-creation-flow.mdc)                       |
| Submitting PR         | [pr-checklist.mdc](rules/pr-checklist.mdc)                                     |
| Critical "DON'Ts"     | [important-dont-rules.mdc](rules/important-dont-rules.mdc)                     |

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
