# Rules Index

## Purpose

This page groups the `.cursor/rules/*.mdc` files by topic so both humans and the
agent can quickly find the right rule document to open on demand.

## Global Guardrails & Workflow

- `_00-rules-prefix.mdc`: Global guardrails and high-level rules that always apply.
- `development-workflow.mdc`: Full 3-step development workflow and quality gates.
- `python-changes-require-rebuild.mdc`: Details on when to rebuild vs restart.
- `inheritance-model.mdc`: How parent and child rule sets interact.

## Linting, Docs & Working Files

- `markdownlint-conventions.mdc`: Markdownlint rules and formatting guidance.
- `documentation-standards.mdc`: Documentation length limits and living-doc rules.
- `documentation-archiving.mdc`: How to archive completed investigations to `docs/archive/`.
- `git-practices.mdc`: Commit, branch, and PR guidelines.
- `working-files-convention.mdc`: Working-files directory structure and lifecycle.

## Logging & Debugging

- `logging-mandatory.mdc`: Mandatory logging requirements for all code changes.
- `logging-patterns.mdc`: Logging configuration patterns and anti-patterns.
- `logging-examples.mdc`: Concrete logging examples to copy.
- `debugging-with-logs.mdc`: How to debug via logs and view them effectively.
- `mermaid-diagrams.mdc`: How and when to use Mermaid diagrams.

## Runtime, MQTT & Cloud Relay

- `critical-commands.mdc`: Command callbacks, ACK handling, and timeouts.
- `critical-state-management.mdc`: Device/controller state and offline/online rules.
- `mqtt-integration.mdc`: MQTT discovery and Home Assistant integration patterns.
- `mqtt-entity-cleanup.mdc`: Safe MQTT entity cleanup workflows.
- `cloud-relay-patterns.mdc`: Cloud relay mode behavior and limitations.
- `dns-requirements.mdc`: DNS redirection and name-resolution requirements.
- `supervisor-api-access.mdc`: Home Assistant Supervisor API access and auth.

## Tooling, Environment & Web Search

- `critical-docker.mdc`: Docker/devcontainer rules and build patterns.
- `devcontainer-quirks.mdc`: Devcontainer setup and troubleshooting.
- `helper-scripts.mdc`: Available helper scripts and how to run them.
- `daily-dev-cheatsheet.mdc`: Quick reference for common dev commands.
- `mcp-tools-guide.mdc`: MCP tools (GitHub, Brave Search, etc.) usage.
- `ai-browser-testing.mdc`: Playwright-based browser testing guidance.
- `brave-ai-grounding-cli.mdc`: Brave AI Grounding CLI usage patterns.
- `web-search-brave.mdc`: Brave Search MCP web/news/image/video search usage.
- `token-creation-flow.mdc`: Automated LLAT creation and debugging.

## Architecture, Quality & Testing

- `architecture-concepts.mdc`: Core architecture and module responsibilities.
- `performance-tuning.mdc`: Performance investigation and optimization patterns.
- `known-bugs-workarounds.mdc`: Known issues and existing workarounds.
- `shell-scripting.mdc`: Shell script standards and requirements.
- `testing-workflows.mdc`: Testing workflows, markers, and procedures.
