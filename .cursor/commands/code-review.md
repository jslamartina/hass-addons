# Comprehensive Code Review for this repository (parent: hass-addons; child: python-rebuild-tcp-comm)

## Goal

- Perform a thorough, actionable code review across pending Git changes, focusing on "bugs, SOLID, accuracy, tests".
- Deliver a Cursor Plan with prioritized findings with code citations and concrete fixes, aligned with project rules.

## Preset defaults (override only if needed)

- SCOPE: Pending Git Changes
- AREAS_OF_FOCUS: "bugs, SOLID, accuracy, tests"
- MAX_ISSUES: Unlimited

## Repository Context (must follow)

- Project: hass-addons (parent) + python-rebuild-tcp-comm (child). Treat as a single system.
- Python edits require REBUILD; config/static changes require RESTART. Never start Docker manually (Supervisor manages).
- Lint-Format-First. No code should be proposed that would fail [`npm run lint`](../../package.json#L18).
- Logging-First. New functions must have entry/exit logs, no secrets, and logger/handler levels set from config.
- DRY/SOLID, clean architecture, separation of concerns.
- Single findings file per investigation. Keep output concise; move detail to a findings artifact as specified below.
- For any external lookups, use Brave Search MCP (not built-in web), and prefer Brave AI Grounding for synthesized, cited answers.

## Exploration Method (how to work)

- Start with a broad semantic discovery pass across the repo; then drill down by subsystem.
- Prefer semantic code search over exact text when exploring; use exact grep for symbol/name lookups.
- Break questions into small, focused searches. Keep searching until confident coverage is complete.
- Maximize parallel read-only operations (multiple searches, greps, file reads) rather than sequential steps.
- For large files, search within the file (vs reading entire file) to find relevant regions faster.

## What to Review (checklist)

- Architecture: layering, boundaries, duplication, cohesion, reuse; adherence to DRY/SOLID; cross-module dependencies.
- Logging: entry/exit logs on new/critical paths; no secrets; levels from config; consistency with logging-mandatory/patterns/examples.
- Error handling: clear exceptions, no silent failures, consistent handling; actionable messages; no broad blanket excepts.
- State management: follows critical-state-management rules; atomic updates; consistency across async flows.
- MQTT: discovery, suggested_area usage, entity cleanup, behavior on changes; scripts for cleanup; topics and payload correctness.
- Credentials/security: critical-credentials rules; options/secrets usage; Supervisor API handling/auth; no hardcoded secrets.
- Dev workflow: [rebuild.sh](../../cync-controller/rebuild.sh), [config.yaml](../../cync-controller/config.yaml), [run.sh](../../cync-controller/run.sh), Docker/devcontainer patterns; never bypass Supervisor; restart/rebuild distinctions.
- Performance: avoid blocking I/O on critical paths; async correctness; batching/throttling; resource usage in loops.
- Tests: coverage of core paths; deterministic tests; fixtures/mocks for IO; meaningful assertions; CI readiness.
- Docs: living docs rules; avoid history/future in living files; clarity of HOW/WHAT now; add Mermaid diagrams where needed (flow, sequence, state).

## Deliverables (must provide)

1) High-level Summary (at top)
   - Prioritized issues (no cap) across categories with severity (P1 critical, P2 major, P3 minor), impact, and quick-win labels.
2) Detailed Findings Artifact (single file)
   - Create one findings file under `~/hass-addons/working-files/<YYYYMMDDhhmm>_<conversation-topic-slug>-code-review/<YYYYMMDDhhmm>_code-review.md`
   - Include: issues grouped by category; code citations; rationale; fix proposals; risk/effort; ordered remediation plan.
   - If helpful, include a `.mermaid` diagram file in the same folder for key visual flows.
3) For each issue
   - Code citations using CODE REFERENCES (see exact format below).
   - Why it’s an issue (risk/impact), how to detect/measure (if applicable).
   - Minimal, precise fix with either edited code or step-by-step instructions.
   - Mark if fix requires REBUILD vs RESTART and any follow-up commands.
4) Quick Wins vs Deep Work
   - Separate lists with estimated effort (S/M/L) and blast radius (low/med/high).
5) Verification steps
   - Exact commands (lint, format, rebuild/restart, logs) and what to check in output.

## Output and Formatting Rules (strict)

- Use status updates: 1–2 sentences before each new batch of searches/reads; again before final summary.
- For file changes, put the document-relative location (with starting line number) **outside** the fence so Cursor/VSC can treat it as a clickable link, then follow with the diff block, e.g.

  [../../python-rebuild-tcp-comm/src/harness/toggler.py#L50](../../python-rebuild-tcp-comm/src/harness/toggler.py#L50)

  ```diff
  + # Initialize new logging system
  + logger = get_logger(__name__)

  # Configure third-party loggers (uvicorn, mqtt) to reduce noise
  - uv_handler = logging.StreamHandler(sys.stdout)
  uv_handler.setLevel(logging.INFO)
  ```

  [../../docs/developer/architecture.md#L26](../../docs/developer/architecture.md#L26)

  ```diff
  cloud_relay:
    enabled: false # Enable relay mode (disables commands)
  - forward_to_cloud: true # Forward packets to cloud (false = LAN-only)
  + cloud_server: "35.196.85.236" # Cync cloud server IP
  + cloud_port: 23779 # Cync cloud port
    debug_packet_logging: false # Log parsed packets (verbose)
    disable_ssl_verification: false # Disable SSL verify (debug only)
  ```

  If you're adding a brand-new file, list the intended path on its own line before the fence (Cursor will treat it as a clickable target once the file exists).

  [../../docs/developer](../../docs/developer/)

  ```markdown
  # This is my new document
  ## It did not exist before
  ```

- Follow [markdown-conventions.md](../rules/markdownlint-conventions.mdc)
- Keep the chat response concise and skimmable; put exhaustive details into the findings file. Only one findings file.

## Acceptance Criteria

- Coverage: You reviewed all major subsystems in "/hass-addons", including architecture, logging, errors, state, MQTT, security, workflow, performance, tests, and docs.
- Quality: Each reported issue has at least one valid code citation and an actionable fix proposal.
- Prioritization: Issues tagged with P1/P2/P3; quick wins clearly called out. No cap on count; do not truncate.
- Compliance: All rules above followed; no extra findings files; formatting/citation rules honored.
- Commands: Provide exact verification commands and expected outcomes.

## Repository-specific commands (reference)

- Lint/format (spot check):
  - npm run lint
- Rebuild (Python changes):
  - cd /workspaces/hass-addons/cync-controller && ./rebuild.sh
- Restart (config/static changes):
  - ha addons restart local_cync-controller
- Logs (follow):
  - ha addons logs local_cync-controller --follow
- MQTT cleanup (when discovery fields change):
  - sudo python3 /workspaces/hass-addons/scripts/delete-mqtt-safe.py --dry-run

## Review Flow (execute in this order)

1) Discovery pass: broad semantic search across repo; identify key subsystems and files.
2) Drill-down: targeted searches for logging, errors, state mgmt, MQTT, credentials, build/rebuild scripts, tests.
3) Read and cite: open only relevant file regions; cite with CODE REFERENCES.
4) Findings: draft issues with severity, rationale, fixes; group and prioritize.
5) Produce plan (+ optional .mermaid).
6) Finalize: high-level summary in chat; create the Cursor Plan; provide verification commands.
