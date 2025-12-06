# Linting Setup Summary

## What Changed

### 1. Removed Pylint, Enabled Ruff

- **Removed**: `ms-python.pylint` extension
- **Removed**: `ms-python.isort` extension (Ruff handles import sorting)
- **Kept**: `charliermarsh.ruff` extension
- **Configured**: Ruff native language server to show errors in Problems tab

### 2. Configuration Updates

- `.devcontainer.json`: Disabled Pylint, removed deprecated Ruff settings
- `AGENTS.md`: Updated documentation to reflect Ruff as the standard linter
- `package.json`: Added convenient npm scripts for linting

### 3. Why Ruff?

- **10-100x faster** than Pylint/Flake8 (written in Rust)
- **Compatible** with Pylint, Flake8, isort rules
- **Modern** - supports Python 3.14+ features
- **Already configured** in `pyproject.toml`

## How to Use

### Command Line

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

### VS Code Problems Tab

- **Ruff errors will now appear automatically** in the Problems tab
- **No need to run commands** - errors show as you type
- **Autofix on save** - `source.fixAll` and `source.organizeImports` enabled

## Next Steps

1. **Reload VS Code Window** - Press `Ctrl+Shift+P` → "Developer: Reload Window"
2. **Verify**: Open `cync-controller/src/cync_lan/main.py` - you should see Ruff errors in Problems tab
3. **Fix issues**: Run `npm run lint:python:fix` to autofix many issues

## Current Status

Running `./scripts/lint-all.sh` shows **61 Ruff errors** (42 autofixable):

- Type annotation modernization (Optional[X] → X | None)
- Import organization issues
- **Critical**: Syntax errors in `devices.py` (indentation issues)
- Unused imports and f-strings

### Priority Fixes

1. **Fix syntax errors** in `devices.py` first (lines 2566-3097)
2. Run `ruff check . --fix` to autofix simple issues
3. Manually fix remaining type annotations and logic errors

## Documentation Updates

✅ **AGENTS.md updated** (October 17, 2025):

- Updated "Code Quality and Linting" section with Ruff details
- Added npm script commands for linting and formatting
- Updated "Workflow: Making Code Changes" to include linting steps
- Added linting commands to "Useful Commands" table
- Updated "PR Instructions" checklist with linting commands
- Added "Most used commands" section with linting shortcuts
- Added reference to this file in "Critical files to know" section

✅ **docs/README.md updated** (October 17, 2025):

- File moved from `.cursor/` to `docs/developer/` following naming conventions
- Renamed from `LINTING_SETUP.md` to `linting-setup.md` (kebab-case)
- Added to developer documentation structure diagram
- Updated all cross-references in AGENTS.md and README.md

✅ Linting and formatting information documented in AGENTS.md and cursor rules

## Summary

The repository now uses **Ruff as the standard Python linter** (replacing Pylint), with:

- Automatic error detection in VS Code Problems tab
- Autofix on save enabled
- Convenient npm scripts for all linting tasks
- Comprehensive documentation in AGENTS.md

All AI agents and developers should now use `npm run lint` and `npm run lint:python:fix` as part of their workflow.

## Unified Python project (Dec 2025)

- Single root `pyproject.toml` (package name `cync_controller`, version `0.0.4.13`).
- Install: `poetry install` (creates `.venv` at repo root).
- Lint: `ruff check .` (or `npm run lint:python`); type-check: `basedpyright --project pyrightconfig.json`.
- Tests: run targeted suites from root, e.g. `pytest tests/unit/protocol/test_checksum.py`.
- Console scripts preserved: `cync-controller`, `rebuild-tcp-comm`.
