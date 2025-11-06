<!-- 93dce99d-9102-42af-8688-5444d3cfde77 fdd06d6e-7a19-4c09-ae87-5fc0bedbd94c -->

# Remove Duplicate Source Files After Repo Consolidation

## Problem

After consolidating the cync-controller repo, we have duplicate source files:

- Root level: `hass-addons/src/` and `hass-addons/pyproject.toml`
- Add-on level: `hass-addons/cync-controller/src/` and `hass-addons/cync-controller/pyproject.toml`

The "build copy" architecture is no longer needed since everything is in one repo. Docker can access `cync-controller/` directly.

## Solution

Keep source in `cync-controller/` (where Docker needs it) and remove root-level duplicates.

## Implementation Steps

- [x] Delete root-level duplicate files ✅
  - Removed `hass-addons/src/`
  - Removed `hass-addons/pyproject.toml`

- [x] Update `.gitignore` ✅
  - Removed build-time copy gitignore rules (lines 215-218)

- [x] Update `cync-controller/rebuild.sh` ✅
  - Removed rsync and cp commands (lines 22-25)
  - Simplified header comments to remove "build copy" architecture references

- [x] Update `cync-controller/README-DEV.md` ✅
  - Rewrote to reflect single source location in this directory
  - Added clear development workflow section

- [x] Update `AGENTS.md` ✅
  - Removed all "PRIMARY SOURCE" vs "BUILD COPY" distinctions
  - Updated Repository Structure section to show single source location
  - Updated file path references throughout
  - Removed references to rebuild.sh syncing files

- [x] Update `cync-controller/Dockerfile` ✅
  - Updated comments to remove symlink/build.yaml references

- [x] Test rebuild process ✅
  - Rebuild completed successfully
  - Addon restarted and running properly
  - MQTT discovery working correctly

## ✅ Complete Summary

Successfully simplified the repository architecture by removing duplicate source files. The "build copy" architecture from the separate repository days is no longer needed.

### Changes Made

1. **Deleted duplicates**: Removed root-level `src/` and `pyproject.toml`
2. **Single source location**: `cync-controller/src/` and `cync-controller/pyproject.toml` are now the only source
3. **Updated build process**: Simplified `rebuild.sh` to remove syncing logic
4. **Updated documentation**: AGENTS.md, README-DEV.md, and Dockerfile comments updated
5. **Verified functionality**: Addon builds, runs, and functions correctly

The repository is now properly consolidated with one source location. The source files in `cync-controller/` are ready to be added to version control.
