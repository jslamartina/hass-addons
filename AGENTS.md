# AGENTS Guide (Codex)

- Repo contains the Home Assistant Cync Controller add-on (`cync-controller/`) and a child TCP library (`python-rebuild-tcp-comm/`). Follow parent rules unless working in the child project, where child rules extend the parent set.

## Golden Rules

- Never edit or add ignore files; never suppress lint/format/error rules without explicit user approval.
- Work in the loop: plan → edit → rebuild/restart → verify; stop on tool errors/timeouts. Keep responses concise (<200 lines).
- Prefer Brave Search MCP or Brave AI Grounding for web queries; built-in web search is forbidden.
- Logging is mandatory for code changes: structured logs with `extra={}`, entry/exit coverage, no secrets.
- Use `/working-files/<timestamp>_<topic>/...` for scratch artifacts; no `/tmp` use.
- Do not label anything “FINAL/COMPLETE/READY” without user confirmation or passing CI.

## Parent Project Workflow (cync-controller)

- Python edits → `cd cync-controller && ./rebuild.sh` (runs lint, format, tests, build). Config/static changes → `ha addons restart local_cync-controller`. When unsure, rebuild.
- Verify via `ha addons logs local_cync-controller --follow`. Never start Docker manually (Supervisor controlled).
- Markdown: `npx prettier --write <file.md>` + `npm run lint:markdown:fix`. Finish tasks with `npm run lint`.
- Key npm scripts: `npm run lint`, `npm run format`, `npm run test:unit`, Playwright via `npx playwright test`.

## Child Project Workflow (python-rebuild-tcp-comm)

- Package manager: Poetry 1.8.3. Development steps: edit → `poetry run ruff check .` and `pyright python-rebuild-tcp-comm/src python-rebuild-tcp-comm/tests` → `./scripts/test-all.sh` (or `./scripts/test-unit.sh`) → verify coverage ≥90%.
- Architecture: async I/O everywhere, strict type hints, absolute imports from package root.

## Critical Patterns

- Commands must register callbacks and wait for ACKs; handle timeouts with retries. Avoid refresh cascades after ACKs; update internal state before external notifications.
- Device offline handling uses failure thresholds (no immediate offline flips). Avoid polling loops; favor event-driven updates with scheduled health checks.

## Documentation Expectations

- Follow documentation-standards: keep docs concise, avoid redundancy; max one findings file per investigation. Living docs avoid status/timeline; archive completed work under `docs/archive/` with timestamped filenames when applicable.
- When editing docs, format with Prettier + markdownlint. Keep AGENTS and similar guides succinct and actionable.

## Navigation

- Docs index: `docs/README.md`. Developer guides: `docs/developer/` (architecture, testing, linting, MCP tools, entity management). User docs: `docs/user/` (DNS setup required).
- Cursor rules reference: `.cursor/rules/` (parent) and `python-rebuild-tcp-comm/.cursor/rules/` (child). Inheritance rules in `.cursor/rules/inheritance-model.mdc`.
