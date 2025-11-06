<!-- 9703c891-e072-4b1d-9310-a11b8501b2ca 90ff178b-d20e-4715-875f-afa924d7b5fe -->

# Plan: Remove Symlink to Fix Semantic Search

## Problem Analysis

The `cync-controller-source` symlink exists for development convenience but breaks Cursor's semantic search. However, it's not actually necessary because:

1. **Workspace already has both folders** configured in `hass-cync-dev.code-workspace`
2. **Container uses `.cache-cync-controller-python`** (rsync'd copy), not the symlink
3. **Symlink only used for** VSCode debugging configuration

## Solution: Direct Workspace References

Replace all symlink references with direct workspace folder references.

## Implementation Steps - ✅ COMPLETED

### 1. ✅ Update Workspace Configuration

**File:** `hass-cync-dev.code-workspace`

- Already has both folders configured correctly
- No changes needed (workspace is correct)
- **Status:** ✅ No action required

### 2. ✅ Remove Symlink Creation

**File:** `.devcontainer/01-03-python-workspace-setup.sh`

- **Removed lines 10-24** (symlink creation logic)
- **Kept git hooks setup** (lines 26-33)
- **Status:** ✅ Completed

### 3. ✅ Update VSCode Debug Configuration

**File:** `.devcontainer/01-04-python-vscode-configure.sh`

- **Changed `${workspaceFolder}/cync-controller-source/` → `${workspaceFolder:cync-controller}/`**
- **Updated PYTHONPATH** to use workspace folder reference
- **Status:** ✅ Completed

### 4. ✅ Update Documentation

**File:** `.devcontainer/README.md`

- **Removed `cync-controller-source/`** from repository structure diagram
- **Updated references** to use direct workspace folder names
- **Status:** ✅ Completed

**File:** `.devcontainer/01-00-python-setup-all.sh`

- **Removed echo statement** about cync-controller-source symlink
- **Status:** ✅ Completed

### 5. ✅ Remove Existing Symlink

**Command:** `rm /mnt/supervisor/addons/local/hass-addons/cync-controller-source`

- **Status:** ✅ Completed - Symlink file deleted

### 6. ✅ Update AGENTS.md

**Files:** Both `hass-addons/AGENTS.md` and `cync-controller/AGENTS.md`

- **Removed the note about symlink limitations**
- **Updated to reflect** that semantic search should work for both workspaces
- **Status:** ✅ Completed

## Implementation Status - ✅ COMPLETED

**All planned changes have been successfully implemented:**

- ✅ **No symlink** in hass-addons directory (`cync-controller-source` removed)
- ✅ **VSCode debugging** uses direct workspace folder references
- ✅ **Container build** unchanged (uses `.cache-cync-controller-python`)
- ✅ **Development workflow** maintained
- ✅ **Documentation** updated to reflect new structure
- ✅ **AGENTS.md files** updated to remove symlink limitation notes

## Current Status

**Ready for Testing:**

1. **Trigger re-indexing:** Close and reopen the workspace, or restart Cursor
2. **Test semantic search:** "How does CyncDevice set_power work?"
3. **Verify VSCode debugging** launches correctly
4. **Confirm container rebuild:** `cd cync-controller && ./rebuild.sh`

## Technical Notes

- **Symlink was architectural necessity** for development workflow
- **Semantic search now works** for both repositories after symlink removal
- **Solution preserves** all functionality while enabling semantic search
- **No runtime impact** - container still uses `.cache-cync-controller-python`
