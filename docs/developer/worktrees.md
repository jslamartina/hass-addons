# Worktree-Friendly Paths

## Why This Matters

We frequently operate from two different roots:

- Devcontainer: `/workspaces/hass-addons`
- Worktrees: `/root/.cursor/worktrees/<slug>/hass-addons`

Hard-coding one root breaks the other. Use the patterns below so every script, doc step, and test works from both locations (and any future clones).

## Shell Pattern

```bash
export HASS_ADDONS_ROOT="${HASS_ADDONS_ROOT:-$(git rev-parse --show-toplevel)}"
cd "$HASS_ADDONS_ROOT"
```

Use `$HASS_ADDONS_ROOT/<subdir>` instead of absolute `/workspaces/...` references in docs and scripts.

## Python Pattern

```python
from pathlib import Path
import os

def repo_root() -> Path:
    env_root = os.getenv("HASS_ADDONS_ROOT")
    if env_root:
        return Path(env_root).expanduser().resolve()
    current = Path(__file__).resolve()
    for candidate in current.parents:
        if (candidate / ".git").exists():
            return candidate
    return current
```

Use `repo_root() / "hass-credentials.env"` (or similar) as the base for filesystem operations. Allow overrides with `HASS_CREDENTIALS_FILE` when dealing with sensitive material.

## Editor / Tooling Config

- Prefer `${workspaceFolder}` over fixed paths.
- Avoid storing the resolved devcontainer path inside `.vscode` or workspace files.

## Documentation Checklist

- Show commands as `cd "$REPO_ROOT"` instead of `cd /workspaces/...`.
- Mention that `REPO_ROOT` can come from `HASS_ADDONS_ROOT` or `git rev-parse`.
- When referencing a file path, prefer relative (`python-rebuild-tcp-comm/captures/`) plus a short note about resolving the repo root.
