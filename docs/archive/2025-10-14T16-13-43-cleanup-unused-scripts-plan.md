<!-- 3c539595-6178-4547-b4db-e29db3907d00 a79a5e61-3d16-497c-85a8-14de2c490ae6 -->
# Cleanup Unused Scripts and Archive MITM Tools

## Phase 1: Remove Redundant MQTT Deletion Scripts

**Keep only:** `scripts/delete-mqtt-safe.py` (the safe, comprehensive solution)

**Delete these redundant scripts:**

- `scripts/nuclear-delete-mqtt.sh` - Overlaps with delete-mqtt-safe.py
- `scripts/clear-mqtt-discovery.sh` - Partial solution, superseded
- `scripts/delete-mqtt-entities-api.sh` - API-only approach, incomplete
- `scripts/delete-mqtt-entities-except-bridge.sh` - Shell wrapper for Playwright (superseded by Python)
- `scripts/delete-mqtt-completely.py` - Similar to delete-mqtt-safe.py
- `scripts/delete-mqtt-entities-permanent.py` - Redundant deletion approach
- `scripts/delete-devices.py` - Superseded by comprehensive tool

**Delete Playwright deletion scripts:**

- `scripts/playwright/delete-entities.ts` - UI automation no longer needed
- `scripts/playwright/delete-mqtt-entities.ts` - Redundant
- `scripts/playwright/delete-all-mqtt-entities-except-bridge.ts` - Superseded by Python script

## Phase 2: Archive MITM Documentation and Remove Code

Cloud relay mode has replaced MITM tools as the recommended approach.

**Move to `docs/archive/mitm/`:**

- `mitm/README.md` (security warnings)
- `mitm/MITM_TESTING_GUIDE.md`
- `mitm/FINDINGS_SUMMARY.md`
- `mitm/CLEANUP_SUMMARY.md`
- `mitm/mode_change_analysis.md`

**Delete MITM code and scripts entirely:**

- `mitm/*.py` (mitm_with_injection.py, query_mode.py, send_via_mitm.py, packet_parser.py, checksum.py, test_mode_change.py)
- `mitm/*.sh` (run_mitm.sh, restart_mitm.sh, inject_mode.sh, inject_raw.sh, create_certs.sh)
- `mitm/archive/` (entire directory - already archived historical content)
- `mitm/certs/` (keep README.md in docs, delete directory)
- `mitm/*.txt` (capture files)
- `mitm/*.log` (old logs)
- `mitm/pyproject.toml`
- `mitm/__pycache__/`

## Phase 3: Remove Unused Monitoring Script

**Delete:**

- `GUI_TEST_AUTOMATION.sh` - Unused monitoring helper (no references, easily recreatable)

## Phase 4: Update Documentation

**Update `AGENTS.md`:**

- Remove all references to deleted MQTT scripts
- Update "Debugging" section to remove MITM references
- Point users to `scripts/delete-mqtt-safe.py` for entity cleanup
- Note that MITM documentation is archived

**Update `scripts/README.md`:**

- Remove documentation for deleted scripts
- Keep only: `configure-addon.sh`, `test-cloud-relay.sh`, `run-mcp-with-env.sh`
- Add brief mention of `delete-mqtt-safe.py`

**Update `docs/developer/entity-management.md`:**

- Update to reference `delete-mqtt-safe.py` instead of shell wrappers
- Remove Playwright-based deletion workflows

**Create `docs/archive/mitm/README.md`:**

- Explain that MITM tools are archived
- Reference cloud relay mode as the modern replacement
- Preserve security warnings

## Summary

**Files to delete:** ~30 files (10+ scripts, MITM code, Playwright scripts)
**Files to move:** 5 documentation files to `docs/archive/mitm/`
**Files to update:** 3 documentation files (AGENTS.md, scripts/README.md, entity-management.md)
**Result:** Cleaner repository with only actively maintained tools