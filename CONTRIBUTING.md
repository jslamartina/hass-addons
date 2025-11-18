# Contributing to Cync Controller

Thank you for your interest in contributing to the Cync Controller add-on!

> **Project status:** This repository is now the canonical home for the add-on. All contributions should target the `dev` branch; `master` is reserved for release tags.

## Table of Contents

- [Code Quality and Linting](#code-quality-and-linting)
- [Python Code](#python-code)
- [Configuration Files](#configuration-files)
- [Shell Scripts](#shell-scripts)
- [PR Submission](#pr-submission)

## Code Quality and Linting

### ⚠️ CRITICAL: Linting is MANDATORY after every file edit. Issues must be fixed before work is complete

All code should follow linting suggestions provided by the appropriate static analysis tools:

### Python Code

Use [Ruff](https://docs.astral.sh/ruff/) for fast, comprehensive linting and formatting:

- Modern linter and formatter written in Rust (10-100x faster than Pylint/Flake8/Black)
- Checks for errors, enforces coding standards, and identifies code smells
- Compatible with Pylint, Flake8, isort, and Black formatter rules
- Follows PEP 8 style guidelines and supports modern Python features
- Configuration in `pyproject.toml` (lines 41-101)
- **Replaces Pylint and Black** - Both extensions removed from devcontainer
- **VS Code Integration** - Errors appear automatically in Problems tab (no need to run commands)
- **Autofix and format on save** - `source.fixAll`, `source.organizeImports`, and formatting enabled

### Running Linters

```bash
## Run all linters (Python + Shell + Format check)
npm run lint
## or
./scripts/lint-all.sh

## Python only
npm run lint:python
## or
ruff check .

## Auto-fix Python issues
npm run lint:python:fix
## or
ruff check . --fix

## Shell scripts only
npm run lint:shell
```

## Code Formatting

```bash
## Format all files (Python, Markdown, JSON, YAML, Shell)
npm run format

## Check formatting without modifying files
npm run format:check

## Format specific file types
npm run format:python       # Python files only
npm run format:python:check # Check Python formatting
npm run format:shell        # Shell scripts only
npm run format:json         # JSON/YAML files only
```

**Why this matters:** Linting catches bugs early, ensures consistency across the codebase, and improves maintainability. **Skipping linting leads to technical debt accumulation** - small issues compound into large problems that are harder to fix later.

### Enforcement Policy

1. ✅ Run linters after EVERY file edit (not just at the end)
2. ✅ Fix ALL issues before moving to the next task
3. ✅ Use autofix tools (`npm run lint:python:fix`, `npm run format`) to speed up fixes
4. ❌ NEVER commit code with linting errors
5. ❌ NEVER skip linting because "it's just a small change"

### How to Check for NEW Linting Errors

When you modify files, check for new errors by running `ruff check` on the specific files you edited:

```bash
## ✅ CORRECT: Check the files you modified
ruff check cync-controller/src/cync_lan/mqtt_client.py cync-controller/src/cync_lan/devices.py

## ❌ WRONG: Don't grep for specific line numbers or filter output
ruff check cync-controller/src/cync_lan/mqtt_client.py | grep "1708" # Misses other errors!

## ✅ CORRECT: Full output shows ALL errors (pre-existing + new)
## Compare error count before and after your changes
```

**Pre-existing technical debt** (like "too many branches") can be ignored if they existed before your changes, but **NEW errors must be fixed immediately**. The key is to see the full output to identify what you introduced.

### Shell Scripts

Use [ShellCheck](https://www.shellcheck.net/wiki/) for shell script analysis:

- Provides warnings for easy-to-miss issues (quoting, variable expansion, etc.)
- Suggests best practices for POSIX compliance
- Address all shellcheck warnings before committing
- Particularly important for `.devcontainer` and `scripts/` directories

### Guidelines

- Use `bashio::` functions for add-on scripts (provided by Home Assistant base image)
- Always use `set -e` for error handling
- Use descriptive variable names in SCREAMING_SNAKE_CASE for environment variables
- Comment complex logic, especially protocol-specific code

#### Script Idempotency

**All scripts MUST be idempotent** - running the same script multiple times should produce the same result without causing errors or unwanted side effects.

#### Why idempotency matters

1. **Reliability** - Scripts can safely recover from failures by re-running
2. **Development workflow** - Devcontainer startup scripts run on every container restart
3. **Automation** - CI/CD pipelines and automated testing can safely re-run operations
4. **User experience** - Users can safely re-run setup scripts without breaking their environment
5. **Debugging** - Failed operations can be retried without manual cleanup

### How to achieve idempotency

- ✅ **Check before creating** - Test if files/directories/resources exist before creating them:

  ```bash
  # ✅ GOOD: Idempotent
  if [ ! -d "/path/to/dir" ]; then
    mkdir -p /path/to/dir
  fi

  # ✅ BETTER: mkdir -p is inherently idempotent
  mkdir -p /path/to/dir
  ```

- ✅ **Use conditional operations** - Only perform actions when necessary:

  ```bash
  # ✅ GOOD: Only install if not already installed
  if ! command -v docker &> /dev/null; then
    apt-get install -y docker
  fi
  ```

````text

- ✅ **Use upsert patterns** - Create or update (don't fail if exists):

  ```bash
  # ✅ GOOD: Use -f for file operations
  ln -sf /source /target # Overwrites existing symlink
  cp -f source dest      # Overwrites existing file

  # ✅ GOOD: Use || true for non-critical operations
  docker network create my-network 2> /dev/null || true
````

- ✅ **Cleanup stale state** - Remove partial/corrupted state before creating:

  ```bash
  # ✅ GOOD: Clean up before fresh install
  rm -f /tmp/incomplete_download
  curl -o /tmp/complete_download https://example.com/file
  ```

### Common idempotent patterns

```bash
## File creation - use conditional or -p flag
mkdir -p /path/to/dir                 # Always safe
[ -f /path/file ] || touch /path/file # Create if missing

## Package installation - check first
dpkg -l | grep -q package || apt-get install -y package

## Configuration - use append if not present
grep -q "config_line" /etc/config || echo "config_line" >> /etc/config

## Service management - restart vs start
systemctl restart service # Works whether running or not
## Better than: systemctl start service (fails if already running)

## Docker operations - use || true or check first
docker rm -f container_name 2> /dev/null || true # Safe cleanup
docker network create net 2> /dev/null || true   # Create if missing

## Git operations - safe patterns
git pull || git clone https://repo.git        # Pull if exists, clone if not
git checkout -b branch || git checkout branch # Create or switch
$()$(
  bash

  ## Anti-patterns (non-idempotent)

)$()bash
## ❌ BAD: Fails on second run
mkdir /path/to/dir           # Error: directory exists
docker network create my-net # Error: network exists
ln -s /source /target        # Error: file exists

## ❌ BAD: Appends on every run (duplicates)
echo "export PATH=/new:$PATH" >> ~/.bashrc # Duplicates every run

## ❌ BAD: Side effects accumulate
counter=$((counter + 1)) # Increments on every run
$()$(
  markdown

  ## Testing for idempotency:

  The simplest test is to run your script twice in succession:

)$()bash
## Should succeed both times with same result
./my-script.sh
./my-script.sh # Should not fail or change state
```

## Examples from this repo

- `.devcontainer/post-start.sh` - **MUST be idempotent** (runs on every container restart)
- `scripts/setup-fresh-ha.sh` - Designed to be safely re-run if interrupted
- `cync-controller/rebuild.sh` - Safe to run multiple times (cleans before building)

## Python Code

### Style guidelines for the cync-controller package

- Follow Ruff formatter style (Black-compatible, configured in pyproject.toml)
- Use type hints for function signatures
- Async/await for all I/O operations (TCP, MQTT, HTTP)
- Logging prefix format: `lp = "ClassName:method_name:"`
- Use dataclasses or Pydantic models for structured data

## Configuration Files

- Add-on config: `cync-controller/config.yaml` (JSON Schema format)
- Environment variables: Prefix with `CYNC_` for add-on settings
- MQTT topics: Follow Home Assistant MQTT discovery schema

## PR Submission

### Before submitting a pull request

1. **Title Format:** Use clear, descriptive titles in the format: `[component] Brief description`
   - Examples: `[cync-controller] Fix device availability flickering`, `[docs] Update AGENTS.md standard compliance`

2. **Pre-submission Checklist:**
   - [ ] **MANDATORY: Zero linting errors** - Run `npm run lint` and verify all checks pass
   - [ ] **MANDATORY: Code is formatted** - Run `npm run format:check` with no issues
   - [ ] Used autofix tools: `npm run lint:python:fix` and `npm run format`
   - [ ] All tests pass and no linting/formatting errors remain
   - [ ] Update CHANGELOG.md for user-facing changes
   - [ ] Test in devcontainer environment
   - [ ] Verify add-on rebuilds successfully if Python code changed
   - [ ] **Double-check: No linting debt introduced** - Compare `npm run lint` output before and after changes

3. **Review Expectations:**
   - Changes should follow existing coding conventions
   - Include testing verification in PR description
   - Reference related issues or discussions
   - Be prepared to address review feedback promptly

## Testing Checklist

Before submitting changes:

1. [ ] **MANDATORY: All linting passes with zero errors**:
   - Run `npm run lint` - must show all green checkmarks
   - Run `npm run format:check` - must show no formatting issues
   - Fix any issues before proceeding (use `npm run lint:python:fix` and `npm run format`)

2. [ ] **If you edited Python files (`.py`)**: Rebuild with `./rebuild.sh` or `ha addons rebuild`
3. [ ] **If you only edited config/scripts**: Restart with `ha addons restart local_cync-controller`
4. [ ] Add-on starts without errors (`ha addons start local_cync-controller`)
5. [ ] Entities appear in Home Assistant (check Developer Tools → States)
6. [ ] Device commands work (toggle lights, adjust brightness)
7. [ ] **Group commands work** - Test toggling group entities multiple times
8. [ ] **Commands work after refresh** - Click "Refresh Device Status" then test commands immediately
9. [ ] **No availability flickering** - Watch device availability over 30+ seconds
10. [ ] MQTT messages are valid (check EMQX logs or `mosquitto_sub`)
11. [ ] No Python exceptions in logs (`ha addons logs local_cync-controller`)
12. [ ] Devcontainer still starts cleanly (test in fresh container)
13. [ ] Changes documented in CHANGELOG.md if user-facing
14. [ ] If config schema changed: Follow "Testing Add-on UI Configuration Changes" workflow
15. [ ] UI configuration options visible after hard refresh (Ctrl+Shift+R)

## Documentation Guidelines

When you complete a task or fix an issue, **document your findings in `docs/archive/`** rather than leaving summary files in the repository root.

### What belongs in `docs/archive/`

- Implementation summaries (for example, "How we fixed X")
- Debugging session findings
- Historical context for major changes
- Exploration notes and research
- One-off investigation results

### Why archive these

- ✅ Keeps repository root clean and focused
- ✅ Preserves institutional knowledge
- ✅ Makes findings searchable for future reference
- ✅ Separates active documentation from historical records

### File naming for archived docs

- Use descriptive SCREAMING_CAPS names: `SWITCH-STATUS-FIX-SUMMARY.md`
- Or timestamp prefix for chronological ordering: `2025-10-22-SETUP-SCRIPT-IDEMPOTENCY.md`
- Be specific in titles so content is discoverable

### What stays in repository root

- Active development guides (for example, AGENTS.md, CHANGELOG.md)
- Critical user-facing documentation (for example, README.md)
- Current project status files

## File Naming Conventions

- **Shell scripts**: `kebab-case.sh` (for example, `configure-addon.sh`)
- **Python files**: `snake_case.py` (for example, `mqtt_client.py`)
- **Documentation**: `SCREAMING_CAPS.md` for top-level, `kebab-case.md` for docs/ folder
- **Directories**: `kebab-case/` preferred
- **Archived documentation**: `YYYY-MM-DDTHH-MM-SS-category-description.md` (for example, `2025-10-14T17-00-00-MITM-CLEANUP_SUMMARY.md`)

---

_For more information, see [Cursor Rules Guide](.cursor/RULES_GUIDE.md)._
