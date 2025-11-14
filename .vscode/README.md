# VS Code Tasks Configuration

## Ruff Linting Tasks

This directory contains VS Code task configurations for running Ruff linting checks.

### Tasks Available

1. **Ruff: Check All Files (cync-controller)** - Runs Ruff on `cync-controller` directory
2. **Ruff: Check All Files (python-rebuild-tcp-comm)** - Runs Ruff on `python-rebuild-tcp-comm` directory
3. **Ruff: Check All Files (Both Projects)** - Runs both tasks in parallel

### Purpose

These tasks provide **manual** Ruff linting via VS Code's task system. They complement (but don't replace) the Ruff extension's native language server integration.

**Note:** The Ruff extension (`charliermarsh.ruff`) already provides automatic error detection in the Problems tab. These tasks are useful for:

- Manual linting runs via Command Palette (`Ctrl+Shift+P` → "Tasks: Run Task")
- CI/CD integration scenarios
- Batch linting across multiple projects
- When extension language server is disabled

### Key Features

- **Improved regex pattern**: Handles Ruff's `[*]` fixable markers cleanly
- **Error handling**: Tasks won't fail if Ruff isn't installed or directories are missing
- **No auto-run**: Tasks don't run automatically on folder open (prevents duplicate execution)
- **Problem matcher**: Parses Ruff output and shows errors in Problems tab

### Usage

Run tasks manually via:

- Command Palette: `Ctrl+Shift+P` → "Tasks: Run Task" → Select task
- Terminal: `Ctrl+Shift+P` → "Tasks: Run Task" → Select task
- Keyboard shortcut: Configure in `keybindings.json` if desired

### Configuration Details

- **Output format**: `concise` (Ruff's compact format)
- **ANSI stripping**: Removes color codes for clean problem matcher parsing
- **Error handling**: Uses `|| true` to prevent task failure on lint errors
- **Regex pattern**: `^(.+):(\\d+):(\\d+):\\s+(\\w+)(?:\\s+\\[\\*\\])?\\s+(.+)$`
  - Captures: file, line, column, code, message
  - Optionally handles `[*]` fixable markers

### Related Documentation

- Ruff extension: `.devcontainer.json` (configured with native language server)
- Linting setup: `docs/developer/linting-setup.md`
- Contributing guide: `CONTRIBUTING.md`
