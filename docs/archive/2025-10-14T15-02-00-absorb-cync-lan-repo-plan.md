# 2025 10 14T15 02 00 Absorb Cync Lan Repo Plan

<!-- 064fc85a-f42a-4957-a0fb-6fe899fde1ac 619cd7b8-2b1f-4fed-87d2-76d3b4b4e4b6 -->

## Cleanup Duplicate Files After Consolidation

## Current Situation

After consolidating the cync-controller repo, we have duplicated files in two places:

### Primary Source (Authoritative)

```bash
hass-addons/
├── pyproject.toml                  # Python package config
└── src/cync_lan/                   # Python package source
    ├── __init__.py
    ├── main.py
    ├── server.py
    └── ... (all Python files)
```text

### Build-Time Copies (Synced by rebuild.sh)

```sql
hass-addons/cync-controller/
├── pyproject.toml                  # DUPLICATE - synced from ../
└── src/cync_lan/                   # DUPLICATE - synced from ../src/
    ├── __init__.py
    ├── main.py
    └── ... (all Python files)
```text

## Why Duplicates Exist

The `rebuild.sh` script syncs files to `cync-controller/` because Docker's build context is limited to the `cync-controller/` directory. The Dockerfile can't access `../src/` directly.

## The Problem

1. **Two copies of everything** - pyproject.toml and entire src/ tree
2. **Confusion** - Which is the source of truth? (Answer: hass-addons/src/)
3. **Git tracking** - Should build-time copies be version controlled?
4. **Maintenance** - Easy to accidentally edit the wrong copy

## Solution Options

### Option 1: Keep Current Architecture (Recommended)

#### Keep duplicates but clarify their purpose

- Primary source: `hass-addons/src/cync_lan/` and `hass-addons/pyproject.toml`
- Build copies: `hass-addons/cync-controller/src/` and `hass-addons/cync-controller/pyproject.toml`
- Add to `.gitignore`: `cync-controller/src/` and `cync-controller/pyproject.toml`
- Update `rebuild.sh` to explain this

### Pros

- ✅ Works with Docker build context limitations
- ✅ Simple rebuild process
- ✅ No complex Docker workarounds needed

### Cons

- ⚠️ Duplicates exist (but gitignored)

### Option 2: Use Docker Build Context Tricks

#### Use .dockerignore and build args

- Keep only primary source
- Modify build process to set context higher
- Use build arguments to copy from parent directory

### Pros

- ✅ No duplicates

### Cons

- ⚠️ More complex build process
- ⚠️ May break Home Assistant's add-on builder expectations
- ⚠️ Harder to debug

### Option 3: Move Source Into cync-controller/

#### Make cync-controller/ the primary location

- Move `src/` → `cync-controller/src/`
- Move `pyproject.toml` → `cync-controller/pyproject.toml`
- Delete top-level copies

### Pros

- ✅ No duplicates
- ✅ Docker build context works naturally

### Cons

- ⚠️ Less conventional structure
- ⚠️ Couples package to add-on directory
- ⚠️ Harder to have multiple add-ons share code

## Recommended Approach: Option 1 (Clarify + Gitignore)

### Steps

1. **Add build-time copies to .gitignore:**

   ```gitignore
   # Build-time copies (synced from ../src by rebuild.sh)
   cync-controller/src/
   cync-controller/pyproject.toml
   ```

```text

1. **Update rebuild.sh with clear comments:**

   ```bash
   #!/bin/bash
   set -e

   # Sync source code from primary location (../src) to build directory
   # These are build-time copies required for Docker build context
   echo "Syncing cync-controller source code from ../src..."
   rsync -av --delete ../src/ src/ --exclude='__pycache__' --exclude='*.pyc'
   cp ../pyproject.toml pyproject.toml

   echo "Rebuilding addon..."
   ha addons rebuild local_cync-controller
   # ... rest
```text

1. **Add README note in cync-controller/ directory:**

Create `cync-controller/README-DEV.md`:

```markdown
## Developer Note

The `src/` and `pyproject.toml` in this directory are **build-time copies**
synced from `../src/` and `../pyproject.toml` by `rebuild.sh`.

**DO NOT EDIT FILES HERE** - Edit the primary source in `../src/cync_lan/` instead.

These copies exist because Docker's build context is limited to this directory.
```text

1. **Update AGENTS.md to explain the structure:**

Add note about primary vs build-time copies

### Alternative: Simplify with .dockerignore (If we want to try Option 2)

This would require testing and may not work with HA's builder system.

## Implementation Checklist

- [x] Add `cync-controller/src/` and `cync-controller/pyproject.toml` to .gitignore ✅
- [x] Update rebuild.sh with clear comments explaining primary vs build copies ✅
- [x] Create README-DEV.md in cync-controller/ explaining the copies ✅
- [x] Update AGENTS.md to document the primary source vs build copies structure ✅
- [x] Update AGENTS.md Task Planning section with instruction to update plan files after every step ✅
- [x] Test that add-on still builds correctly ✅
- [x] Verify .gitignore works (copies not tracked by git) ✅
- [x] Fix file paths in documentation files ✅
- [x] Clean up confusing documentation (deleted DOCS-OVERVIEW.md, improved DOCS.md and README-DEV.md) ✅

**Note:** This plan file was updated after each completed step to demonstrate the progressive update workflow.

## ✅ Complete Summary

All tasks from the cync-controller repository consolidation have been successfully completed:

### 1. Repository Consolidation

- ✅ Moved Python source from separate repo to `hass-addons/src/cync_lan/`
- ✅ Moved documentation to appropriate locations (developer/, protocol/)
- ✅ Updated all references and URLs

### 2. Build System

- ✅ Updated Dockerfile to use local source
- ✅ Updated rebuild.sh to sync from primary source
- ✅ Gitignored build-time copies

### 3. Documentation

- ✅ Fixed all file paths referencing old cync-controller repo
- ✅ Cleaned up confusing documentation files
- ✅ Each file now has clear purpose for its audience
- ✅ Updated AGENTS.md with plan update workflow instructions

### 4. Testing

- ✅ Add-on builds and runs successfully
- ✅ Manufacturer field corrected to "Savant"
- ✅ All repository URLs updated to jslamartina/hass-addons

The separate cync-controller repository has been successfully absorbed into hass-addons!
